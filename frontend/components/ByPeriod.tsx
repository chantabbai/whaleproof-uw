"use client";
import { arrowPct, moveTone, plainPct } from "@/lib/format";

/** One period's numbers, as TrackerTable's summarize() makes them, plus the all-alerts baseline. */
export type PeriodRow = {
  p: string; closed: number; open: number; won: number; spyAvg: number | null; vsAvg: number | null; stockWin: number | null; stockAvg: number | null;
  stockMed: number | null; optN: number; optWin: number | null; optAvg: number | null; optMed: number | null; optBeat: number | null;
  base: number | null; alerts: number | null;
};

const FEW = 30;
const few = (n: number) => n > 0 && n < FEW;
const n = (v: number) => v.toLocaleString("en-US");
/** Same as the tracker's Move: arrow + up/down colour, muted when flat or when `dim` (too few trades). */
const Num = ({ v, bold = false, dim = false }: { v: number | null | undefined; bold?: boolean; dim?: boolean }) =>
  v == null ? <span className="text-muted">–</span>
    : <span className={`${dim ? "text-muted" : moveTone(v)} ${bold ? "font-semibold" : ""}`}>{arrowPct(v)}</span>;

/** Owner 10-07: answers first, then one table (cards on phone) with two column groups — edge over all UW alerts, and
 *  the typical stock vs option trade — oldest period first, live last and muted, colour only on the answer columns. */
/** The section's one-line summary (goes in the collapsible's grey note, like the page's other sections). */
export function byPeriodNote(rows: PeriodRow[]): string {
  const tested = rows.filter((r) => r.vsAvg != null && r.base != null);
  const wins = tested.filter((r) => (r.vsAvg as number) > (r.base as number)).length;
  const priced = rows.filter((r) => r.optBeat != null && !few(r.optN));
  const total = priced.reduce((a, r) => a + r.optN, 0);
  const stockWon = priced.reduce((a, r) => a + r.optN - Math.round((r.optBeat as number) * r.optN), 0);
  return `Our shortlist of UW alerts added an edge in ${wins} of ${tested.length} test periods` +
    (total ? `, and the stock did better than the whale's option in ${n(stockWon)} of ${n(total)} trade${total === 1 ? "" : "s"} (${plainPct(stockWon / total)}).` : ".");
}

function Edge({ r }: { r: PeriodRow }) {
  const added = r.vsAvg != null && r.base != null ? r.vsAvg - r.base : null;
  return (
    <span data-testid="edge-cell">
      {added == null ? <span className="text-muted">–</span> : <span data-testid="edge"><Num v={added} dim={few(r.closed)} /></span>}
      {few(r.closed) && <span data-testid="too-small" className="block text-xs text-warn">too small: {r.closed} of {FEW} needed</span>}
    </span>);
}

/** Owner 10-21: the real win count (stock up after costs), so "Stock vs option" isn't read as wins. */
const Won = ({ r }: { r: PeriodRow }) => r.closed
  ? <span data-testid="won" className={few(r.closed) ? "text-muted" : ""}>{`${n(r.won)} of ${n(r.closed)} (${plainPct(r.won / r.closed)})`}</span>
  : <span className="text-muted">–</span>;

function Better({ r }: { r: PeriodRow }) {
  if (r.optBeat == null) return <span className="text-muted">–</span>;
  const o = Math.round(r.optBeat * r.optN), st = r.optN - o;
  return (
    <span data-testid="better-trade">
      <span className={few(r.optN) ? "text-muted" : ""}>{o > st ? "Option won " : st > o ? "Stock won " : "Even, "}{`${n(Math.max(o, st))} of ${n(r.optN)} (${plainPct(Math.max(o, st) / r.optN)})`}</span>
      {few(r.optN) && <span data-testid="too-small" className="block text-xs text-warn">too small: {r.optN} of {FEW} needed</span>}
    </span>);
}

