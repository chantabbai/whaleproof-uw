"use client";
import { useState } from "react";

export type CurvePoint = { d: string; eq: number; spy: number };

const fmtX = (v: number) => `$${v.toFixed(2)}`;
const fmtDate = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { month: "short", year: "numeric" });

/** $1 compounded: signals traded in stock (brass, solid) vs SPY buy-and-hold (blue, dashed). Window starts marked. */
export default function CompoundChart({ data, windows }: { data: CurvePoint[]; windows: [string, string][] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (data.length < 2) return null;
  const w = 640, h = 240, l = 40, r = 96, t = 20, b = 24;
  const hi = Math.max(...data.flatMap((p) => [p.eq, p.spy])), lo = Math.min(1, ...data.flatMap((p) => [p.eq, p.spy]));
  const x = (i: number) => l + (i / (data.length - 1)) * (w - l - r);
  const y = (v: number) => t + (1 - (v - lo) / (hi - lo || 1)) * (h - t - b);
  const path = (k: "eq" | "spy") => data.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[k]).toFixed(1)}`).join("");
  const ticks = [1, 2, 3, 4, 5, 6].filter((v) => v >= lo && v <= hi);
  const idxOf = (d: string) => data.findIndex((p) => p.d >= d);
  const last = data[data.length - 1], hp = hover === null ? null : data[hover];
  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * (w - l - r);
    setHover(Math.max(0, Math.min(data.length - 1, Math.round((px / (w - l - r)) * (data.length - 1)))));
  };
  return (
    <figure className="relative">
      <svg viewBox={`0 0 ${w} ${h}`} className="h-auto w-full" role="img"
        aria-label={`$1 traded in signals grew to ${fmtX(last.eq)}; SPY buy-and-hold grew to ${fmtX(last.spy)} (${fmtDate(data[0].d)} – ${fmtDate(last.d)})`}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={l} x2={w - r} y1={y(v)} y2={y(v)} stroke="var(--line)" strokeWidth={1} strokeDasharray={v === 1 ? undefined : "2 4"} />
            <text x={l - 6} y={y(v) + 3} textAnchor="end" fontSize={12} fill="var(--muted)">${v}</text>
          </g>
        ))}
        {windows.map(([name, start]) => {
          const i = idxOf(start);
          return i < 0 ? null : (
            <g key={name}>
              <line x1={x(i)} x2={x(i)} y1={t - 6} y2={h - b} stroke="var(--line)" strokeWidth={1} />
              <text x={x(i) + 3} y={t - 8} fontSize={12} fill="var(--muted)">{name}</text>
            </g>
          );
        })}
        <path d={path("spy")} fill="none" stroke="var(--bull)" strokeWidth={2} strokeDasharray="6 4" />
        <path d={path("eq")} fill="none" stroke="var(--brass)" strokeWidth={2} />
        <text x={w - r + 6} y={y(last.eq) + 4} fontSize={13} fill="var(--text)">Signals {fmtX(last.eq)}</text>
        <text x={w - r + 6} y={y(last.spy) + 4} fontSize={13} fill="var(--text)">SPY {fmtX(last.spy)}</text>
        <text x={l} y={h - 6} fontSize={12} fill="var(--muted)">{fmtDate(data[0].d)}</text>
        <text x={w - r} y={h - 6} fontSize={12} fill="var(--muted)" textAnchor="end">{fmtDate(last.d)}</text>
        {hp && hover !== null && (
          <g pointerEvents="none">
            <line x1={x(hover)} x2={x(hover)} y1={t} y2={h - b} stroke="var(--muted)" strokeWidth={1} />
            <circle cx={x(hover)} cy={y(hp.eq)} r={4} fill="var(--brass)" stroke="var(--panel)" strokeWidth={2} />
            <circle cx={x(hover)} cy={y(hp.spy)} r={4} fill="var(--bull)" stroke="var(--panel)" strokeWidth={2} />
          </g>
        )}
        <rect x={l} y={t} width={w - l - r} height={h - t - b} fill="transparent"
          onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
      </svg>
      {hp && hover !== null && (
        <div className="pointer-events-none absolute top-8 rounded border border-line bg-panel2 px-2 py-1 text-xs shadow"
          style={{ left: `${Math.min(70, (x(hover) / w) * 100)}%` }}>
          <div className="text-muted">week of {hp.d}</div>
          <div><span className="text-brass">━</span> Signals {fmtX(hp.eq)}</div>
          <div><span className="text-bull">┅</span> SPY {fmtX(hp.spy)}</div>
        </div>
      )}
      <figcaption className="mt-1 flex flex-wrap gap-x-4 text-xs text-muted">
        <span><span className="text-brass">━</span> Signals, bought as stock (5 rotating sleeves)</span>
        <span><span className="text-bull">┅</span> SPY buy-and-hold</span>
        <span>one point per week</span>
      </figcaption>
    </figure>
  );
}
