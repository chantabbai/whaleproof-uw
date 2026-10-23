import type { NextConfig } from "next";

// Local only: the browser talks to this app, which proxies /api/* to `whaleproof serve` on 127.0.0.1.
const API = process.env.WHALEPROOF_API ?? "http://127.0.0.1:8100";

const nextConfig: NextConfig = {
  // Pin the root: a stray ~/package-lock.json made Turbopack pick the home folder, so edits were missed (stale SSR)
  // and the server HTML could disagree with the client (hydration errors).
  turbopack: { root: __dirname },
  outputFileTracingRoot: __dirname,
  distDir: process.env.NEXT_DIST_DIR ?? ".next",   // smoke tests use their own build dir next to the dev server
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

export default nextConfig;
