"use client";
import Link from "next/link";
import { useState } from "react";
import { MatchedAndPeriods, type History } from "./BetsTable";
import { More, MoreList } from "./v2/ui";
import { pct, plainPct, px, shortDate, days, plural } from "@/lib/format";

type Inputs = { ticker: string; spot: number; spot_date: string; spot_source?: "close" | "alert"; otm_pct: number; dte: number; sector: string | null };
type Filter = { signal: boolean; stage: string; tier: string | null; reason: string; record?: { tier: string; trades: number; beat: number; avg: number } };
type Result = History & { inputs: Inputs | null; filter: Filter | null };

/** The one-line answer a trader wants first, from the same history numbers. */
function verdict(h: History): [string, string] {
  if (h.matches === 0) return ["No earlier bets like this.", "Nothing in three years of history to compare it with."];
  if (h.thin) return ["Too few to tell.", `Only ${plural(h.matches, "earlier bet")} like it.`];
  if (h.periods_agree === false) return ["Noise.", `The test periods disagree, so the ${pct(h.avg)} average could be luck.`];
  if (h.periods_agree == null) return ["Too soon to tell.", "Fewer than two test periods have 10 or more bets like it, so they can't be compared."];
  return (h.avg ?? 0) > 0 ? ["Beat the S&P in every test period.", "History only: bets like this were never tested as a signal."]
    : ["Lagged the S&P in every test period.", "Bets like this tended to trail the market over five days."];
}
const TIER: Record<string, string> = { whale: "a whale-size bet", far_otm: "a long shot at a fair price" };
const TIER_PLURAL: Record<string, string> = { whale: "Whale-size bets", far_otm: "Long shots" };

/** "Check a bet you saw on Unusual Whales": typed the way UW shows an alert (ticker, strike, expiry), or by hand
 *  (% out of the money and days) when there's no ticker. Shows how earlier bets like it did. */
