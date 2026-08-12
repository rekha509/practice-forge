"""Batch blind re-solve over the real selected set: for each problem, ask
an independent model (see blind_resolve.py's collision guard) to re-solve
from scratch given only the statement/params, then compares its answer
against the SAME variant's own execution-verified answer — reporting the
actual relative difference per problem, not just pass/fail.

Real incident this responds to: a fresh process's RPM token bucket starts
at full capacity (see rate_limiter.py's _TokenBucket), so it has no way to
know how much of Google's real per-minute window a PREVIOUS process already
spent — confirmed live, twice, via a real 429 RESOURCE_EXHAUSTED quoting
"limit: 15, model: gemini-3.5-flash-lite" at request ~17 of 20, both times
discarding every already-computed row in the same batch because nothing
caught it. One retry with the server's own suggested delay is enough since
the daily bucket (checked separately, nowhere near exhausted) isn't the
issue -- this is purely a per-minute burst collision.
"""

from __future__ import annotations

import ast
import re
import time
import uuid
from dataclasses import dataclass

from google.genai.errors import ClientError
from sqlalchemy.orm import Session

from practice_forge.db.models import VariantORM
from practice_forge.llm.client import LLMClient
from practice_forge.render.render import _collect_rendered_problems
from practice_forge.verification.answer_parsing import compare_values
from practice_forge.verification.blind_resolve import (
    BlindResolveParseError,
    BlindResolveResult,
    run_blind_resolve,
)

_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*:\s*['\"](\d+)")
_MAX_RPM_RETRIES = 4


def _run_blind_resolve_with_rpm_retry(
    client: LLMClient, job_id: str, variant: VariantORM
) -> BlindResolveResult:
    """A single retry isn't enough -- confirmed live: over a 20-call batch
    against a real 15/min cap, more than one collision can land in the same
    run. Bounded (not infinite) so a genuinely stuck quota still surfaces as
    a real error rather than hanging."""
    for attempt in range(_MAX_RPM_RETRIES):
        try:
            return run_blind_resolve(client, job_id, variant)
        except ClientError as exc:
            if exc.code != 429 or attempt == _MAX_RPM_RETRIES - 1:
                raise
            match = _RETRY_DELAY_RE.search(str(exc))
            delay_s = max(min(float(match.group(1)), 90.0), 5.0) if match else 60.0
            time.sleep(delay_s)
    raise AssertionError("unreachable")


@dataclass(frozen=True)
class BlindResolveRow:
    index: int
    name: str
    solver_verified_answer: str | None
    blind_raw_text: str
    outcome: str  # "agrees" | "disagrees" | "solver_unparseable" | "blind_unparseable"
    detail: str


def run_blind_resolve_batch(
    session: Session, book_id: uuid.UUID, client: LLMClient, *, tol: float = 0.01
) -> list[BlindResolveRow]:
    problems = _collect_rendered_problems(session, book_id)
    rows: list[BlindResolveRow] = []

    for i, problem in enumerate(problems):
        variant = problem.variant

        if variant.verified_answer is None:
            rows.append(
                BlindResolveRow(
                    index=i + 1,
                    name=problem.card.name,
                    solver_verified_answer=None,
                    blind_raw_text="",
                    outcome="solver_unparseable",
                    detail="variant has no verified_answer to compare against",
                )
            )
            continue

        try:
            solver_results: dict[str, float] = ast.literal_eval(variant.verified_answer)
        except (ValueError, SyntaxError):
            rows.append(
                BlindResolveRow(
                    index=i + 1,
                    name=problem.card.name,
                    solver_verified_answer=variant.verified_answer,
                    blind_raw_text="",
                    outcome="solver_unparseable",
                    detail=f"verified_answer did not parse as a dict: {variant.verified_answer!r}",
                )
            )
            continue

        try:
            blind = _run_blind_resolve_with_rpm_retry(client, f"blind-{book_id}-{i}", variant)
        except BlindResolveParseError as exc:
            rows.append(
                BlindResolveRow(
                    index=i + 1,
                    name=problem.card.name,
                    solver_verified_answer=variant.verified_answer,
                    blind_raw_text="",
                    outcome="blind_unparseable",
                    detail=str(exc),
                )
            )
            continue

        # Per solver quantity, not per blind-answer key: names can legitimately
        # differ between the two models (e.g. "cop" vs "performance_ratio" —
        # confirmed live), so for each of the solver's own named quantities,
        # find its single BEST-matching value among the blind response's
        # (now structurally exact, JSON-parsed) answers.
        details: list[str] = []
        any_mismatch = False
        for name, si_value in solver_results.items():
            best_key, best_rel = None, None
            for bname, bv in blind.answers.items():
                result = compare_values(si_value, bv.value, bv.unit, tol=tol)
                if result.relative_difference is not None and (
                    best_rel is None or result.relative_difference < best_rel
                ):
                    best_key, best_rel = bname, result.relative_difference
            if best_key is None:
                any_mismatch = True
                details.append(f"solver.{name}={si_value:.6g} -> no comparable value in blind response")
                continue
            rel_str = f"{best_rel:.4f}" if best_rel is not None else "n/a"
            matched = best_rel is not None and best_rel <= tol
            if not matched:
                any_mismatch = True
            best_bv = blind.answers[best_key]
            details.append(
                f"solver.{name}={si_value:.6g} vs blind.{best_key}={best_bv.value}{best_bv.unit} "
                f"rel_diff={rel_str} -> {'AGREE' if matched else 'DISAGREE'}"
            )

        rows.append(
            BlindResolveRow(
                index=i + 1,
                name=problem.card.name,
                solver_verified_answer=variant.verified_answer,
                blind_raw_text=blind.raw_text,
                outcome="disagrees" if any_mismatch else "agrees",
                detail="; ".join(details),
            )
        )

    return rows
