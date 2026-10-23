"use client";
/** Track-record charts for the Track record page (finished signals in the current filter).
 *  Distribution: share of trades per result bucket, stock vs the whale's option, ONE axis (both are % results).
 *  Month strip: average stock result per signal month, polarity colours (blue up / orange down) with ▲▼ in the readout,
 *  test periods as background bands, thin months faded.
 *  Identity is never colour alone: legend + stock solid brass (the filter's-picks colour, owner 10-08: not white) vs option grey; hover shows a readout line (no native-title wait). */
import { useState } from "react";
import { pct, plural } from "@/lib/format";
import { H2 } from "@/components/v2/ui";

const EDGES = [-1, -0.75, -0.5, -0.25, -0.1, -0.03, 0.03, 0.1, 0.25, 0.5, 1, Infinity];
const LABELS = ["−100…−75%", "−75…−50%", "−50…−25%", "−25…−10%", "−10…−3%", "−3…+3%", "+3…+10%", "+10…+25%", "+25…+50%",
  "+50…+100%", "over +100%"];
const FLAT = 5;                                            // the −3…+3% bucket

function buckets(v: number[]) {
  const n = new Array(LABELS.length).fill(0);
  for (const x of v) {
    let i = EDGES.findIndex((e, k) => k > 0 && x < e) - 1;
    if (i < 0) i = x < EDGES[0] ? 0 : LABELS.length - 1;
    n[i] += 1;
  }
  return n.map((c) => (v.length ? c / v.length : 0));
}

/** A bar with a 4px rounded data end and a square base, growing up (v ≥ 0) or down from the baseline. */
function bar(x: number, w: number, yVal: number, yBase: number) {
  const h = Math.abs(yBase - yVal);
  if (h < 0.5) return "";
  const r = Math.min(4, w / 2, h);
  if (yVal <= yBase)
    return `M${x},${yBase}V${yVal + r}Q${x},${yVal} ${x + r},${yVal}H${x + w - r}Q${x + w},${yVal} ${x + w},${yVal + r}V${yBase}Z`;
  return `M${x},${yBase}V${yVal - r}Q${x},${yVal} ${x + r},${yVal}H${x + w - r}Q${x + w},${yVal} ${x + w},${yVal - r}V${yBase}Z`;
}

const share = (a: number[], idx: number[]) => idx.reduce((t, i) => t + a[i], 0);
const p0 = (v: number) => `${Math.round(v * 100)}%`;

export function Distribution({ stock, option }: { stock: number[]; option: number[] }) {
  const [hi, setHi] = useState<number | null>(null);
  const s = buckets(stock), o = buckets(option);
  const W = 860, H = 220, L = 36, B = 22, T = 24, R = 8;
  const step = Math.max(...s, ...o) > 0.2 ? 0.1 : 0.05;
  const max = Math.max(step, Math.ceil(Math.max(...s, ...o) / step) * step);
  const bw = (W - L - R) / LABELS.length;
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  const ticks = Array.from({ length: Math.round(max / step) + 1 }, (_, i) => i * step);
  const xFlat = L + FLAT * bw;
  const readout = hi == null
    ? <>Stock: <b className="text-text">{p0(share(s, [4, 5, 6]))}</b> of trades ended within ±10%. Whale&apos;s option: <b className="text-text">{p0(share(o, [0, 1]))}</b> lost
        more than half, <b className="text-text">{p0(share(o, [10]))}</b> more than doubled.</>
    : <><b className="text-text">{LABELS[hi]}</b>: stock {p0(s[hi])} of trades, whale&apos;s option {p0(o[hi])}.</>;
  return (
    <figure className="m-0 min-w-0">
      <figcaption><H2 wave sub={<span className="flex flex-wrap items-center gap-x-4 gap-y-1">Result after five days, after costs.
        <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-brass" />Stock ({stock.length.toLocaleString("en-US")} trades)</span>
        <span className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-muted opacity-60" />Whale&apos;s option ({option.length.toLocaleString("en-US")} trades)</span></span>}>Where results landed</H2>
      </figcaption>
      <p className="mt-1 min-h-[2.5em] text-[13px] text-muted" aria-live="polite">{readout}</p>
      <div className="mt-1 overflow-x-auto"><svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[620px]" role="img" onMouseLeave={() => setHi(null)}
        aria-label={`Share of trades by result after five days. Stock: ${p0(share(s, [4, 5, 6]))} within plus or minus 10%. Whale's option: ${p0(share(o, [0, 1]))} lost more than half.`}>
        <rect x={xFlat} y={T} width={bw} height={H - T - B} className="fill-panel2" />
        <text x={xFlat - 8} y={T - 9} textAnchor="end" className="fill-muted text-[11px]">← lost money</text>
        <text x={xFlat + bw / 2} y={T - 9} textAnchor="middle" className="fill-muted text-[11px]">about flat</text>
        <text x={xFlat + bw + 8} y={T - 9} className="fill-muted text-[11px]">made money →</text>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="stroke-line" strokeWidth={v === 0 ? 1.5 : 1} />
            <text x={L - 6} y={y(v) + 3} textAnchor="end" className="fill-muted text-[11px]">{p0(v)}</text>
          </g>
        ))}
        {LABELS.map((lab, i) => {
          const x0 = L + i * bw, w = (bw - 14) / 2, dim = hi != null && hi !== i;
          return (
            <g key={lab} onMouseEnter={() => setHi(i)} className="cursor-default">
              <rect x={x0} y={T} width={bw} height={H - T} fill="transparent" />
              <path d={bar(x0 + 6, w, y(s[i]), y(0))} className="fill-brass" opacity={dim ? 0.35 : 1} />
              <path d={bar(x0 + 8 + w, w, y(o[i]), y(0))} className="fill-muted" opacity={dim ? 0.2 : 0.6} />
              <text x={x0 + bw / 2} y={H - B + 14} textAnchor="middle" className={`text-[11px] ${hi === i ? "fill-text" : "fill-muted"}`}>{lab}</text>
            </g>
          );
        })}
      </svg></div>
    </figure>
  );
}

