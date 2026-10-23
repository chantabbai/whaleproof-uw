import Link from "next/link";
import { UW_DATA } from "@/lib/copy";

const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

/** Site footer: what UW data the desk is built on (scannable chips), where the data lives, then the legal line set
 *  smaller and apart so it reads as fine print, not as part of the pitch. */
export default function Footer() {
  return (
    <footer className="mx-auto max-w-[1180px] px-4 pb-10 md:px-8">
      <div className="border-t border-line pt-6">
        <div className="grid gap-6 md:grid-cols-[1fr_auto] md:items-start">
          <section aria-labelledby="built-on">
            <h2 id="built-on" className="text-[13px] font-semibold text-muted [font-variation-settings:'wdth'_100]">
              Built on the Unusual Whales API
            </h2>
            <ul className="mt-2.5 flex flex-wrap gap-1.5" aria-label="Unusual Whales data used">
              {UW_DATA.map((d) => (
                <li key={d} className="rounded-full border border-line px-2.5 py-0.5 text-[12px] text-text">{cap(d)}</li>
              ))}
            </ul>
          </section>
          <div className="flex flex-col gap-2 text-[12px] text-muted md:items-end md:text-right">
            <p className="flex items-center gap-1.5">
              <svg aria-hidden viewBox="0 0 16 16" className="h-3.5 w-3.5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="7" width="10" height="7" rx="1.5" /><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
              </svg>
              Runs locally. Your data stays on this computer.
            </p>
            <p className="flex gap-3">
              <Link href="/methodology" className="tap underline decoration-line underline-offset-4 hover:text-text">How it works</Link>
              <Link href="/tracker" className="tap underline decoration-line underline-offset-4 hover:text-text">Track record</Link>
            </p>
          </div>
        </div>
        <div className="mt-6 border-t border-dashed border-line pt-4 text-[11px] leading-relaxed text-muted">
          <p className="max-w-[90ch]">For research and education only, not investment advice. Results are backtests and paper trades after estimated
          trading costs. Past performance does not guarantee future results. Stocks and options can lose money.</p>
        </div>
      </div>
    </footer>
  );
}
