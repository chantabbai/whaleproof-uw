import Link from "next/link";
import { get, type Stats } from "@/lib/api";
import { EVIDENCE_LINK } from "@/lib/copy";

type W = { signals: Stats; all_directional: Stats } | null | undefined;
type M = { evidence: { preperiod_farotm?: W; preperiod?: W; train_post: { train: W; post: W } | null; holdout: W } };

/** The one caveat on a results page: the result first, "Backtested 2023–2026" after (owner 10-23, was "Not proven yet"), a link to how it was tested.
 *  Counts are read from the evidence files, so the badge can't drift from How it works. */
export default async function EvidenceBadge() {
  const m = await get<M>("/api/desk/methodology");
  const e = m?.evidence;
  if (!e?.train_post) return null;
  const ws = [e.preperiod_farotm ?? e.preperiod, e.train_post.train, e.holdout, e.train_post.post].filter((w): w is NonNullable<W> => !!w);
  const beat = ws.filter((w) => w.signals.mean != null && w.all_directional.mean != null && w.signals.mean > w.all_directional.mean).length;
  return (
    <Link href={EVIDENCE_LINK} className="inline-flex flex-wrap items-baseline gap-x-2 rounded-full border border-line px-3 py-1 text-[13px] hover:border-text">
      <span className="font-semibold text-text">Our shortlist of UW alerts added an edge in {beat} of {ws.length} test periods</span>
      <span className="text-muted">Backtested 2023–2026. See how it was tested →</span>
    </Link>
  );
}
