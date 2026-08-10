# Per-discipline sandbox image for mechanical (profiles/mechanical.yaml's
# solver_libs). Adds CoolProp on top of the shared base — needed for real
# steam/gas property lookups (steam tables), which several real generated
# solutions genuinely require and a hand-coded polynomial fit cannot
# reliably substitute for. Confirmed the gap live: a real S9 codegen
# attempt failed with `ModuleNotFoundError: No module named 'CoolProp'`
# because this image didn't exist yet and every discipline was falling
# back to the base image.

FROM practice-forge-sandbox-base:latest

RUN pip install --no-cache-dir CoolProp==6.6.0