export default function LookupForm({ todays = {} }: { todays?: Record<string, number> }) {
  const [byHand, setByHand] = useState(false);
  const [ticker, setTicker] = useState("");
  const [side, setSide] = useState("bought");
  const [type, setType] = useState("call");
  const [strike, setStrike] = useState("");
  const [expiry, setExpiry] = useState("");
  const [premium, setPremium] = useState("500000");
  const [dte, setDte] = useState("30");
  const [otm, setOtm] = useState("5");
  const [sweep, setSweep] = useState(false);
  const [res, setRes] = useState<Result | null | { err: string }>(null);

  async function go(e: React.FormEvent) {
    e.preventDefault();
    const call = type === "call";
    const bought = side === "bought";
    const p = new URLSearchParams({
      direction: String((call ? 1 : -1) * (bought ? 1 : -1)), opt_type: type, premium, sweep: String(sweep),
      bet_kind: bought ? "clean buy" : call ? "not a clean buy" : "put sale",
      ...(byHand ? { dte, otm_pct: String(Number(otm) / 100) } : { ticker: ticker.trim().toUpperCase(), strike, expiry }),
    });
    const r = await fetch(`/api/desk/lookup?${p}`, { cache: "no-store" }).catch(() => null);
    if (r?.ok) return setRes(await r.json());
    const msg = r ? ((await r.json().catch(() => null))?.detail as string | undefined) : undefined;
    setRes({ err: msg && msg !== "bad lookup" ? msg : "Couldn't look that up. Check the numbers and try again." });
  }

  const showToday = (t: string) => { window.dispatchEvent(new CustomEvent("bets:ticker", { detail: t })); document.getElementById("bets")?.scrollIntoView({ behavior: "smooth" }); };
  const f = "field mt-1 px-2 text-text";
  const out = (v: number) => (v < 0 ? `${Math.round(-v * 100)}% in the money` : Math.round(v * 100) === 0 ? "at the money" : `${Math.round(v * 100)}% out of the money`);
  const inp = res && !("err" in res) ? res.inputs : null;
  const n = inp ? todays[inp.ticker] ?? 0 : 0;
  return (
    <div>
      <form onSubmit={go} className="flex flex-wrap items-end gap-2" aria-label="Check a bet">
        {!byHand && <label className="grid text-xs text-muted">Ticker<input className={`${f} w-24 uppercase`} required value={ticker}
          onChange={(e) => setTicker(e.target.value.replace(/[^A-Za-z0-9.\-]/g, ""))} placeholder="NVDA" autoCapitalize="characters" /></label>}
        <label className="grid text-xs text-muted">Side<select className={f} value={side} onChange={(e) => setSide(e.target.value)}>
          <option value="bought">Bought (at the ask)</option><option value="sold">Sold (at the bid)</option></select></label>
        <label className="grid text-xs text-muted">Type<select className={f} value={type} onChange={(e) => setType(e.target.value)}>
          <option value="call">Call</option><option value="put">Put</option></select></label>
        {byHand ? <>
          <label className="grid text-xs text-muted">Days to expiry<input className={`${f} w-20`} inputMode="numeric" required value={dte}
            onChange={(e) => setDte(e.target.value.replace(/[^0-9]/g, ""))} /></label>
          <label className="grid text-xs text-muted">% out of the money (negative if in)<input className={`${f} w-20`} inputMode="decimal" required value={otm}
            onChange={(e) => setOtm(e.target.value.replace(/[^0-9.-]/g, ""))} /></label>
        </> : <>
          <label className="grid text-xs text-muted">Strike<input className={`${f} w-24`} inputMode="decimal" required value={strike}
            onChange={(e) => setStrike(e.target.value.replace(/[^0-9.]/g, ""))} placeholder="210" /></label>
          <label className="grid text-xs text-muted">Expiry<input className={f} type="date" required value={expiry} onChange={(e) => setExpiry(e.target.value)} /></label>
        </>}
        <label className="grid text-xs text-muted">Paid ($)<input className={`${f} w-32`} inputMode="numeric" required value={premium ? Number(premium).toLocaleString("en-US") : ""}
          onChange={(e) => setPremium(e.target.value.replace(/[^0-9]/g, "").slice(0, 12))} /></label>
        <label className="flex items-center gap-1.5 pb-2 text-sm"><input type="checkbox" checked={sweep} onChange={(e) => setSweep(e.target.checked)} /> Sweep</label>
        <button type="submit" className="btn">Check this bet</button>
      </form>
      <button type="button" className="mt-2 text-xs text-muted underline underline-offset-4" onClick={() => { setByHand(!byHand); setRes(null); }}>
        {byHand ? "Use ticker, strike and expiry instead" : "No ticker? Enter % out of the money and days instead"}</button>
      {res && "err" in res && <p className="mt-3 text-sm text-bad" role="alert">{res.err}</p>}
      {res && !("err" in res) && <div className="relative mt-4 bg-panel2 p-4" data-testid="check-result">
        <button type="button" onClick={() => setRes(null)} aria-label="Clear the result"
          className="absolute right-3 top-3 rounded-full px-2.5 py-1 text-xs text-muted hover:bg-panel hover:text-text">Clear ×</button>
        {res.filter && <div className="mb-4 pr-20">
          <p className="wide text-[22px] leading-tight">{res.filter.signal
            ? <><span className="mark">Signal</span>: {TIER[res.filter.tier ?? ""] ?? "it passes every check"}.</> : "Not a signal."}</p>
          {!res.filter.signal && <p className="mt-1 max-w-[72ch] text-sm">{res.filter.reason}</p>}
          <p className="mt-1 text-xs text-muted">Our filter&apos;s rules, checked on what you typed; assumes it was one option opening a new position.</p>
        </div>}
        {res.filter?.record && <div className="mb-2 border-t border-line pt-3">
          <p className="text-xs text-muted">{TIER_PLURAL[res.filter.record.tier]} in the sealed test (Oct 2025 to May 2026), buying the stock at the next open and selling five days later</p>
          <dl className="mt-2 grid grid-cols-3 gap-4 text-sm">
            <div><dt className="text-xs text-muted">Trades</dt><dd className="wide text-[22px]">{res.filter.record.trades.toLocaleString("en-US")}</dd></div>
            <div><dt className="text-xs text-muted">Beat the S&amp;P</dt><dd className="wide text-[22px]">{plainPct(res.filter.record.beat)}</dd></div>
            <div><dt className="text-xs text-muted">Average vs the S&amp;P</dt><dd className="wide text-[22px]">{pct(res.filter.record.avg, 2)}</dd><dd className="text-xs text-muted">a trade, after costs</dd></div>
          </dl>
          <p className="mt-2 text-xs text-muted">Backtested 2023–2026. <Link className="underline underline-offset-4" href="/methodology">See how it was tested</Link></p>
        </div>}
        {inp && <p className="mt-4 text-xs text-muted">
          {inp.ticker} {inp.spot_source === "alert" ? "price on its latest UW alert" : "last close"} <b className="text-text">{px(inp.spot)}</b> ({shortDate(inp.spot_date)}): strike {out(inp.otm_pct)}, {inp.dte === 0 ? <b className="text-text">expires today</b> : <><b className="text-text">{days(inp.dte)}</b> to expiry</>}{inp.sector ? <>, sector {inp.sector}</> : ""}.{" "}
          {n > 0 ? <>{inp.ticker} has {n} bet{n === 1 ? "" : "s"} in today&apos;s list. <button type="button" className="underline underline-offset-4" onClick={() => showToday(inp.ticker)}>Show {n === 1 ? "it" : "them"}</button></>
            : <Link className="underline underline-offset-4" href={`/ticker/${inp.ticker}`}>Open {inp.ticker}</Link>}
        </p>}
        {res.filter ? <div className="mt-2"><MoreList><More title="How similar bets did before">
          <SimilarBets h={res} />
        </More></MoreList></div> : <div className={inp ? "mt-4 border-t border-line pt-3" : ""}>
          <p className="mb-3 pr-20 text-xs text-muted">How similar bets did before. Add the ticker, strike and expiry to also see whether our filter would take it.</p>
          <SimilarBets h={res} />
        </div>}
        <p className="mt-3 text-xs text-muted">Measured on the stock over five days against the S&amp;P 500, not on the option.</p>
      </div>}
    </div>
  );
}

