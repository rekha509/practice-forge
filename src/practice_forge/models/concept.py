"""ConceptCard is the unit concept-level dedup operates on. concept_fingerprint
must be a pure function of physics-identity fields — never of wording, numbers,
or the source book — so that S1 dedup, S5 fingerprinting and S7 selection agree
on what "the same problem" means."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ConceptCard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    book_id: UUID
    section_id: UUID
    name: str
    topic_node_ids: list[UUID] = []
    governing_equations_latex: list[str]
    canonical_equation_srepr: list[str]
    assumptions: list[str] = []
    solution_strategy: str
    typical_pitfalls: list[str] = []
    given_dimensions: list[str]  # e.g. ["[length]", "[force]", "[force]/[length]**2"]
    solve_for_dimension: str
    method_tag: str

    # Extension-gating fields (S6 reads these to populate eligible_extension_types)
    continuous_param_count: int = 0
    has_degradation_mode: bool = False
    has_design_tradeoff: bool = False
    has_tolerance_spec: bool = False

    concept_fingerprint: str  # sha256, see fingerprint.py
    embedding: list[float]
    source_pages: list[int] = []


class ConceptCluster(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    discipline_id: UUID
    representative_card_id: UUID
    member_card_ids: list[UUID]
    centroid_embedding: list[float]
