<!-- version: 1 -->
<!-- used by: src/practice_forge/scoring/scoring.py (S6 candidate scoring) -->
<!-- model: routed via config/llm_routing.yaml, stage "s6_scoring" -->

You are scoring engineering concepts for inclusion in a student practice
problem set. Score EACH concept below on six axes, 0-5, with a one-line
written rationale for each axis.

- pedagogical_value: does this teach a transferable method, or is it a
  one-line plug-in-the-formula exercise?
- computational_suitability: does writing Python code for this add real
  value — iteration, root-finding, a parametric sweep, a plot — or would
  code just restate one line of arithmetic?
- self_containedness: is the problem fully specified without needing an
  external reference the system can't access? IMPORTANT: this discipline's
  solver stack includes CoolProp, which computes steam and gas properties
  (enthalpy, entropy, specific volume, etc.) directly from state variables
  — the same properties a student would otherwise look up in a steam table
  or gas table appendix. Do NOT score self_containedness low just because
  a problem needs a steam/gas table lookup — CoolProp can supply that value
  in generated code instead of an appendix. Only score this axis low when
  a genuinely non-obtainable-from-CoolProp value is needed (e.g. a
  material property specific to this textbook's own worked example, not a
  standard fluid property).
- syllabus_centrality: how core is this topic to how the subject is
  actually taught?
- verifiability: is there a checkable final answer given or derivable?
- ml_extension_potential: would an ML teaching extension attached to this
  problem teach something real, or would it be decoration? Score 0 if
  nothing about this concept plausibly supports surrogate modeling,
  digital twins, anomaly detection, design optimization, sensitivity
  analysis, or uncertainty quantification.

Also assign difficulty: "easy", "medium", or "hard".

Concepts:
{concepts_block}

Return a JSON array with exactly one object per concept, one per index
below. Copy each concept's own "index" value into your object for it.
scoring_rationale must be an object with keys exactly matching the six axis
names above, each a one-sentence rationale string.

Respond with the requested JSON only.
