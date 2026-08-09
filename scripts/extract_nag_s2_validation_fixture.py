"""Extracts a SEPARATE, validation-only fixture for testing the TOC-driven
S2 rewrite: real TOC pages (2-6) + a continuous real span covering four
chapter boundaries (Chapter 3 "Work and Heat Transfer" through the start of
Chapter 6 "Second Law of Thermodynamics", PDF indices 43-117).

Deliberately NOT tests/fixtures/nag_real.pdf — that fixture is reserved for
the user's own hand-count of S3 recall and must not change page count or
content. This is a different file, used only to validate S2.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter

SOURCE = Path(__file__).resolve().parents[1] / "Thermodynamics by PK Nag.pdf"
DEST = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "nag_s2_validation.pdf"

TOC_PAGES = range(2, 7)  # 0-indexed inclusive of 2..6
CHAPTER_SPAN = range(43, 118)  # Chapter 3 start through just past Chapter 6 start


def main() -> None:
    reader = PdfReader(SOURCE)
    writer = PdfWriter()
    for i in list(TOC_PAGES) + list(CHAPTER_SPAN):
        writer.add_page(reader.pages[i])

    DEST.parent.mkdir(parents=True, exist_ok=True)
    with DEST.open("wb") as f:
        writer.write(f)

    print(f"wrote {DEST} ({len(list(TOC_PAGES)) + len(list(CHAPTER_SPAN))} pages)")


if __name__ == "__main__":
    main()
