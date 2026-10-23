# Methodology

This is the detail behind the [README](../README.md): how the filter decides, what I tried before settling on it, how
the tests were kept fair, and how to run everything yourself. The dashboard's How it works page tells the same story
with pictures.

## How the filter decides

The dashboard and the backtest call the same function (`backend/whaleproof/desk/signals.py`), so what you see live is
exactly what was tested. Every threshold lives in `backend/whaleproof/desk/config.py`.

An alert has to get through six steps, in this order.

1. It has to be a clean opening buy. At least 70% of the premium traded at the ask, it's a single leg (not a floor or
   cross trade, not part of a spread or straddle), it's clearly opening a new position, the strike is between 5% in
   the money and 30% out of the money, and expiry is 7 to 90 days away. Stocks, ADRs and ETFs count, but ETF puts
   don't.
2. It has to be bullish. Big put buys lost money in the practice year, and most of them are insurance anyway.
3. The stock has to be at least $5, in line with UW's own liquidity guidance.
4. There can't be an earnings report between the flow and the planned sale. This uses the report's date and time,
   because a premarket report the next morning would land before the entry.
5. It has to show conviction, in one of two ways. A whale-size bet is $1M or more on a strike more than 5% out of the
   money. A long shot at a fair price is more than 15% out of the money with an option that isn't expensive, meaning
   an IV rank under 70 for the past year. That yardstick is the same live and in every test period.
6. Duplicates go. I keep one alert per ticker and direction per day, and signals from the same sector on the same day
   are flagged as one cluster, since they're really one bet.

The checks lean on published research: Pan & Poteshman (2006), Cremers & Weinbaum (2010), Xing, Zhang & Zhao (2010),
Ni, Pearson & Poteshman (2005) and Ni, Pan & Poteshman (2008). The How it works page says which paper backs which check.

## What I tried first

All of this was in the practice year, Oct 2024 to Sep 2025. Each result is the stock's five-day move against the
S&P 500, per trade.

| Idea | Result | Kept? |
|---|---|---|
| Every clean opening buy (16,400 trades) | −0.13% | No. Nothing on its own |
| Six kinds of buy alert on their own (sweeps, repeat buyers, before earnings, far out of the money, …) | −1.5% to 0.0% | No. None beat the market alone |
| Bearish bets (put buys) | −0.68% | No. Mostly insurance |
| Dark-pool buying as a filter | +0.5% (most vs least) | No. Right direction, but could be luck |
| Sector flow as a filter | the strongest third did 0.8% worse | No. Wrong direction |
| A 12-part score (including GEX, insider buying, market regime) | top 5 a day +0.06% | No. Same as the market |
| 687 combinations of simple rules | only those with 100+ trades that made money in both halves of the year | Shortlist |
| Cheap option + bullish (about 18 a day) | +0.90% | No. Failed the timing test |
| Before earnings + cheap option | +2.02% | No. Under 200 trades, and the range included zero |
| **Call more than 15% out of the money at a fair price** | **+1.99%** | **Yes: the long-shot signal** |
| **$1M+ on a call more than 5% out of the money** | **+1.42%** | **Yes: the whale signal** |

The timing test asks whether the stock did better after the alert than that same stock usually does in a week. If it
didn't, the alert just picked a strong stock, not a good moment. Dark pool, gamma walls and sector flow still show up
on the ticker and Market pages as context. They just don't decide anything. Skew and sentiment had no history to test.

The raw research output behind this table is in [`analysis-train-simple.md`](analysis-train-simple.md),
[`analysis-train-combos.md`](analysis-train-combos.md) and [`analysis-train.md`](analysis-train.md). The first and
last start with a short guide to reading them.

## Keeping the tests fair

There are four periods.

| Period | What it is |
|---|---|
| 🔒 Oct 2023 – Sep 2024 | The second sealed test: an older year nobody had looked at. Opened once |
| Oct 2024 – Sep 2025 | The practice year, where I chose the rules. Expect it to look best |
| 🔒 Oct 2025 – May 2026 | The sealed test. Rules locked first, then opened once |
| Jun – Sep 2026 | Recent months. I'd already looked at them, so it's a report, not a test |

I froze the rules before opening either sealed test, and every result file records which version of the rules it
used. In every period a decision only uses what was known that day, the stock is bought at the next morning's open and sold at the close five trading days later, 0.10% is taken off for
costs, and the result is compared with both the S&P 500 and every one-way UW alert. The live dashboard runs the same
code. `whaleproof evidence --holdout` refuses to run the sealed test a second time.

