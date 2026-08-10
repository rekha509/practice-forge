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
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import BookORM, CandidateScoreORM, ConceptCardORM, DisciplineORM
from practice_forge.llm.batching import call_batch
from practice_forge.llm.client import LLMClient
from practice_forge.llm.sanitize import strip_nul
from practice_forge.models.enums import DifficultyLevel, ExtensionType
from practice_forge.models.scoring import composite_score
from practice_forge.profiles.loader import load_profile

_SCORING_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "s6_candidate_scoring.md"

# A single unbatched call for a whole book (as this stage originally did)
# breaks at real book scale — found live while sizing the 700-page
# projection, not from a test. 15 rather than S3's 20: each item carries a
# scoring_rationale dict with free-text per axis, heavier than S3's schema.
BATCH_SIZE = 15


def _chunked(items: Sequence[ConceptCardORM], size: int) -> list[Sequence[ConceptCardORM]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


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


def run_scoring(
    session: Session, book_id: uuid.UUID, job_id: str, llm_client: LLMClient | None = None
) -> dict[str, int]:
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
    total_candidates = len(cards)
    if not cards:
        return {"scored": 0, "candidates": 0}

    # Idempotency: skip any card that already has a score (concept_card_id
    # is UNIQUE on candidate_scores — a real DB guard, not just an
    # application-level check). Filtering before batching also means a
    # re-run doesn't re-spend LLM quota on cards already scored.
    already_scored = set(
        session.execute(
            select(CandidateScoreORM.concept_card_id).where(
                CandidateScoreORM.concept_card_id.in_([c.id for c in cards])
            )
        )
        .scalars()
        .all()
    )
    cards = [c for c in cards if c.id not in already_scored]
    if not cards:
        return {"scored": 0, "candidates": total_candidates}

    client = llm_client or LLMClient()
    scored = 0

    for batch_no, batch in enumerate(_chunked(cards, BATCH_SIZE)):
        concepts_block = "\n---\n".join(
            f"[index {i}]\nName: {c.name}\nMethod: {c.method_tag}\n"
            f"Governing equations: {c.governing_equations_latex}\n"
            f"Given dimensions: {c.given_dimensions}\nSolve for: {c.solve_for_dimension}\n"
            f"Assumptions: {c.assumptions}"
            for i, c in enumerate(batch)
        )
        prompt = _SCORING_PROMPT_PATH.read_text(encoding="utf-8").replace(
            "{concepts_block}", concepts_block
        )

        items, _response = call_batch(
            client,
            stage="s6_scoring",
            prompt=prompt,
            job_id=f"{job_id}-batch{batch_no}",
            item_model=ScoreBatchItem,
            expected_count=len(batch),
            max_tokens=6144,
        )

        for card, item in zip(batch, items, strict=True):
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
                    # NUL bytes (0x00) crash Postgres text/JSONB columns
                    # outright — found live at full-book scale in S3's
                    # LLM-generated fields (see llm/sanitize.py); the same
                    # exposure applies to any free-text LLM output.
                    scoring_rationale={
                        strip_nul(k): strip_nul(v) for k, v in item.scoring_rationale.items()
                    },
                )
            )
            scored += 1

        # Commit per batch, not once at the end — a later batch hitting a
        # quota wall must not discard earlier batches' already-paid-for
        # scores (same bug class fixed in detection.py and concepts.py).
        session.commit()

    return {"scored": scored, "candidates": total_candidates}
