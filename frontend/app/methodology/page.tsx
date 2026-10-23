import Link from "next/link";
import CompoundChart, { type CurvePoint } from "@/components/CompoundChart";
import Empty from "@/components/Empty";
import { Block, Hero, More, MoreList, Tile, Tiles } from "@/components/v2/ui";
import Sieve from "@/components/Sieve";
import { get, type Funnel, type Holding, type Stats } from "@/lib/api";
import { num, pct, plainPct } from "@/lib/format";

/** Plain-English, visual-first methodology for a general audience. Every number is read from the evidence files except
 *  the "What we tried" ladder, which summarises the practice-year studies (docs/analysis-train-simple.md,
 *  docs/analysis-train-combos.md). The full technical page lives at /methodology/details. */

type Win = { funnel: Funnel & { days: number; per_day: Funnel }; all_directional: Stats; signals: Stats; tiers: Record<string, Stats> };
type BGroup = { x5: { mean: number; n: number }; beta_adj: { mean: number }; avg_beta: number };
type Sim = { total_return: number; max_drawdown?: number; trades?: number };
type M = {
  evidence: { preperiod_farotm?: Win | null; preperiod?: Win | null; train_post: { meta: { filter_hash: string }; train: Win; post: Win } | null; holdout: Win | null };
  beta?: Record<string, Record<string, BGroup> | unknown> | null;
  holding?: Holding | null;
  compound?: { curve: CurvePoint[]; windows: Record<string, [string, string]>; all: Record<string, Sim>; whale: Record<string, Sim>;
    far_otm: Record<string, Sim>; spy: Record<string, Sim> } | null;
};

type Period = { key: string; name: string; when: string; role: string; tone: "exam" | "practice" | "seen"; w: Win | null | undefined };

