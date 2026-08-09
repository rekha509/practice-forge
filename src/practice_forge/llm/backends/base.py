"""The interface every provider backend implements. `LLMClient` (client.py)
never talks to a provider SDK directly — only through this."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class BackendResponse:
    text: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    # Provider-specific tokens that aren't input or output but still count
    # against quota/cost (e.g. Gemini's thinking tokens). 0 for providers
    # that don't have this concept.
    extra_tokens: int = 0


class Backend(Protocol):
    def complete(
        self,
        *,
        model: str,
        prompt: str,
        max_tokens: int,
        system: str | None = None,
        output_schema: dict[str, Any] | None = None,
        thinking_budget: int | None = None,
    ) -> BackendResponse: ...
