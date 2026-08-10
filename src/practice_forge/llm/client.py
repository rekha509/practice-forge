"""The one facade every pipeline stage calls through — provider-agnostic.
Routing (config/llm_routing.yaml) decides which provider+model serves each
stage; nothing here hardcodes either. See docs/adr/0006: pivoted to the
Gemini free tier after the Anthropic account turned out to have no billing
credit. The Anthropic backend is kept fully working — repoint a stage back
to it in the YAML whenever there's a paid budget again.

Every call goes through the rate limiter first (config/llm_routing.yaml's
`limits` section) — free-tier daily quotas are the binding constraint here,
not cost. `DailyQuotaExhausted` propagates up uncaught; callers must stop
cleanly, not swallow it and retry.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from practice_forge.config import get_settings
from practice_forge.llm.backends.anthropic_backend import AnthropicBackend
from practice_forge.llm.backends.base import Backend
from practice_forge.llm.backends.gemini_backend import GeminiBackend
from practice_forge.llm.rate_limiter import RateLimiter
from practice_forge.llm.routing import RoutingConfig, load_routing

logger = logging.getLogger("practice_forge.llm")

# USD per million tokens — Anthropic only. Gemini free tier is $0; its
# tokens are still logged (extra_tokens/input_tokens/output_tokens) for RPD
# visibility, which is what actually matters on that provider.
_ANTHROPIC_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-5": (5.00, 25.00),
}


@dataclass(frozen=True)
class LLMResponse:
    text: str
    stop_reason: str | None
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    extra_tokens: int
    cost_usd: float


def _estimate_cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    if provider != "anthropic":
        return 0.0
    input_price, output_price = _ANTHROPIC_PRICING_PER_MTOK.get(model, (0.0, 0.0))
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


class LLMClient:
    def __init__(
        self,
        *,
        routing: RoutingConfig | None = None,
        rate_limiter: RateLimiter | None = None,
        anthropic_api_key: str | None = None,
        gemini_api_key: str | None = None,
    ) -> None:
        settings = get_settings()
        self._routing = routing or load_routing()
        self._rate_limiter = rate_limiter or RateLimiter()
        self._backends: dict[str, Backend] = {}
        self._anthropic_api_key = anthropic_api_key or settings.anthropic_api_key
        self._gemini_api_key = gemini_api_key or settings.gemini_api_key
        self._job_costs_usd: dict[str, float] = defaultdict(float)

    def cost_for_job(self, job_id: str) -> float:
        return self._job_costs_usd[job_id]

    def _backend_for(self, provider: str) -> Backend:
        if provider not in self._backends:
            if provider == "gemini":
                if not self._gemini_api_key:
                    raise RuntimeError("GEMINI_API_KEY is not configured")
                self._backends[provider] = GeminiBackend(self._gemini_api_key)
            elif provider == "anthropic":
                self._backends[provider] = AnthropicBackend(self._anthropic_api_key or None)
            else:
                raise ValueError(f"Unknown provider {provider!r} in llm_routing.yaml")
        return self._backends[provider]

    def complete(
        self,
        *,
        stage: str,
        prompt: str,
        job_id: str,
        system: str | None = None,
        max_tokens: int = 2048,
        output_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        route = self._routing.route_for(stage)
        limits = self._routing.limits_for(route.provider, route.model)

        # Raises DailyQuotaExhausted uncaught on a spent daily quota — no
        # retry loop here, by design (see module docstring).
        self._rate_limiter.acquire(route.provider, route.model, limits)

        backend = self._backend_for(route.provider)
        result = backend.complete(
            model=route.model,
            prompt=prompt,
            max_tokens=max_tokens,
            system=system,
            output_schema=output_schema,
            thinking_budget=route.thinking_budget,
            temperature=route.temperature,
        )

        cost_usd = _estimate_cost_usd(
            route.provider, route.model, result.input_tokens, result.output_tokens
        )
        self._job_costs_usd[job_id] += cost_usd

        logger.info(
            json.dumps(
                {
                    "job_id": job_id,
                    "stage": stage,
                    "provider": route.provider,
                    "model": route.model,
                    "stop_reason": result.stop_reason,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "extra_tokens": result.extra_tokens,
                    "cost_usd": round(cost_usd, 6),
                    "requests_used_today": self._rate_limiter.used_today(
                        route.provider, route.model
                    ),
                    "rpd_limit": limits.rpd,
                }
            )
        )

        return LLMResponse(
            text=result.text,
            stop_reason=result.stop_reason,
            provider=route.provider,
            model=route.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            extra_tokens=result.extra_tokens,
            cost_usd=cost_usd,
        )
