import Link from "next/link";
import AutoRefresh from "@/components/AutoRefresh";
import Empty from "@/components/Empty";
import EvidenceBadge from "@/components/v2/EvidenceBadge";
import SignalCard from "@/components/SignalCard";
import ComingUp, { type EarnNext } from "@/components/v2/ComingUp";
import Haystack from "@/components/v2/Haystack";
import HoldGrid from "@/components/v2/HoldGrid";
import HoldTape from "@/components/v2/HoldTape";
import SignalPanelProvider from "@/components/v2/SignalPanel";
import { Eyebrow, H2, More, Tile, Tiles } from "@/components/v2/ui";
import SignalTile from "@/components/v2/SignalTile";
import { BEARISH_NOTE } from "@/lib/copy";
import { get, type EarnWarn, type EvWindow, type Funnel, type Gex, type Rejected, type Signal, type Spot } from "@/lib/api";
import { etTime, money, num, pct, plainPct, px, shortDate, arrowPct, moveTone, plural } from "@/lib/format";
import { watchSet } from "@/lib/watch";

type Today = {
  day: string; funnel: Funnel | null; signals: Signal[]; active: Signal[]; bearish: Signal[]; forming: boolean; entering: Signal[];
  rejected_top: Rejected[]; latest: { day: string; tickers: string[] } | null;
  surfacing?: { first_seen: Record<string, string>; went_under: Under[] };
  regime: { gamma: { positive: boolean; spot: number; flip: number; date: string } | null; gex: Record<string, Gex>; spot: Record<string, Spot | null>;
    spy_today?: { today_move: number | null; today_day: string | null } };
  events: { calendar: { et: string; event: string; forecast: string | null; prev: string | null }[];
    earnings: Record<string, { ticker: string; expected_move_perc: number | null; marketcap?: number | null }[]>; earnings_day?: string };
  evidence: { pre: EvWindow; train: EvWindow; holdout: EvWindow; post: EvWindow; filter_hash: string } | null;
};
type Under = { ticker: string; direction: number; tier: string | null; premium: number | null; first_seen: string; went_under: string; reason: string };
type Swing = { signals: Signal[]; earnings_watch: ({ ticker: string } & EarnWarn)[]; earnings_next?: EarnNext };


