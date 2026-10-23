/** Sightings "Reporting earnings": which companies get a tile (owner 10-16). Before the open on report day both sides
 *  count; from 9:30 ET the before-the-open reports are out, so only after-the-close ones. Biggest market cap first. */
type Sided<R> = R & { side: "Before the open" | "After the close" };

export function topReporters<R extends { marketcap?: number | null }>(
  today: { premarket: R[]; afterhours: R[] }, day: string | undefined, now: Date, n = 5,
): Sided<R>[] {
  const nyDay = now.toLocaleDateString("sv-SE", { timeZone: "America/New_York" });
  const hm = now.toLocaleTimeString("en-GB", { timeZone: "America/New_York", hour12: false, hour: "2-digit", minute: "2-digit" });
  const opened = (!day || day === nyDay) && hm >= "09:30";
  const pool: Sided<R>[] = [
    ...(opened ? [] : today.premarket.map((r) => ({ ...r, side: "Before the open" as const }))),
    ...today.afterhours.map((r) => ({ ...r, side: "After the close" as const })),
  ];
  return pool.sort((a, b) => (b.marketcap ?? -1) - (a.marketcap ?? -1)).slice(0, n);
}
