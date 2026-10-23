import Link from "next/link";
import type { EarnWarn } from "@/lib/api";
import { etTime, plainPct, shortDate } from "@/lib/format";
import { H2 } from "@/components/v2/ui";
import { heat } from "@/components/EarnBits";
import { topReporters } from "@/lib/reporters";

type Release = { et: string; event: string; forecast: string | null; prev: string | null };
type Reporter = { ticker: string; expected_move_perc: number | null; marketcap?: number | null };
export type EarnNext = { ticker: string; date: string; time: string } | null;

const when = (t: string) => (t === "premarket" ? "before the open" : t === "postmarket" ? "after the close" : "time not set");
/** UW sends plain numbers as strings ("15000000000"); show 15B. Anything else (1.3%, 48) passes through. */
const big = (v: string) => (/^-?\d+(\.\d+)?$/.test(v) && Math.abs(+v) >= 10_000
  ? new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(+v) : v).replace(/^-/, "−");
const weekday = (iso: string) => new Date(iso).toLocaleDateString("en-US", { timeZone: "America/New_York", weekday: "short" });

/** Small label + its rows, so the three lists read as one consistent block. */
function Part({ label, aside, children }: { label: string; aside?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="flex items-baseline justify-between gap-2 text-[13px] font-semibold text-muted"><span>{label}</span>
        {aside && <span className="font-normal">{aside}</span>}</h3>
      <div className="mt-2">{children}</div>
    </section>
  );
}

const rowCls = "grid items-baseline gap-x-3 py-2";

/** Releases that move the whole market; Fed speakers and small reports fold away (trader review 10-06). */
const KEY = /FOMC|Federal Open Market|rate decision|CPI|Consumer Price|PPI|Producer Price|Nonfarm|payroll|Unemployment|Jobless|JOLTS|GDP|PCE|Retail Sales|ISM|Michigan|Consumer Confidence|Powell/i;

/** Owner 10-07 colour pass: each of the next days gets its own pill colour, so the list reads by day at a glance. */
const DAY_PILL = ["bg-brass-soft text-brass", "bg-sea-soft text-sea", "bg-bull-soft text-bull"];

function ReleaseRow({ e, pill }: { e: Release; pill: string }) {
  return (
    <li className={`${rowCls} grid-cols-[4rem_1fr]`}>
      <span className={`self-start rounded-md py-1 text-center text-xs font-semibold ${pill}`}>{weekday(e.et)}
        <span className="block font-normal">{etTime(e.et).replace(" ET", "")}</span></span>
      <span>{e.event}
        {(e.forecast || e.prev) && <span className="block text-xs text-muted">
          {[e.forecast && `Forecast ${big(e.forecast)}`, e.prev && `last ${big(e.prev)}`].filter(Boolean).join(", ")}</span>}</span>
    </li>
  );
}

/** Today's "Coming up": your stocks' earnings first, then only market-moving releases and the 5 biggest companies
 *  reporting (owner 10-15: by market cap, so tiny names with wild expected moves don't push out the popular ones;
 *  10-16: top 5, and from 9:30 ET on report day only the after-the-close ones — see lib/reporters);
 *  the rest is one click away (trader review 10-06: the sidebar had grown taller than the signals). */
