"""Generates tests/fixtures/*.pdf for Phase 2's ingest/dedup tests.

Run once with `python scripts/make_fixtures.py` (needs fpdf2, a dev-only
tool — see pyproject.toml's dev extra). The generated PDFs are committed
(tests/fixtures/*.pdf is the one *.pdf pattern .gitignore allows) so tests
don't depend on regenerating them.
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

TITLE_PAGE = """Title: Strength of Materials
Author: R.S. Khurmi, N. Khurmi
Edition: 3rd Edition
"""

BODY_PARAGRAPHS = [
    "Chapter 4: Bending Stress in Beams",
    "When a beam is subjected to a bending moment M, the bending equation "
    "sigma / y = M / I = E / R relates the bending stress sigma at a distance "
    "y from the neutral axis to the moment of inertia I and the modulus of "
    "elasticity E.",
    "Example 4.3: A simply supported beam of length 4 m carries a point load "
    "of 20 kN at mid-span. The cross-section is rectangular, 100 mm wide and "
    "200 mm deep. Determine the maximum bending stress sigma_max in N/mm^2 "
    "(MPa), given that the bending moment M = W L / 4.",
    "Solution: M = 20 kN * 4 m / 4 = 20 kN*m. I = b d^3 / 12 = 100 * 200^3 / "
    "12 mm^4. sigma_max = M y / I where y = d / 2 = 100 mm.",
    "Problem 4.12: Repeat the above calculation for a cantilever beam of "
    "length 2 m carrying a point load of 10 kN at the free end, with the "
    "same rectangular cross-section.",
    "Chapter 5: Shear Force and Torsion",
    "The shear stress tau in a circular shaft of radius R subjected to "
    "torque T is tau = T r / J, where J is the polar moment of inertia and "
    "r is the radial distance from the shaft axis, measured in N/mm^2.",
]


def _write_pdf(path: Path, title_page: str, body: list[str]) -> None:
    pdf = FPDF(format="A4")
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_font("helvetica", size=11)

    pdf.add_page()
    for line in title_page.splitlines():
        pdf.write(8, line + "\n")

    for paragraph in body:
        pdf.add_page()
        pdf.write(8, paragraph)

    pdf.output(str(path))


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    # Baseline book.
    _write_pdf(FIXTURES_DIR / "sample.pdf", TITLE_PAGE, BODY_PARAGRAPHS)

    # Same book, different scan: same title page, paragraphs lightly
    # reworded/reordered — should still MinHash-dedup against `sample.pdf`
    # (same title/author, page count within tolerance, Jaccard >= 0.8).
    rescanned_body = [
        BODY_PARAGRAPHS[0],
        BODY_PARAGRAPHS[1] + " (rescanned copy, minor OCR noise)",
        BODY_PARAGRAPHS[2],
        BODY_PARAGRAPHS[3],
        BODY_PARAGRAPHS[4],
        BODY_PARAGRAPHS[5],
        BODY_PARAGRAPHS[6],
    ]
    _write_pdf(FIXTURES_DIR / "sample_rescan.pdf", TITLE_PAGE, rescanned_body)

    # A genuinely different book — must NOT dedup against the above.
    other_title = "Title: Basic Electrical Engineering\nAuthor: D.P. Kothari\nEdition: 5th Edition\n"
    other_body = [
        "Chapter 1: DC Circuits",
        "Ohm's law states that V = I R, relating voltage V, current I and "
        "resistance R in a linear resistive element.",
        "Example 1.1: A resistor of 10 ohm carries a current of 2 A. Find "
        "the voltage drop V across it and the power P dissipated.",
    ]
    _write_pdf(FIXTURES_DIR / "other_book.pdf", other_title, other_body)

    # Phase 3 (S3 problem detection) fixture. Deliberately includes a case
    # designed to trip the regex layer into a false candidate (a page whose
    # first line matches "Example N.M" but isn't actually a solvable
    # problem) so the LLM-confirm step has something real to reject —
    # see tests/fixtures/labelled_spans.json for the ground truth this is
    # checked against.
    detection_title = "Title: Strength of Materials\nAuthor: R.S. Khurmi, N. Khurmi\nEdition: 3rd Edition\n"
    detection_body = [
        "Chapter 6: Torsion of Shafts",
        "Torsion is a classic problem in mechanical design, arising whenever "
        "a shaft transmits power through rotation.",
        "Example 6.1 illustrates a common misconception about shaft "
        "stiffness and is discussed qualitatively only; no numerical "
        "solution is given here.",
        "Example 6.2: A solid circular shaft of diameter 50 mm transmits a "
        "torque of 2 kN*m. Determine the maximum shear stress tau_max in "
        "the shaft, given that tau_max = T r / J.",
        "Problem 6.5: A hollow circular shaft has outer diameter 60 mm and "
        "inner diameter 40 mm, and carries a torque of 3 kN*m. Find the "
        "shear stress at the outer surface.",
        "Chapter 7: Fluid Mechanics",
    ]
    _write_pdf(FIXTURES_DIR / "detection_sample.pdf", detection_title, detection_body)

    print("wrote sample.pdf, sample_rescan.pdf, other_book.pdf, detection_sample.pdf")


if __name__ == "__main__":
    main()
