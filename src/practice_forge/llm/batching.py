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
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from practice_forge.llm.client import LLMClient, LLMResponse

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
