"use client";

import { ListChecks } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { listRuns, type RunQueueItemOut, type RunQueueOut } from "@/lib/api/client";
import { formatCredits, formatDuration } from "@/lib/format";
import { RUN_KIND_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/ui";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

/** Poll fast while something is working, slowly otherwise. */
const ACTIVE_POLL_MS = 5_000;
const IDLE_POLL_MS = 30_000;
const RECENT_LIMIT = 8;

const OWNER_PATH: Record<NonNullable<RunQueueItemOut["owner"]>["kind"], string> = {
  thesis: "/app/discover",
  case: "/app/cases",
  investor_search: "/app/investors",
};

function ownerHref(item: RunQueueItemOut): string | null {
  return item.owner ? `${OWNER_PATH[item.owner.kind]}/${encodeURIComponent(item.owner.id)}` : null;
}

const isActive = (item: RunQueueItemOut) => item.state === "pending" || item.state === "running";

function elapsedSeconds(item: RunQueueItemOut, now: number): number {
  const start = Date.parse(item.started_at ?? item.created_at);
  const end = item.finished_at ? Date.parse(item.finished_at) : now;
  return Number.isFinite(start) && Number.isFinite(end) ? Math.max(0, (end - start) / 1000) : 0;
}

function credits(item: RunQueueItemOut): string {
  const { settled, reserved, unknown_cost_calls } = item.credits;
  let text = `${formatCredits(settled)} cr`;
  if (reserved > 0) text += ` + ${formatCredits(reserved)} held`;
  if (unknown_cost_calls > 0) text += " + unknown";
  return text;
}

function JobRow({ item, now }: { item: RunQueueItemOut; now: number }) {
  const href = ownerHref(item);
  const active = isActive(item);
  const status = active
    ? (item.current_step ?? (item.state === "pending" ? "Queued" : "Working"))
    : item.state === "failed"
      ? "Stopped"
      : "Finished";
  const body = (
    <>
      <span className="flex min-w-0 items-baseline justify-between gap-3">
        <span className="truncate text-sm text-ink">
          {item.owner?.label || RUN_KIND_LABEL[item.kind]}
        </span>
        <span className="shrink-0 font-mono text-2xs text-ink-muted">
          {item.steps_done}/{item.steps_total}
        </span>
      </span>
      <span className="flex min-w-0 items-baseline justify-between gap-3 text-2xs text-ink-muted">
        <span className={cn("truncate", item.state === "failed" && "text-contradicted")}>
          {RUN_KIND_LABEL[item.kind]} · {status}
        </span>
        <span className="shrink-0 font-mono">
          {formatDuration(elapsedSeconds(item, now))} · {credits(item)}
        </span>
      </span>
    </>
  );
  const className = "flex flex-col gap-0.5 rounded-md px-2 py-1.5";
  return (
    <li>
      {href ? (
        <Link href={href} className={cn(className, "transition-colors hover:bg-surface-raised")}>
          {body}
        </Link>
      ) : (
        <div className={className}>{body}</div>
      )}
    </li>
  );
}

/**
 * The workspace's jobs, in the top bar: a count of runs queued or working, and a list of
 * them and the latest finished ones. Runs live on the server, so a reload or another tab
 * sees the same jobs; each row links to the page that follows it.
 */
export function JobsIndicator() {
  const [active, setActive] = useState<RunQueueOut | null>(null);
  const [recent, setRecent] = useState<RunQueueItemOut[] | null>(null);
  const [open, setOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const count = active?.active_count ?? 0;
  const countRef = useRef(count);
  useEffect(() => {
    countRef.current = count;
  }, [count]);

  const loadRecent = useCallback(async () => {
    try {
      setRecent((await listRuns("recent", RECENT_LIMIT)).items);
    } catch {
      /* the active list still shows; the next open tries again */
    }
  }, []);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      if (stopped) return;
      if (typeof document === "undefined" || !document.hidden) {
        try {
          const next = await listRuns("active");
          if (stopped) return;
          // A job just finished: refresh the recent list too, if it is showing.
          if (next.active_count < countRef.current && open) void loadRecent();
          setActive(next);
        } catch {
          /* signed out or offline: keep the last answer and try again later */
        }
      }
      if (!stopped) timer = setTimeout(tick, countRef.current > 0 ? ACTIVE_POLL_MS : IDLE_POLL_MS);
    };
    void tick();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [open, loadRecent]);

  // Elapsed times move while the list is open.
  useEffect(() => {
    if (!open) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [open]);

  const activeItems = active?.items ?? [];
  const finished = (recent ?? []).filter((item) => !isActive(item));

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        setNow(Date.now());
        if (next) void loadRecent();
      }}
    >
      <PopoverTrigger
        aria-label={count > 0 ? `Jobs: ${count} running` : "Jobs"}
        className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2 text-sm text-ink-secondary transition-colors hover:bg-surface-raised hover:text-ink data-[state=open]:bg-surface-raised"
      >
        <Icon icon={ListChecks} />
        <span className="hidden sm:inline">Jobs</span>
        {count > 0 ? (
          <span className="min-w-5 rounded-full bg-ink px-1.5 text-center font-mono text-2xs leading-5 text-paper">
            {count}
          </span>
        ) : null}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 p-2">
        <section aria-label="Running jobs">
          <h2 className="px-2 pt-1 pb-1.5 text-2xs font-medium text-ink-muted">
            {count > 0 ? `Running · ${count}` : "Nothing running"}
          </h2>
          {activeItems.length > 0 ? (
            <ul className="flex flex-col">
              {activeItems.map((item) => (
                <JobRow key={item.id} item={item} now={now} />
              ))}
            </ul>
          ) : null}
        </section>
        <section aria-label="Recent jobs" className="mt-1 border-t border-line pt-1">
          <h2 className="px-2 pt-1 pb-1.5 text-2xs font-medium text-ink-muted">Recent</h2>
          {recent === null ? (
            <p className="px-2 pb-1.5 text-2xs text-ink-muted">Loading</p>
          ) : finished.length === 0 ? (
            <p className="px-2 pb-1.5 text-2xs text-ink-muted">No finished jobs yet</p>
          ) : (
            <ul className="flex flex-col">
              {finished.map((item) => (
                <JobRow key={item.id} item={item} now={now} />
              ))}
            </ul>
          )}
        </section>
      </PopoverContent>
    </Popover>
  );
}
