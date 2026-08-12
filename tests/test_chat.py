"""explain_step.py tests -- PLUMBING ONLY: every LLM response below is a
hand-written fake string, not a real model call, so these prove prompt
construction and index validation, not answer quality.
"""

from __future__ import annotations

import uuid

import pytest

from practice_forge.chat.explain_step import StepIndexError, build_explain_step_prompt, explain_step
from practice_forge.db.models import VariantORM
from practice_forge.models.enums import DifficultyLevel, ExtensionType, VerificationStatus


def _make_variant() -> VariantORM:
    return VariantORM(
        id=uuid.uuid4(),
        concept_cluster_id=uuid.uuid4(),
        statement_md="A piston-cylinder contains 2 kg of air at 300 K.",
        params={"mass_kg": 2.0},
        difficulty=DifficultyLevel.MEDIUM,
        topic_node_ids=[],
        solution_steps=["Apply the ideal gas law.", "Solve for T2 using the isentropic relation."],
        core_python_code="print('RESULT t2: 450.0')",
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


def test_build_explain_step_prompt_includes_target_step_and_question() -> None:
    variant = _make_variant()
    prompt = build_explain_step_prompt(variant, 2, "Why is the process isentropic?")

    assert variant.statement_md in prompt
    assert "Solve for T2 using the isentropic relation." in prompt
    assert "Why is the process isentropic?" in prompt
    assert "step 2 of 2" in prompt


def test_build_explain_step_prompt_rejects_out_of_range_step() -> None:
    variant = _make_variant()
    with pytest.raises(StepIndexError):
        build_explain_step_prompt(variant, 3, "why?")
    with pytest.raises(StepIndexError):
        build_explain_step_prompt(variant, 0, "why?")


def test_explain_step_calls_llm_and_returns_stripped_text() -> None:
    calls: list[str] = []

    class _FakeClient:
        def complete(self, *, stage: str, prompt: str, job_id: str, **kwargs: object) -> object:
            calls.append(stage)

            class _Response:
                text = "  Because entropy is constant along the process.  "

            return _Response()

    variant = _make_variant()
    answer = explain_step(_FakeClient(), "job-1", variant, 2, "Why?")  # type: ignore[arg-type]

    assert calls == ["chat_explain_step"]
    assert answer == "Because entropy is constant along the process."