const PERIODS: [string, string, string][] = [                                   // [first month, last month, name]
  ["2023-10", "2024-09", "Second sealed test"], ["2024-10", "2025-09", "Practice year"],
  ["2025-10", "2026-05", "Sealed test"], ["2026-06", "9999-12", "Recent months"],
];
const periodOf = (m: string) => PERIODS.find(([a, b]) => m >= a && m <= b)?.[2] ?? "";
const THIN = 5;

export function MonthStrip({ months }: { months: { m: string; avg: number; n: number }[] }) {
  const [hi, setHi] = useState<number | null>(null);
  if (!months.length) return null;
  const W = 860, H = 160, L = 36, T = 26, B = 22, R = 8;
  const lim = Math.max(0.02, Math.ceil(Math.max(...months.map((x) => Math.abs(x.avg))) * 100) / 100);
  const y = (v: number) => T + (1 - (v + lim) / (2 * lim)) * (H - T - B);
  const bw = (W - L - R) / months.length;
  const lab = (m: string) => new Date(`${m}-15T12:00:00`).toLocaleDateString("en-US", { month: "short", year: "2-digit" });
  const every = Math.ceil(months.length / 8);
  const bands = PERIODS.map(([, , name], k) => {
    const idx = months.map((x, i) => (periodOf(x.m) === name ? i : -1)).filter((i) => i >= 0);
    return idx.length ? { name, k, x: L + idx[0] * bw, w: idx.length * bw } : null;
  }).filter((b): b is NonNullable<typeof b> => !!b);
  const up = months.filter((x) => x.avg > 0).length;
  const h = hi == null ? null : months[hi];
  return (
    <figure className="m-0 min-w-0">
      <figcaption><H2 wave sub={<>Average stock result of each month&apos;s signals. Faded bars had fewer than {THIN} signals. The second sealed test is the older year, opened last.</>}>Month by month</H2></figcaption>
      <p className="mt-1 text-[13px] text-muted" aria-live="polite">{h
        ? <><b className="text-text">{lab(h.m)}</b> ({periodOf(h.m).toLowerCase()}): <span className={h.avg >= 0 ? "text-bull" : "text-bear"}>{h.avg >= 0 ? "▲" : "▼"} {pct(h.avg)}</span> average, {h.n} signal{h.n === 1 ? "" : "s"}.</>
        : <><b className="text-text">{up} of {months.length}</b> months averaged a gain. Hover a bar for the month.</>}</p>
      <div className="mt-1 overflow-x-auto"><svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[620px]" role="img" onMouseLeave={() => setHi(null)}
        aria-label={`${up} of ${plural(months.length, "month")} averaged a gain.`}>
        {bands.map((b) => (
          <g key={b.name}>
            {b.k % 2 === 1 && <rect x={b.x} y={T - 18} width={b.w} height={H - T - B + 18} className="fill-panel2" />}
            <text x={b.x + 6} y={T - 6} className="fill-muted text-[11px]">{b.name}</text>
          </g>
        ))}
        {[lim, 0, -lim].map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="stroke-line" strokeWidth={v === 0 ? 1.5 : 1} />
            <text x={L - 6} y={y(v) + 3} textAnchor="end" className="fill-muted text-[11px]">{v === 0 ? "0%" : pct(v, 0)}</text>
          </g>
        ))}
        {months.map((x, i) => {
          const op = (x.n < THIN ? 0.4 : 1) * (hi != null && hi !== i ? 0.45 : 1);
          return (
            <g key={x.m} onMouseEnter={() => setHi(i)}>
              <rect x={L + i * bw} y={T} width={bw} height={H - T - B} fill="transparent" />
              <path d={bar(L + i * bw + 2, Math.max(1, bw - 4), y(x.avg), y(0))} className={x.avg >= 0 ? "fill-bull" : "fill-bear"} opacity={op} />
              {i % every === 0 && <text x={L + i * bw + bw / 2} y={H - 6} textAnchor="middle" className="fill-muted text-[11px]">{lab(x.m)}</text>}
            </g>
          );
        })}
      </svg></div>
    </figure>
  );
}
