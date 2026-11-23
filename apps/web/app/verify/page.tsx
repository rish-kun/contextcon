import type { Metadata } from "next";
import Link from "next/link";
import { TextLink } from "@/components/ui";
import { VerifyForm } from "./verify-form";

// The URL carries a one-time token: never send it on in a Referer header.
export const metadata: Metadata = { title: "Confirm your email · DealProof", referrer: "no-referrer" };

/**
 * The link in the sign-up email lands here. Using the token signs the person in, so it
 * happens on a button press rather than on page load: a mail scanner that opens links
 * must not use up the token, or be handed the session.
 */
export default async function VerifyPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const raw = (await searchParams).token;
  const token = typeof raw === "string" ? raw.trim() : "";

  return (
    <div className="flex min-h-dvh flex-col bg-paper px-4 md:px-6 lg:px-8">
      <header className="flex h-14 items-center">
        <Link href="/" className="rounded-xs text-base font-medium text-ink">
          DealProof
        </Link>
      </header>
      <main className="flex flex-1 items-center py-12">
        <div className="mx-auto flex w-full max-w-sm flex-col gap-8">
          <div className="flex flex-col gap-2">
            <h1 className="text-2xl font-medium text-ink">Confirm your email</h1>
            <p className="text-sm text-ink-secondary">
              One step left. Confirming switches your account on and logs you in
            </p>
          </div>
          <VerifyForm token={token} />
          <p className="border-t border-line pt-4 text-dense text-ink-secondary">
            Already confirmed? <TextLink href="/login">Log in</TextLink>
          </p>
        </div>
      </main>
    </div>
  );
}
