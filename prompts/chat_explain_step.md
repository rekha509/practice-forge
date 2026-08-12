<!-- version: 1 -->
<!-- used by: api/routers/problem_sets.py's POST /{problem_set_id}/chat (P12) -->
<!-- model: routed via config/llm_routing.yaml, stage "chat_explain_step" -->

A student or instructor is looking at one step of a worked solution and has
a question about it. Answer their question directly and concisely, using
the full problem and solution for context — but do not just restate the
step; explain the reasoning behind it.

Problem:
{statement_md}

Full solution steps, in order:
{solution_steps}

The step they're asking about (step {step_number} of {step_count}):
{target_step}

Their question:
{question}

Answer in a few sentences. If the question can't be answered from the
information given, say so plainly rather than guessing.
