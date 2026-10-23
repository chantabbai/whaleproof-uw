import { Suspense } from "react";
import CloseTrade from "@/components/CloseTrade";
import DeleteTrade from "@/components/DeleteTrade";
import Dir from "@/components/Dir";
import Empty from "@/components/Empty";
import JournalForm from "@/components/JournalForm";
import { Block, Hero, More, MoreList, Tile, Tiles } from "@/components/v2/ui";
import { get } from "@/lib/api";
import { signedMoney, num, pct, plainPct, px, shortDate, etTime, arrowPct, moveTone } from "@/lib/format";

type Trade = { id: number; ticker: string; instrument?: string; direction: number; entry_date: string; entry_price: number; exit_date: string | null;
  exit_price: number | null; stop: number | null; size: number | null; setup: string; notes: string; status: string;
  pnl_pct: number | null; pnl: number | null; r_multiple: number | null;
  now: { price: number; source: "live" | "close"; at: string | null; date: string; move: number; pnl: number | null } | null;
  signal: { tier: string; why: string[]; premium: number; session_date: string } | null };
type J = { trades: Trade[]; stats: { open: number; closed: number; win_rate: number | null; avg_r: number | null; avg_pct: number | null;
  by_setup: Record<string, { n: number; win_rate: number; avg_r: number | null }> } };

/** Dollars to the cent under $1K: small paper positions (−$4.73 is not −$5). */
const cents = (v: number) => (Math.abs(v) >= 1000 ? signedMoney(v) : `${v >= 0 ? "+" : "−"}$${Math.abs(v).toFixed(2)}`);

const SETUP: Record<string, string> = { whale: "Whale-size bet", far_otm: "Long shot", day: "Day trade", manual: "My own idea" };

