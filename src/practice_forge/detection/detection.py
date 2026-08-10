"""S3: regex problem-candidate detection + a BATCHED LLM confirm pass, into
SourceProblem rows.

Batched, not one-call-per-candidate: free-tier RPD (~1000/day Flash-Lite on
this account — see config/llm_routing.yaml, docs/adr/0006) makes per-item
calls not viable for any real book with more than a handful of candidates.
All candidates for a book go through in chunks of `BATCH_SIZE`.

The confirm step is dependency-injected (`confirm_fn`) rather than reaching
for a module-level LLMClient: unit tests supply a deterministic fake (per
the testing standard — never let a unit test hit the API), and
`make_default_batch_confirm_fn` is the real implementation callers wire up
in production. `figure_dependency` starts at NONE for every persisted row
here and is classified by a separate pass (`figures.run_figure_descope`,
S4 — see docs/adr/0007), not by this module.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import PageORM, SectionORM, SourceProblemORM
from practice_forge.llm.batching import call_batch
from practice_forge.llm.client import LLMClient
from practice_forge.llm.sanitize import strip_nul, strip_nul_list, strip_nul_opt
from practice_forge.models.enums import FigureDependency, ProblemKind

BATCH_SIZE = 20

# Safety cap on a single candidate's span. Found live on tests/fixtures/
# nag_real.pdf: this book's end-of-chapter exercises are a numbered list
# ("5.1 ...", "5.2 ...") under one "PROBLEMS" section header, never
# repeating the word "Problem" per item — so _EXERCISE_PATTERN doesn't
# segment them individually, and the span from the last matched heading to
# end-of-book swallows the whole exercise list as one candidate (observed:
# 14000+ characters). Truncating avoids burning a batch's token budget on
# one degenerate item; it does NOT fix under-segmentation of that book's
# exercise list — tracked as a known gap (see PROGRESS.md), not silently
# hidden.
MAX_CANDIDATE_CHARS = 4000

_WORKED_EXAMPLE_PATTERN = re.compile(r"^(Example|Illustrative Example)\s+\d+\.\d+", re.IGNORECASE)
_EXERCISE_PATTERN = re.compile(r"^Problem\s+\d+\.\d+", re.IGNORECASE)
_EXERCISE_SECTION_PATTERN = re.compile(r"^(PROBLEMS|EXERCISES)\b")

# End-of-chapter exercise lists in this book are a bare numbered sequence
# ("5.1 ...", "5.2 ...") under one "PROBLEMS"/"EXERCISES" header, with no
# per-item keyword — _EXERCISE_PATTERN above needs the literal word
# "Problem" and never matches these, so the whole list fell through as one
# giant blob under _EXERCISE_SECTION_PATTERN (see MAX_CANDIDATE_CHARS's
# original note). `I` is included alongside `\d+` because this book's OCR
# routinely misreads the digit "1" as a capital "I" in this exact position
# (confirmed live: "I.I A pwnp discharges..." on a real page whose true
# text is "1.1 A pump discharges..."). The chapter component is deliberately
# `[1-9]\d*`, not bare `\d+`: found live at full-book scale that a solution's
# own inline numeric result (e.g. "0.06\nFor the fluid system, calculate...")
# false-matched as a new exercise item — this book's real chapters are
# numbered 1-22, never 0, so excluding a leading zero removes that
# false-positive class without needing anything smarter than the book's
# own numbering convention.
_SEQUENTIAL_ITEM_PATTERN = re.compile(r"^(?:[1-9]\d*|I)\.(?:\d+|I)\b")

_CONFIRM_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "s3_problem_confirm.md"


@dataclass(frozen=True)
class Candidate:
    page_no: int
    kind_guess: ProblemKind
    text: str


@dataclass(frozen=True)
class ConfirmResult:
    is_problem: bool
    kind: ProblemKind | None
    given: list[str] = field(default_factory=list)
    find: list[str] = field(default_factory=list)
    final_answer: str | None = None


class ConfirmBatchItem(BaseModel):
    """One element of the batch confirm pass's JSON array response. Strict
    (`extra="forbid"`) so `model_json_schema()` emits `additionalProperties:
    false` — the schema Gemini/Anthropic structured output is asked to
    match."""

    model_config = ConfigDict(extra="forbid")

    index: int
    is_problem: bool
    kind: Literal["worked_example", "exercise", "derivation", "not_a_problem"]
    given: list[str] = []
    find: list[str] = []
    final_answer: str | None = None


BatchConfirmFn = Callable[[list[str]], list[ConfirmResult | None]]


def detect_candidates(pages: list[tuple[int, str]]) -> list[Candidate]:
    """Scans every line across the whole book, not just each page's first
    line. On a real (scanned/OCR'd) book, a heading like "Example 5.1" is
    routinely a few lines into a page — after a running header/footer the
    OCR pass captured as ordinary text — and a page can hold more than one
    example (verified on tests/fixtures/nag_real.pdf: pages with two
    consecutive "Example N.M" headings exist). A candidate's span runs from
    its heading line to the next heading (of any kind), which may fall on
    a later page — real problems routinely cross a page break.
    """
    flat_lines: list[tuple[int, str]] = []
    for page_no, text in pages:
        for line in text.splitlines():
            stripped_line = line.strip()
            if stripped_line:
                flat_lines.append((page_no, stripped_line))

    headings: list[tuple[int, ProblemKind, bool]] = []
    for i, (_, line) in enumerate(flat_lines):
        if _WORKED_EXAMPLE_PATTERN.match(line):
            headings.append((i, ProblemKind.WORKED_EXAMPLE, False))
        elif _EXERCISE_PATTERN.match(line):
            headings.append((i, ProblemKind.EXERCISE, False))
        elif _EXERCISE_SECTION_PATTERN.match(line):
            headings.append((i, ProblemKind.EXERCISE, True))

    candidates: list[Candidate] = []
    for idx, (start_i, kind_guess, is_section_header) in enumerate(headings):
        end_i = headings[idx + 1][0] if idx + 1 < len(headings) else len(flat_lines)

        if is_section_header:
            # Sequential-enumeration: once inside a PROBLEMS/EXERCISES
            # section, every subsequent N.M-numbered line starts its own
            # candidate — not one blob for the whole section — running
            # until the next such line or this section's own end boundary
            # (the next detected heading of any kind, i.e. effectively the
            # next chapter/section).
            item_starts = [
                i
                for i in range(start_i + 1, end_i)
                if _SEQUENTIAL_ITEM_PATTERN.match(flat_lines[i][1])
            ]
            if item_starts:
                for item_idx, item_start in enumerate(item_starts):
                    item_end = (
                        item_starts[item_idx + 1]
                        if item_idx + 1 < len(item_starts)
                        else end_i
                    )
                    span_text = "\n".join(
                        line for _, line in flat_lines[item_start:item_end]
                    )[:MAX_CANDIDATE_CHARS]
                    page_no = flat_lines[item_start][0]
                    candidates.append(Candidate(page_no, ProblemKind.EXERCISE, span_text))
                continue
            # No numbered items found under this header (a section that
            # doesn't fit the pattern) — fall back to the old whole-blob
            # candidate below as a safety net, rather than dropping it.

        span_text = "\n".join(line for _, line in flat_lines[start_i:end_i])[:MAX_CANDIDATE_CHARS]
        page_no = flat_lines[start_i][0]
        candidates.append(Candidate(page_no, kind_guess, span_text))
    return candidates


def _item_to_confirm_result(item: ConfirmBatchItem | None) -> ConfirmResult:
    if item is None or not item.is_problem or item.kind == "not_a_problem":
        return ConfirmResult(is_problem=False, kind=None)
    return ConfirmResult(
        is_problem=True,
        kind=ProblemKind(item.kind),
        given=item.given,
        find=item.find,
        final_answer=item.final_answer,
    )


def default_llm_confirm_batch(
    llm_client: LLMClient, job_id: str, candidate_texts: list[str]
) -> list[ConfirmResult | None]:
    """Real S3 confirm pass: ONE call for up to `BATCH_SIZE` candidates,
    structured JSON array output, per-item schema validation."""
    candidates_block = "\n---\n".join(
        f"[index {i}]\n{text}" for i, text in enumerate(candidate_texts)
    )
    # .replace(), not .format(): candidate text can itself contain literal
    # `{`/`}` (LaTeX, OCR artifacts), which .format() misparses as
    # placeholders — found live on real content (see docs/adr for detail).
    prompt = _CONFIRM_PROMPT_PATH.read_text(encoding="utf-8").replace(
        "{candidates_block}", candidates_block
    )

    items, _response = call_batch(
        llm_client,
        stage="s3_confirm",
        prompt=prompt,
        job_id=job_id,
        item_model=ConfirmBatchItem,
        expected_count=len(candidate_texts),
        max_tokens=4096,
    )

    return [None if item is None else _item_to_confirm_result(item) for item in items]


def _find_section_id(sections: list[SectionORM], page_no: int) -> uuid.UUID:
    for section in sections:
        if section.page_start <= page_no <= section.page_end:
            return section.id
    raise ValueError(
        f"page {page_no} falls outside every detected Section — run structure (S2) first"
    )


def _chunked(items: list[Candidate], size: int) -> list[list[Candidate]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def run_detection(
    session: Session,
    book_id: uuid.UUID,
    confirm_fn: BatchConfirmFn,
) -> list[SourceProblemORM]:
    pages = (
        session.execute(
            select(PageORM.page_no, PageORM.markdown)
            .where(PageORM.book_id == book_id)
            .order_by(PageORM.page_no)
        )
        .all()
    )
    sections = (
        session.execute(select(SectionORM).where(SectionORM.book_id == book_id)).scalars().all()
    )

    candidates = detect_candidates([(p.page_no, p.markdown) for p in pages])

    # Idempotency: skip any candidate already persisted for this book.
    # Natural key is (book_id, page_no, statement_md), NOT bare
    # (book_id, page_no) — confirmed live on real content that a single
    # page can hold two distinct problems (this book's page 23 has two),
    # so page_no alone would treat the second real problem on that page as
    # a duplicate of the first and silently drop it on any re-run.
    # Filtering before the confirm call also means a re-run doesn't
    # re-spend LLM quota reconfirming candidates already persisted.
    existing_keys = {
        (row.page_no, row.statement_md)
        for row in session.execute(
            select(SourceProblemORM.page_no, SourceProblemORM.statement_md).where(
                SourceProblemORM.book_id == book_id
            )
        )
    }
    candidates = [c for c in candidates if (c.page_no, c.text) not in existing_keys]

    persisted: list[SourceProblemORM] = []
    for batch in _chunked(candidates, BATCH_SIZE):
        results = confirm_fn([c.text for c in batch])
        if len(results) != len(batch):
            raise ValueError(
                f"confirm_fn returned {len(results)} results for a batch of {len(batch)} "
                "candidates — batch confirm functions must return one result per input, "
                "using None for anything missing/malformed."
            )

        for candidate, result in zip(batch, results, strict=True):
            if result is None or not result.is_problem or result.kind is None:
                continue

            problem = SourceProblemORM(
                id=uuid.uuid4(),
                book_id=book_id,
                section_id=_find_section_id(list(sections), candidate.page_no),
                page_no=candidate.page_no,
                kind=result.kind,
                statement_md=strip_nul(candidate.text),
                given=strip_nul_list(result.given),
                find=strip_nul_list(result.find),
                solution_md=None,
                final_answer=strip_nul_opt(result.final_answer),
                figure_ids=[],
                figure_dependency=FigureDependency.NONE,
                # A derive/prove exercise has no numeric given/find and no
                # computable final answer — per explicit instruction, this
                # project targets numerical problems with an executable
                # Python check (S9), and a proof has nothing for that check
                # to verify. Excluded here at the same is_solvable flag S4
                # already uses for figure-dependent exclusions, not a new
                # column — same meaning ("this SourceProblem cannot feed
                # the numeric pipeline"), different reason.
                is_solvable=result.kind != ProblemKind.DERIVATION,
            )
            session.add(problem)
            persisted.append(problem)

        # Commit per batch, not once at the end: found live on the full
        # 781-page book — a single bad row anywhere in the whole run (a
        # NUL byte from OCR, see ingest/extract.py's fix) previously
        # rolled back EVERY already-confirmed batch in one transaction,
        # discarding LLM work that had already been paid for in quota.
        # Committing per batch means a later batch's failure can't erase
        # earlier batches' real, already-persisted output — and combined
        # with this function's own idempotency check above, a re-run
        # after a crash resumes cleanly from whatever did commit.
        session.commit()

    return persisted


def make_default_batch_confirm_fn(job_id: str, llm_client: LLMClient | None = None) -> BatchConfirmFn:
    """Wires a real LLMClient for production use (`pf detect`). Tests never
    call this — they pass their own `confirm_fn` directly to `run_detection`."""
    client = llm_client or LLMClient()

    def _confirm(candidate_texts: list[str]) -> list[ConfirmResult | None]:
        return default_llm_confirm_batch(client, job_id, candidate_texts)

    return _confirm
