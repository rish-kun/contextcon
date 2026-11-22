import type { Metadata } from "next";
import { getShowcase } from "@/lib/api/client";
import { SearchView } from "@/components/investors";

export const metadata: Metadata = { title: "Investors" };

/** The showcase's real investor search, read-only (the client reads the public route). */
export default async function ShowcaseInvestorsPage() {
  const index = await getShowcase().catch(() => null);
  const id = index?.investor_search_id ?? "showcase";
  return <SearchView key={id} id={id} fresh={false} fixtureState={undefined} />;
}
