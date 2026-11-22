"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";

/** A page outside the app that threw. Same paper and wordmark; one retry. */
export default function RootError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="flex min-h-dvh flex-col bg-paper px-4 md:px-6 lg:px-8">
      <header className="flex h-14 items-center">
        <Link href="/" className="rounded-xs text-base font-medium text-ink">
          DealProof
        </Link>
      </header>
      <main role="alert" className="flex max-w-xl flex-col items-start gap-2 pt-8">
        <h1 className="text-2xl font-medium text-ink">This page did not open</h1>
        <p className="text-dense text-ink-secondary">
          Something went wrong while drawing it. Nothing was changed and nothing was sent.
          {error.digest ? <span className="pl-2 font-mono text-xs text-ink-muted">{error.digest}</span> : null}
        </p>
        <div className="pt-4">
          <Button onClick={reset}>Try again</Button>
        </div>
      </main>
    </div>
  );
}
