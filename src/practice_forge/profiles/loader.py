"""Loads profiles/*.yaml into validated DisciplineProfile objects.

Discipline differences (solver libs, ML libs, permitted extension types,
topic taxonomy, sandbox image) live entirely in these declarative files —
pipeline code must never branch on discipline key directly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator

from practice_forge.config import get_settings
from practice_forge.models.enums import ExtensionType


class TopicSpec(BaseModel):
    name: str
    # Real terms a book's own section titles use for this topic, matched
    # via keyword overlap (structure.py's match_topic_nodes) — needed
    # because a topic's bare name alone rarely overlaps enough with a real
    # chapter title to clear TOPIC_MATCH_THRESHOLD.
    aliases: list[str] = []


class DisciplineProfile(BaseModel):
    key: str
    display_name: str
    sandbox_image_tag: str
    solver_libs: list[str]
    ml_libs: list[str]
    allowed_extension_types: list[ExtensionType]
    topics: list[TopicSpec]

    @field_validator("topics", mode="before")
    @classmethod
    def _coerce_bare_topic_names(cls, topics: list[Any]) -> list[Any]:
        # Backward compatible with the original flat `topics: [str, ...]`
        # form still used by every profile except mechanical.yaml — a bare
        # string is just a topic with no aliases yet.
        return [{"name": t} if isinstance(t, str) else t for t in topics]


def _profiles_dir() -> Path:
    return get_settings().profiles_dir


@lru_cache
def load_profile(key: str) -> DisciplineProfile:
    path = _profiles_dir() / f"{key}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No discipline profile for key={key!r} at {path}")
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return DisciplineProfile.model_validate(raw)


@lru_cache
def list_profiles() -> tuple[DisciplineProfile, ...]:
    profiles_dir = _profiles_dir()
    keys = sorted(p.stem for p in profiles_dir.glob("*.yaml"))
    return tuple(load_profile(key) for key in keys)
