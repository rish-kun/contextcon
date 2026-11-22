import { ClaimsTab } from "@/components/case/claims-tab";

export default async function ClaimsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  return <ClaimsTab initialStatus={status} />;
}
