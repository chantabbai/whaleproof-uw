/** Anything held for the five sessions: a Sightings signal or a Track record row. */
type Hold = { id: string; ticker: string; direction: number; exit_by: string };

/** A repeat signal: earlier open holds on the same ticker and direction (an earlier sell date = bought earlier; every
 *  hold is five sessions). Returns the first of them and this one's place in the run (2 = 2nd signal), or null when
 *  s is the first (or only) one. Research (docs/REPEAT-SIGNALS.md): a repeat is the same bet, not a stronger one. */
export function earlierHold<T extends Hold>(s: T, open: T[]): { first: T; nth: number } | null {
  const prior = open.filter((o) => o.id !== s.id && o.ticker === s.ticker && o.direction === s.direction && o.exit_by < s.exit_by)
    .sort((a, b) => a.exit_by.localeCompare(b.exit_by));
  return prior.length ? { first: prior[0], nth: prior.length + 1 } : null;
}

export const ordinal = (n: number) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] ?? "th"}`;
