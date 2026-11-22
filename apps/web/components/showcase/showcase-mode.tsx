"use client";

import Link from "next/link";
import { useEffect } from "react";
import { setPublicShowcaseMode } from "@/lib/api/client";
import { Button } from "@/components/ui/button";

/**
 * Switches the browser's API client to the public read-only showcase routes for as long
 * as a `/showcase/**` page is mounted. Set during render, so the first client fetch of
 * any child already goes to `/public/showcase/*`.
 */
export function ShowcaseMode({ children }: { children: React.ReactNode }) {
  if (typeof window !== "undefined") setPublicShowcaseMode(true);
  useEffect(() => {
    setPublicShowcaseMode(true);
    return () => setPublicShowcaseMode(false);
  }, []);
  return <>{children}</>;
}

const NAV = [
  { href: "/showcase/discovery", label: "Discovery" },
  { href: "/showcase/case", label: "Case" },
  { href: "/showcase/investors", label: "Investors" },
];

/** The showcase's own top bar: what this is, where to go, and the way in. */
export function ShowcaseBar() {
  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 md:px-8">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
          <Link href="/" className="text-sm font-medium text-ink">
            DealProof
          </Link>
          <span className="font-mono text-xs text-ink-secondary">
            Real run · read-only · public information only
          </span>
          <nav aria-label="Showcase" className="flex items-center gap-4 text-dense">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="rounded-xs text-ink-secondary underline-offset-2 transition-colors hover:text-ink hover:underline"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
        <Button asChild variant="primary" size="sm">
          <Link href="/login">Log in to work on your own cases</Link>
        </Button>
      </div>
    </header>
  );
}
