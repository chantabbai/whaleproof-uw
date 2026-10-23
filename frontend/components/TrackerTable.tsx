"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import ByPeriod, { byPeriodNote } from "./ByPeriod";
import Dir from "./Dir";
import PathChart from "./PathChart";
import { Distribution, MonthStrip } from "./TrackerCharts";
import { contractLabel, etTime, money, pct, plainPct, px, TIER, isFlat, arrowPct, moveTone, moveDigits, md, days, plural } from "@/lib/format";
import { H2, More, MoreList, Tile, Tiles } from "./v2/ui";
import { earlierHold, ordinal } from "@/lib/repeat";

/** "2026-09-30" → "Sep 30" (year added when not this year's data). */
type Stock = { status: "waiting" | "open" | "closed"; entry_date: string | null; entry: number | null; exit_date: string | null;
  exit: number | null; last: number | null; days_held: number; ret: number | null; move?: number | null; vs_spy: number | null; spy_ret: number | null;
  peak: number | null; peak_date: string | null; drawdown: number | null; drawdown_date: string | null; priced_through: string | null;
  path?: [string, number][]; live_at?: string | null;
  now?: { entry: number | null; price: number | null; source: "live" | "close" | null; at: string | null; move: number | null; net: number | null } };
type Option = { contract: string; buy: number; spread_pct: number | null; sell: number; sell_date: string; ret: number;
  peak: number | null; peak_date: string | null; drawdown: number | null; drawdown_date: string | null; priced_through: string;
  path?: [string, number][]; live_at?: string | null; now?: { bid: number; at: string; ret: number } | null } | null;
export type TrackerRow = { id: string; source: "history" | "live"; hold_day?: number; session_date: string; ticker: string; direction: number;
  tier: "whale" | "far_otm"; label: string; premium: number; otm_pct: number; sector: string | null; contract: string | null;
  spot_at_alert: number | null; entry_on: string; exit_by: string; period: string; gap_at_entry: number | null; stock: Stock; option: Option };
export type TrackerData = { as_of: string; baseline?: Record<string, { mean: number | null; n: number | null; unpriced?: number | null; open?: number | null }>; rows: TrackerRow[]; priced_through: string | null; periods: string[]; note: string;
  history_loaded?: boolean;
  last_close_update: { at: string; day: string; bars_missing: string[]; options_missing: string[] } | null };

const HOLD = 5;
const PAGE = 50;
const TIERS: Record<string, string> = { whale: "Whale-size", far_otm: "Long shot" };
const SORTS = { new: "Newest first", best: "Best stock result", worst: "Worst stock result", opt: "Best option result",
  edge: "Option beat the stock most", peak: "Biggest stock peak", dd: "Deepest stock drawdown", odd: "Deepest option drawdown" } as const;

