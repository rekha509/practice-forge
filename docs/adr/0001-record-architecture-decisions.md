# 1. Record architecture decisions

## Status
Accepted

## Context
This project runs autonomously across many sessions (see PROGRESS.md). A
future session — possibly with no memory of this one — needs to know *why*
a non-obvious choice was made, not just what the code currently does.

## Decision
We use ADRs, one file per significant decision, numbered sequentially in
`docs/adr/`. Each records status, context, decision, and consequences.

## Consequences
Any decision that isn't obvious from reading the code gets a short ADR
before moving on. Obvious mechanical choices don't need one.
