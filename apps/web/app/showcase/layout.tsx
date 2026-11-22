import type { Metadata } from "next";
import { ShowcaseBar, ShowcaseMode } from "@/components/showcase/showcase-mode";

export const metadata: Metadata = {
  title: { default: "Showcase", template: "%s · DealProof showcase" },
};

/**
 * The public, read-only showcase: one real discovery run, one real verified case and one
 * real investor search, served by the API's `/public/showcase/*` routes from records
 * flagged `is_showcase`. No session; nothing on these pages changes anything.
 */
export default function ShowcaseLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <ShowcaseMode>
      <div className="min-h-dvh bg-canvas">
        <ShowcaseBar />
        <main className="mx-auto w-full max-w-[1440px] px-4 py-6 md:px-8 md:py-8">{children}</main>
      </div>
    </ShowcaseMode>
  );
}