/** Sightings, the home page (v2 owner 10-05; renamed from Today 10-06): one job — what to look at — and everything else one click deeper. */
export default async function TodayV2() {
  const [t, sw, watch] = await Promise.all([get<Today>("/api/desk/today"), get<Swing>("/api/desk/swing"), watchSet()]);
  if (!t) return <Empty>The WhaleProof API is not answering. Start it with <code>scripts/desk.sh up</code>, then reload.</Empty>;
  const rich = new Map((sw?.signals ?? []).map((s) => [s.id, s]));
  const pick = (s: Signal) => rich.get(s.id) ?? s;
  const signals = t.signals.map(pick);
  // only what's drawn as a card above leaves the hold list. While today forms, the cards are today's surfacing signals
  // and last session's signals (bought at this morning's open) sit in the hold list as day 1 (owner 10-07)
  const shown = new Set(signals.map((s) => s.id));
  const holding = (sw?.signals ?? t.active).filter((s) => !shown.has(s.id));
  const main = signals;
  const under = t.forming ? t.surfacing?.went_under ?? [] : [];
  const seen = t.surfacing?.first_seen ?? {};
  const ho = t.evidence?.holdout;
  const f = t.funnel;
  const openUp = holding.filter((s) => (s.since_entry ?? 0) > 0).length;
  const openDown = holding.filter((s) => (s.since_entry ?? 0) < 0).length;   // not priced yet (before the entry open) = neither
  const nextExit = holding.map((s) => s.exit_by).sort()[0];      // the headline already counts new signals (trader review)
  const selling = holding.filter((s) => s.exit_by === nextExit);
  const g = t.regime.gamma;
  const earnAhead = sw?.earnings_watch ?? [];

  return (
    <SignalPanelProvider watch={[...watch]}><div>
      <AutoRefresh seconds={60} />
      <Eyebrow>{longDay(t.day)}{t.forming ? ", still forming until 4:15 PM ET" : ""}</Eyebrow>
      <HoldTape holds={holding} spy={t.regime.spy_today} live={holding.some((s) => s.price_source === "live")} pageDay={t.day} />

      {f && f.raw > 0 ? <section className="mt-3">
        <h1 className="text-[40px] leading-[1.05] md:text-[56px]"><span className="sr-only">Sightings: </span>
          {plural(f.raw, "alert")}. <span className="mark">{num(signals.length)}</span> worth a look.
        </h1>
        <div className="mt-8"><Haystack f={f} day={t.day} tickers={[...new Set(signals.map((s) => s.ticker))]} /></div>
      </section> : <h1 className="mt-3 text-[40px] leading-[1.05] md:text-[56px]"><span className="sr-only">Sightings: </span>No flow saved for {shortDate(t.day)} yet.</h1>}

      <div className="mt-12"><Tiles cols={3}>
        <Tile k="Selling next" v={nextExit ? shortDate(nextExit) : "–"} accent="amber"
          sub={nextExit ? <span className="flex flex-wrap items-center gap-1.5">
            {selling.map((s) => <Link key={s.id} href={`/ticker/${s.ticker}`} className="rounded-full border border-amber/50 px-2 py-0.5 text-xs font-medium text-amber hover:border-amber">{s.ticker}</Link>)}
            <span>at the close</span></span> : "Nothing in its hold."} />
        <Tile k="Riding with the whales" v={num(holding.length)} accent="sea"
          sub={holding.length > 0 ? <span aria-label={`${openUp} up and ${openDown} down since entry`}>
            <span aria-hidden className="mt-1 flex h-1 gap-0.5 overflow-hidden rounded-full">
              {openUp > 0 && <span className="bg-bull opacity-70" style={{ flex: openUp }} />}
              {openDown > 0 && <span className="bg-bear opacity-70" style={{ flex: openDown }} />}</span>
            <span aria-hidden className="mt-1.5 flex justify-between"><span className="text-bull">{openUp} up</span><span className="text-bear">{openDown} down</span></span>
          </span> : "Nothing in its hold."} />
        <Tile k="Sealed test, average trade vs the S&P" v={ho ? pct(ho.signals.mean, 2) : "–"} sub={ho ? `${num(ho.signals.n)} trades, ${plainPct(ho.signals.win_rate)} won` : ""}
          href="/tracker" tone={(ho?.signals.mean ?? 0) >= 0 ? "bull" : "bear"} accent="brass" />
      </Tiles></div>
      <div className="mt-4"><EvidenceBadge /></div>

      <div className="mt-14 grid gap-x-12 gap-y-14 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-14">
          {/* 3 · Signals */}
          <section>
            <H2 wave>{t.forming ? "Surfacing today" : `Surfaced on ${shortDate(t.day)}`}</H2>
            <p className="mt-1 text-sm text-muted">{t.forming
              ? "Whale bets passing every check so far today. Nothing is final until 4:15 PM ET, and the rule buys at the next open, so these are to watch, not buy yet."
              : "Sightings: the whale bets that passed every check. Each one is a signal with one rule: buy the stock at the next open, sell at the close of the fifth trading day."}</p>
            {main.length === 0 ? <div className="mt-4"><Empty>{t.forming ? "Nothing has surfaced yet today." : "No new signals. The filter is built to say no, and most days it does."}
              {t.latest && <> Latest signals: <b className="text-text">{shortDate(t.latest.day)}</b>, {t.latest.tickers.map((x, i) => <span key={x}>{i ? ", " : ""}<Link href={`/ticker/${x}`} className="font-semibold text-text underline-offset-4 hover:underline">{x}</Link></span>)}.
                {" "}<Link href="/tracker" className="underline underline-offset-4">Track record</Link></>}</Empty></div>
              : <div className="mt-5 grid gap-4 sm:grid-cols-2">{main.map((s) => <SignalTile key={s.id} s={s} group={main} watching={watch.has(s.ticker)}
                  surfacedAt={t.forming ? seen[`${s.ticker}:${s.direction}`] ?? null : undefined} />)}</div>}
            {under.length > 0 && <div className="mt-6" data-testid="went-under">
              <h3 className="text-sm font-semibold">Went back under ({under.length})</h3>
              <p className="text-xs text-muted">Passed every check earlier today, then stopped passing.</p>
              <ul className="mt-2 divide-y divide-line text-sm">{under.map((u) => (
                <li key={`${u.ticker}:${u.direction}`} className="flex flex-wrap gap-x-3 py-1.5">
                  <Link href={`/ticker/${u.ticker}`} className="w-14 font-semibold">{u.ticker}</Link>
                  <span className="text-muted">surfaced {etTime(u.first_seen)}, under at {etTime(u.went_under)}</span>
                  <span className="flex-1">{u.reason}</span></li>))}</ul>
            </div>}
          </section>

          {/* 4 · Open */}
          <section>
            <H2 wave>Riding with the whales</H2>
            <p className="mt-1 text-sm text-muted">Price move since the entry open: live while the market is open, the closing price after that (same as Track record). Tap one for its card.</p>
            <div className="mt-5">{holding.length === 0 ? <Empty>Nothing open.</Empty> : <HoldGrid signals={holding} watch={[...watch]} />}</div>
          </section>
        </div>

        {/* 5 · Market, glanceable */}
        <aside className="min-w-0">
          <div className="rounded-md bg-panel2 p-5">
            <span aria-hidden className="-mx-5 -mt-5 mb-4 block h-0.5 rounded-t-md bg-sea opacity-80" />
            <H2 wave>Market</H2>
            {/* gamma isn't direction: no ▲▼ or up/down colours; calm accents instead (amber = moves run, sea = damped) */}
            {g && <p className={`mt-3 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm font-semibold ${g.positive ? "border-sea/40 text-sea" : "border-amber/40 text-amber"}`}
              title={g.positive ? "SPY above its gamma flip: dealer hedging tends to sell rallies and buy dips" : "SPY below its gamma flip: dealer hedging tends to sell drops and buy rallies"}>
              <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${g.positive ? "bg-sea" : "bg-amber"}`} />
              {g.positive ? "Positive gamma: moves tend to be damped" : "Negative gamma: moves tend to run"}</p>}
            <ul className="mt-4 space-y-2 text-sm">
              {["SPY", "QQQ", "IWM"].map((k) => {
                const s = t.regime.spot[k], ch = s?.last && s.prev_close ? s.last / s.prev_close - 1 : null;
                return <li key={k} className="flex items-baseline justify-between">
                  <Link href={`/ticker/${k}`} className="font-semibold hover:underline">{k}</Link>
                  <span>{px(s?.last)} <span className={`ml-1 ${moveTone(ch, 2)}`}>{ch == null ? "" : arrowPct(ch, 2)}</span></span>
                </li>;
              })}
            </ul>
            <Link href="/market" className="mt-4 inline-block text-sm underline underline-offset-4">Full market view</Link>
          </div>

          <ComingUp ahead={earnAhead} next={sw?.earnings_next ?? null} releases={t.events.calendar}
            today={{ premarket: t.events.earnings.premarket ?? [], afterhours: t.events.earnings.afterhours ?? [] }} day={t.events.earnings_day} />
        </aside>
      </div>

      {/* 6 · One click deeper */}
      <section className="mt-16 border-t border-line">
        <More title={<span>Bearish bets to watch <span className="ml-1 text-[13px] font-medium text-bear" aria-label={`(${t.bearish.length})`}>{t.bearish.length}</span></span>} note={BEARISH_NOTE}>
          {t.bearish.map((s) => <SignalCard key={s.id} s={s} watching={watch.has(s.ticker)} />)}
        </More>
        <More title={<span>Biggest alerts that got cut <span className="ml-1 text-[13px] font-medium text-muted" aria-label={`(${t.rejected_top.length})`}>{t.rejected_top.length}</span></span>} note="What the raw feed shouted loudest about, and why each one failed.">
          <ul className="divide-y divide-line text-sm">{t.rejected_top.map((r, i) => (
            <li key={i} className="flex flex-wrap gap-x-4 py-2"><Link href={`/ticker/${r.ticker}`} className="w-14 font-semibold">{r.ticker}</Link>
              <span className="w-16">{money(r.premium)}</span><span className="flex-1 text-muted">{r.reason}</span></li>))}</ul>
        </More>
      </section>
    </div></SignalPanelProvider>
  );
}

function longDay(iso: string) {
  return new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
}
