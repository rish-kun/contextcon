import { ClaimsTab } from "@/components/case/claims-tab";

export default async function ShowcaseClaimsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  // Keyed by the filter, so a link to another status re-seeds the tab.
  return <ClaimsTab key={status ?? "all"} initialStatus={status} />;
}
