import type { Metadata } from "next";
import Link from "next/link";
import { Button, EmptyState, Page, PageHeader } from "@/components/ui";

export const metadata: Metadata = { title: "Compare" };

/** Route stub: the Compare screen is being built in `components/compare`. */
export default function ComparePage() {
  return (
    <Page>
      <PageHeader title="Compare" />
      <EmptyState
        size="page"
        title="Compare is not built yet"
        actions={
          <Button asChild size="sm">
            <Link href="/app">Go to Overview</Link>
          </Button>
        }
      >
        Two to four cases side by side on what decides a screening. This view is on its way; nothing is hidden behind it.
      </EmptyState>
    </Page>
  );
}
