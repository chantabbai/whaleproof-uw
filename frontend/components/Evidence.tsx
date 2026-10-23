import type { EvWindow } from "@/lib/api";
import { num, pct, plainPct } from "@/lib/format";

/** Headline evidence: filtered signals vs every directional alert, per validation window, never mixed. */
export default function Evidence({ pre = null, train, holdout, post, live = null }: { pre?: EvWindow; train: EvWindow; holdout: EvWindow; post: EvWindow; live?: EvWindow }) {
  const rows = [["Second sealed test", "Oct 2023 to Sep 2024. An older year, opened once.", pre], ["Practice year", "Oct 2024 to Sep 2025. The rules were chosen here.", train],
    ["Sealed test", "Oct 2025 to May 2026. Rules locked first, then opened once.", holdout], ["Recent months", "Jun to Sep 2026. We'd seen these before the rules were locked.", post],
    ["Live trading", "Since Sep 30, 2026. Signals nobody had seen when the rules were set.", live]] as const;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[680px] text-sm">
        <caption className="max-w-[80ch] pb-3 text-left text-[13px] text-muted">
          How much the stock beat the S&amp;P 500 over the five days after the signal, buying at the next open and paying 0.10% in costs.
          &ldquo;Per trade&rdquo; counts every signal once. &ldquo;Per day&rdquo; averages each day first and shows the range the real number
          probably sits in. If that range includes zero, it could still be luck.
        </caption>
        <thead className="border-b border-text text-left text-xs text-muted">
          <tr><th className="py-2 pr-4 font-normal">Period</th><th className="px-2 font-normal">Alerts a day, then signals a day</th>
            <th className="px-2 font-normal">Every UW alert, no filter</th><th className="px-2 font-normal">Signals, per trade</th><th className="px-2 font-normal">Signals, per day (likely range)</th>
            <th className="px-2 font-normal">Signals that won</th><th className="px-2 font-normal">Signals traded</th></tr>
        </thead>
        <tbody>
          {rows.map(([name, sub, w]) => w && (
            <tr key={name} className="border-t border-line">
              <td className="py-2.5 pr-4"><span className="font-semibold">{name}</span><span className="block text-xs text-muted">{sub}</span>
                {w.signals.n < 30 && <span className="block text-xs text-warn">{w.signals.n ? `${w.signals.n} finished: too few to tell` : "No finished trades yet"}</span>}
                {!!w.open && <span className="block text-xs text-muted">{num(w.open)} UW alerts (no-filter column) still in their five days</span>}
                {!!w.unpriced && <span className="block text-xs text-muted">{num(w.unpriced)} UW alerts (no-filter column) still waiting on prices</span>}</td>
              <td className="px-2">{num(w.funnel.per_day.raw)}, then <span className="font-semibold">{num(w.funnel.per_day.signals, 1)}</span></td>
              <td className="px-2">{w.all.n ? pct(w.all.mean, 2) : "–"}</td>
              <td className={`px-2 font-semibold ${(w.signals.mean ?? 0) >= 0 ? "text-bull" : "text-bear"}`}>{w.signals.n ? <>{(w.signals.mean ?? 0) >= 0 ? "▲" : "▼"} {pct(w.signals.mean, 2)}</> : "–"}</td>
              <td className="px-2">{w.signals.n ? pct(w.signals.day_mean, 2) : "–"}{w.signals.ci_low != null && <span className="block text-xs text-muted">{pct(w.signals.ci_low, 2)} to {pct(w.signals.ci_high, 2)}</span>}</td>
              <td className="px-2">{plainPct(w.signals.win_rate)}</td>
              <td className="px-2">{num(w.signals.n)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
