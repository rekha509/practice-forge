"""S6: candidate scoring. The six numeric axes + difficulty come from a
real batched LLM call (stage="s6_scoring"); `eligible_extension_types` is
computed deterministically in code from each ConceptCard's own gating
fields intersected with the discipline profile's `allowed_extension_types`
— never LLM-invented, per spec ("Populate eligible_extension_types[] from
gating conditions and the discipline profile"). `composite_score` reuses
the exact weighted formula already defined in `models/scoring.py`.

`physics_informed` is never auto-gated here: the spec calls it "RARE...
gate hard," which needs real judgment about whether a concept has a
genuinely clean ODE/PDE, not a mechanical rule over four booleans — left
out of the deterministic gate rather than guessed.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import BookORM, CandidateScoreORM, ConceptCardORM, DisciplineORM
from practice_forge.llm.batching import call_batch
from practice_forge.llm.client import LLMClient
from practice_forge.models.enums import DifficultyLevel, ExtensionType
from practice_forge.models.scoring import composite_score
from practice_forge.profiles.loader import load_profile

_SCORING_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "s6_candidate_scoring.md"


class ScoreBatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    pedagogical_value: float
    computational_suitability: float
    self_containedness: float
    syllabus_centrality: float
    verifiability: float
    ml_extension_potential: float
    difficulty: Literal["easy", "medium", "hard"]
    scoring_rationale: dict[str, str]


def eligible_extension_types_for(
    card: ConceptCardORM, allowed: list[ExtensionType]
) -> list[ExtensionType]:
    types: list[ExtensionType] = []
    if card.continuous_param_count >= 2 and ExtensionType.SURROGATE_MODEL in allowed:
        types.append(ExtensionType.SURROGATE_MODEL)
    if card.has_degradation_mode:
        if ExtensionType.DIGITAL_TWIN in allowed:
            types.append(ExtensionType.DIGITAL_TWIN)
        if ExtensionType.ANOMALY_DETECTION in allowed:
            types.append(ExtensionType.ANOMALY_DETECTION)
    if card.has_design_tradeoff and ExtensionType.DESIGN_OPTIMISATION in allowed:
        types.append(ExtensionType.DESIGN_OPTIMISATION)
    if card.continuous_param_count >= 3 and ExtensionType.SENSITIVITY_ANALYSIS in allowed:
        types.append(ExtensionType.SENSITIVITY_ANALYSIS)
    if card.has_tolerance_spec and ExtensionType.UNCERTAINTY_QUANTIFICATION in allowed:
        types.append(ExtensionType.UNCERTAINTY_QUANTIFICATION)
    return types


def run_scoring(session: Session, book_id: uuid.UUID, job_id: str) -> dict[str, int]:
    book = session.get(BookORM, book_id)
    if book is None:
        raise ValueError(f"No such book: {book_id}")
    discipline = session.get(DisciplineORM, book.discipline_id)
    assert discipline is not None
    profile = load_profile(discipline.key)
    allowed = profile.allowed_extension_types

    cards = (
        session.execute(select(ConceptCardORM).where(ConceptCardORM.book_id == book_id))
        .scalars()
        .all()
    )
    if not cards:
        return {"scored": 0}

    client = LLMClient()
    concepts_block = "\n---\n".join(
        f"[index {i}]\nName: {c.name}\nMethod: {c.method_tag}\n"
        f"Governing equations: {c.governing_equations_latex}\n"
        f"Given dimensions: {c.given_dimensions}\nSolve for: {c.solve_for_dimension}\n"
        f"Assumptions: {c.assumptions}"
        for i, c in enumerate(cards)
    )
    prompt = _SCORING_PROMPT_PATH.read_text(encoding="utf-8").replace(
        "{concepts_block}", concepts_block
    )

    items, _response = call_batch(
        client,
        stage="s6_scoring",
        prompt=prompt,
        job_id=job_id,
        item_model=ScoreBatchItem,
        expected_count=len(cards),
        max_tokens=6144,
    )

    scored = 0
    for card, item in zip(cards, items, strict=True):
        if item is None:
            continue
        composite = composite_score(
            item.pedagogical_value,
            item.computational_suitability,
            item.self_containedness,
            item.syllabus_centrality,
            item.verifiability,
            item.ml_extension_potential,
        )
        session.add(
            CandidateScoreORM(
                id=uuid.uuid4(),
                concept_card_id=card.id,
                pedagogical_value=item.pedagogical_value,
                computational_suitability=item.computational_suitability,
                self_containedness=item.self_containedness,
                syllabus_centrality=item.syllabus_centrality,
                verifiability=item.verifiability,
                ml_extension_potential=item.ml_extension_potential,
                eligible_extension_types=[
                    e.value for e in eligible_extension_types_for(card, allowed)
                ],
                composite_score=composite,
                difficulty=DifficultyLevel(item.difficulty),
                scoring_rationale=item.scoring_rationale,
            )
        )
        scored += 1

    session.flush()
    return {"scored": scored, "candidates": len(cards)}
