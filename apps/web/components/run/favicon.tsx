"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { SourceClassGlyph } from "@/components/dealproof/glyphs";
import { reliabilityOf } from "./wording";

/** Names the favicon route refuses outright; asking would only cost a request. */
const NEVER_PUBLIC = /\.(example|test|invalid|localhost|local|internal)$/;

/**
 * A site's favicon, 16px, from the same-origin route `/api/favicon`. The browser never
 * asks a third-party icon service. When there is no icon, or for a Crustdata record, the
 * tile shows the source-class glyph.
 */
export function Favicon({
  domain,
  sourceClass,
  muted = false,
  className,
}: {
  /** Null for anything that is not a web page. */
  domain: string | null;
  sourceClass: string;
  muted?: boolean;
  className?: string;
}) {
  const [missing, setMissing] = useState<string | null>(null);
  const askable = domain !== null && !NEVER_PUBLIC.test(domain) && missing !== domain;

  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex size-4 shrink-0 items-center justify-center overflow-hidden rounded-xs",
        !askable && "bg-surface-raised text-ink-secondary",
        muted && "opacity-60",
        className,
      )}
    >
      {askable ? (
        // A plain <img>: the route already sizes, caches and limits the icon.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={`/api/favicon?domain=${encodeURIComponent(domain)}`}
          alt=""
          width={16}
          height={16}
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setMissing(domain)}
          className="size-4"
        />
      ) : (
        <SourceClassGlyph reliability={reliabilityOf(sourceClass)} size={12} />
      )}
    </span>
  );
}
