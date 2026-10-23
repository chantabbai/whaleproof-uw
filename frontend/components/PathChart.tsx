/** Day-by-day path of one signal: the stock and the whale's option, both as % from what you paid, on ONE axis.
 *  Stock = solid line in text ink, option = dashed grey line (identity never colour alone: dash + legend + end labels).
 *  Each point carries a native tooltip; the table next to it is the accessible view of the same numbers. */
import { pct, plural } from "@/lib/format";

type Pt = [string, number];

export default function PathChart({ stock, option, hold = 5 }: { stock: Pt[]; option: Pt[]; hold?: number }) {
  const W = 360, H = 150, L = 44, R = 84, T = 12, B = 22;
  const vals = [0, ...stock.map((p) => p[1]), ...option.map((p) => p[1])];
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = Math.max((hi - lo) * 0.08, 0.005);
  lo -= pad; hi += pad;
  const days = Array.from(new Set([...stock, ...option].map((p) => p[0]))).sort();
  const n = Math.max(hold, days.length);
  const x = (d: string) => L + (days.indexOf(d) / Math.max(1, n - 1)) * (W - L - R);
  const y = (v: number) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const line = (pts: Pt[]) => pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
  const series = [
    { name: "Stock", pts: stock, cls: "stroke-text fill-text", dash: undefined },
    { name: "Option", pts: option, cls: "stroke-muted fill-muted", dash: "5 4" },
  ].filter((s) => s.pts.length);
  const ends = series.map((s) => ({ ...s, end: s.pts[s.pts.length - 1] }));
  if (ends.length === 2 && Math.abs(y(ends[0].end[1]) - y(ends[1].end[1])) < 14) {      // keep end labels apart
    const [a, b] = y(ends[0].end[1]) <= y(ends[1].end[1]) ? [0, 1] : [1, 0];
    (ends[a] as { ly?: number }).ly = y(ends[a].end[1]) - 7;
    (ends[b] as { ly?: number }).ly = y(ends[b].end[1]) + 7;
  }
  const short = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return (
    <figure className="m-0">
      <figcaption className="flex gap-4 text-xs text-muted">
        <span className="flex items-center gap-1"><svg width="18" height="6" aria-hidden><line x1="0" y1="3" x2="18" y2="3" className="stroke-text" strokeWidth="2" /></svg>Stock</span>
        {option.length > 0 && <span className="flex items-center gap-1"><svg width="18" height="6" aria-hidden><line x1="0" y1="3" x2="18" y2="3" className="stroke-muted" strokeWidth="2" strokeDasharray="5 4" /></svg>Whale&apos;s option</span>}
        <span>Total % from what you paid, at each close, after costs</span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 w-full max-w-[420px]" role="img"
        aria-label={`Path over ${plural(days.length, "session")}. ${ends.map((e) => `${e.name} ended ${pct(e.end[1])}`).join(", ")}.`}>
        {[hi - pad, 0, lo + pad].filter((v) => v === 0 || Math.abs(y(v) - y(0)) >= 12).map((v, i) => (   // no label on top of 0%
          <g key={i}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="stroke-line" strokeWidth={v === 0 ? 1.5 : 1} />
            <text x={L - 6} y={y(v) + 4} textAnchor="end" className="fill-muted text-[11px]">{pct(v, 0)}</text>
          </g>
        ))}
        {days.map((d) => <text key={d} x={x(d)} y={H - 6} textAnchor="middle" className="fill-muted text-[11px]">{short(d)}</text>)}
        {series.map((s) => (
          <g key={s.name}>
            <path d={line(s.pts)} className={s.cls.split(" ")[0]} fill="none" strokeWidth="2" strokeDasharray={s.dash} strokeLinejoin="round" />
            {s.pts.map((p) => (
              <circle key={p[0]} cx={x(p[0])} cy={y(p[1])} r="4" className={`${s.cls.split(" ")[1]} stroke-panel`} strokeWidth="2">
                <title>{`${s.name} ${short(p[0])}: ${pct(p[1])}`}</title>
              </circle>
            ))}
          </g>
        ))}
        {ends.map((e) => (
          <text key={e.name} x={x(e.end[0]) + 8} y={((e as { ly?: number }).ly ?? y(e.end[1])) + 4} className="fill-text text-[11px]">
            {e.name} {pct(e.end[1])}
          </text>
        ))}
      </svg>
    </figure>
  );
}
