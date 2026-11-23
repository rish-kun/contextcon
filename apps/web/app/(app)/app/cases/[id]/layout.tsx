import type { Metadata } from "next";
import { cookies } from "next/headers";
import { Suspense, cache } from "react";
import { type CaseDetail, getCase } from "@/lib/api/client";
import { CaseProvider } from "@/components/case/case-context";
import { CaseLoading, CaseShell } from "@/components/case/case-shell";

/**
 * Fetch the case on the server with the reader's session, so the first paint already has
 * it. If that fails for any reason the provider loads it again in the browser and shows
 * the reason there. `cache` shares the one fetch between the metadata and the layout.
 */
const loadCase = cache(async (id: string): Promise<CaseDetail | null> => {
  try {
    const cookie = (await cookies()).toString();
    return await getCase(id, { headers: { cookie } });
  } catch {
    return null;
  }
});

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const detail = await loadCase(id);
  // The app layout appends "· DealProof".
  return { title: detail?.case.name ?? "Case" };
}

/**
 * The case read is wrapped in its own Suspense boundary: a layout that reads cookies
 * blocks navigation until it finishes, so without it a click on a case showed nothing
 * until the whole `GET /cases/{id}` came back. Now the skeleton shows at once and the
 * case streams in.
 */
export default function CaseLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  return (
    <Suspense fallback={<CaseLoading />}>
      <LoadedCase params={params}>{children}</LoadedCase>
    </Suspense>
  );
}

async function LoadedCase({
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
