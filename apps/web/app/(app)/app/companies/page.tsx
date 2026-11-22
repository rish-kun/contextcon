import type { Metadata } from "next";
import Link from "next/link";
import { Button, EmptyState, Page, PageHeader } from "@/components/ui";

export const metadata: Metadata = { title: "Companies" };

/** Route stub: the Companies screen is being built in `components/companies`. */
export default function CompaniesPage() {
  return (
    <Page>
      <PageHeader title="Companies" />
      <EmptyState
        size="page"
        title="Companies is not built yet"
        actions={
          <Button asChild size="sm">
            <Link href="/app">Go to Overview</Link>
          </Button>
        }
      >
        Every company DealProof holds a record for, from cases and shortlists. This view is on its way; nothing is hidden behind it.
      </EmptyState>
    </Page>
  );
}
