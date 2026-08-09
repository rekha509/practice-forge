"""The one wrapper every Anthropic API call in the pipeline goes through.

Nothing outside this module calls `anthropic.Anthropic()` directly. Retries
are the SDK's own (configurable `max_retries`; Anthropic's SDKs already
retry 429/5xx with backoff — hand-rolling that here would just duplicate
it). Prompt caching is opt-in per call (`cache_system=True`). Every call
logs one structured JSON line with `job_id`, token counts, and an estimated
USD cost, and accumulates per-job totals in-process — "what did this book
cost" is always answerable by summing the logs, or via `cost_for_job`
within a single pipeline run.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import anthropic

logger = logging.getLogger("practice_forge.llm")

# Per TECH STACK: Haiku for bulk extraction/classification/scoring, Sonnet
# for figure interpretation (vision), Opus for solving/variant generation/
# code generation (extended thinking).
HAIKU = "claude-haiku-4-5"
SONNET = "claude-sonnet-5"
OPUS = "claude-opus-5"

# USD per million tokens (input, output). List/standard pricing, not the
# temporary Claude Sonnet 5 introductory rate (expires 2026-08-31) — using
# list price means this table doesn't silently under-report cost once that
# window closes. Cache write (5-minute TTL) is ~1.25x input; cache read is
# ~0.1x input (Anthropic's published multipliers, applied here rather than
# hardcoding a second table per model).
_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    HAIKU: (1.00, 5.00),
    SONNET: (3.00, 15.00),
    OPUS: (5.00, 25.00),
}
_CACHE_WRITE_MULTIPLIER = 1.25
_CACHE_READ_MULTIPLIER = 0.10


@dataclass(frozen=True)
class LLMResponse:
    text: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    cost_usd: float


class LLMRefusalError(RuntimeError):
    """Raised when the model declines for safety reasons (`stop_reason ==
    "refusal"`) rather than returning content. Callers must not treat this
    like an empty/low-confidence result — it means the classifier fired,
    not that there was nothing to find."""


def _estimate_cost_usd(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int,
    cache_read_input_tokens: int,
) -> float:
    input_price, output_price = _PRICING_PER_MTOK[model]
    return (
        input_tokens * input_price
        + output_tokens * output_price
        + cache_creation_input_tokens * input_price * _CACHE_WRITE_MULTIPLIER
        + cache_read_input_tokens * input_price * _CACHE_READ_MULTIPLIER
    ) / 1_000_000


class LLMClient:
    def __init__(self, api_key: str | None = None, max_retries: int = 2) -> None:
        self._client = anthropic.Anthropic(api_key=api_key or None, max_retries=max_retries)
        self._job_costs_usd: dict[str, float] = defaultdict(float)

    def cost_for_job(self, job_id: str) -> float:
        return self._job_costs_usd[job_id]

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        job_id: str,
        system: str | None = None,
        thinking: bool = False,
        effort: str | None = None,
        cache_system: bool = False,
        output_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """One call, fully accounted. `thinking=True` sets adaptive thinking
        (Opus 5 only needs this to be explicit for documentation purposes —
        it's already on by default). `output_schema` requests structured
        JSON output via `output_config.format` instead of hoping the model's
        prose happens to parse."""
        kwargs: dict[str, Any] = {}

        if system is not None:
            if cache_system:
                kwargs["system"] = [
                    {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
                ]
            else:
                kwargs["system"] = system

        if thinking:
            kwargs["thinking"] = {"type": "adaptive"}

        output_config: dict[str, Any] = {}
        if effort is not None:
            output_config["effort"] = effort
        if output_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": output_schema}
        if output_config:
            kwargs["output_config"] = output_config

        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,  # type: ignore[arg-type]  # plain dicts, structurally a MessageParam
            **kwargs,
        )

        usage = response.usage
        cost_usd = _estimate_cost_usd(
            model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
            cache_read_input_tokens=usage.cache_read_input_tokens or 0,
        )
        self._job_costs_usd[job_id] += cost_usd

        logger.info(
            json.dumps(
                {
                    "job_id": job_id,
                    "model": model,
                    "stop_reason": response.stop_reason,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "cache_creation_input_tokens": usage.cache_creation_input_tokens or 0,
                    "cache_read_input_tokens": usage.cache_read_input_tokens or 0,
                    "cost_usd": round(cost_usd, 6),
                    "job_cost_usd_running_total": round(self._job_costs_usd[job_id], 6),
                }
            )
        )

        if response.stop_reason == "refusal":
            raise LLMRefusalError(
                f"model {model} declined (job_id={job_id}); see stop_details for category"
            )

        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMResponse(
            text=text,
            stop_reason=response.stop_reason,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
            cache_read_input_tokens=usage.cache_read_input_tokens or 0,
            cost_usd=cost_usd,
        )
