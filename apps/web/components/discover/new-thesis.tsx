"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { RunOut, ThesisOut } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { CriteriaEditor } from "./criteria-editor";
import { DiscoverHeader, DiscoverPage } from "./step-header";
import { ThesisForm } from "./thesis-form";

/**
 * New thesis: write it, review the criteria DealProof read from it, then run the search.
 * The page moves to the thesis itself once the run has started.
 */
export function NewThesis() {
  const router = useRouter();
  const [thesis, setThesis] = useState<ThesisOut | null>(null);
  const [draft, setDraft] = useState("");

  function started(_run: RunOut, saved: ThesisOut) {
    router.push(`/app/discover/${encodeURIComponent(saved.id)}?live=1`);
  }

  return (
    <DiscoverPage>
      <DiscoverHeader step={thesis ? 2 : 1}>
        <p className="max-w-3xl text-sm text-ink-secondary">
          Describe the companies you want. DealProof turns that into criteria, searches live
          company data, and explains why each company is on the shortlist.
        </p>
      </DiscoverHeader>

      {thesis ? (
        <>
          <section
            aria-label="Thesis"
            className="flex max-w-3xl flex-col gap-2 rounded-lg border border-line bg-surface p-4 sm:flex-row sm:items-start sm:justify-between sm:gap-6"
          >
            <div className="flex min-w-0 flex-col gap-1">
              <h2 className="text-xs text-ink-muted">Thesis</h2>
              <p className="text-sm text-ink">{thesis.text}</p>
            </div>
            <Button
              variant="quiet"
              size="sm"
              className="-ml-3 self-start sm:-mr-2 sm:ml-0"
              onClick={() => {
                setDraft(thesis.text);
                setThesis(null);
              }}
            >
              Edit thesis
            </Button>
          </section>
          <CriteriaEditor key={thesis.id + thesis.text} thesis={thesis} onStarted={started} />
        </>
      ) : (
        <ThesisForm initialText={draft} onExtracted={setThesis} />
      )}
    </DiscoverPage>
  );
}
