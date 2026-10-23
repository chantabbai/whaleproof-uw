"use client";
import Link from "next/link";
import { useEffect, useId, useState } from "react";
import type { Signal } from "@/lib/api";
import { plainPct, shortDate, TIER, moveTone, isFlat, md } from "@/lib/format";
import Dir from "./Dir";
import BetLine from "./v2/BetLine";
import SignalDetail from "./v2/SignalDetail";
import WatchButton from "./WatchButton";

const day = (iso: string) => new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString("en-US", { weekday: "long" });

/** One signal, readable as two sentences: what the whale bought, and what we tested. Everything else folds out. */
export default function SignalCard({ s, watching, open: openAll = false, embedded = false }:
  { s: Signal; watching: boolean; detail?: boolean; open?: boolean; embedded?: boolean }) {
  const [open, setOpen] = useState(openAll);
  useEffect(() => setOpen(openAll), [openAll]);
  const panelId = useId();
  // forming = today's flow before the filter's decision time (4:15 PM ET); after that the signal is final
  const nyNow = new Date().toLocaleString("sv-SE", { timeZone: "America/New_York" });   // "YYYY-MM-DD HH:MM:SS"
  const formingToday = s.session_date === nyNow.slice(0, 10) && nyNow.slice(11, 16) < "16:15";
  const heads: string[] = [];
  if (s.cluster && s.cluster.sector && s.cluster.sector !== "Unknown") heads.push(`${s.cluster.n} ${s.cluster.sector} signals came in on ${md(s.session_date)}, so treat them as one sector bet.`);
  if (s.earnings_warning) heads.push(`Earnings ${shortDate(s.earnings_warning.date)}.`);
  if (s.oi?.confirmed === false) heads.push("Open interest didn't grow the next morning, so the whale may have closed it. In past signals that made no clear difference.");
  return (
    <article className={embedded ? "" : `border-t py-5 ${s.watch_only ? "border-dashed border-line" : "border-text"}`}>
      {embedded ? heads.length > 0 && <p className="text-sm text-warn">Heads up: {heads.join(" ")}</p> : <>
      <header className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <Link href={`/ticker/${s.ticker}`} className="wide text-[28px] leading-none hover:underline">
          {s.watch_only ? s.ticker : <span className="mark">{s.ticker}</span>}
        </Link>
        <Dir d={s.direction} />
        <span className="text-sm text-muted">{s.watch_only ? `${TIER[s.tier]}, on watch only` : TIER[s.tier]}</span>
        {formingToday && <span className="text-sm font-medium text-warn">Still forming. Final after 4:15 PM ET.</span>}
        <span className="ml-auto flex items-baseline gap-4">
          <WatchButton ticker={s.ticker} on={watching} />
          <Link href={`/journal?ticker=${s.ticker}&direction=${s.direction}&setup=${s.tier}${s.entry_price ? `&entry=${s.entry_price}` : ""}`}
            className="tap text-[13px] text-muted underline-offset-4 hover:text-text hover:underline">Log trade</Link>
        </span>
      </header>

      <div className="mt-3 max-w-[70ch] space-y-1.5 text-[15px] leading-relaxed">
        <BetLine s={s} />
        {s.watch_only
          ? <p className="text-muted">Put buys aren&apos;t part of the signal rules, so this is here to watch, not to act on.</p>
          : <p>The trade: buy the stock at the {day(s.entry)} open <span className="whitespace-nowrap">({md(s.entry)})</span> and sell at the {day(s.exit_by)} close <span className="whitespace-nowrap">({md(s.exit_by)})</span>.
              {s.since_entry != null && <> Since that open it&apos;s <span className={`font-semibold ${moveTone(s.since_entry)}`}>
                {isFlat(s.since_entry) ? "flat" : `${s.since_entry > 0 ? "▲ up" : "▼ down"} ${plainPct(Math.abs(s.since_entry), 1)}`}</span>.</>}</p>}
        {heads.length > 0 && <p className="text-sm text-warn">Heads up: {heads.join(" ")}</p>}
      </div>

      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls={panelId}
        className="mt-3 text-[13px] text-muted underline underline-offset-4 hover:text-text">
        {open ? "Hide details" : "Show details"}
      </button>
      </>}

      {(open || embedded) && <div id={panelId} className={embedded ? "mt-3" : "mt-4 bg-panel2 px-4 py-4"}>
        <SignalDetail s={s} />
      </div>}
    </article>
  );
}