export default async function Methodology() {
  const m = await get<M>("/api/desk/methodology");
  if (!m) return <Empty>The WhaleProof API is not answering. Start it with <code>scripts/desk.sh up</code>, then reload.</Empty>;
  if (!m.evidence.train_post) return <Empty>No evidence file yet. Run <code>uv run whaleproof evidence</code> in backend/.</Empty>;
  const tp = m.evidence.train_post, ho = m.evidence.holdout;
  const pre = m.evidence.preperiod_farotm ?? m.evidence.preperiod;
  const periods: Period[] = [
    { key: "pre", name: "Second sealed test", when: "Oct 2023 to Sep 2024", role: "An older year nobody had looked at. Opened once.", tone: "exam", w: pre },
    { key: "train", name: "Practice year", when: "Oct 2024 to Sep 2025", role: "Where the rules were picked, so expect it to look best.", tone: "practice", w: tp.train },
    { key: "holdout", name: "Sealed test", when: "Oct 2025 to May 2026", role: "Rules locked first, then opened once. This is the main exam.", tone: "exam", w: ho },
    { key: "post", name: "Recent months", when: "Jun to Sep 2026", role: "We'd already seen these, so it's a report, not a test.", tone: "seen", w: tp.post },
  ];
  const beta = (k: string) => (m.beta?.[k] as Record<string, BGroup> | undefined)?.signals;
  const wins = periods.filter((p) => p.w && p.w.signals.mean != null && p.w.all_directional.mean != null && p.w.signals.mean > p.w.all_directional.mean);
  const betas = periods.map((p) => beta(p.key)?.avg_beta).filter((x): x is number => !!x);
  const betaX = betas.length ? betas.reduce((a, b) => a + b, 0) / betas.length : null;
  const maxAbs = Math.max(0.005, ...periods.flatMap((p) => [p.w?.signals.mean ?? 0, p.w?.all_directional.mean ?? 0, beta(p.key)?.beta_adj.mean ?? 0].map(Math.abs)));

  return (
    <div>
      <Hero name="How it works" eyebrow="How it works, in plain English"
        title={<>{num(ho?.funnel.per_day.raw ?? 0)} alerts a day. {num(ho?.funnel.per_day.signals ?? 0, 0)} signals. Ahead of the rest in {wins.length} of {periods.length} periods.</>}
        lead={<>Unusual Whales flow carries real information, mixed in with hedges and closing trades. We took those out, tested what was left on three years of history with the rules locked first, and show where it fails. Every table is in the <Link href="/methodology/details" className="underline">technical version</Link>.</>} />

      <div className="mt-10"><Tiles>
        <Tile accent="sea" k="Alerts a day, cut to signals" v={`${num(ho?.funnel.per_day.raw ?? 0)} → ${num(ho?.funnel.per_day.signals ?? 0, 0)}`} sub="sealed test averages" />
        <Tile accent="amber" k="Our shortlist added an edge" v={`${wins.length} of ${periods.length}`} sub="test periods, both sealed tests included" tone="bull" />
        <Tile accent="amber" k="How much they swing vs the S&P 500" v={betaX ? `${betaX.toFixed(1)}×` : "–"} sub={betaX ? `signal stocks move ${betaX.toFixed(1)}× as much; part of the gain is that extra risk` : ""} />
        <Tile accent="brass" k="Verdict" v="Promising" sub="Not proven yet. Paper-trade first." />
      </Tiles></div>

      <div className="mt-14 max-w-[80ch] space-y-14">
        <Block wave title="1. Throw out the noise" sub="Most big option trades aren't bets on direction: hedges, closing trades, halves of spreads, premium selling. Those go first.">
        {ho && <Sieve f={{ raw: Math.round(ho.funnel.per_day.raw), directional: Math.round(ho.funnel.per_day.directional), clean: Math.round(ho.funnel.per_day.clean), signals: Math.round(ho.funnel.per_day.signals) }}
          average bare caption="Averages from the sealed test, October 2025 to May 2026." />}
        <div className="mt-6 grid gap-x-8 gap-y-1 text-sm sm:grid-cols-2">
          <Rule ok text="Bought at the ask, a single option, clearly a new position" />
          <Rule ok text="Bullish only (call buys). Put buys lost money and are mostly hedges" />
          <Rule ok text="Stock price $5 or more, so it's easy to trade" />
          <Rule ok text="No earnings before we'd sell, since earnings jumps are a coin flip" />
        </div>
        </Block>

        <Block wave title="2. Test it fairly" sub="Rules locked before opening the sealed tests, like sealing your answers before seeing the answer key. The locked rules have a fingerprint (a code hash), so any later change would show.">
        <div className="grid grid-cols-2 gap-x-4 gap-y-4 text-xs sm:grid-cols-4">
          {periods.map((p) => (
            <div key={p.key} className={`border-t-[3px] pt-2 ${p.tone === "exam" ? "border-text" : p.tone === "practice" ? "border-muted" : "border-dashed border-line"}`}>
              <div className="text-sm font-semibold">{p.name}</div>
              <div className="text-muted">{p.when}</div>
              <div className="mt-1 text-muted">{p.tone === "exam" ? "Sealed, opened once" : p.tone === "practice" ? "Practice" : "Already seen"}</div>
            </div>))}
        </div>
        <p className="mt-2 text-xs text-muted">Oldest to newest.</p>
        <div className="mt-6 grid gap-x-8 gap-y-1 text-sm sm:grid-cols-2">
          <Rule ok text="Only what was known on the day. No peeking at what happened next" />
          <Rule ok text="Buy at the next morning's open, sell at the close of the fifth trading day" />
          <Rule ok text="Trading costs come off every trade" />
          <Rule ok text="Compared with all UW alerts and with the S&P 500" />
          <Rule ok text="The exact same code runs live and in the tests" />
          <Rule ok text="Checked again with the effect of jumpy stocks taken out" />
        </div>
        </Block>

        <Block wave id="results" title="3. Results" sub="Per trade over five days, against the S&P 500 over the same days, after costs. Right of the line beat the market.">
        <div className="border-t border-line">
          {periods.map((p) => p.w && (
            <div key={p.key} className="border-b border-line py-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div><span className="font-semibold">{p.name}</span> <span className="text-sm text-muted">{p.when}</span></div>
                {p.w.signals.mean != null && p.w.all_directional.mean != null && (p.w.signals.mean > p.w.all_directional.mean
                  ? <span className="text-xs font-semibold text-bull">✓ added an edge</span>
                  : <span className="text-xs font-semibold text-bear">✗ no edge</span>)}
              </div>
              <p className="text-xs text-muted">{p.role}</p>
              <div className="mt-2 space-y-1.5">
                <BarRow label="All UW alerts" v={p.w.all_directional.mean} max={maxAbs} tone="muted" />
                <BarRow label={`Our shortlist, ${num(p.w.signals.n)} trades`} v={p.w.signals.mean} max={maxAbs} tone="brass" />
                {beta(p.key) && <BarRow label="Our shortlist, risk-adjusted" v={beta(p.key)!.beta_adj.mean} max={maxAbs} tone="outline" />}
              </div>
            </div>))}
        </div>
        <p className="mt-4 text-sm">Our shortlist added an edge over all UW alerts in {wins.length} of {periods.length} periods, including both sealed tests. The exception was the
          most recent months. Signal stocks move about {betaX ? betaX.toFixed(1) : "2"}× as much as the market, so we took that out too. The gain shrinks but stays ahead in
          the same periods. The alerts it throws out (put buys, earnings inside the hold) also did worse than the ones it keeps in those periods.</p>
        </Block>

        <Block wave title="4. How to act on a signal">
        <div className="grid gap-x-10 gap-y-6 sm:grid-cols-2">
          <div className="border-t-[3px] border-text pt-3">
            <div className="text-[17px] font-semibold">Buy the stock</div>
            <p className="mt-1 text-sm">That&apos;s what we tested. The edge is small, nothing expires, and a bad week usually costs a few percent rather than the whole position.</p>
          </div>
          <div className="border-t-[3px] border-dashed border-line pt-3">
            <div className="text-[17px] font-semibold">The whale&apos;s own option is harder to profit from</div>
            <p className="mt-1 text-sm">The stock captured the move the flow pointed to. The typical copied call lost about a quarter of its value in five days. When the stock went the wrong way it lost about 58%, and even when it went the right way it lost about one time in three, to costs and time decay.</p>
          </div>
        </div>
        </Block>

        <Block wave title="5. Limits">
        <div className="grid gap-x-10 gap-y-5 sm:grid-cols-2">
          <Limit title="The recent months lost" text="June to September 2026 went the wrong way, and a new period can too." />
          <Limit title="Jumpy stocks" text="Signal stocks are riskier than the market. Part of the gain is that risk paying off while markets rose." />
          <Limit title="The past isn't the future" text="These are tests on history. Not financial advice. Paper-trade before you use real money." />
        </div>
        </Block>
      </div>

      <div className="mt-14 max-w-[80ch]"><MoreList>
        <More title="What we tried before landing on two kinds of signal" note="In the practice year we tried a lot of ideas and kept only what held up. Each number is the stock over five days against the S&P 500, per trade.">
        <ol className="border-t border-line">
          {TRIED.map((t, i) => (
            <li key={i} className="flex items-start gap-4 border-b border-line py-3">
              <span className={`w-14 shrink-0 pt-0.5 text-xs font-semibold ${t.kept ? "text-text" : t.kept === false ? "text-muted" : "text-muted"}`}>
                {t.kept ? "Kept" : t.kept === false ? "Dropped" : "Then"}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <span className="font-semibold">{t.kept ? <span className="mark">{t.idea}</span> : t.idea}</span>
                  {t.result != null && <span className={`text-sm font-semibold ${t.result >= 0 ? "text-bull" : "text-bear"}`}>{pct(t.result, 2)} per trade</span>}
                </div>
                {t.result != null && <MiniBar v={t.result} max={0.025} />}
                <p className="mt-1 text-sm text-muted">{t.why}</p>
              </div>
            </li>))}
        </ol>
        <p className="mt-4 text-sm">We called the last check the <span className="font-semibold">moment test</span>. Did the stock do better after the alert than that same stock
          usually does in a week? If not, the alert just picked a strong stock, not a good moment. Two ideas passed, and they&apos;re the two kinds of signal you see.</p>
        </More>
        {m.compound && <More title="What $1 would have done" note="A simulation, not a track record. Every signal bought as stock, held five days, money split five ways.">
        {m.compound && <div>
          <p className="mb-3 mt-1 text-xs text-muted">This is a simulation, not a track record. Every signal bought as stock and held five days, money split five ways, no taxes or
            leverage. It looks bigger than the per-trade numbers because gains compound. Notice the drop in the recent months.</p>
          <CompoundChart data={m.compound.curve} windows={[["Second test", m.compound.windows.pre[0]], ["Practice", m.compound.windows.train[0]], ["Sealed test", m.compound.windows.holdout[0]], ["Recent", m.compound.windows.post[0]]]} />
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-2 pr-4 font-normal">Period</th><th className="px-2 font-normal">$1 in signals (bought as stock) became</th>
                <th className="px-2 font-normal">Worst drop along the way</th><th className="px-2 font-normal">$1 in the S&amp;P 500 became</th></tr></thead>
              <tbody>
                {[...periods.map((p) => [p.key, `${p.name}, ${p.when}`] as const), ["all", "All of it, about 2.9 years (includes the practice year)"] as const].map(([k, label]) => {
                  const a = m.compound!.all[k], spy = m.compound!.spy[k];
                  return a && (
                    <tr key={k} className={`border-b border-line ${k === "all" ? "font-semibold" : ""}`}>
                      <td className="py-2 pr-4">{label}</td>
                      <td className={`px-2 font-semibold ${a.total_return >= 0 ? "text-bull" : "text-bear"}`}>{dollars(a.total_return)}</td>
                      <td className="px-2">{pct(a.max_drawdown, 0)}</td>
                      <td className="px-2">{dollars(spy?.total_return)}</td>
                    </tr>);
                })}
              </tbody>
            </table>
          </div>
          {(() => { const fo = m.compound!.far_otm.all?.total_return, wh = m.compound!.whale.all?.total_return, sp = m.compound!.spy.all?.total_return;
            return fo != null && wh != null && sp != null && <p className="mt-3 text-sm text-muted">Most of the gain came from the long shots, where $1 became {dollars(fo)}. Whale-size bets on their own
              turned $1 into {dollars(wh)}, {wh < sp ? "less than just holding the S&P 500" : "a little more than the S&P 500"} ({dollars(sp)}).</p>; })()}
        </div>}
        </More>}
        {m.holding && <More title="Why sell after 5 days?" note="We also tried 10, 20 and 30 days, after the tests, so it explains the choice rather than proving anything new.">
          <HoldSection h={m.holding} />
        </More>}
        <More title="Every table, threshold and caveat">
          <p className="text-sm"><Link href="/methodology/details" className="underline">Open the technical version</Link>: filter thresholds, the research we leaned on, results check by check and month by month, the beta table, stock vs options studies and caveats.</p>
        </More>
      </MoreList></div>
    </div>
  );
}

