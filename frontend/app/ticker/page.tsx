import { redirect } from "next/navigation";

/** Old URL: the bets list is now Flow check (/bets); single tickers stay at /ticker/SYMBOL. */
export default function TickerIndex() {
  redirect("/bets");
}
