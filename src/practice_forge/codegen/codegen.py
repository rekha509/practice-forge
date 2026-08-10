"""S9 Part A: core solver generation + real sandbox execution verification.

A real LLM call generates a self-contained Python script; real execution
(`sandbox.runner.run_code`) determines `verified_answer`/
`verification_status`, never the LLM's own claimed answer — this project's
whole premise is execution-verified problems, so nothing here trusts the
model's arithmetic.

Calls `run_code` directly rather than through the HTTP-wrapped
sandbox-runner service (docs/adr/0002). That service exists for the
worker's real deployment path, where isolating docker.sock access to one
dedicated container matters; this CLI-driven flow runs on the host
already (same trust level as an operator running `docker` commands
directly, which this whole session already has), so the extra HTTP hop
buys nothing here. A real `SandboxRunnerClient` HTTP wrapper is still
needed before the worker/API path can use this — not built yet, out of
scope for this session.
"""

from __future__ import annotations

import re
from pathlib import Path

from practice_forge.db.models import ConceptCardORM, VariantORM
from practice_forge.llm.client import LLMClient
from practice_forge.models.enums import VerificationStatus
from practice_forge.sandbox.runner import run_code

_CODEGEN_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "s9_codegen.md"
_RESULT_LINE = re.compile(r"^RESULT\s+([\w.]+):\s*(.+)$")
_CODE_FENCE = re.compile(r"^```(?:python)?\n?|\n?```$")

# One real attempt, one real retry with the actual stderr fed back — never
# more. Retrying indefinitely into a wrong-code wall is the same class of
# mistake as retrying into an exhausted quota; a human should see a
# genuinely stuck case, not have it silently loop.
MAX_ATTEMPTS = 2


def _build_prompt(
    card: ConceptCardORM, variant: VariantORM, extra_libs: list[str], retry_note: str
) -> str:
    extra_libs_note = f"Also available: {', '.join(extra_libs)}." if extra_libs else ""
    return (
        _CODEGEN_PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{method_tag}", card.method_tag)
        .replace("{equations}", ", ".join(card.governing_equations_latex))
        .replace("{assumptions}", ", ".join(card.assumptions))
        .replace("{statement_md}", variant.statement_md)
        .replace("{params}", str(variant.params))
        .replace("{extra_libs_note}", extra_libs_note)
        .replace("{retry_note}", retry_note)
    )


def _parse_results(stdout: str) -> dict[str, float] | None:
    results: dict[str, float] = {}
    for line in stdout.splitlines():
        m = _RESULT_LINE.match(line.strip())
        if not m:
            continue
        try:
            results[m.group(1)] = float(m.group(2))
        except ValueError:
            continue
    return results or None


def generate_and_verify_solution(
    client: LLMClient,
    job_id: str,
    card: ConceptCardORM,
    variant: VariantORM,
    *,
    extra_libs: list[str],
    sandbox_image: str,
    sandbox_timeout_s: int,
) -> None:
    """Mutates `variant` in place: core_python_code, verified_answer,
    verification_status, verification_log. Never raises on a bad
    generation/execution — a stuck variant is recorded as FAILED with the
    real error in its log, not allowed to abort the rest of a batch."""
    retry_note = ""
    log: list[str] = []

    for attempt in range(1, MAX_ATTEMPTS + 1):
        prompt = _build_prompt(card, variant, extra_libs, retry_note)
        response = client.complete(
            stage="s9_codegen",
            prompt=prompt,
            job_id=f"{job_id}-attempt{attempt}",
            max_tokens=4096,
        )
        code = _CODE_FENCE.sub("", response.text.strip())
        variant.core_python_code = code

        result = run_code(code, image=sandbox_image, timeout_s=sandbox_timeout_s)
        log.append(
            f"attempt {attempt}: exit_code={result.exit_code} "
            f"timed_out={result.timed_out} oom_killed={result.oom_killed}"
        )
        if result.stdout:
            log.append(f"attempt {attempt} stdout: {result.stdout[:2000]}")
        if result.stderr:
            log.append(f"attempt {attempt} stderr: {result.stderr[:2000]}")

        if result.ok:
            parsed = _parse_results(result.stdout)
            if parsed is not None:
                variant.verified_answer = str(parsed)
                variant.verification_status = VerificationStatus.VERIFIED
                variant.verification_log = log
                return
            log.append(f"attempt {attempt}: ran cleanly but printed no parseable RESULT line")
            retry_note = (
                "Your previous attempt ran without error but printed no line matching "
                "'RESULT <name>: <value>'. Every requested quantity must be printed in "
                "exactly that form, one per line."
            )
        else:
            retry_note = (
                f"Your previous attempt failed to run. stderr:\n{result.stderr[:1500]}\n"
                "Fix the error and return a corrected, complete script."
            )

    variant.verification_status = VerificationStatus.FAILED
    variant.verification_log = log
