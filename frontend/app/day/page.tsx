import { redirect } from "next/navigation";

/** Old URL: Day trading is now the Market page. */
export default function DayPage() {
  redirect("/market");
}
