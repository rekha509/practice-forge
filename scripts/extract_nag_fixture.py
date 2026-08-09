"""One-off extraction of a real 30-page span from the P.K. Nag Engineering
Thermodynamics textbook (repo root, gitignored — the full book is never
committed) into tests/fixtures/nag_real.pdf.

Span chosen: Chapter 5, "First Law Applied to Flow Processes" — PDF page
indices 86-115 inclusive (0-indexed), located by reading the table of
contents (PDF pages 2-6) and confirming chapter start/end boundaries
against the actual page content, not by trusting the TOC's own printed
page numbers (this is a scanned/OCR'd book; printed-page-to-PDF-index
offset is not constant throughout). Dense with solved numerical examples
and end-of-chapter problems — exactly the shape S1-S3 need real content
to run against.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter

SOURCE = Path(__file__).resolve().parents[1] / "Thermodynamics by PK Nag.pdf"
DEST = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "nag_real.pdf"

FIRST_PAGE_INDEX = 86  # 0-indexed; "First Law Applied to Flow Processes" heading
LAST_PAGE_INDEX = 115  # 0-indexed inclusive; page before Chapter 6 heading


def main() -> None:
    reader = PdfReader(SOURCE)
    writer = PdfWriter()
    for i in range(FIRST_PAGE_INDEX, LAST_PAGE_INDEX + 1):
        writer.add_page(reader.pages[i])

    DEST.parent.mkdir(parents=True, exist_ok=True)
    with DEST.open("wb") as f:
        writer.write(f)

    print(f"wrote {DEST} ({LAST_PAGE_INDEX - FIRST_PAGE_INDEX + 1} pages)")


if __name__ == "__main__":
    main()
