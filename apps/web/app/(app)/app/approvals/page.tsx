import type { Metadata } from "next";
import Link from "next/link";
import { Button, EmptyState, Page, PageHeader } from "@/components/ui";

export const metadata: Metadata = { title: "Approvals" };

/** Route stub: the Approvals screen is being built in `components/approvals`. */
export default function ApprovalsPage() {
  return (
    <Page>
      <PageHeader title="Approvals" />
      <EmptyState
        size="page"
        title="Approvals is not built yet"
        actions={
          <Button asChild size="sm">
            <Link href="/app">Go to Overview</Link>
          </Button>
        }
      >
        Every seller request across cases, by state. This view is on its way; nothing is hidden behind it.
      </EmptyState>
    </Page>
  );
}
