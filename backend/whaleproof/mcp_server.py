"""WhaleProof MCP server (Plan 3). Use it from any MCP app (Claude Desktop, Claude Code, Cursor…).

Every tool is a thin, read-only view over the same local API the dashboard uses (built in-process from the same
`create_app`), so the MCP app, the dashboard and the CLI can never disagree. Cache only: no Unusual Whales calls.
Default tools: desk_signals, desk_ticker, desk_evidence, desk_lookup, desk_tracker. Every answer carries its period label, says "not proven" where it
applies, and includes the disclaimer. The old engine's tools are only built with build_server(..., legacy=True).

Register:  add `uv run --directory <repo>/backend whaleproof mcp` as a stdio server in your MCP app
"""
from __future__ import annotations

from datetime import date

from typing import Callable
from urllib.parse import urlencode

from mcp.server.mcpserver import MCPServer

from whaleproof.core.options.pnl import parse_contract, readable

DISCLAIMER = "Not investment advice. Paper-trade only until a strategy passes the one-time final exam."
NOT_RUNNING = "WhaleProof data is not available (the local database or journal could not be read)."
Get = Callable[[str], object]
DESK_DISCLAIMER = ("Not financial advice. Signals are filtered observations of public options flow, not recommendations; "
                   "every result says which test period it comes from, and past results do not predict future ones.")


# Plain names shared with the Methodology page (technical label in brackets for anyone cross-checking the docs).
PERIODS = (
    ("pre", "Second sealed test · Oct 2023 – Sep 2024", "An older year nobody had looked at; opened once (pre-period, out-of-sample)."),
    ("train", "Practice year · Oct 2024 – Sep 2025", "Where the rules were chosen, so expect it to look best (train, in-sample)."),
    ("holdout", "Sealed test · Oct 2025 – May 2026", "Rules locked first, then opened once: the main exam (holdout, out-of-sample)."),
    ("post", "Recent months · Jun – Sep 2026", "Seen before the rules were locked, so a report, not a test (post-period)."),
)
HOW_TO_READ = ("Each *_avg_per_trade is the average five-day stock move in the signal's direction minus the S&P 500 (SPY) "
               "over the same days, after 0.10% costs, per trade. signals_traded = how many signals that average is over "
               "(more trades = more trustworthy). buying_every_alert = the same for every directional UW alert, the baseline.")


def _pct(v) -> str:
    if v is None:
        return "n/a"
    s = f"{v:+.2%}"                     # true minus like the app; a move that rounds to zero has no sign
    return "0.00%" if s in ("+0.00%", "-0.00%") else s.replace("-", "−")


def _plain_period(name: str, s, a, traded, lo=None, hi=None) -> str:
    """One quotable sentence per period, trade count written out — so answers never fall back to '(n=170)'."""
    label, _, dates = name.partition(" · ")
    out = (f"{label} ({dates}): {traded} signal{'' if traded == 1 else 's'} traded, averaging {_pct(s)} per trade vs the S&P 500 over five days "
           f"(after costs); all one-way UW alerts averaged {_pct(a)}.")
    if lo is not None and hi is not None:
        out += (f" Likely range of the average signal day: {_pct(lo)} to {_pct(hi)}"
                + (" — range includes zero." if lo <= 0 <= hi else " — stays on one side of zero."))
    return out


def _period_row(name: str, what: str, sig: dict, allr: dict) -> dict:
    s, a = sig.get("mean"), allr.get("mean")
    return {"period": name, "what_it_is": what,
            "in_plain_words": _plain_period(name, s, a, sig.get("n"), sig.get("ci_low"), sig.get("ci_high")),
            "signals_avg_per_trade": _round(s), "buying_every_alert_avg_per_trade": _round(a),
            "signals_traded": sig.get("n"), "beat_buying_every_alert": None if s is None or a is None else s > a}


def _cluster(c: dict | None) -> dict | None:
    """Same-sector signals on the signal's own day (not today, for older holds). ETFs have no sector: 'Unknown' is no cluster."""
    if not c or c.get("sector") in (None, "", "Unknown"):
        return None
    return {"sector": c.get("sector"), "signals_in_sector_that_day": c.get("n")}


def _md(iso: str | None) -> str:
    if not iso:
        return "?"
    d = date.fromisoformat(iso[:10])
    return f"{d:%b} {d.day}"


def _past_by_period(ticker: str, past: list[dict]) -> list[str]:
    """Per-period sentence for one ticker's past signals (count, how many beat the S&P 500, average)."""
    groups: dict[str, list] = {}
    for p in past:
        groups.setdefault(p.get("period") or "Unlabeled", []).append(p.get("x5"))
    out = []
    for period, xs in groups.items():
        done = [x for x in xs if x is not None]
        k = len(xs)
        head = f"{period}: {k} past signal{'s' if k != 1 else ''} on {ticker}"
        if not done:
            out.append(f"{head}, still inside {'its' if k == 1 else 'their'} five-day hold (no result yet).")
            continue
        line = (f"{head}, {sum(x > 0 for x in done)} beat the S&P 500 over five days, "
                f"average {_pct(sum(done) / len(done))} per trade")
        if len(done) < k:
            line += f" ({k - len(done)} still inside the five-day hold)"
        out.append(line + ".")
    return out


