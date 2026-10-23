import Link from "next/link";
import FitOneLine from "./FitOneLine";

/** Shared pieces of the v2 look: big answer first, a few numbers, detail one click deeper. */
export function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="text-[15px] text-muted">{children}</p>;
}

/** `name` is the page name for screen readers (the visible headline is the answer, not the page title). */
export function Hero({ name, eyebrow, title, lead }: { name: string; eyebrow?: React.ReactNode; title: React.ReactNode; lead?: React.ReactNode }) {
  return (
    <header>
      {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
      <h1 className="mt-3 text-[40px] leading-[1.05] md:text-[56px]"><span className="sr-only">{name}: </span>{title}</h1>
      {lead && <p className="mt-4 max-w-[60ch] text-[17px] leading-relaxed text-muted">{lead}</p>}
    </header>
  );
}

/** Small teal wave before a heading (Sightings' whale theme, owner 10-07); decorative, hidden from screen readers. */
function Wave() {
  return <svg aria-hidden viewBox="0 0 28 12" className="mr-2.5 inline-block h-3 w-7 align-middle"><path d="M1 8 Q5 2 9 8 T17 8 T27 8" fill="none"
    stroke="var(--sea)" strokeWidth="2.5" strokeLinecap="round" opacity="0.8" /></svg>;
}

export function H2({ children, sub, wave = false }: { children: React.ReactNode; sub?: React.ReactNode; wave?: boolean }) {
  return (
    <div>
      <h2 className="text-[22px] font-bold" style={{ fontVariationSettings: '"wdth" 112' }}>{wave && <Wave />}{children}</h2>
      {sub && <p className="mt-1 max-w-[68ch] text-sm text-muted">{sub}</p>}
    </div>
  );
}

export function Block({ title, sub, children, id, wave = false }: { title: React.ReactNode; sub?: React.ReactNode; children: React.ReactNode; id?: string; wave?: boolean }) {
  return <section id={id} className="scroll-mt-36"><H2 sub={sub} wave={wave}>{title}</H2><div className="mt-5">{children}</div></section>;
}

/** A ledger row: one thick rule over the row, thin rules between figures. Numbers carry the weight, not boxes. */
export function Tiles({ children, cols = 4 }: { children: React.ReactNode; cols?: 3 | 4 }) {
  return (
    <dl className={`grid grid-cols-2 border-t-[3px] border-text ${cols === 3 ? "lg:grid-cols-3" : "lg:grid-cols-4"}
      [&>*]:min-w-0 [&>*]:border-line [&>*]:py-4 [&>*:nth-child(odd)]:pr-4 [&>*:nth-child(even)]:border-l [&>*:nth-child(even)]:pl-4
      lg:[&>*]:border-l lg:[&>*]:px-5 lg:[&>*:first-child]:border-l-0 lg:[&>*:first-child]:pl-0`}>{children}</dl>
  );
}

const ACCENT = { amber: "bg-amber", sea: "bg-sea", brass: "bg-marker" } as const;

export function Tile({ k, v, sub, href, tone, accent, fit = true }: { k: React.ReactNode; v: React.ReactNode; sub?: React.ReactNode; href?: string; tone?: "bull" | "bear" | null;
  accent?: keyof typeof ACCENT; fit?: boolean }) {
  const body = <>
    {accent && <span aria-hidden className={`-mt-4 mb-[14px] block h-0.5 w-full rounded-b opacity-80 ${ACCENT[accent]}`} />}
    <dt className="text-[13px] text-muted">{k}</dt>
    <dd className={`wide mt-2 break-words text-[24px] leading-none sm:text-[30px] md:text-[40px] ${tone === "bull" ? "text-bull" : tone === "bear" ? "text-bear" : ""}`}>{fit ? <FitOneLine>{v}</FitOneLine> : v}</dd>
    {sub && <dd className="mt-2 max-w-[36ch] text-[13px] leading-snug text-muted">{sub}</dd>}
  </>;
  return href ? <Link href={href} className="group block [&_dt]:underline-offset-4 [&_dt]:group-hover:underline">{body}</Link> : <div>{body}</div>;
}

export function More({ title, note, children, open = false, id }: { title: React.ReactNode; note?: React.ReactNode; children: React.ReactNode; open?: boolean; id?: string }) {
  return (
    <details id={id} open={open} className="group scroll-mt-36 border-b border-line py-4">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-[17px] font-semibold">
        {title}<span aria-hidden className="text-xl leading-none text-muted transition-transform duration-200 group-open:rotate-45">+</span></summary>
      {note && <p className="mt-1 max-w-[68ch] text-sm text-muted">{note}</p>}
      <div className="mt-4">{children}</div>
    </details>
  );
}

export function MoreList({ children }: { children: React.ReactNode }) {
  return <div className="border-t border-line">{children}</div>;
}

export function Pill({ children, tone }: { children: React.ReactNode; tone?: "bull" | "bear" | "mark" | null }) {
  const c = tone === "bull" ? "bg-bull-soft text-bull" : tone === "bear" ? "bg-bear-soft text-bear" : tone === "mark" ? "bg-marker text-[color:var(--marker-ink)]" : "bg-panel2";
  return <span className={`inline-block rounded-full px-3 py-1 text-sm font-semibold ${c}`}>{children}</span>;
}

export function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-md bg-panel2 p-5 ${className}`}>{children}</div>;
}