const mean = (v: number[]) => (v.length ? v.reduce((a, b) => a + b, 0) / v.length : null);
const median = (v: number[]) => {
  if (!v.length) return null;
  const s = [...v].sort((a, b) => a - b), m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
const words = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;

function Move({ v, bold = false }: { v: number | null | undefined; bold?: boolean }) {
  if (v == null) return <span className="text-muted">–</span>;
  return <span className={`${moveTone(v)} ${bold ? "font-semibold" : ""}`}>{arrowPct(v)}</span>;
}

/** An open hold as it stands now: the API's live mark (same price Sightings shows) laid over the last close.
 *  Display copy only: summaries and finished results always read the record's closing prices. */
function liveRow(r: TrackerRow): TrackerRow {
  const n = r.stock.now, o = r.option;
  const entering = r.stock.status === "waiting";        // bought at today's open; the record settles it at the close
  const stock = n && n.move != null && (n.source === "live" || entering)
    ? { ...r.stock, move: n.move, ret: n.net, last: n.price, live_at: n.at,
        ...(entering ? { entry: n.entry, entry_date: r.entry_on, priced_through: r.entry_on } : {}) } : r.stock;
  const option = o && o.now ? { ...o, sell: o.now.bid, ret: o.now.ret, live_at: o.now.at } : o;
  return { ...r, stock, option };
}
const nowLabel = (at: string | null | undefined, close: string | null | undefined, what = "close") =>
  at ? `live ${etTime(at)}` : `${md(close)} ${what}`;

/** Finished trades open on each weekday from the first entry to the last exit: the typical day (median) and the
 *  busiest. $1,000 each, so this is the capital it takes; the average alone would hide the busy weeks. */
function openAtOnce(rows: TrackerRow[]): { typical: number; peak: number } {
  const day = 864e5, cnt = new Map<number, number>();
  let lo = Infinity, hi = -Infinity;
  for (const r of rows) if (r.stock.entry_date && r.stock.exit_date) {
    const a = Date.parse(r.stock.entry_date), b = Date.parse(r.stock.exit_date);
    lo = Math.min(lo, a); hi = Math.max(hi, b);
    for (let t = a; t <= b; t += day) cnt.set(t, (cnt.get(t) ?? 0) + 1);
  }
  const days: number[] = [];
  for (let t = lo; t <= hi; t += day) { const w = new Date(t).getUTCDay(); if (w > 0 && w < 6) days.push(cnt.get(t) ?? 0); }
  if (!days.length) return { typical: 0, peak: 0 };
  days.sort((x, y) => x - y);
  return { typical: days[Math.floor(days.length / 2)], peak: days[days.length - 1] };
}

function summarize(rows: TrackerRow[]) {
  const closed = rows.filter((r) => r.stock.status === "closed" && r.stock.ret != null);
  const st = closed.map((r) => r.stock.ret as number);
  const vs = closed.filter((r) => r.stock.vs_spy != null).map((r) => r.stock.vs_spy as number);
  const spy = closed.filter((r) => r.stock.spy_ret != null).map((r) => r.stock.spy_ret as number);
  const opt = closed.filter((r) => r.option).map((r) => (r.option as NonNullable<Option>).ret);
  return {
    closed: closed.length, open: rows.filter((r) => r.stock.status !== "closed").length,
    stockWin: st.length ? st.filter((x) => x > 0).length / st.length : null, stockAvg: mean(st), stockMed: median(st),
    won: st.filter((x) => x > 0).length, spyAvg: mean(spy),
    vsAvg: mean(vs), beat: vs.length ? vs.filter((x) => x > 0).length / vs.length : null,
    optN: opt.length, optWin: opt.length ? opt.filter((x) => x > 0).length / opt.length : null, optAvg: mean(opt), optMed: median(opt),
    stock1k: st.reduce((a, b) => a + b * 1000, 0), opt1k: opt.reduce((a, b) => a + b * 1000, 0),
    optBeat: opt.length ? closed.filter((r) => r.option && r.option.ret > (r.stock.ret as number)).length / opt.length : null,
    open1k: openAtOnce(closed),
  };
}

export default function TrackerTable({ data }: { data: TrackerData }) {
  const [period, setPeriod] = useState("all");
  const [tier, setTier] = useState("all");
  const [q, setQ] = useState("");
  const [sector, setSector] = useState("all");
  const [sort, setSort] = useState<keyof typeof SORTS>("new");
  const [shown, setShown] = useState(PAGE);

  const rows = useMemo(() => {
    const t = q.trim().toUpperCase();
    const f = data.rows.filter((r) => (period === "all" || r.period === period) && (tier === "all" || r.tier === tier)
      && (!t || r.ticker.startsWith(t)) && (sector === "all" || (r.sector ?? "Unknown") === sector));
    const hi: Partial<Record<keyof typeof SORTS, (r: TrackerRow) => number | null | undefined>> = {
      best: (r) => r.stock.ret, opt: (r) => r.option?.ret, peak: (r) => r.stock.peak,
      edge: (r) => (r.option && r.stock.ret != null ? r.option.ret - r.stock.ret : null) };
    const lo: Partial<Record<keyof typeof SORTS, (r: TrackerRow) => number | null | undefined>> = {
      worst: (r) => r.stock.ret, dd: (r) => r.stock.drawdown, odd: (r) => r.option?.drawdown };
    if (hi[sort]) f.sort((a, b) => (hi[sort]!(b) ?? -Infinity) - (hi[sort]!(a) ?? -Infinity));
    if (lo[sort]) f.sort((a, b) => (lo[sort]!(a) ?? Infinity) - (lo[sort]!(b) ?? Infinity));
    return f;
  }, [data.rows, period, tier, q, sort, sector]);
  const sectors = useMemo(() => Array.from(new Set(data.rows.map((r) => r.sector ?? "Unknown"))).sort(), [data.rows]);
  const months = useMemo(() => {
    const by = new Map<string, number[]>();
    for (const r of rows) if (r.stock.status === "closed" && r.stock.ret != null) {
      const m = r.session_date.slice(0, 7);
      by.set(m, [...(by.get(m) ?? []), r.stock.ret]);
    }
    return Array.from(by.entries()).sort().map(([m, v]) => ({ m, avg: mean(v) as number, n: v.length }));
  }, [rows]);
  const bought = (r: TrackerRow) => r.stock.status === "open" || (r.stock.status === "waiting" && r.stock.now?.move != null);
  const open = useMemo(() => rows.filter(bought).map(liveRow)
    .sort((a, b) => b.session_date.localeCompare(a.session_date)), [rows]);
  const waiting = useMemo(() => rows.filter((r) => r.stock.status === "waiting" && !bought(r)), [rows]);
  const done = useMemo(() => rows.filter((r) => r.stock.status === "closed"), [rows]);
  const s = useMemo(() => summarize(rows), [rows]);
  const byPeriod = useMemo(() => data.periods.map((p) => ({ p, ...summarize(data.rows.filter((r) => r.period === p)) }))
    .filter((x) => x.closed + x.open > 0), [data.rows, data.periods]);

  const sel = "field px-2";
  const usd = (v: number) => `${v >= 0 ? "+" : "−"}${money(Math.abs(v))}`;

  return (
    <>
      <div className="mt-8 flex flex-wrap items-center gap-2 rounded-md bg-panel2 p-3" role="group" aria-label="Filters">
        <span className="mr-1 text-[13px] text-muted">Show</span>
        <select aria-label="Period" className={`${sel} max-w-full`} value={period} onChange={(e) => { setPeriod(e.target.value); setShown(PAGE); }}>
          <option value="all">All periods</option>
          {data.periods.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select aria-label="Signal type" className={sel} value={tier} onChange={(e) => { setTier(e.target.value); setShown(PAGE); }}>
          <option value="all">Both kinds</option><option value="whale">Whale-size bets</option><option value="far_otm">Long shots</option>
        </select>
        <select aria-label="Sector" className={sel} value={sector} onChange={(e) => { setSector(e.target.value); setShown(PAGE); }}>
          <option value="all">All sectors</option>
          {sectors.map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
        <input aria-label="Ticker" placeholder="Ticker" value={q} onChange={(e) => { setQ(e.target.value); setShown(PAGE); }}
          className={`${sel} w-28 uppercase`} />
        <a href="/api/desk/tracker.csv" download="signal-tracker.csv" className="ml-auto text-sm underline underline-offset-4">Download CSV</a>
      </div>

      {s.closed === 0 && open.length > 0 ? <HoldTiles open={open} waiting={waiting.length} entry={waiting[0]?.entry_on} /> : <div className="mt-6" data-testid="tracker-tiles"><Tiles>
        <Tile accent="sea" k="Finished signals" v={s.closed.toLocaleString("en-US")} sub={s.open ? `and ${s.open} still open` : undefined} />
        <Tile accent="amber" k="Average stock trade" v={pct(s.stockAvg, 2)} tone={(s.stockAvg ?? 0) >= 0 ? "bull" : "bear"}
          sub={s.vsAvg != null ? `${pct(s.vsAvg, 2)} vs the S&P 500, beat it ${plainPct(s.beat)} of the time` : undefined} />
        <Tile accent="amber" k="Stock went up" v={plainPct(s.stockWin)} sub={s.stockMed != null ? `middle trade ${pct(s.stockMed)}` : undefined} />
        <Tile accent="brass" k="$1,000 on every trade" v={s.closed ? usd(s.stock1k) : "–"} tone={s.stock1k >= 0 ? "bull" : "bear"}
          sub={s.closed ? <>Flat, not reinvested{s.open1k.peak > 1 ? (s.open1k.typical === s.open1k.peak ? `: ${s.open1k.peak} open at once` : `: usually about ${s.open1k.typical} open at once, up to ${s.open1k.peak} on the busiest days`) : ""}.{s.optN ? <> The whale&apos;s option instead: {usd(s.opt1k)}</> : null}</> : undefined} />
      </Tiles></div>}
      {s.closed > 0 && s.closed < 30 && <p className="mt-3 max-w-[72ch] text-[13px] text-muted">Fewer than 30 finished trades here, so treat these numbers as noise.</p>}

      <section className="mt-14">
        <H2 sub={open.length > 0 ? `${words(open.length, "signal")} in their five-day hold, the same list as Sightings: price move since the entry open, live while the market is open, the last close after that. Click one for its day-by-day path.` : undefined} wave>Riding with the whales</H2>
        {waiting.length > 0 && (
          <p className="mt-4 rounded-md bg-brass-soft px-4 py-3 text-sm">
            <span className="font-semibold">Buying at the {md(waiting[0].entry_on)} open:</span>{" "}
            {waiting.map((r, i) => <span key={r.id}>{i ? ", " : ""}<Link href={`/ticker/${r.ticker}`} className="font-semibold underline-offset-4 hover:underline">{r.ticker}</Link>
              <span className="text-xs text-muted"> ({TIERS[r.tier].toLowerCase()})</span></span>)}
            <span className="text-muted">. Sell at the {md(waiting[0].exit_by)} close.</span>
          </p>
        )}
        {open.length > 0 && <OpenGrid rows={open} />}
        {open.length > 0 && <div className="mt-4"><MoreList><More title="The same, as a table with the whale's option">
          <Rows rows={open} live />
        </More></MoreList></div>}
        {open.length + waiting.length === 0 && <p className="mt-3 text-sm text-muted">Nothing open for these filters.</p>}
      </section>

      {s.closed > 0 && (
        <div className="mt-14 grid gap-12">
          <Distribution stock={rows.filter((r) => r.stock.status === "closed" && r.stock.ret != null).map((r) => r.stock.ret as number)}
            option={rows.filter((r) => r.stock.status === "closed" && r.option).map((r) => (r.option as NonNullable<Option>).ret)} />
          <MonthStrip months={months} />
        </div>
      )}

      <div className="mt-14"><MoreList>
        <More title={`Every finished signal (${done.length.toLocaleString("en-US")})`}
          note={s.closed > 0 ? <>Stock {pct(s.stockAvg)} on average, option {pct(s.optAvg)}; the option came out ahead on {plainPct(s.optBeat)} of trades with option prices. Click a row for its path.</> : undefined}>
          <label className="text-[13px] text-muted">Sort <select aria-label="Sort" className={`${sel} ml-1`} value={sort} onChange={(e) => setSort(e.target.value as keyof typeof SORTS)}>
            {Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></label>
          {done.length === 0 ? <p className="mt-2 text-sm text-muted">No finished signals for these filters.</p> : <Rows rows={done.slice(0, shown)} scroll />}
          {shown < done.length && (
            <button type="button" onClick={() => setShown(shown + PAGE)} className="mt-3 field">
              Show {Math.min(PAGE, done.length - shown)} more (of {done.length.toLocaleString("en-US")})
            </button>
          )}
        </More>
        {(() => {
          const withBase = byPeriod.map((x) => { const b = data.baseline?.[x.p]; return { ...x, base: b?.n ? b.mean : null, alerts: b?.n ?? null }; });
          const live = withBase.find((x) => x.p.startsWith("Live")) ?? null;
          const tests = withBase.filter((x) => x !== live).reverse();                    // oldest first, live last
          return <More title="By period: four test periods and live trading" note={byPeriodNote(tests)}><ByPeriod rows={tests} live={live} /></More>;
        })()}
      </MoreList></div>
    </>
  );
}

function OpenedCard({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="mt-4 rounded-md border border-text p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-[13px] text-muted">{title}</span>
        <button type="button" onClick={onClose} className="rounded-md border border-line px-3 py-1 text-[13px] hover:border-text">Close ✕</button>
      </div>
      {children}
    </div>
  );
}

/** Open signals at a glance: move since the tested buy, day of five; click for the day-by-day path. */
function OpenGrid({ rows }: { rows: TrackerRow[] }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const sel = rows.find((r) => r.id === openId);
  return (
    <div className="mt-5">
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {rows.map((r) => {
          const m = r.stock.move ?? null, dg = moveDigits(m), up = (m ?? 0) >= 0, flat = m != null && isFlat(m, dg), n = r.hold_day ?? r.stock.days_held, rep = earlierHold(r, rows);
          return (
            <li key={r.id} className="flex">
              <button type="button" onClick={() => setOpenId(openId === r.id ? null : r.id)} aria-expanded={openId === r.id}
                aria-label={`${r.ticker} ${m == null ? "" : `${flat ? "flat" : up ? "up" : "down"} ${pct(m, dg)}, `}day ${n} of ${HOLD}, ${rep ? `${ordinal(rep.nth)} signal, first one sells ${md(rep.first.exit_by)}, ` : ""}details`}
                className={`flex w-full flex-col justify-start rounded-md p-3 text-left outline-offset-2 transition-colors duration-150 hover:outline hover:outline-1 ${openId === r.id ? "outline outline-2" : ""} ${m == null || flat ? "bg-panel2" : up ? "bg-bull-soft" : "bg-bear-soft"}`}>
                <span className="flex flex-wrap items-baseline justify-between gap-x-1">
                  <span className="wide text-[17px]">{r.ticker}</span>
                  <span className={`ml-auto whitespace-nowrap text-[15px] font-semibold ${moveTone(m, dg)}`}>{m == null ? "–" : arrowPct(m, dg)}</span>
                </span>
                <span className="mt-2 flex gap-1" aria-hidden>
                  {Array.from({ length: HOLD }, (_, i) => <span key={i} className={`h-1 flex-1 rounded-full ${i < n ? "bg-text" : "bg-line"}`} />)}
                </span>
                <span className="mt-1.5 block text-xs text-muted">day {n} of {HOLD}, sells {md(r.exit_by)}</span>
                {rep && <span className="mt-1 block text-xs leading-snug text-amber" data-testid="repeat-label"><span className="block">{ordinal(rep.nth)} signal,</span> <span className="block">first one sells {md(rep.first.exit_by)}</span></span>}
              </button>
            </li>
          );
        })}
      </ul>
      {sel && <OpenedCard title={`${sel.ticker}, day by day`} onClose={() => setOpenId(null)}>{(() => { const rep = earlierHold(sel, rows); return rep && <p className="mb-2 text-sm text-amber">{ordinal(rep.nth)} signal on {sel.ticker}: the first one is still open, sells {md(rep.first.exit_by)}.</p>; })()}<Detail r={sel} /></OpenedCard>}
    </div>
  );
}

const Muted = ({ children }: { children: React.ReactNode }) => <span className="text-xs text-muted">{children}</span>;

/** Nothing finished under these filters yet (e.g. Live in its first week): the tiles describe the open holds so far
 *  instead of four blanks. Same live marks as the hold list below; nothing here counts toward the record. */
function HoldTiles({ open, waiting, entry }: { open: TrackerRow[]; waiting: number; entry?: string }) {
  const mv = open.map((r) => r.stock.move).filter((x): x is number => x != null);
  const net = open.map((r) => r.stock.ret).filter((x): x is number => x != null);
  const opt = open.map((r) => r.option?.ret).filter((x): x is number => x != null);
  const avg = mean(mv), up = mv.length ? mv.filter((x) => x > 0).length / mv.length : null;
  const usd = (v: number) => `${v >= 0 ? "+" : "−"}${money(Math.abs(v))}`;
  const k1 = net.reduce((a, b) => a + b * 1000, 0), o1 = opt.reduce((a, b) => a + b * 1000, 0);
  return <div className="mt-6" data-testid="tracker-tiles">
    <Tiles>
      <Tile accent="sea" k="Finished signals" v="0" sub={`${open.length} in their hold${waiting ? `, ${waiting} more with entry at the ${md(entry)} open` : ""}`} />
      <Tile accent="amber" k="Average so far" v={pct(avg, 2)} tone={(avg ?? 0) >= 0 ? "bull" : "bear"} sub="price move since each entry open" />
      <Tile accent="amber" k="Up so far" v={plainPct(up)} sub={mv.length ? `${mv.filter((x) => x > 0).length} of ${plural(mv.length, "hold")}` : undefined} />
      <Tile accent="brass" k="$1,000 on each so far" v={net.length ? usd(k1) : "–"} tone={k1 >= 0 ? "bull" : "bear"}
        sub={opt.length ? `the whale's option instead: ${usd(o1)}` : "after 0.10% costs"} />
    </Tiles>
    <p className="mt-3 max-w-[72ch] text-[13px] text-muted">Nothing here has finished its five-day hold yet, so these are open positions, not results. They can still swing either way.</p>
  </div>;
}

/** Two small lines: stock over option, so a column compares them. */
function Two({ stock, option }: { stock: React.ReactNode; option: React.ReactNode }) {
  return <div className="whitespace-nowrap text-xs leading-5"><div>{stock}</div><div>{option}</div></div>;
}

function Rows({ rows, live = false, scroll = false }: { rows: TrackerRow[]; live?: boolean; scroll?: boolean }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const th = "py-2 pr-3 font-normal";
  return (
    <div className={`mt-2 overflow-x-auto ${scroll ? "max-h-[75vh] overflow-y-auto" : ""}`}>
      <table className="w-full min-w-[820px] text-sm">
        <thead className="sticky top-0 z-10 bg-panel text-left text-xs text-muted shadow-[0_1px_0_var(--text)]"><tr>
          <th className={th}>Signal</th><th className={th}>{live ? "Progress" : "Held"}</th>
          <th className={th} title="Open: price move since the buy. Finished: net result after 0.10% trading costs.">Stock</th><th className={th}>Whale&apos;s option</th><th className={th} title="Option result minus stock result, in percentage points">Option vs stock</th>
          <th className={th} title="Stock: best intraday high. Option: best closing bid.">Peak <span className="text-[11px]">stock / option</span></th>
          <th className={th} title="Stock: worst intraday low. Option: worst closing bid.">Drawdown <span className="text-[11px]">stock / option</span></th><th className="w-6" aria-hidden /></tr></thead>
        <tbody>{rows.map((r) => {
          const on = openId === r.id;
          return [
            <tr key={r.id} onClick={() => setOpenId(on ? null : r.id)} aria-expanded={on}
              className={`cursor-pointer border-b border-line align-top hover:bg-panel2 ${on ? "bg-panel2" : ""}`}>
              <td className="py-2 pr-3">
                <button type="button" className="font-semibold" aria-label={`${r.ticker} details`}
                  onClick={(e) => { e.stopPropagation(); setOpenId(on ? null : r.id); }}>{r.ticker}</button>{" "}
                <Dir d={r.direction} compact />
                <span className="block text-xs text-muted">{md(r.session_date)}, {TIERS[r.tier].toLowerCase()}</span>
              </td>
              <td className="py-2 pr-3"><Progress r={r} /></td>
              <td className="py-2 pr-3">{r.stock.ret == null ? <Muted>entry at the {md(r.entry_on)} open</Muted>
                : r.stock.status === "closed" ? <><Move v={r.stock.ret} bold />
                  <span className="block text-xs text-muted">net{r.stock.vs_spy != null && <>, {pct(r.stock.vs_spy)} vs the S&amp;P</>}</span>
                  <span className="block text-xs text-muted">{px(r.stock.entry)} to {px(r.stock.exit)}</span></>
                : <><Move v={r.stock.move} bold /><span className="block text-xs text-muted">so far, {pct(r.stock.ret)} net</span>
                  <span className="block text-xs text-muted">{px(r.stock.entry)} to {px(r.stock.last)}, {nowLabel(r.stock.live_at, r.stock.priced_through)}</span></>}</td>
              <td className="py-2 pr-3">{r.option ? <><Move v={r.option.ret} bold />
                <span className="block text-xs text-muted">{px(r.option.buy)} to {px(r.option.sell)}{r.stock.status === "closed" ? "" : `, ${nowLabel(r.option.live_at, r.option.sell_date, "bid")}`}</span>
                <Wide o={r.option} /></> : <Muted>{r.stock.entry_date ? optMissing(r) : "–"}</Muted>}</td>
              <td className="py-2 pr-3">{r.option && r.stock.ret != null ? <Edge v={r.option.ret - r.stock.ret} /> : <Muted>–</Muted>}</td>
              <td className="py-2 pr-3">{r.stock.peak_date ? <Two stock={<Pk v={r.stock.peak} />} option={r.option ? <Pk v={r.option.peak} /> : <Muted>–</Muted>} /> : <Muted>–</Muted>}</td>
              <td className="py-2 pr-3">{r.stock.peak_date ? <Two stock={<Pk v={r.stock.drawdown} />} option={r.option ? <Pk v={r.option.drawdown} /> : <Muted>–</Muted>} /> : <Muted>–</Muted>}</td>
              <td className="py-2 pr-3 text-muted" aria-hidden>{on ? "▾" : "▸"}</td>
            </tr>,
            on && <tr key={`${r.id}-d`} className="bg-panel2"><td colSpan={8} className="px-3 pb-4 pt-1"><div className="sticky left-3 max-w-[calc(100vw-4rem)] md:max-w-none"><Detail r={r} /></div></td></tr>,
          ];
        })}</tbody>
      </table>
    </div>
  );
}

// the option's paid price is the entry day's opening trade (+ half the spread): no trade that day → never guessed
const etToday = () => new Date().toLocaleString("sv-SE", { timeZone: "America/New_York" }).slice(0, 10);
const optMissing = (r: TrackerRow) => !r.contract ? "no contract"
  : r.stock.status !== "closed" && r.entry_on === etToday() ? "no trade in this contract yet today"
  : r.stock.status !== "closed" && r.entry_on > etToday() ? "–"
  : !r.stock.entry_date ? "–"
  : r.stock.status === "closed" ? "not measured"          // no entry-day trade or no exit-day price (How results are measured)
  : "not measured: no trade on the entry day";

const WIDE = 0.25;      // spread over 25% of the option's price: most of a small result is the spread, not the move
function Wide({ o }: { o: NonNullable<Option> }) {
  if (o.spread_pct == null || o.spread_pct <= WIDE) return null;
  return <span className="block text-xs text-warn" title="Ask minus bid, as a share of the mid price, on the entry day">
    wide spread ({Math.round(o.spread_pct * 100)}% of the price): much of this is the spread</span>;
}
const Pk = ({ v }: { v: number | null | undefined }) => v == null ? <Muted>none</Muted> : <Move v={v} />;

function Edge({ v }: { v: number }) {
  return <span className={`text-xs ${v >= 0 ? "text-bull" : "text-bear"}`}>{v >= 0 ? "option" : "stock"} ahead by {Math.round(Math.abs(v) * 100)} point{Math.round(Math.abs(v) * 100) === 1 ? "" : "s"}</span>;
}

function Progress({ r }: { r: TrackerRow }) {
  const st = r.stock, n = r.hold_day ?? st.days_held;
  if (st.status === "closed") return <span className="text-xs text-muted">{days(st.days_held)}<span className="block">{md(st.entry_date)} to {md(st.exit_date)}</span></span>;
  return (
    <div className="w-36 whitespace-nowrap text-xs">
      <div className="flex gap-0.5" aria-label={`day ${n} of ${HOLD}`}>
        {Array.from({ length: HOLD }, (_, i) => <span key={i} className={`h-1.5 flex-1 ${i < n ? "bg-text" : "bg-line"}`} />)}
      </div>
      <span className="mt-1 block text-muted">{st.status === "waiting" && n === 0 ? `buys ${md(r.entry_on)}` : `day ${n} of ${HOLD}`}, sells {md(r.exit_by)}</span>
    </div>
  );
}

type WhyLost = {
  how_common?: { signals: { losers: number; winners: number }; share: Record<string, { losers: number | null; winners: number | null }> } };

const share = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);

type Note = { kind: string; text: string };
type Review = { went_well: Note[]; better: Note[]; lagged: boolean; not_checked: string[]; label: string; how_common?: WhyLost["how_common"] };
type RuleOutcome = { key: string; text: string; taken: boolean | null; net?: number | null; exit_date?: string | null; base: number };

// results, not causes: how often they show up on winners vs losers is true by definition, so no rate line
const OUTCOMES = new Set(["beat_spx", "stock", "option_beat", "option_lagged"]);

/** "How common" line: the side the note points to comes first; near-equal shares say it explains little. */
function Rate({ r, good }: { r: { losers: number | null; winners: number | null }; good: boolean }) {
  if (r.losers == null || r.winners == null) return null;
  const parts = good ? [`${share(r.winners)} of winners`, `${share(r.losers)} of losers`] : [`${share(r.losers)} of losers`, `${share(r.winners)} of winners`];
  const d = (good ? r.winners - r.losers : r.losers - r.winners);
  const read = Math.abs(d) < 0.05 ? "about as common either way, so it explains little"
    : d < 0 ? `more common on ${good ? "losers" : "winners"}, so not much of a sign` : null;
  return <span className="block text-xs text-muted">Seen on {parts[0]} and {parts[1]}{read ? `: ${read}` : ""}.</span>;
}

function NoteList({ notes, hc, good }: { notes: Note[]; hc?: WhyLost["how_common"]; good: boolean }) {
  return <ul className="mt-1 space-y-1.5">{notes.map((n) => {
    const r = OUTCOMES.has(n.kind) ? undefined : hc?.share[n.kind];
    return <li key={n.kind}>{n.text}{r && <Rate r={r} good={good} />}</li>;
  })}</ul>;
}

/** Every finished signal: what went well, why it lagged (losers: causes only), and what could have gone better. */
const NOT_A_CAUSE = new Set(["gave_back", "option_lagged"]);   // things to do better, not reasons the stock lagged

function ReviewNotes({ w }: { w: Review }) {
  const why = w.lagged ? w.better.filter((n) => !NOT_A_CAUSE.has(n.kind)) : [];
  const better = w.lagged ? w.better.filter((n) => NOT_A_CAUSE.has(n.kind)) : w.better;
  return (
    <div className="space-y-3">
      {w.went_well.length > 0 && <section data-testid="went-well" className="border-l-2 border-bull py-1 pl-4 text-sm">
        <h3 className="font-semibold">What went well</h3><NoteList notes={w.went_well} hc={w.how_common} good /></section>}
      {why.length > 0 && <section data-testid="why-lost" className="border-l-2 border-bear py-1 pl-4 text-sm">
        <h3 className="font-semibold">Why it lagged the S&amp;P 500</h3><NoteList notes={why} hc={w.how_common} good={false} /></section>}
      {better.length > 0 && <section data-testid="could-be-better" className="border-l-2 border-warn py-1 pl-4 text-sm">
        <h3 className="font-semibold">What could have gone better</h3><NoteList notes={better} hc={w.how_common} good={false} /></section>}
      <p className="text-xs text-muted">
        {w.not_checked.length > 0 && <>Couldn&apos;t check {w.not_checked.join(", ")} (no saved data). </>}
        From saved prices and UW&apos;s market tide. They describe what happened; they aren&apos;t rules.
      </p>
    </div>
  );
}

/** What each locked lesson rule would have done to this one trade (fixed rules, so no hindsight per trade). */
function RuleOutcomes({ rules }: { rules: RuleOutcome[] }) {
  return (
    <section data-testid="rule-outcomes" className="text-sm">
      <h3 className="font-semibold">With each lesson rule instead</h3>
      <table className="mt-1 w-full text-xs"><tbody>{rules.map((x) => (
        <tr key={x.key} className="border-b border-line"><td className="py-1 pr-3">{x.text}</td>
          <td className="whitespace-nowrap py-1">{x.taken === null ? <Muted>no data</Muted> : x.taken === false ? <Muted>skipped (0%)</Muted>
            : <><Move v={x.net ?? null} /> <Muted>{x.exit_date ? `sold ${md(x.exit_date)}` : ""}</Muted></>}</td>
          <td className="whitespace-nowrap py-1 pl-3">{x.taken === null ? null : <Edge2 v={(x.net ?? 0) - x.base} />}</td></tr>))}</tbody></table>
      <p className="mt-1 text-xs text-muted">After costs. The signal rule made {pct(rules[0]?.base)} on this trade. The rules were locked before we ran them (Lessons from the record, below).</p>
    </section>
  );
}

function Edge2({ v }: { v: number }) {
  if (Math.abs(v) < 0.0005) return <Muted>same</Muted>;
  return <span className={v > 0 ? "text-bull" : "text-bear"}>{v > 0 ? "better" : "worse"} by {Math.abs(v * 100).toFixed(1)} pts</span>;
}

function Detail({ r }: { r: TrackerRow }) {
  const st = r.stock, o = r.option;
  const [path, setPath] = useState<{ stock: [string, number][]; option: [string, number][]; why_lost?: WhyLost | null;
    review?: Review | null; lessons?: RuleOutcome[] | null; oi?: [string, number, number | null][] } | null>(null);
  useEffect(() => {
    let live = true;
    fetch(`/api/desk/tracker/${encodeURIComponent(r.id)}/path`, { cache: "no-store" }).then((x) => (x.ok ? x.json() : null))
      .then((j) => live && setPath(j ?? { stock: [], option: [] })).catch(() => live && setPath({ stock: [], option: [] }));
    return () => { live = false; };
  }, [r.id]);
  const open = st.status !== "closed";
  // today's bar mid-session isn't a close: show the live result on it instead and label the row "live"
  const today = new Date().toLocaleString("sv-SE", { timeZone: "America/New_York" }).slice(0, 10);
  const raw = path?.stock ?? [];
  const liveToday = open && !!st.live_at && raw.length > 0 && raw[raw.length - 1][0] === today && st.ret != null;
  const sp: [string, number][] = liveToday ? [...raw.slice(0, -1), [today, st.ret as number]] : raw;
  const op = path?.option ?? [], oi = path?.oi ?? [];
  const dl = "grid grid-cols-[7rem_1fr] gap-x-3 gap-y-0.5 text-sm";
  const dates = Array.from(new Set([...sp.map((p) => p[0]), ...op.map((p) => p[0]), ...oi.map((p) => p[0])])).sort();
  const oiAt = (d: string) => oi.find((p) => p[0] === d);
  const at = (path: [string, number][], d: string) => path.find((p) => p[0] === d)?.[1];
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
      <div className="space-y-3">
        <dl className={dl}>
          <dt className="text-muted">Signal</dt><dd>{TIER[r.tier]}, {money(r.premium)}, {pct(r.otm_pct, 0).replace("+", "")} out of the money</dd>
          <dt className="text-muted">Period</dt><dd>{r.period}{r.sector ? `, ${r.sector}` : ""}</dd>
          <dt className="text-muted">Whale&apos;s option</dt><dd>{r.contract ? contractLabel(r.contract) : "none"}</dd>
          <dt className="text-muted">More</dt><dd><Link href={`/ticker/${r.ticker}`} className="underline">Open {r.ticker}</Link></dd>
        </dl>
        <table className="w-full text-sm">
          <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="font-normal" /><th className="font-normal">Bought</th><th className="font-normal">{open ? "Now" : "Sold"}</th><th className="font-normal">{open ? "So far" : "Result"}</th></tr></thead>
          <tbody>
            <tr className="border-b border-line"><td className="py-1 text-muted">Stock</td>
              <td>{st.entry_date ? <>{px(st.entry)} <Muted>{md(st.entry_date)} open</Muted></> : <Muted>entry at the {md(r.entry_on)} open</Muted>}</td>
              <td>{st.status === "closed" ? <>{px(st.exit)} <Muted>{md(st.exit_date)} close</Muted></> : st.last != null ? <>{px(st.last)} <Muted>{nowLabel(st.live_at, st.priced_through)}</Muted></> : <Muted>sells {md(r.exit_by)} close</Muted>}</td>
              <td>{st.ret == null ? <Muted>–</Muted> : <><Move v={st.move ?? null} /> <Muted>price</Muted>
                <span className="block"><Move v={st.ret} /> <Muted>net</Muted></span></>}</td></tr>
            <tr className="border-b border-line"><td className="py-1 text-muted">Option</td>
              <td>{o ? <>{px(o.buy)} <Muted>open plus half the spread</Muted></> : <Muted>{optMissing(r)}</Muted>}</td>
              <td>{o ? <>{px(o.sell)} <Muted>{o.live_at ? `bid, ${nowLabel(o.live_at, null)}` : `${md(o.sell_date)} closing bid`}</Muted></> : <Muted>–</Muted>}</td>
              <td>{o ? <><Move v={o.ret} /><Wide o={o} /></> : <Muted>–</Muted>}</td></tr>
          </tbody>
        </table>
        <p className="text-xs text-muted">
          {r.gap_at_entry != null && <>Stock opened {pct(r.gap_at_entry)} vs its price at the alert. </>}
          {st.peak_date && <>Stock peak {pct(st.peak)} ({md(st.peak_date)} intraday high), drawdown {pct(st.drawdown)} ({md(st.drawdown_date)} intraday low), so they can sit outside the closes on the chart. </>}
          {o && <>Option peak {o.peak == null ? "none (never closed above what you paid)" : `${pct(o.peak)} on ${md(o.peak_date)}`}, drawdown {o.drawdown == null ? "none" : `${pct(o.drawdown)} on ${md(o.drawdown_date)}`}, at closing bids. </>}
          Price = the stock&apos;s move since the buy. Net = that move minus 0.10% in trading costs; the path and day table
          use net, so the last day matches the net result.
        </p>
        {path?.review && <ReviewNotes w={path.review} />}
        {path?.lessons && <RuleOutcomes rules={path.lessons} />}
      </div>
      <div>
        {dates.length ? <>
          <PathChart stock={sp} option={op} hold={HOLD} />
          <table className="mt-2 w-full max-w-[520px] text-xs" data-testid="day-table">
            <thead className="text-left text-muted"><tr><th className="font-normal">Close</th><th className="font-normal">Stock, total since entry</th>
              <th className="font-normal">Option, total since entry</th>{oi.length > 0 && <th className="font-normal">Open interest*</th>}</tr></thead>
            <tbody>{dates.map((d) => { const k = oiAt(d); return <tr key={d} className="border-b border-line">
              <td className="whitespace-nowrap py-0.5">{md(d)}{d === r.session_date ? <Muted> signal</Muted> : liveToday && d === today ? <Muted> live</Muted> : null}</td>
              <td>{pct(at(sp, d))}</td><td>{o ? pct(at(op, d)) : "–"}</td>
              {oi.length > 0 && <td className="whitespace-nowrap">{k ? <>{k[1].toLocaleString("en-US")}{k[2] != null && <Muted> ({k[2] >= 0 ? "+" : "−"}{Math.abs(k[2]).toLocaleString("en-US")})</Muted>}</> : <Muted>–</Muted>}</td>}
            </tr>; })}</tbody>
          </table>
          {oi.length > 0 && <p className="mt-1 max-w-[520px] text-[11px] text-muted">* Contracts of the whale&apos;s option still open after that day&apos;s trading, with the change from the day before.
            UW publishes it the next morning around 6:45 AM ET, so the latest day fills in tomorrow. Context only: it doesn&apos;t change the signal.</p>}
        </> : path === null ? <p className="text-sm text-muted">Loading the day-by-day path…</p> : <p className="text-sm text-muted">No prices yet. Entry is at the {md(r.entry_on)} open; the first price comes after that day&apos;s close.</p>}
      </div>
    </div>
  );
}
