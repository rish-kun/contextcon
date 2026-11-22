import type { Metadata } from "next";
import { cookies } from "next/headers";
import { type CaseDetail, getCase } from "@/lib/api/client";
import { CaseProvider } from "@/components/case/case-context";
import { CaseShell } from "@/components/case/case-shell";

/**
 * Fetch the case on the server with the reader's session, so the first paint already has
 * it. If that fails for any reason the provider loads it again in the browser and shows
 * the reason there.
 */
async function loadCase(id: string): Promise<CaseDetail | null> {
  try {
    const cookie = (await cookies()).toString();
    return await getCase(id, { headers: { cookie } });
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const detail = await loadCase(id);
  return { title: detail ? `${detail.case.name} · DealProof` : "Case · DealProof" };
}

export default async function CaseLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const initial = await loadCase(id);

  return (
    <CaseProvider key={id} caseId={id} initial={initial}>
      <CaseShell>{children}</CaseShell>
    </CaseProvider>
  );
}
