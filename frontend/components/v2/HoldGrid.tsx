"use client";
import type { Signal } from "@/lib/api";
import { pct, isFlat, arrowPct, moveTone, moveDigits, md } from "@/lib/format";
import { useSignalPanel } from "./SignalPanel";
import { earlierHold, ordinal } from "@/lib/repeat";


/** Open signals as a compact grid: ticker, progress through the five sessions, move since the tested buy. */
export default function HoldGrid({ signals }: { signals: Signal[]; watch?: string[] }) {
  const { open, openId } = useSignalPanel();
  return (
    <div>
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {signals.map((s) => {
          const m = s.since_entry, dg = moveDigits(m), up = (m ?? 0) >= 0, flat = m != null && isFlat(m, dg), n = s.hold_day ?? 0, rep = earlierHold(s, signals);
          return (
            <li key={s.id} className="flex">
              <button type="button" onClick={() => open(signals, s.id)} aria-haspopup="dialog"
                aria-label={`${s.ticker} ${m == null ? "" : `${flat ? "flat" : up ? "up" : "down"} ${pct(m, dg)}, `}day ${n} of 5, ${rep ? `${ordinal(rep.nth)} signal, first one sells ${md(rep.first.exit_by)}, ` : ""}full card`}
                className={`flex w-full flex-col justify-start rounded-md border p-3 text-left transition-colors duration-150 hover:border-text ${openId === s.id ? "border-text" : "border-line"} ${m == null || flat ? "bg-panel2" : up ? "bg-bull-soft" : "bg-bear-soft"}`}>
                <span className="flex flex-wrap items-baseline justify-between gap-x-1">
                  <span className="wide text-[17px]">{s.ticker}</span>
                  <span className={`ml-auto whitespace-nowrap text-[15px] font-semibold ${moveTone(m, dg)}`}>
                    {m == null ? "–" : arrowPct(m, dg)}</span>
                </span>
                <span className="mt-2 flex gap-1" aria-label={`day ${n} of 5`}>
                  {[1, 2, 3, 4, 5].map((i) => <span key={i} className={`h-1 flex-1 rounded-full ${i <= n ? "bg-text" : "bg-line"}`} />)}
                </span>
                <span className="mt-1.5 block text-xs text-muted">day {n} of 5, sells {md(s.exit_by)}</span>
                {rep && <span className="mt-1 block text-xs leading-snug text-amber" data-testid="repeat-label"><span className="block">{ordinal(rep.nth)} signal,</span> <span className="block">first one sells {md(rep.first.exit_by)}</span></span>}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
