"use client";
import { useEffect, useRef, useState } from "react";
import type { Signal } from "@/lib/api";
import { contractLabel, etTime, IV_RV_CHEAP, IV_RV_RICH, lvl, money, num, plainPct, px, shortDate, md, days as nDays, dte, plural, earnWarnText } from "@/lib/format";
import { askShare } from "./BetLine";

const days = (a: string, b: string) => (Date.parse(b.slice(0, 10)) - Date.parse(a.slice(0, 10))) / 86_400_000;

type TagTone = "good" | "meh" | "warn" | "quiet";
const TAG: Record<TagTone, string> = {
  good: "border-sea/50 text-sea", meh: "border-amber/50 text-amber", warn: "border-warn/50 text-warn", quiet: "border-line text-muted" };
const Tag = ({ tone, children }: { tone: TagTone; children: React.ReactNode }) =>
  <span className={`whitespace-nowrap rounded-full border px-1.5 text-[11px] font-semibold leading-[18px] ${TAG[tone]}`}>{children}</span>;

/** One question, a one-line answer and a small picture; the explanation opens from the ⓘ (tap works on phones). */
function Box({ q, side, answer, info, children }: { q: string; side?: React.ReactNode; answer: React.ReactNode; info?: React.ReactNode; children?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-w-0 rounded-md bg-panel px-3.5 py-3">
      <div className="flex items-start justify-between gap-2 text-xs text-muted">
        <span className="flex items-center gap-1"><span>{q}</span>
          {/* tooltip: hover or keyboard focus on desktop, tap on phones; floats, so the box never changes size */}
          {info && <span className="group relative" onMouseLeave={() => setOpen(false)}>
            <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} aria-label={`More on: ${q}`}
              className="inline-flex h-[15px] w-[15px] items-center justify-center rounded-full border border-line text-[10px] hover:border-text">i</button>
            <span role="tooltip" className={`absolute left-1/2 top-5 z-20 w-64 -translate-x-1/2 rounded-md border border-line bg-panel2 p-2.5 text-xs leading-snug text-text shadow-xl
              ${open ? "block" : "hidden group-hover:block group-focus-within:block"}`}>{info}</span>
          </span>}</span>
        {side && <span className="flex flex-wrap justify-end gap-1">{side}</span>}
      </div>
      <div className="mt-0.5 text-sm font-semibold">{answer}</div>
      {children}
    </div>
  );
}

type Pt = { v: number; label: string; tone: string; dot?: boolean };
/** Neighbouring labels on one side of the line that would overlap become one label ("put wall 70 · call wall 75").
 *  Overlap is judged in pixels: the line's real width and each label's length (≈ 6.5px a character at 11px). */
const CH = 6.5, GAP = 10, EDGE = 40;
function merge(row: Pt[], lo: number, hi: number, pad: number, w: number) {
  const span = hi - lo + 2 * pad;
  const x = (v: number) => Math.min(Math.max(((v - lo + pad) / span) * w, EDGE), w - EDGE);
  const out: { key: string; v: number; label: string; tone: string; dot?: boolean }[] = [];
  for (const p of [...row].sort((a, b) => a.v - b.v)) {
    const last = out[out.length - 1];
    if (last && x(p.v) - x(last.v) < ((last.label.length + p.label.length) / 2) * CH + GAP) {
      last.label += ` · ${p.label}`; last.v = (last.v + p.v) / 2; last.key += p.label;
    } else out.push({ key: p.label, v: p.v, label: p.label, tone: p.tone, dot: p.dot });
  }
  return out;
}

