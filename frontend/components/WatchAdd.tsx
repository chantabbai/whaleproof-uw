"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function WatchAdd() {
  const router = useRouter();
  const [v, setV] = useState("");
  const [err, setErr] = useState("");
  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    const r = await fetch(`/api/desk/watchlist/${encodeURIComponent(v.trim())}`, { method: "POST" }).catch(() => null);
    if (!r?.ok) { setErr("Not a valid ticker symbol."); return; }
    setV("");
    router.refresh();
  };
  return (
    <form onSubmit={add} className="flex flex-wrap items-center gap-2">
      <label htmlFor="wadd" className="sr-only">Ticker to watch</label>
      <input id="wadd" value={v} onChange={(e) => setV(e.target.value)} placeholder="Add ticker, e.g. AMD"
        className="w-44 field uppercase" />
      <button type="submit" className="btn">Add to watchlist</button>
      {err && <span className="text-sm text-bad">{err}</span>}
    </form>
  );
}
