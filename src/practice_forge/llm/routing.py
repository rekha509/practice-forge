"""Loads config/llm_routing.yaml: which (provider, model) serves each
pipeline stage, and the RPM/RPD limits each (provider, model) pair must
respect. Nothing in code hardcodes a model — see docs/adr/0006."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ROUTING_PATH = REPO_ROOT / "config" / "llm_routing.yaml"


class StageRoute(BaseModel):
    provider: str
    model: str
    thinking_budget: int | None = None
    temperature: float | None = None


class RateLimitConfig(BaseModel):
    rpm: int
    rpd: int


class RoutingConfig(BaseModel):
    stages: dict[str, StageRoute]
    limits: dict[str, dict[str, RateLimitConfig]]

    def route_for(self, stage: str) -> StageRoute:
        try:
            return self.stages[stage]
        except KeyError:
            raise ValueError(
                f"No routing entry for stage {stage!r} in config/llm_routing.yaml"
            ) from None

    def limits_for(self, provider: str, model: str) -> RateLimitConfig:
        try:
            return self.limits[provider][model]
        except KeyError:
            raise ValueError(
                f"No rate limit entry for {provider}/{model} in config/llm_routing.yaml "
                "limits section — every routed model must have one."
            ) from None


@lru_cache
def load_routing(path: Path = DEFAULT_ROUTING_PATH) -> RoutingConfig:
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return RoutingConfig.model_validate(raw)
