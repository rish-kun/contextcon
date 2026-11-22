"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useCase, useCaseDetail } from "./case-context";
import { Memo } from "./memo";

/**
 * The Overview tab is the memo. `autoPrint` is set when the reader chose "Print memo"
 * from another tab: the print dialog opens once the fonts are in, and the flag leaves
 * the address so a reload does not print again.
 */
export function OverviewTab({ autoPrint = false }: { autoPrint?: boolean }) {
  const detail = useCaseDetail();
  const { basePath } = useCase();
  const router = useRouter();

  useEffect(() => {
    if (!autoPrint) return;
    let cancelled = false;
    void document.fonts.ready.then(() => {
      if (cancelled) return;
      window.print();
      router.replace(basePath);
    });
    return () => {
      cancelled = true;
    };
  }, [autoPrint, basePath, router]);

  return <Memo detail={detail} />;
}
