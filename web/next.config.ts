import type { NextConfig } from "next";

// Deliberately host:port, not a full URL with scheme -- Render's
// blueprint spec (render.yaml) can only populate this from another
// service's real address via `fromService`/`hostport`, which returns
// "name:port" with no scheme, and blueprint env vars can't concatenate a
// literal prefix onto a `fromService` value. Prepending "http://" here in
// code instead of expecting it in the env var keeps ONE var usable by
// both docker-compose.prod.yml (API_PROXY_HOST=api:8000) and render.yaml.
const API_PROXY_HOST = process.env.API_PROXY_HOST ?? "localhost:8000";
const API_PROXY_TARGET = `http://${API_PROXY_HOST}`;

const nextConfig: NextConfig = {
  // Emits .next/standalone with only the files a production deploy needs
  // (select node_modules included) — see docker/web/Dockerfile, which
  // copies exactly that output rather than the whole node_modules tree.
  output: "standalone",
  // Proxies /api/* to the real backend so a single cloudflared tunnel (or
  // any reverse proxy) pointed at this server also reaches the API — the
  // browser only ever talks to this one origin.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_PROXY_TARGET}/api/:path*` }];
  },
  // Dev-server-only concern (blocks cross-origin requests for JS chunks/
  // the HMR socket from any host but localhost) — confirmed live: without
  // it, a page loaded through a tunnel renders its initial SSR HTML fine
  // but React never hydrates, so every button silently does nothing.
  // `next start`/standalone serves compiled assets directly and has no
  // such check, so this is meaningless (and Next ignores it) outside dev
  // — guarded rather than left in unconditionally so that's not implicit.
  ...(process.env.NODE_ENV !== "production"
    ? { allowedDevOrigins: ["*.trycloudflare.com"] }
    : {}),
  // Next's dev proxy buffers the whole request body in memory and caps it
  // at 10MB by default — confirmed live: the chunked upload's 16MiB chunk
  // size (api.ts's CHUNK_SIZE) got silently truncated to "the first 10MB"
  // going through the /api/* rewrite above, corrupting every upload with
  // a chunk bigger than that. Raised well above CHUNK_SIZE, not removed,
  // so a real oversized/malicious body still gets bounded. This applies
  // in production too (rewrites/proxy behavior isn't dev-only).
  experimental: {
    proxyClientMaxBodySize: "32mb",
  },
};

export default nextConfig;
