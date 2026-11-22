import type { Metadata } from "next";
import { SIGNUP_ENABLED } from "@/lib/signup";
import Link from "next/link";
import { Suspense } from "react";
import { buttonVariants } from "@/components/ui/button";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Log in · DealProof" };

/**
 * Sign-in. The form sits on the left at desktop widths; the right half states, in the
 * product's own words, what is behind it. New visitors are pointed at sign-up.
 */
export default function LoginPage() {
  return (
    <div className="grid min-h-dvh bg-paper lg:grid-cols-2">
      <div className="flex flex-col px-4 md:px-6 lg:px-8">
        <header className="flex h-14 items-center">
          <Link href="/" className="rounded-xs text-base font-medium text-ink">
            DealProof
          </Link>
        </header>
        <main className="flex flex-1 items-center py-12">
          <div className="mx-auto flex w-full max-w-sm flex-col gap-8">
            <div className="flex flex-col gap-2">
              <h1 className="text-2xl font-medium text-ink">Log in</h1>
              <p className="text-sm text-ink-secondary">
                Use your work email and password
              </p>
            </div>
            {/* The form reads the `next` query parameter, which needs a Suspense boundary. */}
            <Suspense fallback={<div className="h-56" aria-hidden />}>
              <LoginForm />
            </Suspense>
            {SIGNUP_ENABLED && (
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
                <p className="text-dense text-ink-secondary">New to DealProof?</p>
                <Link href="/signup" className={buttonVariants({ variant: "secondary", size: "sm" })}>
                  Sign up
                </Link>
              </div>
            )}
          </div>
        </main>
      </div>

      <aside className="hidden border-l border-line bg-paper-warm lg:flex lg:flex-col lg:justify-center lg:px-16">
        <div className="flex max-w-md flex-col gap-8">
          <p className="font-serif text-4xl tracking-display text-ink">
            Know what is proven before the second meeting
          </p>
          <ul className="flex flex-col text-sm text-ink-secondary">
            <li className="border-t border-line-strong py-3">
              Every fact ends in its source and the date it was true
            </li>
            <li className="border-t border-line-strong py-3">
              Cannot verify is a finished answer, with the document that would settle it
            </li>
            <li className="border-y border-line-strong py-3">
              Your signed-in name is recorded on every request you approve
            </li>
          </ul>
        </div>
      </aside>
    </div>
  );
}
