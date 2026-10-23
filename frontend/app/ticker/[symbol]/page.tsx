import EvidenceBadge from "@/components/v2/EvidenceBadge";
import Link from "next/link";
import AutoRefresh from "@/components/AutoRefresh";
import { HistoryChip, type BetsData } from "@/components/BetsTable";
import Dir from "@/components/Dir";
import Empty from "@/components/Empty";
import PriceChart from "@/components/PriceChart";
import { Block, Eyebrow, More, MoreList, Pill, Tile, Tiles } from "@/components/v2/ui";
import SignalCard from "@/components/SignalCard";
import WatchButton from "@/components/WatchButton";
import { BarsKey, EarnChip, ImpliedChip, PastMoves, When, movePct } from "@/components/EarnBits";
import { get, type EarnCard, type Gex, type Signal, type Spot } from "@/lib/api";
import { etTime, IV_RV_CHEAP, IV_RV_RICH, money, pct, plainPct, px, ratioX, shortDate, arrowPct, moveTone, days, dte, plural, pastSignalsSub } from "@/lib/format";

type T = {
  ticker: string; day: string; sector: string | null; watch: boolean;
  company?: { name: string | null; description: string | null } | null;
  flow_daily: { date: string; bull: number; bear: number; other: number; n: number }[];
  top_alerts: { premium: number; kind: string; strike: number; expiry: string; dte: number; ask_share: number;
    direction: number; sweep: boolean; opening: boolean; date: string; otm_pct: number }[];
  bars: { date: string; close: number }[]; iv_rank: { date: string; v: number }[];
  vol: [string, number | null, number | null, string | null][]; gex: Gex | null; dp_levels: [number, number][];
  earnings: { date: string; time: string }[]; signal_today: Signal[]; holding?: Signal[];
  rejected_today: { reason: string; premium: number; strike: number; kind: string }[];
  history_loaded?: boolean; updating?: boolean; fresh_at?: string | null; earnings_view?: EarnCard;
  spot?: Spot | null; spot_at?: string | null;
  past_signals: { date: string; tier: string; direction: number; premium: number; otm_pct: number; x5: number | null; ret?: number | null; period: string }[];
  benchmark?: boolean;
};

