"""Loads profiles/*.yaml into validated DisciplineProfile objects.

Discipline differences (solver libs, ML libs, permitted extension types,
topic taxonomy, sandbox image) live entirely in these declarative files —
pipeline code must never branch on discipline key directly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from practice_forge.config import get_settings
from practice_forge.models.enums import ExtensionType


class DisciplineProfile(BaseModel):
    key: str
    display_name: str
    sandbox_image_tag: str
    solver_libs: list[str]
    ml_libs: list[str]
    allowed_extension_types: list[ExtensionType]
    topics: list[str]


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
