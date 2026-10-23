"use client";
import { useEffect, useState } from "react";
import type { Status } from "@/lib/api";
import { etTime, num } from "@/lib/format";

const weekday = (iso: string) => new Date(iso).toLocaleDateString("en-US", { timeZone: "America/New_York", weekday: "long" });
const dayName = (d: string) => new Date(`${d}T12:00:00`).toLocaleDateString("en-US", { weekday: "long" });

/** One line under the masthead: is the market open, whose flow is on screen, and anything that needs attention. */
export default function StatusBar() {
  const [s, setS] = useState<Status | null>(null);
  const [down, setDown] = useState(false);
  useEffect(() => {
    const load = () => fetch("/api/desk/status", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status))).then((j) => { setS(j); setDown(false); })
      .catch(() => setDown(true));
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);
  if (down) return <Line><span className="text-bad">The WhaleProof API is not answering on 127.0.0.1:8100. Start it with <code>scripts/desk.sh up</code>.</span></Line>;
  if (!s) return <Line>Checking the market…</Line>;

  const open = s.clock.state === "open";
  const market = open ? (s.clock.close ? `Market's open until ${etTime(s.clock.close)}.` : "Market's open.")
    : s.clock.state === "pre" ? `Pre-market. Opens ${etTime(s.clock.next_open)}.`
    : s.clock.state === "after" ? `After hours. Opens ${weekday(s.clock.next_open)} ${etTime(s.clock.next_open)}.`
    : `Market's closed. Opens ${weekday(s.clock.next_open)} ${etTime(s.clock.next_open)}.`;
  const flow = open ? "Flow is coming in live." : `Showing ${dayName(s.data_day)}'s flow.`;

  const alerts: string[] = [];
  if (!s.live_enabled) alerts.push("No UW key, so you're looking at cached data only.");
  if (s.quota_exhausted) alerts.push("Out of UW calls for today. Live data comes back after the 8 PM ET reset.");
  if (s.blocked) alerts.push("Something on the network is blocking Unusual Whales (not a key problem).");
  if (s.auth_failed) alerts.push("Unusual Whales turned down the API key or plan.");
  if (s.usage?.stopped) alerts.push("Live refresh is paused to save the last of today's calls. It resumes after 8 PM ET.");
  if (s.usage?.mode === "eod" && !s.usage.live_now) alerts.push("End-of-day mode: live pulls are paused until 3:30 PM ET.");
  if (s.usage?.mode === "eod" && s.usage.live_now) alerts.push("Pulling the day's final flow for tomorrow's signals.");
  if (open && s.usage?.pace != null && s.usage.pace > 1.05 && s.usage.mode !== "eod")
    alerts.push(`Refreshing ${num(s.usage.pace, 1)}× slower than usual to make the calls last until 8 PM.`);
  const failing = Object.keys(s.failing).filter((k) => k !== "uw" && !/^(earnings|oi|vol|sector):/.test(k));
  if (failing.length) alerts.push(`Not updating right now: ${failing.slice(0, 3).join(", ")}.`);

  // owner 10-16: no UW call count here (UW sets no daily cap; the count is plumbing). /api/desk/status still has it.
  return (
    <Line>
      <span aria-hidden className={`mr-1 inline-block h-2 w-2 self-center rounded-full ${open ? "bg-[#3fb950] motion-safe:animate-pulse" : "bg-muted"}`} />
      <span className="text-text">{market}</span> <span>{flow}</span>
      {alerts.map((a) => <span key={a} className="font-medium text-warn"> {a}</span>)}
    </Line>
  );
}

function Line({ children }: { children: React.ReactNode }) {
  return <div role="status" className="mt-3 flex flex-wrap items-baseline gap-x-1 gap-y-1 pb-3 text-[13px] text-muted">{children}</div>;
}