def _evidence_line(ev: dict | None) -> dict | None:
    """Short per-period summary for desk_signals (from the Today API's evidence)."""
    if not ev:
        return None
    rows = [_period_row(name, what, ev[k]["signals"], ev[k]["all"]) for k, name, what in PERIODS if ev.get(k)]
    return {"periods": rows, "how_to_read": HOW_TO_READ}


def _round(v, n=4):
    return None if v is None else round(v, n)


def _desk_signal(x: dict) -> dict:
    """One signal for the assistant: the whale's option trade is the evidence (`whale_did`); the action that was tested is the
    stock (`tested_action`), so an answer never reads as 'copy this option'."""
    out = {k: x.get(k) for k in ("ticker", "direction", "tier", "why", "entry", "exit_by", "next_earnings", "cluster")}
    out["cluster"] = _cluster(out["cluster"])
    if x.get("since_entry") is not None:
        # same numbers as the Sightings page and Track record: price move (no fees) and net after the 0.10% round trip
        out["since_entry"] = {"price_move": _round(x["since_entry"]), "net_after_costs": _round(x.get("since_entry_net")),
                              "entry_price": x.get("entry_price"), "last_price": x.get("last_price"),
                              "marked_at": x.get("price_source")}
    else:
        out["since_entry"] = None
    out["signal_type"] = {"whale": "Whale-size bet", "far_otm": "Long shot, not overpriced"}.get(x.get("tier"), x.get("tier"))
    out["whale_did"] = {k: x.get(k) for k in ("premium", "kind", "strike", "expiry", "dte", "otm_pct")}
    if x.get("direction", 1) > 0 and not x.get("watch_only"):
        out["tested_action"] = (f"Buy {x.get('ticker')} stock at the {_md(x.get('entry'))} open and sell at the "
                                f"{_md(x.get('exit_by'))} close. That's what the backtest measured.")
    else:
        out["tested_action"] = "None. It's a bearish bet to watch, not a tested signal."
    return out


LOOKUP_NOTE = ("History lookup: how earlier bets like this one did, measured on the stock over five days against the "
               "S&P 500. It describes the past. It isn't a tested signal; only the filter's signals were tested.")


def _history(h: dict) -> dict:
    """Lookup result with plain keys (earlier_bets_matched, beat_sp500_share, avg_vs_sp500) and its sentence."""
    def row(x: dict) -> dict:
        return {"earlier_bets_matched": x.get("matches"), "beat_sp500_share": _round(x.get("win_share")),
                "avg_vs_sp500": _round(x.get("avg")), "median_vs_sp500": _round(x.get("median"))}
    out = row(h) | {"in_plain_words": h.get("in_plain_words"), "too_few_to_tell": h.get("thin"),
                    "periods_agree": h.get("periods_agree"), "traits_dropped_to_find_matches": h.get("traits_dropped")}
    if h.get("periods"):
        out["periods"] = [{"period": p.get("period")} | row(p) for p in h["periods"]]
    if h.get("baseline"):
        out["all_bets_baseline"] = row(h["baseline"])
    return out


def _filter_words(f: dict | None) -> dict | None:
    """The API's filter check on a described contract → would it be a signal, why, and that type's sealed-test record."""
    if not f:
        return None
    out = {"is_signal": bool(f.get("signal")), "filter_said": f.get("reason")}
    if f.get("tier"):
        out["signal_type"] = {"whale": "Whale-size bet", "far_otm": "Long shot, not overpriced"}.get(f["tier"], f["tier"])
    r = f.get("record")
    if r:
        out["sealed_test_record"] = {
            "trades": r["trades"], "beat_sp500_share": _round(r["beat"]), "avg_vs_sp500": _round(r["avg"]),
            "in_plain_words": f"In the sealed test (Oct 2025 to May 2026), {r['trades']:,} {out['signal_type'].lower()} "
                              f"signals traded on the stock (next open, sold five days later): {r['beat']:.0%} beat the "
                              f"S&P 500, average {_pct(r['avg'])} a trade after costs. Not proven."}
    return out


def _bet(b: dict) -> dict:
    return {"side": "bullish" if b.get("direction", 1) > 0 else "bearish", "option_type": b.get("opt_type"),
            "bet_kind": b.get("bet_kind"), "premium": b.get("premium"), "strike": b.get("strike"),
            "expiry": b.get("expiry"), "days_to_expiry": b.get("dte"), "otm_pct": _round(b.get("otm_pct")),
            "sweep": b.get("sweep"), "sector": b.get("sector"), "is_signal": b.get("verdict") == "signal",
            "filter_said": "passed: today's signal" if b.get("verdict") == "signal" else b.get("reason")}


