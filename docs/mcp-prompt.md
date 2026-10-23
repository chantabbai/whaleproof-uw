# Using WhaleProof from an MCP app

WhaleProof's MCP server works with any MCP app (Claude Desktop, Claude Code, Cursor, VS Code…). Its tools read the
local cache only, so they make no Unusual Whales calls. Run the dashboard or the quick-start once first to fill it.

## Register (once)

Add this server entry to your MCP app's config (Claude Desktop: `claude_desktop_config.json`):
```json
{ "mcpServers": { "whaleproof": { "command": "uv",
  "args": ["run", "--directory", "<repo>/backend", "whaleproof", "mcp"] } } }
```
Command-line apps take the same command, for example `<app> mcp add whaleproof -- uv run --directory "<repo>/backend" whaleproof mcp`.

Optional: Unusual Whales' own MCP (`https://api.unusualwhales.com/api/mcp`, header `Authorization: Bearer <UW key>`).
It uses the same UW key, so its calls count against your daily budget.

## Tools
| tool | answers |
|---|---|
| `desk_signals` | today's signals with reasons, the whale's trade vs the tested stock action, the noise funnel, the biggest rejected alerts, whether today is still forming |
| `desk_ticker` | one ticker: flow by direction, GEX walls, dark-pool levels, IV rank, earnings, today's verdict, past signals by period |
| `desk_evidence` | has the filter paid? one plain-words row per test period, risk-adjusted, frozen thresholds |
| `desk_lookup` | "should I care about this flow?": today's bets on a ticker, a bet seen on UW (ticker + strike + expiry → would the filter take it, why, sealed-test record), or a described bet, with how earlier bets like it did |
| `desk_earnings` | earnings in the next five sessions: implied move vs the stock's own past moves (cheap/fair/rich), or one ticker; plus what 28K past reports say (description, not a trade) |
| `desk_tracker` | the signal record: finished per period (stock vs the S&P 500, the whale's option), open now, waiting |

## Suggested instructions (paste at the start of a chat)
> Use the whaleproof tools. For every number, say which tool it came from. Quote `in_plain_words` where a row has it.
> Write counts as words, not "n=". If a tool says "not proven" or the periods disagree, say so. Describe acting on a
> signal with the stock (that is what was tested). A `desk_lookup` result is history, not a signal. Never invent
> numbers. End with the disclaimer.

## Example questions
- "What passed WhaleProof's filter today, and why?"
- "Someone just bought $2M of NVDA calls 6% out of the money, 45 days out, as a sweep. Should I care?"
- "Show today's bets on SPY and how bets like them did before."
- "How are the live signals doing so far? Which ones are open?"
- "How did Technology signals do in the sealed test?"
- "Has this filter actually paid?"
