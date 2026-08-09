"""CandidateScore: six 0-5 axes with written rationale, combined into the
composite S7 selection optimises against. Weights match the spec exactly —
change them in one place (here) if the balance ever needs retuning."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from practice_forge.models.enums import DifficultyLevel, ExtensionType

AXIS_WEIGHTS = {
    "pedagogical_value": 0.25,
    "computational_suitability": 0.20,
    "self_containedness": 0.18,
    "syllabus_centrality": 0.14,
    "verifiability": 0.08,
    "ml_extension_potential": 0.15,
}


def composite_score(
    pedagogical_value: float,
    computational_suitability: float,
    self_containedness: float,
    syllabus_centrality: float,
    verifiability: float,
    ml_extension_potential: float,
) -> float:
    return (
        AXIS_WEIGHTS["pedagogical_value"] * pedagogical_value
        + AXIS_WEIGHTS["computational_suitability"] * computational_suitability
        + AXIS_WEIGHTS["self_containedness"] * self_containedness
        + AXIS_WEIGHTS["syllabus_centrality"] * syllabus_centrality
        + AXIS_WEIGHTS["verifiability"] * verifiability
        + AXIS_WEIGHTS["ml_extension_potential"] * ml_extension_potential
    )


class CandidateScore(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    concept_card_id: UUID

    pedagogical_value: float
    computational_suitability: float
    self_containedness: float
    syllabus_centrality: float
    verifiability: float
    ml_extension_potential: float

    eligible_extension_types: list[ExtensionType] = []
    composite_score: float
    difficulty: DifficultyLevel
    scoring_rationale: dict[str, str]  # axis name -> one-line written rationale

    @model_validator(mode="after")
    def _axes_in_range(self) -> "CandidateScore":
        for axis in AXIS_WEIGHTS:
            value = getattr(self, axis)
            if not 0.0 <= value <= 5.0:
                raise ValueError(f"{axis}={value} out of range [0, 5]")
        return self
