<!-- version: 1 -->
<!-- used by: src/practice_forge/ingest/metadata.py::extract_metadata_llm (S1b fallback) -->
<!-- model: routed via config/llm_routing.yaml, stage "s1_metadata" -->

Below is the raw OCR/extracted text of the first few pages of a real
engineering textbook. Real scanned title pages are messy: publisher
boilerplate, ISBN blocks, running headers, and OCR noise are all normal.

Identify the book's real title, author(s), and edition, if stated
anywhere in this text. If a field genuinely isn't present, say so — do
not invent a plausible-sounding value.

Text:
{sample_text}

Respond with the title, authors, and edition only.
