"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";

export default function CloseTrade({ id }: { id: number }) {
  const router = useRouter();
  const [v, setV] = useState("");
  const [err, setErr] = useState(false);
  const close = async (e: React.FormEvent) => {
    e.preventDefault();
    const r = await fetch(`/api/desk/journal/${id}/close`, { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ exit_price: Number(v) }) }).catch(() => null);
    setErr(!r?.ok);
    if (r?.ok) router.refresh();
  };
  return (
    <form onSubmit={close} className="flex items-center gap-1">
      <label htmlFor={`x${id}`} className="sr-only">Exit price</label>
      <input id={`x${id}`} type="number" step="any" min="0.0001" required value={v} onChange={(e) => setV(e.target.value)} placeholder="Exit price"
        className="field w-24 px-2 py-1 text-xs" />
      <button type="submit" className="whitespace-nowrap text-xs underline underline-offset-4">Close trade</button>
      {err && <span className="text-xs text-bad">Didn&apos;t save</span>}
    </form>
  );
}
