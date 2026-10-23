import { expect, test } from "@playwright/test";
import { topReporters } from "../lib/reporters";

const SECTIONS: [string, RegExp][] = [
  ["/", /Sightings:/], ["/market", /Market/], ["/bets", /Flow check/],
  ["/ticker/SPY", /SPY/], ["/watchlist", /Watchlist/], ["/earnings", /Earnings/], ["/journal", /Journal/], ["/tracker", /Track record/], ["/methodology", /How it works/], ["/methodology/details", /technical version/],
];

for (const [path, heading] of SECTIONS) {
  test(`loads ${path}`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const r = await page.goto(path);
    expect(r?.status()).toBe(200);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(heading);
    await expect(page.getByRole("status").first()).not.toContainText("not answering");
    expect(errors).toEqual([]);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);                     // no horizontal page scroll, phone included
  });
}

test("old Swing and Day trading URLs land on Sightings and Market", async ({ page }) => {
  await page.goto("/swing");
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/day");
  await expect(page).toHaveURL(/\/market$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Market");
});

test("ticker page: a symbol with no prices or flow says so instead of reading like a quiet stock", async ({ page }) => {
  await page.goto("/ticker/ZZZZQ");
  await expect(page.getByText("No prices or options flow for ZZZZQ.")).toBeVisible();
  await expect(page.getByText("Not a signal today")).toHaveCount(0);
  await page.goto("/ticker/SPY");
  await expect(page.getByText(/No prices or options flow/)).toHaveCount(0);
});

test("market says 'options lean' throughout and short-dated tiles show what they're ranked by", async ({ page }) => {
  await page.goto("/market");
  for (const h of ["Options lean through the day", "Options lean by sector", "Short-dated buying"])
    await expect(page.getByRole("heading", { name: h })).toBeVisible();
  await expect(page.getByText("Leans most bullish")).toBeVisible();
  await expect(page.getByText("Leans most bearish")).toBeVisible();
  await expect(page.getByText(/Most money (into|out of)/)).toHaveCount(0);
  const tiles = page.getByTestId("short-dte-tile");
  if (await tiles.count()) {
    await expect(tiles.first()).toContainText(/traded, \d+% calls/);
    const traded = await tiles.evaluateAll((els) => els.map((e) => Number(e.getAttribute("data-total"))));
    expect(traded).toEqual([...traded].sort((a, b) => b - a));              // biggest money first, as the tile says
  }
});

test("today lists each open signal once, with the hold list opening into the full card", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Riding with the whales/ })).toBeVisible();
  const open = page.getByRole("button", { name: / full card$/ }).first();
  if (await open.count()) {
    await open.click();
    await expect(page.getByText("Why it made the cut").first()).toBeVisible();
    await page.getByRole("button", { name: "Close ✕" }).click();             // an opened card can be closed
    await expect(page.getByText("Why it made the cut")).toHaveCount(0);
  }
});

test("today: the hold tape shows the open book's move today next to the S&P, and every hold scrolling", async ({ page }) => {
  await page.goto("/");
  test.skip(await page.getByText("Nothing open.").isVisible(), "no open holds in this cache");
  const tape = page.getByTestId("hold-tape");                                     // owner 10-07: catch the eye
  await expect(tape).toBeVisible();
  await expect(tape.getByTestId("book-today")).toContainText(/\d+ holds? (today|at the close|on .+)/);
  await expect(tape.getByTestId("book-today")).toContainText(/[+−]\d+\.\d{1,2}%|0\.0%/);   // small moves show two decimals
  await expect(tape.getByTestId("book-today")).toContainText(/S&P [▲▼]?\s?[+−]?\d+\.\d{1,2}%/);
  await expect(tape.locator("[data-copy=a]").first()).toContainText(/^[A-Z.]+\s*(▲|▼)?\s*[+−]?\d+\.\d{1,2}%$/);
  await expect(tape.locator("ul.sr-only li").first()).toContainText(/(today|since its entry open)$/);   // bought today: counted from its entry open
});

test("today shows the noise sieve with real counts", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/alerts\. \d+ worth a look/);
  await expect(page.getByText(/one-way bets$/).first()).toBeVisible();
  await page.getByText(/new buys$/).first().hover();
  await expect(page.getByRole("tooltip").filter({ hasText: "paid the asking price" })).toBeVisible();
  // the period table lives on How it works (10-07: removed from Sightings); the evidence badge links there
  await expect(page.getByRole("link", { name: /See how it was tested/ })).toBeVisible();
});

