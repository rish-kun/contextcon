import { formatDateTime, plural } from "@/lib/format";
import type { AssessmentDiff, AssessmentVersionMeta } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChangeList } from "./change-list";

/**
 * On the Assessment tab the rail and the diff are drawn as one joined view,
 * `ChangeTimeline` in components/explainers, which puts the cause between two versions
 * under the version it produced. `VersionRail` and `VersionDiff` stay for places that need
 * one without the other; both draw their rows with `ChangeList`, so a change reads the
 * same way everywhere.
 */

/**
 * The version rail: dated nodes, oldest first. The current version is a filled node and
 * says "current" in words. Pass `onOpen` to let a reader open an earlier version read-only.
 */
export function VersionRail({
  versions,
  current,
  viewing,
  onOpen,
  className,
}: {
  versions: AssessmentVersionMeta[];
  current: number;
  /** The version open on the page, when it is not the current one. */
  viewing?: number;
  onOpen?: (version: number) => void;
  className?: string;
}) {
  return (
    <ol className={cn("flex flex-col", className)} aria-label="Assessment history">
      {versions.map((item, index) => {
        const isCurrent = item.version === current;
        const last = index === versions.length - 1;
        return (
          <li key={item.version} className="grid grid-cols-[1rem_minmax(0,1fr)] gap-x-3">
            <span className="flex flex-col items-center" aria-hidden>
              <span
                className={cn(
                  "mt-1 size-3 shrink-0 rounded-full border-2 border-ink",
                  isCurrent ? "bg-ink" : "bg-surface",
                )}
              />
              {last ? null : <span className="w-px flex-1 bg-line-strong" />}
            </span>
            <div className={cn("flex flex-wrap items-center gap-x-2 gap-y-1", last ? "pb-0" : "pb-4")}>
              <span className={cn("font-mono text-xs text-ink", isCurrent && "font-medium")}>
                v{item.version}
              </span>
              <span className="font-mono text-xs text-ink-secondary">
                {formatDateTime(item.created_at)}
              </span>
              <span className="text-dense text-ink-secondary">· {item.trigger}</span>
              {isCurrent ? (
                <Badge variant="mono">current</Badge>
              ) : null}
              {item.version === viewing && !isCurrent ? (
                <Badge variant="accent" className="font-mono text-2xs">
                  reading
                </Badge>
              ) : onOpen && item.version !== (viewing ?? current) ? (
                <Button
                  variant="link"
                  size="inline"
                  className="text-xs font-normal"
                  onClick={() => onOpen(item.version)}
                >
                  Open version {item.version}
                </Button>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Shown above a case that is open at an earlier version. */
export function ReadingOldVersionBanner({
  reading,
  current,
  className,
  children,
}: {
  reading: number;
  current: number;
  className?: string;
  /** A way back, for example a link that opens the current version. */
  children?: React.ReactNode;
}) {
  return (
    <p
      role="status"
      className={cn(
        "rounded-md border border-accent-line bg-accent-tint px-3 py-2 text-dense text-accent",
        className,
      )}
    >
      You are reading version {reading}. Version {current} is current
      {children ? <> · {children}</> : null}
    </p>
  );
}

/**
 * What changed between two assessment versions, most decision-relevant first, with
 * repeats of one cause folded into a single row (see `ChangeList`). A downgrade looks
 * exactly like an upgrade: no celebration and no softening.
 */
export function VersionDiff({
  diff,
  highlight = false,
  header = true,
  onShowUnchanged,
  className,
}: {
  diff: AssessmentDiff;
  /** One-time accent highlight on each changed row, for a version that has just arrived. */
  highlight?: boolean;
  /** Off where a heading above already says which versions these are. */
  header?: boolean;
  onShowUnchanged?: () => void;
  className?: string;
}) {
  return (
    <section
      aria-label={`What changed in version ${diff.to_version}`}
      className={cn("overflow-hidden rounded-lg border border-line bg-surface", className)}
    >
      {header ? (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
          <h3 className="text-sm font-medium text-ink">What changed in v{diff.to_version}</h3>
          <p className="font-mono text-2xs text-ink-secondary">
            v{diff.from_version} → v{diff.to_version}
          </p>
        </header>
      ) : null}
      {diff.changes.length === 0 ? (
        <p className="px-4 py-3 text-dense text-ink-secondary">Nothing changed</p>
      ) : (
        <ChangeList changes={diff.changes} highlight={highlight} />
      )}
      <footer className="flex flex-wrap items-center gap-3 border-t border-line bg-surface-raised px-4 py-2 text-xs text-ink-secondary">
        <span>{plural(diff.unchanged_claims, "claim")} unchanged</span>
        {onShowUnchanged ? (
          <Button variant="link" size="inline" className="text-xs font-normal" onClick={onShowUnchanged}>
            Show
          </Button>
        ) : null}
      </footer>
    </section>
  );
}
