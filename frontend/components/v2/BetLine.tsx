import type { Signal } from "@/lib/api";
import { money, plainPct, px, md } from "@/lib/format";


/** Share of the premium paid at the ask, read from the first "why" line (the engine writes "N% of it paid at the ask"). */
export function askShare(s: Signal): number | null {
  const m = s.why[0]?.match(/(\d+)% of it paid at the ask/);
  return m ? Number(m[1]) : null;
}

/** Owner 10-07: what the bet means first ("A whale bet $107K on KTOS rising 15%+ by Nov 20."; "bet", not "put", so it never reads as the option type — team review 10-20), the contract and the
 *  stock price (at the bet, and now) on a small line under it. Calls read "rising", puts "falling". */
export default function BetLine({ s, className = "" }: { s: Signal; className?: string }) {
  const way = s.kind === "put" ? "falling" : "rising";
  const by = s.otm_pct >= 0.01 ? <>{way} <span className="font-semibold text-brass">{plainPct(s.otm_pct)}+</span></> : way;
  const ask = askShare(s);
  const now = s.price_now ?? s.last_price;
  return (
    <div className={className}>
      <p className="text-[15px] leading-snug">A whale bet <b>{money(s.premium)}</b> on {s.ticker} {by} by <b>{md(s.expiry)}</b>.</p>
      <p className="mt-1 text-[13px] text-muted">
        {px(s.strike)} {s.kind}s{ask === 100 ? " · all at the ask" : ask != null && ask >= 50 ? ` · ${ask}% at the ask` : ""}
        {" · "}stock {px(s.spot_at_alert)}{now != null && Math.abs(now - s.spot_at_alert) >= 0.005
          ? <> → <span className="text-text">{px(now)} now</span></> : " at the bet"}
      </p>
    </div>
  );
}
