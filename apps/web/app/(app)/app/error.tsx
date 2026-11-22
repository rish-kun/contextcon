"use client";

import { ErrorState, Page, PageHeader } from "@/components/ui";

/** A page inside the app that threw while rendering. The sidebar stays; one retry. */
export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <Page>
      <PageHeader title="This page did not open" />
      <ErrorState
        size="page"
        what="This page"
        reason={`Something went wrong while drawing it. Nothing was changed and nothing was sent.${error.digest ? ` Reference ${error.digest}` : ""}`}
        onRetry={reset}
      />
    </Page>
  );
}
