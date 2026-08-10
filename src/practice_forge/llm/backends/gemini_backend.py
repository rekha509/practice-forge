"""Gemini backend (google-genai SDK) — the active provider (see docs/adr/0006).

Field names/behavior here were verified by introspecting the installed SDK
and by live calls against a real free-tier key, not assumed from memory —
no bundled skill covers this SDK, and several assumed-safe things turned
out wrong empirically: `gemini-2.5-flash` / `gemini-2.5-flash-lite` are
retired for new accounts (404), `gemini-2.5-pro` has zero free-tier quota
on this account (429, `limit: 0`), and `gemini-flash-latest` spends
"thinking" tokens by default even on trivial prompts (see `thinking_budget`).
"""

from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

from practice_forge.llm.backends.base import BackendResponse


class GeminiBackend:
    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)

    def complete(
        self,
        *,
        model: str,
        prompt: str,
        max_tokens: int,
        system: str | None = None,
        output_schema: dict[str, Any] | None = None,
        thinking_budget: int | None = None,
        temperature: float | None = None,
    ) -> BackendResponse:
        config_kwargs: dict[str, Any] = {"max_output_tokens": max_tokens}
        if system is not None:
            config_kwargs["system_instruction"] = system
        if output_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_json_schema"] = output_schema
        if thinking_budget is not None:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=thinking_budget
            )
        if temperature is not None:
            config_kwargs["temperature"] = temperature

        response = self._client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        finish_reason = None
        if response.candidates:
            reason = response.candidates[0].finish_reason
            finish_reason = reason.name if reason is not None else None

        usage = response.usage_metadata
        return BackendResponse(
            text=response.text or "",
            stop_reason=finish_reason,
            input_tokens=usage.prompt_token_count if usage and usage.prompt_token_count else 0,
            output_tokens=(
                usage.candidates_token_count if usage and usage.candidates_token_count else 0
            ),
            extra_tokens=(
                usage.thoughts_token_count if usage and usage.thoughts_token_count else 0
            ),
        )