/** A horizontal price line with labelled points; positions scale to the points' own range. */
function Line({ pts, zone }: { pts: Pt[]; zone?: [number, number] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(320);                // phone-ish until measured
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth || 320)); ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const vs = pts.map((p) => p.v);
  const lo = Math.min(...vs), hi = Math.max(...vs), pad = (hi - lo) * 0.08 || 1;
  const at = (v: number) => `${((v - lo + pad) / (hi - lo + 2 * pad)) * 100}%`;
  // a label's centre stays at least half its width (≈ 5.8px a character) from either edge, so it never leaves the box
  const inside = (v: number, label: string) => {
    const half = (label.length * 5.8) / 2 + 2;
    return `${Math.min(Math.max(((v - lo + pad) / (hi - lo + 2 * pad)) * w, half), Math.max(w - half, half))}px`;
  };
  return (
    <div ref={ref} className="relative mt-1 h-[46px]" aria-hidden>
      <span className="absolute inset-x-0 top-[21px] h-0.5 rounded bg-line" />
      {zone && <span className="absolute top-[20px] h-1 rounded bg-gradient-to-r from-bull to-marker opacity-60"
        style={{ left: at(Math.min(...zone)), width: `calc(${at(Math.max(...zone))} - ${at(Math.min(...zone))})` }} />}
      {pts.map((p) => p.dot
        ? <span key={p.label} className={`absolute top-[16px] h-[11px] w-[11px] -translate-x-1/2 rounded-full border-2 border-panel ${p.tone.replace("text-", "bg-")}`} style={{ left: at(p.v) }} />
        : <span key={p.label} className="absolute top-[16px] h-3 w-0.5 -translate-x-1/2 bg-muted" style={{ left: at(p.v) }} />)}
      {/* walls label above the line, the stock and the strike below; labels that would touch merge into one */}
      {[pts.filter((p) => !p.dot), pts.filter((p) => p.dot)].flatMap((row) => merge(row, lo, hi, pad, w)).map((g) =>
        <span key={g.key} className={`absolute -translate-x-1/2 whitespace-nowrap text-[11px] ${g.dot ? "top-[30px]" : "top-0"} ${g.tone}`}
          style={{ left: inside(g.v, g.label) }}>{g.label}</span>)}
    </div>
  );
}

