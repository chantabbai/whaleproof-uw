import Link from "next/link";
import CompoundChart, { type CurvePoint } from "@/components/CompoundChart";
import Empty from "@/components/Empty";
import Evidence from "@/components/Evidence";
import { Hero, More, MoreList } from "@/components/v2/ui";
import Sieve from "@/components/Sieve";
import { get, type Funnel, type Holding, type Stats } from "@/lib/api";
import { money, num, pct, plainPct } from "@/lib/format";

type Win = { label?: string; funnel: Funnel & { days: number; per_day: Funnel }; all_directional: Stats; clean: Stats; signals: Stats;
  tiers: Record<string, Stats>; rejected_by_stage: Record<string, Stats>; signals_monthly: ({ month: string } & Stats)[];
  checks: Record<string, { label: string; source: string; with: Stats; without: Stats }>;
  cluster: { days_with_2plus: number; days_with_sector_cluster: number }; meta?: { label: string } };
type SStat = { n: number; mean?: number; median?: number; win_rate?: number; worst?: number };
type Sim = { total_return: number; cagr: number; max_drawdown?: number; trades?: number };
type Compound = { label: string; curve: CurvePoint[]; windows: Record<string, [string, string]>;
  all: Record<string, Sim>; whale: Record<string, Sim>; far_otm: Record<string, Sim>; spy: Record<string, Sim> };
const SIM_ROWS: [string, string][] = [["pre", "Pre-period, Oct 2023 to Sep 2024, out-of-sample"], ["train", "Train, Oct 2024 to Sep 2025, in-sample (rules chosen here)"],
  ["holdout", "Holdout, Oct 2025 to May 2026, out-of-sample"], ["post", "Post-period, Jun to Sep 2026, seen before"], ["all", "All of it, about 2.9 years"]];
type BStat = { n: number; mean: number; ci_low?: number; ci_high?: number };
type BGroup = { x5: BStat; beta_adj: BStat; avg_beta: number };
type Beta = Record<string, Record<string, BGroup> | unknown>;
const BETA_ROWS: [string, string][] = [["pre", "Pre-period, 2023 to 2024, out-of-sample"], ["train", "Train, in-sample"], ["holdout", "Holdout, out-of-sample"], ["post", "Post-period, Jun to Sep 2026, seen"]];
const bg = (b: Beta | null | undefined, w: string, g: string) => ((b?.[w] as Record<string, BGroup> | undefined)?.[g]);
type M = {
  compound?: Compound | null;
  beta?: Beta | null;
  holding?: Holding | null;
  oi_confirm?: { periods: Record<string, { groups: Record<string, OiGroup>; unconfirmed: OiGroup;
    unconfirmed_minus_confirmed: [number, number] | null }> } | null;
  structures: { meta: { note: string; labels: Record<string, string> }; windows: Record<string, Record<string, SStat>> } | null; filter: Record<string, number | string | boolean>; windows: { train: string[]; holdout: string[] };
  evidence: { live?: (Win & { unpriced?: number | null; open?: number | null }) | null; preperiod?: Win | null; preperiod_farotm?: (Win & { tiers: Record<string, { n: number; mean?: number; ci_low?: number; ci_high?: number }>; verdict: string }) | null; train_post: { meta: { filter_hash: string; metric: string; raw_definition: string; generated_at: string }; train: Win; post: Win } | null; holdout: Win | null };
  citations: { key: string; cite: string; supports: string }[] };

const STAGE: Record<string, string> = { gate: "Not a clean opening buy (gate)", direction: "Bearish buys", liquidity: "Stock under $5",
  earnings: "Earnings inside the hold", conviction: "Not big enough" };

