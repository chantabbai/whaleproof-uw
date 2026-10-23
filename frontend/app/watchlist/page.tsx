import Link from "next/link";
import AutoRefresh from "@/components/AutoRefresh";
import Empty from "@/components/Empty";
import WatchAdd from "@/components/WatchAdd";
import WatchButton from "@/components/WatchButton";
import { Hero } from "@/components/v2/ui";
import { get, type EarnWarn, type Signal, type Spot } from "@/lib/api";
import { money, px, shortDate, arrowPct, moveTone, isFlat, md, plural, earnWarnText } from "@/lib/format";

type W = { day: string; tickers: { ticker: string; spot: Spot | null; last_close: number | null; prev_close: number | null;
  flow_today: { n: number; bull: number; bear: number }; signal: Signal | null; earnings_warning: EarnWarn | null }[] };

export default async function WatchlistPage() {
  const w = await get<W>("/api/desk/watchlist");
  if (!w) return <Empty>The WhaleProof API is not answering. Start it with <code>scripts/desk.sh up</code>, then reload.</Empty>;
  const withSignal = w.tickers.filter((t) => t.signal).length;
  return (
    <div>
      <AutoRefresh seconds={60} />
      <Hero name="Watchlist" eyebrow="Saved on this machine"
        title={w.tickers.length ? <>{w.tickers.length} {w.tickers.length === 1 ? "name" : "names"} you&apos;re watching.{withSignal > 0 && <> <span className="mark">{withSignal} with a recent signal.</span></>}</> : "Pick a few names to keep an eye on."}
        lead="They get live prices and levels on Market, earnings warnings on Sightings, and a star wherever they show up." />
      <div className="mt-6 max-w-xl"><WatchAdd /></div>
      {w.tickers.length === 0 ? <div className="mt-8"><Empty>Nothing here yet. Add a ticker above, or press Watch on any signal.</Empty></div> : (
        <ul className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {w.tickers.map((t) => {
            const last = t.spot?.last ?? t.last_close, m = moves(t, w.day);
            const tot = t.flow_today.bull + t.flow_today.bear;
            return (
              <li key={t.ticker} className={`rounded-md border border-line p-4 ${m.day == null || isFlat(m.day) ? "" : m.day > 0 ? "bg-bull-soft" : "bg-bear-soft"}`}>
                <div className="flex items-start justify-between gap-3">
                  <Link href={`/ticker/${t.ticker}`} className="wide text-[28px] leading-none hover:underline">{t.signal ? <span className="mark">{t.ticker}</span> : t.ticker}</Link>
                  <WatchButton ticker={t.ticker} on />
                </div>
                <p className="mt-3 text-[20px] font-semibold" data-testid="watch-move">{px(last)} {m.day != null && <span className={`text-[15px] ${moveTone(m.day, 2)}`}>{arrowPct(m.day, 2)}</span>}
                  <span className="ml-1 text-xs font-normal text-muted">{m.dayLabel}{m.ext != null && ` · ${m.extLabel} ${arrowPct(m.ext, 2)}`}</span></p>
                <div className="mt-3">
                  <div className="flex h-1.5 overflow-hidden rounded-full bg-panel2" aria-hidden>
                    {tot > 0 && <><span className="bg-bull" style={{ width: `${(t.flow_today.bull / tot) * 100}%` }} /><span className="bg-bear" style={{ width: `${(t.flow_today.bear / tot) * 100}%` }} /></>}
                  </div>
                  <p className="mt-1.5 text-xs text-muted">{t.flow_today.n === 0 ? `No alerts ${shortDate(w.day)}` : <>{plural(t.flow_today.n, "alert")} {shortDate(w.day)}: <span className="text-bull">{money(t.flow_today.bull)} bullish</span>, <span className="text-bear">{money(t.flow_today.bear)} bearish</span></>}</p>
                </div>
                {(t.signal || t.earnings_warning) && <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  {t.signal && <span className="rounded-full bg-marker px-2.5 py-0.5 font-semibold text-[color:var(--marker-ink)]">Signal {md(t.signal.session_date)}, {t.signal.tier === "whale" ? "whale-size" : "long shot"} · {t.signal.direction > 0 ? "▲ bullish" : "▼ bearish"}</span>}
                  {t.earnings_warning && <span className="text-warn">● {earnWarnText(t.earnings_warning)}</span>}
                </div>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** The day's move, named by its day, plus the after-hours or pre-market move on top of it (owner 10-08: after the close
 *  "+0.00% live" compared the after-hours price with today's close). While the market is open: the move today, live. */
function moves(t: W["tickers"][number], day: string) {
  const sp = t.spot, mt = sp?.market_time;
  if (sp?.last && sp.prev_close && mt === "regular") return { day: sp.last / sp.prev_close - 1, dayLabel: "today, live", ext: null, extLabel: "" };
  // After hours the quote's prev_close is today's close; if the daily bars haven't caught up yet, last_close is still
  // yesterday's, so measure today's move from it instead.
  const lagging = mt === "postmarket" && sp?.prev_close && t.last_close && sp.prev_close !== t.last_close;
  const d = lagging ? sp!.prev_close! / t.last_close! - 1 : t.last_close && t.prev_close ? t.last_close / t.prev_close - 1 : null;
  const name = new Date(`${day}T12:00:00`).toLocaleDateString("en-US", { weekday: "short" });
  const ext = sp?.last && sp.prev_close && (mt === "postmarket" || mt === "premarket") ? sp.last / sp.prev_close - 1 : null;
  return { day: d, dayLabel: name, ext, extLabel: mt === "premarket" ? "pre-market" : "after hours" };
}

