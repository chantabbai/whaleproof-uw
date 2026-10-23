"use client";
import { useState } from "react";

type Level = { v: number; label: string; tone: "bull" | "bear" | "muted" | "brass" };

const COLOR = { bull: "var(--bull)", bear: "var(--bear)", muted: "var(--muted)", brass: "var(--brass)" };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const SESSIONS = 63;             // about three months: enough to see the run-up, levels stay readable

/** Round price steps (1, 2, 2.5, 5 × 10^k) giving about `n` gridlines between lo and hi. */
export function niceTicks(lo: number, hi: number, n = 5): number[] {
  const raw = (hi - lo) / n || 1;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}

const md = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
const money = (v: number) => (v >= 1000 || Number.isInteger(v) ? v.toFixed(0) : v.toFixed(2));
const SHORT: Record<string, string> = { "dark-pool level": "dark pool" };

/** Daily closes for about three months, then today's levels (GEX walls, gamma flip, dark-pool level) in a strip at the
 *  right edge only: they are today's values, so they aren't drawn back through history. The put-wall to call-wall range
 *  is shaded in that strip. Levels within 0.6% of each other share one label. Labels wear text colours; a short colour
 *  tick carries identity. Hover the line for the date and close.
 *  liveNow: the last point is today's live price (market open), so it is labelled "now", not "last close". */
