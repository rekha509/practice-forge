"""Anthropic backend. Not the active path right now (see docs/adr/0006 —
pivoted to Gemini free tier after the Anthropic account turned out to have
no billing credit) but kept fully working: point a stage's `provider` back
to `anthropic` in config/llm_routing.yaml and it runs unchanged.

Retries are the SDK's own `max_retries` — Anthropic's SDK already retries
429/5xx with backoff; duplicating that here would just be risk for no gain.
"""

from __future__ import annotations

from typing import Any

import anthropic

from practice_forge.llm.backends.base import BackendResponse


class LLMRefusalError(RuntimeError):
    """`stop_reason == "refusal"` — the model declined for safety reasons.
    Callers must not treat this like an empty/low-confidence result."""


class AnthropicBackend:
    def __init__(self, api_key: str | None = None, max_retries: int = 2) -> None:
        self._client = anthropic.Anthropic(api_key=api_key or None, max_retries=max_retries)

    def complete(
        self,
        *,
        model: str,
        prompt: str,
        max_tokens: int,
        system: str | None = None,
        output_schema: dict[str, Any] | None = None,
        thinking_budget: int | None = None,
    ) -> BackendResponse:
        kwargs: dict[str, Any] = {}
        if system is not None:
            kwargs["system"] = system

        # Anthropic has no fixed thinking-token-budget concept on current
        # models (removed in favour of adaptive thinking) — bridge the
        # generic "0 disables, anything else enables" contract onto that.
        if thinking_budget:
            kwargs["thinking"] = {"type": "adaptive"}

        output_config: dict[str, Any] = {}
        if output_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": output_schema}
        if output_config:
            kwargs["output_config"] = output_config

        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )

        if response.stop_reason == "refusal":
            raise LLMRefusalError(f"model {model} declined; see stop_details for category")

        text = "".join(block.text for block in response.content if block.type == "text")
        usage = response.usage
        return BackendResponse(
            text=text,
            stop_reason=response.stop_reason,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            extra_tokens=0,
        )
