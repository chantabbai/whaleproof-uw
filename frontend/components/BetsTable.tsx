"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import Dir from "./Dir";
import { days, dte, etTime, money, pct, plainPct, px, shortDate } from "@/lib/format";

export type Chip = { matches: number; win_share: number | null; avg: number | null; thin: boolean;
  periods_agree: boolean | null; traits_dropped: string[] };
export type BetRow = { id: string; ticker: string; direction: number; opt_type: "call" | "put"; bet_kind: string;
  premium: number; strike: number; expiry: string; dte: number; otm_pct: number; sweep: boolean; sector: string | null;
  created_at: string; verdict: string; reason: string; history: Chip };
export type BetsData = { day: string; as_of: string | null; forming: boolean; bets: BetRow[]; history_size: number; label: string };
type PeriodStat = { period: string; matches: number; win_share: number | null; avg: number | null };
export type History = Chip & { median: number | null; traits: Record<string, string | number | boolean>;
  periods: PeriodStat[]; baseline: { matches: number; win_share: number | null; avg: number | null }; in_plain_words: string };

const PAGE = 50;
const VERDICT: Record<string, string> = {
  signal: "Signal", gate: "Not a clean buy", direction: "Bearish, not taken", liquidity: "Stock under $5",
  earnings: "Earnings before the sell date", conviction: "Not big enough", unknown: "–",
};
/** The reason minus its opening words when the verdict label already says them ("Not big enough: $6M…" → "$6M…"). */
const detail = (r: string) => r.replace(/^(Not big enough|Bearish)[:.]\s*/, "").replace(/^./, (c) => c.toUpperCase());
const SHOWS = { all: "Every bet", signal: "Our signals", clean: "Clean buys", notclean: "Everything else", putsale: "Put sales" } as const;
const SORTS = { premium: "Biggest premium", new: "Newest first", ticker: "Ticker A–Z" } as const;
const TRAIT_NAMES: Record<string, string> = { sector: "sector", sweep: "sweep", dte: "days to expiry", otm: "distance out of the money", premium: "size" };

/** "Our filter said: Not big enough. $4.4M at 1% in the money…": the verdict, then its reason once, as sentences. */
function said(b: BetRow) {
  const why = b.verdict !== "signal" && b.reason ? ` ${detail(b.reason)}` : "";
  return `Our filter said: ${VERDICT[b.verdict] ?? b.verdict}.${why}${why && !/[.!?]$/.test(why) ? "." : ""}`;
}

/** Direction comes from the side (ask = bought, bid = sold), so call + bullish = bought, put + bullish = sold. */
function kindOf(b: BetRow) {
  return `${(b.direction > 0) === (b.opt_type === "call") ? "bought" : "sold"} ${b.opt_type}s`;
}

/** History bucket labels in words: "≥1M" → "1M or more", "≤7d" → "up to 7d", ">15% OTM" → "over 15% OTM". */
const bucket = (v: string) => v.replace(/^≥\s*(.+)$/, "$1 or more").replace(/^≤\s*/, "up to ").replace(/^>\s*/, "over ").replace(/^<\s*/, "under ");

function traitWords(t: Record<string, string | number | boolean>) {
  const out: string[] = [];
  for (const [k, v] of Object.entries(t)) {
    if (k === "direction") out.push(Number(v) > 0 ? "bullish" : "bearish");
    else if (k === "opt_type") out.push(`${v}s`);
    else if (k === "sweep") out.push(v ? "sweep" : "not a sweep");
    else if (k === "premium") out.push(`${bucket(String(v)).replace(/(\d+(?:\.\d+)?[KM])/g, "$$$1")} in premium`);
    else if (k === "dte") out.push(`${bucket(String(v)).replace(/(\d)d\b/g, "$1 days")} to expiry`);
    else if (k === "otm") out.push(bucket(String(v)).replace(/\bITM\b/, "in the money").replace(/\bOTM\b/, "out of the money"));
    else out.push(String(v));
  }
  return out.join(", ");
}

/** Compact "history says" chip. Neutral colours: a lookup, not a recommendation. */
export function HistoryChip({ h }: { h: Chip }) {
  if (h.matches === 0) return <span className="text-xs text-muted">No earlier bets like this</span>;
  if (h.thin) return <span className="text-xs text-muted">Too few to tell ({h.matches})</span>;
  return (
    <span className="whitespace-nowrap text-xs">
      <span className="font-semibold">{plainPct(h.win_share)}</span> beat the S&amp;P, average {pct(h.avg)}
      <span className="block text-muted">{h.matches.toLocaleString("en-US")} bets, {h.periods_agree === true ? "same story in every period"
        : h.periods_agree === false ? "periods disagree" : "too few to compare periods"}</span>
    </span>
  );
}