/** The full signal card, compact (owner 10-07): four questions in a 2×2 grid, then the reasons as ✓ chips. */
export default function SignalDetail({ s }: { s: Signal }) {
  const v = s.value && s.value.verdict !== "unknown" ? s.value : null;
  const rank = v?.iv_rank ?? s.iv_rank ?? null;
  const ivrv = v?.iv_rv ?? null;
  const ask = askShare(s);
  const g = s.gex && !s.gex_stale ? s.gex : null;
  const oi = s.oi;
  const acc = s.accumulation;
  const now = s.price_now ?? s.last_price ?? null;

  // a wall more than 20% from the stock (UW's put wall can sit far below) would squash the line; name it instead
  const near = (v: number) => Math.abs(v / s.spot_at_alert - 1) <= 0.2;
  const far = [g?.put_wall && !near(g.put_wall) ? `put wall (${px(g.put_wall)})` : "",
    g?.call_wall && !near(g.call_wall) ? `call wall (${px(g.call_wall)})` : ""].filter(Boolean).map((w, i) => `${i ? "the" : "The"} ${w}`);
  const where = (
    <Box q="Where is the bet?" side={<span className="text-xs text-muted">{px(s.strike)} {s.kind} · {dte(s.dte)}</span>}
      answer={s.otm_pct >= 0.01 ? <>Needs <span className="text-brass">{s.kind === "put" ? "−" : "+"}{plainPct(s.otm_pct)}</span> to the strike</> : "Strike near the stock price"}
      info={<>{contractLabel(s.contract)}. Stock {px(s.spot_at_alert)} when the whale bought{now != null ? `, ${px(now)} now` : ""}.
        {g && <> Gamma levels from {shortDate(s.gex_date)}: a {s.kind === "put" ? "put wall can slow a drop below it" : "call wall can slow a run above it"}.</>}
        {far.length > 0 && <> {far.join(" and ")} {far.length === 1 ? "is" : "are"} more than 20% from the stock, so {far.length === 1 ? "it's" : "they're"} left off the line.</>}
        {s.dp_levels && s.dp_levels.length > 0 && !s.dp_stale && <> Dark-pool levels: {s.dp_levels.map((l) => px(l[0])).join(", ")}.</>}</>}>
      <Line zone={[s.spot_at_alert, s.strike]} pts={[
        ...(g?.put_wall && near(g.put_wall) ? [{ v: g.put_wall, label: `put wall ${lvl(g.put_wall)}`, tone: "text-muted" }] : []),
        { v: s.spot_at_alert, label: lvl(s.spot_at_alert), tone: "text-bull", dot: true },
        { v: s.strike, label: `strike ${lvl(s.strike)}`, tone: "text-brass", dot: true },
        ...(g?.call_wall && near(g.call_wall) ? [{ v: g.call_wall, label: `call wall ${lvl(g.call_wall)}`, tone: "text-muted" }] : []),
      ]} />
    </Box>
  );

  const fair = (
    <Box q="Fair price?" side={<>
        {v && <Tag tone={v.verdict === "cheap" ? "good" : v.verdict === "rich" ? "warn" : "quiet"}>{v.verdict}</Tag>}
        {ivrv != null && ivrv > IV_RV_RICH && <Tag tone="meh">pricey vs moves</Tag>}
        {ivrv != null && ivrv < IV_RV_CHEAP && <Tag tone="good">cheap vs moves</Tag>}</>}
      answer={rank != null ? <>IV rank {rank.toFixed(0)} of 100</> : <span className="text-muted">Not enough volatility history</span>}
      info={v?.iv != null && v?.rv != null ? <>Implied vol {plainPct(v.iv)} vs {plainPct(v.rv)} realized lately ({ivrv?.toFixed(2)}×):
        {ivrv != null && ivrv > IV_RV_RICH ? " options price a bigger move than the stock has made." : ivrv != null && ivrv < IV_RV_CHEAP ? " options price a smaller move than the stock has made." : " about in line with how much it moves."}</> : undefined}>
      {rank != null && <>
        <div className="relative mt-3 h-[5px] rounded-full bg-gradient-to-r from-sea/40 via-line to-bear/40" aria-hidden>
          <span className="absolute -top-1 h-[13px] w-[3px] -translate-x-1/2 rounded bg-text" style={{ left: `${Math.min(100, Math.max(0, rank))}%` }} /></div>
        <div className="mt-1 flex justify-between text-[11px] text-muted" aria-hidden><span>cheap</span><span>rich</span></div></>}
    </Box>
  );

  const still = s.watch_only ? null : (
    <Box q="Whale still in?" side={oi?.confirmed === true ? <Tag tone="good">stayed open ✓</Tag> : oi?.confirmed === false ? <Tag tone="warn">may have closed</Tag>
        : <Tag tone="quiet">checked next morning</Tag>}
      answer={<>{oi?.latest ? <>Open interest {num(oi.latest.oi)}</> : "Open interest not in yet"}
        {acc && <span className="font-normal text-muted"> · {acc.buys <= 1 ? `only this buy in ${nDays(acc.sessions)}` : `${acc.buys} buys over ${nDays(acc.days)}, ${money(acc.premium)}`}</span>}</>}
      info={<>{oi?.next_morning ? `Open interest ${oi.next_morning.change >= 0 ? "up" : "down"} ${plural(Math.abs(oi.next_morning.change), "contract")} the next morning${oi.next_morning.ratio != null ? ` (${num(oi.next_morning.ratio, 1)}× the whale's size)` : ""}. ` : "Open interest updates around 6:45 AM ET. "}
        {s.quote && (s.quote.bid != null || s.quote.ask != null) && <>The whale&apos;s option at {etTime(s.quote.at)}: {px(s.quote.bid)} bid, {px(s.quote.ask)} ask{s.quote.volume != null ? `, ${num(Number(s.quote.volume))} traded` : ""}. </>}
        The stock captured the move the flow pointed to; the whale&apos;s exact option usually gave it back to the spread and time decay (<a href="/methodology" className="underline">why</a>).</>}>
      {oi && oi.trail.length > 1 && (() => {
        const top = Math.max(...oi.trail.map((p) => p.oi)) || 1;
        return <div className="mt-2 flex h-8 items-end gap-1.5" aria-hidden>{oi.trail.map((p, i) => (
          <span key={p.date} title={`${md(p.date)}: ${num(p.oi)}`} className={`w-5 rounded-t-sm ${i === oi.trail.length - 1 ? "bg-bull" : "bg-bull/35"}`}
            style={{ height: `${Math.max(8, (p.oi / top) * 100)}%` }} />))}<span className="ml-1 text-[11px] text-muted">{oi.trail.map((p) => md(p.date)).join(" → ")}</span></div>;
      })()}
    </Box>
  );

  const ne = s.next_earnings;
  // the API warns about any report within 10 days; only one before the sell is "in the hold" (an after-the-close
  // report on the sell day comes after the sale). AXTI 10-20: hold Oct 20–26, report Oct 29 was tagged "in the hold".
  const ew = s.earnings_warning;
  const warn = ew && (ew.date < s.exit_by || (ew.date === s.exit_by && ew.time !== "postmarket")) ? ew : null;
  const way = s.watch_only ? (
    <Box q="Watch only" answer={<span className="font-normal">No buy or sell dates for this one.</span>}
      info="Most big put buys are insurance on stock people already own, so they aren't part of the signal rules." />
  ) : (
    <Box q="Anything in the way?" side={warn ? <Tag tone="warn">earnings in the hold</Tag> : <Tag tone="good">clear</Tag>}
      answer={warn ? earnWarnText(warn) : ne ? <>Earnings {md(ne.date)}, after the sell</> : "No earnings date known"}>
      {(() => {
        const e = (warn?.date ?? ne?.date) || null;
        const span = Math.max(days(s.entry, s.exit_by) * 1.6, e ? Math.min(days(s.entry, e), 60) + 4 : 0, 10);
        const at = (d: string) => `${Math.min(96, 3 + (days(s.entry, d) / span) * 92)}%`;
        return <div className="relative mt-2 h-[30px]" aria-hidden>
          <span className="absolute inset-x-0 top-[9px] h-0.5 rounded bg-line" />
          <span className="absolute top-[8px] h-1 rounded bg-bull opacity-70" style={{ left: at(s.entry), width: `calc(${at(s.exit_by)} - ${at(s.entry)})` }} />
          <span className="absolute top-[18px] -translate-x-0 whitespace-nowrap text-[11px] text-bull" style={{ left: at(s.entry) }}>hold {md(s.entry)}–{md(s.exit_by)}</span>
          {e && <><span className={`absolute top-[5px] h-[10px] w-[10px] -translate-x-1/2 rounded-full ${warn ? "bg-warn" : "bg-amber"}`} style={{ left: at(e) }} />
            <span className={`absolute top-[18px] -translate-x-1/2 whitespace-nowrap text-[11px] ${warn ? "text-warn" : "text-amber"}`}
              style={{ left: `clamp(3rem, ${at(e)}, calc(100% - 3rem))` }}>earnings {md(e)}{days(s.entry, e) > 60 ? " →" : ""}</span></>}
        </div>;
      })()}
    </Box>
  );

  const checks = [
    `${money(s.premium)}${ask === 100 ? ", all at the ask" : ask != null ? `, ${ask}% at the ask` : ""}`,
    s.why[0]?.includes("one leg") ? "one leg, new position" : null,
    s.otm_pct >= 0.01 ? `${plainPct(s.otm_pct)} out of the money` : null,
    s.dte === 0 ? "expires today" : `${nDays(s.dte)} to expiry`,
    v?.verdict === "cheap" ? "cheap by IV rank" : null,
    !s.watch_only && !s.earnings_warning ? "no earnings in the hold" : null,
  ].filter(Boolean) as string[];

  return (
    <div>
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">{where}{fair}{still}{way}</div>
      <p className="mt-3 text-[13px] font-semibold text-muted">{s.watch_only ? "Why it's on the watch list" : "Why it made the cut"}</p>
      <details className="group mt-1.5">
        <summary className="flex cursor-pointer list-none flex-wrap gap-1.5">
          {checks.map((c) => <span key={c} className="rounded-full border border-sea/40 px-2.5 py-0.5 text-[13px]"><span className="font-bold text-sea">✓</span> {c}</span>)}
          <span className="self-center text-xs text-muted underline-offset-4 group-open:hidden hover:underline">full reasons</span>
        </summary>
        <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm">{s.why.filter((w) => !(s.watch_only && /planned sell/.test(w))).map((w) => <li key={w}>{w}</li>)}</ul>
      </details>
    </div>
  );
}
