"""S9 blind re-solve: an independent second opinion on a variant's answer,
for shipped variants where no book answer exists to calibrate against
(see calibration.py for the stronger check when one does).

Deliberately blind and deliberately a different model:

- The rendered prompt (`build_blind_resolve_prompt`) contains ONLY
  `statement_md` and `params` — never `core_python_code`, never
  `solution_steps`. See prompts/s9_blind_resolve.md and
  tests/test_blind_resolve.py's leak test, which fails if either ever
  appears in the rendered prompt.
- `run_blind_resolve` refuses to call the LLM at all
  (`BlindResolveModelCollisionError`) if config/llm_routing.yaml ever
  routes stage "s9_blind_resolve" to the exact same (provider, model) as
  stage "s9_codegen" — 20/20 agreement between a solver and a re-solver on
  the SAME model measures nothing, so this is enforced, not just
  commented.

v1 asked for free-text "ANSWER <name>: <value> <unit>" lines, parsed with
the same free-text scanner used for the book's own `final_answer` column.
Confirmed live (a real 20-problem batch) that real responses routinely
ignored the "no working shown" instruction and returned full derivations
anyway, and that scanning ALL numbers in that text for a match buried a
genuine agreement under dozens of unrelated intermediate numbers. v2
requires a trailing JSON object instead (see prompts/s9_blind_resolve.md)
and enforces it by parsing, not just asking nicely: `run_blind_resolve`
rejects a response with no valid JSON block and retries once before
raising `BlindResolveParseError` — one retry, not an unbounded loop, so a
model that never complies surfaces as a real, disclosable data point
rather than silently discarding the row (see blind_resolve_batch.py's own
handling of that error).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from practice_forge.db.models import VariantORM
from practice_forge.llm.client import LLMClient
from practice_forge.llm.routing import load_routing

_BLIND_RESOLVE_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "s9_blind_resolve.md"
_MAX_TOKENS = 4096


class BlindResolveModelCollisionError(RuntimeError):
    """Raised when stage "s9_blind_resolve" is routed to the SAME
    (provider, model) as stage "s9_codegen" — defeats the entire point of
    an independent re-solve. Fix config/llm_routing.yaml, don't catch
    this."""


class BlindResolveParseError(RuntimeError):
    """Raised when the blind re-solve's response still has no valid JSON
    answer block after one retry. A real, disclosable data point (the
    model failed to follow the required format) — callers should record
    it, not swallow it (see blind_resolve_batch.py)."""


def build_blind_resolve_prompt(variant: VariantORM, *, retry_note: str = "") -> str:
    """Renders the blind-resolve prompt from ONLY `statement_md`/`params` —
    deliberately excludes `core_python_code` and `solution_steps`, which
    this function never even reads off `variant`."""
    base = (
        _BLIND_RESOLVE_PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{statement_md}", variant.statement_md)
        .replace("{params}", str(variant.params))
    )
    return base + retry_note


@dataclass(frozen=True)
class BlindAnswerValue:
    value: float
    unit: str


@dataclass(frozen=True)
class BlindResolveResult:
    raw_text: str
    provider: str
    model: str
    answers: dict[str, BlindAnswerValue]


def _parse_json_answers(text: str) -> dict[str, BlindAnswerValue] | None:
    """Scans left-to-right for the first `{...}` that both parses as JSON
    AND matches the required {name: {"value": number, "unit": string}}
    shape -- not just the first parseable JSON, since a derivation can
    contain LaTeX/code braces that happen to parse as something JSON-ish
    (e.g. a bare nested {"value": ..., "unit": ...} fragment) without being
    the real top-level answer object. Tolerates a ```json fence around the
    whole response, since models add one despite being told not to."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()

    decoder = json.JSONDecoder()
    idx = stripped.find("{")
    while idx != -1:
        try:
            candidate, _end = decoder.raw_decode(stripped, idx)
        except json.JSONDecodeError:
            idx = stripped.find("{", idx + 1)
            continue

        if isinstance(candidate, dict) and candidate:
            answers: dict[str, BlindAnswerValue] = {}
            valid = True
            for name, entry in candidate.items():
                if not isinstance(entry, dict):
                    valid = False
                    break
                value = entry.get("value")
                unit = entry.get("unit")
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not isinstance(unit, str):
                    valid = False
                    break
                answers[name] = BlindAnswerValue(value=float(value), unit=unit)
            if valid:
                return answers

        idx = stripped.find("{", idx + 1)

    return None


def run_blind_resolve(client: LLMClient, job_id: str, variant: VariantORM) -> BlindResolveResult:
    routing = load_routing()
    blind_route = routing.route_for("s9_blind_resolve")
    codegen_route = routing.route_for("s9_codegen")
    if (blind_route.provider, blind_route.model) == (codegen_route.provider, codegen_route.model):
        raise BlindResolveModelCollisionError(
            f"s9_blind_resolve and s9_codegen are both routed to "
            f"{blind_route.provider}/{blind_route.model} — see "
            "config/llm_routing.yaml and this module's docstring."
        )

    prompt = build_blind_resolve_prompt(variant)
    response = client.complete(
        stage="s9_blind_resolve", prompt=prompt, job_id=f"{job_id}-attempt1", max_tokens=_MAX_TOKENS
    )
    answers = _parse_json_answers(response.text)

    if answers is None:
        retry_prompt = build_blind_resolve_prompt(
            variant,
            retry_note=(
                "\n\nYour previous response did not end in a single valid JSON "
                "object matching the required shape. Respond again, and make "
                "the LAST thing in your response that one JSON object — no "
                "markdown fence, no text after it."
            ),
        )
        response = client.complete(
            stage="s9_blind_resolve", prompt=retry_prompt, job_id=f"{job_id}-attempt2", max_tokens=_MAX_TOKENS
        )
        answers = _parse_json_answers(response.text)
        if answers is None:
            raise BlindResolveParseError(
                f"blind re-solve for job {job_id!r} produced no valid JSON answer block "
                f"after 2 attempts; last raw response: {response.text[:500]!r}"
            )

    return BlindResolveResult(
        raw_text=response.text, provider=response.provider, model=response.model, answers=answers
    )
