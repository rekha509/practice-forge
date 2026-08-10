"""Blind re-solve tests.

The leak test below is the load-bearing one: it fails if the rendered
prompt ever contains the variant's `core_python_code` or `solution_steps`
— the whole point of "blind" is that this stage never sees how the
problem was already solved, only the problem itself.

The collision test proves `run_blind_resolve` refuses to call the LLM at
all when config/llm_routing.yaml routes it to the same (provider, model)
as `s9_codegen` — see blind_resolve.py's module docstring for why that's
enforced, not just documented.
"""

from __future__ import annotations

import uuid

import pytest

from practice_forge.db.models import VariantORM
from practice_forge.llm.client import LLMClient
from practice_forge.llm.routing import RateLimitConfig, RoutingConfig, StageRoute
from practice_forge.models.enums import DifficultyLevel, ExtensionType, VerificationStatus
from practice_forge.verification.blind_resolve import (
    BlindResolveModelCollisionError,
    build_blind_resolve_prompt,
    run_blind_resolve,
)

_DISTINCTIVE_CODE_MARKER = "MARKER_CORE_PYTHON_CODE_MUST_NOT_LEAK_9f3a2"
_DISTINCTIVE_STEPS_MARKER = "MARKER_SOLUTION_STEPS_MUST_NOT_LEAK_7c1e8"


def _make_variant() -> VariantORM:
    return VariantORM(
        id=uuid.uuid4(),
        concept_cluster_id=uuid.uuid4(),
        statement_md="A piston-cylinder contains 2 kg of air at 300 K. Find the final temperature.",
        params={"mass_kg": 2.0, "T1_K": 300.0},
        difficulty=DifficultyLevel.MEDIUM,
        topic_node_ids=[],
        solution_steps=[f"Step one. {_DISTINCTIVE_STEPS_MARKER}", "Step two."],
        core_python_code=f"import numpy as np\n# {_DISTINCTIVE_CODE_MARKER}\nprint('RESULT t2: 450.0')",
        extension_type=ExtensionType.NONE,
        extension_python_code=None,
        extension_learning_notes=None,
        extension_figure_paths=[],
        extension_metrics_json=None,
        verified_answer="{'t2': 450.0}",
        verification_status=VerificationStatus.VERIFIED,
        verification_log=[],
        needs_review=False,
        source_ref={},
        is_recycled=False,
    )


def test_blind_resolve_prompt_never_contains_code_or_solution_steps() -> None:
    variant = _make_variant()
    prompt = build_blind_resolve_prompt(variant)

    assert _DISTINCTIVE_CODE_MARKER not in prompt
    assert _DISTINCTIVE_STEPS_MARKER not in prompt
    assert variant.core_python_code not in prompt
    for step in variant.solution_steps:
        assert step not in prompt

    # The one thing this prompt MUST contain: the problem itself.
    assert variant.statement_md in prompt


def test_blind_resolve_refuses_to_call_llm_when_routed_to_same_model_as_codegen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    colliding_routing = RoutingConfig(
        stages={
            "s9_codegen": StageRoute(provider="gemini", model="gemini-flash-lite-latest"),
            "s9_blind_resolve": StageRoute(provider="gemini", model="gemini-flash-lite-latest"),
        },
        limits={"gemini": {"gemini-flash-lite-latest": RateLimitConfig(rpm=15, rpd=1000)}},
    )
    monkeypatch.setattr(
        "practice_forge.verification.blind_resolve.load_routing", lambda: colliding_routing
    )

    variant = _make_variant()
    with pytest.raises(BlindResolveModelCollisionError):
        run_blind_resolve(LLMClient.__new__(LLMClient), "job-1", variant)


def test_blind_resolve_calls_llm_when_routed_to_a_different_model(monkeypatch: pytest.MonkeyPatch) -> None:
    distinct_routing = RoutingConfig(
        stages={
            "s9_codegen": StageRoute(provider="gemini", model="gemini-flash-lite-latest"),
            "s9_blind_resolve": StageRoute(provider="gemini", model="gemini-flash-latest"),
        },
        limits={
            "gemini": {
                "gemini-flash-lite-latest": RateLimitConfig(rpm=15, rpd=1000),
                "gemini-flash-latest": RateLimitConfig(rpm=10, rpd=20),
            }
        },
    )
    monkeypatch.setattr(
        "practice_forge.verification.blind_resolve.load_routing", lambda: distinct_routing
    )

    calls: list[str] = []

    class _FakeClient:
        def complete(self, *, stage: str, prompt: str, job_id: str, **kwargs: object) -> object:
            calls.append(stage)

            class _Response:
                text = "ANSWER t2: 450.0 K"
                provider = "gemini"
                model = "gemini-flash-latest"

            return _Response()

    variant = _make_variant()
    result = run_blind_resolve(_FakeClient(), "job-1", variant)  # type: ignore[arg-type]

    assert calls == ["s9_blind_resolve"]
    assert result.raw_text == "ANSWER t2: 450.0 K"
    assert result.model == "gemini-flash-latest"
