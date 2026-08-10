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
from practice_forge.llm.sanitize import strip_nul, strip_nul_list

CLUSTER_COSINE_THRESHOLD = 0.92

# Raised 10 -> 30 (2026-08-10) alongside moving this stage off
# gemini-flash-latest onto gemini-flash-lite-latest (see docs/adr/0006's
# addendum): flash-lite doesn't spend thinking tokens against the same
# output budget the way flash-latest did, so the same max_tokens covers a
# bigger batch comfortably — the 10-item batches that hit MAX_TOKENS on
# flash-latest used ~3800-4200 tokens of pure JSON output plus ~2400-7100
# more on thinking; 30 items of JSON alone (~11000-13000 tokens estimated)
# still fits well under max_tokens=16384 with the thinking tax gone.
BATCH_SIZE = 30

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

    # Idempotency: skip any problem that already has a card (natural key —
    # migration 0003 makes source_problem_id NOT NULL + UNIQUE, so this is
    # a real guard, not just an application-level convention). Filtering
    # before batching also means a re-run doesn't re-spend LLM quota on
    # problems it's already distilled.
    already_distilled = set(
        session.execute(
            select(ConceptCardORM.source_problem_id).where(
                ConceptCardORM.source_problem_id.in_([p.id for p in problems])
            )
        )
        .scalars()
        .all()
    )
    problems = [p for p in problems if p.id not in already_distilled]

    if not problems:
        return {"distilled": 0, "parse_failures": 0, "clusters": 0}

    client = llm_client or LLMClient()
    settings = get_settings()
    cards: list[ConceptCardORM] = []
    parse_failures = 0

    for batch_no, batch in enumerate(_chunked(problems, BATCH_SIZE)):
        batch_cards: list[ConceptCardORM] = []
        batch_texts_to_embed: list[str] = []
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
            # Found live at full-book scale: 8192 wasn't enough headroom —
            # gemini-flash-latest's thinking tokens draw from the SAME
            # budget as visible output (extra_tokens + output_tokens
            # landed right at 8192 on the batches that failed), truncating
            # the JSON array mid-response and silently zeroing every item
            # in that batch (call_batch can't parse a truncated array).
            # Confirmed: exactly the 2 batches that hit MAX_TOKENS produced
            # 0 cards each; every STOP-reason batch parsed fully.
            max_tokens=16384,
        )

        for problem, item in zip(batch, items, strict=True):
            if item is None:
                continue

            # NUL bytes (0x00) crash Postgres text columns outright — found
            # live at full-book scale in S3's LLM-generated fields (see
            # llm/sanitize.py); every stage persisting free-text LLM output
            # has the same exposure, not just the one that hit it first.
            equations = strip_nul_list(item.governing_equations_latex)
            given_dimensions = strip_nul_list(item.given_dimensions)
            solve_for_dimension = strip_nul(item.solve_for_dimension)
            method_tag = strip_nul(item.method_tag)

            canonical_reprs = []
            for eq in equations:
                repr_str = canonicalize_equation(eq)
                if repr_str.startswith("UNPARSED::"):
                    parse_failures += 1
                canonical_reprs.append(repr_str)

            fingerprint = concept_fingerprint(
                canonical_reprs, given_dimensions, solve_for_dimension, method_tag
            )

            name = strip_nul(item.name)
            solution_strategy = strip_nul(item.solution_strategy)
            embed_text = f"{name}. {solution_strategy}. Method: {method_tag}"
            batch_texts_to_embed.append(embed_text)

            card = ConceptCardORM(
                id=uuid.uuid4(),
                book_id=book_id,
                section_id=problem.section_id,
                source_problem_id=problem.id,
                name=name,
                topic_node_ids=[],
                governing_equations_latex=equations,
                canonical_equation_srepr=canonical_reprs,
                assumptions=strip_nul_list(item.assumptions),
                solution_strategy=solution_strategy,
                typical_pitfalls=strip_nul_list(item.typical_pitfalls),
                given_dimensions=given_dimensions,
                solve_for_dimension=solve_for_dimension,
                method_tag=method_tag,
                continuous_param_count=item.continuous_param_count,
                has_degradation_mode=item.has_degradation_mode,
                has_design_tradeoff=item.has_design_tradeoff,
                has_tolerance_spec=item.has_tolerance_spec,
                concept_fingerprint=fingerprint,
                embedding=[0.0] * 3072,  # placeholder, filled in below
                source_pages=[problem.page_no],
            )
            batch_cards.append(card)

        # Commit per batch, not once at the end: found live at real
        # book/quota scale — a later batch hitting the daily quota wall
        # (DailyQuotaExhausted, or a real 429 if our own configured RPD
        # was stale) previously discarded every earlier batch's already-
        # paid-for distillation, same class of bug S3's run_detection had
        # (see detection.py). Embeddings are computed per batch too (well
        # under gemini-embedding-001's 100-item cap at BATCH_SIZE=10) so a
        # batch's cards are fully formed before they're added.
        if batch_cards:
            batch_embeddings = embed_texts(settings.gemini_api_key, batch_texts_to_embed)
            for card, embedding in zip(batch_cards, batch_embeddings, strict=True):
                card.embedding = embedding
                session.add(card)
            session.flush()
            cards.extend(batch_cards)
            session.commit()

    clusters = _cluster_cards(session, book.discipline_id, cards)
    session.commit()

    return {
        "distilled": len(cards),
        "parse_failures": parse_failures,
        "clusters": len(clusters),
    }


def _cluster_cards(
    session: Session, discipline_id: uuid.UUID, cards: list[ConceptCardORM]
) -> list[ConceptClusterORM]:
    """Identical fingerprints OR cosine >= 0.92 collapse into one cluster.
    Greedy: walk cards in order, attach to the first matching cluster
    (existing or newly created this call), else start a new cluster.

    Clusters are the no-repeat guarantee's unit of truth (IssuedLedger
    keys on them) and are scoped by discipline, not by book — the whole
    point is catching a duplicate concept across different ingests of the
    same course. Matching only against `cards` (this call's batch, as an
    earlier version did) silently breaks that across any second S5 run —
    idempotency's own filtering makes `cards` frequently empty or partial
    on a resumed/re-run, and a genuine duplicate of an earlier run's
    concept would land in its own new cluster instead of merging. So every
    call loads this discipline's EXISTING clusters first and matches new
    cards against those too, not just against each other."""
    existing_clusters = list(
        session.execute(
            select(ConceptClusterORM).where(ConceptClusterORM.discipline_id == discipline_id)
        )
        .scalars()
        .all()
    )
    clusters: list[ConceptClusterORM] = list(existing_clusters)
    touched: list[ConceptClusterORM] = []

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
            if matched not in touched:
                touched.append(matched)
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
            touched.append(new_cluster)

    session.flush()
    return touched
