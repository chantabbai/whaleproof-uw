"use client";
import Link from "next/link";
import Logo from "./Logo";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

// Grouped by job: what's happening now, your own records, and how it was tested. A thin rule separates the groups.
const GROUPS = [
  [["/", "Sightings"], ["/market", "Market"], ["/earnings", "Earnings"], ["/bets", "Flow check"], ["/watchlist", "Watchlist"]],
  [["/journal", "Journal"], ["/tracker", "Track record"]],
  [["/methodology", "How it works"]],
] as const;

export default function Nav() {
  const path = usePathname();
  return (
    <nav aria-label="Sections" className="flex flex-wrap items-center gap-x-6 gap-y-3">
      <Link href="/" className="wide flex items-center gap-2 text-[22px] leading-none" title="WhaleProof home">
        <Logo size={26} />
        WhaleProof
      </Link>
      <ul className="order-last -mx-4 flex w-[calc(100%+2rem)] snap-x items-center gap-1 overflow-x-auto px-4 text-[14px] [scrollbar-width:none] lg:order-none lg:mx-0 lg:w-auto lg:min-w-0 lg:flex-1 lg:overflow-visible lg:px-0">
        {GROUPS.flatMap((group, gi) => group.map(([href, label], i) => {
          const on = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <li key={href} className={`shrink-0 snap-start ${gi > 0 && i === 0 ? "ml-2 border-l border-line pl-2" : ""}`}>
              <Link href={href} aria-current={on ? "page" : undefined}
                className={`block whitespace-nowrap rounded-full px-3 py-1.5 transition-colors duration-150 ${on ? "bg-[var(--text)] font-semibold text-[color:var(--sheet)]" : "text-muted hover:bg-panel2 hover:text-text"}`}>
                {label}
              </Link>
            </li>
          );
        }))}
      </ul>
      <JumpTo />
    </nav>
  );
}

/** Type a symbol, press Enter, land on its page. */
function JumpTo() {
  const router = useRouter();
  const [v, setV] = useState("");
  return (
    <form role="search" aria-label="Jump to a symbol" className="ml-auto"
      onSubmit={(e) => { e.preventDefault(); const t = v.trim().toUpperCase(); if (/^[A-Z][A-Z0-9.\-]{0,9}$/.test(t)) { router.push(`/ticker/${t}`); setV(""); } }}>
      <input aria-label="Jump to a symbol" value={v} onChange={(e) => setV(e.target.value)} placeholder="Jump to NVDA…" autoCapitalize="characters"
        className="w-36 rounded-full border border-line bg-transparent px-3 py-1.5 text-[13px] uppercase placeholder:normal-case focus:border-text focus:outline-none" />
    </form>
  );
}
