/** WhaleProof mark (owner 10-07, "funnel of squares"): rows of grey alerts narrow 4 → 3 → 2 down to one yellow signal,
 *  the filter drawn. Greys follow the theme (Haystack shades), the signal is the highlighter yellow. */
export default function Logo({ size = 22 }: { size?: number }) {
  const rows = [[0, 1, 2, 3], [0.5, 1.5, 2.5], [1, 2]];
  return (
    <svg aria-hidden viewBox="0 0 4 4" width={size} height={size} className="shrink-0">
      {rows.map((r, y) => r.map((x) => (
        <rect key={`${x}-${y}`} x={x + 0.12} y={y + 0.12} width={0.76} height={0.76} rx={0.12}
          fill="var(--hay-1)" opacity={y === 0 ? 0.45 : 0.8} />)))}
      <rect x={1.62} y={3.12} width={0.76} height={0.76} rx={0.12} fill="var(--marker)" />
    </svg>
  );
}
