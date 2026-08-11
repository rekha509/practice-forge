# 10. Per-faculty bearer token as the minimum viable auth for P10

## Status
Accepted

## Context
`IssuedLedger`'s no-repeat guarantee is scoped per `Course`
(`docs/adr/0003`), and `Course.faculty_name`/`institution` are free-text
display fields with no real ownership check anywhere. Once P10 exposes
`POST /api/problem-sets/{id}/new-set` over HTTP, anyone who can reach the
API can write to any course's ledger — burning a real faculty member's
concept pool (e.g. "AI/ML for Mechanical Systems", faculty Mahesh, RGUKT
Basar) with no way to attribute or prevent it.

Full auth (real accounts, password resets, sessions, SSO) is out of scope
for a departmental tool at this stage and was explicitly not requested —
the ask was for the *minimum* that distinguishes one faculty member from
another, with tradeoffs flagged, decided by the user before implementation
(not by default).

Three options were presented: (a) a per-faculty bearer token, (b)
magic-link email login, (c) username/hashed-password. The user chose (a).

## Decision
Add `FacultyORM` (`id`, `name`, `institution`, `token` — unique, random,
opaque). `CourseORM` gains a nullable `faculty_id` FK (existing
`faculty_name`/`institution` columns are untouched display fields, not
derived from this — a course's printed faculty name shouldn't silently
change if the owning account is ever renamed).

Every mutating API request carries `Authorization: Bearer <token>`. A
FastAPI dependency (`api/auth.py::get_current_faculty`) resolves it to a
`FacultyORM` row or raises 401. Endpoints that act on a `Course` (generate,
reshuffle, new-set) additionally check `course.faculty_id == faculty.id`
(or `faculty_id is None`, i.e. an unclaimed legacy course) before
proceeding, raising 403 otherwise. Read-only endpoints (library list/
detail, job status, problem-set/PDF downloads) do not require a token —
nothing sensitive is scoped there, and requiring one would just add
friction to the low-stakes majority of requests.

No login form, no password, no session store. A faculty member's token is
provisioned once (an admin creates the `Faculty` row and hands over the
token out of band — email, in person, whatever) and pasted into the PWA
once, where it's kept in `localStorage`.

## Consequences
- Real: distinguishes individuals, scopes ledger-mutating actions to the
  Course they actually own, costs almost nothing to build or operate (one
  table, one dependency, one ownership check).
- Not real auth: a leaked token is fully valid until an admin deletes/
  reissues the row — no expiry, no revocation UI, no audit log beyond
  whatever the DB itself records. Acceptable for a small departmental
  deployment; not acceptable if this ever needs to survive a token leak
  gracefully or support self-service password/token reset.
- No signup flow exists yet — Faculty rows are created directly (a `pf`
  CLI command or a one-off admin script), not through the API. Out of
  scope for this decision; flagged so it isn't assumed to exist.
- If the school ever wants institutional SSO, this whole mechanism is
  replaced, not extended — `faculty_id`/`get_current_faculty`'s call
  signature is the only real coupling point, so the replacement cost is
  contained to `api/auth.py` and however Faculty rows get created.
