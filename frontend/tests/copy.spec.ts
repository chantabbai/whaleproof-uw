import { expect, test } from "@playwright/test";

// Copy guard (field review 10-06): the pages read pro-UW, and "not proven" is said once where results are shown,
// through the evidence badge, instead of on every tile. The technical appendix (/methodology/details) is exempt.
const AT_MOST_ONCE = ["/", "/tracker", "/ticker/SPY", "/methodology"];
const NEVER = ["/market", "/watchlist", "/journal", "/earnings", "/bets"];
const BANNED = /blind alerts|buying every alert|firehose/i;

const mainText = (page: import("@playwright/test").Page) => page.locator("main").evaluate((m) => m.textContent ?? "");

for (const path of [...AT_MOST_ONCE, ...NEVER]) {
  test(`copy on ${path}: pro-UW wording, "not proven" said once at most`, async ({ page }) => {
    await page.goto(path);
    const text = await mainText(page);
    expect(text).not.toMatch(BANNED);
    const n = (text.match(/not proven/gi) ?? []).length;
    expect(n).toBeLessThanOrEqual(AT_MOST_ONCE.includes(path) ? 1 : 0);
    const foot = page.locator("body > footer");
    await expect(foot).toContainText("not investment advice");
    await expect(foot).toContainText("Unusual Whales");
  });
}

test("evidence badge leads with the result and links to how it was tested", async ({ page }) => {
  await page.goto("/");
  const badge = page.getByRole("link", { name: /Our shortlist of UW alerts added an edge in \d of \d test periods/ });
  await expect(badge).toBeVisible();
  await expect(badge).toContainText("Backtested 2023–2026. See how it was tested");   // owner 10-23: was "Not proven yet."
  await expect(badge).toHaveAttribute("href", /\/methodology/);
});

// Owner 10-08: pages never point readers at repo files ("The full method is in docs/X.md").
for (const path of [...AT_MOST_ONCE, ...NEVER, "/methodology/details"]) {
  test(`no .md file names on ${path}`, async ({ page }) => {
    await page.goto(path);
    for (const d of await page.locator("details").all()) await d.evaluate((e) => ((e as HTMLDetailsElement).open = true));
    expect(await mainText(page)).not.toMatch(/\.md\b/i);
  });
}


// Owner 10-13 ("no confusion, even a plural"): every page, with every section and the first rows opened, is free of
// the small slips that crept in before — a GOOGL 339-day call read "expires Fri, Sep 17" in October, "1 days",
// "(… position.).", "-82.0%", "$1650 call", "−0%", "230–230", "Sep 17, 27".
const SMELLS: [string, RegExp][] = [
  ["count of one with a plural noun", /\b1 (days|bets|alerts|signals|trades|sessions|buys|holds|reports|periods|times|months|contracts|shares)\b/],
  ["full stop before a closing bracket", /\.\)/],
  ["double full stop", /(?<!\.)\.\.(?!\.)/],
  ["empty brackets", /\(\s*\)/],
  ["code value leaked into copy", /\b(undefined|null|NaN|Infinity)\b/],
  ["ASCII hyphen as a minus", /(^|[\s(])-\d/m],
  ["dollar amount without a thousands comma", /\$\d{4,}(?![\d,])/],
  ["minus zero", /−0(\.0+)?%/],
  ["same number twice in a range", /\b(\d[\d,.]*)–\1\b/],
  ["\"0 days\" for an option expiring today", /\b0 days\b/],
  ["two-digit year", /\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{1,2}, \d{2}\b(?!\d)/],
  ["\"put\" as a verb next to option flow (reads as the option type)", /\bwhale put \$/i],
];
for (const path of ["/", "/market", "/earnings", "/bets", "/watchlist", "/journal", "/tracker", "/methodology",
  "/methodology/details", "/ticker/SPY", "/ticker/NVDA"]) {
  test(`no copy slips on ${path}, everything opened`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await page.evaluate(() => {
      document.querySelectorAll("details").forEach((d) => { d.open = true; });
      document.querySelectorAll("button").forEach((b) => { if (/^(Show details|\+)$/.test((b.textContent ?? "").trim())) b.click(); });
    });
    let text = await page.locator("main").innerText();
    const rows = page.locator("tr[aria-expanded]");
    for (let i = 0; i < Math.min(await rows.count(), 12); i++) {         // open the first rows one by one (accordion)
      await rows.nth(i).click({ position: { x: 5, y: 5 } });
      text += "\n" + (await rows.nth(i).evaluate((r) => (r.nextElementSibling as HTMLElement | null)?.innerText ?? ""));
    }
    for (const [name, re] of SMELLS) {
      const m = text.match(re);
      expect(m, `${name}: “…${m ? text.slice(Math.max(0, (m.index ?? 0) - 40), (m.index ?? 0) + 40) : ""}…”`).toBeNull();
    }
  });
}
