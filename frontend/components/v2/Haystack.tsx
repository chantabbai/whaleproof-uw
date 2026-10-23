import Link from "next/link";
import type { Funnel } from "@/lib/api";
import { num, plural } from "@/lib/format";
import { gridSize, placeSpots, rng } from "@/lib/haystack";

/** The day's flow as a haystack: one square per alert, shaded by how far it got through the filter, with the signals
 *  as the only marked squares. Positions are a seeded shuffle of the day, so the picture is stable between reloads. */
const CELL = 8, GAP = 2, STEP = CELL + GAP;

export default function Haystack({ f, day, tickers }: { f: Funnel; day: string; tickers: string[] }) {
  const n = Math.max(f.raw, 1), { cols: COLS, rows, scale } = gridSize(n);   // busy days widen, not lengthen (10-16)
  const W = COLS * STEP - GAP, H = rows * STEP - GAP;
  const rand = rng(day);
  const order = Array.from({ length: n }, (_, i) => i);
  for (let i = n - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [order[i], order[j]] = [order[j], order[i]]; }
  // stage of the k-th alert: 0 raw only, 1 one-way bet, 2 new buy (signals are marked on top)
  const paths = ["", "", ""];
  for (let k = 0; k < n; k++) {                 // the signals' own cells stay fresh-buy dark; their marks are drawn on top
    const st = k < f.clean ? 2 : k < f.directional ? 1 : 0;
    const p = order[k], x = (p % COLS) * STEP, y = Math.floor(p / COLS) * STEP;
    paths[st] += `M${x} ${y}h${CELL}v${CELL}h-${CELL}z`;
  }
  const placed = placeSpots(tickers, rows, COLS, rand, scale);
  const spots = placed.map(({ t, c, r }) => ({ t, x: c * STEP, y: r * STEP }));
  const mark = (CELL * 3 + GAP * 2) * scale;         // a signal's square: same size on screen however wide the grid
  return (
    <figure className="m-0">
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img"
          aria-label={`${plural(f.raw, "alert")} as squares: ${num(f.directional)} one-way bets, ${num(f.clean)} new buys, ${plural(tickers.length, "signal")}${tickers.length ? `: ${tickers.join(", ")}` : ""}.`}>
          <path d={paths[0]} fill="var(--hay-0)" />
          <path d={paths[1]} fill="var(--hay-1)" />
          <path d={paths[2]} fill="var(--hay-2)" />
          {spots.map((s) => (
            <rect key={s.t} x={s.x + CELL / 2 - mark / 2} y={s.y + CELL / 2 - mark / 2} width={mark} height={mark}
              fill="var(--marker)" stroke="var(--ink)" strokeWidth={2 * scale} className="hay-pop" />
          ))}
        </svg>
        {spots.map((s) => (
          <Link key={s.t} href={`/ticker/${s.t}`} className="wide hay-pop absolute -translate-y-1/2 whitespace-nowrap rounded-sm bg-[var(--ink)] px-2 py-0.5 text-[13px] text-[color:var(--sheet)] hover:underline md:text-[15px]"
            style={{ left: `calc(${((s.x + CELL / 2 + mark / 2 + GAP) / W) * 100}% + 6px)`, top: `${((s.y + CELL / 2) / H) * 100}%` }}>{s.t}</Link>
        ))}
      </div>
      <figcaption className="mt-4 text-[13px] text-muted">
        <p>One square per alert over $100K, shaded by how far it got through the filter (key below).</p>
        <ol className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-2 text-sm text-text" aria-label="How far the alerts got (point at or tap a step for what it removed)">
          <Key c="var(--hay-0)" tip="Every options alert over $100K that Unusual Whales flagged today.">
            <b>{num(f.raw)}</b> alerts</Key>
          <Arrow />
          <Key c="var(--hay-1)" tip="Repeats of the same bet on one ticker count once. Trades that mix calls and puts, or have several legs, are dropped.">
            <b>{num(f.directional)}</b> one-way bets</Key>
          <Arrow />
          <Key c="var(--hay-2)" tip="Only real new buys stay: paid the asking price, one option on its own, opening a position. Sales, closes, hedges, spreads, lottery tickets and deep in-the-money contracts are dropped.">
            <b>{num(f.clean)}</b> new buys</Key>
          <Arrow />
          <Key c="var(--marker)" ring tip="Last rules: calls only, share price $5 or more, no earnings before the planned sell, no small bets close to the current price. Each signal follows one rule: buy at the next open, sell at the close of the fifth trading day.">
            <b>{num(f.signals)}</b> signal{f.signals === 1 ? "" : "s"}</Key>
        </ol>
      </figcaption>
    </figure>
  );
}

function Arrow() {
  return <li aria-hidden className="text-muted">→</li>;
}

/** Legend step; what it removed shows on hover or keyboard focus (and on tap, which focuses it). */
function Key({ c, ring = false, tip, children }: { c: string; ring?: boolean; tip: string; children: React.ReactNode }) {
  return (
    <li tabIndex={0} className="group relative inline-flex cursor-help items-center gap-2 outline-offset-2">
      <span aria-hidden className={`inline-block h-3 w-3 ${ring ? "outline outline-1 outline-[var(--ink)]" : ""}`} style={{ background: c }} />
      <span className="underline decoration-dotted underline-offset-4">{children}</span>
      <span role="tooltip" className="pointer-events-none absolute bottom-full left-0 z-20 mb-2 hidden w-64 max-w-[80vw] rounded-md bg-[var(--ink)] px-3 py-2 text-[13px] leading-snug text-[color:var(--sheet)] shadow-lg group-hover:block group-focus:block">{tip}</span>
    </li>
  );
}
