import type { Metadata } from "next";
import { AppShell } from "@/components/app-shell";

export const metadata: Metadata = {
  title: { default: "DealProof", template: "%s · DealProof" },
};

/**
 * Every signed-in route (`/app/**`) renders inside the shell: sidebar, top bar, and a
 * content column padded 32 and capped at 1440 (docs/design/design-direction.md, 11.2).
 */
export default function AppLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <AppShell>{children}</AppShell>;
}
