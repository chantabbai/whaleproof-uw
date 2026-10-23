/** Sightings haystack: seeded randomness and where each signal's square + label goes. */

// sized for the narrowest phone (measured at 360px): square + a five-letter label ≈ 29 cells wide, 8 tall
export const LABEL_COLS = 30, CLEAR_ROWS = 9;
export const BASE_COLS = 110, MAX_ROWS = 45;

/** Owner 10-16: the grid used to grow taller with the day's alerts (7.6K on Oct 15–16 doubled it). Up to MAX_ROWS rows it
 *  stays BASE_COLS wide, exactly as before; past that it keeps the shape of a MAX_ROWS × BASE_COLS day (more columns
 *  and rows in step), so it is never taller than the busiest normal day; cells (and everything sized in cells) shrink
 *  by `scale`. */
export function gridSize(n: number) {
  const m = Math.max(n, 1);
  const cols = m <= BASE_COLS * MAX_ROWS ? BASE_COLS : Math.ceil(Math.sqrt((m * BASE_COLS) / MAX_ROWS));
  return { cols, rows: Math.ceil(m / cols), scale: cols / BASE_COLS };
}

export function rng(seed: string) {
  let h = 1779033703 ^ seed.length;
  for (let i = 0; i < seed.length; i++) {
    h = Math.imul(h ^ seed.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return () => {
    h = Math.imul(h ^ (h >>> 16), 2246822507); h = Math.imul(h ^ (h >>> 13), 3266489909);
    return ((h ^= h >>> 16) >>> 0) / 4294967296;
  };
}

type Spot = { t: string; c: number; r: number };
const clear = (placed: Spot[], c: number, r: number, L = LABEL_COLS, R = CLEAR_ROWS) =>
  placed.every((p) => Math.abs(p.c - c) >= L || Math.abs(p.r - r) >= R);

/** Signals spread left to right (position means nothing), away from the edges so labels fit. Heights are random, but
 *  a spot whose square + label would touch an earlier one is re-drawn; if 40 random heights all touch, every height
 *  is tried, then other columns nearest first, so no label covers another (the closest-to-clear spot only if none is free). */
export function placeSpots(tickers: string[], rows: number, cols: number, rand: () => number, scale = 1): Spot[] {
  const placed: Spot[] = [];
  const L = LABEL_COLS * scale, R = CLEAR_ROWS * scale, e = Math.ceil(scale);   // scale 1: L 30, R 9, e 1 (as before)
  const lo = e, hi = Math.max(rows - 1 - e, e), cMax = Math.floor(cols - L);
  for (const [i, t] of tickers.entries()) {
    const c0 = Math.round((0.12 + ((i + 0.5) / tickers.length) * 0.7 + (rand() - 0.5) * 0.08) * (cols - 3 * e));
    let c = c0, r = 0, ok = false;
    for (let tries = 0; tries < 40 && !ok; tries++) {
      r = Math.round((0.25 + rand() * 0.5) * Math.max(rows - 3, 1));
      ok = clear(placed, c, r, L, R);
    }
    if (!ok) {
      let best = { c, r, gap: -1 };
      const cs = Array.from({ length: cMax - 3 * e + 1 }, (_, k) => k + 3 * e).sort((x, y) => Math.abs(x - c0) - Math.abs(y - c0));
      search: for (const cc of cs) {                   // nearest columns first
        const mid = Math.round((lo + hi) / 2);           // middle rows first, then outwards
        for (let k = 0; k <= 2 * (hi - lo); k++) {
          const rr = mid + (k % 2 ? -(k + 1) / 2 : k / 2);
          if (rr < lo || rr > hi) continue;
          if (clear(placed, cc, rr, L, R)) { c = cc; r = rr; ok = true; break search; }
          const gap = Math.min(...placed.map((p) => Math.max(Math.abs(p.c - cc) / L, Math.abs(p.r - rr) / R)));
          if (gap > best.gap) best = { c: cc, r: rr, gap };
        }
      }
      if (!ok) { c = best.c; r = best.r; }
    }
    placed.push({ t, c, r });
  }
  const clash = placed.some((a, i) => placed.slice(i + 1).some((b) => !clear([a], b.c, b.r, L, R)));
  const bandsC = Math.floor((cMax - 3 * e) / L) + 1, bandsR = Math.floor((hi - lo) / R) + 1;
  if (!clash || tickers.length > bandsC * bandsR) return placed;
  // random spots got boxed in: evenly spaced slots instead, left to right, heights staggered
  const nc = Math.min(bandsC, tickers.length), nr = Math.ceil(tickers.length / nc);
  const gc = nc > 1 ? (cMax - 3 * e) / (nc - 1) : 0, gr = nr > 1 ? Math.min((hi - lo) / (nr - 1), R * 2) : 0;
  const top = lo + Math.round(((hi - lo) - gr * (nr - 1)) / 2);
  return tickers.map((t, i) => ({ t, c: Math.round(3 * e + (i % nc) * gc), r: Math.round(top + Math.floor(i / nc) * gr + (nr === 1 ? (i % 2) * R / 2 : 0)) }));
}
