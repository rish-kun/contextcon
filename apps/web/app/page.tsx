import Link from "next/link";

// Placeholder only. Product pages come at a later checkpoint; the design system is at /design.
export default function Home() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-(--layout-prose-max) flex-col justify-center gap-4 px-4 py-16 md:px-6">
      <p className="text-base font-medium text-ink">DealProof</p>
      <h1 className="font-serif text-3xl text-ink">
        Discover opportunities. Verify the evidence. Evaluate with confidence
      </h1>
      <p className="text-base text-ink-secondary">
        The product pages are not built yet. The components they will be made
        from are in the gallery.
      </p>
      <p>
        <Link
          href="/design"
          className="rounded-xs text-sm text-accent underline underline-offset-4 transition-colors hover:text-accent-hover"
        >
          Open the component gallery
        </Link>
      </p>
    </main>
  );
}
