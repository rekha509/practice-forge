"""S3: regex problem-candidate detection + an LLM confirm pass, into
SourceProblem rows.

The confirm step is dependency-injected (`confirm_fn`) rather than reaching
for a module-level LLMClient: unit tests supply a deterministic fake (per
the testing standard — never let a unit test hit the API), and
`default_llm_confirm` is the real implementation callers wire up in
production. Figure interpretation (S4) hasn't landed yet, so every
persisted SourceProblem here gets figure_dependency=NONE — a problem this
naive regex pass would flag as figure-dependent is out of scope until then.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.config import get_settings
from practice_forge.db.models import PageORM, SectionORM, SourceProblemORM
from practice_forge.llm.client import HAIKU, LLMClient
from practice_forge.models.enums import FigureDependency, ProblemKind

_WORKED_EXAMPLE_PATTERN = re.compile(r"^(Example|Illustrative Example)\s+\d+\.\d+", re.IGNORECASE)
_EXERCISE_PATTERN = re.compile(r"^Problem\s+\d+\.\d+", re.IGNORECASE)
_EXERCISE_SECTION_PATTERN = re.compile(r"^(PROBLEMS|EXERCISES)\b")

_CONFIRM_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "s3_problem_confirm.md"

_CONFIRM_SCHEMA = {
    "type": "object",
    "properties": {
        "is_problem": {"type": "boolean"},
        "kind": {
            "type": "string",
            "enum": ["worked_example", "exercise", "derivation", "not_a_problem"],
        },
        "given": {"type": "array", "items": {"type": "string"}},
        "find": {"type": "array", "items": {"type": "string"}},
        "final_answer": {"type": ["string", "null"]},
    },
    "required": ["is_problem", "kind", "given", "find", "final_answer"],
    "additionalProperties": False,
}


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


ConfirmFn = Callable[[str], ConfirmResult]


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


def default_llm_confirm(llm_client: LLMClient, job_id: str, candidate_text: str) -> ConfirmResult:
    """Real S3 confirm pass: Haiku, structured JSON output."""
    prompt = _CONFIRM_PROMPT_PATH.read_text(encoding="utf-8").format(candidate_text=candidate_text)
    response = llm_client.complete(
        model=HAIKU,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
        job_id=job_id,
        output_schema=_CONFIRM_SCHEMA,
    )
    data = json.loads(response.text)
    kind = ProblemKind(data["kind"]) if data["is_problem"] else None
    return ConfirmResult(
        is_problem=data["is_problem"],
        kind=kind,
        given=data["given"],
        find=data["find"],
        final_answer=data["final_answer"],
    )


def _find_section_id(sections: list[SectionORM], page_no: int) -> uuid.UUID:
    for section in sections:
        if section.page_start <= page_no <= section.page_end:
            return section.id
    raise ValueError(
        f"page {page_no} falls outside every detected Section — run structure (S2) first"
    )


def run_detection(
    session: Session,
    book_id: uuid.UUID,
    confirm_fn: ConfirmFn,
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
    for candidate in candidates:
        result = confirm_fn(candidate.text)
        if not result.is_problem or result.kind is None:
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


def make_default_confirm_fn(job_id: str, api_key: str | None = None) -> ConfirmFn:
    """Wires a real LLMClient for production use (`pf detect`). Tests never
    call this — they pass their own `confirm_fn` directly to `run_detection`."""
    client = LLMClient(api_key=api_key or get_settings().anthropic_api_key)

    def _confirm(candidate_text: str) -> ConfirmResult:
        return default_llm_confirm(client, job_id, candidate_text)

    return _confirm
