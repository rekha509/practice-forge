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
from collections.abc import Iterator
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf._page import PageObject

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


def _extract_one_page(page: PageObject, page_no: int) -> PageExtraction:
    # Real bug, hit live at full-book (781-page) scale, never at the
    # 30/80-page excerpts: pypdf occasionally extracts a literal NUL
    # (0x00) byte from certain embedded fonts/OCR artifacts, which
    # Postgres text columns reject outright ("PostgreSQL text fields
    # cannot contain NUL bytes") — and since that surfaces at INSERT
    # time, not extraction time, it silently poisoned an entire
    # already-LLM-confirmed batch downstream. Stripped at the source
    # so every consumer is protected, not just the one that happened
    # to trip over it first.
    text = (page.extract_text() or "").replace("\x00", "")
    return PageExtraction(
        page_no=page_no,
        markdown=text,
        has_math=bool(_MATH_HINTS.search(text)),
        has_figure=len(page.images) > 0 if hasattr(page, "images") else False,
        unit_system_detected=_detect_unit_system(text),
        extraction_confidence=0.9 if text.strip() else 0.1,
    )


def page_count(pdf_path: str) -> int:
    """Cheap: PDF page count lives in the file's page tree, not its
    content — reading it doesn't require extracting any page text. Used to
    give a real ETA denominator before extraction (which IS per-page work)
    even starts."""
    return len(PdfReader(pdf_path).pages)


def iter_pages(pdf_path: str) -> Iterator[PageExtraction]:
    """Same real per-page extraction as `extract_pages`, but yielded one
    page at a time so a caller (see
    `ingest/pipeline.py::run_ingest_resumable`) can persist and commit
    after each page — real crash-resume at page granularity, not just
    "resume once the whole file has been extracted." `extract_pages` below
    is unchanged and still extracts everything into memory first; this
    doesn't replace it, existing callers (`pf ingest`) are unaffected."""
    reader = PdfReader(pdf_path)
    for i, page in enumerate(reader.pages, start=1):
        yield _extract_one_page(page, i)


def extract_pages(pdf_path: str) -> list[PageExtraction]:
    return list(iter_pages(pdf_path))
