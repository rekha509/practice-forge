# Base sandbox image shared by every discipline (see PIPELINE STAGES S9 and
# profiles/*.yaml). Per-discipline images FROM this and add solver_libs/ml_libs
# for that discipline only — kept out of P1 scope, added starting P7/P8.

FROM python:3.12-slim

RUN pip install --no-cache-dir \
    pint==0.24.4 \
    numpy==2.0.1 \
    sympy==1.13.1 \
    scipy==1.14.0 \
    matplotlib==3.9.1

# The runner always sets --read-only with a /tmp tmpfs and runs as UID 65534
# (nobody). No writable HOME exists in the image itself, so matplotlib/config
# caches are redirected into that tmpfs at runtime.
ENV MPLBACKEND=Agg
ENV MPLCONFIGDIR=/tmp/mplconfig
ENV HOME=/tmp

WORKDIR /tmp
