"""S9 blind re-solve: an independent second opinion on a variant's answer,
for shipped variants where no book answer exists to calibrate against
(see calibration.py for the stronger check when one does).

Deliberately blind and deliberately a different model:

- The rendered prompt (`build_blind_resolve_prompt`) contains ONLY
  `statement_md` and `params` — never `core_python_code`, never
  `solution_steps`. See prompts/s9_blind_resolve.md and
  tests/test_blind_resolve.py's leak test, which fails if either ever
  appears in the rendered prompt.
- `run_blind_resolve` refuses to call the LLM at all
  (`BlindResolveModelCollisionError`) if config/llm_routing.yaml ever
  routes stage "s9_blind_resolve" to the exact same (provider, model) as
  stage "s9_codegen" — 20/20 agreement between a solver and a re-solver on
  the SAME model measures nothing, so this is enforced, not just
  commented.

The response is free text ("ANSWER <name>: <value> <unit>" lines per the
prompt) parsed with the SAME `answer_parsing.parse_numeric_values` used
for the book's own `final_answer` column — one parser, two real sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from practice_forge.db.models import VariantORM
from practice_forge.llm.client import LLMClient
from practice_forge.llm.routing import load_routing

_BLIND_RESOLVE_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "s9_blind_resolve.md"


class BlindResolveModelCollisionError(RuntimeError):
    """Raised when stage "s9_blind_resolve" is routed to the SAME
    (provider, model) as stage "s9_codegen" — defeats the entire point of
    an independent re-solve. Fix config/llm_routing.yaml, don't catch
    this."""


def build_blind_resolve_prompt(variant: VariantORM) -> str:
    """Renders the blind-resolve prompt from ONLY `statement_md`/`params` —
    deliberately excludes `core_python_code` and `solution_steps`, which
    this function never even reads off `variant`."""
    return (
        _BLIND_RESOLVE_PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{statement_md}", variant.statement_md)
        .replace("{params}", str(variant.params))
    )


@dataclass(frozen=True)
class BlindResolveResult:
    raw_text: str
    provider: str
    model: str


def run_blind_resolve(client: LLMClient, job_id: str, variant: VariantORM) -> BlindResolveResult:
    routing = load_routing()
    blind_route = routing.route_for("s9_blind_resolve")
    codegen_route = routing.route_for("s9_codegen")
    if (blind_route.provider, blind_route.model) == (codegen_route.provider, codegen_route.model):
        raise BlindResolveModelCollisionError(
            f"s9_blind_resolve and s9_codegen are both routed to "
            f"{blind_route.provider}/{blind_route.model} — see "
            "config/llm_routing.yaml and this module's docstring."
        )

    prompt = build_blind_resolve_prompt(variant)
    response = client.complete(stage="s9_blind_resolve", prompt=prompt, job_id=job_id, max_tokens=1024)
    return BlindResolveResult(raw_text=response.text, provider=response.provider, model=response.model)
