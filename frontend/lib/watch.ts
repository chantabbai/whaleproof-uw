import { get } from "./api";

export async function watchSet(): Promise<Set<string>> {
  const w = await get<{ tickers: { ticker: string }[] }>("/api/desk/watchlist");
  return new Set((w?.tickers ?? []).map((t) => t.ticker));
}
