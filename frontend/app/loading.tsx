/** Shown while a page's data loads: grey shapes in the page's own layout (headline, four figures, a section), so the
 *  page does not jump when the numbers land. */
export default function Loading() {
  return (
    <div aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading…</span>
      <div aria-hidden>
        <div className="skel h-4 w-48" />
        <div className="skel mt-5 h-10 w-full max-w-[640px] md:h-14" />
        <div className="skel mt-3 h-10 w-2/3 max-w-[420px] md:h-14" />
        <div className="skel mt-6 h-4 w-full max-w-[560px]" />
        <div className="mt-10 grid grid-cols-2 gap-4 border-t-[3px] border-line pt-4 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <div key={i}><div className="skel h-3 w-24" /><div className="skel mt-3 h-9 w-32" /></div>)}
        </div>
        <div className="skel mt-12 h-6 w-56" />
        <div className="mt-5 space-y-3">{[0, 1, 2, 3].map((i) => <div key={i} className="skel h-14 w-full" />)}</div>
      </div>
    </div>
  );
}
