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
in production. Figure interpretation (S4) hasn't landed yet, so every
persisted SourceProblem here gets figure_dependency=NONE — a problem this
naive regex pass would flag as figure-dependent is out of scope until then.
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
from practice_forge.models.enums import FigureDependency, ProblemKind

BATCH_SIZE = 20

_WORKED_EXAMPLE_PATTERN = re.compile(r"^(Example|Illustrative Example)\s+\d+\.\d+", re.IGNORECASE)
_EXERCISE_PATTERN = re.compile(r"^Problem\s+\d+\.\d+", re.IGNORECASE)
_EXERCISE_SECTION_PATTERN = re.compile(r"^(PROBLEMS|EXERCISES)\b")

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
    candidates: list[Candidate] = []
    for page_no, text in pages:
        stripped = text.strip()
        if not stripped:
            continue
        first_line = stripped.splitlines()[0]
        if _WORKED_EXAMPLE_PATTERN.match(first_line):
            candidates.append(Candidate(page_no, ProblemKind.WORKED_EXAMPLE, stripped))
        elif _EXERCISE_PATTERN.match(first_line) or _EXERCISE_SECTION_PATTERN.match(first_line):
            candidates.append(Candidate(page_no, ProblemKind.EXERCISE, stripped))
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
    prompt = _CONFIRM_PROMPT_PATH.read_text(encoding="utf-8").format(
        candidates_block=candidates_block
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
                statement_md=candidate.text,
                given=result.given,
                find=result.find,
                solution_md=None,
                final_answer=result.final_answer,
                figure_ids=[],
                figure_dependency=FigureDependency.NONE,
                is_solvable=True,
            )
            session.add(problem)
            persisted.append(problem)

    session.flush()
    return persisted


def make_default_batch_confirm_fn(job_id: str, llm_client: LLMClient | None = None) -> BatchConfirmFn:
    """Wires a real LLMClient for production use (`pf detect`). Tests never
    call this — they pass their own `confirm_fn` directly to `run_detection`."""
    client = llm_client or LLMClient()

    def _confirm(candidate_texts: list[str]) -> list[ConfirmResult | None]:
        return default_llm_confirm_batch(client, job_id, candidate_texts)

    return _confirm
