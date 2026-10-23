import Link from "next/link";
import AutoRefresh from "@/components/AutoRefresh";
import Empty from "@/components/Empty";
import { Block, Hero, More, MoreList, Panel, Tile, Tiles } from "@/components/v2/ui";
import TideChart from "@/components/TideChart";
import { get, type Fresh, type Gex, type Spot, type TidePoint } from "@/lib/api";
import { age, etTime, money, px, shortDate, signedMoney, arrowPct, moveTone, isFlat, days as nDays, dte, plural, md } from "@/lib/format";

type Day = {
  day: string; short_dte_total: number; note: string; tide: TidePoint[]; tide_day: string | null;
  short_dte_board: { ticker: string; calls: number; puts: number; net: number; n: number; watch: boolean;
    top: { premium: number; kind: string; strike: number; expiry: string; dte: number; at: string; sweep: boolean } }[];
  sectors: { sector: string; net: number; call: number; put: number }[];
  levels: Record<string, { spot: Spot | null; gex: Gex | null; dp_top: [number, number][]; dp_date?: string | null }>;
  freshness: { flow: Fresh; tide: Fresh };
};

type Regime = { regime: { gamma: { positive: boolean; spot: number; flip: number; date: string } | null } };
type Rotation = { rotation: { sector: string; days: Record<string, number | null>; total: number }[] };

