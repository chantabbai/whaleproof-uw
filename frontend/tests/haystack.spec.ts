import { expect, test } from "@playwright/test";
import { CLEAR_ROWS, LABEL_COLS, gridSize, placeSpots, rng } from "../lib/haystack";

const clash = (a: { c: number; r: number }, b: { c: number; r: number }) =>
  Math.abs(a.c - b.c) < LABEL_COLS && Math.abs(a.r - b.r) < CLEAR_ROWS;

test("sightings haystack: signal labels never land on top of each other (Oct 12: SNAP touched CIEN)", () => {
  const t6 = ["SNDK", "EWY", "SNAP", "CIEN", "SQQQ", "GOOGL"];
  const spots = placeSpots(t6, 33, 110, rng("2026-10-12"));
  for (const [i, a] of spots.entries()) for (const b of spots.slice(i + 1)) expect(clash(a, b), `${a.t} vs ${b.t}`).toBe(false);
  for (let d = 0; d < 300; d++) {        // many days, 1–8 signals (live days so far: 3–8), a normal day's 25–45 rows
    const n = 1 + (d % 8), rows = 25 + (d % 21);
    const s = placeSpots(Array.from({ length: n }, (_, i) => `T${i}`), rows, 110, rng(`day-${d}`));
    for (const [i, a] of s.entries()) for (const b of s.slice(i + 1)) expect(clash(a, b), `day ${d}: ${a.t} vs ${b.t}`).toBe(false);
    for (const p of s) { expect(p.r).toBeGreaterThanOrEqual(1); expect(p.r).toBeLessThanOrEqual(rows - 2); }
  }
});

test("busy days: the grid widens instead of growing taller, and labels still keep apart (10-14..16: 6.8–7.6K alerts)", () => {
  // Owner 10-16: the haystack doubled in height when UW's alert count doubled. Up to 45 rows the grid stays 110 wide
  // (unchanged); beyond that it keeps a 45 × 110 day's shape, and the label spacing scales with the smaller cells.
  expect(gridSize(4950)).toEqual({ cols: 110, rows: 45, scale: 1 });
  expect(gridSize(3616)).toEqual({ cols: 110, rows: 33, scale: 1 });
  const g = gridSize(7640);
  expect(g.cols).toBe(137);
  expect(g.rows / g.cols).toBeLessThanOrEqual(45 / 110 + 0.005);    // never taller (on screen) than a 45-row day
  for (const n of [4951, 6000, 9000, 15000]) { const x = gridSize(n); expect(x.rows / x.cols).toBeLessThanOrEqual(45 / 110 + 0.01); }
  for (let d = 0; d < 200; d++) {
    const n = 1 + (d % 8);
    const s = placeSpots(Array.from({ length: n }, (_, i) => `T${i}`), g.rows, g.cols, rng(`busy-${d}`), g.scale);
    for (const [i, a] of s.entries()) for (const b of s.slice(i + 1))
      expect(Math.abs(a.c - b.c) < LABEL_COLS * g.scale && Math.abs(a.r - b.r) < CLEAR_ROWS * g.scale, `day ${d}: ${a.t} vs ${b.t}`).toBe(false);
    for (const p of s) { expect(p.r).toBeGreaterThanOrEqual(Math.ceil(g.scale)); expect(p.r).toBeLessThanOrEqual(g.rows - 1 - Math.ceil(g.scale)); }
  }
});

test("normal days: placement is exactly what it was (scale 1)", () => {
  const t6 = ["SNDK", "EWY", "SNAP", "CIEN", "SQQQ", "GOOGL"];
  expect(placeSpots(t6, 33, 110, rng("2026-10-12"), 1)).toEqual(placeSpots(t6, 33, 110, rng("2026-10-12")));
});
