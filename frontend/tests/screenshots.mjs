// Capture README screenshots from the running dashboard: `node tests/screenshots.mjs` (needs scripts/desk.sh up).
import { chromium } from "@playwright/test";

const BASE = process.env.DESK_URL ?? "http://127.0.0.1:3100";
const PAGES = [["today", "/"], ["market", "/market"], ["ticker", "/ticker/MRVL"], ["watchlist", "/watchlist"],
  ["journal", "/journal"], ["tracker", "/tracker"], ["methodology", "/methodology"]];
const HIDE_DEV = "nextjs-portal { display: none !important; }";   // Next dev-mode badge
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
for (const [name, path] of PAGES) {
  await page.goto(BASE + path, { waitUntil: "networkidle" });
  await page.addStyleTag({ content: HIDE_DEV });
  await page.screenshot({ path: `../docs/screenshots/${name}.png`, fullPage: name !== "methodology" });
}
const phone = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
await phone.goto(BASE + "/", { waitUntil: "networkidle" });
await phone.addStyleTag({ content: HIDE_DEV });
await phone.screenshot({ path: "../docs/screenshots/today-phone.png" });
await browser.close();
console.log("saved to docs/screenshots/");
