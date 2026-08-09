"""Per-page text extraction (S1c).

Real implementation per TECH STACK is marker-pdf with --use_llm (plus a
full-page VLM fallback for math-heavy/scanned pages) — a large ML-based
PDF-to-markdown converter. Wiring that in is deferred (see docs/adr/0004):
it needs real model weights and is overkill to stand up just to prove the
dedup/persistence logic this phase's gate actually checks. `pypdf` gives
real per-page text for genuinely text-based PDFs today; swapping in marker
later only touches this one function.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pypdf import PdfReader

_MATH_HINTS = re.compile(r"[=∫∑√±×÷≤≥∂∇]|\\frac|\\int|\\sum")
_UNIT_HINTS = {
    "SI": re.compile(r"\bN/mm|\bMPa\b|\bkN\b|\bkg\b|\bm/s\b"),
    "Indian-mixed": re.compile(r"\bkgf\b|\bkgf/cm|\bbar\b"),
    "imperial": re.compile(r"\bpsi\b|\blbf\b|\bft-lb"),
}


@dataclass(frozen=True)
class PageExtraction:
    page_no: int
    markdown: str
    has_math: bool
    has_figure: bool
    unit_system_detected: str | None
    extraction_confidence: float


def _detect_unit_system(text: str) -> str | None:
    for system, pattern in _UNIT_HINTS.items():
        if pattern.search(text):
            return system
    return None


def extract_pages(pdf_path: str) -> list[PageExtraction]:
    reader = PdfReader(pdf_path)
    pages: list[PageExtraction] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(
            PageExtraction(
                page_no=i,
                markdown=text,
                has_math=bool(_MATH_HINTS.search(text)),
                has_figure=len(page.images) > 0 if hasattr(page, "images") else False,
                unit_system_detected=_detect_unit_system(text),
                extraction_confidence=0.9 if text.strip() else 0.1,
            )
        )
    return pages