export default async function MethodologyDetails() {
  const m = await get<M>("/api/desk/methodology");
  if (!m) return <Empty>The WhaleProof API is not answering. Start it with <code>scripts/desk.sh up</code>, then reload.</Empty>;
  if (!m.evidence.train_post) return <Empty>No evidence file yet. Run <code>uv run whaleproof evidence</code> in backend/.</Empty>;
  const tp = m.evidence.train_post, ho = m.evidence.holdout;
  const pick = (w: (Win & { unpriced?: number | null; open?: number | null }) | null | undefined) => w ? { label: w.label ?? "", funnel: w.funnel, signals: w.signals, all: w.all_directional, clean: w.clean, unpriced: w.unpriced ?? null, open: w.open ?? null } : null;
  // full filter once IV rank was backfilled (docs/PREPERIOD-FAROTM-TEST.md); whale-only first run as fallback
  const pre = m.evidence.preperiod_farotm ?? m.evidence.preperiod ?? null;
  const preFar = m.evidence.preperiod_farotm?.tiers.far_otm;
  const bHo = bg(m.beta, "holdout", "signals"), bPost = bg(m.beta, "post", "signals");
  const avgBeta = m.beta ? BETA_ROWS.map(([w]) => bg(m.beta, w, "signals")?.avg_beta ?? 0).filter(Boolean) : [];
  const betaX = avgBeta.length ? avgBeta.reduce((a, b) => a + b, 0) / avgBeta.length : null;
  const months = [...(pre?.signals_monthly ?? []).map((x) => ({ ...x, w: "pre" })), ...tp.train.signals_monthly.map((x) => ({ ...x, w: "train" })), ...(ho?.signals_monthly ?? []).map((x) => ({ ...x, w: "holdout" })),
    ...tp.post.signals_monthly.map((x) => ({ ...x, w: "post" }))];
  const maxAbs = Math.max(0.01, ...months.map((x) => Math.abs(x.mean ?? 0)));
  const f = m.filter;
  return (
    <div>
      <Hero name="How it works, technical version" eyebrow={<>Part of <Link href="/methodology" className="underline underline-offset-4">How it works</Link></>}
        title={"The technical version, every table."}
        lead="Training window where the rules were chosen, a holdout tested once after they were frozen, a post-period we'd already seen, and an older year opened once. Open any section below." />
      <p className="mt-3 text-[13px] text-muted">{tp.meta.metric}.</p>
      <div className="mt-12 max-w-[80ch]"><MoreList>

      <More title="The noise problem, measured" note={`On an average holdout day, ${num(ho?.funnel.per_day.raw ?? 0)} alerts came down to ${num(ho?.funnel.per_day.signals ?? 0, 1)} signals. Raw means ${tp.meta.raw_definition}.`}>
        {ho && <Sieve f={{ raw: Math.round(ho.funnel.per_day.raw), directional: Math.round(ho.funnel.per_day.directional), clean: Math.round(ho.funnel.per_day.clean), signals: Math.round(ho.funnel.per_day.signals) }}
          average caption={`Averaged over ${ho.funnel.days} holdout sessions, October 2025 to May 2026. In total, ${num(ho.funnel.raw)} alerts became ${num(ho.funnel.signals)} signals.`} />}
      </More>

      <More title="Does the filter help? Four test periods and live trading">
        <Evidence pre={pick(pre)} train={pick(tp.train)} holdout={pick(ho)} post={pick(tp.post)} live={pick(m.evidence.live)} />
        <div className="mt-3 space-y-2 text-sm">
          <p><span className="font-semibold">In plain words.</span> The flow feed is large, about {num(ho?.funnel.per_day.raw ?? 0)} alerts a day. The value is in which ones you act on.
            Taken together, directional alerts averaged about −0.1% against SPY over five days in every window. Filtered signals beat that in training and in the one-time holdout
            ({pct(ho?.signals.mean, 2)} per trade over {num(ho?.signals.n)} signals, {plainPct(ho?.signals.win_rate)} winners, profit factor {num(ho?.signals.profit_factor ?? null, 2)}).
            The holdout&apos;s 95% range for the daily average still touches zero, though ({pct(ho?.signals.ci_low, 2)} to {pct(ho?.signals.ci_high, 2)}, five-day block bootstrap).
            The miss was June to September 2026 ({pct(tp.post.signals.mean, 2)} per trade).
            {bHo && bPost && betaX && <> Signals swing about {betaX.toFixed(1)}× as much as SPY. Adjusted for that beta they still beat all one-way alerts in 3 of 4 windows,
              but the edge shrinks (holdout {pct(bHo.x5.mean, 2)} down to {pct(bHo.beta_adj.mean, 2)}), and beta explains about {Math.round((1 - bPost.beta_adj.mean / bPost.x5.mean) * 100)}% of
              the June to September 2026 loss (table below).</>}
            {pre && preFar && <> A second untouched year, October 2023 to September 2024, was pre-registered and opened once for each tier: the whale tier first, then the
              far-OTM tier once IV-rank history was backfilled. Signals made {pct(pre.signals.mean, 2)} against {pct(pre.all_directional.mean, 2)} for all alerts ({num(pre.signals.n)} signals).
              The far-OTM tier made {pct(preFar.mean, 2)} per trade over {num(preFar.n)} trades, but its 95% range ({pct(preFar.ci_low, 2)} to {pct(preFar.ci_high, 2)}) dips just
              below zero, so the verdict was &ldquo;does not support&rdquo;. The gains are fat-tailed: without the top five trades it&apos;s about +1.1%.</>}
            {" "}The filter beat all one-way alerts in 3 of 4 windows, and the groups it removes (bearish buys, earnings inside the hold) did worse than what it keeps in the same 3 windows.
            Whether what&apos;s left makes money is not proven.</p>
        </div>
      </More>

      {m.beta && <More title="Is it just market beta?" note="An exploratory check, run after the holdout. Beta is the slope of the stock's daily returns against SPY's over the 120 sessions before the flow day, using only what was known then. Beta-adjusted is the five-day return minus beta times SPY's return over the same days, after 0.10% costs. Both columns use the same rows. A few new listings without 20 days of history are left out.">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] text-sm">
            <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-2 pr-4 font-normal">Window</th><th className="px-2 font-normal">Signals&apos; beta</th>
              <th className="px-2 font-normal">Signals, plain (vs SPY)</th><th className="px-2 font-normal">Signals, beta-adjusted (per-day 95% range)</th><th className="px-2 font-normal">All alerts, beta-adjusted</th></tr></thead>
            <tbody>
              {BETA_ROWS.map(([w, label]) => { const s = bg(m.beta, w, "signals"), a = bg(m.beta, w, "all"); return s && (
                <tr key={w} className="border-b border-line">
                  <td className="py-2 pr-4">{label}</td>
                  <td className="px-2">{s.avg_beta.toFixed(2)}×</td>
                  <td className="px-2">{pct(s.x5.mean, 2)}<span className="block text-xs text-muted">{num(s.x5.n)} trades</span></td>
                  <td className={`px-2 font-semibold ${s.beta_adj.mean >= 0 ? "text-bull" : "text-bear"}`}>{s.beta_adj.mean >= 0 ? "▲" : "▼"} {pct(s.beta_adj.mean, 2)}
                    <span className="block text-xs font-normal text-muted">{pct(s.beta_adj.ci_low, 2)} to {pct(s.beta_adj.ci_high, 2)}</span></td>
                  <td className="px-2">{pct(a?.beta_adj.mean, 2)}</td>
                </tr>); })}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-sm"><span className="font-semibold">What it means.</span> Signal stocks are high-beta, so part of the gap over SPY is just market beta. After adjusting,
          signals still lead all one-way alerts in the same 3 of 4 windows, with a smaller edge, and every range includes zero. By tier, far-OTM keeps a positive
          beta-adjusted result in 3 of 4 windows, while the whale tier is mostly beta.</p>
      </More>}

      {m.compound && <More title="If you had traded every signal in stock" note="Exploratory simulation, not a track record. $1 is split into five rotating sleeves. Each day's signals are bought at the next open and sold at the fifth close, equal weight, and a day with no signal stays in cash. 0.10% comes off every trade. No taxes, no extra slippage, no leverage.">
        <CompoundChart data={m.compound.curve} windows={[["Pre", m.compound.windows.pre[0]], ["Train", m.compound.windows.train[0]], ["Holdout", m.compound.windows.holdout[0]], ["Post", m.compound.windows.post[0]]]} />
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-2 pr-4 font-normal">Window</th><th className="px-2 font-normal">Signals (stock)</th>
              <th className="px-2 font-normal">Worst drop</th><th className="px-2 font-normal">Whale only</th><th className="px-2 font-normal">Far-OTM only</th><th className="px-2 font-normal">SPY hold</th></tr></thead>
            <tbody>
              {SIM_ROWS.map(([k, label]) => { const a = m.compound!.all[k]; return a && (
                <tr key={k} className="border-b border-line">
                  <td className="py-2 pr-4">{label}</td>
                  <td className={`px-2 font-semibold ${a.total_return >= 0 ? "text-bull" : "text-bear"}`}>{a.total_return >= 0 ? "▲" : "▼"} {pct(a.total_return, 0)}
                    <span className="block text-xs font-normal text-muted">{num(a.trades ?? 0)} trades</span></td>
                  <td className="px-2">{pct(a.max_drawdown, 0)}</td>
                  <td className="px-2">{pct(m.compound!.whale[k]?.total_return, 0)}</td>
                  <td className="px-2">{pct(m.compound!.far_otm[k]?.total_return, 0)}</td>
                  <td className="px-2">{pct(m.compound!.spy[k]?.total_return, 0)}</td>
                </tr>); })}
            </tbody>
          </table>
        </div>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted">
          <li><span className="font-semibold text-text">Compounding blows up a small, unproven edge.</span> About 50 trades a year per sleeve turn roughly +2% a week into triple digits, while the per-trade 95% ranges above still touch zero.</li>
          <li><span className="font-semibold text-text">It beat SPY in 3 of 4 windows.</span> The miss was June to September 2026 ({pct(m.compound.all.post?.total_return, 0)} while SPY did {pct(m.compound.spy.post?.total_return, 0)}). Signals swing about 2.3× as much as SPY, so a lot of this path is market beta. Per trade, beta-adjusted holdout returns are about 40% of the plain ones. The training year is in-sample, so it flatters.</li>
          <li><span className="font-semibold text-text">High-beta names and a few big winners</span> carry much of it. Worst drops are only marked when trades close, so the real dips were deeper. Paper-trade first.</li>
        </ul>
      </More>}

      <More title="How an alert becomes a signal" note={`Thresholds (frozen, hash ${tp.meta.filter_hash}).`}>
        <ol className="list-decimal space-y-2 pl-5 text-sm">
          <li><span className="font-semibold">Gate: is it a clean opening buy?</span> At least 70% of the premium at the ask. A single leg, not a floor or cross trade. Clearly opening
            (UW&apos;s opening flag, volume above open interest, or size above open interest). Strike between 5% in and 30% out of the money, 7 to 90 days to expiry.
            Common stock, ADR or ETF, but no ETF puts, which are usually hedges. No call and put on the same expiry bought within 15 minutes (a straddle), and no leg sold in the same second (a spread).</li>
          <li><span className="font-semibold">Direction:</span> bullish only{f.longs_only ? "" : " (off)"}. Put buys lost money in training and are mostly hedges.</li>
          <li><span className="font-semibold">Liquidity:</span> the stock is at least ${String(f.min_stock_price)}. UW&apos;s own guidance is that names under $5 fill badly.</li>
          <li><span className="font-semibold">Earnings:</span> no report between the flow and the planned exit, using the report&apos;s date and time. A report before the next morning&apos;s open lands before our entry.</li>
          <li><span className="font-semibold">Conviction:</span> either a <span className="font-semibold">whale-size bet</span>, meaning at least {money(Number(f.whale_premium))} on a strike more than {plainPct(Number(f.whale_min_otm))} out of the money,
            or a <span className="font-semibold">long shot</span>, meaning more than {plainPct(Number(f.far_otm))} out of the money with the option not expensive. Not expensive means IV rank under 70 for the past year, the same yardstick live and in every tested window. The contract&apos;s IV against the stock&apos;s 21-day realized vol is shown for information only.</li>
          <li><span className="font-semibold">One per ticker and direction per day</span>, the largest clean buy. Same-sector signals on one day are flagged as a cluster rather than counted as separate bets.
            In training, {tp.train.cluster.days_with_sector_cluster} of {tp.train.cluster.days_with_2plus} days with more than one signal had a sector cluster.</li>
        </ol>
      </More>

      <More title="What each filtered-out group did" note="Holdout, same measure. A filter step earns its place if the group it removes did worse than what it keeps.">
        <table className="w-full text-sm">
          <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-1.5 font-normal">Removed at</th><th className="font-normal">Alerts</th><th className="font-normal">Average five days vs SPY</th><th className="font-normal">Winners</th></tr></thead>
          <tbody>
            {Object.entries(ho?.rejected_by_stage ?? {}).map(([k, v]) => (
              <tr key={k} className="border-b border-line"><td className="py-1.5">{STAGE[k] ?? k}</td><td>{num(v.n)}</td><td className={(v.mean ?? 0) >= 0 ? "text-bull" : "text-bear"}>{pct(v.mean, 2)}</td><td>{plainPct(v.win_rate)}</td></tr>))}
            {ho && Object.entries(ho.tiers).map(([k, v]) => (
              <tr key={k} className="border-b border-line font-semibold"><td className="py-1.5"><span className="mark">Kept: {k === "whale" ? "whale-size bets" : "long shots"}</span></td><td>{num(v.n)}</td><td className={(v.mean ?? 0) >= 0 ? "text-bull" : "text-bear"}>{pct(v.mean, 2)}</td><td>{plainPct(v.win_rate)}</td></tr>))}
          </tbody>
        </table>
      </More>

      <More title="Research behind each check, and what our data said" note="Each check tested alone on clean buys, with and without it, in training and then the holdout. A check can help only in combination: far-OTM alone is negative, but far-OTM plus bullish plus a fair price is the tier we kept.">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[780px] text-sm">
            <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-1.5 font-normal">Check</th><th className="font-normal">Train: with / without</th><th className="font-normal">Holdout: with / without</th><th className="font-normal">Pre-period: with / without</th><th className="font-normal">Basis</th></tr></thead>
            <tbody>{Object.entries(tp.train.checks).map(([k, c]) => {
              const h = ho?.checks[k];
              return (
                <tr key={k} className="border-b border-line align-top">
                  <td className="py-1.5 pr-2 font-semibold">{c.label}</td>
                  <td className="pr-2">{pct(c.with.mean, 2)} / {pct(c.without.mean, 2)}<span className="block text-xs text-muted">{num(c.with.n)} / {num(c.without.n)} trades</span></td>
                  <td className="pr-2">{h ? <>{pct(h.with.mean, 2)} / {pct(h.without.mean, 2)}<span className="block text-xs text-muted">{num(h.with.n)} / {num(h.without.n)} trades</span></> : "–"}</td>
                  <td className="pr-2">{pre?.checks[k] ? <>{pct(pre.checks[k].with.mean, 2)} / {pct(pre.checks[k].without.mean, 2)}<span className="block text-xs text-muted">{num(pre.checks[k].with.n)} / {num(pre.checks[k].without.n)} trades</span></> : "–"}</td>
                  <td className="text-xs text-muted">{c.source}</td>
                </tr>);
            })}</tbody>
          </table>
        </div>
        <ul className="mt-4 space-y-2 text-sm">
          {m.citations.map((c) => <li key={c.key}><span className="text-muted">{c.cite}</span><span className="block">{c.supports}</span></li>)}
        </ul>
      </More>

      <More title="Signals month by month" note="Average five-day return against SPY per signal. Pre-period and holdout months were never seen before their single test run (the pre-period used the full filter after the IV-rank backfill). Train months are in-sample, and post-period months had been seen. Solid bars are the sealed months.">
        <div className="py-1">
          <ul className="space-y-1 text-xs">
            {months.map((x) => (
              <li key={x.month} className="grid grid-cols-[4.5rem_4.5rem_1fr_4rem] items-center gap-2">
                <span>{monthName(x.month)}</span><span className="text-muted">{x.w}</span>
                <span className="relative h-2.5 rounded-sm bg-panel2">
                  <span className="absolute top-0 h-2.5 rounded-sm" style={{ left: (x.mean ?? 0) >= 0 ? "50%" : `${50 - (Math.abs(x.mean ?? 0) / maxAbs) * 50}%`, width: `${(Math.abs(x.mean ?? 0) / maxAbs) * 50}%`, background: (x.mean ?? 0) >= 0 ? "var(--bull)" : "var(--bear)", opacity: x.w === "holdout" || x.w === "pre" ? 1 : 0.6 }} />
                </span>
                <span className={(x.mean ?? 0) >= 0 ? "text-bull" : "text-bear"}>{(x.mean ?? 0) >= 0 ? "▲" : "▼"}{pct(x.mean, 1)} <span className="text-muted">({x.n})</span></span>
              </li>))}
          </ul>
        </div>
      </More>

      {m.structures && (
        <More title="Stock or options? How to trade a bullish signal" note={<>Same signals, same five-session hold. Every row uses real prices: stock bars, and UW&apos;s daily history for every option leg
          (7,758 contracts fetched on Sep 30), including the whale&apos;s own contract. Returns are on capital at risk. A few near-zero-risk spreads distort the
          bull put spread&apos;s average, so read its median.</>}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] text-sm">
              <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="font-normal">How</th>
                {["train", "holdout", "post"].map((w) => <th key={w} className="font-normal">{w === "post" ? "Jun to Sep 2026" : w === "train" ? "Train" : "Holdout"} (median, mean, winners, worst)</th>)}</tr></thead>
              <tbody>{["stock", "real_long_call", "real_short_put", "real_call_atm_60d", "real_call_itm10_60d", "real_call_spread", "real_put_spread"].map((k) => (
                <tr key={k} className="border-b border-line align-top">
                  <td className="py-1.5 pr-2 font-semibold">{k === "stock" ? "Buy the stock" : k === "real_long_call" ? "Buy the whale's call" : `${m.structures!.meta.labels[k.replace("real_", "")]}`} <span className="text-xs font-normal text-muted">(real prices)</span></td>
                  {["train", "holdout", "post"].map((w) => {
                    const x = m.structures!.windows[w]?.[k];
                    return <td key={w} className="pr-2">{x && x.n ? <><span className={(x.median ?? 0) >= 0 ? "text-bull" : "text-bear"}>{pct(x.median)}</span>, {pct(x.mean)}, {plainPct(x.win_rate)}, {pct(x.worst, 0)}<span className="block text-xs text-muted">{x.n} trades</span></> : "–"}</td>;
                  })}
                </tr>))}</tbody>
            </table>
          </div>
          <p className="mt-2 text-sm"><span className="font-semibold">What it means.</span> The best way to act on a signal is the stock. On real prices nothing beat it. Buying options (the whale&apos;s,
            or our own 60-day at-the-money and 10% in-the-money calls) lost on the typical trade, and call and put spreads lost too. Selling a 5% out-of-the-money put
            was about breakeven: a median of +0.6% to +0.8% of the cash set aside, an average near 0%, 59% to 64% winners, and a loss from June to September 2026.
            Returns are on capital at risk, meaning the debit paid, the max loss on a credit spread, or the cash that secures the short put.</p>
        </More>
      )}

      {m.holding && <More title="Holding period: 5, 10, 20 or 30 sessions?" note="Exploratory, run after the holdout. Same signals, with the stock bought at the next open and sold at the close of session H. The return is in the signal's direction minus SPY over the same days, after 0.10% costs (H = 5 matches the main results exactly). Only trades with 30 sessions of later prices count, so every H uses the same trades. The 95% range is a block bootstrap of daily means with block length H.">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-2 pr-4 font-normal">Window</th><th className="px-2 font-normal">Hold</th>
              <th className="px-2 font-normal">Trades</th><th className="px-2 font-normal">Average per trade</th><th className="px-2 font-normal">Per session held</th>
              <th className="px-2 font-normal">Winners</th><th className="px-2 font-normal">95% range (day mean)</th><th className="px-2 font-normal">All alerts</th>
              <th className="px-2 font-normal">Earnings inside</th></tr></thead>
            <tbody>
              {Object.entries(m.holding.periods).flatMap(([k, p]) => m.holding!.horizons.map((H, i) => { const c = p.by_horizon[String(H)], s = c?.signals; return s?.trades ? (
                <tr key={`${k}${H}`} className={`border-b border-line ${H === 5 ? "font-semibold" : ""}`}>
                  <td className="py-1.5 pr-4">{i === 0 ? p.name : ""}</td><td className="px-2">{H}</td><td className="px-2">{num(s.trades)}</td>
                  <td className={`px-2 ${(s.avg_per_trade ?? 0) >= 0 ? "text-bull" : "text-bear"}`}>{pct(s.avg_per_trade, 2)}</td>
                  <td className="px-2">{pct(s.avg_per_session_held, 2)}</td><td className="px-2">{plainPct(s.win_rate)}</td>
                  <td className="px-2">{s.range95_day_mean?.[0] == null ? "too few days" : `${pct(s.range95_day_mean[0], 2)} to ${pct(s.range95_day_mean[1], 2)}`}</td>
                  <td className="px-2">{pct(c.every_alert.avg_per_trade, 2)}</td><td className="px-2">{plainPct(c.share_with_earnings_inside)}</td>
                </tr>) : null; }))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-sm"><span className="font-semibold">What it means.</span> Longer holds earn more per trade but less per session held, the range gets three
          to five times wider, and 20% to 41% of 20 and 30-session holds run through an earnings report (the filter only blocks earnings inside five sessions). In
          training, 5 and 10 tie, and only those ranges stay clear of zero. In the holdout, 10 is weaker per session. So we kept five sessions. This isn&apos;t
          beta-adjusted, so long holds of high-beta names look better in rising markets. Recent signals without 30 later sessions are left out.</p>
      </More>}

      {m.oi_confirm && <OiSection o={m.oi_confirm} />}
      <More title="Caveats">
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li>Signals are filtered observations, not recommendations. Not financial advice.</li>
          <li>Results are on the stock, not options. Long calls lost on the typical trade at normal fills. A wrong-way move cost about 58%, and about one in three still lost when the stock went the right way, to the spread and time decay.</li>
          <li>Signal stocks are high-beta, about 2.1 to 2.4× SPY. Beta-adjusted, the edge shrinks but stays positive in 3 of 4 windows. The whale tier alone is mostly beta.</li>
          <li>Samples are modest: hundreds of signals and about 150 to 250 trading days per window. Same-day signals cluster by sector.</li>
          <li>&ldquo;Raw&rdquo; only counts UW flow alerts with at least $100K in premium. The cache and the live pull use the same floor, so the UW website shows more.</li>
          <li>Earnings dates can move, and history only keeps the final date, so the backtested earnings block is slightly optimistic.</li>
          <li>The holdout was run {m.evidence.holdout ? "once" : "not yet"}. Any change to the filter after that makes later results exploratory.</li>
        </ul>
      </More>
      </MoreList></div>
    </div>
  );
}

