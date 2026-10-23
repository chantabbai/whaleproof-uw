"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";

/** Delete a journal entry, with an inline "are you sure" step (no browser dialog). A backup is kept before every change. */
export default function DeleteTrade({ id, ticker }: { id: number; ticker: string }) {
  const router = useRouter();
  const [ask, setAsk] = useState(false);
  const [err, setErr] = useState(false);
  const del = async () => {
    const r = await fetch(`/api/desk/journal/${id}`, { method: "DELETE" }).catch(() => null);
    setErr(!r?.ok);
    if (r?.ok) { setAsk(false); router.refresh(); }
  };
  if (!ask) return <button type="button" onClick={() => setAsk(true)} aria-label={`Delete the ${ticker} trade`}
    className="text-xs text-muted underline-offset-4 hover:text-bad hover:underline">Delete</button>;
  return (
    <span role="group" aria-label={`Confirm deleting the ${ticker} trade`} className="flex flex-wrap items-center gap-2 text-xs">
      <span>Delete this trade?</span>
      <button type="button" onClick={del} className="rounded-md bg-bad px-2 py-0.5 font-semibold text-white">Yes, delete</button>
      <button type="button" onClick={() => setAsk(false)} className="underline underline-offset-4">Cancel</button>
      {err && <span className="text-bad">Didn&apos;t delete</span>}
    </span>
  );
}
