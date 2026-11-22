import { OverviewTab } from "@/components/case/overview-tab";

export default async function CaseOverviewPage({
  searchParams,
}: {
  searchParams: Promise<{ print?: string }>;
}) {
  const { print } = await searchParams;
  return <OverviewTab autoPrint={print === "1"} />;
}
