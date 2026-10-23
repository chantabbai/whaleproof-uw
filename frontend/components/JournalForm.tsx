"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

/** Log a trade. When the ticker has an open signal, the API snapshots it automatically at entry. */
export default function JournalForm() {
  const q = useSearchParams();
  const router = useRouter();
  // today's date in New York: after 8 PM ET the UTC date is already tomorrow
  const today = new Date().toLocaleDateString("sv-SE", { timeZone: "America/New_York" });
  const [f, setF] = useState({ ticker: q.get("ticker") ?? "", instrument: "stock", direction: q.get("direction") ?? "1", entry_price: q.get("entry") ?? "",
    stop: "", size: "", setup: q.get("setup") ?? "manual", notes: "", entry_date: today });
  const [msg, setMsg] = useState("");
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg("");
    const body = { ...f, direction: Number(f.direction), entry_price: Number(f.entry_price),
      stop: f.stop ? Number(f.stop) : null, size: f.size ? Number(f.size) : null };
    const r = await fetch("/api/desk/journal", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }).catch(() => null);
    if (!r?.ok) { setMsg("That didn't save. Check the ticker and entry price."); return; }
    setMsg("Trade logged.");
    setF({ ...f, ticker: "", entry_price: "", stop: "", size: "", notes: "" });
    router.refresh();
  };
  const input = "field w-full px-2";
  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-3 py-1 sm:grid-cols-4">
      <L label="Ticker"><input required value={f.ticker} onChange={set("ticker")} className={`${input} uppercase`} /></L>
      <L label="Bought"><select value={f.instrument} onChange={set("instrument")} className={input}><option value="stock">Stock</option><option value="option">Option</option></select></L>
      <L label="Direction"><select value={f.direction} onChange={set("direction")} className={input}><option value="1">Long</option><option value="-1">Short</option></select></L>
      <L label={f.instrument === "option" ? "Entry price (per option, e.g. 1.50)" : "Entry price (per share)"}><input required type="number" step="any" min="0.0001" value={f.entry_price} onChange={set("entry_price")} className={input} /></L>
      <L label="Entry date"><input type="date" value={f.entry_date} onChange={set("entry_date")} className={input} /></L>
      <L label="Stop (for R)"><input type="number" step="any" min="0.0001" value={f.stop} onChange={set("stop")} className={input} /></L>
      <L label={f.instrument === "option" ? "Contracts" : "Shares"}><input type="number" step="any" min="0.0001" value={f.size} onChange={set("size")} className={input} /></L>
      <L label="Setup"><select value={f.setup} onChange={set("setup")} className={input}>
        <option value="whale">Whale-size bet</option><option value="far_otm">Long shot</option><option value="day">Day trade</option><option value="manual">My own idea</option></select></L>
      <L label="Notes"><input value={f.notes} onChange={set("notes")} className={input} /></L>
      <div className="col-span-2 flex items-center gap-3 sm:col-span-4">
        <button type="submit" className="btn">Log trade</button>
        <span role="status" className="text-sm text-muted">{msg}</span>
      </div>
    </form>
  );
}

function L({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block text-xs text-muted">{label}<span className="mt-1 block text-text">{children}</span></label>;
}
