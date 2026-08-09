"""S5: concept distillation, fingerprinting, and clustering.

Batched (one call for all of a book's solvable problems — see
docs/adr/0006, the same free-tier RPD constraint that forced S3's batching)
into `ConceptCard` rows, fingerprinted via `concepts.fingerprint`, embedded
via `concepts.embedding` (Gemini, not BGE-M3 — docs/adr/0008), and
clustered: identical fingerprints OR cosine >= 0.92 collapse into one
`ConceptCluster`, per spec.

Only `SourceProblem` rows with `is_solvable=True` are distilled — S4's
figure-dependent exclusions (docs/adr/0007) never reach this stage.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.concepts.embedding import embed_texts
from practice_forge.concepts.fingerprint import canonicalize_equation, concept_fingerprint
from practice_forge.config import get_settings
from practice_forge.db.models import BookORM, ConceptCardORM, ConceptClusterORM, SourceProblemORM
from practice_forge.llm.batching import call_batch
from practice_forge.llm.client import LLMClient

CLUSTER_COSINE_THRESHOLD = 0.92

# Smaller than S3's BATCH_SIZE=20: this stage's per-item schema carries far
# more free-text fields (equations, assumptions, pitfalls, solution
# strategy) than S3's confirm pass, so the same item count risks a bigger
# batch response than max_tokens allows. A single unbatched call for a
# whole book (as this stage originally did) breaks at real book scale —
# found live while sizing the 700-page projection, not from a test.
BATCH_SIZE = 10

_DISTILLATION_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "s5_concept_distillation.md"
)


class DistillationBatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    name: str
    governing_equations_latex: list[str]
    assumptions: list[str] = []
    solution_strategy: str
    typical_pitfalls: list[str] = []
    given_dimensions: list[str]
    solve_for_dimension: str
    method_tag: str
    continuous_param_count: int = 0
    has_degradation_mode: bool = False
    has_design_tradeoff: bool = False
    has_tolerance_spec: bool = False


def _chunked(
    items: Sequence[SourceProblemORM], size: int
) -> list[Sequence[SourceProblemORM]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def run_concept_distillation(
    session: Session, book_id: uuid.UUID, job_id: str, llm_client: LLMClient | None = None
) -> dict[str, int]:
    book = session.get(BookORM, book_id)
    if book is None:
        raise ValueError(f"No such book: {book_id}")

    problems = (
        session.execute(
            select(SourceProblemORM).where(
                SourceProblemORM.book_id == book_id,
                SourceProblemORM.is_solvable.is_(True),
            )
        )
        .scalars()
        .all()
    )
    if not problems:
        return {"distilled": 0, "parse_failures": 0, "clusters": 0}

    client = llm_client or LLMClient()
    settings = get_settings()
    cards: list[ConceptCardORM] = []
    parse_failures = 0
    texts_to_embed: list[str] = []

    for batch_no, batch in enumerate(_chunked(problems, BATCH_SIZE)):
        problems_block = "\n---\n".join(
            f"[index {i}]\nStatement: {p.statement_md}\n"
            f"Given: {p.given}\nFind: {p.find}\nAnswer: {p.final_answer}"
            for i, p in enumerate(batch)
        )
        # .replace(), not .format(): problem text can itself contain literal
        # `{`/`}` (LaTeX, OCR artifacts) that .format() misparses as
        # placeholders — this exact failure happened live on this book's
        # content (see detection.py's identical fix).
        prompt = _DISTILLATION_PROMPT_PATH.read_text(encoding="utf-8").replace(
            "{problems_block}", problems_block
        )

        items, _response = call_batch(
            client,
            stage="s5_distillation",
            prompt=prompt,
            job_id=f"{job_id}-batch{batch_no}",
            item_model=DistillationBatchItem,
            expected_count=len(batch),
            max_tokens=8192,
        )

        for problem, item in zip(batch, items, strict=True):
            if item is None:
                continue

            canonical_reprs = []
            for eq in item.governing_equations_latex:
                repr_str = canonicalize_equation(eq)
                if repr_str.startswith("UNPARSED::"):
                    parse_failures += 1
                canonical_reprs.append(repr_str)

            fingerprint = concept_fingerprint(
                canonical_reprs, item.given_dimensions, item.solve_for_dimension, item.method_tag
            )

            embed_text = f"{item.name}. {item.solution_strategy}. Method: {item.method_tag}"
            texts_to_embed.append(embed_text)

            card = ConceptCardORM(
                id=uuid.uuid4(),
                book_id=book_id,
                section_id=problem.section_id,
                name=item.name,
                topic_node_ids=[],
                governing_equations_latex=item.governing_equations_latex,
                canonical_equation_srepr=canonical_reprs,
                assumptions=item.assumptions,
                solution_strategy=item.solution_strategy,
                typical_pitfalls=item.typical_pitfalls,
                given_dimensions=item.given_dimensions,
                solve_for_dimension=item.solve_for_dimension,
                method_tag=item.method_tag,
                continuous_param_count=item.continuous_param_count,
                has_degradation_mode=item.has_degradation_mode,
                has_design_tradeoff=item.has_design_tradeoff,
                has_tolerance_spec=item.has_tolerance_spec,
                concept_fingerprint=fingerprint,
                embedding=[0.0] * 3072,  # placeholder, filled in below
                source_pages=[problem.page_no],
            )
            cards.append(card)

    embeddings = embed_texts(settings.gemini_api_key, texts_to_embed)
    for card, embedding in zip(cards, embeddings, strict=True):
        card.embedding = embedding
        session.add(card)
    session.flush()

    clusters = _cluster_cards(session, book.discipline_id, cards)

    return {
        "distilled": len(cards),
        "parse_failures": parse_failures,
        "clusters": len(clusters),
    }


def _cluster_cards(
    session: Session, discipline_id: uuid.UUID, cards: list[ConceptCardORM]
) -> list[ConceptClusterORM]:
    """Identical fingerprints OR cosine >= 0.92 collapse into one cluster.
    Greedy: walk cards in order, attach to the first existing cluster that
    matches either condition against its representative, else start a new
    cluster."""
    clusters: list[ConceptClusterORM] = []

    for card in cards:
        matched: ConceptClusterORM | None = None
        for cluster in clusters:
            rep = session.get(ConceptCardORM, cluster.representative_card_id)
            assert rep is not None
            if rep.concept_fingerprint == card.concept_fingerprint:
                matched = cluster
                break
            if _cosine(rep.embedding, card.embedding) >= CLUSTER_COSINE_THRESHOLD:
                matched = cluster
                break

        if matched is not None:
            matched.member_card_ids = [*matched.member_card_ids, card.id]
        else:
            new_cluster = ConceptClusterORM(
                id=uuid.uuid4(),
                discipline_id=discipline_id,
                representative_card_id=card.id,
                member_card_ids=[card.id],
                centroid_embedding=card.embedding,
            )
            session.add(new_cluster)
            clusters.append(new_cluster)

    session.flush()
    return clusters
