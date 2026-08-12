"""Force S9 re-verification on already-verified variants, unchanged
params/statement, under whatever model `s9_codegen` is currently routed
to — for comparing solver quality across models (e.g. flash-lite vs
flash-latest) on the SAME 20 real selected problems. Deliberately NOT
the existing idempotency-skip path (`pf generate` skips anything already
VERIFIED) — the whole point here is re-solving what's already verified.

Stops cleanly on `DailyQuotaExhausted` rather than losing already-
collected results: each row is committed individually, so a mid-batch
quota cutoff leaves every already-reverified row intact and reports
exactly where it stopped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from practice_forge.codegen.codegen import generate_and_verify_solution
from practice_forge.llm.client import LLMClient
from practice_forge.llm.rate_limiter import DailyQuotaExhausted
from practice_forge.render.render import _collect_rendered_problems


@dataclass(frozen=True)
class ReverifyRow:
    index: int
    name: str
    old_verified_answer: str | None
    old_status: str
    new_verified_answer: str | None
    new_status: str
    changed: bool


@dataclass(frozen=True)
class ReverifyReport:
    rows: list[ReverifyRow]
    total_selected: int
    quota_exhausted: bool


def run_reverify(
    session: Session,
    book_id: uuid.UUID,
    client: LLMClient,
    *,
    extra_libs: list[str],
    sandbox_image: str,
    sandbox_timeout_s: int = 15,
) -> ReverifyReport:
    problems = _collect_rendered_problems(session, book_id)
    rows: list[ReverifyRow] = []
    quota_exhausted = False

    for i, problem in enumerate(problems):
        variant = problem.variant
        old_answer = variant.verified_answer
        old_status = variant.verification_status.value

        try:
            generate_and_verify_solution(
                client,
                f"reverify-{book_id}-{i}",
                problem.card,
                variant,
                extra_libs=extra_libs,
                sandbox_image=sandbox_image,
                sandbox_timeout_s=sandbox_timeout_s,
            )
        except DailyQuotaExhausted:
            quota_exhausted = True
            break

        session.add(variant)
        session.commit()

        rows.append(
            ReverifyRow(
                index=i + 1,
                name=problem.card.name,
                old_verified_answer=old_answer,
                old_status=old_status,
                new_verified_answer=variant.verified_answer,
                new_status=variant.verification_status.value,
                changed=variant.verified_answer != old_answer,
            )
        )

    return ReverifyReport(rows=rows, total_selected=len(problems), quota_exhausted=quota_exhausted)