/** What we tried in the practice year (Oct 2024 – Sep 2025), in order. Source: docs/analysis-train-simple.md,
 *  docs/analysis-train-combos.md, docs/analysis-train.md (H1, H5 tercile tests; signs in journal/analysis-freeze.json:
 *  dark_pool +1, sector_flow −1), weights V05 in core/verdict/weights.py, session-8 review. kept: true = kept, false = dropped, null = step. */
const TRIED: { idea: string; result: number | null; why: string; kept: boolean | null }[] = [
  { idea: "Every clean opening buy (16,400 trades)", result: -0.0013, kept: false, why: "On their own, clean buys roughly broke even. The size and strike rules below are what added the edge." },
  { idea: "Six kinds of buy alert on their own (sweeps, repeat buyers, before earnings, far out of the money and so on)", result: null, kept: false, why: "None beat the market alone (from −1.5% to 0.0% per trade). Far out-of-the-money buys on their own lost 1.5%." },
  { idea: "Bearish bets (put buys)", result: -0.0068, kept: false, why: "Lost money. Most big put buys are insurance on stock people own, not bets." },
  { idea: "Other UW data as filters: dark pool, sector flow, and a 12-check blended score (with gamma, insider buying and market regime)", result: null, kept: false,
    why: "Dark-pool buying in the same direction helped a little (+0.5% from least to most), but not enough to rule out luck. Sector flow pointed the wrong way (the strongest third did 0.8% worse), and that wasn't reliable either. The blended score's top five picks a day just matched the market (+0.06%). So these show up as background (gamma walls and dark-pool levels on ticker pages, sector flow on Market) instead of filters. Skew and sentiment have no history to test." },
  { idea: "687 combinations of simple rules", result: null, kept: null, why: "Kept only combinations with 100+ trades that made money in both halves of the year. A short list survived." },
  { idea: "Cheap option + bullish (about 18 a day)", result: 0.009, kept: false, why: "Failed the moment test: those stocks did just as well on any day. It picked strong stocks, not good moments." },
  { idea: "Before earnings + cheap option", result: 0.0202, kept: false, why: "Fewer than 200 trades, the range included zero, and earnings jumps are a coin flip." },
  { idea: "Long shot: a call more than 15% out of the money at a fair price", result: 0.0199, kept: true, why: "Made money in both halves of the year and passed the moment test (+0.68%). This became the second kind of signal." },
  { idea: "Whale-size bet: $1M or more on a call more than 5% out of the money", result: 0.0142, kept: true, why: "Passed the moment test (+1.34%). This became the first kind of signal." },
];