export default async function JournalPage({ searchParams }: { searchParams: Promise<{ ticker?: string }> }) {
  const { ticker } = await searchParams;
  const j = await get<J>("/api/desk/journal");
  if (!j) return <Empty>The WhaleProof API is not answering. Start it with <code>scripts/desk.sh up</code>, then reload.</Empty>;
  const s = j.stats;
  const marked = j.trades.filter((t) => t.now), moves = marked.map((t) => t.now!.move);
  const openPnl = marked.reduce((a, t) => a + (t.now!.pnl ?? 0), 0), hasPnl = marked.some((t) => t.now!.pnl != null);
  const avgNow = moves.length ? moves.reduce((a, b) => a + b, 0) / moves.length : null;
  return (
    <div>
      <Hero name="Journal" eyebrow="Stored only on this machine"
        title={"Your paper trades, in one place."}
        lead="Log what you bought, close it when you sell, and see whether following the signals is working for you." />

      <div className="mt-10"><Tiles>
        <Tile accent="sea" k="Closed trades" v={String(s.closed)} sub={`${s.open} still open`} />
        {s.closed === 0 && moves.length > 0 ? <>
          {/* Nothing closed yet: where the open trades stand, not four dashes (owner 10-08, like Track record). */}
          <Tile accent="amber" k="Open trades up so far" v={`${moves.filter((m) => m > 0).length} of ${moves.length}`} sub="at the last price" />
          <Tile accent="amber" k="Average so far" v={pct(avgNow)} tone={(avgNow ?? 0) >= 0 ? "bull" : "bear"} sub="price move since your entry" />
          <Tile accent="brass" k="Open profit/loss" v={hasPnl ? cents(openPnl) : "–"} tone={openPnl >= 0 ? "bull" : "bear"} sub={hasPnl ? "on the shares you logged" : "log a size to see dollars"} />
        </> : <>
          <Tile accent="amber" k="Winners" v={plainPct(s.win_rate)} />
          <Tile accent="amber" k="Average R" v={s.avg_r == null ? "–" : `${num(s.avg_r, 2)}R`} sub="profit over the risk to your stop" tone={s.avg_r == null ? null : s.avg_r >= 0 ? "bull" : "bear"} />
          <Tile accent="brass" k="Average return" v={pct(s.avg_pct)} tone={s.avg_pct == null ? null : s.avg_pct >= 0 ? "bull" : "bear"} />
        </>}
      </Tiles></div>
      {s.closed < 30 && <p className="mt-3 text-[13px] text-muted">{s.closed} closed so far. Under about 30 trades, read the numbers as noise.</p>}

      <div className="mt-12"><MoreList>
        <More title={ticker ? `Log a trade in ${ticker.toUpperCase()}` : "Log a trade"} open={!!ticker || j.trades.length === 0}
          note="If the ticker has an open signal, its reasons are saved with the trade."><Suspense><JournalForm /></Suspense></More>
      </MoreList></div>

      <div className="mt-14">
        <Block wave title="Trades" sub={<a href="/api/desk/journal.csv" download="signal-desk-journal.csv" className="underline">Download all as CSV</a>}>
          {j.trades.length === 0 ? <Empty>No trades yet. Log one above, or press &ldquo;Log trade&rdquo; on any signal.</Empty> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-sm">
                <thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-2 pr-3 font-normal">Ticker</th><th className="font-normal">Entry</th><th className="font-normal">Exit</th><th className="font-normal">Result</th><th className="font-normal">Setup</th><th className="font-normal">Signal when you entered</th><th className="pr-3 font-normal"><span className="sr-only">Delete</span></th></tr></thead>
                <tbody>{j.trades.map((t) => (
                  <tr key={t.id} className="border-b border-line align-top">
                    <td className="py-2 pr-3"><span className="font-semibold">{t.ticker}</span> <Dir d={t.direction} compact /></td>
                    <td className="py-2 pr-4">{px(t.entry_price)}<span className="block text-xs text-muted">{shortDate(t.entry_date)}{t.size ? `, ${num(t.size, Number.isInteger(t.size) ? 0 : 2)} ${t.instrument === "option" ? (t.size === 1 ? "contract" : "contracts") : (t.size === 1 ? "share" : "shares")}` : ""}{t.stop ? `, stop ${px(t.stop)}` : ""}</span></td>
                    <td className="py-2 pr-4">{t.status === "closed" ? <>{px(t.exit_price)}<span className="block text-xs text-muted">{shortDate(t.exit_date)}</span></> : <CloseTrade id={t.id} />}</td>
                    <td className={`py-2 pr-4 ${(t.pnl_pct ?? 0) >= 0 ? "text-bull" : "text-bear"}`}>{t.pnl_pct == null ? (t.now ? <NowCell n={t.now} /> : <span className="text-muted">Still open</span>) : <>{t.pnl_pct >= 0 ? "▲" : "▼"} {pct(t.pnl_pct)}{t.r_multiple != null && ` (${num(t.r_multiple, 2)}R)`}{t.pnl != null && <span className="block text-xs">{signedMoney(t.pnl)}</span>}</>}</td>
                    <td className="py-2 pr-4">{SETUP[t.setup] ?? t.setup}{t.notes && <span className="block text-xs text-muted">{t.notes}</span>}</td>
                    <td className="py-2 pr-4 text-xs text-muted">{t.signal ? `${t.signal.tier === "whale" ? "Whale-size" : "Long shot"} signal from ${shortDate(t.signal.session_date)}: ${t.signal.why[0]}` : "None"}</td>
                    <td className="py-2 pr-3 text-right"><DeleteTrade id={t.id} ticker={t.ticker} /></td>
                  </tr>))}</tbody>
              </table>
            </div>
          )}
        </Block>
      </div>

      {Object.keys(s.by_setup).length > 0 && <div className="mt-14"><MoreList>
        <More title="Results by setup">
          <table className="w-full max-w-lg text-sm"><thead className="border-b border-text text-left text-xs text-muted"><tr><th className="py-1.5 font-normal">Setup</th><th className="font-normal">Closed</th><th className="font-normal">Winners</th><th className="font-normal">Average R</th></tr></thead>
            <tbody>{Object.entries(s.by_setup).map(([k, v]) => <tr key={k} className="border-b border-line"><td className="py-1.5">{SETUP[k] ?? k}</td><td>{v.n}</td><td>{plainPct(v.win_rate)}</td><td>{v.avg_r == null ? "–" : num(v.avg_r, 2)}</td></tr>)}</tbody></table>
        </More>
      </MoreList></div>}
    </div>
  );
}

/** An open trade where it stands: same price as Sightings, live while the market is open, the last close after. */
function NowCell({ n }: { n: NonNullable<Trade["now"]> }) {
  return <><span className={moveTone(n.move)}>{arrowPct(n.move)}</span> <span className="text-xs text-muted">so far</span>
    <span className="block text-xs text-muted">{px(n.price)}, {n.source === "live" && n.at ? `live ${etTime(n.at)}` : `${shortDate(n.date)} close`}{n.pnl != null && ` · ${cents(n.pnl)}`}</span></>;
}