export default async function TickerPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params;
  const [t, all] = await Promise.all([get<T>(`/api/desk/ticker/${encodeURIComponent(symbol.toUpperCase())}`),
    get<BetsData>("/api/desk/alerts")]);
  if (!t) return <Empty>Nothing came back for {symbol.toUpperCase()}. Check the symbol, or make sure the API is running.</Empty>;
  const levels = [
    ...(t.gex?.call_wall ? [{ v: t.gex.call_wall, label: "call wall", tone: "bull" as const }] : []),
    ...(t.gex?.put_wall ? [{ v: t.gex.put_wall, label: "put wall", tone: "bear" as const }] : []),
    ...(t.gex?.gamma_flip ? [{ v: t.gex.gamma_flip, label: "gamma flip", tone: "muted" as const }] : []),
    ...(t.dp_levels[0] ? [{ v: t.dp_levels[0][0], label: "dark-pool level", tone: "brass" as const }] : []),
  ];
  const maxFlow = Math.max(1, ...t.flow_daily.map((d) => Math.max(d.bull, d.bear)));
  const ivNow = t.iv_rank.at(-1);
  const rv = [...t.vol].reverse().find((v) => v[2] != null);
  const iv30 = [...t.vol].reverse().find((v) => v[1] != null);
  // An S&P tracker can't beat the S&P (always −costs), so its own signals are scored on the plain five-day move
  const score = (p: T["past_signals"][number]) => (t.benchmark ? p.ret ?? null : p.x5);
  const scored = t.past_signals.filter((p) => score(p) != null);
  const bets = (all?.bets ?? []).filter((b) => b.ticker === t.ticker);
  // During the session the newest daily bar is today's unfinished candle: it isn't a close, so the close is the bar before
  const intraday = t.spot?.market_time === "regular" && t.bars.at(-1)?.date === t.day;
  const lastBar = intraday ? t.bars.at(-2) : t.bars.at(-1), firstBar = t.bars.at(-22);
  // the live price while the market is open, even before today's bar arrives (the levels text said "Last close" under a live price tile)
  const liveNow = t.spot?.market_time === "regular" && t.spot.last ? t.spot.last : null;
  const ch30 = lastBar && firstBar ? lastBar.close / firstBar.close - 1 : null;
  const now = t.spot?.last ?? null;
  const dayCh = now && t.spot?.prev_close ? now / t.spot.prev_close - 1 : null;
  const session = t.spot?.market_time === "postmarket" ? "after hours" : t.spot?.market_time === "premarket" ? "pre-market" : "today";
  const liveRecent = !!t.spot_at && Date.now() - Date.parse(t.spot_at) < 5 * 60_000;   // refresher still pricing it
  const ratio = iv30?.[1] && rv?.[2] ? iv30[1] / rv[2] : null;
  const priced = ratio == null ? "–" : ratio > IV_RV_RICH ? "Expensive" : ratio < IV_RV_CHEAP ? "Cheap" : "Fair";
  const nextE = t.earnings_view?.next ?? null;
  const isSignal = t.signal_today.length > 0;
  const held = t.holding ?? [];
  const won = scored.filter((p) => (score(p) ?? 0) > 0).length;
  const flowTot = t.flow_daily.reduce((a, d) => ({ bull: a.bull + d.bull, bear: a.bear + d.bear }), { bull: 0, bear: 0 });
  // a typo (/ticker/ZZZZQ) has nothing at all once the refresher has looked: say so, not "Not a signal today"
  if (!t.updating && !t.bars.length && !t.flow_daily.length && !t.company && !t.past_signals.length && !isSignal && !held.length)
    return (
      <div>
        <h1 className="wide text-[48px] leading-none md:text-[56px]">{t.ticker}</h1>
        <div className="mt-6"><Empty>No prices or options flow for {t.ticker}. Check the symbol.</Empty></div>
      </div>
    );
  return (
    <div>
      <header className="flex flex-wrap items-start gap-x-6 gap-y-4">
        <div>
          <Eyebrow>{t.company?.name
            ? <><span className="font-semibold text-text" data-testid="company">{t.company.name}</span>{t.sector ? ` · ${t.sector}` : ""}{lastBar ? `${t.sector ? "," : " ·"} prices through ${shortDate(lastBar.date)}` : ""}</>
            : <>{t.sector ?? "Ticker"}{lastBar ? `, prices through ${shortDate(lastBar.date)}` : ""}</>}</Eyebrow>
          <div className="mt-3 flex flex-wrap items-center gap-4">
            <h1 className="wide text-[48px] leading-none md:text-[56px]">{isSignal || held.length ? <span className="mark">{t.ticker}</span> : t.ticker}</h1>
            <Pill tone={isSignal || held.length ? "mark" : null}>{isSignal ? "Signal on the latest session" : held.length ? `Signal from ${shortDate(held[0].session_date)}, in its five-day hold` : "Not a signal today"}</Pill>
            <WatchButton ticker={t.ticker} on={t.watch} />
          </div>
          {t.company?.description && <p className="mt-2.5 line-clamp-2 max-w-[72ch] text-sm text-muted">{t.company.description}</p>}
        </div>
      </header>
      <p className="mt-3 text-[13px] text-muted" role="status">
        {t.gex?.date ? `Gamma levels from ${shortDate(t.gex.date)}.` : ""}
        {t.updating ? " Getting the latest prices and levels now…" : t.fresh_at ? ` Refreshed at ${etTime(t.fresh_at)}.` : ""}
      </p>
      {t.updating ? <AutoRefresh seconds={10} /> : liveRecent && <AutoRefresh seconds={60} />}

      <div className="mt-8"><Tiles>
        {now != null
          ? <Tile accent="sea" k={`${session === "today" ? "Price" : session === "after hours" ? "After-hours price" : "Pre-market price"} at ${etTime(t.spot_at)}`} v={px(now)}
              sub={<>{dayCh != null && <span className={moveTone(dayCh, 2)}>{arrowPct(dayCh, 2)} {session === "today" ? "today" : `${session}, vs the last close`}</span>}
              {lastBar && <span className="block">last close {px(lastBar.close)}{ch30 != null ? `, ${arrowPct(ch30)} over a month` : ""}</span>}</>} />
          : <Tile accent="sea" k="Last close" v={px(lastBar?.close)} sub={ch30 == null ? undefined : `${arrowPct(ch30)} over a month`} />}
        <Tile accent="amber" k={ivNow ? `Option prices: IV rank, ${shortDate(ivNow.date)}` : "Option prices: IV rank"} v={ivNow ? `${ivNow.v.toFixed(0)}/100` : "–"}
          sub={ivNow ? `Where implied vol sits in its range over the past 12 months: 0 = cheapest, 100 = priciest.${ratio ? ` Against the stock's recent moves: ${priced.toLowerCase()}.` : ""}` : "not saved yet"} />
        <Tile accent="amber" k={nextE?.reported ? "Earnings today" : "Next earnings"} v={nextE ? shortDate(nextE.date) : t.earnings[0] ? shortDate(t.earnings[0].date) : "–"}
          sub={nextE ? <><When time={nextE.time} lower />{nextE.reported ? ", already out" : nextE.implied != null && <>, options expect <ImpliedChip v={nextE.implied} /></>}</> : "none on file"} />
        <Tile accent="brass" k="Past signals" v={scored.length ? `${won} of ${scored.length}` : "0"} sub={pastSignalsSub({ finished: scored.length, open: isSignal || held.length > 0 || t.past_signals.length > 0, holding: held.length > 0, benchmark: !!t.benchmark })} />
      </Tiles></div>
      {scored.length > 0 && <div className="mt-4"><EvidenceBadge /></div>}

      {held.length > 0 && <div className="mt-14"><Block wave title="Still in its hold" sub="An earlier signal on this stock, with its move since entry.">
        <div>{held.map((s) => <SignalCard key={s.id} s={s} watching={t.watch} detail open />)}</div>
      </Block></div>}

      {isSignal && <div className="mt-14"><Block wave title="The signal">
        <div>{t.signal_today.map((s) => <SignalCard key={s.id} s={s} watching={t.watch} detail open />)}</div>
      </Block></div>}
      {!isSignal && t.rejected_today.length > 0 && (
        <div className="mt-14"><Block wave title={held.length ? "Today's bets on it, and why none is a new signal" : "Why it isn't a signal"}>
          <ul className="space-y-2 text-sm">{t.rejected_today.slice(0, 3).map((r, i) => (
            <li key={i} className="rounded-md bg-panel2 px-4 py-2.5"><b>{money(r.premium)}</b> on the {px(r.strike)} {r.kind}: {r.reason}</li>))}</ul>
        </Block></div>
      )}

      <div className="mt-14">
        <Block wave title="Price and levels" sub={levelsRead(liveNow ?? lastBar?.close ?? null, t.gex, t.dp_levels[0]?.[0] ?? null, liveNow != null)}>
          <div className="max-w-[820px]"><PriceChart bars={intraday && t.spot?.last ? [...t.bars.slice(0, -1), { ...t.bars[t.bars.length - 1], close: t.spot.last }] : t.bars} levels={levels} liveNow={intraday} /></div>
          <div className="mt-4 max-w-[820px]"><MoreList><More title="What these levels mean">
            <p className="max-w-[68ch] text-sm text-muted">They are stock prices worked out from options trading, useful whether you trade the stock or
              options. A wall is the strike with the biggest pile of options: calls for the call wall, puts for the put wall. Above the gamma flip
              (positive gamma), dealers tend to sell rallies and buy dips, which damps moves; below it (negative gamma), they tend to sell
              drops and buy rallies, which makes moves bigger. The dark-pool level
              is where the most off-exchange stock volume traded. All of it is context, not a buy or sell signal.</p>
          </More></MoreList></div>
        </Block>
      </div>

      <div className="mt-14">
        <Block wave title="Big-money flow, last 30 days" sub={t.flow_daily.length ? <><span className="text-bull">■ {money(flowTot.bull)} bullish</span> and <span className="text-bear">▨ {money(flowTot.bear)} bearish</span> in alerts over $100K</> : undefined}>
          {t.flow_daily.length === 0 ? <Empty>No flow alerts in the last 30 days.</Empty> : (
            <div>
              <div className="flex h-32 items-end gap-1" role="img" aria-label="Daily bullish and bearish premium">
                {t.flow_daily.map((d) => (
                  <div key={d.date} className="flex flex-1 flex-col justify-end gap-px" title={`${shortDate(d.date)}: ${money(d.bull)} bullish, ${money(d.bear)} bearish, ${plural(d.n, "alert")}`}>
                    <div className="rounded-t-sm bg-bull" style={{ height: `${(d.bull / maxFlow) * 60}px` }} />
                    <div className="rounded-b-sm" style={{ height: `${(d.bear / maxFlow) * 60}px`, background: "repeating-linear-gradient(45deg, var(--bear) 0 3px, transparent 3px 5px)" }} />
                  </div>
                ))}
              </div>
              <p className="mt-2 text-xs text-muted">{shortDate(t.flow_daily[0].date)} to {shortDate(t.flow_daily.at(-1)?.date)}. Calls bought and puts sold count as bullish.</p>
            </div>
          )}
        </Block>
      </div>

      <div className="mt-14"><MoreList>
        {bets.length > 0 && <More title={`How bets like today's did before (${bets.length})`} note={<>How similar bets did before. History only, not a signal. More on <Link className="underline" href="/bets#bets">Flow check</Link>.</>}>
          <ul className="border-t border-line text-sm">{bets.map((b) => (
            <li key={b.id} className="flex flex-wrap items-start gap-x-4 gap-y-1 border-b border-line py-2.5">
              <span><Dir d={b.direction} compact /> {money(b.premium)} on the {px(b.strike)} {b.opt_type}, {dte(b.dte, " out")}
                <span className="block text-xs text-muted">{b.verdict === "signal" ? "This one is our signal." : b.reason}</span></span>
              <span className="ml-auto"><HistoryChip h={b.history} /></span>
            </li>))}</ul>
        </More>}
        {t.earnings_view && (t.earnings_view.next || t.earnings_view.history.length > 0) && (() => {
          const ev = t.earnings_view, n = ev.next;
          const beats = ev.history.filter((h) => h.beat != null);
          return (
            <More title="Earnings: expected move vs past moves" note={<>Background only. Cheap expected moves got beaten more often than expensive ones every year, but not enough to trade on. More on <Link className="underline" href="/earnings">Earnings</Link>.</>}>
              <div className="grid gap-3 text-sm md:grid-cols-[1fr_auto] md:items-center">
                <div>
                  {n ? (
                    <p>{n.reported ? "Reported" : "Next report"} <strong>{shortDate(n.date)}</strong>, <When time={n.time} lower />. {n.implied != null ? <>Options {n.reported ? "expected" : "expect"} <ImpliedChip v={n.implied} />; the typical past move was {movePct(n.past)}.</> : `No expected move priced yet. The typical past move was ${movePct(n.past)}.`}{" "}
                      {n.label ? <><EarnChip label={n.label} /> <span className="text-xs text-muted">options charge {n.ratio != null ? ratioX(n.ratio) : ""}× the usual move</span></> : <span className="text-xs text-muted">({n.note})</span>}
                    </p>
                  ) : <p className="text-muted">No upcoming report on file.</p>}
                  {beats.length > 0 && <p className="mt-1 text-xs text-muted">In the last {plural(beats.length, "report")} the stock moved more than expected {beats.filter((h) => h.beat).length} time{beats.filter((h) => h.beat).length === 1 ? "" : "s"}.</p>}
                </div>
                <PastMoves history={ev.history} implied={n?.implied ?? null} />
              </div>
              {ev.history.length > 0 && <p className="mt-2 text-xs text-muted">Bars, oldest first: <BarsKey /></p>}
            </More>
          );
        })()}
        {t.top_alerts.length > 0 && <More title={`Biggest alerts (${t.top_alerts.length})`}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-2 pr-3 font-normal">Date</th><th className="font-normal">Side</th><th className="font-normal">Paid</th><th className="font-normal">Contract</th><th className="font-normal">Strike vs price</th><th className="pr-3 font-normal">Notes</th></tr></thead>
              <tbody>{t.top_alerts.map((a, i) => (
                <tr key={i} className="border-b border-line">
                  <td className="py-1.5 pr-3">{shortDate(a.date)}</td>
                  <td>{a.direction ? <Dir d={a.direction} compact /> : <span className="text-xs text-muted">mixed</span>}</td>
                  <td>{money(a.premium)}</td><td className="whitespace-nowrap">{px(a.strike)} {a.kind}, {shortDate(a.expiry)} ({dte(a.dte)})</td>
                  <td>{otmWords(a.otm_pct)}</td>
                  <td className="pr-3 text-xs text-muted">{[a.sweep && "swept", a.opening && "opening", `${plainPct(a.ask_share)} at the ask`].filter(Boolean).join(", ")}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </More>}
        <More title={`Past signals on ${t.ticker} (${t.past_signals.length})`} note={t.benchmark ? "Net = the five-day stock result after 0.10% trading costs (this is the S&P 500, so there is nothing to compare it with). Same numbers as Track record." : "Net = the five-day stock result after 0.10% trading costs; next to it, the same days against the S&P 500. Same numbers as Track record."}>
          {t.past_signals.length === 0 ? (t.history_loaded === false
            ? <Empty>History isn&apos;t loaded on this install. Run the full backfill (README, &ldquo;Run it yourself&rdquo;) to see signals back to October 2023.</Empty>
            : <Empty>{t.ticker} has never had a signal since October 2023.</Empty>) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-sm">
                <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-2 pr-3 font-normal">Flow date</th><th className="font-normal">Kind</th><th className="font-normal">Paid</th><th className="font-normal">Net, 5 days</th>{!t.benchmark && <th className="font-normal">vs S&amp;P 500</th>}<th className="pr-3 font-normal">Test period</th></tr></thead>
                <tbody>{t.past_signals.map((p, i) => (
                  <tr key={i} className="border-b border-line">
                    <td className="py-1.5 pr-3">{shortDate(p.date)}</td><td>{p.tier === "whale" ? "Whale-size" : "Long shot"} <Dir d={p.direction} compact /></td>
                    <td>{money(p.premium)}</td>
                    <td className={moveTone(p.ret)}>{p.ret == null ? <span className="text-xs text-muted">in its hold</span> : arrowPct(p.ret)}</td>
                    {!t.benchmark && <td className={moveTone(p.x5)}>{p.x5 == null ? "–" : pct(p.x5)}</td>}
                    <td className="pr-3 text-xs text-muted">{p.period}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          )}
        </More>
        <More title="Volatility and dates">
          <dl className="grid gap-4 text-sm sm:grid-cols-2">
            <div><dt className="text-xs text-muted">Implied vol vs how much it actually moved (30 vs 21 days)</dt>
              <dd className="text-lg font-semibold">{iv30?.[1] != null ? plainPct(iv30[1]) : "–"} vs {rv?.[2] != null ? plainPct(rv[2]) : "–"}</dd></div>
            <div><dt className="text-xs text-muted">IV rank over the past year (0 = cheapest all year)</dt>
              <dd className="text-lg font-semibold">{ivNow ? `${ivNow.v.toFixed(0)} / 100` : "–"}</dd></div>
            <div className="sm:col-span-2"><dt className="text-xs text-muted">Earnings dates</dt>
              <dd>{t.earnings.length ? t.earnings.map((e) => `${shortDate(e.date)} (${e.time === "premarket" ? "before open" : e.time === "postmarket" ? "after close" : "time not set"})`).join(", ") : "None saved."}</dd></div>
            <div className="sm:col-span-2"><dt className="text-xs text-muted">Dark-pool levels</dt><dd>{t.dp_levels.map((l) => px(l[0])).join(", ") || "none"}</dd></div>
          </dl>
        </More>
      </MoreList></div>
    </div>
  );
}


/** The levels lines under "Price and levels", written from where the price sits right now. Describes, never advises:
 *  walls held no better than ordinary strikes in our study (docs/WALLS-SR.md), so no "support/resistance" claims. */
function levelsRead(p: number | null, g: Gex | null, dp: number | null, live: boolean): React.ReactNode {
  if (!p || (!g && !dp)) return "Price levels worked out from options trading. None saved for this stock yet.";
  const near = (v: number) => Math.abs(v / p - 1) < 0.005;                 // "on the flip": hedging can go either way
  const away = (v: number) => (Math.abs(v / p - 1) < 0.0025 ? "right at the price" : `${(Math.abs(v / p - 1) * 100).toFixed(1)}% ${v > p ? "above" : "below"}`);
  const rows: [string, string][] = [];
  const f = g?.gamma_flip;
  if (f) rows.push(["Gamma", near(f)
    ? `On the gamma flip (${px(f)}): dealers' hedging can switch between leaning against moves and chasing them.`
    : p > f ? `Positive gamma: above the flip (${px(f)}, ${away(f)}). Dealers tend to sell rallies and buy dips, which damps moves.`
      : `Negative gamma: below the flip (${px(f)}, ${away(f)}). Dealers tend to sell drops and buy rallies, which makes moves bigger.`]);
  const call = g?.call_wall, put = g?.put_wall;
  if (call && put && put < p && p < call) rows.push(["Walls", `Between the put wall ${px(put)} (${away(put)}) and the call wall ${px(call)} (${away(call)}).`]);
  else if (call || put) rows.push(["Walls", [
    call ? (p >= call ? `Above the call wall (${px(call)}).` : `Call wall ${px(call)}, ${away(call)}.`) : "",
    put ? (p <= put ? `Below the put wall (${px(put)}).` : `Put wall ${px(put)}, ${away(put)}.`) : ""].filter(Boolean).join(" ")]);
  if (dp) rows.push(["Dark pool", `Most off-exchange volume traded at ${px(dp)}, ${away(dp)}.`]);
  return (
    <span className="block">
      <span className="block font-semibold text-text">{live ? "Now" : "Last close"} {px(p)}. Context, not a buy or sell signal.</span>
      <span className="mt-1 grid grid-cols-[5.5rem_1fr] gap-x-2 gap-y-1">
        {rows.map(([k, v]) => <span key={k} className="contents"><span className="text-text">{k}</span><span>{v}</span></span>)}
      </span>
    </span>
  );
}

/** Distance of the strike, said like Flow check: "6% out", "2% in", "at the money" (the column read "−2%"). */
function otmWords(v: number | null | undefined) {
  if (v == null) return "–";
  const p = Math.round(Math.abs(v) * 100);
  return p === 0 ? "at the money" : `${p}% ${v > 0 ? "out" : "in"}`;
}