function dollars(r: number | null | undefined) {
  return r == null ? "–" : `$${(1 + r).toFixed(2)}`;
}

function Rule({ text, ok }: { text: string; ok?: boolean }) {
  return <div className="flex items-start gap-2 border-b border-line py-2"><span aria-hidden className="font-semibold">{ok ? "✓" : "•"}</span><span>{text}</span></div>;
}

function Limit({ title, text }: { title: string; text: string }) {
  return <div className="border-t border-line pt-2"><div className="font-semibold">{title}</div><p className="mt-1 text-sm text-muted">{text}</p></div>;
}

function MiniBar({ v, max }: { v: number; max: number }) {
  const w = Math.min(50, (Math.abs(v) / max) * 50);
  return (
    <div className="relative mt-1 h-1.5 rounded bg-panel2" aria-hidden>
      <span className="absolute top-[-2px] h-2.5 w-px bg-muted" style={{ left: "50%" }} />
      <span className={`absolute h-1.5 rounded ${v >= 0 ? "bg-bull" : "bg-bear"}`} style={v >= 0 ? { left: "50%", width: `${w}%` } : { left: `${50 - w}%`, width: `${w}%` }} />
    </div>
  );
}

function BarRow({ label, v, max, tone }: { label: string; v: number | null | undefined; max: number; tone: "muted" | "brass" | "outline" }) {
  const x = v ?? 0, w = Math.min(50, (Math.abs(x) / max) * 50);
  const fill = tone === "brass" ? "bg-brass" : tone === "muted" ? "bg-line" : "border-2 border-brass bg-transparent";   // brass = the filter's picks (owner 10-08: not white)
  return (
    <div className="grid grid-cols-[minmax(0,11rem)_1fr_4.5rem] items-center gap-2 text-sm sm:grid-cols-[16rem_1fr_4.5rem]" title={`${label}: ${pct(v, 2)} per trade vs the S&P 500`}>
      <span className="truncate text-muted">{label}</span>
      <div className="relative h-4 rounded bg-panel2">
        <span className="absolute top-0 h-4 w-px bg-line" style={{ left: "50%" }} />
        <span data-bar={tone} className={`absolute top-0.5 h-3 rounded ${fill}`} style={x >= 0 ? { left: "50%", width: `${w}%` } : { left: `${50 - w}%`, width: `${w}%` }} />
      </div>
      <span className={`text-right font-semibold ${x >= 0 ? "text-bull" : "text-bear"}`}>{pct(v, 2)}</span>
    </div>
  );
}

