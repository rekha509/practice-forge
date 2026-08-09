"""Enumerations shared across the data model."""

from __future__ import annotations

from enum import StrEnum


class IngestStatus(StrEnum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    STRUCTURING = "structuring"
    DONE = "done"
    FAILED = "failed"
    DEDUPED = "deduped"  # reused an existing canonical Book, no fresh ingest performed


class ProblemKind(StrEnum):
    WORKED_EXAMPLE = "worked_example"
    EXERCISE = "exercise"
    DERIVATION = "derivation"


class FigureDependency(StrEnum):
    NONE = "none"
    DECORATIVE = "decorative"
    ESSENTIAL = "essential"


class FigureKind(StrEnum):
    BEAM_DIAGRAM = "beam_diagram"
    TRUSS = "truss"
    CIRCUIT = "circuit"
    FREE_BODY = "free_body"
    MOHR_CIRCLE = "mohr_circle"
    SHAFT = "shaft"
    CYCLE_DIAGRAM = "cycle_diagram"
    FLOWSHEET = "flowsheet"
    PLOT = "plot"
    OTHER = "other"


class ExtensionType(StrEnum):
    NONE = "none"
    SURROGATE_MODEL = "surrogate_model"
    DIGITAL_TWIN = "digital_twin"
    ANOMALY_DETECTION = "anomaly_detection"
    DESIGN_OPTIMISATION = "design_optimisation"
    SENSITIVITY_ANALYSIS = "sensitivity_analysis"
    UNCERTAINTY_QUANTIFICATION = "uncertainty_quantification"
    PHYSICS_INFORMED = "physics_informed"


class DifficultyLevel(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class VerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
