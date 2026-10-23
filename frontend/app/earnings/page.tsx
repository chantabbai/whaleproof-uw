import AutoRefresh from "@/components/AutoRefresh";
import Link from "next/link";
import Empty from "@/components/Empty";
import { BarsKey, EarnChip, ImpliedChip, PastMoves, When, heat, movePct } from "@/components/EarnBits";
import { Block, Hero, More, MoreList, Tile, Tiles } from "@/components/v2/ui";
import { get, type EarnBacktest, type EarnLabel, type Earnings } from "@/lib/api";
import { etTime, plainPct, ratioX, shortDate, plural } from "@/lib/format";

const LABELS: EarnLabel[] = ["cheap", "fair", "rich"];
const YEARS = ["2023", "2024", "2025", "2026"];

function Backtest({ b, th }: { b: EarnBacktest; th: Earnings["thresholds"] }) {
  const L = b.by_label;
  return (
    <div className="py-1 text-sm">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-sm">
          <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-1.5 font-normal">How often it moved more than expected</th>
            {YEARS.map((y) => <th key={y} className="font-normal">{y}</th>)}<th className="font-normal">All</th></tr></thead>
          <tbody>{LABELS.map((l) => (
            <tr key={l} className="border-b border-line">
              <td className="py-1.5"><EarnChip label={l} /></td>
              {YEARS.map((y) => {
                const s = b.by_label_year[l]?.[y];
                return <td key={y} title={s ? plural(s.reports, "report") : ""}>{s ? plainPct(s.beat) : "–"}</td>;
              })}
              <td title={plural(L[l].reports, "report")}>{plainPct(L[l].beat)}</td>
            </tr>))}</tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-muted">
        &ldquo;Cheap&rdquo; means the implied move was under {th.cheap_below}× the median of the stock&apos;s last {th.max_past} report moves
        (at least {th.min_past}, all within three years and before the report). &ldquo;Rich&rdquo; means over {th.rich_above}×. We set those
        cut-offs before looking at any results. This was exploratory, run {new Date(`${b.run.slice(0, 10)}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}. We left out {plural(b.sensitivity.dropped, "report")} with implied moves
        over 50%, which are junk on thinly traded names, and the results barely change either way. The label compares best on the last session
        before a report, because that&apos;s when we measured it. Earlier in the week it leans rich. Some of the gap between cheap and rich is just
        noise in the implied move.
      </p>
    </div>
  );
}

const WORD: Record<EarnLabel, string> = { cheap: "Cheap", fair: "Fair", rich: "Rich" };

/** What cheap / fair / rich mean, next to the column that uses them (owner 10-08: "how can a user understand the label?"). */
function PriceKey({ th, bt }: { th: Earnings["thresholds"]; bt: EarnBacktest | null | undefined }) {
  const beat = (l: EarnLabel) => (bt ? ` (beaten ${plainPct(bt.by_label[l].beat)} of the time)` : "");
  return (
    <p className="mb-6 max-w-[90ch] rounded-md bg-panel2 px-3 py-2 text-[13px] leading-relaxed">
      <span className="font-semibold">Options price vs usual move:</span>{" "}
      <EarnChip label="cheap" /> = options charge under {th.cheap_below}× the usual move{beat("cheap")} · <EarnChip label="fair" /> = {th.cheap_below}–{th.rich_above}×{beat("fair")} ·{" "}
      <EarnChip label="rich" /> = over {th.rich_above}×{beat("rich")}. Beaten = the stock moved more than options charged for.
    </p>
  );
}

export default async function EarningsPage() {
  const e = await get<Earnings>("/api/desk/earnings");
  if (!e) return <Empty>The WhaleProof API is not answering. Start it with <code>scripts/desk.sh up</code>, then reload.</Empty>;
  // owner 10-16: biggest companies first (was UW's calendar order: before-the-open list, then after-the-close)
  const biggest = (a: { marketcap: number | null }, b: { marketcap: number | null }) => (b.marketcap ?? -1) - (a.marketcap ?? -1);
  const byDay = e.sessions.map((d) => ({ d, rows: e.upcoming.filter((r) => r.date === d).sort(biggest) }));
  const bt = e.backtest;
  const ahead = e.upcoming.filter((r) => !r.reported);   // today's reports already out don't count as coming up
  const top = [...ahead].sort(biggest).slice(0, 6);
  const n = (l: EarnLabel) => ahead.filter((r) => r.label === l).length;
  return (
    <div>
      <AutoRefresh seconds={300} />
      <Hero name="Earnings" eyebrow={`The next ${e.sessions.length || 5} sessions of reports`}
        title={bt ? <>Options usually over-price the move. Stocks beat it {plainPct(bt.all.beat)} of the time.</> : "Earnings"}
        lead={bt ? <>When the priced-in move looked cheap next to the stock&apos;s past reports, it got beaten {plainPct(bt.by_label.cheap.beat)} of the time; rich ones {plainPct(bt.by_label.rich.beat)}. That pattern held every year since 2023. Trading it with real option prices hasn&apos;t been checked yet.</>
          : "Before a report, options price in a move. This compares it with how much the stock actually moved on past reports."} />
      <p className="mt-3 text-[13px] text-muted">{e.at ? `Calendar updated ${shortDate(e.at)} at ${etTime(e.at)}.` : "The calendar hasn't loaded yet."}</p>

      <div className="mt-10"><Tiles>
        <Tile accent="sea" k="Reports coming up" v={String(ahead.length)} sub={`over ${plural(e.sessions.length, "session")}`} />
        <Tile accent="amber" k="Look cheap" v={String(n("cheap"))} sub={bt ? `history: beaten ${plainPct(bt.by_label.cheap.beat)}` : ""} />
        <Tile accent="amber" k="Look rich" v={String(n("rich"))} sub={bt ? `history: beaten ${plainPct(bt.by_label.rich.beat)}` : ""} />
        <Tile accent="brass" k="Reports checked" v={bt ? bt.scored.toLocaleString("en-US") : "–"} sub="since 2022" />
      </Tiles></div>

      {top.length > 0 && <div className="mt-14">
        <Block wave title="Biggest reporting">
          <ul className="grid grid-cols-3 gap-2 lg:grid-cols-6">{top.map((r) => (
            <li key={r.ticker}>
              <Link href={`/ticker/${r.ticker}`} className={`block rounded-md px-2.5 py-2 text-center outline-offset-2 hover:outline hover:outline-1 ${r.implied != null ? heat(r.implied) : "bg-panel2"}`}>
                <span className="flex items-center justify-center gap-1.5 text-xs font-semibold">
                  {r.time === "premarket" ? <span aria-hidden>☀</span> : r.time === "postmarket" || r.time === "afterhours" ? <span aria-hidden>☾</span> : null}{r.ticker}</span>
                <span className="mt-0.5 block text-[15px] font-bold tabular-nums">{r.implied != null ? `±${plainPct(r.implied, 1)}` : "n/a"}</span>
                <span className="mt-0.5 block text-[11px] text-muted">{shortDate(r.date)}</span>
              </Link>
            </li>))}</ul>
          <p className="mt-2 text-xs text-muted"><span className="text-amber">☀</span> before the open, <span className="text-sea">☾</span> after the close.
            Biggest companies reporting in the next {plural(e.sessions.length || 5, "session")} (± = what options price in).</p>
        </Block>
      </div>}

      <div className="mt-14">
        <Block wave title="Coming up" sub="Implied = the move options charge for, shaded like the earnings tiles on Sightings (darker = bigger). Usual move = the stock's typical move on its past reports. Bars = those past moves, oldest first (key below the tables).">
          <PriceKey th={e.thresholds} bt={bt} />
          {byDay.length === 0 ? <Empty>No reports listed for the next few sessions yet{e.at ? "" : ". The calendar loads about a minute after the desk starts"}.</Empty> : (
            <div className="space-y-10">
              {byDay.map(({ d, rows }) => (
                <div key={d} className="overflow-x-auto">
                  <h3 className="text-[15px] font-semibold">{shortDate(d)} <span className="font-normal text-muted">· {plural(rows.length, "report")}{rows.some((r) => r.reported) ? `, ${rows.filter((r) => r.reported).length} already out` : ""}</span></h3>
                  <table className="mt-2 w-full min-w-[600px] table-fixed text-sm">
                    <colgroup><col className="w-[12%]" /><col className="w-[14%]" /><col className="w-[11%]" /><col className="w-[14%]" />
                      <col className="w-[22%]" /><col className="w-[27%]" /></colgroup>
                    <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-1.5 pr-3 font-normal">Ticker</th><th className="font-normal">When</th>
                      <th className="font-normal">Implied</th><th className="font-normal">Usual move</th><th className="font-normal">Options price vs usual move</th>
                      <th className="font-normal">Past moves</th></tr></thead>
                    <tbody>{rows.map((r) => (
                      <tr key={r.ticker} className="border-b border-line align-middle">
                        <td className="py-2 pr-3 font-semibold"><Link href={`/ticker/${r.ticker}`} className="hover:underline">{r.ticker}</Link></td>
                        <td className="text-xs"><When time={r.time} />{r.reported && <span className="block text-muted">already out</span>}</td>
                        <td>{r.implied == null ? "–" : <ImpliedChip v={r.implied} />}</td>
                        <td>{movePct(r.past)}</td>
                        <td title={r.label && r.ratio != null ? `Options charge ${ratioX(r.ratio)}× this stock's usual report move.${bt ? ` ${WORD[r.label]} ones got beaten ${plainPct(bt.by_label[r.label].beat)} of the time.` : ""}` : undefined}>
                          {r.label ? <><EarnChip label={r.label} /> <span className="text-xs text-muted">{r.ratio != null ? ratioX(r.ratio) : ""}× usual</span></> : <span className="text-xs text-muted">{r.note}</span>}</td>
                        <td><PastMoves history={r.history} implied={r.implied} /></td>
                      </tr>))}</tbody>
                  </table>
                </div>
              ))}
              <p className="text-xs text-muted"><span className="text-amber">☀</span> before the open, <span className="text-sea">☾</span> after the close. Past moves: <BarsKey /></p>
            </div>
          )}
        </Block>
      </div>

      <div className="mt-14"><MoreList>
        <More title="Cheap, fair, rich: year by year" note="How often the stock moved more than options expected, by label. The order held every year.">
          {bt ? <Backtest b={bt} th={e.thresholds} /> : <Empty>The earnings history check hasn&apos;t been run on this install. Run it as the README explains (&ldquo;Run it yourself&rdquo;).</Empty>}
        </More>
        <More title="How the implied move is worked out" note="UW's formula: the front-month at-the-money straddle × 0.85. It's what the market is charging, not a forecast.">
          <p className="max-w-[68ch] text-sm text-muted">The signal filter already skips any trade with earnings inside its five-day hold, so this page is background, not a list of signals. Not financial advice.</p>
        </More>
      </MoreList></div>
    </div>
  );
}
