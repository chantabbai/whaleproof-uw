import { expect, test } from "@playwright/test";
import type { Signal } from "../lib/api";
import { earlierHold, ordinal } from "../lib/repeat";

const sig = (id: string, ticker: string, direction: number, entry: string, exit_by: string) =>
  ({ id, ticker, direction, entry, exit_by } as Signal);

test("repeat signal: the newer open hold on the same ticker + direction points at the earlier one (EWY 10-19)", () => {
  const first = sig("a", "EWY", 1, "2026-10-16", "2026-10-22"), second = sig("b", "EWY", 1, "2026-10-19", "2026-10-23");
  const list = [second, sig("c", "CIEN", 1, "2026-10-19", "2026-10-23"), first];
  expect(earlierHold(second, list)).toEqual({ first: first, nth: 2 });
  expect(earlierHold(first, list)).toBeNull();                       // the first one gets no label
  expect(earlierHold(list[1], list)).toBeNull();                     // different ticker
  expect(earlierHold(sig("d", "EWY", -1, "2026-10-19", "2026-10-23"), list)).toBeNull();  // other direction = other bet
  expect(earlierHold(sig("e", "EWY", 1, "2026-10-16", "2026-10-22"), list)).toBeNull();   // same entry day = same trade
});

test("repeat signal: a third open hold counts as 3rd and points at the first (EWY 10-19 had entries 13, 16, 19)", () => {
  const a = sig("a", "EWY", 1, "2026-10-13", "2026-10-19"), b = sig("b", "EWY", 1, "2026-10-16", "2026-10-22"),
    c = sig("c", "EWY", 1, "2026-10-19", "2026-10-23");
  expect(earlierHold(c, [c, b, a])).toEqual({ first: a, nth: 3 });
  expect(earlierHold(b, [c, b, a])).toEqual({ first: a, nth: 2 });
  expect([1, 2, 3, 4, 11, 12, 13, 21, 22].map(ordinal)).toEqual(["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"]);
});

test("repeat signal: Track record rows (entry_on, no entry) get the same answer, ordered by sell date", () => {
  const row = (id: string, exit_by: string) => ({ id, ticker: "EWY", direction: 1, exit_by });
  const a = row("a", "2026-10-19"), b = row("b", "2026-10-22"), c = row("c", "2026-10-23");
  expect(earlierHold(c, [a, b, c])).toEqual({ first: a, nth: 3 });
  expect(earlierHold(a, [a, b, c])).toBeNull();
});
