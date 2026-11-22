"use client";

import { Download, ExternalLink } from "lucide-react";
import { useState } from "react";
import { getDocumentUrl, type DocumentUrlOut } from "@/lib/api/client";
import { formatTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";

/**
 * Files are never linked directly. Asking for a download fetches a short-lived,
 * case-scoped URL; the link says when it stops working.
 */
export function DocumentDownload({ documentId, filename }: { documentId: string; filename: string }) {
  const [link, setLink] = useState<DocumentUrlOut | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "failed">("idle");

  const request = async () => {
    setState("loading");
    try {
      setLink(await getDocumentUrl(documentId));
      setState("idle");
    } catch {
      setState("failed");
    }
  };

  if (link) {
    return (
      <span className="flex flex-col items-end gap-1">
        <a
          href={link.url}
          target="_blank"
          rel="noreferrer noopener"
          className="inline-flex items-center gap-1 rounded-xs text-dense text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
        >
          <Icon icon={ExternalLink} size={14} />
          Open file
          <span className="sr-only">
            {" "}
            {filename} (opens in a new tab)
          </span>
        </a>
        <span className="font-mono text-2xs text-ink-secondary" role="status">
          link expires {formatTime(link.expires_at) ?? "soon"}
        </span>
      </span>
    );
  }

  return (
    <span className="flex flex-col items-end gap-1">
      <Button
        size="sm"
        onClick={request}
        disabled={state === "loading"}
        aria-label={`Download ${filename}`}
      >
        <Icon icon={Download} />
        {state === "loading" ? "Getting link" : "Download"}
      </Button>
      {state === "failed" ? (
        <span role="alert" className="text-xs text-contradicted">
          Could not get a link. Try again
        </span>
      ) : null}
    </span>
  );
}
