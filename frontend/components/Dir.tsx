/** Direction is shown with a glyph and a word, never colour alone. */
export default function Dir({ d, compact = false }: { d: number; compact?: boolean }) {
  const bull = d > 0;
  return (
    <span className={`inline-flex items-baseline gap-1 text-[13px] font-semibold ${bull ? "text-bull" : "text-bear"}`}>
      <span aria-hidden className="text-[11px]">{bull ? "▲" : "▼"}</span>{compact ? (bull ? "Bull" : "Bear") : bull ? "Bullish" : "Bearish"}
    </span>
  );
}