export default async function MarketPage() {
  const [d, td, sw] = await Promise.all([get<Day>("/api/desk/day"), get<Regime>("/api/desk/today"), get<Rotation>("/api/desk/swing")]);
  if (!d) return <Empty>The WhaleProof API is not answering. Start it with <code>scripts/desk.sh up</code>, then reload.</Empty>;
  const scale = sectorScale(d.sectors.map((x) => x.net));
  const g = td?.regime.gamma ?? null;
  const rot = sw?.rotation ?? [];
  const days = [...new Set(rot.flatMap((r) => Object.keys(r.days)))].sort();
  const maxRot = Math.max(1, ...rot.flatMap((r) => Object.values(r.days).map((v) => Math.abs(v ?? 0))));
  const last = d.tide.at(-1);
  const spy = d.levels.SPY?.spot, spyCh = spy?.last && spy.prev_close ? spy.last / spy.prev_close - 1 : null;
  const top = d.sectors[0], bottom = d.sectors.at(-1);
  const flowAge = age(d.freshness.flow.age_s).replace(" old", "");
  const board = [...d.short_dte_board].sort((a, b) => b.calls + b.puts - (a.calls + a.puts));   // biggest money first
  return (
    <div>
      <AutoRefresh seconds={60} />
      <Hero name="Market" eyebrow={longDay(d.day)}
        title={g ? (g.positive ? "Positive gamma: dealers lean against moves." : "Negative gamma: dealers chase moves.") : "Market"}
        lead={g ? <>SPY {px(g.spot)} is {g.positive ? "above" : "below"} its gamma flip ({px(g.flip)}), so dealer hedging tends to {g.positive ? "sell rallies and buy dips, which damps moves and favors ranges" : "sell into drops and buy into rallies, which makes moves bigger both ways"}. An estimate from options positioning, not a forecast: news still moves markets.</>
          : "Background for reading the signals. Not a trade list."} />
      <p className="mt-3 text-[13px] text-muted">{d.freshness.flow.stale
        ? <span className="font-semibold text-warn">{flowAge === "never" ? "Flow hasn't loaded yet." : <>Flow hasn&apos;t updated in {flowAge}.</>}</span> : <>Flow updated {flowAge} ago, every minute while open.</>}</p>

      <div className="mt-10"><Tiles>
        <Tile accent="sea" k="SPY today" v={spyCh == null ? "–" : arrowPct(spyCh, 2)} sub={spy?.last ? px(spy.last) : "not loaded"} tone={spyCh == null || isFlat(spyCh, 2) ? null : spyCh > 0 ? "bull" : "bear"} />
        <Tile accent="amber" k="Options lean, whole market" v={last ? signedMoney(last.net) : "–"} sub={last ? `${last.net >= 0 ? "Bullish" : "Bearish"}: money into calls minus money into puts (bought minus sold), at ${etTime(last.t)}` : "not loaded"} tone={last ? (last.net >= 0 ? "bull" : "bear") : null} />
        <Tile accent="brass" k="Leans most bullish" v={top ? <SectorName name={top.sector} /> : "–"} fit={false} sub={top ? signedMoney(top.net) : "not loaded"} tone={top ? "bull" : null} />
        <Tile accent="amber" k="Leans most bearish" v={bottom && bottom.net < 0 ? <SectorName name={bottom.sector} /> : "–"} fit={false} sub={bottom && bottom.net < 0 ? signedMoney(bottom.net) : top ? "no sector leans bearish" : "not loaded"} tone={bottom && bottom.net < 0 ? "bear" : null} />
      </Tiles></div>

      <div className="mt-14 grid gap-x-12 gap-y-14 lg:grid-cols-2 [&>*]:min-w-0">
        <Block wave title="Options lean through the day" sub="Running total for the whole market, in five-minute steps: bought at the ask minus sold at the bid. Below zero means more sold than bought.">
          <Panel><TideChart data={d.tide} height={170} /></Panel>
        </Block>
        <Block wave title="Options lean by sector" sub="Money into calls minus money into puts (bought minus sold), by sector. Right of the line leans bullish, left leans bearish.">
          <ul className="space-y-2 text-sm">
            {d.sectors.map((x) => {
              const w = (Math.min(Math.abs(x.net), scale) / scale) * 50, left = x.net >= 0 ? 50 : 50 - w;
              return (
                <li key={x.sector} className="grid grid-cols-[9rem_1fr_5.5rem] items-center gap-2">
                  <span className="truncate" title={x.sector}>{x.sector}</span>
                  <span className="relative h-2.5 rounded-full bg-panel2">
                    <span aria-hidden className="absolute -top-1 bottom-[-4px] left-1/2 w-px bg-line" />
                    <span className="absolute top-0 h-2.5 rounded-full" style={{ left: `${left}%`, width: `${Math.max(w, 0.6)}%`, background: x.net >= 0 ? "var(--bull)" : "var(--bear)" }} />
                  </span>
                  <span className={`text-right ${x.net >= 0 ? "text-bull" : "text-bear"}`}>{signedMoney(x.net)}</span>
                </li>);
            })}
            {d.sectors.length === 0 && <li className="text-muted">Sector numbers haven&apos;t loaded yet.</li>}
          </ul>
        </Block>
      </div>

      <div className="mt-14">
        <Block wave title="Short-dated buying" sub={`Options expiring within a week, bought at the ask. ${plural(d.short_dte_total, "trade")} today. Biggest money first. The bar splits it into calls (blue) and puts (orange); the number is calls minus puts.`}>
          {board.length === 0 ? <Empty>No short-dated buying yet this session.</Empty> : (
            <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              {board.slice(0, 12).map((b) => {
                const total = b.calls + b.puts, up = b.net >= 0;
                return (
                  <li key={b.ticker}><Link href={`/ticker/${b.ticker}`} data-testid="short-dte-tile" data-total={total}
                    className={`block rounded-md border border-line p-3 transition-colors duration-150 hover:border-text ${up ? "bg-bull-soft" : "bg-bear-soft"}`}>
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="wide text-[17px]">{b.watch ? "★ " : ""}{b.ticker}</span>
                      <span className={`text-[15px] font-semibold ${up ? "text-bull" : "text-bear"}`}>{up ? "▲" : "▼"} {signedMoney(b.net)}</span>
                    </span>
                    <span aria-hidden className="mt-2 flex gap-[3px]">
                      {b.calls > 0 && <span className="h-1 rounded-full bg-bull" style={{ flex: b.calls }} />}
                      {b.puts > 0 && <span className="h-1 rounded-full bg-bear" style={{ flex: b.puts }} />}
                    </span>
                    <span className="mt-1.5 block text-xs text-muted">{money(total)} traded, {total > 0 ? Math.round((b.calls / total) * 100) : 0}% calls</span>
                  </Link></li>);
              })}
            </ul>
          )}
        </Block>
      </div>

      <div className="mt-14"><MoreList>
        <More title={`All short-dated names (${board.length})`} note="Net = calls bought minus puts bought. A star means it's on your watchlist.">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-sm">
              <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-2 pr-3 font-normal">Ticker</th><th className="font-normal">▲ Calls bought</th><th className="font-normal">▼ Puts bought</th><th className="font-normal">Net</th><th className="pr-3 font-normal">Biggest single trade</th></tr></thead>
              <tbody>{board.map((b) => (
                <tr key={b.ticker} className="border-b border-line">
                  <td className="py-1.5 pr-3 font-semibold"><Link href={`/ticker/${b.ticker}`} className="hover:underline">{b.watch ? "★ " : ""}{b.ticker}</Link></td>
                  <td className="text-bull">{money(b.calls)}</td><td className="text-bear">{money(b.puts)}</td>
                  <td className={b.net >= 0 ? "text-bull" : "text-bear"}>{b.net >= 0 ? "▲" : "▼"} {signedMoney(b.net)}</td>
                  <td className="pr-3 text-muted">{money(b.top.premium)} on the {px(b.top.strike)} {b.top.kind}, {dte(b.top.dte, " out")}{b.top.sweep ? ", swept" : ""}, {etTime(b.top.at)}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </More>
        <More title="Key levels: gamma walls and dark pool" note="Walls are strikes where dealer hedging piles up. Prices often pin near big strikes into expiry (Ni, Pearson and Poteshman, 2005). A level more than 20% from the price shows how far it is; that far out it has little pull. Add names to your watchlist to see them here.">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[460px] text-sm">
              <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-2 pr-3 font-normal">Ticker</th><th className="font-normal">Last</th><th className="font-normal">Put wall</th><th className="font-normal">Flip</th><th className="font-normal">Call wall</th><th className="pr-3 font-normal">Busiest dark-pool price</th></tr></thead>
              <tbody>{Object.entries(d.levels).map(([t, l]) => {
                const ch = l.spot?.last && l.spot.prev_close ? l.spot.last / l.spot.prev_close - 1 : null;
                return (
                  <tr key={t} className="border-b border-line">
                    <td className="py-1.5 pr-3 font-semibold"><Link href={`/ticker/${t}`} className="hover:underline">{t}</Link></td>
                    <td>{px(l.spot?.last)} {ch != null && <span className={`text-xs ${moveTone(ch, 2)}`}>{arrowPct(ch, 2)}</span>}</td>
                    <td><Lvl v={l.gex?.put_wall} last={l.spot?.last} /></td><td><Lvl v={l.gex?.gamma_flip} last={l.spot?.last} /></td><td><Lvl v={l.gex?.call_wall} last={l.spot?.last} /></td>
                    <td className="pr-3">{l.dp_top[0] ? <>{px(l.dp_top[0][0])}{l.dp_date && l.dp_date !== d.day && <span className="text-xs text-muted">, {md(l.dp_date)}</span>}</> : "–"}</td>
                  </tr>);
              })}</tbody>
            </table>
          </div>
        </More>
        {rot.length > 0 && <More title="Sector money over the last five sessions" note="Is money rotating? Money into calls minus money into puts (bought minus sold), per sector per session.">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-2 pr-3 font-normal">Sector</th>
                {days.map((x) => <th key={x} className="font-normal">{shortDate(x)}</th>)}<th className="pr-3 font-normal">Total</th></tr></thead>
              <tbody>
                {rot.map((r) => (
                  <tr key={r.sector} className="border-b border-line">
                    <td className="py-1.5 pr-3">{r.sector}</td>
                    {days.map((x) => {
                      const v = r.days[x] ?? null;
                      return <td key={x} className="py-1.5 pr-2">{v == null ? "–" : (
                        <span className={v >= 0 ? "text-bull" : "text-bear"}>
                          <span className="inline-block h-2 rounded-full align-middle" style={{ width: `${Math.max(3, (Math.abs(v) / maxRot) * 60)}px`, background: v >= 0 ? "var(--bull)" : "var(--bear)" }} />
                          <span className="ml-1 text-xs">{signedMoney(v)}</span></span>)}</td>;
                    })}
                    <td className={`pr-3 font-semibold ${r.total >= 0 ? "text-bull" : "text-bear"}`}>{signedMoney(r.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </More>}
      </MoreList></div>
    </div>
  );
}

/** Bar scale for the sector list: the biggest sector, unless it dwarfs the rest; then stop just past the second-biggest
 *  so the others stay visible (owner 10-08). A bigger sector just gets a full bar; its number is exact. */
function sectorScale(nets: number[]) {
  const a = nets.map(Math.abs).sort((x, y) => y - x);
  if (a.length < 2 || a[1] === 0) return Math.max(1, a[0] ?? 1);
  return a[0] > a[1] * 1.25 ? a[1] * 1.25 : a[0];
}

function longDay(iso: string) {
  return new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
}

/** A sector name in a tile: sized from the tile's width so the longest UW name ("Communication Services", ≈ 12.5em) fits
 *  on one line and both sector tiles match; below 16px it wraps between words, never inside one. */
function SectorName({ name }: { name: string }) {
  return (
    <span className="block [container-type:inline-size]">
      <span className="block [overflow-wrap:normal]" style={{ fontSize: "clamp(16px, calc(100cqw / 12.8), 26px)", fontVariationSettings: '"wdth" 100' }}>{name}</span>
    </span>
  );
}

/** A gamma level; more than 20% from the price it says how far (UW's put wall can sit far below, e.g. IWM $95 at $276).
 *  20% = the ticker chart's level range. */
function Lvl({ v, last }: { v?: number | null; last?: number | null }) {
  if (v == null) return <>{px(v)}</>;
  const off = last ? v / last - 1 : 0;
  return <>{px(v)}{Math.abs(off) > 0.2 && <span className="block text-xs text-muted">{Math.round(Math.abs(off) * 100)}% {off > 0 ? "above" : "below"}</span>}</>;
}
