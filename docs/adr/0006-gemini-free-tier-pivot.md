# 6. Pivot from Anthropic (paid) to Gemini (free tier) as the active LLM provider

## Status
Accepted

## Context
The Anthropic account configured for this project has no billing credit —
confirmed via a live call that authenticated successfully but failed with
`400: "Your credit balance is too low to access the Anthropic API."` No
paid API budget exists. The user's direction: run everything on the Gemini
free tier via the `google-genai` SDK instead, keep the Anthropic backend
working for whenever a paid budget exists again, and make provider/model
configurable per pipeline stage rather than hardcoded — because the two
providers have completely different constraints (Anthropic: cost-bound;
Gemini free tier: **requests-per-day**-bound, not cost) and those
constraints will keep changing as accounts/plans change.

## What we found empirically (not assumed)
No bundled skill covers the `google-genai` SDK, so behavior here was
verified by introspecting the installed package and by live calls against
the real key, not recalled from training:

- `gemini-2.5-flash` and `gemini-2.5-flash-lite` — the model IDs originally
  specified for routing — both return `404: "no longer available to new
  users"` on this account. They're retired IDs; only the rolling
  `*-latest` aliases work.
- `gemini-2.5-pro` (and `gemini-pro-latest`, `gemini-2.0-flash`,
  `gemini-2.0-flash-lite`) return `429 RESOURCE_EXHAUSTED` with
  **`limit: 0`** explicitly quoted in the error for every quota dimension
  (RPD, RPM, input-tokens) — this account has zero free-tier quota for
  anything Pro-tier or those specific legacy IDs, not a transient rate
  limit.
- `gemini-flash-lite-latest` works cleanly.
- `gemini-flash-latest` works, but is a thinking model by default — it
  spent 94 thinking tokens replying "OK" to a 16-token budget. Thinking
  tokens are billed against the same output-token quota; `thinking_config
  = ThinkingConfig(thinking_budget=0)` disables it, `thinking_budget=None`
  leaves it on the model's automatic default.
- Structured JSON output is via `response_mime_type="application/json"` +
  `response_json_schema=<standard JSON Schema dict>` — a separate field
  from `response_schema` (which wants a `genai.types.Schema` object or
  Pydantic model in Google's own OpenAPI-3.0-subset format). Using
  `response_json_schema` meant the same schema dicts already built for
  Anthropic's `output_config.format` could be reused as-is.
- Free-tier per-key RPM/RPD numbers aren't exposed via the API — only via
  the account-specific AI Studio rate-limit page, which isn't fetchable
  here. `config/llm_routing.yaml`'s `limits` section carries forward the
  user's own approximate figures for the equivalent tier (~1000/day
  Flash-Lite, ~250/day Flash) applied to the working aliases, flagged as
  best-effort and meant to be corrected against the real account page.

**Consequence for routing:** no working free-tier Pro-tier model exists on
this account at all right now. Decided with the user: route S8/S9 (variant
generation, code generation — the highest-stakes stages) to
`gemini-flash-latest` with thinking left on, rather than blocking on a
Gemini quota increase or spending paid Anthropic credit.

## Decision
- `llm/` is now a provider-agnostic package: `llm/backends/{base,
  anthropic_backend, gemini_backend}.py` implement a common `Backend`
  protocol; `llm/client.py`'s `LLMClient` is the facade every pipeline
  stage calls through via `stage=` (e.g. `"s3_confirm"`), never a hardcoded
  model string.
- `config/llm_routing.yaml` maps stage -> {provider, model,
  thinking_budget} and (provider, model) -> {rpm, rpd}. Changing providers
  or models is a YAML edit, not a code change.
- `llm/rate_limiter.py`: an in-memory token bucket enforces RPM (blocking
  sleep — this is a batch pipeline, not a live server); a JSON file
  (`data/llm_rate_limit_state.json`, gitignored) persists each
  (provider, model, UTC date)'s request count so RPD tracking survives
  process restarts. `acquire()` raises `DailyQuotaExhausted` immediately on
  a spent daily quota — no retry loop, ever, into an exhausted quota.
- `llm/batching.py`: every high-volume stage sends ALL its items in one
  call and gets a JSON array back, because per-item calls are not viable
  under a ~250-1000/day budget. Each item's schema carries an `index`
  field; alignment on read is by that field, not by response position, so
  a dropped/malformed element degrades to `None` for that one item instead
  of invalidating the batch.
- Anthropic pricing/cost tracking stays in `llm/client.py` (Gemini free
  tier is $0 by construction); Gemini calls log token counts and
  `requests_used_today` instead, which is the metric that actually matters
  there.

## Consequences
- S3's confirm pass (`detection.py`) is now batched (`BATCH_SIZE = 20`) and
  routes through `stage="s3_confirm"` instead of a hardcoded Haiku call.
  `_fake_confirm` from the earlier (Anthropic-era) P3 gate is gone — see
  `docs/adr` cross-reference in PROGRESS.md and `tests/stubs.py` for the
  replacement discipline (stubs require explicit `PF_USE_STUB_LLM=1`
  opt-in and are never used for the accuracy gate itself).
- The routing/limits numbers in `config/llm_routing.yaml` are best-effort
  and will need correcting against the account's real AI Studio
  rate-limit page — flagged inline in that file, not silently trusted.
- `*-latest` aliases can change underneath the pipeline without notice
  (Google's own stated tradeoff for using them) — accepted deliberately
  since the pinned `2.5-*` IDs are the ones that don't work.
- Marker-pdf, when it eventually replaces the `pypdf` placeholder (see
  `docs/adr/0004`), must run **without** `--use_llm` — an LLM-assisted
  extraction pass would compete with the pipeline's own stages for the
  same scarce daily request budget, for a stage (raw text extraction) that
  doesn't need it as urgently as classification/scoring/solving do.
