"use client";
import Link from "next/link";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { Signal } from "@/lib/api";
import { arrowPct, moveTone, TIER, md } from "@/lib/format";
import { earlierHold, ordinal } from "@/lib/repeat";
import WatchButton from "../WatchButton";
import BetLine from "./BetLine";
import SignalDetail from "./SignalDetail";

const wd = (iso: string) => new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString("en-US", { weekday: "short" });

type Ctx = { open: (list: Signal[], id: string) => void; openId: string | null };
const PanelCtx = createContext<Ctx>({ open: () => {}, openId: null });
export const useSignalPanel = () => useContext(PanelCtx);

/** Owner 10-07: "Why it passed" opens a panel instead of growing the card. Desktop: a centred dialog (a side panel sat too
 *  far from the content on wide screens), ‹ › steps through the same group. Phone: a bottom sheet, swipe down or ✕. */
export default function SignalPanelProvider({ watch, children }: { watch: string[]; children: React.ReactNode }) {
  const [list, setList] = useState<Signal[]>([]);
  const [idx, setIdx] = useState(-1);
  const s = idx >= 0 ? list[idx] : null;
  const open = useCallback((l: Signal[], id: string) => { setList(l); setIdx(l.findIndex((x) => x.id === id)); }, []);
  const close = useCallback(() => setIdx(-1), []);
  const closeBtn = useRef<HTMLButtonElement>(null);
  const startY = useRef<number | null>(null);
  const [drag, setDrag] = useState(0);

  useEffect(() => {
    if (!s) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeBtn.current?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "ArrowRight") setIdx((i) => Math.min(list.length - 1, i + 1));
      if (e.key === "ArrowLeft") setIdx((i) => Math.max(0, i - 1));
    };
    window.addEventListener("keydown", key);
    return () => { document.body.style.overflow = prev; window.removeEventListener("keydown", key); };
  }, [s, list.length, close]);

  return (
    <PanelCtx.Provider value={{ open, openId: s?.id ?? null }}>
      {children}
      {s && <>
        <div aria-hidden onClick={close} className="fixed inset-0 z-40 bg-black/45" />
        <div role="dialog" aria-modal="true" aria-label={`${s.ticker}, full card`} data-testid="signal-panel"
          style={{ transform: drag ? `translateY(${drag}px)` : undefined }}
          className="fixed inset-x-0 bottom-0 z-50 max-h-[86vh] overflow-y-auto rounded-t-2xl border-t border-line bg-panel2 px-4 pb-6 pt-2 shadow-2xl
            sm:inset-auto sm:left-1/2 sm:top-1/2 sm:max-h-[85vh] sm:w-[min(660px,92vw)] sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-xl sm:border sm:px-6 sm:pb-6 sm:pt-5">
          <div className="sm:hidden" onTouchStart={(e) => { startY.current = e.touches[0].clientY; }}
            onTouchMove={(e) => { if (startY.current != null) setDrag(Math.max(0, e.touches[0].clientY - startY.current)); }}
            onTouchEnd={() => { if (drag > 80) close(); setDrag(0); startY.current = null; }}>
            <span aria-hidden className="mx-auto mb-2 block h-1 w-10 rounded-full bg-line" />
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-1.5 text-[13px] text-muted">
              {list.length > 1 && <>
                <button type="button" aria-label="Previous signal" disabled={idx === 0} onClick={() => setIdx(idx - 1)}
                  className="rounded-md border border-line px-2.5 py-0.5 hover:border-text disabled:opacity-40">‹</button>
                <button type="button" aria-label="Next signal" disabled={idx === list.length - 1} onClick={() => setIdx(idx + 1)}
                  className="rounded-md border border-line px-2.5 py-0.5 hover:border-text disabled:opacity-40">›</button>
                <span className="ml-1">{idx + 1} of {list.length}</span></>}
            </span>
            <button ref={closeBtn} type="button" onClick={close} className="rounded-md border border-line px-3 py-1 text-[13px] hover:border-text">Close ✕</button>
          </div>

          <header className="mt-3 flex flex-wrap items-center gap-2">
            <Link href={`/ticker/${s.ticker}`} className="wide text-[28px] leading-none hover:underline">{s.watch_only ? s.ticker : <span className="mark">{s.ticker}</span>}</Link>
            <span className="rounded-full border border-bull/30 px-2 py-0.5 text-[13px] font-semibold text-bull">{s.direction > 0 ? "▲ Bullish" : "▼ Bearish"}</span>
            <span className="text-[13px] text-muted">{TIER[s.tier]}</span>
          </header>
          <BetLine s={s} className="mt-3" />
          {!s.watch_only && <dl className="mt-3 flex items-center gap-2.5 text-sm" aria-label="Entry and exit">
            <span aria-hidden className="h-[7px] w-[7px] shrink-0 rounded-full bg-bull" />
            <div className="flex items-baseline gap-1.5"><dt className="text-muted">Buy<span className="sr-only"> at the open</span></dt><dd className="font-semibold">{wd(s.entry)}, {md(s.entry)}</dd></div>
            <span aria-hidden className="h-px min-w-4 flex-1 bg-line" />
            <div className="flex items-baseline gap-1.5"><dt className="text-muted">Sell<span className="sr-only"> at the close</span></dt><dd className="font-semibold">{wd(s.exit_by)}, {md(s.exit_by)}</dd></div>
            <span aria-hidden className="h-[7px] w-[7px] shrink-0 rounded-full bg-sea" />
          </dl>}
          {s.since_entry != null && !s.watch_only && <p className="mt-2 text-sm text-muted">Since the {md(s.entry)} open:{" "}
            <span className={`font-semibold ${moveTone(s.since_entry)}`}>{arrowPct(s.since_entry)}</span>
            {s.hold_day != null && <> · day {s.hold_day} of 5</>}</p>}
          {!s.watch_only && (() => { const rep = earlierHold(s, list); return rep && <p className="mt-1 text-sm text-amber">{ordinal(rep.nth)} signal on {s.ticker}: the first one is still open, sells {md(rep.first.exit_by)}.</p>; })()}

          {(() => {
            const heads: string[] = [];
            if (s.cluster && s.cluster.sector && s.cluster.sector !== "Unknown") heads.push(`${s.cluster.n} ${s.cluster.sector} signals came in on ${md(s.session_date)}, so treat them as one sector bet.`);
            if (s.earnings_warning) heads.push(`Earnings ${md(s.earnings_warning.date)}.`);
            if (s.oi?.confirmed === false) heads.push("Open interest didn't grow the next morning, so the whale may have closed it. In past signals that made no clear difference.");
            return heads.length > 0 && <p className="mt-2 text-sm text-warn">Heads up: {heads.join(" ")}</p>;
          })()}

          <div className="mt-4"><SignalDetail s={s} /></div>

          <footer className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line pt-3 text-[13px]">
            <Link href={`/journal?ticker=${s.ticker}&direction=${s.direction}&setup=${s.tier}${s.entry_price ? `&entry=${s.entry_price}` : ""}`}
              className="underline underline-offset-4">Log trade</Link>
            <WatchButton ticker={s.ticker} on={watch.includes(s.ticker)} />
            <Link href={`/ticker/${s.ticker}`} className="text-muted underline-offset-4 hover:text-text hover:underline">Open {s.ticker} page →</Link>
          </footer>
        </div>
      </>}
    </PanelCtx.Provider>
  );
}
