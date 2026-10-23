"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function WatchButton({ ticker, on, compact = false }: { ticker: string; on: boolean; compact?: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const toggle = async () => {
    setBusy(true); setErr("");
    const r = await fetch(`/api/desk/watchlist/${encodeURIComponent(ticker)}`, { method: on ? "DELETE" : "POST" }).catch(() => null);
    setBusy(false);
    if (!r?.ok) { setErr("Couldn't update the watchlist. Is the API running?"); return; }
    router.refresh();
  };
  return (
    <span className="inline-flex items-center gap-2">
      <button type="button" disabled={busy} onClick={toggle} aria-pressed={on} title={on ? "Remove from watchlist" : "Add to watchlist"}
        aria-label={compact ? (on ? `Watching ${ticker}` : `Watch ${ticker}`) : undefined}
        className={compact ? `text-lg leading-none ${on ? "text-marker" : "text-muted hover:text-text"}`
          : `text-[13px] underline-offset-4 hover:underline ${on ? "font-semibold text-text" : "text-muted hover:text-text"}`}>
        {compact ? (on ? "★" : "☆") : on ? "★ Watching" : "☆ Watch"}
      </button>
      {err && <span className="text-xs text-bad">{err}</span>}
    </span>
  );
}
