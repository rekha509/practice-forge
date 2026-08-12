# P13: production deployment

## Render (chosen path — web + api + db + redis, always-on, public link)

Render can't run `worker`/`sandbox-runner` (no Docker-socket access from
inside a service — that's what actually executes/verifies generated
code), so this is a real, disclosed split: **web + api + Postgres +
Redis run on Render** (reachable by anyone, anytime); **worker +
sandbox-runner keep running on this machine**, connecting OUT to
Render's databases over their external connection URLs.

1. Push this repo to GitHub (needed either way — Render deploys from a
   repo, not a local directory).
2. In the Render dashboard: **New > Blueprint**, point it at the repo.
   Render reads `render.yaml` (already in the repo root) and creates:
   `practice-forge-db` (Postgres, pgvector-enabled), `practice-forge-redis`
   (Key Value), `practice-forge-api`, `practice-forge-web`.
3. Set `GEMINI_API_KEY`/`ANTHROPIC_API_KEY` on `practice-forge-api` in the
   dashboard — `render.yaml` deliberately leaves these `sync: false`
   (never committed).
4. On `practice-forge-db`'s Info page, run `CREATE EXTENSION vector;` via
   its PSQL Command — needed once, Render's pgvector isn't auto-enabled.
5. On `practice-forge-redis`, add this machine's current public IP to
   its IP Allow List (Render dashboard → that service → Access Control)
   — external connections are blocked by default otherwise.
6. Point the LOCAL worker at Render's real databases instead of the
   local `db`/`redis` containers: copy the external connection strings
   from each service's Info page into `.env` as `DATABASE_URL`/
   `REDIS_URL`, then `docker compose up -d worker sandbox-runner
   sandbox-base` (skip `db`/`redis`/`api` — those now live on Render).
7. Run `alembic upgrade head` against Render's `DATABASE_URL` once, to
   create the real schema there (it starts empty).

Real, disclosed limitation: if this machine is off, `worker` can't
process new generate/reshuffle/new-set jobs — library browsing, PDF
downloads, and chat still work, since those don't need `worker`. A
full always-on generate path needs a real VPS (allows Docker-socket
access) instead of this split — worth doing later if generation-on-demand
from anywhere matters more than the setup cost.

## Local dev: the free cloudflared quick tunnel

Still fine for local dev/testing — no account needed, but the hostname
changes every restart and the tunnel has died outright multiple times
this project with no logged reason (real, disclosed instability — see
PROGRESS.md). For a stable local-dev hostname instead of Render, a named
Cloudflare Tunnel is the fix (needs a free Cloudflare account):

```
cloudflared tunnel login
cloudflared tunnel create practice-forge
cloudflared tunnel route dns practice-forge <subdomain>.<your-domain>
```

Then a `~/.cloudflared/config.yml`:
```yaml
tunnel: <tunnel-id>
credentials-file: /path/to/<tunnel-id>.json
ingress:
  - hostname: <subdomain>.<your-domain>
    service: http://localhost:3000
  - service: http_status:404
```
`cloudflared tunnel run practice-forge` (or `cloudflared service install`
to survive reboots) — the hostname is then permanent.