def _avg(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


MIN_OPTIONS_PRICED = 10   # fewer → the option average is not quoted in words (2 priced read as +58%)


def _tracker_period(period: str, rows: list[dict]) -> dict:
    done = [r for r in rows if (r.get("stock") or {}).get("status") == "closed" and r["stock"].get("vs_spy") is not None]
    vs = [r["stock"]["vs_spy"] for r in done]
    opts = [(r.get("option") or {}).get("ret") for r in done if (r.get("option") or {}).get("ret") is not None]
    beat, avg, oavg = sum(v > 0 for v in vs), _avg(vs), _avg(opts)
    if done:
        words = (f"{period}: {len(done)} finished signal{'s' if len(done) != 1 else ''}, {beat} beat the S&P 500 over "
                 f"the five-day hold, stock average {_pct(avg)} per trade vs the S&P 500 after costs")
        if len(opts) >= MIN_OPTIONS_PRICED:
            words += f"; the whale's own option averaged {_pct(oavg)} ({len(opts)} priced)."
        else:
            words += f"; too few whale options priced to tell ({len(opts)})."
    else:
        words = f"{period}: no finished signals yet."
    return {"period": period, "signals": len(rows), "finished": len(done), "beat_sp500": beat,
            "stock_avg_vs_sp500": _round(avg), "stock_avg_return": _round(_avg([r["stock"].get("ret") for r in done])),
            "whale_option_avg_return": _round(oavg) if len(opts) >= MIN_OPTIONS_PRICED else None,
            "whale_options_priced": len(opts), "in_plain_words": words}


def _tracker_open(r: dict) -> dict:
    """An open hold priced like Sightings: the API's live mark (`stock.now`, `hold_day`, `option.now`) while the
    market is open, else the last close. vs the S&P 500 is on daily bars (the record's rule); while the market is open
    the latest bar is today's, so it is "so far", not "at the last close"."""
    s, o = r.get("stock") or {}, r.get("option") or {}
    now, onow = s.get("now") or {}, o.get("now")
    live = now.get("price") is not None
    opt = o.get("contract") and {"contract": o["contract"], "paid": _round(o.get("buy"), 2),
                                 "price_now": _round(onow["bid"] if onow else o.get("sell"), 2),
                                 "return_so_far": _round(onow["ret"] if onow else o.get("ret")),
                                 "price_source": "live" if onow else "last close"}
    return {"ticker": r["ticker"], "signal_day": r.get("session_date"), "entry_date": s.get("entry_date"),
            "entry": now.get("entry") or s.get("entry"), "price_now": now["price"] if live else s.get("last"),
            "price_source": "live" if now.get("source") == "live" else "last close",
            "day_of_hold": r.get("hold_day") or s.get("days_held"), "exit_by": r.get("exit_by"),
            "price_move_so_far": _round(now["move"] if live else s.get("move")),
            "net_after_costs_so_far": _round(now["net"] if live else s.get("ret")),
            "vs_sp500_so_far": _round(s.get("vs_spy")), "whale_option": opt or None,
            "period": r.get("period")}


def _pick_summary(p: dict) -> dict:
    plan, pnl = p.get("plan") or {}, p.get("pnl") or {}
    return {"rank": p.get("rank"), "ticker": p["ticker"], "direction": "long" if p["direction"] > 0 else "short",
            "whale_contract": p.get("contract"), "we_buy": pnl.get("contract"),
            "entry_ref": plan.get("entry_ref"), "stop": plan.get("invalidation"), "target": plan.get("target"),
            "max_hold_sessions": plan.get("time_stop_sessions"), "exit_by": p.get("exit_by"),
            "option_premium": _round(pnl.get("entry_premium"), 2),
            "option_at_target": _round(pnl.get("ret_target_net", pnl.get("ret_target"))),
            "option_at_stop": _round(pnl.get("ret_stop_net", pnl.get("ret_stop"))),
            "option_reward_to_risk": _round(pnl.get("option_rr"), 2), "delta": _round(pnl.get("delta"), 2),
            "option_value": (p.get("value") or {}).get("verdict"),
            "next_morning_check": (p.get("confirmation") or {}).get("status", "pending (8:30 AM ET)"),
            "money_still_in": (p.get("health") or {}).get("state"),
            "result_so_far": p.get("outcome"), "why": p.get("reasons_for"), "against": p.get("reasons_against")}


def _readable(v):
    """Every contract code in an answer → "SPY $765 Call · Nov 20 '26 (SPY261120C00765000)" (owner 09-29)."""
    if isinstance(v, dict):
        return {k: _readable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_readable(x) for x in v]
    if isinstance(v, str) and parse_contract(v):
        return f"{readable(v)} ({v})"
    return v



def _when(time: str | None) -> str:
    return {"premarket": "before the open", "postmarket": "after the close", "afterhours": "after the close"}.get(
        time or "", "at a time not yet known")


def _day_words(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{d:%a}, {d:%b} {d.day}"


def _earn_words(r: dict) -> str:
    """One coming report in plain words (UW implied move vs the ticker's own past report moves)."""
    imp = r.get("implied")
    s = f"{r['ticker']} {'reported' if r.get('reported') else 'reports'} {_day_words(r['date'])} {_when(r.get('time'))}."
    if imp is None:
        return s + f" No implied move yet ({r.get('note') or 'not listed'})."
    s += f" Options price a move of about {imp:.1%};"
    if not r.get("label"):
        return s + f" no label ({r.get('note')})."
    s += (f" its median move on its last {r['history_reports']} reports was {r['past']:.1%}, so the implied move looks "
          f"{r['label']} ({r['ratio']:.2f}×).")
    hist = [h for h in r.get("history") or [] if h.get("beat") is not None]
    if hist:
        k = sum(1 for h in hist if h["beat"])
        s += f" On the {len(hist)} most recent reports the move beat the implied move {k} time{'' if k == 1 else 's'}."
    return s


def _earn_history_words(b: dict | None) -> str:
    if not b:
        return "The earnings backtest has not been run on this install."
    L, y26 = b["by_label"], (b.get("by_label_year", {}).get("cheap") or {}).get("2026")
    return (f"Across {b['scored']:,} reports since 2022, the next-day move beat UW's implied move on {b['all']['beat']:.0%} "
            f"of them (options usually price a bigger move than happens). By label: cheap {L['cheap']['beat']:.0%}, "
            f"fair {L['fair']['beat']:.0%}, rich {L['rich']['beat']:.0%}; that order held every year 2023–2026, so the "
            f"label is a fair description. It is not a trade: even cheap reports beat the implied move only "
            f"{(y26 or L['cheap'])['beat']:.0%} of the time in 2026, and real option prices were not tested — not proven "
            f"to pay. Exploratory.")

def build_server(get: Get, legacy: bool = False) -> MCPServer:
    """`get(path)` returns the API's JSON for a path, or None when unavailable. Exposes the three desk tools; the old
    WhaleProof engine's tools (option picks, finalists, scorecard…) only with `legacy=True` — owner 2026-09-30: they
    recommend options, which the tested results advise against, and their data is a stale copy in this fork."""
    raw_get = get
    get = lambda path: _readable(raw_get(path))  # noqa: E731
    rejected = lambda: getattr(raw_get, "rejected", None)  # noqa: E731 — the API's reason a lookup was refused
    mcp = MCPServer("whaleproof", instructions=(
        "WhaleProof filters Unusual Whales options-flow alerts down to a few signals a day and tests which kinds have "
        "paid. Use the tools' plain period names (second sealed test, practice year, sealed test, recent months) and "
        "write counts as words ('628 signals traded'), never 'n=', 'n', 'CI' or other statistics shorthand; when a row has "
        "in_plain_words, quote or paraphrase it rather than rebuilding the numbers. Cite which tool each number came from, say 'not proven' when "
        "the tool says so, never invent numbers, describe acting on a signal with the stock (that is what was tested), "
        "and end with the disclaimer."))

    def down() -> dict:
        return {"error": NOT_RUNNING, "disclaimer": DISCLAIMER}

    @mcp.tool()
    def desk_signals() -> dict:
        """Signal Desk: today's high-conviction signals (UW flow that passed the noise filter) with the plain-English
        reasons each one passed, signals still inside their five-day hold, the noise funnel (raw alerts → signals) and the
        biggest alerts the filter rejected with the reason. Start here for 'what is worth looking at today?'."""
        d = get("/api/desk/today")
        if not d:
            return down()
        out = {"flow_day": d["day"], "still_forming": bool(d.get("forming")), "funnel": d["funnel"],
               "signals": [_desk_signal(x) for x in d["signals"]], "still_open": [_desk_signal(x) for x in d["active"]],
               "rejected_biggest": d["rejected_top"][:8], "regime": {k: d["regime"].get(k) for k in ("gamma", "tide_last")},
               "evidence": _evidence_line(d.get("evidence")), "disclaimer": DESK_DISCLAIMER}
        if d.get("forming"):         # same words as Sightings while the day's flow is still coming in
            words = (f"{_day_words(d['day'])} is still forming: nothing is final until 4:15 PM ET, and the rule buys at "
                     "the next open, so today's signals are to watch, not buy yet.")
            if not d["signals"] and (lt := d.get("latest")):
                words += f" Latest signals: {_day_words(lt['day'])}, {', '.join(lt['tickers'])}."
            out["in_plain_words"] = words
        return out

    @mcp.tool()
    def desk_ticker(ticker: str) -> dict:
        """Signal Desk drill-down for one ticker: 30-day flow by direction, GEX walls, dark-pool levels, IV rank,
        earnings dates with report time, today's signal or why it was rejected, and every past signal with its five-day
        stock result vs the S&P 500, labeled by test period (second sealed test, practice year, sealed test, recent months)."""
        d = get(f"/api/desk/ticker/{ticker.strip().upper()}")
        if not d:
            return down()
        past = [{"date": p.get("date"), "tier": p.get("tier"), "direction": p.get("direction"), "premium": p.get("premium"),
                 "otm_pct": p.get("otm_pct"), "net_result_5d": p.get("ret"), "result_5d_vs_sp500": p.get("x5"),
                 "period": p.get("period")}
                for p in d.get("past_signals") or []]
        iv = (d.get("iv_rank") or [None])[-1]
        today = [x | {"cluster": _cluster(x.get("cluster"))} for x in d.get("signal_today") or []]
        flow = [{"date": f.get("date"), "bullish_premium": f.get("bull"), "bearish_premium": f.get("bear"),
                 "other_premium": f.get("other"), "alerts": f.get("n")} for f in d.get("flow_daily") or []]
        return {k: d.get(k) for k in ("ticker", "sector", "gex", "dp_levels", "earnings", "rejected_today")} | {
            "signal_today": today, "flow_daily": flow, "past_signals": past,
            "past_signals_by_period": _past_by_period(d.get("ticker") or ticker.strip().upper(), d.get("past_signals") or []),
            "iv_rank_latest": iv and {"date": iv.get("date"), "iv_rank": iv.get("v")}, "disclaimer": DESK_DISCLAIMER}

    @mcp.tool()
    def desk_evidence() -> dict:
        """Has the WhaleProof filter paid? One plain-words row per test period (second sealed test 2023-24, practice year
        where the rules were chosen, sealed test, recent months already seen): alerts/day → signals/day and the average five-day
        return vs SPY of signals vs all directional alerts, the beta-adjusted check, the frozen filter thresholds and
        research citations."""
        d = get("/api/desk/methodology")
        if not d:
            return down()
        ev = d.get("evidence") or {}
        tp = ev.get("train_post") or {}
        wins = {"pre": ev.get("preperiod_farotm") or ev.get("preperiod"), "train": tp.get("train"),
                "holdout": ev.get("holdout"), "post": tp.get("post")}
        beta = d.get("beta") or {}
        periods = []
        for k, name, what in PERIODS:
            w = wins.get(k)
            if not w:
                continue
            row = _period_row(name, what, w["signals"], w["all_directional"])
            sg = w["signals"]
            row |= {"signals_per_day": _round(w["funnel"]["per_day"].get("signals"), 1),
                    "alerts_per_day": _round(w["funnel"]["per_day"].get("raw"), 0),
                    "signal_win_rate": _round(sg.get("win_rate")),
                    "likely_range_per_day_95pct": [_round(sg.get("ci_low")), _round(sg.get("ci_high"))]}
            bs = (beta.get(k) or {}).get("signals") if isinstance(beta.get(k), dict) else None
            if bs:
                row |= {"signals_move_vs_market": _round(bs.get("avg_beta"), 2),
                        "risk_adjusted_signals_avg_per_trade": _round(bs["beta_adj"]["mean"])}
            periods.append(row)
        return {"periods": periods,
                "how_to_read": HOW_TO_READ + " signals_move_vs_market = how much more the signal stocks swing than the "
                "S&P 500 (2.4 = 2.4x); risk_adjusted_signals_avg_per_trade removes that extra swing. "
                "likely_range_per_day_95pct includes zero when the result could still be luck.",
                "filter": d["filter"], "citations": d["citations"],
                "reading": "UW flow carries information; the value is in which alerts you act on. Signals beat all one-way UW alerts "
                "in 3 of 4 periods (second sealed test, practice year, sealed test); the miss was the recent months "
                "(Jun-Sep 2026). Signal stocks swing about 2.3x as much as the S&P 500: after removing that, they still "
                "lead in the same 3 periods, with a smaller edge. The likely ranges include zero, so the edge is not "
                "proven. Best way to act on a signal: the stock.",
                "disclaimer": DESK_DISCLAIMER}

    @mcp.tool()
    def desk_lookup(ticker: str = "", side: str = "", option_type: str = "", premium: float = 0, days_to_expiry: int = 0,
                    otm_pct: float = 0, sweep: bool = False, bet_kind: str = "clean buy", sector: str = "",
                    strike: float = 0, expiry: str = "") -> dict:
        """'Should I care about this flow?' — how earlier UW bets like this one did (stock, five-day hold, vs the S&P 500),
        split by test period, next to the all-bets baseline. Three ways to ask:
        (1) ticker only, e.g. ticker="NVDA": today's UW-flagged directional bets on that ticker (biggest first, up to 5),
            each with what our filter said and its history;
        (2) a bet you saw on UW: ticker, side ("bullish"/"bearish"), option_type ("call"/"put"), premium in dollars,
            strike, expiry ("YYYY-MM-DD"), optional sweep and bet_kind → also whether our filter would take it, why,
            and that signal type's sealed-test record (days to expiry and % out of the money come from the last close);
        (3) describe a bet: side, option_type, premium, days_to_expiry,
            otm_pct as a fraction (0.05 = 5% out of the money, same unit as otm_pct in desk_signals / desk_ticker),
            optional sweep, bet_kind ("clean buy", "put sale", "not a clean buy"), sector. Descriptive history only — not a tested signal; only the filter's signals were tested."""
        if option_type:
            if side not in ("bullish", "bearish") or option_type not in ("call", "put"):
                return {"error": 'side must be "bullish" or "bearish" and option_type "call" or "put".',
                        "disclaimer": DESK_DISCLAIMER}
            if ticker.strip() and strike and expiry:
                q = {"direction": 1 if side == "bullish" else -1, "opt_type": option_type, "premium": float(premium),
                     "ticker": ticker.strip().upper(), "strike": float(strike), "expiry": expiry.strip()[:10],
                     "sweep": str(bool(sweep)).lower(), "bet_kind": bet_kind}
                h = get("/api/desk/lookup?" + urlencode(q))
                if not h and rejected():
                    return {"error": rejected(), "disclaimer": DESK_DISCLAIMER}
                if not h:
                    return down() | {"hint": "check the bet: premium in dollars ($100K or more), strike above 0, expiry "
                                             "YYYY-MM-DD and not passed, and a ticker the desk has a recent price for"}
                i = h.get("inputs") or {}
                return {"filter_check": _filter_words(h.get("filter")), "history": _history(h),
                        "worked_out_from": {"stock_price": i.get("spot"), "price_date": i.get("spot_date"),
                                            "otm_pct": _round(i.get("otm_pct"), 3), "days_to_expiry": i.get("dte"),
                                            "sector": i.get("sector")},
                        "label": h.get("label"), "disclaimer": DESK_DISCLAIMER}
            q = {"direction": 1 if side == "bullish" else -1, "opt_type": option_type, "premium": float(premium),
                 "dte": int(days_to_expiry), "otm_pct": otm_pct, "sweep": str(bool(sweep)).lower(),
                 "bet_kind": bet_kind} | ({"sector": sector} if sector else {})
            h = get("/api/desk/lookup?" + urlencode(q))
            if not h and rejected():
                return {"error": rejected(), "disclaimer": DESK_DISCLAIMER}
            if not h:
                return down() | {"hint": "check the bet's numbers (premium ≥ 0, days to expiry 0–3650, OTM fraction −1…10)"}
            return {"history": _history(h), "label": h.get("label"), "disclaimer": DESK_DISCLAIMER}
        t = ticker.strip().upper()
        if not t:
            return {"error": "Give a ticker (today's bets on it) or describe a bet (side, option_type, premium, "
                             "days_to_expiry, otm_pct).", "disclaimer": DESK_DISCLAIMER}
        d = get("/api/desk/alerts")
        if not d:
            return down()
        mine = sorted((b for b in d.get("bets") or [] if b.get("ticker") == t), key=lambda b: -(b.get("premium") or 0))
        bets = []
        for b in mine[:5]:
            detail = get(f"/api/desk/alerts/{b['id']}") or {}
            bets.append(_bet(b) | {"history": _history(detail.get("history") or {})})
        out = {"flow_day": d.get("day"), "ticker": t, "bets": bets, "bets_today_on_ticker": len(mine),
               "label": d.get("label") or LOOKUP_NOTE, "disclaimer": DESK_DISCLAIMER}
        if not mine:
            out["in_plain_words"] = (f"No UW-flagged bets on {t} on {d.get('day')}. Describe a bet instead (side, "
                                     "option_type, premium, days_to_expiry, otm_pct) to see how similar bets did.")
        return out

    @mcp.tool()
    def desk_tracker(period: str = "", sector: str = "") -> dict:
        """Signal Desk record: every signal the filter produced (history + live since Sep 30), priced at the daily close
        — stock bought at the next open and sold at the 5th session's close vs the S&P 500 after costs, and the whale's
        own option for comparison. Per period: finished signals, how many beat the S&P 500, averages, in plain words;
        plus signals open now (inside their five-day hold) and waiting for their entry open. Optional filters: period
        (start of the period name: "live", "sealed", "second", "practice", "recent") and sector (e.g. "Technology")."""
        d = get("/api/desk/tracker")
        if not d:
            return down()
        rows = [r for r in d.get("rows") or []
                if (not period or (r.get("period") or "").lower().startswith(period.strip().lower()))
                and (not sector or sector.strip().lower() == (r.get("sector") or "").lower())]
        groups: dict[str, list] = {}
        for r in rows:
            groups.setdefault(r.get("period") or "Unlabeled", []).append(r)
        periods = [_tracker_period(p, rs) for p, rs in groups.items()]
        st = lambda r: (r.get("stock") or {}).get("status")  # noqa: E731
        open_now = [_tracker_open(r) for r in rows if st(r) == "open"]
        waiting = [{"ticker": r["ticker"], "signal_day": r.get("session_date"), "entry_on": r.get("entry_on"),
                    "exit_by": r.get("exit_by")} for r in rows if st(r) == "waiting"]
        return {"prices_through": d.get("priced_through"), "filters": {"period": period or None, "sector": sector or None},
                "periods": periods, "open_now": open_now[:25], "open_now_total": len(open_now), "waiting": waiting,
                "how_to_read": d.get("note"), "disclaimer": DESK_DISCLAIMER}

    @mcp.tool()
    def desk_earnings(ticker: str = "") -> dict:
        """Earnings (exploratory): UW's implied earnings move compared with the stock's own past report moves →
        cheap / fair / rich, for reports in the next five sessions (or one ticker's next report and its last reports),
        plus what 28K past reports say about the label. Context, not a signal: the desk's filter already skips trades
        with earnings inside the five-day hold."""
        if ticker.strip():
            t = ticker.strip().upper()
            d = get(f"/api/desk/earnings/{t}")
            if not d:
                return down()
            nxt = d.get("next")
            return {"ticker": t, "next": nxt and (nxt | {"in_plain_words": _earn_words(nxt)}),
                    "past_reports": d.get("history") or [], "disclaimer": DESK_DISCLAIMER}
        d = get("/api/desk/earnings")
        if not d:
            return down()
        # rows keep their sentence (it counts the beats), not every past report: 40 full rows overflow an MCP app's answer limit
        coming = [{k: v for k, v in r.items() if k != "history"} | {"in_plain_words": _earn_words(r)}
                  for r in d.get("upcoming") or []]
        # same picks as the Earnings page's "Biggest reporting" strip: not out yet, biggest market cap first
        biggest = sorted((r for r in coming if not r.get("reported")), key=lambda r: -(r["marketcap"] if r.get("marketcap") is not None else -1))[:6]
        return {"calendar_as_of": d.get("at"), "sessions": d.get("sessions"),
                "what_history_says": _earn_history_words(d.get("backtest")), "biggest_coming": biggest,
                "coming": coming[:40], "coming_total": len(coming), "disclaimer": DESK_DISCLAIMER}

    if not legacy:
        return mcp

    @mcp.tool()
    def todays_picks() -> dict:
        """Today's 5 official picks (one per stock), with the plan (stop, target, exit date), the option WhaleProof
        would buy, its estimated gain at target / loss at stop after costs, and the next-morning check."""
        d = get("/api/picks")
        if not d:
            return down()
        return {"flow_day": d["session_date"], "enter_at_open_of": d["entry_session"],
                "picks": [_pick_summary(p) for p in d["picks"]], "status": "not proven", "disclaimer": DISCLAIMER}

    @mcp.tool()
    def finalist_trades() -> dict:
        """Today's whale buys matching the three finalist strategies (F1–F3) found in the learning year, their
        learning-year record, final-exam status, and stocks picked by more than one finalist."""
        d = get("/api/finalists")
        if not d:
            return down()
        out = []
        for f in d["finalists"]:
            ex = f.get("exam")
            exam = "not taken yet" if not ex else ("passed" if ex.get("tradeable") else f"not passed ({ex.get('status')})")
            trade = lambda t: {"ticker": t["ticker"], "direction": "long" if t["direction"] > 0 else "short",  # noqa: E731
                               "whale_premium": t.get("premium"), "whale_contract": t.get("contract"),
                               "we_buy": (t.get("pnl") or {}).get("contract"), "also_in": t.get("also_in", [])}
            out.append({"id": f["id"], "name": f["name"], "rules": f["blocks"], "learning_year": f.get("train"),
                        "final_exam": exam, "trades": [trade(t) for t in f["trades"]],
                        "waiting_for_8_30_check": [trade(t) for t in f.get("waiting", [])]})
        return {"flow_day": d["session_date"], "enter_at_open_of": d["entry_session"], "sell_at_close_of": d["exit_by"],
                "finalists": out, "overlap": d.get("overlap", []), "disclaimer": DISCLAIMER}

    @mcp.tool()
    def check_ticker(ticker: str) -> dict:
        """What WhaleProof knows about one stock from its local cache: last week's big whale alerts, last close, and
        whether it is in today's official picks or finalist lists. No live data."""
        t = ticker.strip().upper()
        d = get(f"/api/ticker/{t}")
        if d is None:
            return down()
        fin = get("/api/finalists") or {"finalists": []}
        picks = get("/api/picks") or {"picks": []}
        bars = d.get("bars") or []
        return {"ticker": t, "last_close": bars[-1]["close"] if bars else None,
                "last_close_date": bars[-1]["date"] if bars else None,
                "big_alerts_last_week": [{"contract": a.get("option_chain"), "premium": a.get("total_premium"),
                                          "at": a.get("created_at")} for a in (d.get("alerts") or [])[:10]],
                "in_todays_picks": any(p["ticker"] == t for p in picks["picks"]),
                "in_finalists": [f["id"] for f in fin["finalists"]
                                 if any(x["ticker"] == t for x in f["trades"] + f.get("waiting", []))],
                "disclaimer": DISCLAIMER}

    @mcp.tool()
    def explain_pick(ticker: str) -> dict:
        """Every official/intraday pick on a stock from the tamper-evident journal: plan, reasons for and against,
        next-morning check, whether the money is still in, and the result so far (stock and estimated option)."""
        t = ticker.strip().upper()
        h = get("/api/history")
        if h is None:
            return down()
        rows = [r for r in h if r["ticker"] == t]
        return {"ticker": t, "picks": [_pick_summary(r) | {
                    "flow_day": r.get("session_date"), "rules_version": r.get("weights_version"),
                    "option_result_estimate": r.get("option_result")} for r in rows],
                "note": "" if rows else f"no pick on {t} in the journal", "disclaimer": DISCLAIMER}

    @mcp.tool()
    def scorecard() -> dict:
        """The live record since Sep 28: official picks and the pure-buys research track, and whether the
        hash-chained journal is untampered."""
        s, p = get("/api/scorecard"), get("/api/pure")
        if not s:
            return down()
        o = s.get("overall") or {}
        return {"journal_untampered": s.get("chain_valid"),
                "official": {"scored": o.get("n"), "closed": s.get("closed_count"), "open": s.get("open_count"),
                             "win_rate": o.get("hit_rate"), "average_return": o.get("mean")},
                "pure_buys": (p or {}).get("scorecard"),
                "note": "Too few picks to judge yet.", "disclaimer": DISCLAIMER}

    @mcp.tool()
    def strategy_results(top: int = 10) -> dict:
        """Learning-year strategy lab: best mixes of simple rules (return vs market AND biggest drop), the chosen
        finalists, and a baseline of all clean whale buys. Learning-year only: not proof."""
        c = get("/api/combos")
        if not c:
            return {"error": "strategy results not available yet", "disclaimer": DISCLAIMER}
        row = lambda r: {"rules": r["blocks"], **{k: r.get(k) for k in (  # noqa: E731
            "trades_per_day", "win_rate", "mean_x5", "max_drawdown", "ci_low", "ci_high")}}
        return {"mixes_tested": c.get("tested"), "baseline_all_clean_buys": c.get("baseline"),
                "finalists": [row(r) for r in c.get("finalists", [])],
                "top": [row(r) for r in c.get("ranked", [])[:max(1, min(top, 20))]],
                "how_to_read": "mean_x5 = average five-day return vs the market per trade; max_drawdown = biggest fall "
                               "of an account taking these trades", "status": "not proven", "disclaimer": DISCLAIMER}

    @mcp.tool()
    def money_moved() -> dict:
        """Open picks where the whale's money shrank, exited, rolled or flipped (from next-morning open interest)."""
        m = get("/api/money-moved")
        if m is None:
            return down()
        return {"changes": m, "disclaimer": DISCLAIMER}

    return mcp


def local_api() -> Get:
    """The dashboard's API built in-process (no server needed, no network, no UW calls)."""
    import logging

    from fastapi.testclient import TestClient
    logging.getLogger("httpx").setLevel(logging.WARNING)      # keep stdio quiet

    from whaleproof.api.app import create_app
    from whaleproof.config import REPO_ROOT, load_settings
    s = load_settings()
    from whaleproof.desk.service import DeskService
    from whaleproof.desk.userdb import UserDB
    desk = (DeskService(s.db_path, ""), UserDB(REPO_ROOT / "data" / "signaldesk.sqlite"), REPO_ROOT / "data" / "desk")
    client = TestClient(create_app(s.journal_path, s.db_path, REPO_ROOT / "data" / "backfill.log",
                                   REPO_ROOT / "journal" / "backtest-summary.json", desk=desk))

    import time

    from whaleproof.core.data_layer.store import Store
    svc, store, last = desk[0], Store(s.db_path), [0.0]

    def refresh() -> None:
        # No refresher thread here: rebuild panels (earnings calendar, tide, quotes…) from the cache the dashboard keeps
        # writing, at most once a minute, so answers match the dashboard. The service has no key: never calls UW.
        if time.time() - last[0] > 60:
            last[0] = time.time()
            try:
                svc.refresh(store)
            except Exception:  # noqa: BLE001 — stale panels beat a failed answer
                pass
    return _api_get(client, refresh)


def _api_get(client, refresh: Callable[[], None]) -> Get:
    """JSON for a path, or None. `get.rejected` keeps the API's 400 message from the last call (a bad bet in a lookup:
    expiry passed, premium under $100K…), so desk_lookup can say why instead of 'not available'."""
    def get(path: str):
        refresh()
        get.rejected = None
        try:
            r = client.get(path)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 400:
                detail = r.json().get("detail")
                get.rejected = detail if isinstance(detail, str) else None
            return None
        except Exception:  # noqa: BLE001 — a broken read reads as "not available", never a crash
            return None
    get.rejected = None
    return get