export default function PriceChart({ bars: all, levels = [], liveNow = false }: { bars: { date: string; close: number }[]; levels?: Level[]; liveNow?: boolean }) {
  const [hi, setHi] = useState<number | null>(null);
  if (all.length < 2) return <p className="text-sm text-muted">No price history cached for this ticker.</p>;
  const bars = all.slice(-SESSIONS);
  const W = 680, H = 280, L = 44, R = 168, T = 12, B = 24, STRIP = 46;   // plot x L..W-R; levels strip = last STRIP px
  const closes = bars.map((b) => b.close);
  const last = closes[closes.length - 1];
  const inView = levels.filter((l) => l.v >= last * 0.8 && l.v <= last * 1.2);
  const lo0 = Math.min(...closes, ...inView.map((l) => l.v)), hi0 = Math.max(...closes, ...inView.map((l) => l.v));
  const padV = (hi0 - lo0) * 0.06 || 1;
  const lo = lo0 - padV, top = hi0 + padV;
  const x1 = W - R - STRIP;                                               // the price line ends here; the strip is "today"
  const x = (i: number) => L + (i / (bars.length - 1)) * (x1 - L);
  const y = (v: number) => T + (1 - (v - lo) / (top - lo)) * (H - T - B);
  const d = bars.map((b, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(b.close).toFixed(1)}`).join("");
  const ticks = niceTicks(lo, top, 5);
  const months = bars.flatMap((b, i) => (i > 0 && b.date.slice(5, 7) !== bars[i - 1].date.slice(5, 7)
    ? [{ i, m: MONTHS[+b.date.slice(5, 7) - 1] }] : []));
  const put = inView.find((l) => l.label === "put wall"), call = inView.find((l) => l.label === "call wall");

  // labels: the price plus each level, merged when within 0.6%, then spaced at least 15 px apart
  const raw = [{ v: last, label: liveNow ? "now" : "last close", tone: "text" as const }, ...inView].sort((a, b) => b.v - a.v);
  const groups: { v: number; items: { v: number; label: string; tone: string }[] }[] = [];
  for (const l of raw) {
    const g = groups.at(-1);
    const isNow = (it: { tone: string }) => it.tone === "text";
    if (g && Math.abs(g.v / l.v - 1) < 0.006 && !isNow(l) && !g.items.some(isNow)) g.items.push(l);
    else groups.push({ v: l.v, items: [l] });
  }
  const named = groups.map((g) => {
    const vs = g.items.map((i) => i.v);
    const lo = money(Math.min(...vs)), hi = money(Math.max(...vs));
    const price = lo === hi ? lo : `${lo}–${hi}`;                       // two levels at one price read "230", not "230–230"
    return { v: g.v, label: `${price} ${g.items.map((i) => SHORT[i.label] ?? i.label).join(" + ")}`, tones: g.items.map((i) => i.tone) };
  });
  const tags = named.map((g) => ({ ...g, ty: y(g.v) }));
  let prev = -Infinity;
  for (const t of tags) { t.ty = Math.min(Math.max(t.ty, prev + 15), H - B); prev = t.ty; }
  const col = (tone: string) => (tone === "text" ? "var(--text)" : COLOR[tone as Level["tone"]]);
  const h = hi == null ? null : bars[hi];

  return (
    <figure className="m-0">
      <p className="min-h-[1.25em] text-[13px] text-muted" aria-live="polite">
        {h ? <><b className="text-text">{md(h.date)}</b>: close {money(h.close)}</> : <>Hover the line for any day&apos;s close.</>}</p>
      <div className="overflow-x-auto"><svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full min-w-[560px]" role="img" onMouseLeave={() => setHi(null)}
        aria-label={`Daily close from ${bars[0].date} to ${bars[bars.length - 1].date}, ${liveNow ? "now" : "last"} ${last.toFixed(2)}`}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="var(--line)" strokeWidth={1} opacity={0.6} />
            <text x={L - 6} y={y(v) + 4} textAnchor="end" fontSize={11} fill="var(--muted)">{v % 1 ? v.toFixed(2) : v}</text>
          </g>
        ))}
        {months.map(({ i, m }) => <text key={i} x={x(i)} y={H - 6} textAnchor="middle" fontSize={11} fill="var(--muted)">{m}</text>)}
        <text x={x1 + STRIP / 2} y={H - 6} textAnchor="middle" fontSize={11} fill="var(--muted)">today</text>
        <rect x={x1 + 4} y={T} width={STRIP - 4} height={H - T - B} fill="var(--sheet-2)" />
        {put && call && call.v > put.v && (
          <rect x={x1 + 4} y={y(call.v)} width={STRIP - 4} height={y(put.v) - y(call.v)} fill="var(--bull)" opacity={0.12} />
        )}
        {inView.map((l) => (
          <line key={l.label} x1={x1 + 4} x2={W - R} y1={y(l.v)} y2={y(l.v)} stroke={COLOR[l.tone]}
            strokeWidth={2} strokeDasharray={l.label === "gamma flip" ? "3 3" : undefined} />
        ))}
        <line x1={x(bars.length - 1)} x2={W - R} y1={y(last)} y2={y(last)} stroke="var(--text)" strokeWidth={1} strokeDasharray="2 3" />
        <path data-testid="price-line" d={d} fill="none" stroke="var(--muted)" strokeWidth={2} strokeLinejoin="round" />   {/* soft grey: the coloured levels carry the chart (owner 10-08) */}
        {h && <>
          <line x1={x(hi as number)} x2={x(hi as number)} y1={T} y2={H - B} stroke="var(--muted)" strokeWidth={1} />
          <circle cx={x(hi as number)} cy={y(h.close)} r={4} fill="var(--text)" stroke="var(--sheet)" strokeWidth={2} />
        </>}
        <circle cx={x(bars.length - 1)} cy={y(last)} r={4} fill="var(--text)" stroke="var(--sheet)" strokeWidth={2} />
        {bars.map((b, i) => (
          <rect key={b.date} x={x(i) - (x1 - L) / bars.length / 2} y={T} width={(x1 - L) / bars.length} height={H - T - B}
            fill="transparent" onMouseEnter={() => setHi(i)} />
        ))}
        {tags.map((t) => (
          <g key={t.label}>
            <line x1={W - R} x2={W - R + 8} y1={y(t.v)} y2={t.ty} stroke="var(--muted)" strokeWidth={1} />
            {t.tones.map((tone, k) => <rect key={k} x={W - R + 10 + k * 5} y={t.ty - 5} width={3} height={10} rx={1} fill={col(tone)} />)}
            <text x={W - R + 14 + (t.tones.length - 1) * 5} y={t.ty + 4} fontSize={11.5} fontWeight={t.tones.includes("text") ? 700 : 500}
              fill={t.tones.includes("text") ? "var(--text)" : "var(--muted)"}>{t.label}</text>
          </g>
        ))}
      </svg></div>
      <figcaption className="text-xs text-muted">Daily close, {md(bars[0].date)} to {md(bars[bars.length - 1].date)}. Levels are today&apos;s; the shaded band runs from the put wall to the call wall.</figcaption>
    </figure>
  );
}
