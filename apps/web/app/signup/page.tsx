import type { Metadata } from "next";
import { SIGNUP_ENABLED } from "@/lib/signup";
import { cookies } from "next/headers";
import Link from "next/link";
import { redirect } from "next/navigation";
import { TextLink } from "@/components/ui";
import { SESSION_COOKIE } from "@/lib/api/proxy-rules";
import { SignupForm } from "./signup-form";

export const metadata: Metadata = { title: "Create your account · DealProof" };

const STATEMENTS = [
  "We look up your organisation in public company data and show you what we found, with the source on every line",
  "You confirm or correct it. Nothing is assumed",
  "Your profile sets defaults. It never changes what the evidence says",
];

/**
 * Sign-up. The same two columns as the login page, so the two read as one pair: the form
 * on the left, a plain statement of what happens next on the right. A visitor who already
 * has a session goes straight to the app.
 */
export default async function SignupPage() {
  if ((await cookies()).has(SESSION_COOKIE)) redirect("/app");

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
              <h1 className="text-2xl font-medium text-ink">Create your account</h1>
              <p className="text-sm text-ink-secondary">
                One workspace for your organisation. You can change all of this later
              </p>
            </div>
            {SIGNUP_ENABLED ? (
              <SignupForm />
            ) : (
              <p className="text-sm text-ink-secondary">
                Sign-up is closed on this deployment. Ask the person who runs DealProof for your
                team for an account. <TextLink href="/login">Go to the login page</TextLink>
              </p>
            )}
            <p className="border-t border-line pt-4 text-dense text-ink-secondary">
              Already have an account? <TextLink href="/login">Log in</TextLink>
              <span className="mt-2 block text-xs text-ink-muted">
                We store your name, your email and a hash of your password
              </span>
            </p>
          </div>
        </main>
      </div>

      <aside className="hidden border-l border-line bg-paper-warm lg:flex lg:flex-col lg:justify-center lg:px-16">
        <div className="flex max-w-md flex-col gap-8">
          <p className="font-serif text-4xl tracking-display text-ink">
            Tell us who you are once. Every screen starts from there
          </p>
          <ul className="flex flex-col text-sm text-ink-secondary">
            {STATEMENTS.map((statement) => (
              <li key={statement} className="border-t border-line-strong py-3 last:border-b">
                {statement}
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
