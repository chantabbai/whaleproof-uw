import type { Funnel } from "@/lib/api";
import { num } from "@/lib/format";

/** The filter, told as a sentence and then step by step. Bar width = share of the raw alert count (square-root scaled so
 *  the last step stays visible). Only the final count gets the highlighter. */
const STEPS: { key: keyof Funnel; label: string; removed: string }[] = [
  { key: "raw", label: "alerts over $100K", removed: "Everything Unusual Whales flagged that day." },
  { key: "directional", label: "clear one-way bets", removed: "Repeats on the same stock merged. Mixed and multi-leg trades dropped." },
  { key: "clean", label: "new buys", removed: "Gone: sold options, closing trades, hedges, spreads, straddles, lottery tickets and deep in-the-money." },
  { key: "signals", label: "signals", removed: "Gone: puts, stocks under $5, earnings before the planned sell, and small near-the-money bets." },
];

export default function Sieve({ f, caption, day, average = false, bare = false }: { f: Funnel; caption?: string; day?: string; average?: boolean; bare?: boolean }) {
  return (
    <figure>
      {!bare && <p className="max-w-[38ch] text-[26px] leading-snug md:text-[28px]" style={{ fontVariationSettings: '"wdth" 110' }}>
        {average
          ? <>On an average day {num(f.raw)} whale alerts come in and <span className="mark font-bold">{num(f.signals)}</span> make it through.</>
          : <>{num(f.raw)} whale alerts came in{day ? ` on ${day}` : ""}. <span className="mark font-bold">{num(f.signals)}</span> made it through.</>}
      </p>}
      <ol className="mt-6 grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((s) => {
          const v = f[s.key];
          const w = Math.max(3, Math.sqrt(v / Math.max(f.raw, 1)) * 100);
          const last = s.key === "signals";
          return (
            <li key={s.key}>
              <div className="h-1.5 w-full bg-panel2"><div className={`sieve-bar h-1.5 ${last ? "bg-marker" : "bg-muted"}`} style={{ width: `${w}%` }} /></div>
              <p className="mt-2 text-sm"><span className="font-bold">{num(v)}</span> {s.label}</p>
              <p className="mt-0.5 text-[13px] leading-snug text-muted">{s.removed}</p>
            </li>
          );
        })}
      </ol>
      {caption && <figcaption className="mt-4 max-w-[68ch] text-[13px] text-muted">{caption}</figcaption>}
    </figure>
  );
}