export default function ComingUp({ ahead, next, releases, today, day }: {
  ahead: ({ ticker: string } & EarnWarn)[]; next: EarnNext; releases: Release[];
  today: { premarket: Reporter[]; afterhours: Reporter[] }; day?: string;
}) {
  const nyToday = new Date().toLocaleDateString("sv-SE", { timeZone: "America/New_York" });
  const reporters = [...today.premarket.map((r) => ({ ...r, side: "Before the open" })),
    ...today.afterhours.map((r) => ({ ...r, side: "After the close" }))];
  const top = topReporters(today, day, new Date());
  const key = releases.filter((e) => KEY.test(e.event)).slice(0, 5);
  const minor = releases.filter((e) => !key.includes(e));
  const days = [...new Set(releases.map((e) => weekday(e.et)))];
  const pill = (e: Release) => DAY_PILL[days.indexOf(weekday(e.et)) % DAY_PILL.length];
  return (
    <div className="mt-6 space-y-6 text-sm">
      <H2 wave>Coming up</H2>

      <Part label="Earnings on your open signals and watchlist">
        {ahead.length === 0 ? (
          <p className="text-muted">
            None in the next 10 days.
            {next && <> Next: <Link href={`/ticker/${next.ticker}`} className="font-semibold text-text hover:underline">{next.ticker}</Link>,{" "}
              {shortDate(next.date)}, {when(next.time)}.</>}
          </p>
        ) : (
          <ul className="divide-y divide-line border-y border-line">{ahead.map((e) => (
            <li key={e.ticker} className={`${rowCls} grid-cols-[4rem_1fr]`}>
              <Link href={`/ticker/${e.ticker}`} className="font-semibold hover:underline">{e.ticker}</Link>
              <span>{shortDate(e.date)}, {when(e.time)}
                <span className="block text-xs text-muted">Last full session before it: {shortDate(e.last_session_before)}</span></span>
            </li>))}</ul>
        )}
      </Part>

      <Part label="Market-moving releases, next 3 days">
        {releases.length === 0 ? <p className="text-muted">None scheduled.</p> : (<>
          {key.length === 0 ? <p className="text-muted">No major release; {minor.length} smaller ones.</p> : (
            <ul className="divide-y divide-line border-y border-line">{key.map((e) => <ReleaseRow key={e.et + e.event} e={e} pill={pill(e)} />)}</ul>)}
          {minor.length > 0 && <details className="group mt-1">
            <summary className="cursor-pointer list-none py-1 text-xs text-muted hover:text-text">
              <span className="group-open:hidden">+ {minor.length} smaller releases and Fed talks</span>
              <span className="hidden group-open:inline">− Hide smaller releases</span></summary>
            <ul className="divide-y divide-line border-y border-line">{minor.map((e) => <ReleaseRow key={e.et + e.event} e={e} pill={pill(e)} />)}</ul>
          </details>}
        </>)}
      </Part>

      <Part label={!day || day === nyToday ? "Reporting earnings today" : `Reporting earnings ${shortDate(day)}`}>
        {reporters.length === 0 ? <p className="text-muted">None.</p> : top.length === 0 ? (
          <p className="text-muted">All of today&apos;s reports came out before the open.{" "}
            <Link href="/earnings" className="underline underline-offset-4">More on Earnings</Link></p>) : (<>
          <ul className="grid grid-cols-3 gap-2">{top.map((r) => (
            <li key={r.ticker}>
              <Link href={`/ticker/${r.ticker}`} title={r.side}
                className={`block rounded-md px-2.5 py-2 text-center outline-offset-2 hover:outline hover:outline-1 ${r.expected_move_perc != null ? heat(r.expected_move_perc) : "bg-panel2"}`}>
                <span className="flex items-center justify-center gap-1.5 text-xs font-semibold">
                  {r.side === "Before the open" ? <span aria-hidden>☀</span> : <span aria-hidden>☾</span>}{r.ticker}<span className="sr-only">, {r.side}</span></span>
                <span className="mt-0.5 block text-[15px] font-bold tabular-nums">{r.expected_move_perc != null ? `±${plainPct(r.expected_move_perc, 1)}` : "n/a"}</span>
              </Link>
            </li>))}</ul>
          <p className="mt-2 text-xs text-muted"><span className="text-amber">☀</span> before the open, <span className="text-sea">☾</span> after the close.
            Biggest companies reporting (± = what options price in).{" "}
            <Link href="/earnings" className="underline underline-offset-4">{reporters.length > top.length ? `All ${reporters.length} on Earnings` : "More on Earnings"}</Link></p>
        </>)}
      </Part>
    </div>
  );
}
