"""Do the MCP and the dashboard agree? Runs each MCP tool on the MCP's own in-process API (cache) and on the running
dashboard API (:8100), prints every difference. Optional arg N: N rounds 70 s apart (a long-lived MCP must keep up).
Usage: cd backend && uv run python scripts/mcp_vs_dashboard.py [N]   (desk must be up; no UW calls)"""
import asyncio, json, sys, time, urllib.request


from whaleproof.mcp_server import build_server, local_api


def http_get(path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8100" + path, timeout=120) as r:
            return json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        print("http fail", path, e)
        return None


CALLS = [("desk_signals", {}), ("desk_tracker", {"period": "live"}), ("desk_ticker", {"ticker": "NVDA"}),
         ("desk_ticker", {"ticker": "CIEN"}), ("desk_evidence", {}), ("desk_earnings", {}),
         ("desk_earnings", {"ticker": "INTC"}), ("desk_lookup", {"ticker": "NVDA"})]
IGNORE = ("tide_last", "calendar_as_of", "age_s", "flow_daily")


def diff(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in IGNORE:
                continue
            out += diff(a.get(k, "<missing>"), b.get(k, "<missing>"), f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: len {len(a)} vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, f"{path}[{i}]")
    elif a != b:
        out.append(f"{path}: MCP={str(a)[:90]} | DASHBOARD={str(b)[:90]}")
    return out


async def run(c, name, args):
    r = await c.call_tool(name, args)
    return r.structured_content if r.structured_content is not None else json.loads(r.content[0].text)


async def main():
    from mcp import Client
    async with Client(build_server(local_api()), raise_exceptions=True) as mcp_srv,             Client(build_server(http_get), raise_exceptions=True) as web_srv:
        await loop(mcp_srv, web_srv)


async def loop(mcp_srv, web_srv):
    for rnd in range(int(sys.argv[1]) if len(sys.argv) > 1 else 1):
        if rnd:
            time.sleep(70)
        print(f"===== round {rnd + 1}")
        for name, args in CALLS:
            a, b = await run(mcp_srv, name, args), await run(web_srv, name, args)
            d = diff(a, b)
            print(f"--- {name} {args}: {len(d)} diffs, MCP {len(json.dumps(a)):,} chars")
            for x in d[:25]:
                print("   ", x)

asyncio.run(main())
