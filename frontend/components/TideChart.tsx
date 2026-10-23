import type { TidePoint } from "@/lib/api";
import { etTime, signedMoney } from "@/lib/format";

/** Market tide: cumulative net call premium (blue, solid) vs net put premium (orange, dashed) through the session. */
export default function TideChart({ data, height = 140 }: { data: TidePoint[]; height?: number }) {
  if (data.length < 2) return <p className="text-sm text-muted">Nothing for this session yet.</p>;
  const w = 600, h = height, pad = 4;
  const vals = data.flatMap((d) => [d.call, d.put]);
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  const x = (i: number) => pad + (i / (data.length - 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - ((v - lo) / (hi - lo || 1)) * (h - 2 * pad);
  const line = (k: "call" | "put") => data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d[k]).toFixed(1)}`).join("");
  const last = data[data.length - 1];
  return (
    <figure>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-auto w-full" role="img"
        aria-label={`Market tide: net calls ${signedMoney(last.call)}, net puts ${signedMoney(last.put)} at ${etTime(last.t)}`}>
        <line x1={0} x2={w} y1={y(0)} y2={y(0)} stroke="var(--line)" strokeWidth={1} />
        <path d={line("call")} fill="none" stroke="var(--bull)" strokeWidth={2} />
        <path d={line("put")} fill="none" stroke="var(--bear)" strokeWidth={2} strokeDasharray="5 4" />
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-x-4 text-xs text-muted">
        <span><span className="text-bull">━ Calls</span> {signedMoney(last.call)}: {sideWords(last.call)}</span>
        <span><span className="text-bear">┅ Puts</span> {signedMoney(last.put)}: {sideWords(last.put)}</span>
        <span>at {etTime(last.t)}</span>
      </figcaption>
    </figure>
  );
}

/** Plain words for one line's running total (owner 10-08: "Calls −$466M" read as calls losing money). */
const sideWords = (v: number) => (v >= 0 ? "more bought than sold" : "more sold than bought");
