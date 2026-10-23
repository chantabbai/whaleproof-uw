import AutoRefresh from "@/components/AutoRefresh";
import BetsTable, { type BetsData } from "@/components/BetsTable";
import LookupForm from "@/components/LookupForm";
import { Block, Hero, More, MoreList, Tile, Tiles } from "@/components/v2/ui";
import { get } from "@/lib/api";
import { etTime, shortDate } from "@/lib/format";

export default async function AllBets() {
  const a = await get<BetsData>("/api/desk/alerts");
  const signals = a ? a.bets.filter((b) => b.verdict === "signal").length : 0;
  const bull = a ? a.bets.filter((b) => b.direction > 0).length : 0;
  const todays: Record<string, number> = {};
  for (const b of a?.bets ?? []) todays[b.ticker] = (todays[b.ticker] ?? 0) + 1;
  return (
    <div>
      <AutoRefresh seconds={60} />
      <Hero name="Flow check" eyebrow={a?.day ? `${longDay(a.day)}${a.forming ? ", still forming until 4:15 PM ET" : ""}` : undefined}
        title={a ? <>{a.bets.length.toLocaleString("en-US")} one-way bets. <span className="mark">{signals}</span> made the cut.</> : "Flow check"}
        lead="Every one-way bet in the day's Unusual Whales flow: what our filter made of it, and how similar bets did before. Click a ticker for its full page." />

      <div className="mt-14">
        <Block wave id="check" title="Check a bet you saw on Unusual Whales" sub="Type it the way UW shows it. We work out how far out of the money it is and the days left from the stock's last close, then show how earlier bets like it did.">
          <div className="mt-4"><LookupForm todays={todays} /></div>
        </Block>
      </div>

      {a && <div className="mt-14"><Tiles cols={3}>
        <Tile accent="sea" k="Cut by our filter" v={(a.bets.length - signals).toLocaleString("en-US")} sub={`each row below says why${a.as_of ? `, as of ${etTime(a.as_of)}${a.forming ? " (still forming)" : ""}` : ""}`} />
        <Tile accent="brass" k="Bullish · bearish" v={`${bull.toLocaleString("en-US")} · ${(a.bets.length - bull).toLocaleString("en-US")}`} sub={`one-way bets by direction${a.day ? ` on ${shortDate(a.day)}` : ""}`} />
        <Tile accent="amber" k="Earlier bets to compare with" v={a.history_size ? a.history_size.toLocaleString("en-US") : "–"} sub="five-day results, point in time" />
      </Tiles></div>}

      <div className="mt-14">
        <Block wave id="bets" title="Every bet and our verdict" sub="One row per ticker and direction (the biggest alert): what our filter made of it, and how similar bets did before. History only, not a signal; most kinds average out to about zero.">
          {!a ? <p className="text-sm text-muted" role="status">The WhaleProof API is not answering. Start it with <code>scripts/desk.sh up</code>, then reload.</p> : <BetsTable data={a} />}
        </Block>
      </div>

      <div className="mt-14"><MoreList>
        <More title="How the history works">
          <p className="max-w-[68ch] text-sm text-muted">
            For each earlier bet we take the stock over the same five-day hold our signals use (buy at the next open, sell at the fifth
            close, minus costs), compare it with the S&amp;P 500, and flip the sign for bearish bets. Only bets whose five days were already
            over count. A match needs the same direction, call or put, and kind of bet. Then we match on size, days to expiry, distance out of
            the money, sweep and sector, and loosen those one at a time if fewer than 30 match. Check that the periods agree.
            Not financial advice.
          </p>
        </More>
      </MoreList></div>
    </div>
  );
}

function longDay(iso: string) {
  return new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
}
