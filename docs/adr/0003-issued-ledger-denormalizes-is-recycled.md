# 3. IssuedLedger denormalizes `is_recycled` to enforce the no-repeat constraint

## Status
Accepted

## Context
The spec's hard guarantee: `IssuedLedger` has `UNIQUE (course_id,
concept_cluster_id)` *unless* the row is recycled (S7d — when fewer than 20
unissued clusters remain, the system reissues a cluster with materially
different parameters/framing/extension type, flagged `is_recycled`).

`is_recycled` is a `Variant` field in the spec's data model, not an
`IssuedLedger` field. A Postgres partial unique index can't reach across
tables to check a sibling row's column.

## Decision
`issued_ledger` carries its own `is_recycled` boolean column, written from
`Variant.is_recycled` in the same S10 transaction that writes the ledger row.
The uniqueness guarantee is one partial unique index:

```sql
CREATE UNIQUE INDEX uq_issued_ledger_course_cluster_unless_recycled
ON issued_ledger (course_id, concept_cluster_id)
WHERE is_recycled = false;
```

## Consequences
- The no-repeat guarantee is enforced by Postgres itself, not application
  logic that could be bypassed by a bug in the selection code.
- Requires S10 to keep the two `is_recycled` values in sync at write time —
  there is exactly one write path (the S10 ledger-commit transaction), so
  this is a single, auditable place to get right rather than a general
  denormalization-drift risk.
