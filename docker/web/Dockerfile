# Production build for the P11 PWA frontend (P13 deployment infra).
# Multi-stage: builder installs deps + runs `next build` (output:
# "standalone" in next.config.ts), runtime copies only what
# .next/standalone actually needs -- not the builder's full node_modules
# or the source tree. `public`/`.next/static` are copied in manually per
# Next's own standalone docs (they're excluded by default since a real
# deployment is expected to put them behind a CDN; this project doesn't
# have one yet, so the app server just serves them itself).

FROM node:22-slim AS builder
WORKDIR /app

RUN corepack enable && corepack prepare pnpm@11.21.0 --activate

COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY web/ ./
# API_PROXY_TARGET is read at request time inside next.config.ts's
# rewrites(), not baked in at build time -- set as a real runtime env var
# on the container (see docker-compose.prod.yml), not an ARG here.
RUN pnpm build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