export default function ByPeriod({ rows, live }: { rows: PeriodRow[]; live: PeriodRow | null }) {
  const all = live ? [...rows, live] : rows;
  const head = "py-2 pr-3 font-normal";
  const cell = (r: PeriodRow, first = false) => `py-2 pr-3 ${first ? "" : "tabular-nums"} ${r === live ? "text-muted" : ""}`;
  const signals = (r: PeriodRow) => `${n(r.closed)} signal${r.closed === 1 ? "" : "s"}${r.open ? ` · ${r.open} open` : ""}`;
  const sep = (r: PeriodRow) => (r === live ? "border-t border-dashed border-line" : "border-t border-line");

  return (
    <div className="space-y-6">

      <div className="overflow-x-auto">
        <table data-testid="by-period-table" className="hidden w-full text-sm sm:table">
          <thead className="text-left text-xs text-muted">
            <tr><th />
              <th colSpan={4} className="pb-1 pr-3 font-normal"><span className="block border-b border-line pb-1">vs S&amp;P 500, stock held 5 days</span></th>
              <th colSpan={4} className="pb-1 font-normal"><span className="block border-b border-line pb-1">Typical trade on the same signal</span></th></tr>
            <tr className="border-b border-text">
              <th className={head}>Period</th><th className={`${head}`}>Our shortlist</th><th className={`${head}`}>All UW alerts</th>
              <th className={head}>Edge</th><th className={head}>S&amp;P 500</th>
              <th className={head}>Won</th><th className={`${head}`}>Stock</th><th className={`${head}`}>Option</th><th className={head}>Stock vs option</th></tr></thead>
          <tbody>{all.map((r) => (
            <tr key={r.p} data-testid="period" className={`${sep(r)} align-top`}>
              <td className={cell(r, true)}>{r.p}<span className="block text-xs text-muted">{signals(r)}</span></td>
              <td className={cell(r)}><Num v={r.vsAvg} dim={r === live} /></td>
              <td className={cell(r)}><Num v={r.base} dim={r === live} /></td>
              <td className={cell(r)}><Edge r={r} /></td>
              <td className={cell(r)}><span data-testid="spy"><Num v={r.spyAvg} dim /></span></td>
              <td className={cell(r)}><Won r={r} /></td>
              <td className={cell(r)}><Num v={r.stockMed} dim={r === live} /></td>
              <td className={cell(r)}><Num v={r.optMed} dim={r === live || few(r.optN)} /></td>
              <td className={cell(r)}><Better r={r} /></td>
            </tr>))}</tbody>
        </table>
      </div>

      <div data-testid="by-period-cards" className="space-y-2 sm:hidden">
        {all.map((r) => (
          <div key={r.p} data-testid="period" className={`rounded-md bg-panel2 p-3 text-[13px] ${r === live ? "text-muted" : ""}`}>
            <div className="font-semibold">{r.p} <span className="font-normal text-muted">· {signals(r)}</span></div>
            <div className="mt-1.5 flex items-start justify-between gap-2"><span className="text-muted">Edge</span><span className="text-right"><Edge r={r} /></span></div>
            <div className="text-xs text-muted">Our shortlist <Num v={r.vsAvg} dim={r === live} /> vs all UW alerts <Num v={r.base} dim={r === live} />, vs S&amp;P 500 (S&amp;P 500 itself <span data-testid="spy"><Num v={r.spyAvg} dim /></span>)</div>
            <div className="mt-1.5 flex items-start justify-between gap-2"><span className="text-muted">Won</span><span className="text-right"><Won r={r} /></span></div>
            <div className="mt-1.5 text-muted">Typical stock <Num v={r.stockMed} dim={r === live} /> · option <Num v={r.optMed} dim={r === live || few(r.optN)} /></div>
            <div className="mt-1.5 flex items-start justify-between gap-2"><span className="text-muted">Stock vs option</span><span className="text-right"><Better r={r} /></span></div>
          </div>))}
      </div>

      <div className="space-y-1 text-xs text-muted">
        <p>Our shortlist / All UW alerts = average return vs the S&amp;P 500, every call or put bet UW flagged those days traded the same way. Edge = what narrowing to the shortlist added. S&amp;P 500 = what the S&amp;P 500 itself did over the same days, on average.</p>
        <p>Won = trades where the stock made money after costs. Typical = the median trade, so a few big winners can&apos;t swing it. Stock vs option = whether the stock or the option returned more on the same signal, and how often.</p>
        <p>The practice year is where the rules were chosen. Numbers from fewer than 30 trades are grey and marked too small: about 4 live signals finish a day. Averages and win rates per period: pick the period in the filter above.</p>
      </div>

    </div>
  );
}
