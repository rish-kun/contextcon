import type { Metadata } from "next";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Page not found · DealProof" };

/** Outside the app: the same paper, the wordmark, and the two places a reader can go. */
export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col bg-paper px-4 md:px-6 lg:px-8">
      <header className="flex h-14 items-center">
        <Link href="/" className="rounded-xs text-base font-medium text-ink">
          DealProof
        </Link>
      </header>
      <main className="flex max-w-xl flex-col items-start gap-2 pt-8">
        <p className="font-mono text-xs text-ink-muted">404</p>
        <h1 className="text-2xl font-medium text-ink">Page not found</h1>
        <p className="text-dense text-ink-secondary">
          No page has this address. The link may be mistyped, or the record may have been removed
          when its retention period ended.
        </p>
        <div className="flex flex-wrap gap-2 pt-4">
          <Button asChild variant="primary">
            <Link href="/app">Open the app</Link>
          </Button>
          <Button asChild>
            <Link href="/">Home page</Link>
          </Button>
        </div>
      </main>
    </div>
  );
}
