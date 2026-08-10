"""S8: variant generation.

Real LLM call per selected concept: new numeric parameters, a rewritten
self-contained problem statement, and a step-by-step solution APPROACH.
Deliberately not a trusted final answer here — S9 (codegen.py) computes
the real numeric result independently by running actual code, and that
execution result is what `Variant.verified_answer` records, never
anything asserted by this stage.

Extension attachment (docs/adr/0009): eligibility is a pool property
computed in S6 (`CandidateScore.eligible_extension_types`) — a boolean
per type, per concept. Whether an extension actually gets ATTACHED to a
generated variant is decided here, at generation time, not gated into S7
selection: `select_extension_attachments` picks at most
MAX_EXTENSION_ATTACHMENTS of the selected set, ranked by
`ml_extension_potential`, while making sure the attached set spans
`MIN_DISTINCT_EXTENSION_TYPES` distinct types.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from practice_forge.db.models import ConceptCardORM, SourceProblemORM, VariantORM
from practice_forge.llm.client import LLMClient
from practice_forge.llm.sanitize import strip_nul, strip_nul_list
from practice_forge.models.enums import DifficultyLevel, ExtensionType, VerificationStatus
from practice_forge.selection.selection import PoolMember

MAX_EXTENSION_ATTACHMENTS = 12
MIN_DISTINCT_EXTENSION_TYPES = 3

_VARIANT_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "s8_variant_generation.md"


class VariantGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_params: dict[str, float | str]
    statement_md: str
    solution_steps: list[str]


def select_extension_attachments(
    members: list[PoolMember],
) -> dict[uuid.UUID, ExtensionType | None]:
    """Real S9-time rule (docs/adr/0009), keyed by ConceptCard.id. Ranks
    eligible members by ml_extension_potential; a first pass prioritizes
    reaching MIN_DISTINCT_EXTENSION_TYPES by only taking an unused type
    per member, then a second pass fills the remaining budget by pure
    rank regardless of type repeats."""
    attachments: dict[uuid.UUID, ExtensionType | None] = {m.card.id: None for m in members}
    eligible = [m for m in members if m.score.eligible_extension_types]
    ranked = sorted(eligible, key=lambda m: m.score.ml_extension_potential, reverse=True)

    used_types: set[str] = set()
    attached_count = 0
    for m in ranked:
        if attached_count >= MAX_EXTENSION_ATTACHMENTS or len(used_types) >= MIN_DISTINCT_EXTENSION_TYPES:
            break
        for t in m.score.eligible_extension_types:
            if t not in used_types:
                attachments[m.card.id] = ExtensionType(t)
                used_types.add(t)
                attached_count += 1
                break

    for m in ranked:
        if attached_count >= MAX_EXTENSION_ATTACHMENTS:
            break
        if attachments[m.card.id] is not None:
            continue
        attachments[m.card.id] = ExtensionType(m.score.eligible_extension_types[0])
        attached_count += 1

    return attachments


def generate_variant(
    client: LLMClient,
    job_id: str,
    cluster_id: uuid.UUID,
    card: ConceptCardORM,
    source_problem: SourceProblemORM,
    difficulty_tier: str,
) -> VariantORM | None:
    """One real LLM call. Returns None (logged by the caller, not raised)
    if the model's response doesn't parse — a single bad variant must not
    abort generation for the rest of the selected set."""
    prompt = (
        _VARIANT_PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{name}", card.name)
        .replace("{equations}", ", ".join(card.governing_equations_latex))
        .replace("{method_tag}", card.method_tag)
        .replace("{assumptions}", ", ".join(card.assumptions))
        .replace("{given_dimensions}", ", ".join(card.given_dimensions))
        .replace("{solve_for_dimension}", card.solve_for_dimension)
        .replace("{original_statement}", source_problem.statement_md[:2000])
    )
    response = client.complete(
        stage="s8_variant_generation",
        prompt=prompt,
        job_id=job_id,
        max_tokens=4096,
        output_schema=VariantGenerationResult.model_json_schema(),
    )
    try:
        result = VariantGenerationResult.model_validate(json.loads(response.text))
    except (json.JSONDecodeError, ValidationError):
        return None

    return VariantORM(
        id=uuid.uuid4(),
        concept_cluster_id=cluster_id,
        statement_md=strip_nul(result.statement_md),
        params=result.new_params,
        difficulty=DifficultyLevel(difficulty_tier),
        topic_node_ids=card.topic_node_ids,
        solution_steps=strip_nul_list(result.solution_steps),
        core_python_code="",  # filled in by S9 (codegen.py)
        extension_type=ExtensionType.NONE,  # set by the caller if attached
        extension_python_code=None,
        extension_learning_notes=None,
        extension_figure_paths=[],
        extension_metrics_json=None,
        verified_answer=None,
        verification_status=VerificationStatus.PENDING,
        verification_log=[],
        needs_review=False,
        source_ref={
            "source_problem_id": str(source_problem.id),
            "book_id": str(source_problem.book_id),
            "page_no": source_problem.page_no,
        },
        is_recycled=False,
    )