/** Why sell after 5 days: the exploratory 5/10/20/30-day study (journal/research/holding-period.json). */
function HoldSection({ h }: { h: Holding }) {
  const cell = (p: string, H: number) => h.periods[p]?.by_horizon[String(H)];
  const tone = (v?: number) => (v == null ? "" : v >= 0 ? "text-bull" : "text-bear");
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-2 pr-4 font-normal">Hold the stock</th>
            <th className="px-2 font-normal">Practice year, per trade</th><th className="px-2 font-normal">Sealed test, per trade</th>
            <th className="px-2 font-normal">Sealed test, per day held</th><th className="px-2 font-normal">Recent months, per trade</th>
            <th className="px-2 font-normal">Trades with an earnings report inside</th></tr></thead>
          <tbody>
            {h.horizons.map((H) => { const tr = cell("train", H), ho = cell("holdout", H), po = cell("post", H); return (
              <tr key={H} className={`border-b border-line ${H === 5 ? "font-semibold" : ""}`}>
                <td className="py-2 pr-4">{H} days{H === 5 ? " (what we use)" : ""}</td>
                <td className={`px-2 ${tone(tr?.signals.avg_per_trade)}`}>{pct(tr?.signals.avg_per_trade, 2)}</td>
                <td className={`px-2 ${tone(ho?.signals.avg_per_trade)}`}>{pct(ho?.signals.avg_per_trade, 2)}</td>
                <td className={`px-2 ${tone(ho?.signals.avg_per_session_held)}`}>{pct(ho?.signals.avg_per_session_held, 2)}</td>
                <td className={`px-2 ${tone(po?.signals.avg_per_trade)}`}>{pct(po?.signals.avg_per_trade, 2)}</td>
                <td className="px-2">{plainPct(ho?.share_with_earnings_inside)}</td>
              </tr>); })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-muted">Every row uses the same trades: only signals old enough to have 30 days of prices
        ({h.periods.train?.by_horizon["5"]?.signals.trades ?? "–"} practice-year, {h.periods.holdout?.by_horizon["5"]?.signals.trades ?? "–"} sealed-test
        and {h.periods.post?.by_horizon["5"]?.signals.trades ?? "–"} recent-months trades). That&apos;s why the 5-day row can differ a little from the results above,
        most in the recent months, where the newest signals are left out.</p>
      <div className="mt-6 grid gap-x-8 gap-y-5 sm:grid-cols-3">
        <Limit title="More per trade, less per day" text="Longer holds make more per trade, but much less for each day your money is tied up." />
        <Limit title="Much bumpier" text="At 20 to 30 days the range of likely results is three to five times wider, and losing stretches hurt more. In the recent months it was about −5.6% a trade at 20 days, against −2% at 5." />
        <Limit title="Earnings sneak back in" text="The filter avoids earnings inside five days. Hold for 20 to 30 days and one to two trades in five go through an earnings report." />
      </div>
      <p className="mt-5 text-sm">So we stick with five days. It&apos;s one trading week, it&apos;s the time frame the research points to, and it did best or tied per day held.
        Ten days did about as well in the practice year but worse in the sealed test. No hold length is <span className="font-semibold">proven</span>.</p>
    </div>);
}