export function HistoryDetail({ h, bet }: { h: History; bet?: BetRow }) {
  return (
    <div className="grid gap-3 text-sm">
      <p className="max-w-[68ch]">{h.in_plain_words}</p>
      {bet && bet.bet_kind !== "clean buy" && (
        <p className="max-w-[68ch] text-xs text-warn" role="note">
          This alert isn&apos;t a clean buy (the reason is above), so these numbers assume you traded the stock the way
          the alert points.
        </p>
      )}
      <MatchedAndPeriods h={h} />
    </div>
  );
}

/** "Matched on …" and the per-period table: the detail behind a history answer. */
export function MatchedAndPeriods({ h }: { h: History }) {
  return (
    <div className="grid gap-3">
      <p className="text-xs text-muted">
        Matched on {traitWords(h.traits)}.
        {h.traits_dropped.length > 0 && <> Not matched on {h.traits_dropped.map((t) => TRAIT_NAMES[t] ?? t).join(", ")}, because too few bets were left.</>}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[480px] text-sm">
          <thead className="border-b border-text text-left text-xs text-muted"><tr>
            <th className="py-1 pr-3 font-normal">Period</th><th className="pr-3 font-normal">Bets</th>
            <th className="pr-3 font-normal">Beat the S&amp;P</th><th className="font-normal">Average vs S&amp;P</th></tr></thead>
          <tbody>
            {h.periods.map((p) => (
              <tr key={p.period} className="border-b border-line">
                <td className="py-1 pr-3">{p.period}</td><td className="pr-3">{p.matches.toLocaleString("en-US")}</td>
                <td className="pr-3">{plainPct(p.win_share)}</td><td>{pct(p.avg)}</td>
              </tr>
            ))}
            <tr className="border-t border-text text-muted">
              <td className="py-1 pr-3">Every bet (baseline)</td><td className="pr-3">{h.baseline.matches.toLocaleString("en-US")}</td>
              <td className="pr-3">{plainPct(h.baseline.win_share)}</td><td>{pct(h.baseline.avg)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Detail({ b }: { b: BetRow }) {
  const [h, setH] = useState<History | null | "err">(null);
  useEffect(() => {
    fetch(`/api/desk/alerts/${encodeURIComponent(b.id)}`, { cache: "no-store" }).then((x) => (x.ok ? x.json() : null))
      .then((d) => setH(d ? d.history : "err")).catch(() => setH("err"));
  }, [b.id]);
  return (
    <div className="grid gap-2">
      <p className="text-xs text-muted">
        {px(b.strike)} {b.opt_type}, expires {shortDate(b.expiry)}, {b.sector ?? "no sector on file"}. {said(b)}
        {" "}<Link className="underline" href={`/ticker/${b.ticker}`}>Open {b.ticker}</Link>
      </p>
      {h === null ? <p className="text-sm text-muted">Looking up history…</p> : h === "err" ? <p className="text-sm text-muted">Couldn&apos;t load the history for this one.</p>
        : <HistoryDetail h={h} bet={b} />}
    </div>
  );
}

export default function BetsTable({ data }: { data: BetsData }) {
  const [show, setShow] = useState<keyof typeof SHOWS>("all");
  const [dir, setDir] = useState("both");
  const [minPrem, setMinPrem] = useState(0);
  const [sort, setSort] = useState<keyof typeof SORTS>("premium");
  const [q, setQ] = useState("");
  const [shown, setShown] = useState(PAGE);
  const [openId, setOpenId] = useState<string | null>(null);
  useEffect(() => {                                    // "Show them" from the check-a-bet form above
    const on = (e: Event) => { setQ((e as CustomEvent<string>).detail); setShow("all"); setDir("both"); setMinPrem(0); setShown(PAGE); };
    window.addEventListener("bets:ticker", on);
    return () => window.removeEventListener("bets:ticker", on);
  }, []);

  const rows = useMemo(() => {
    const t = q.trim().toUpperCase();
    const out = data.bets.filter((b) =>
      (show === "all" || (show === "signal" && b.verdict === "signal") || (show === "clean" && b.bet_kind === "clean buy")
        || (show === "notclean" && b.bet_kind === "not a clean buy") || (show === "putsale" && b.bet_kind === "put sale"))
      && (dir === "both" || (dir === "bull" ? b.direction > 0 : b.direction < 0))
      && b.premium >= minPrem && (!t || b.ticker.startsWith(t)));
    return out.sort((a, b) => sort === "premium" ? b.premium - a.premium
      : sort === "new" ? b.created_at.localeCompare(a.created_at) : a.ticker.localeCompare(b.ticker));
  }, [data.bets, show, dir, minPrem, sort, q]);

  const sel = "field px-2";
  const reset = () => setShown(PAGE);
  const th = "py-2 pr-3 font-normal";
  return (
    <>
      <div className="mt-5 flex flex-wrap gap-2" role="group" aria-label="Filters">
        <select aria-label="Show" className={sel} value={show} onChange={(e) => { setShow(e.target.value as keyof typeof SHOWS); reset(); }}>
          {Object.entries(SHOWS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select aria-label="Direction" className={sel} value={dir} onChange={(e) => { setDir(e.target.value); reset(); }}>
          <option value="both">Bullish and bearish</option><option value="bull">Bullish</option><option value="bear">Bearish</option>
        </select>
        <select aria-label="Minimum premium" className={sel} value={minPrem} onChange={(e) => { setMinPrem(Number(e.target.value)); reset(); }}>
          <option value={0}>Any premium</option><option value={500000}>$500K+</option><option value={1000000}>$1M+</option>
        </select>
        <select aria-label="Sort" className={sel} value={sort} onChange={(e) => setSort(e.target.value as keyof typeof SORTS)}>
          {Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <input aria-label="Filter bets by ticker" placeholder="Ticker" value={q} onChange={(e) => { setQ(e.target.value); reset(); }} className={`${sel} w-28 uppercase`} />
      </div>
      <p className="mt-3 text-sm text-muted" role="status">{rows.length.toLocaleString("en-US")} of {data.bets.length.toLocaleString("en-US")} bets. Click a row for the full history.</p>
      {rows.length === 0 ? <p className="mt-2 text-sm text-muted">No bets for these filters.</p> : (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="sticky top-0 z-10 bg-panel text-left text-xs text-muted shadow-[0_1px_0_var(--text)]"><tr>
              <th className={th}>Bet</th><th className={th}>Size</th><th className={th}>Our filter</th>
              <th className={th}>History says <span className="text-[11px]">(stock vs S&amp;P, five days)</span></th><th className="w-6" aria-hidden /></tr></thead>
            <tbody>{rows.slice(0, shown).map((b) => {
              const on = openId === b.id;
              return [
                <tr key={b.id} onClick={() => setOpenId(on ? null : b.id)} aria-expanded={on}
                  className={`cursor-pointer border-b border-line align-top hover:bg-panel2 ${on ? "bg-panel2" : ""}`}>
                  <td className="py-2 pr-3">
                    <button type="button" className="font-semibold" aria-label={`${b.ticker} history`}
                      onClick={(e) => { e.stopPropagation(); setOpenId(on ? null : b.id); }}>{b.ticker}</button>{" "}
                    <Dir d={b.direction} compact />
                    <span className="block text-xs text-muted">{kindOf(b)}, {etTime(b.created_at)}</span>
                  </td>
                  <td className="py-2 pr-3 whitespace-nowrap">{money(b.premium)}
                    <span className="block text-xs text-muted">{dte(b.dte)}, {b.otm_pct < 0 ? "in the money" : Math.round(b.otm_pct * 100) === 0 ? "at the money" : `${(b.otm_pct * 100).toFixed(0)}% out`}{b.sweep ? ", swept" : ""}</span></td>
                  <td className="py-2 pr-3">
                    <span className={b.verdict === "signal" ? "mark font-semibold" : "text-muted"}>{VERDICT[b.verdict] ?? b.verdict}</span>
                    {b.verdict !== "signal" && b.reason && <span className="block max-w-[220px] truncate text-xs text-muted" title={detail(b.reason)}>{detail(b.reason)}</span>}
                  </td>
                  <td className="py-2 pr-3"><HistoryChip h={b.history} /></td>
                  <td className="py-2 pr-3 text-muted" aria-hidden>{on ? "▾" : "▸"}</td>
                </tr>,
                on && <tr key={`${b.id}-d`} className="bg-panel2"><td colSpan={5} className="px-3 pb-4 pt-1"><div className="sticky left-3 max-w-[calc(100vw-4rem)] md:max-w-none"><Detail b={b} /></div></td></tr>,
              ];
            })}</tbody>
          </table>
        </div>
      )}
      {rows.length > shown && (
        <button type="button" onClick={() => setShown(shown + PAGE)} className="mt-3 field">
          Show {Math.min(PAGE, rows.length - shown)} more
        </button>
      )}
    </>
  );
}
