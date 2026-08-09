"""Test-only stand-ins for real LLM calls.

Every stub here is gated behind `PF_USE_STUB_LLM=1` (default off) and
raises loudly if invoked without it explicitly set in that test — a stub
must never again be able to silently satisfy a detection-quality gate. See
PROGRESS.md's Phase 3 correction (a hand-written fake tuned to a
self-authored fixture was mistakenly reported as validating accuracy) and
the `feedback_dont_overclaim_selfauthored_test_validity` memory.
"""

from __future__ import annotations

import os

from practice_forge.detection.detection import ConfirmResult
from practice_forge.models.enums import ProblemKind


def _require_stub_opt_in() -> None:
    if os.environ.get("PF_USE_STUB_LLM") != "1":
        raise RuntimeError(
            "A stub LLM confirm function fired without PF_USE_STUB_LLM=1 explicitly "
            "set. Stubs must never silently satisfy a gate — if a test genuinely needs "
            "one (to check plumbing, not detection accuracy), set "
            "monkeypatch.setenv('PF_USE_STUB_LLM', '1') in that test only, and don't "
            "cite its results as evidence of real detection quality."
        )


def stub_batch_confirm_fn(candidate_texts: list[str]) -> list[ConfirmResult | None]:
    """Hand-written stand-in tuned to tests/fixtures/detection_sample.pdf's
    exact wording — for plumbing tests only. NEVER used for the P3 accuracy
    gate; see tests/test_detection.py for the real, unstubbed version of
    that test."""
    _require_stub_opt_in()
    results: list[ConfirmResult | None] = []
    for text in candidate_texts:
        if "qualitatively only" in text:
            results.append(ConfirmResult(is_problem=False, kind=None))
        elif text.startswith("Problem"):
            results.append(
                ConfirmResult(
                    is_problem=True,
                    kind=ProblemKind.EXERCISE,
                    given=["T = 3 kN*m", "outer diameter = 60 mm", "inner diameter = 40 mm"],
                    find=["shear stress at the outer surface"],
                )
            )
        else:
            results.append(
                ConfirmResult(
                    is_problem=True,
                    kind=ProblemKind.WORKED_EXAMPLE,
                    given=["T = 2 kN*m", "diameter = 50 mm"],
                    find=["tau_max"],
                )
            )
    return results