test("watchlist add and remove", async ({ page }) => {
  await page.goto("/watchlist");
  await page.getByPlaceholder("Add ticker, e.g. AMD").fill("amd");
  await page.getByRole("button", { name: "Add to watchlist" }).click();
  await expect(page.getByRole("link", { name: "AMD", exact: true })).toBeVisible();
  const move = page.getByTestId("watch-move").first();                         // the day's move, named by its day, never "live" off-hours
  await expect(move).toContainText(/Mon|Tue|Wed|Thu|Fri|today/);
  await page.getByRole("button", { name: "★ Watching" }).first().click();
  await expect(page.getByRole("link", { name: "AMD", exact: true })).toHaveCount(0);
});

test("journal logs and closes a trade", async ({ page }) => {
  await page.goto("/journal?ticker=MSFT&direction=1&setup=manual");
  await page.getByLabel("Entry price").fill("100");
  await page.getByLabel("Stop (for R)").fill("95");
  await page.getByRole("button", { name: "Log trade" }).click();
  await expect(page.getByText("Trade logged.")).toBeVisible();
  await page.reload();
  await expect(page.locator("tbody tr").first()).toContainText(/so far/);           // an open trade shows where it stands
  await page.getByPlaceholder("Exit price").first().fill("110");
  await page.getByRole("button", { name: "Close trade" }).first().click();
  await expect(page.getByText("2.00R").first()).toBeVisible();
  const rows = page.locator("tbody tr").filter({ hasText: "MSFT" });
  const before = await rows.count();
  await page.getByRole("button", { name: "Delete the MSFT trade" }).first().click();
  await page.getByRole("button", { name: "Cancel" }).click();                        // cancel keeps it
  await expect(rows).toHaveCount(before);
  await page.getByRole("button", { name: "Delete the MSFT trade" }).first().click();
  await page.getByRole("button", { name: "Yes, delete" }).click();
  await expect(rows).toHaveCount(before - 1);
});

test("methodology shows the compounded stock simulation, labelled exploratory, with the losing window", async ({ page }) => {
  await page.goto("/methodology/details");
  await page.getByText("If you had traded every signal in stock").click();
  await expect(page.getByText(/Exploratory simulation, not a track record/)).toBeVisible();
  await expect(page.getByRole("img", { name: /\$1 traded in signals grew to/ })).toBeVisible();
  await expect(page.getByRole("cell", { name: /Post-period, Jun to Sep 2026, seen before/ })).toBeVisible();
});

test("methodology shows the beta-adjusted check per window", async ({ page }) => {
  await page.goto("/methodology/details");
  await page.getByText("Is it just market beta?").click();
  await expect(page.getByRole("cell", { name: /Holdout, out-of-sample/ })).toBeVisible();
});

test("plain-English methodology walks through the steps, shows what was tried, results and links to details", async ({ page }) => {
  await page.goto("/methodology");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/Ahead of the rest in \d of \d periods/);
  for (const t of ["1. Throw out the noise", "2. Test it fairly", "3. Results", "4. How to act on a signal", "5. Limits"])
    await expect(page.getByRole("heading", { name: t })).toBeVisible();
  await expect(page.getByText("✗ no edge")).toBeVisible();                       // the losing period stays visible
  await page.getByText("What we tried before landing on two kinds of signal").click();
  await expect(page.getByText("687 combinations of simple rules")).toBeVisible();
  await page.getByText("What $1 would have done").click();
  await expect(page.getByRole("columnheader", { name: "$1 in signals (bought as stock) became" })).toBeVisible();
  await expect(page.getByRole("cell", { name: /Recent months, Jun to Sep 2026/ })).toBeVisible();
  await page.getByRole("link", { name: "technical version" }).first().click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("technical version");
});

test("methodology explains why the stock is sold after 5 days, with trade counts in words", async ({ page }) => {
  await page.goto("/methodology");
  await page.getByText("Why sell after 5 days?").click();
  await expect(page.getByRole("cell", { name: "5 days (what we use)" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "30 days" })).toBeVisible();
  await expect(page.getByText(/Our shortlist, [\d,]+ trades/).first()).toBeVisible();
  await page.goto("/methodology/details");
  await page.getByText("Holding period: 5, 10, 20 or 30 sessions?").click();
  await expect(page.getByRole("columnheader", { name: "Hold" })).toBeVisible();
});

