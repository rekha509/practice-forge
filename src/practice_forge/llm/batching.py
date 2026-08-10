"""Batches N items into one call, expects a JSON array back, validates each
element independently — one malformed element must not poison the batch.

This exists because free-tier RPD (~1000/day Flash-Lite, ~250/day Flash on
this account — see config/llm_routing.yaml) makes one-call-per-item not
viable for any real book: a few hundred candidates would burn a whole day's
quota on S3 alone. Every high-volume stage must batch.

Each item's schema MUST include an `index` field echoing its position in
the input list. Alignment is by that field, not by response order/position
— the model can drop, reorder, or fail to return an element, and `index`
is what lets us tell which input item a given output belongs to (or that
one is simply missing).
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from practice_forge.llm.client import LLMClient, LLMResponse

logger = logging.getLogger("practice_forge.llm")

# PEP 695 `def call_batch[T: BaseModel](...)` syntax is a Python 3.12
# parser feature, not just a mypy/ruff style choice — this host's dev venv
# is still on 3.11 (no 3.12 interpreter available, see PROGRESS.md), and
# that syntax would fail to even import there. Classic TypeVar until a real
# 3.12 interpreter is in use.
ItemModelT = TypeVar("ItemModelT", bound=BaseModel)


def batch_array_schema(item_schema: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item_schema}


def call_batch(  # noqa: UP047 - see ItemModelT comment above
    client: LLMClient,
    *,
    stage: str,
    prompt: str,
    job_id: str,
    item_model: type[ItemModelT],
    expected_count: int,
    max_tokens: int,
    system: str | None = None,
) -> tuple[list[ItemModelT | None], LLMResponse]:
    """One call for the whole batch. Returns a list of length
    `expected_count`; `result[i]` is the validated item for input index i,
    or None if the model omitted it or returned something that failed
    schema validation.
    """
    schema = batch_array_schema(item_model.model_json_schema())
    response = client.complete(
        stage=stage,
        prompt=prompt,
        job_id=job_id,
        system=system,
        max_tokens=max_tokens,
        output_schema=schema,
    )

    results: list[ItemModelT | None] = [None] * expected_count

    if response.stop_reason == "MAX_TOKENS":
        # Found live at full-book scale (S5, docs/adr history): a model
        # whose thinking tokens draw from the same budget as visible
        # output can hit max_tokens mid-JSON-array, which then fails to
        # parse below and silently zeroes every item in the batch — not a
        # per-item failure, the WHOLE batch. Loud, not silent: this is the
        # one stop_reason where "the batch produced nothing" has an
        # actionable fix (raise max_tokens for this stage) rather than
        # being an expected shape of LLM output.
        logger.warning(
            "call_batch: stage=%s job_id=%s hit MAX_TOKENS (output_tokens=%d "
            "extra_tokens=%d, budget=%d) — the JSON array is likely truncated "
            "and this whole batch of %d items may parse to zero results. "
            "Consider raising max_tokens for this stage.",
            stage,
            job_id,
            response.output_tokens,
            response.extra_tokens,
            max_tokens,
            expected_count,
        )

    try:
        raw_items = json.loads(response.text)
    except json.JSONDecodeError:
        return results, response

    if not isinstance(raw_items, list):
        return results, response

    for raw_item in raw_items:
        if not isinstance(raw_item, dict) or "index" not in raw_item:
            continue
        idx = raw_item["index"]
        if not isinstance(idx, int) or not (0 <= idx < expected_count):
            continue
        try:
            results[idx] = item_model.model_validate(raw_item)
        except ValidationError:
            continue  # malformed element — leave as None, don't fail the batch

    return results, response
