// Gate fix 10-16: next dev compiles each page on its first visit, and the fresh test API builds today's signals on its
// first /api/desk/today (≈45 s after a full trading day with the live desk busy on the same machine). Together the first
// visit to "/" took over 90 s and failed its test. Load every page once before the tests
// (failures ignored: this only warms the compiler and the API's caches; the tests still check everything).
const BASE = "http://127.0.0.1:3199";
const PAGES = ["/", "/market", "/earnings", "/bets", "/watchlist", "/journal", "/tracker", "/methodology",
  "/methodology/details", "/ticker/SPY", "/ticker/NVDA"];

export default async function warmup() {
  for (const path of PAGES) {
    try {
      const r = await fetch(BASE + path, { signal: AbortSignal.timeout(240_000) });
      await r.text();                     // the page streams: wait for the whole body, not just the headers
    } catch {
      // a slow or failed warm-up is fine; the test for that page reports any real problem
    }
  }
}
