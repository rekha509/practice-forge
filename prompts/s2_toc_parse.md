<!-- version: 1 -->
<!-- used by: src/practice_forge/structure/toc.py (S2 TOC-driven structure detection) -->
<!-- model: routed via config/llm_routing.yaml, stage "s2_structure" -->

The text below is OCR output from a textbook's table of contents. OCR
introduces noise (misread characters, garbled spacing, stray symbols) —
read through it, don't expect clean text.

Extract every TOP-LEVEL CHAPTER entry (not subsections within a chapter,
not "Solved Examples"/"Review Questions"/"Problems" sub-entries — only the
numbered chapters themselves, e.g. "4. First Law of Thermodynamics ... 63",
"5. First Law Applied to Flow Processes ... 81").

For each chapter, extract:
- chapter_no: the chapter's number as printed.
- title: the chapter's title, cleaned of obvious OCR artifacts where you
  can confidently tell what the text should say — but do not invent a
  title you can't actually read.
- printed_page: the page number printed next to the chapter title in the
  table of contents (this is the BOOK's own printed page number, not a
  PDF file page index — do not try to convert it).

Table of contents text:
---
{toc_text}
---

Return a JSON array with one object per chapter, in chapter order.

Respond with the requested JSON only.
