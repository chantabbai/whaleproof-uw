import { redirect } from "next/navigation";

/** Old URL: now Flow check (/bets). */
export default function AlertsPage() {
  redirect("/bets#bets");
}
