"use client";

import { Download } from "lucide-react";
import { useMemo } from "react";
import type { Schemas } from "@/lib/api/client";
import { formatDateTime, plural } from "@/lib/format";
import { RELIABILITY_LABEL, RELIABILITY_NOTE } from "@/lib/labels";
import { SourceClassGlyph } from "@/components/dealproof/glyphs";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { SourceClass } from "./adapt";

type SourceRecord = Schemas["SourceRecordOut"];

const PROVIDER_LABEL: Record<string, string> = {
  crustdata: "Crustdata",
  web: "Web",
  upload: "Upload",
  user: "Typed by a user",
};

const isUrl = (value: string) => /^https?:\/\//i.test(value);

/** A source class, optionally narrowed to the sources behind one cell of the coverage map. */
export interface SourcesFilter {
  sourceClass: SourceClass;
  /** The kind of claim the cell belongs to, for the label. Null for a whole class. */
  category: string | null;
  /** Null keeps every source of the class. */
  sourceIds: string[] | null;
}

/**
 * The full source record: what was read, from where, when, and what it was used for.
 * A source that was fetched but not attached to this company stays in the list and says
 * why, so the record shows everything that was looked at.
 */
export function SourcesTable({
  sources,
  uses,
  exportName,
  filter = null,
  onClearFilter,
}: {
  sources: SourceRecord[];
  /** Source id → where its facts appear: "Claim 1", "Fit criteria". */
  uses: Record<string, string[]>;
  /** File name stem for the exported record. */
  exportName: string;
  /** Set by the coverage map above the table, which is the table's filter. */
  filter?: SourcesFilter | null;
  onClearFilter?: () => void;
}) {
  const rows = useMemo(
    () =>
      sources
        .filter(
          (source) =>
            !filter ||
            (source.source_class === filter.sourceClass &&
              (filter.sourceIds === null || filter.sourceIds.includes(source.source_id))),
        )
        .sort((a, b) => a.retrieved_at.localeCompare(b.retrieved_at)),
    [sources, filter],
  );

  const exportRecord = () => {
    const record = sources.map((source) => ({ ...source, used_for: uses[source.source_id] ?? [] }));
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(record, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `${exportName}-sources.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-dense text-ink-secondary" aria-live="polite">
          {filter ? (
            <>
              <span className="inline-flex items-center gap-2 text-ink">
                <SourceClassGlyph reliability={filter.sourceClass} className="text-ink-muted" />
                {filter.category ? `${filter.category} · ` : null}
                {RELIABILITY_LABEL[filter.sourceClass]}
              </span>
              <span className="font-mono text-xs">
                {rows.length} of {plural(sources.length, "source")}
              </span>
              {onClearFilter ? (
                <Button variant="link" size="inline" className="text-dense font-normal" onClick={onClearFilter}>
                  Show all sources
                </Button>
              ) : null}
            </>
          ) : (
            <span className="font-mono text-xs">{plural(sources.length, "source")}</span>
          )}
        </p>
        <Button size="sm" onClick={exportRecord}>
          <Icon icon={Download} />
          Export source record
        </Button>
      </div>

      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Source</TableHead>
            <TableHead>Reliability class</TableHead>
            <TableHead>Provider</TableHead>
            <TableHead>URL or request</TableHead>
            <TableHead>Retrieved</TableHead>
            <TableHead>Used for</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((source) => {
            const usedFor = uses[source.source_id] ?? [];
            return (
              <TableRow key={source.source_id} className="align-top">
                <TableCell className="align-top">
                  <span className="flex flex-col gap-1">
                    <span className="text-ink">{source.label}</span>
                    {source.title || source.publisher ? (
                      <span className="text-xs text-ink-secondary">
                        {[source.title, source.publisher].filter(Boolean).join(" · ")}
                      </span>
                    ) : null}
                  </span>
                </TableCell>
                <TableCell className="align-top whitespace-nowrap">
                  <span className="inline-flex items-center gap-2 text-ink-secondary">
                    <SourceClassGlyph reliability={source.source_class} className="text-ink-muted" />
                    {RELIABILITY_LABEL[source.source_class]}
                  </span>
                </TableCell>
                <TableCell className="align-top whitespace-nowrap text-ink-secondary">
                  {PROVIDER_LABEL[source.provider] ?? source.provider}
                </TableCell>
                <TableCell className="max-w-80 align-top">
                  <span className="flex flex-col gap-1 font-mono text-xs break-all">
                    {isUrl(source.url_or_endpoint) ? (
                      <a
                        href={source.url_or_endpoint}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="rounded-xs text-accent underline underline-offset-2 transition-colors hover:text-accent-hover"
                      >
                        {source.url_or_endpoint}
                        <span className="sr-only"> (opens in a new tab)</span>
                      </a>
                    ) : (
                      <span className="text-ink">{source.url_or_endpoint}</span>
                    )}
                    {source.request ? (
                      <span className="text-2xs text-ink-secondary">
                        {JSON.stringify(source.request)}
                      </span>
                    ) : null}
                  </span>
                </TableCell>
                <TableCell className="align-top font-mono text-xs whitespace-nowrap text-ink-secondary">
                  {formatDateTime(source.retrieved_at) ?? "time not recorded"}
                </TableCell>
                <TableCell className="align-top">
                  {source.attached ? (
                    usedFor.length ? (
                      <span className="text-ink">{usedFor.join(", ")}</span>
                    ) : (
                      <span className="text-ink-secondary">Read, no fact taken from it</span>
                    )
                  ) : (
                    <span className="flex flex-col gap-1">
                      <span className="text-ink">Not attached to this company</span>
                      <span className="text-xs text-ink-secondary">
                        {source.unattached_reason ?? "No reason recorded"}
                      </span>
                    </span>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      {rows.length === 0 ? (
        <p className="text-dense text-ink-secondary">
          No source on the record matches. The facts in that cell came from a source that is
          not listed here
        </p>
      ) : null}
      <p className="text-xs text-ink-secondary">
        Oldest retrieval first
        {filter ? `. ${RELIABILITY_LABEL[filter.sourceClass]}: ${RELIABILITY_NOTE[filter.sourceClass]}` : null}
      </p>
    </div>
  );
}