test("signal tracker: open and finished sections, row expands to the day-by-day path", async ({ page }) => {
  await page.goto("/tracker");
  await expect(page.getByText(/Prices through/)).toBeVisible();
  await expect(page.getByRole("heading", { name: /Riding with the whales/ })).toBeVisible();   // same name as on Sightings
  await expect(page.getByRole("heading", { name: "Where results landed" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Month by month" })).toBeVisible();
  await page.getByLabel("Period").selectOption({ label: "Sealed test (Oct 2025–May 2026)" });
  await page.getByText("Every finished signal (628)").click();
  await expect(page.getByRole("columnheader", { name: /Drawdown/ }).first()).toBeVisible();
  await expect(page.getByText(/^\$[\d,.]+ to \$[\d,.]+$/).first()).toBeVisible();   // finished row: bought → sold price in the table
  await page.getByRole("button", { name: /details$/ }).first().click();
  await expect(page.getByRole("img", { name: /Path over/ })).toBeVisible();
  await expect(page.getByTestId("day-table")).toBeVisible();
  await page.getByLabel("Ticker").fill("ZZZZZZ");
  await expect(page.getByText("No finished signals for these filters.")).toBeVisible();
});

test("tracker: a period with nothing finished yet still fills the tiles with its open holds", async ({ page }) => {
  await page.goto("/tracker");
  await page.getByLabel("Period").selectOption({ label: "Live (from Sep 30, 2026)" });
  const tiles = page.getByTestId("tracker-tiles");
  await expect(tiles).toBeVisible();
  await expect(tiles).not.toContainText(/Average stock trade\s*–/);           // owner 10-07: Live showed four blank tiles
  await expect(tiles).not.toContainText(/Stock went up\s*–/);
});

test("tracker by period: answers first, then one table (cards on phone): edge over all UW alerts and stock vs option", async ({ page }, info) => {
  await page.goto("/tracker");
  await page.getByText("By period: four test periods and live trading").click();
  await expect(page.getByText(/^Our shortlist of UW alerts added an edge in \d of \d test periods, and the stock did better than the whale.s option in [\d,]+ of [\d,]+ trades/)).toBeVisible();   // grey note, like the other sections
  const phone = info.project.name === "phone";
  const box = page.getByTestId(phone ? "by-period-cards" : "by-period-table");            // owner 10-07: one table, periods once
  await expect(box).toBeVisible();
  await expect(page.getByTestId(phone ? "by-period-table" : "by-period-cards")).toBeHidden();
  const items = box.getByTestId("period");
  await expect(items).toHaveCount(5);
  await expect(items.first()).toContainText("Second sealed test");                        // oldest first
  await expect(items.last()).toContainText("Live");                                        // live last, muted
  const sealed = items.filter({ hasText: /^Sealed test/ });
  await expect(sealed).toContainText(/628 signals/);
  await expect(sealed.getByTestId("edge")).toHaveText(/[+−]\d+\.\d%/);
  await expect(sealed.getByTestId("better-trade")).toContainText(/Stock won [\d,]+ of [\d,]+ \(\d+%\)/);
  await expect(sealed.getByTestId("won")).toHaveText(/^[\d,]+ of [\d,]+ \(\d+%\)$/);              // owner 10-21: real win count
  await expect(sealed.getByTestId("spy")).toHaveText(/\d+\.\d%$/);                     // S&P 500's own move, same days
  const live = items.last(), small = live.getByTestId("too-small");                          // follows the data:
  if (await small.count()) await expect(small.first()).toHaveText(/^too small: \d+ of 30 needed$/);   // under 30 finished
  else await expect(live).toContainText(/\d+ signals[\s\S]*[+−]\d+\.\d%/);                   // 30+ (Live passed 30 on 10-19): real numbers
  if (!phone) {
    await expect(box.getByRole("columnheader", { name: "Edge", exact: true })).toBeVisible();
    await expect(box.getByRole("columnheader", { name: "Option", exact: true })).toBeVisible();
    await expect(box.getByRole("columnheader", { name: "Stock vs option", exact: true })).toBeVisible();   // was "Winner" (read as wins)
    await expect(box.getByRole("columnheader", { name: "Won", exact: true })).toBeVisible();
    await expect(box.getByRole("columnheader", { name: "S&P 500", exact: true })).toBeVisible();
  }
});

test("tracker: lessons from the record list every locked rule, and a finished trade shows each rule's outcome", async ({ page }) => {
  await page.goto("/tracker");
  const l = page.getByTestId("lessons");
  await l.getByText("Lessons from the record").click();                              // owner 10-07: collapsible, like By period
  await expect(l.locator("tbody tr")).toHaveCount(4);
  await expect(l.getByText(/locked on .* before\s+we ran any of them against the record/)).toBeVisible();
  await page.getByLabel("Period").selectOption({ label: "Sealed test (Oct 2025–May 2026)" });
  await page.getByText(/^Every finished signal/).click();
  await page.getByRole("button", { name: /details$/ }).first().click();
  const r = page.getByTestId("rule-outcomes");
  await expect(r.getByRole("heading", { name: "With each lesson rule instead" })).toBeVisible();
  await expect(r.locator("tr")).toHaveCount(4);
});

test("tracker: a losing signal explains why it lagged, with how common each note is on winners", async ({ page }) => {
  await page.goto("/tracker");
  await page.getByLabel("Period").selectOption({ label: "Sealed test (Oct 2025–May 2026)" });
  await page.getByText(/^Every finished signal/).click();
  await page.getByLabel("Sort").selectOption("worst");
  await page.getByRole("button", { name: /details$/ }).first().click();
  const why = page.getByTestId("why-lost");
  await expect(why.getByRole("heading", { name: "Why it lagged the S&P 500" })).toBeVisible();
  await expect(page.getByText(/Seen on \d+% of (losers|winners) and \d+% of (losers|winners)/).first()).toBeVisible();
  await expect(page.getByText(/They describe what happened; they aren.t rules/)).toBeVisible();   // one footer for all notes
});

test("all bets: every bet with our verdict and a history chip, row opens the period table, manual lookup", async ({ page }) => {
  await page.goto("/alerts");                                   // old URL redirects
  await expect(page).toHaveURL(/\/bets/);
  await expect(page.getByText(/bets\. Click a row/)).toBeVisible();
  await expect(page.getByRole("columnheader", { name: /History says/ })).toBeVisible();
  await page.getByLabel("Show").selectOption("all");     // real cache: early in a session there may be no signal yet
  await page.getByRole("button", { name: /^[A-Z][A-Z0-9.-]* history$/ }).first().click();
  await expect(page.getByRole("cell", { name: "Every bet (baseline)", exact: true })).toBeVisible();
  await page.getByLabel("Filter bets by ticker").fill("ZZZZZZ");
  await expect(page.getByText("No bets for these filters.")).toBeVisible();
  await page.getByText("No ticker? Enter % out of the money and days instead").click();
  await page.getByRole("button", { name: "Check this bet" }).click();
  const r = page.getByTestId("check-result");
  await expect(r).toContainText(/Noise\.|Too few to tell\.|Too soon to tell\.|No earlier bets like this\.|test period\./);
  await expect(r).toContainText("not on the option");
  await expect(r).not.toContainText("Our filter");                  // by hand: no price or earnings, so no verdict
  await expect(r.getByTestId("history")).toBeVisible();              // owner 10-12: by hand showed an empty panel
  await r.getByRole("button", { name: "Clear the result" }).click();   // owner 10-12: no way to close it
  await expect(page.getByTestId("check-result")).toHaveCount(0);
});

test("all bets: check a bet the way UW shows it (ticker, strike, expiry), see the worked-out distance and jump to its rows", async ({ page }) => {
  await page.goto("/bets");
  const first = page.getByRole("button", { name: /^[A-Z][A-Z0-9.-]* history$/ }).first();
  test.skip(!(await first.count()), "no bets in this cache");
  const t = (await first.innerText()).trim();
  const check = page.getByRole("form", { name: "Check a bet" });
  await check.getByLabel("Ticker").fill(t);
  await check.getByLabel("Strike").fill("100");
  const exp = new Date(Date.now() + 40 * 864e5).toISOString().slice(0, 10);
  await check.getByLabel("Expiry").fill(exp);
  await check.getByRole("button", { name: "Check this bet" }).click();
  const line = page.getByText(new RegExp(`${t.replace(".", "\\.")} (last close|price on its latest UW alert) \\$`));
  await expect(line).toBeVisible();
  await expect(line).toContainText(/\d+ days\s+to\s+expiry/);
  await expect(page.getByTestId("check-result")).toContainText(/Signal: a |Not a signal\./);
  await expect(page.getByTestId("check-result")).toContainText("How similar bets did before");
  await page.getByRole("button", { name: /^Show (it|them)$/ }).click();
  await expect(page.getByLabel("Filter bets by ticker")).toHaveValue(t);
});

test("earnings: base rate and cheap/fair/rich by year first, then the coming reports with labels or a reason", async ({ page }) => {
  await page.goto("/earnings");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/Stocks beat it \d+% of the time/);
  await expect(page.getByText(/real option prices hasn.t been checked/i).first()).toBeVisible();
  await page.getByText("Cheap, fair, rich: year by year").click();
  await expect(page.getByRole("row").filter({ hasText: "Cheap" }).first()).toContainText("%");
  const coming = page.locator("section", { hasText: "Coming up" });
  const rows = coming.locator("tbody tr");
  if (await rows.count()) {
    await expect(rows.first()).toContainText(/Before open|After close|Time not set/);
    await expect(rows.first()).toContainText(/Cheap|Fair|Rich|implied|past reports?\b/);
  } else {
    await expect(coming.getByText(/No reports listed/)).toBeVisible();
  }
});

test("earnings reads like Sightings: neutral cheap/rich tiles, sun/moon times, implied move as a heat chip", async ({ page }) => {
  await page.goto("/earnings");
  for (const k of ["Look cheap", "Look rich"]) {
    const v = page.locator("dt", { hasText: k }).locator("xpath=following-sibling::dd[1]");
    await expect(v).not.toHaveClass(/text-bull|text-bear/);            // price, not direction: no blue/orange
  }
  await expect(page.getByText(/Cheap = options charge under [\d.]+× the usual move/)).toBeVisible();   // what the label means, always shown
  const rows = page.locator("section", { hasText: "Coming up" }).locator("tbody tr");
  if (await rows.count()) {
    await expect(page.getByText(/before the open, .*after the close/).first()).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Options price vs usual move" }).first()).toBeVisible();
    const implied = rows.locator("[data-heat]");
    if (await implied.count()) await expect(implied.first()).toHaveAttribute("data-heat", /^[123]$/);
  }
});

test("all bets: cut bets read grey so the signal stands out; price line is not the text colour", async ({ page }) => {
  await page.goto("/bets");
  const cut = page.getByText("Not a clean buy", { exact: true }).first();
  if (await cut.count()) await expect(cut).toHaveClass(/text-muted/);
  await page.goto("/ticker/SPY");
  const line = page.locator('[data-testid="price-line"]');
  if (await line.count()) await expect(line).toHaveAttribute("stroke", "var(--muted)");
});

test("ticker page: company name and description from UW's stock info sit in the header, no logo", async ({ page }) => {
  await page.goto("/ticker/NVDA");
  const head = page.locator('[data-testid="company"]');
  await expect(head).toContainText("NVIDIA");
  await expect(page.locator("header img")).toHaveCount(0);
  await expect(page.getByText(/Nvidia Corporation is/)).toBeVisible();
});

test("how it works: shortlist results bars are brass (the filter's-picks colour), never the text colour", async ({ page }) => {
  await page.goto("/methodology");
  const fills = page.locator("#results [data-bar]");
  await expect(fills.first()).toBeVisible();
  for (const f of await fills.all()) await expect(f).not.toHaveClass(/bg-text|border-text/);
  await expect(page.locator('#results [data-bar="brass"]').first()).toHaveClass(/bg-brass/);
});

test("a bearish watch-only card never shows buy and sell dates", async ({ page }) => {
  await page.goto("/");
  const summary = page.getByText(/^Bearish bets to watch/);
  await summary.click();
  const card = page.locator("article").filter({ hasText: "on watch only" }).first();
  if (!(await card.count())) return;                          // no bearish bets that day
  await card.getByRole("button", { name: "Show details" }).click();
  await expect(card.getByText("Watch only", { exact: true })).toBeVisible();
  await expect(card.getByText("The trade", { exact: true })).toHaveCount(0);
  await expect(card.getByText(/planned sell/)).toHaveCount(0);
});

test("all bets (was Ticker lookup): old /ticker address lands here, heading counts the bets, single ticker pages light no menu item", async ({ page }) => {
  await page.goto("/ticker");
  await expect(page).toHaveURL(/\/bets$/);
  await expect(page.locator("main h1")).toContainText(/\d[\d,]* one-way bets\. \d+ made the cut\./);
  await expect(page.getByRole("link", { name: "Flow check" })).toHaveAttribute("aria-current", "page");
  await page.goto("/ticker/SPY");
  await expect(page.locator('nav [aria-current="page"]')).toHaveCount(0);
});

test("sightings: reporting earnings today shows the biggest companies first, not the tiny ones with wild moves", async ({ page, request }) => {
  await page.goto("/");
  const t = await (await request.get("http://127.0.0.1:8199/api/desk/today")).json();
  const e = t.events?.earnings ?? {};
  const all = [...(e.premarket ?? []), ...(e.afterhours ?? [])] as { ticker: string; marketcap: number | null }[];
  test.skip(all.length === 0, "no reporters in the cache for this day");
  const want = topReporters({ premarket: (e.premarket ?? []) as { ticker: string; marketcap: number | null }[],
    afterhours: (e.afterhours ?? []) as { ticker: string; marketcap: number | null }[] }, t.events?.earnings_day, new Date())
    .map((r) => r.ticker);                                   // owner 10-16: top 5; after 9:30 ET only after-the-close
  expect(want.length).toBeLessThanOrEqual(5);
  const part = page.locator("section", { has: page.getByRole("heading", { name: /Reporting earnings/ }) });
  await expect(part.locator("ul li a")).toHaveCount(want.length);   // tiles load after the heading; wait (was flaky)
  const got = await part.locator("ul li a").evaluateAll((as) => as.map((a) => a.getAttribute("href")!.split("/").pop()));
  expect(got).toEqual(want);
  await expect(part).toContainText(want.length ? "Biggest companies reporting" : "came out before the open");  // after 9:30 ET a before-open-only day has no tiles
});

test("earnings: biggest reporting strip names the 6 largest coming reports, and each day lists the biggest first", async ({ page, request }) => {
  // Owner 10-16: top and popular companies first; show at least 5 (option A: Sightings-style tiles).
  await page.goto("/earnings");
  const e = await (await request.get("http://127.0.0.1:8199/api/desk/earnings")).json();
  type R = { ticker: string; date: string; marketcap: number | null; reported: boolean };
  const rows = e.upcoming as R[];
  test.skip(rows.length === 0, "no reports in the cache for the next sessions");
  const big = (a: R, b: R) => (b.marketcap ?? -1) - (a.marketcap ?? -1);
  const want = rows.filter((r) => !r.reported).sort(big).slice(0, 6).map((r) => r.ticker);
  const strip = page.locator("section", { has: page.getByRole("heading", { name: "Biggest reporting" }) });
  await expect(strip.locator("ul li a").first()).toBeVisible();          // the page streams in after its loading view
  const got = await strip.locator("ul li a").evaluateAll((as) => as.map((a) => a.getAttribute("href")!.split("/").pop()));
  expect(got).toEqual(want);
  await expect(strip).toContainText("Biggest companies reporting in the next");
  const day = e.sessions.find((d: string) => rows.some((r) => r.date === d));
  const first = page.locator("section", { has: page.getByRole("heading", { name: "Coming up" }) }).locator("table").first();
  const order = await first.locator("tbody tr td:first-child").allInnerTexts();
  expect(order).toEqual(rows.filter((r) => r.date === day).sort(big).map((r) => r.ticker));
});

test("status bar: no UW call count (UW sets no daily cap), but UW problems still show", async ({ page }) => {
  // Owner 10-16: hide the call count ("888 of 40,000" was our own fallback cap); warnings stay.
  await page.route("**/api/desk/status", async (route) => {
    const real = await (await route.fetch()).json();
    await route.fulfill({ json: { ...real, auth_failed: true, usage: { ...(real.usage ?? {}), count: 888, limit: 40000 } } });
  });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/market");
  const bar = page.getByRole("status").first();
  await expect(bar).toContainText("Unusual Whales turned down the API key or plan.");
  await expect(bar).not.toContainText(/UW calls|888|40,000/);
});
