import { defineConfig, devices } from "@playwright/test";

// End-to-end smoke: starts the REAL API on the local cache (no UW calls: --no-live) with a throwaway user DB, plus the
// dashboard on its own port, then loads every section. Real data, nothing mocked.
export default defineConfig({
  testDir: "tests",
  globalSetup: "./tests/warmup.ts",               // load every page once (cold compile) before the first test
  timeout: 90_000,
  use: { baseURL: "http://127.0.0.1:3199" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 } } },
  ],
  workers: 1,
  webServer: [
    { command: "uv run whaleproof serve --port 8199 --no-live", cwd: "../backend", url: "http://127.0.0.1:8199/api/desk/status",
      env: { SIGNALDESK_USERDB: "/tmp/signaldesk-e2e.sqlite" }, reuseExistingServer: false, timeout: 120_000 },
    { command: "next dev --turbopack -H 127.0.0.1 -p 3199", url: "http://127.0.0.1:3199/methodology",
      // 10-22: with Oct 22's 7,407 alerts the dev server hit its memory threshold mid-suite and restarted (connection refused)
      env: { WHALEPROOF_API: "http://127.0.0.1:8199", NEXT_DIST_DIR: ".next-test", NODE_OPTIONS: "--max-old-space-size=8192" },
      reuseExistingServer: false, timeout: 120_000 },
  ],
});
