"""Figure interpretation results. structured_spec_json is the ONLY form a figure
takes downstream — the raw image never reaches the solver or the LLM solving stage."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from practice_forge.models.enums import FigureKind


class Figure(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    book_id: UUID
    page_no: int
    label: str | None = None
    image_path: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 in PDF page coordinates
    figure_kind: FigureKind
    structured_spec_json: dict[str, Any] | None = None
    interpretation_confidence: float = 0.0
