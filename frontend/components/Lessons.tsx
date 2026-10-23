import { etTime, money, shortDate, plural } from "@/lib/format";
import { More } from "./v2/ui";

type Sum = { trades: number; taken?: number; base_1k?: number; rule_1k?: number; diff_1k?: number };
export type LessonsData = {
  frozen: { hash: string; frozen_at: string; git_sha: string } | null; changed_since_freeze: boolean; min_trades: number;
  rules: { key: string; text: string; forward: Sum;
    history: { history: Sum; helped_periods: number; voting_periods: number } | null }[];
};

const usd = (v: number | undefined) => v == null ? "–" : `${v >= 0 ? "+" : "−"}${money(Math.abs(v))}`;

/** Lessons from the record (owner 10-07): fixed "fixes" locked before they were run, scored on history (hindsight) and on
 *  signals decided after the lock (the fair test). Track record is where testing words belong. */
export default function Lessons({ d }: { d: LessonsData }) {
  if (!d.frozen) return null;
  const hist = d.rules.map((r) => r.history).filter((h) => h != null);
  const worse = hist.filter((h) => (h.history.diff_1k ?? 0) < 0).length;
  const base = hist[0]?.history.base_1k;
  const fwdN = Math.max(0, ...d.rules.map((r) => r.forward.trades));
  return (
    <div data-testid="lessons">   {/* continues the tracker's list of collapsibles right above */}
      <More title="Lessons from the record" note={<>Fixes a trader might reach for, written down and locked on {shortDate(d.frozen.frozen_at)} at {etTime(d.frozen.frozen_at)} before
        we ran any of them against the record. Every one stays on the list, good or bad.</>}>
      {d.changed_since_freeze && <p className="text-sm text-warn">These rules changed after the lock, so the forward column no longer counts as a fair test.</p>}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="border-b border-text text-left text-xs text-muted"><tr>
            <th className="py-2 pr-3 font-normal">Rule</th>
            <th className="py-2 pr-3 font-normal">History, $1,000 a trade{base != null && <> (as is: {usd(base)})</>}</th>
            <th className="py-2 pr-3 font-normal">Helped in</th>
            <th className="py-2 font-normal">Since the lock</th></tr></thead>
          <tbody>{d.rules.map((r) => {
            const h = r.history?.history, f = r.forward;
            return <tr key={r.key} className="border-b border-line align-top">
              <td className="py-2 pr-3">{r.text}</td>
              <td className="py-2 pr-3">{h ? <>{usd(h.rule_1k)} <span className={`text-xs ${(h.diff_1k ?? 0) >= 0 ? "text-bull" : "text-bear"}`}>({usd(h.diff_1k)})</span></> : "–"}</td>
              <td className="py-2 pr-3">{r.history ? `${r.history.helped_periods} of ${plural(r.history.voting_periods, "period")}` : "–"}</td>
              <td className="py-2">{f.trades === 0 ? <span className="text-muted">no finished signals yet</span>
                : <>{f.trades} trade{f.trades === 1 ? "" : "s"}, {usd(f.diff_1k)} vs as is
                  {f.trades < d.min_trades && <span className="block text-xs text-muted">too few to tell</span>}</>}</td>
            </tr>;
          })}</tbody>
        </table>
      </div>
      {hist.length > 0 && <p className="mt-3 max-w-[72ch] text-sm">
        {worse === hist.length
          ? <>In the history every one of these would have done worse than the plain five-day rule. They mostly make each trade smaller, which only helped in the period when the signals were losing. So far the lesson is to let the rule run.</>
          : <>{hist.length - worse} of {hist.length} would have beaten the plain rule in the history. That is a lead, not a change: only the forward column can confirm it.</>}
      </p>}
      <p className="mt-2 max-w-[72ch] text-xs text-muted">
        History is hindsight: we picked these rules after seeing those trades. The fair check is the signals that came after
        the lock on {shortDate(d.frozen.frozen_at)}: {fwdN} finished so far, and under {d.min_trades} is too few to tell. Rules
        like &ldquo;+5%&rdquo; assume a sale at exactly that price, which flatters them a little. None of this changes the signal rules.
      </p>
      </More>
    </div>
  );
}
