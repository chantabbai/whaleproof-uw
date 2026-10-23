/** "$879K", "$1.3M"; a value that rounds up into the next unit moves to it ($999.6K → "$1.0M", never "$1000K"). */
export const money = (v: number | null | undefined): string => {
  if (v == null) return "–";
  if (v < 0) return `−${money(-v)}`;
  const up = (x: number, d: number) => Math.round(x * 10 ** d) / 10 ** d;
  if (up(v / 1e9, 1) >= 1) return `$${(v / 1e9).toFixed(1)}B`;
  if (up(v / 1e6, 1) >= 1) return `$${(v / 1e6).toFixed(1)}M`;
  if (up(v / 1e3, 0) >= 1) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
};
export const signedMoney = (v: number | null | undefined) => (v == null ? "–" : `${v >= 0 ? "+" : "−"}${money(Math.abs(v))}`);
/** True when v shows as 0 at d decimals (in %), so it gets no sign, no arrow and no up/down colour. */
export const isFlat = (v: number, d = 1) => Number((Math.abs(v) * 100).toFixed(d)) === 0;
export const pct = (v: number | null | undefined, d = 1) =>
  v == null || Number.isNaN(v) ? "–" : isFlat(v, d) ? `${(0).toFixed(d)}%` : `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(d)}%`;
/** "▲ +1.2%" / "▼ −1.2%" / "0.0%": the arrow follows the number as shown, never a hidden −0.004%. */
export const arrowPct = (v: number, d = 1) => (isFlat(v, d) ? pct(v, d) : `${v > 0 ? "▲" : "▼"}\u00a0${pct(v, d)}`);
/** Decimals for a hold's move: two under 0.1% so a nearly flat hold reads "▼ −0.04%", not a frozen "0.0%". */
export const moveDigits = (v: number | null | undefined) => (v != null && Math.abs(v) < 0.001 ? 2 : 1);
/** Up/down colour class for a move, muted when it rounds to flat. */
export const moveTone = (v: number | null | undefined, d = 1) =>
  v == null || isFlat(v, d) ? "text-muted" : v > 0 ? "text-bull" : "text-bear";
export const days = (n: number) => plural(n, "day");
/** Days to expiry: 0 reads "expires today" (was "0 days"); `tail` (" out") is only added to a count of days. */
export const dte = (n: number, tail = "") => (n === 0 ? "expires today" : `${days(n)}${tail}`);
export const plainPct = (v: number | null | undefined, d = 0) =>
  v == null ? "–" : `${(v * 100).toFixed(d).replace(/^-(0\.?0*)$/, "$1").replace(/^-/, "−")}%`;
export const num = (v: number | null | undefined, d = 0) =>
  v == null ? "–" : v.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
export const px = (v: number | null | undefined) =>
  v == null ? "–" : `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
/** Earnings options-vs-usual ratio: one decimal, two near the cheap (0.8) and rich (1.25) lines so the number agrees
 *  with its label (0.79 cheap, 0.82 fair). */
export const ratioX = (r: number) => (Math.abs(r - 0.8) < 0.05 || Math.abs(r - 1.25) < 0.05 ? r.toFixed(2) : r.toFixed(1));
/** A price level on a small chart: whole numbers bare, otherwise two decimals (192.50, 210). */
export const lvl = (v: number) => (Number.isInteger(v) ? v.toLocaleString("en-US") : px(v).slice(1));
const etYear = (now: Date) => now.toLocaleDateString("sv-SE", { timeZone: "America/New_York" }).slice(0, 4);
/** "Tue, Oct 13"; a date in another year also gets the year ("Fri, Sep 17, 2027"), so a far expiry or an old report
 *  can't pass for this year. */
export const shortDate = (iso: string | null | undefined, now: Date = new Date()) => {
  if (!iso) return "–";
  // a full timestamp (e.g. 01:22 UTC) is dated in ET, not by its UTC day
  const day = iso.length > 10 ? new Date(iso).toLocaleDateString("sv-SE", { timeZone: "America/New_York" }) : iso.slice(0, 10);
  const d = new Date(`${day}T12:00:00`);
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: day.slice(0, 4) === etYear(now) ? undefined : "numeric" });
};
/** "Oct 13"; with the year when it isn't this year ("Sep 17, 2027"). */
export const md = (iso: string | null | undefined, now: Date = new Date()) => {
  if (!iso) return "–";
  const d = new Date(`${iso.slice(0, 10)}T12:00:00`);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: iso.slice(0, 4) === etYear(now) ? undefined : "numeric" });
};
/** When a report lands, as Sightings says it: "before the open", "after the close", "time not set". */
export const reportWhen = (t: string | null | undefined) =>
  t === "premarket" ? "before the open" : t === "postmarket" || t === "afterhours" ? "after the close" : "time not set";
/** An earnings warning in plain words: "Earnings Thu, Oct 29, after the close; last full session before it: Thu, Oct 29". */
export const earnWarnText = (w: { date: string; time: string; last_session_before: string }, now: Date = new Date()) =>
  `Earnings ${shortDate(w.date, now)}, ${reportWhen(w.time)}; last full session before it: ${shortDate(w.last_session_before, now)}`;
/** "1 day", "2 days", "1,204 alerts". */
export const plural = (n: number | null | undefined, word: string, many = `${word}s`) =>
  n == null ? "–" : `${n.toLocaleString("en-US")} ${n === 1 ? word : many}`;
export const etTime = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "numeric", minute: "2-digit" }) + " ET" : "–";
export const age = (s: number | null | undefined) =>
  s == null ? "never" : s < 90 ? `${Math.round(s)} s old` : s < 5400 ? `${Math.round(s / 60)} min old` : `${(s / 3600).toFixed(1)} h old`;
/** Option price vs the stock's realized move: same cut-offs as the engine (backend core/options/pricing.value_view). */
export const IV_RV_CHEAP = 0.95, IV_RV_RICH = 1.35;
export const TIER: Record<string, string> = { whale: "Whale-size bet", far_otm: "Long shot, not overpriced" };

/** OCC option symbol → plain English: "CRWV261023C00107000" → "CRWV $107 call, Fri, Oct 23 2026". */
export const contractLabel = (sym: string | null | undefined, now: Date = new Date()) => {
  const m = sym?.match(/^([A-Z.]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$/);
  if (!m) return sym ?? "–";
  const [, tk, yy, mm, dd, cp, k] = m;
  return `${tk} ${px(Number(k) / 1000)} ${cp === "C" ? "call" : "put"}, expires ${shortDate(`20${yy}-${mm}-${dd}`, now)}`;
};

// Ticker page "Past signals" tile: a signal still open (today's or in its hold) is not "never a signal" (NTRA Oct 23)
export const pastSignalsSub = (p: { finished: number; open: boolean; holding: boolean; benchmark: boolean }) =>
  p.finished ? (p.benchmark ? "went up over five days (this is the S&P, so no comparison)" : "beat the S&P over five days")
    : p.open ? (p.holding ? "none finished yet, still in its five-day hold" : "none finished yet")
    : "never a signal since Oct 2023";
