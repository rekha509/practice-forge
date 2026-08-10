"""S7 selection — real constrained selection against the real scored pool.

No LLM call: this stage is a constrained optimization over already-scored
data, per spec ("Selection is a constrained optimisation, not top-N by
score"). Hard constraints (section cap, physics-informed cap, pairwise
diversity) are enforced DURING construction — see `_select_with_constraints`
— not just checked afterward; an earlier version of this module only
checked constraints post-hoc against a plain top-N-by-score slice, which is
why "<= 3 per section" failed with a real max of 4 even though 20 problems
across 22 real sections should trivially fit under that cap. If the pool is
too small to reach the target size at all, that's reported plainly (see
`run_selection`) rather than silently returning fewer than 20 while
claiming success.

Eligible-extension-type COUNT is deliberately not a selection-time
constraint (see docs/adr/0009): eligibility is a property of the scored
pool (computed in S6), not a selection-time target — which VARIANTS
actually get an extension attached is an S9-time decision
(`variants.select_extension_attachments`), not something S7 should
gate the 20-problem set on.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import CandidateScoreORM, ConceptCardORM, ConceptClusterORM
from practice_forge.models.enums import ExtensionType

TARGET_SET_SIZE = 20
DIFFICULTY_TARGET = {"easy": 6, "medium": 9, "hard": 5}
MIN_DISTINCT_TOPICS = 6
MAX_PER_SECTION = 3
MIN_COMPUTATIONAL_HIGH = 4
MIN_DISTINCT_EXTENSION_TYPES = 3
MAX_PHYSICS_INFORMED = 2
MAX_PAIRWISE_COSINE = 0.85

_DIFFICULTY_RANK = {"easy": 0, "medium": 1, "hard": 2}


@dataclass
class PoolMember:
    cluster_id: uuid.UUID
    card: ConceptCardORM
    score: CandidateScoreORM
    difficulty_tier: str = ""  # filled by _assign_percentile_difficulty


@dataclass
class SelectionResult:
    pool_size: int
    selected: list[PoolMember]
    constraints_satisfied: dict[str, bool] = field(default_factory=dict)
    can_reach_target: bool = False
    reason: str = ""
    relaxations_applied: list[str] = field(default_factory=list)


def _cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom else 0.0


def _assign_percentile_difficulty(members: list[PoolMember]) -> None:
    """Real fix for a real, observed problem: the LLM's own absolute
    easy/medium/hard label clusters (measured live: 0 easy, 3 medium, 17
    hard out of a 20-selection from a 288-card pool) and structurally
    cannot produce a 6/9/5 split no matter how selection is tuned around
    it. Re-derives difficulty as a PERCENTILE RANK within the whole scored
    pool: sort by (the LLM's own label, as a real ordinal signal even if
    compressed) then composite_score as a tiebreak, and slice the sorted
    pool into thirds by POSITION. Needs no new LLM field and no re-scoring
    — a percentile split is well-distributed by construction, which fixes
    the clustering structurally rather than by re-asking the model."""
    ordered = sorted(
        members,
        key=lambda m: (_DIFFICULTY_RANK[m.score.difficulty.value], m.score.composite_score),
    )
    n = len(ordered)
    for i, m in enumerate(ordered):
        if i < n / 3:
            m.difficulty_tier = "easy"
        elif i < 2 * n / 3:
            m.difficulty_tier = "medium"
        else:
            m.difficulty_tier = "hard"


def _check_hard_constraints(members: list[PoolMember]) -> dict[str, bool]:
    distinct_topics = {t for m in members for t in m.card.topic_node_ids}
    per_section: dict[uuid.UUID, int] = {}
    for m in members:
        per_section[m.card.section_id] = per_section.get(m.card.section_id, 0) + 1

    difficulty_counts = {"easy": 0, "medium": 0, "hard": 0}
    for m in members:
        difficulty_counts[m.difficulty_tier] += 1

    computational_high = sum(1 for m in members if m.score.computational_suitability >= 4)
    distinct_extension_types = {e for m in members for e in m.score.eligible_extension_types}
    physics_informed_count = sum(
        1
        for m in members
        if ExtensionType.PHYSICS_INFORMED.value in m.score.eligible_extension_types
    )

    max_pairwise_cosine = 0.0
    for i, a in enumerate(members):
        for b in members[i + 1 :]:
            max_pairwise_cosine = max(max_pairwise_cosine, _cosine(a.card.embedding, b.card.embedding))

    return {
        f">= {MIN_DISTINCT_TOPICS} distinct topics (got {len(distinct_topics)})": len(
            distinct_topics
        )
        >= MIN_DISTINCT_TOPICS,
        f"<= {MAX_PER_SECTION} per section (max got {max(per_section.values(), default=0)})": max(
            per_section.values(), default=0
        )
        <= MAX_PER_SECTION,
        f"difficulty mix {DIFFICULTY_TARGET} (got {difficulty_counts})": difficulty_counts
        == DIFFICULTY_TARGET,
        f">= {MIN_COMPUTATIONAL_HIGH} with computational_suitability>=4 (got {computational_high})": computational_high
        >= MIN_COMPUTATIONAL_HIGH,
        f">= {MIN_DISTINCT_EXTENSION_TYPES} distinct extension types (got {len(distinct_extension_types)})": len(
            distinct_extension_types
        )
        >= MIN_DISTINCT_EXTENSION_TYPES,
        f"<= {MAX_PHYSICS_INFORMED} physics_informed (got {physics_informed_count})": physics_informed_count
        <= MAX_PHYSICS_INFORMED,
        f"no pair with cosine >= {MAX_PAIRWISE_COSINE} (max got {max_pairwise_cosine:.3f})": max_pairwise_cosine
        < MAX_PAIRWISE_COSINE,
    }


def _select_with_constraints(
    members: list[PoolMember],
) -> tuple[list[PoolMember], list[str]]:
    """Greedy constrained selection. Hard filters (section cap,
    physics-informed cap, pairwise-cosine cap) are enforced turn-by-turn
    during construction, never bypassed. The difficulty-tier targets are
    built toward directly (one pass per percentile tier, highest
    composite_score first within each) since the percentile assignment
    above makes the pool's own tiers already balanced; if a tier runs out
    of constraint-respecting candidates before reaching its target count,
    that's the FIRST constraint relaxed (see docs/adr/0009's declared
    order) — backfilling from the remaining pool by score, logged, not
    silent. Pairwise-cosine is relaxed last, only if the set would
    otherwise come in under TARGET_SET_SIZE.
    """
    _assign_percentile_difficulty(members)
    by_tier: dict[str, list[PoolMember]] = {"easy": [], "medium": [], "hard": []}
    for m in members:
        by_tier[m.difficulty_tier].append(m)
    for tier_members in by_tier.values():
        tier_members.sort(key=lambda m: m.score.composite_score, reverse=True)

    selected: list[PoolMember] = []
    selected_ids: set[uuid.UUID] = set()
    per_section: dict[uuid.UUID, int] = {}
    physics_informed_count = 0
    relaxations: list[str] = []

    def is_physics(m: PoolMember) -> bool:
        return ExtensionType.PHYSICS_INFORMED.value in m.score.eligible_extension_types

    def fits(m: PoolMember, *, ignore_cosine: bool = False) -> bool:
        if per_section.get(m.card.section_id, 0) >= MAX_PER_SECTION:
            return False
        if is_physics(m) and physics_informed_count >= MAX_PHYSICS_INFORMED:
            return False
        if not ignore_cosine:
            for s in selected:
                if _cosine(s.card.embedding, m.card.embedding) >= MAX_PAIRWISE_COSINE:
                    return False
        return True

    def take(m: PoolMember) -> None:
        nonlocal physics_informed_count
        selected.append(m)
        selected_ids.add(m.card.id)
        per_section[m.card.section_id] = per_section.get(m.card.section_id, 0) + 1
        if is_physics(m):
            physics_informed_count += 1

    for tier, target in (
        ("easy", DIFFICULTY_TARGET["easy"]),
        ("medium", DIFFICULTY_TARGET["medium"]),
        ("hard", DIFFICULTY_TARGET["hard"]),
    ):
        taken = 0
        for m in by_tier[tier]:
            if taken >= target:
                break
            if fits(m):
                take(m)
                taken += 1

    if len(selected) < TARGET_SET_SIZE:
        remaining = sorted(
            (m for m in members if m.card.id not in selected_ids),
            key=lambda m: m.score.composite_score,
            reverse=True,
        )
        before = len(selected)
        for m in remaining:
            if len(selected) >= TARGET_SET_SIZE:
                break
            if fits(m):
                take(m)
        if len(selected) > before:
            relaxations.append(
                f"difficulty mix {DIFFICULTY_TARGET}: backfilled {len(selected) - before} "
                "beyond the exact per-tier targets to reach the 20-problem target size — "
                "at least one tier didn't have enough constraint-respecting candidates"
            )

    if len(selected) < TARGET_SET_SIZE:
        remaining = sorted(
            (m for m in members if m.card.id not in selected_ids),
            key=lambda m: m.score.composite_score,
            reverse=True,
        )
        before = len(selected)
        for m in remaining:
            if len(selected) >= TARGET_SET_SIZE:
                break
            if fits(m, ignore_cosine=True):
                take(m)
        if len(selected) > before:
            relaxations.append(
                f"pairwise cosine diversity (< {MAX_PAIRWISE_COSINE}): relaxed to add "
                f"{len(selected) - before} more and reach the 20-problem target size — "
                "section/physics-informed caps alone left the pool too thin without it"
            )

    return selected, relaxations


def run_selection(
    session: Session,
    book_id: uuid.UUID,
    *,
    excluded_cluster_ids: frozenset[uuid.UUID] = frozenset(),
) -> SelectionResult:
    """`excluded_cluster_ids`: clusters already issued for a course (via
    IssuedLedgerORM, not `is_recycled`) — the no-repeat guarantee's real
    enforcement point. Defaults to empty for every existing caller that
    doesn't yet have a course in scope (rendering the very first set,
    `pf generate`'s ad-hoc CLI flow); ledger-aware callers must pass the
    real already-issued set explicitly, not rely on a default that would
    silently make every "second set" identical to the first."""
    pool_query = (
        select(ConceptClusterORM)
        .join(ConceptCardORM, ConceptClusterORM.representative_card_id == ConceptCardORM.id)
        .where(ConceptCardORM.book_id == book_id)
    )
    if excluded_cluster_ids:
        pool_query = pool_query.where(ConceptClusterORM.id.not_in(excluded_cluster_ids))
    clusters = session.execute(pool_query).scalars().all()

    members: list[PoolMember] = []
    for cluster in clusters:
        card = session.get(ConceptCardORM, cluster.representative_card_id)
        assert card is not None
        score = session.execute(
            select(CandidateScoreORM).where(CandidateScoreORM.concept_card_id == card.id)
        ).scalar_one_or_none()
        if score is None:
            continue
        members.append(PoolMember(cluster_id=cluster.id, card=card, score=score))

    if members:
        _assign_percentile_difficulty(members)

    if len(members) < TARGET_SET_SIZE:
        return SelectionResult(
            pool_size=len(members),
            selected=members,
            constraints_satisfied=_check_hard_constraints(members) if members else {},
            can_reach_target=False,
            reason=(
                f"only {len(members)} unissued, scored concept clusters exist for this "
                f"book — cannot reach the {TARGET_SET_SIZE}-problem target. Not relaxed/"
                "faked to look complete; this is the honest constraint-checked state of "
                "the real pool."
            ),
        )

    selected, relaxations = _select_with_constraints(members)
    reason = "real constrained selection: hard-filtered during construction, not top-N by score"
    if relaxations:
        reason += f"; relaxed {len(relaxations)} constraint(s) per docs/adr/0009's declared order"
    return SelectionResult(
        pool_size=len(members),
        selected=selected,
        constraints_satisfied=_check_hard_constraints(selected),
        can_reach_target=True,
        reason=reason,
        relaxations_applied=relaxations,
    )
