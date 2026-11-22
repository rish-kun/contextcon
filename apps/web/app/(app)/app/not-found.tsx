import type { Metadata } from "next";
import Link from "next/link";
import { Button, EmptyState, Page, PageHeader } from "@/components/ui";

export const metadata: Metadata = { title: "Page not found" };

/** A missing page inside the app keeps the sidebar and says where to go. */
export default function AppNotFound() {
  return (
    <Page>
      <PageHeader title="Page not found" meta="No page in DealProof has this address" />
      <EmptyState
        size="page"
        title="Nothing is stored here"
        actions={
          <>
            <Button asChild variant="primary" size="sm">
              <Link href="/app">Go to Overview</Link>
            </Button>
            <Button asChild size="sm">
              <Link href="/app/companies">Open Companies</Link>
            </Button>
          </>
        }
      >
        The link may be mistyped, or the record may have been removed when its retention period
        ended. Nothing was changed.
      </EmptyState>
    </Page>
  );
}
