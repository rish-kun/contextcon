import type { Metadata } from "next";
import Link from "next/link";
import { Button, EmptyState, Page, PageHeader } from "@/components/ui";

export const metadata: Metadata = { title: "Signals" };

/** Route stub: the Signals screen is being built in `components/signals`. */
export default function SignalsPage() {
  return (
    <Page>
      <PageHeader title="Signals" />
      <EmptyState
        size="page"
        title="Signals is not built yet"
        actions={
          <Button asChild size="sm">
            <Link href="/app">Go to Overview</Link>
          </Button>
        }
      >
        One dated feed of what the record shows across all cases. This view is on its way; nothing is hidden behind it.
      </EmptyState>
    </Page>
  );
}
