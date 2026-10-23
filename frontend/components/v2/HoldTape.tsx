import Link from "next/link";
import type { Signal } from "@/lib/api";
import { arrowPct, isFlat, moveDigits, moveTone, shortDate } from "@/lib/format";

type Move = { today_move: number | null; today_day: string | null } | null | undefined;

/** Sightings tape (owner 10-07): the open book's move today, fixed on the left next to the S&P, and every hold's move
 *  today scrolling on the right. Same prices as the hold cards (live while the market is open, the close after).
 *  The tape pauses on hover and stands still for reduced motion; screen readers and keyboards get the plain list
 *  (the hold cards below are the keyboard path). */
export default function HoldTape({ holds, spy, live, pageDay }: { holds: Signal[]; spy: Move; live: boolean; pageDay?: string }) {
  const items = holds.filter((s) => s.today_move != null) as (Signal & { today_move: number })[];
  if (items.length === 0) return null;
  const book = items.reduce((a, s) => a + s.today_move, 0) / items.length;
  const day = items.map((s) => s.today_day).filter(Boolean).sort().at(-1) ?? null;
  const up = book >= 0, flat = isFlat(book, moveDigits(book));
  const chip = (s: Signal & { today_move: number }, k: string) => {
    const f = isFlat(s.today_move, moveDigits(s.today_move)), u = s.today_move > 0;
    return (
      <Link key={k} href={`/ticker/${s.ticker}`} tabIndex={-1} data-copy={k[0]}
        className={`flex shrink-0 items-center gap-2 rounded-full px-2.5 py-1 text-[13px] transition-transform duration-150 hover:scale-105 ${f ? "bg-panel" : u ? "bg-bull-soft" : "bg-bear-soft"}`}>
        <span className="font-semibold tracking-wide">{s.ticker}</span>
        <span className={`tabular-nums ${moveTone(s.today_move, moveDigits(s.today_move))}`}>{arrowPct(s.today_move, moveDigits(s.today_move))}</span>
      </Link>);
  };
  const fresh = items.some((s) => s.today_since === "entry_open");   // bought today: measured from the entry open
  const secs = Math.max(20, items.length * 4);                 // slow: about 4 s per hold across the strip

  return (
    <section data-testid="hold-tape" aria-label="Open holds today" className="mt-4 flex flex-col overflow-hidden rounded-md bg-panel2 sm:flex-row sm:items-stretch">
      <div data-testid="book-today" className={`relative flex shrink-0 flex-wrap items-baseline gap-x-2 gap-y-0.5 py-2.5 pl-4 pr-4 text-[13px] ${flat ? "" : up ? "bg-bull-soft" : "bg-bear-soft"}`}>
        <span aria-hidden className={`absolute inset-y-0 left-0 w-1 ${flat ? "bg-line" : up ? "bg-bull" : "bg-bear"}`} />
        <span className="flex items-center gap-1.5 text-muted"
          title={fresh ? `Holds bought ${live || !day ? "today" : `on ${shortDate(day)}`} count from their entry open, the rest from the previous close.` : undefined}>
          {live && <span aria-hidden className="tape-live h-2 w-2 self-center rounded-full bg-marker" />}
          {items.length} hold{items.length === 1 ? "" : "s"} {live ? "today" : day === pageDay ? "at the close" : day ? `on ${shortDate(day)}` : "at the last close"}</span>
        <span className={`text-[17px] font-semibold tabular-nums ${moveTone(book, moveDigits(book))}`}>{arrowPct(book, moveDigits(book))}</span>
        {spy?.today_move != null && <span className="text-muted">· S&amp;P <span className={moveTone(spy.today_move, moveDigits(spy.today_move))}>{arrowPct(spy.today_move, moveDigits(spy.today_move))}</span></span>}
      </div>
      <div className="tape-mask relative min-w-0 flex-1 self-center py-1.5">
        <ul className="sr-only">{items.map((s) => <li key={s.id}>{s.ticker} {arrowPct(s.today_move, moveDigits(s.today_move))} {s.today_since === "entry_open" ? "since its entry open" : "today"}</li>)}</ul>
        <div aria-hidden className="tape-track flex w-max gap-2 px-2" style={{ animationDuration: `${secs}s` }}>
          {items.map((s) => chip(s, `a${s.id}`))}
          {items.map((s) => chip(s, `b${s.id}`))}
        </div>
      </div>
    </section>
  );
}
