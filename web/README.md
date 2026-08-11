# practice-forge web (P11)

The PWA frontend for practice-forge's P10 API — library, resumable ingest
progress, generator, and problem-set view. Next.js 16 (App Router,
Turbopack) + Tailwind v4 + shadcn/ui (Base UI primitives, not Radix).

## Run locally

Requires the P10 API running separately (see the repo root's
`docker-compose.yml`, or `uvicorn api.main:app` + a Celery worker + Redis
+ Postgres directly).

```bash
pnpm install
cp .env.local.example .env.local   # points at the API; edit if it's not on localhost:8000
pnpm dev
```

## Design direction

Restrained, near-monochrome, one accent colour (a deep oxblood, `#6b2737`)
reserved for primary actions only. Problem statements and solution steps
render in a serif face (`Source Serif 4`, via the `.statement-prose`
class in `globals.css`) — they're textbook artifacts. Code renders in
Geist Mono with real Prism syntax highlighting (`src/components/code-
block.tsx`).

## Auth

No login form — a per-faculty bearer token, set via the button in the
top-right corner, stored in `localStorage` (see `src/lib/auth.tsx` and
the API's `docs/adr/0010`). Course provisioning isn't self-service yet;
the Generator screen's "Course ID" field is a manual paste until that
exists.

## PWA

`src/app/manifest.ts` + `public/sw.js` (hand-rolled, not a plugin — real
offline app-shell caching, network-first for everything else, never
caches `/api/*`). Verified real installability via Chrome's own
`Page.getInstallabilityErrors` CDP call (zero errors) — Lighthouse's
`pwa` category was removed upstream, so that's the current, authoritative
check instead.
