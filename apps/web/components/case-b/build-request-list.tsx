"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createRequestList } from "@/lib/api/client";
import { Button } from "@/components/ui/button";

/** Builds the request list and the drafted email from the latest assessment. Sends nothing. */
export function BuildRequestList({ caseId }: { caseId: string }) {
  const router = useRouter();
  const [state, setState] = useState<"idle" | "building" | "failed">("idle");

  const build = async () => {
    setState("building");
    try {
      await createRequestList(caseId);
      router.refresh();
    } catch {
      setState("failed");
    }
  };

  return (
    <div className="flex flex-col items-start gap-1">
      <Button variant="primary" size="sm" onClick={build} disabled={state === "building"}>
        {state === "building" ? "Building the list" : "Build request list"}
      </Button>
      {state === "failed" ? (
        <p role="alert" className="text-xs text-contradicted">
          The list was not built. Try again
        </p>
      ) : (
        <p className="text-xs text-ink-secondary">Drafts the list and the email. Nothing is sent</p>
      )}
    </div>
  );
}
