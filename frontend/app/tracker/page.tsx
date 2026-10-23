import AutoRefresh from "@/components/AutoRefresh";
import EvidenceBadge from "@/components/v2/EvidenceBadge";
import Empty from "@/components/Empty";
import TrackerTable, { type TrackerData } from "@/components/TrackerTable";
import Lessons, { type LessonsData } from "@/components/Lessons";
import { get } from "@/lib/api";
import { etTime, pct, shortDate } from "@/lib/format";
import { Hero, More } from "@/components/v2/ui";

export default async function TrackerPage() {
  const [t, lessons] = await Promise.all([get<TrackerData>("/api/desk/tracker"), get<LessonsData>("/api/desk/tracker/lessons")]);
  if (!t) return <Empty>The WhaleProof API is not answering. Start it with <code>scripts/desk.sh up</code>, then reload.</Empty>;
  const u = t.last_close_update;
  const closed = t.rows.filter((r) => r.stock.status === "closed" && r.stock.vs_spy != null);
  const vs = closed.length ? closed.reduce((a, r) => a + (r.stock.vs_spy as number), 0) / closed.length : null;
  const missing = u ? u.bars_missing.length + u.options_missing.length : 0;
  return (
    <div>
      <AutoRefresh seconds={300} />
      <Hero name="Track record" eyebrow={t.history_loaded === false ? "Sessions fetched on this install" : "Since October 2023"}
        title={<>{t.rows.length.toLocaleString("en-US")} signals tracked. {vs != null && <>{pct(vs, 2)} a trade against the S&amp;P.</>}</>}
        lead={<>Every signal follows the same rule: in at the next open, out at the close of the fifth trading day, after costs. Next to it, how the whale&apos;s own option did. That&apos;s what happened, across every period including the one where the rules were picked.</>} />
      <div className="mt-4"><EvidenceBadge /></div>
      {t.history_loaded === false && (
        <p className="mt-3 max-w-[68ch] text-sm text-warn" role="note">History isn&apos;t loaded here. The quick start only fetches the last few sessions;
          run the history backfill (README, &ldquo;Run it yourself&rdquo;) for the full record.</p>
      )}
      <p className="mt-3 text-[13px] text-muted" role="status">
        Prices through the <strong className="text-text">{shortDate(t.priced_through)}</strong> close{u ? `, updated ${etTime(u.at)}` : ""}.
        {missing > 0 && ` Waiting on ${missing} price${missing === 1 ? "" : "s"}, retried every 30 minutes.`}
      </p>
      <TrackerTable data={t} />
      {lessons && <Lessons d={lessons} />}
      <div>{/* same list of collapsibles as the tracker's, no gap */}
        <More title="How results are measured">
          <p className="max-w-[72ch] text-sm text-muted">{t.note} The peak is the highest it got above what you paid during the hold, and the
            drawdown the lowest below. For the stock that uses daily highs and lows; for the option, each day&apos;s closing bid, which is what
            you could really have sold for. &ldquo;None&rdquo; means it never closed above (peak) or below (drawdown) what you paid. &ldquo;Not
            measured&rdquo; means UW had no trade on the entry day or no price on the exit day. We never guess those. Not financial advice.</p>
        </More>
      </div>
    </div>
  );
}