/** How earlier bets like this one did: a one-word verdict, three numbers next to the all-bets baseline, the periods. */
function SimilarBets({ h }: { h: History }) {
  const [head, sub] = verdict(h);
  return (
    <div data-testid="history">
      <p className="wide text-[22px] leading-tight">{head}</p>
      <p className="mt-1 text-sm text-muted">{sub}</p>
      {h.matches > 0 && <dl className="mt-4 grid grid-cols-3 gap-4 border-t border-line pt-3 text-sm">
        <div><dt className="text-xs text-muted">Beat the S&amp;P</dt><dd className="wide text-[22px]">{plainPct(h.win_share)}</dd>
          <dd className="text-xs text-muted">all bets {plainPct(h.baseline.win_share)}</dd></div>
        <div><dt className="text-xs text-muted">Average vs the S&amp;P</dt><dd className="wide text-[22px]">{pct(h.avg)}</dd>
          <dd className="text-xs text-muted">all bets {pct(h.baseline.avg)}</dd></div>
        <div><dt className="text-xs text-muted">Earlier bets like it</dt><dd className="wide text-[22px]">{h.matches.toLocaleString("en-US")}</dd>
          <dd className="text-xs text-muted">over five days, point in time</dd></div>
      </dl>}
      {h.matches > 0 && <div className="mt-4"><MatchedAndPeriods h={h} /></div>}
    </div>
  );
}
