"""Blind re-solve tests.

The leak test below is the load-bearing one: it fails if the rendered
prompt ever contains the variant's `core_python_code` or `solution_steps`
— the whole point of "blind" is that this stage never sees how the
problem was already solved, only the problem itself.

The collision test proves `run_blind_resolve` refuses to call the LLM at
all when config/llm_routing.yaml routes it to the same (provider, model)
as `s9_codegen` — see blind_resolve.py's module docstring for why that's
enforced, not just documented.

The JSON-parsing tests below are PLUMBING ONLY — every LLM response is a
hand-written fake string, not a real model call, so they prove
`_parse_json_answers`/`run_blind_resolve`'s retry logic handles the shapes
we've actually seen live (long derivations, markdown fences, malformed
JSON), not that any particular model will comply with the prompt.
"""

from __future__ import annotations

import uuid

import pytest

from practice_forge.db.models import VariantORM
from practice_forge.llm.client import LLMClient
from practice_forge.llm.routing import RateLimitConfig, RoutingConfig, StageRoute
from practice_forge.models.enums import DifficultyLevel, ExtensionType, VerificationStatus
from practice_forge.verification.blind_resolve import (
    BlindAnswerValue,
    BlindResolveModelCollisionError,
    BlindResolveParseError,
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


def _distinct_routing() -> RoutingConfig:
    return RoutingConfig(
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


class _FakeResponse:
    def __init__(self, text: str, model: str = "gemini-flash-latest") -> None:
        self.text = text
        self.provider = "gemini"
        self.model = model


def test_blind_resolve_calls_llm_when_routed_to_a_different_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "practice_forge.verification.blind_resolve.load_routing", lambda: _distinct_routing()
    )

    calls: list[tuple[str, int]] = []

    class _FakeClient:
        def complete(self, *, stage: str, prompt: str, job_id: str, max_tokens: int, **kwargs: object) -> object:
            calls.append((stage, max_tokens))
            return _FakeResponse('{"t2": {"value": 450.0, "unit": "K"}}')

    variant = _make_variant()
    result = run_blind_resolve(_FakeClient(), "job-1", variant)  # type: ignore[arg-type]

    assert calls == [("s9_blind_resolve", 4096)]
    assert result.raw_text == '{"t2": {"value": 450.0, "unit": "K"}}'
    assert result.answers == {"t2": BlindAnswerValue(value=450.0, unit="K")}
    assert result.model == "gemini-flash-latest"


def test_blind_resolve_parses_json_after_a_long_derivation(monkeypatch: pytest.MonkeyPatch) -> None:
    """A deliberately long derivation (thousands of characters of LaTeX/
    prose, the shape real responses actually took before v2's stricter
    prompt) preceding the trailing JSON block -- proves our own parsing
    finds the real answer regardless of how much reasoning came before it,
    and that max_tokens=4096 (not the old 1024) is what's actually sent, so
    a real long derivation isn't truncated before reaching its answer."""
    monkeypatch.setattr(
        "practice_forge.verification.blind_resolve.load_routing", lambda: _distinct_routing()
    )
    long_derivation = "We analyze the four processes of the cycle.\n" + ("T_1 = 300 K, P_1 = 100 kPa. " * 300)
    response_text = long_derivation + '\n\n{"net_work": {"value": 300.75, "unit": "kJ"}}'
    assert len(response_text) > 4000  # the derivation really is long, not a token-count fake-out

    seen_max_tokens: list[int] = []

    class _FakeClient:
        def complete(self, *, stage: str, prompt: str, job_id: str, max_tokens: int, **kwargs: object) -> object:
            seen_max_tokens.append(max_tokens)
            return _FakeResponse(response_text)

    variant = _make_variant()
    result = run_blind_resolve(_FakeClient(), "job-1", variant)  # type: ignore[arg-type]

    assert seen_max_tokens == [4096]
    assert result.answers == {"net_work": BlindAnswerValue(value=300.75, unit="kJ")}


def test_blind_resolve_tolerates_a_markdown_json_fence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "practice_forge.verification.blind_resolve.load_routing", lambda: _distinct_routing()
    )

    class _FakeClient:
        def complete(self, *, stage: str, prompt: str, job_id: str, **kwargs: object) -> object:
            return _FakeResponse('```json\n{"t2": {"value": 450.0, "unit": "K"}}\n```')

    variant = _make_variant()
    result = run_blind_resolve(_FakeClient(), "job-1", variant)  # type: ignore[arg-type]
    assert result.answers == {"t2": BlindAnswerValue(value=450.0, unit="K")}


def test_blind_resolve_retries_once_on_invalid_json_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "practice_forge.verification.blind_resolve.load_routing", lambda: _distinct_routing()
    )

    responses = [
        _FakeResponse("t2 is approximately 450 K, no JSON here"),
        _FakeResponse('{"t2": {"value": 450.0, "unit": "K"}}'),
    ]
    calls: list[str] = []

    class _FakeClient:
        def complete(self, *, stage: str, prompt: str, job_id: str, **kwargs: object) -> object:
            calls.append(job_id)
            return responses[len(calls) - 1]

    variant = _make_variant()
    result = run_blind_resolve(_FakeClient(), "job-1", variant)  # type: ignore[arg-type]

    assert calls == ["job-1-attempt1", "job-1-attempt2"]
    assert result.answers == {"t2": BlindAnswerValue(value=450.0, unit="K")}


def test_blind_resolve_raises_after_two_invalid_json_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "practice_forge.verification.blind_resolve.load_routing", lambda: _distinct_routing()
    )

    class _FakeClient:
        def complete(self, *, stage: str, prompt: str, job_id: str, **kwargs: object) -> object:
            return _FakeResponse("no JSON in this response at all")

    variant = _make_variant()
    with pytest.raises(BlindResolveParseError):
        run_blind_resolve(_FakeClient(), "job-1", variant)  # type: ignore[arg-type]
