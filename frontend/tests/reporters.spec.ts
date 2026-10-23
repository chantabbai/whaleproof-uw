import { expect, test } from "@playwright/test";
import { topReporters } from "../lib/reporters";

// Owner 10-16: Sightings shows today's popular reporters — before the open both sides, top 5 by market cap; once
// the market opens the before-the-open ones are out, so only after-the-close ones.
const r = (ticker: string, cap: number) => ({ ticker, expected_move_perc: 0.05, marketcap: cap });
const day = { premarket: [r("PRE1", 50), r("PRE2", 300), r("PRE3", 10)], afterhours: [r("AFT1", 200), r("AFT2", 400), r("AFT3", 5), r("AFT4", 100)] };
const et = (iso: string) => new Date(iso);          // UTC instants; Oct 19 2026 is EDT (UTC−4)

test("before the open on report day: both sides, biggest 5", () => {
  const got = topReporters(day, "2026-10-19", et("2026-10-19T13:29:00Z"));      // 09:29 ET
  expect(got.map((x) => x.ticker)).toEqual(["AFT2", "PRE2", "AFT1", "AFT4", "PRE1"]);
  expect(got[1].side).toBe("Before the open");
});

test("from 9:30 ET on report day: only after-the-close reports", () => {
  const got = topReporters(day, "2026-10-19", et("2026-10-19T13:30:00Z"));      // 09:30 ET
  expect(got.map((x) => x.ticker)).toEqual(["AFT2", "AFT1", "AFT4", "AFT3"]);
  expect(got.every((x) => x.side === "After the close")).toBe(true);
});

test("a later day's list (evening or weekend preview): both sides", () => {
  const got = topReporters(day, "2026-10-19", et("2026-10-17T02:45:00Z"));      // Fri Oct 16, 22:45 ET
  expect(got).toHaveLength(5);
  expect(got.map((x) => x.ticker)).toContain("PRE2");
});

test("no day given counts as today", () => {
  expect(topReporters(day, undefined, et("2026-10-19T15:00:00Z")).map((x) => x.ticker)).toEqual(["AFT2", "AFT1", "AFT4", "AFT3"]);
});
