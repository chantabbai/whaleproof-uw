import type { EarnLabel, EarnPast } from "@/lib/api";

// Cheap/fair/rich is about option price vs history, not direction: no bull/bear colours, and no highlighter (that marks
// alerts that passed the signal filter). The word carries the meaning.
// Owner 10-08 calm pass: cheap and rich as a soft pill, fair as plain grey text (11 bold "Rich" boxes in a column shouted).
const STYLE: Record<EarnLabel, string> = {
  cheap: "rounded-full border border-line bg-panel2 px-2.5 py-0.5 text-text", fair: "text-muted", rich: "rounded-full border border-line bg-panel2 px-2.5 py-0.5 text-text",
};
const WORD: Record<EarnLabel, string> = { cheap: "Cheap", fair: "Fair", rich: "Rich" };

export function EarnChip({ label }: { label: EarnLabel | null }) {
  if (!label) return <span className="text-xs text-muted">–</span>;
  return <span className={`inline-block text-xs font-semibold ${STYLE[label]}`}>{WORD[label]}</span>;
}

export const sideLabel = (t: string) =>
  t === "premarket" ? "Before open" : t === "postmarket" || t === "afterhours" ? "After close" : "Time not set";

/** Expected earnings move as a heat chip, the same steps as the Sightings earnings tiles: the bigger the move, the hotter. */
export const heatTier = (v: number) => (v >= 0.2 ? 3 : v >= 0.12 ? 2 : 1);
export const heat = (v: number) => ["", "bg-heat-1 text-heat-1-ink", "bg-heat-2 text-heat-2-ink", "bg-heat-3 text-heat-3-ink"][heatTier(v)];

/** ☀ before the open, ☾ after the close: the marks the Sightings earnings tiles use. */
export function When({ time, lower = false }: { time: string; lower?: boolean }) {
  const mark = time === "premarket" ? <span aria-hidden className="text-amber">☀ </span> : time === "postmarket" || time === "afterhours" ? <span aria-hidden className="text-sea">☾ </span> : null;
  return <>{mark}{lower ? sideLabel(time).toLowerCase() : sideLabel(time)}</>;
}

/** Key for the past-move bars, said the same way wherever they appear. */
export function BarsKey() {
  return <><span aria-hidden className="mr-1 inline-block h-2.5 w-1.5 rounded-sm bg-amber align-middle" />moved more than options priced in,{" "}
    <span aria-hidden className="mr-1 inline-block h-2.5 w-1.5 rounded-sm border border-muted align-middle" />less,{" "}
    <span aria-hidden className="mr-1 inline-block w-3 border-t border-dashed border-muted align-middle" />the move priced in now.</>;
}

/** The implied move as a heat chip (Sightings' earnings-tile shading). */
export function ImpliedChip({ v }: { v: number }) {
  return <span data-heat={heatTier(v)} className={`inline-block rounded-[5px] px-2 py-0.5 font-bold tabular-nums ${heat(v)}`}>{movePct(v)}</span>;
}

export const movePct = (v: number | null | undefined) => (v == null ? "–" : `±${(Math.abs(v) * 100).toFixed(1)}%`);

/** Past report moves as small bars (newest right): height = size of the move; solid (amber, not the down-orange) = beat that
 *  report's implied move, outline = fell short; dashed line = the implied move now. */
export function PastMoves({ history, implied }: { history: EarnPast[]; implied: number | null }) {
  if (history.length === 0) return <span className="text-xs text-muted">No past reports</span>;
  const rows = [...history].reverse();
  const top = Math.max(...rows.map((h) => Math.abs(h.actual)), implied ?? 0, 0.01);
  const H = 28;
  return (
    <span className="relative inline-flex h-7 items-end gap-1" role="img"
      aria-label={`Past moves: ${rows.map((h) => `${h.day} ${(h.actual * 100).toFixed(1)}%${h.beat == null ? "" : h.beat ? " beat implied" : " short of implied"}`).join("; ")}`}>
      {rows.map((h) => (
        <span key={h.day} title={`${h.day}: moved ${(h.actual * 100).toFixed(1)}%, options expected ${movePct(h.implied)}`}
          className={`w-2 rounded-sm border ${h.beat ? "border-amber bg-amber" : "border-muted bg-transparent"}`}
          style={{ height: `${Math.max(2, (Math.abs(h.actual) / top) * H)}px` }} />
      ))}
      {implied != null && implied <= top && (
        <span className="pointer-events-none absolute inset-x-0 border-t border-dashed border-muted" style={{ bottom: `${(implied / top) * H}px` }} />
      )}
    </span>
  );
}