type OiGroup = { trades: number; mean_vs_spy: number | null; beat_spy: number | null; range: [number, number] | null };
const OI_ORDER = ["Practice year (rules chosen here)", "Sealed test", "Recent months", "All periods"];
// research JSONs written before 10-07 key the last window by its old name
const OI_LEGACY: Record<string, string> = { "Recent months": "Recent months (seen before testing)" };
/** The same months every other period table on this page names (the research file keeps the short names). */
const OI_SHOWN: Record<string, string> = { "Practice year (rules chosen here)": "Practice year · Oct 2024 – Sep 2025 (rules chosen here)", "Sealed test": "Sealed test · Oct 2025 – May 2026", "Recent months": "Recent months · Jun – Sep 2026" };
const oiPeriod = (o: { periods: Record<string, { groups: Record<string, OiGroup> }> }, k: string) => o.periods[k] ?? o.periods[OI_LEGACY[k]];
const OI_ROWS: [string, string][] = [["confirmed", "Grew by at least half the whale's size"], ["weak", "Grew, but by less"],
  ["fell", "Went down"], ["unknown", "No open interest in our data"]];

/** Next-morning open interest vs the five-day result (exploratory, scripts/research/oi_confirm.py). */
function OiSection({ o }: { o: NonNullable<M["oi_confirm"]> }) {
  return (
    <More id="oi" title="Does it matter if open interest didn't grow?" note="Exploratory, run Oct 5, 2026, after the tests. The morning after the flow, UW publishes the contract's open interest. If the whale opened a new position it should grow by about the whale's size; if it didn't, the trade may have been a close. The filter never used this. Result is the stock trade against SPY, five sessions, after 0.10% costs. The 95% range resamples whole days.">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-2 pr-4 font-normal">Window</th><th className="px-2 font-normal">Open interest next morning</th>
            <th className="px-2 font-normal">Trades</th><th className="px-2 font-normal">Average vs SPY</th><th className="px-2 font-normal">Beat SPY</th><th className="px-2 font-normal">95% range</th></tr></thead>
          <tbody>
            {OI_ORDER.filter((k) => oiPeriod(o, k)).flatMap((k) => OI_ROWS.map(([g, label], i) => { const s = oiPeriod(o, k).groups[g]; return s?.trades ? (
              <tr key={k + g} className="border-b border-line">
                <td className="py-1.5 pr-4">{i === 0 ? OI_SHOWN[k] ?? k : ""}</td><td className="px-2">{label}</td><td className="px-2">{num(s.trades)}</td>
                <td className={`px-2 ${(s.mean_vs_spy ?? 0) >= 0 ? "text-bull" : "text-bear"}`}>{pct(s.mean_vs_spy, 2)}</td>
                <td className="px-2">{plainPct(s.beat_spy)}</td>
                <td className="whitespace-nowrap px-2">{s.range ? `${pct(s.range[0], 2)} to ${pct(s.range[1], 2)}` : "too few days"}</td>
              </tr>) : null; }))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-sm"><span className="font-semibold">What it means.</span> Almost every signal&apos;s open interest grew as expected. Only {o.periods["All periods"]?.unconfirmed.trades ?? "–"} didn&apos;t,
        and they did about the same as the rest (difference range {(() => { const r = o.periods["All periods"]?.unconfirmed_minus_confirmed; return r ? `${pct(r[0], 1)} to ${pct(r[1], 1)}` : "–"; })()}).
        The ones where it went down did better, not worse, but there are too few to trust that. So it stays a note on the card, not a filter. The second sealed test has no open interest
        in our data. Not proven either way.</p>
    </More>
  );
}

/** "2023-11" → "Nov 2023". */
function monthName(ym: string) {
  return new Date(`${ym}-15T12:00:00`).toLocaleDateString("en-US", { month: "short", year: "numeric" });
}
