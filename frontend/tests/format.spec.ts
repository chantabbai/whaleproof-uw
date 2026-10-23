import { expect, test } from "@playwright/test";
import { arrowPct, contractLabel, days, dte, earnWarnText, lvl, md, money, plural, shortDate, moveDigits, moveTone, plainPct, px, ratioX } from "../lib/format";
import { pastSignalsSub } from "../lib/format";

test("a hold that barely moved shows two decimals instead of a frozen-looking 0.0%", () => {
  const d = moveDigits(-0.00037);                                  // QQQ Oct 9: $749.35 → $749.07
  expect(d).toBe(2);
  expect(arrowPct(-0.00037, d)).toBe("▼\u00a0−0.04%");
  expect(moveTone(-0.00037, d)).toBe("text-bear");
  expect(moveDigits(0.0123)).toBe(1);                              // normal moves keep one decimal
  expect(arrowPct(0.0123, moveDigits(0.0123))).toBe("▲\u00a0+1.2%");
  expect(arrowPct(0.00001, moveDigits(0.00001))).toBe("0.00%");    // truly flat stays flat
});

test("prices of $1,000 and up get a thousands comma (SNDK $1531.89 read as $1531.89)", () => {
  expect(px(1531.888)).toBe("$1,531.89");
  expect(px(1650)).toBe("$1,650.00");
  expect(px(6.5)).toBe("$6.50");
  expect(px(null)).toBe("–");
});

test("options-vs-usual ratio shows two decimals near the cheap/rich lines, so 0.79 (cheap) and 0.82 (fair) don't both read 0.8", () => {
  expect(ratioX(0.79)).toBe("0.79");
  expect(ratioX(0.82)).toBe("0.82");
  expect(ratioX(1.24)).toBe("1.24");
  expect(ratioX(1.27)).toBe("1.27");
  expect(ratioX(2.46)).toBe("2.5");
  expect(ratioX(1.0)).toBe("1.0");
});

test("level labels drop .00 on whole numbers and keep two decimals otherwise (put wall 192.5 → 192.50)", () => {
  expect(lvl(192.5)).toBe("192.50");
  expect(lvl(210)).toBe("210");
  expect(lvl(224.19)).toBe("224.19");
  expect(lvl(1074.8)).toBe("1,074.80");                            // MU bet diagram read "1074.80"
  expect(lvl(722.805)).toBe(px(722.805).slice(1));                 // same rounding as the card ($722.81, diagram said 722.80)
});

test("negative plain percentages use the true minus like everywhere else, and an arrow never ends up alone on a line", () => {
  expect(plainPct(-0.01)).toBe("−1%");
  expect(plainPct(0.05)).toBe("5%");
  expect(arrowPct(0.233)).toBe("▲\u00a0+23.3%");
});

test("days left read in the singular for one day (All bets row said \"1 days, in the money\")", () => {
  expect(days(1)).toBe("1 day");
  expect(days(24)).toBe("24 days");
  expect(days(0)).toBe("0 days");
});

test("an option expiring today reads \"expires today\", not \"0 days\"", () => {
  expect(dte(0)).toBe("expires today");
  expect(dte(0, " out")).toBe("expires today");
  expect(dte(1, " out")).toBe("1 day out");
  expect(dte(12)).toBe("12 days");
});

test("a date in another year shows the year (GOOGL 339-day call read \"expires Fri, Sep 17\" in October)", () => {
  const now = new Date("2026-10-13T14:00:00Z");
  expect(shortDate("2027-09-17", now)).toBe("Fri, Sep 17, 2027");
  expect(shortDate("2026-11-06", now)).toBe("Fri, Nov 6");
  expect(shortDate("2025-07-30", now)).toBe("Wed, Jul 30, 2025");       // an old earnings report
  expect(shortDate(null, now)).toBe("–");
  expect(md("2027-01-15", now)).toBe("Jan 15, 2027");
  expect(md("2026-10-20", now)).toBe("Oct 20");
});

test("counts read in the singular for one (\"1 alerts\", \"1 of 1 holds\")", () => {
  expect(plural(1, "alert")).toBe("1 alert");
  expect(plural(1204, "alert")).toBe("1,204 alerts");
  expect(plural(0, "signal")).toBe("0 signals");
  expect(plural(1, "time", "times")).toBe("1 time");
  expect(plural(null, "alert")).toBe("–");                         // API down: no crash
});

test("money never reads $1000K and rounds .5 up like the reasons do", () => {
  expect(money(999_600)).toBe("$1.0M");
  expect(money(878_500)).toBe("$879K");
  expect(money(999_960_000)).toBe("$1.0B");
  expect(money(-999_600)).toBe("-$1.0M".replace("-", "−"));
});

test("a strike reads the same everywhere: $195.00, $1,650.00 (cards said \"$195.00 puts\" and \"PLTR $195 put\")", () => {
  const now = new Date("2026-10-13T14:00:00Z");
  expect(contractLabel("PLTR261120P00195000", now)).toBe("PLTR $195.00 put, expires Fri, Nov 20");
  expect(contractLabel("SNDK290119P01300000", now)).toBe("SNDK $1,300.00 put, expires Fri, Jan 19, 2029");
});

test("a percent that rounds to zero has no minus (SPY strike read \"−0%\" out of the money)", () => {
  expect(plainPct(-0.003)).toBe("0%");
  expect(plainPct(-0.006)).toBe("−1%");
});

test("an earnings warning reads like Sightings, not the API's ISO dates and 'unknown'", () => {
  const now = new Date("2026-10-20T14:00:00Z");
  expect(earnWarnText({ date: "2026-10-29", time: "unknown", last_session_before: "2026-10-29" }, now))
    .toBe("Earnings Thu, Oct 29, time not set; last full session before it: Thu, Oct 29");
  expect(earnWarnText({ date: "2026-10-29", time: "premarket", last_session_before: "2026-10-28" }, now))
    .toBe("Earnings Thu, Oct 29, before the open; last full session before it: Wed, Oct 28");
});

test("a ticker whose only signal is still open doesn't say 'never a signal' (NTRA Oct 23, in its hold)", () => {
  expect(pastSignalsSub({ finished: 0, open: true, holding: true, benchmark: false })).toBe("none finished yet, still in its five-day hold");
  expect(pastSignalsSub({ finished: 0, open: true, holding: false, benchmark: false })).toBe("none finished yet");
  expect(pastSignalsSub({ finished: 0, open: false, holding: false, benchmark: false })).toBe("never a signal since Oct 2023");
  expect(pastSignalsSub({ finished: 3, open: true, holding: true, benchmark: false })).toBe("beat the S&P over five days");
  expect(pastSignalsSub({ finished: 3, open: false, holding: false, benchmark: true })).toBe("went up over five days (this is the S&P, so no comparison)");
});
