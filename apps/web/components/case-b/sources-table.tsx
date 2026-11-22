"use client";

import { Download } from "lucide-react";
import { useMemo, useState } from "react";
import type { Schemas } from "@/lib/api/client";
import { formatDateTime, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
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
import { SOURCE_CLASS_LABEL, reliabilityOf, type SourceClass } from "./adapt";

type SourceRecord = Schemas["SourceRecordOut"];

const PROVIDER_LABEL: Record<string, string> = {
  crustdata: "Crustdata",
  web: "Web",
  upload: "Upload",
  user: "Typed by a user",
};

const isUrl = (value: string) => /^https?:\/\//i.test(value);

function FilterChip({
  pressed,
  onClick,
  children,
  count,
}: {
  pressed: boolean;
  onClick: () => void;
  children: React.ReactNode;
  count: number;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "inline-flex h-8 items-center gap-2 rounded-md border px-3 text-xs transition-[background-color,border-color,color]",
        pressed
          ? "border-accent-line bg-accent-tint text-accent"
          : "border-line bg-surface text-ink-secondary hover:bg-surface-raised hover:text-ink",
      )}
    >
      {children}
      <span className="font-mono text-2xs">{count}</span>
    </button>
  );
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
}: {
  sources: SourceRecord[];
  /** Source id → where its facts appear: "Claim 1", "Fit criteria". */
  uses: Record<string, string[]>;
  /** File name stem for the exported record. */
  exportName: string;
}) {
  const [filter, setFilter] = useState<SourceClass | null>(null);

  const classes = useMemo(() => {
    const counts = new Map<SourceClass, number>();
    for (const source of sources) {
      counts.set(source.source_class, (counts.get(source.source_class) ?? 0) + 1);
    }
    return [...counts].sort((a, b) =>
      SOURCE_CLASS_LABEL[a[0]].localeCompare(SOURCE_CLASS_LABEL[b[0]]),
    );
  }, [sources]);

  const rows = useMemo(
    () =>
      sources
        .filter((source) => filter === null || source.source_class === filter)
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
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter by source class">
          <FilterChip pressed={filter === null} onClick={() => setFilter(null)} count={sources.length}>
            All
          </FilterChip>
          {classes.map(([sourceClass, count]) => (
            <FilterChip
              key={sourceClass}
              pressed={filter === sourceClass}
              onClick={() => setFilter(filter === sourceClass ? null : sourceClass)}
              count={count}
            >
              <SourceClassGlyph reliability={reliabilityOf(sourceClass)} />
              {SOURCE_CLASS_LABEL[sourceClass]}
            </FilterChip>
          ))}
        </div>
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
                    <SourceClassGlyph
                      reliability={reliabilityOf(source.source_class)}
                      className="text-ink-muted"
                    />
                    {SOURCE_CLASS_LABEL[source.source_class]}
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
      <p className="text-xs text-ink-secondary" aria-live="polite">
        {filter === null
          ? `${plural(sources.length, "source")}, oldest retrieval first`
          : `${rows.length} of ${plural(sources.length, "source")} · ${SOURCE_CLASS_LABEL[filter]}`}
      </p>
    </div>
  );
}