The second sealed test was run as two separate tests, one per signal type, and I wrote down the pass/fail rule before
pulling any data. Both came back "does not support". The whale signals made +0.59% over 63 trades
([`PREPERIOD-TEST.md`](PREPERIOD-TEST.md)). The long shots made +2.17% over 170 trades, but the per-day 95% range
started at −0.03%, just below zero, so they missed by a hair ([`PREPERIOD-FAROTM-TEST.md`](PREPERIOD-FAROTM-TEST.md)).
Those long-shot gains lean on a few big winners: without the top 5 trades the average is about +1.1%. The +1.74% in
the README is both signal types together.

## What the record shows

The filter takes about 3,900 alerts a day down to about 4 signals. In the practice year and both sealed tests, the
alerts it throws out did worse than the ones it keeps. Bearish buys made −0.16% to −0.68% a trade,
and alerts with earnings inside the hold made −0.24% to −0.77%.

Signals beat every one-way UW alert in 3 of the 4 periods, including both sealed tests. The miss was Jun–Sep 2026, at
−1.55% a trade.

Part of the edge is just volatile stocks. Signal stocks swing 2.1 to 2.4 times as much as the S&P 500. Adjusting for
that, the signals still come out ahead in the same 3 periods, but by less: on the same set of trades the sealed test
goes from +1.38% to +0.57% a trade. The swing also explains about 40% of the Jun–Sep 2026 loss
([`BETA-CHECK.md`](BETA-CHECK.md)).

Per trade the sealed test shows +1.43%. Averaged per day it's +1.12%, and the 95% range (from a 5-day block bootstrap)
runs from −0.06% to +2.41%. That range touches zero, so whether the signals make money is not proven.

On the dashboard, a signal that's still in its hold shows the price move since the entry open, like the open P/L in a
broker app, with the result after the 0.10% costs beside it. A finished signal leads with the after-cost result.
Sightings, ticker pages, Track record and the MCP all use the same function, so a signal shows the same number
everywhere.

## Running it

`scripts/desk.sh quickstart` fills an empty cache with the last five finished trading days: the flow alerts, plus
earnings, sector, IV rank and price bars for any ticker that could become a signal, and the option histories of the
signals. Then it starts the dashboard. That costs about 330 UW calls in a quiet week and about 500 in a busy one, and
takes around 80 seconds. There's no call cap unless you set one with `--max-calls N`, and `--sessions N` goes further
back, at about 55 calls a day. Running it again reuses the cache and costs about 10 calls.

After the quick-start, Sightings, Market, Earnings, Flow check, the ticker pages and the MCP tools all have data. How it
works and the test results come from files in the repo, so they're complete from the start. A ticker's past signals
back to 2023 and the full Track record need the long backfill below. Without it, Track record only shows the signals
from the days you fetched.

The "alerts came in" count leaves out index options (SPX, SPXW, RUT, VIX), because UW's history replies don't include
their stock price. They never pass the filter, so signals and results aren't affected.

Other commands, run from `backend/`:

| Command | What it does |
|---|---|
| `uv run whaleproof backfill --start 2024-10-01 --end <yesterday>` | Pulls the full history. This one uses UW calls, about 1,000 to 2,000 per week of history, so run it after the 8 PM ET quota reset |
| `uv run whaleproof forward` | Refreshes the live [forward record](FORWARD-RECORD.md) from the cache |
| `uv run python scripts/desk_build_rows.py A B`, then `uv run whaleproof evidence` | Rebuilds the test results from the cache |
| `uv run python scripts/research/earnings_moves.py` | Rebuilds the earnings history behind the Earnings page |

If you remove your key later, the dashboard keeps showing what it already fetched and says so in the status bar.

The live refresher reads UW's daily request count from every response. It keeps 1,500 calls in reserve, stops if UW
says the daily quota is used up, and shows why in the status bar. With the market open it uses about 13,000 to 14,000
calls a day, mostly price checks every minute for the tickers on screen, well inside a 40,000-a-day plan. The quota
resets at 8 PM ET.

To run the tests: `cd backend && uv run pytest -q` runs the unit tests against a fake UW client (GitHub Actions runs
these too). `cd frontend && npx playwright test` runs the end-to-end tests on desktop and phone sizes. Those start the
real API on your local cache, so they need a filled cache.
