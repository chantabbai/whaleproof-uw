"use client";
import Link from "next/link";
import type { Signal } from "@/lib/api";
import { etTime, TIER, md } from "@/lib/format";
import BetLine from "./BetLine";
import { useSignalPanel } from "./SignalPanel";
import WatchButton from "../WatchButton";

const wd = (iso: string) => new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString("en-US", { weekday: "short" });

/** A signal at a glance: ticker, what the whale bought (one line), the tested trade (buy → sell), actions.
 *  The full card (why it passed, levels, open interest…) opens in place. */
export default function SignalTile({ s, watching, surfacedAt, group = [s] }: { s: Signal; watching: boolean; surfacedAt?: string | null; group?: Signal[] }) {
  const surfacing = surfacedAt !== undefined;      // today's flow, before the 4:15 PM decision: watch, don't buy yet
  const { open: openPanel, openId } = useSignalPanel();
  const open = openId === s.id;
  const warn = [s.oi?.confirmed === false, !!s.earnings_warning, !!(s.cluster && s.cluster.sector && s.cluster.sector !== "Unknown")].filter(Boolean).length;
  return (
    <article className={`relative overflow-hidden rounded-md border bg-panel2 p-5 ${open ? "ring-2 ring-marker/60" : ""} ${s.watch_only || surfacing ? "border-dashed border-line" : "border-line"}`}>
      {!s.watch_only && !surfacing && <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-marker opacity-70" />}
      <header className="flex items-center gap-3">
        <Link href={`/ticker/${s.ticker}`} className="wide text-[28px] leading-none hover:underline"><span className="mark">{s.ticker}</span></Link>
        <span className="rounded-full border border-bull/30 px-2 py-0.5 text-[13px] font-semibold text-bull">▲ Bullish</span>
        <span className="ml-auto shrink-0"><WatchButton ticker={s.ticker} on={watching} compact /></span>
      </header>
      <p className="mt-1.5 text-[13px] text-muted">{TIER[s.tier]}</p>

      <BetLine s={s} className="mt-3" />

      {surfacing
        ? <p className="mt-4 border-l-[3px] border-dashed border-line pl-3 text-sm text-muted" aria-label="Not final yet">
            Surfaced{surfacedAt ? ` at ${etTime(surfacedAt)}` : ""}. Final at 4:15 PM ET; if it stays, the rule buys at the {wd(s.entry)}, {md(s.entry)} open.</p>
        : <dl className="mt-3 flex items-center gap-2.5 text-sm" aria-label="Entry and exit">
            <span aria-hidden className="h-[7px] w-[7px] shrink-0 rounded-full bg-bull" />
            <div className="flex items-baseline gap-1.5"><dt className="text-muted">Buy<span className="sr-only"> at the open</span></dt><dd className="font-semibold">{wd(s.entry)}, {md(s.entry)}</dd></div>
            <span aria-hidden className="h-px min-w-4 flex-1 bg-line" />
            <div className="flex items-baseline gap-1.5"><dt className="text-muted">Sell<span className="sr-only"> at the close</span></dt><dd className="font-semibold">{wd(s.exit_by)}, {md(s.exit_by)}</dd></div>
            <span aria-hidden className="h-[7px] w-[7px] shrink-0 rounded-full bg-sea" />
          </dl>}

      <footer className="mt-3.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px]">
        <button type="button" onClick={() => openPanel(group, s.id)} aria-haspopup="dialog"
          className="rounded-full border border-line px-3 py-1 font-medium hover:border-text">See details →</button>
        <Link href={`/journal?ticker=${s.ticker}&direction=${s.direction}&setup=${s.tier}${s.entry_price ? `&entry=${s.entry_price}` : ""}`}
          className="tap text-muted underline-offset-4 hover:text-text hover:underline">Log trade</Link>
        {warn > 0 && <span className="text-warn">● {warn} heads-up{warn > 1 ? "s" : ""} inside</span>}
      </footer>

    </article>
  );
}
