"""P12: real per-step Q&A for a rendered variant -- a synchronous, single
LLM call answering a student/faculty question about one specific solution
step, not a pipeline stage.

`api/routers/problem_sets.py`'s `/chat` route calls this directly, not
through Celery: a one-off Q&A reply is exactly the kind of short request
FastAPI is fine blocking on. The project's "never block an HTTP request on
marker or on S9" rule (see that router's module docstring) is about bulk,
many-request pipeline stages -- this is neither.
"""

from __future__ import annotations

from pathlib import Path

from practice_forge.db.models import VariantORM
from practice_forge.llm.client import LLMClient

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "chat_explain_step.md"


class StepIndexError(ValueError):
    """Raised when step_index is out of range for the variant's solution_steps."""


def build_explain_step_prompt(variant: VariantORM, step_index: int, question: str) -> str:
    """`step_index` is 1-based, matching the API's `problem_index` convention."""
    steps = variant.solution_steps
    if not (1 <= step_index <= len(steps)):
        raise StepIndexError(f"step_index {step_index} out of range for {len(steps)} steps")

    numbered_steps = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, start=1))
    return (
        _PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{statement_md}", variant.statement_md)
        .replace("{solution_steps}", numbered_steps)
        .replace("{step_number}", str(step_index))
        .replace("{step_count}", str(len(steps)))
        .replace("{target_step}", steps[step_index - 1])
        .replace("{question}", question)
    )


def explain_step(client: LLMClient, job_id: str, variant: VariantORM, step_index: int, question: str) -> str:
    prompt = build_explain_step_prompt(variant, step_index, question)
    response = client.complete(stage="chat_explain_step", prompt=prompt, job_id=job_id, max_tokens=512)
    return response.text.strip()
