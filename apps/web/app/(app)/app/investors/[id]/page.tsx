import type { Metadata } from "next";
import { SearchView } from "@/components/investors";
import { parseFixtureState } from "@/components/investors/fixture-states";

export const metadata: Metadata = { title: "Investor shortlist · DealProof" };

export default async function InvestorSearchPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const state = typeof query.state === "string" ? query.state : undefined;

  return (
    <SearchView
      // A new key per search, so one search's run state never carries into the next.
      key={id}
      id={id}
      fresh={query.new === "1"}
      fixtureState={parseFixtureState(state)}
    />
  );
}
