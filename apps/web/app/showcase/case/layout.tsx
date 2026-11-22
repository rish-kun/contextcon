import type { Metadata } from "next";
import { cache } from "react";
import { type CaseDetail, getShowcaseCase } from "@/lib/api/client";
import { CaseProvider } from "@/components/case/case-context";
import { CaseShell } from "@/components/case/case-shell";

/** The flagged showcase case, fetched on the server without a session. */
const loadCase = cache(async (): Promise<CaseDetail | null> => {
  try {
    return await getShowcaseCase();
  } catch {
    return null;
  }
});

export async function generateMetadata(): Promise<Metadata> {
  const detail = await loadCase();
  return { title: detail?.case.name ?? "Case" };
}

/**
 * The real case screens, read-only: the same tabs as `/app/cases/{id}`, with no verify,
 * claim, upload, identity, approval or send actions. If the server fetch fails, the
 * provider loads the case in the browser (the client maps it to the public route).
 */
export default async function ShowcaseCaseLayout({ children }: { children: React.ReactNode }) {
  const initial = await loadCase();
  return (
    <CaseProvider
      caseId={initial?.case.id ?? "showcase"}
      initial={initial}
      readOnly
      basePath="/showcase/case"
    >
      <CaseShell>{children}</CaseShell>
    </CaseProvider>
  );
}
