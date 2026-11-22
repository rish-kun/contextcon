"use client";

import { FileCheck, type LucideIcon, Megaphone, Newspaper } from "lucide-react";
import type { CaseDetail } from "@/lib/api/client";
import { formatDate, plural } from "@/lib/format";
import { staggerDelay } from "@/lib/transitions";
import { cn } from "@/lib/utils";
import { SourceLine } from "@/components/dealproof";
import { Icon } from "@/components/ui";
import { EVENT_NATURE_MEANING, type EventNature, eventNature, toEvidence } from "./adapt";
import { useCaseDetail } from "./case-context";
import { BlockedByIdentity, EmptyState, TabHeading } from "./parts";

const NATURE_ICON: Record<EventNature, LucideIcon> = {
  Announced: Megaphone,
  Reported: Newspaper,
  Recorded: FileCheck,
};

/** The words on the tag. Only a record counts as a confirmed occurrence. */
const NATURE_TAG: Record<EventNature, string> = {
  Announced: "Announcement",
  Reported: "Reported",
  Recorded: "Confirmed occurrence",
};

/**
 * How the event is known, as shape and words: a solid tag for a confirmed occurrence, a
 * dashed one for something only announced or reported.
 */
export function NatureTag({ nature, className }: { nature: EventNature; className?: string }) {
  const confirmed = nature === "Recorded";
  return (
    <span
      title={EVENT_NATURE_MEANING[nature]}
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1 rounded-xs border px-2 text-xs font-medium whitespace-nowrap",
        confirmed
          ? "border-ink bg-surface text-ink"
          : "border-dashed border-line-strong bg-surface text-ink-secondary",
        className,
      )}
    >
      <Icon icon={NATURE_ICON[nature]} size={14} />
      {NATURE_TAG[nature]}
    </span>
  );
}

function TimelineEvent({
  event,
  index,
  last,
}: {
  event: CaseDetail["events"][number];
  index: number;
  last: boolean;
}) {
  const nature = eventNature(event);
  const confirmed = nature === "Recorded";
  return (
    <li
      style={{ animationDelay: `${staggerDelay(index)}s` }}
      className="grid animate-row-in grid-cols-[1rem_minmax(0,1fr)] gap-x-4 motion-reduce:animate-none sm:grid-cols-[7rem_1rem_minmax(0,1fr)]"
    >
      <time
        dateTime={event.event_date}
        className="col-span-2 pb-1 font-mono text-xs text-ink sm:col-span-1 sm:pt-0.5 sm:pb-0 sm:text-right"
      >
        {formatDate(event.event_date)}
      </time>
      {/* The rail: a filled node for a confirmed occurrence, an open one otherwise. */}
      <div className="flex flex-col items-center" aria-hidden>
        <span
          className={cn(
            "mt-1 size-2.5 shrink-0 rounded-full border-stamp border-ink",
            confirmed ? "bg-ink" : "bg-paper",
          )}
        />
        {last ? null : <span className="w-px flex-1 bg-line-strong" />}
      </div>
      <div className={cn("flex min-w-0 flex-col items-start gap-2", last ? "pb-0" : "pb-8")}>
        <p className="text-sm text-ink">{event.title}</p>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <NatureTag nature={nature} />
          <span className="text-xs text-ink-muted">{EVENT_NATURE_MEANING[nature]}</span>
        </div>
        {event.evidence.quote && !event.evidence.deleted ? (
          <blockquote className="max-w-(--layout-prose-max) border-l-2 border-line-strong pl-3 text-dense text-ink-secondary">
            “{event.evidence.quote}”
          </blockquote>
        ) : null}
        <SourceLine evidence={[toEvidence(event.evidence)]} />
      </div>
    </li>
  );
}

/**
 * Dated events, newest first. Each says how it is known: an announcement is the company
 * saying something, a report is an outlet saying it, and only a record confirms that it
 * happened.
 */
export function EventsTab() {
  const detail = useCaseDetail();
  const events = [...detail.events].sort((a, b) => b.event_date.localeCompare(a.event_date));
  const confirmed = events.filter((event) => eventNature(event) === "Recorded").length;

  return (
    <div className="flex flex-col gap-6">
      <TabHeading
        title="Events"
        summary={
          events.length > 0
            ? `${plural(events.length, "dated event")} · ${confirmed} confirmed by a record · ${
                events.length - confirmed
              } announced or reported only`
            : undefined
        }
      />

      {detail.identity.state !== "confirmed" ? (
        <BlockedByIdentity what="Dated events are attached to a legal entity, not to a name." />
      ) : events.length === 0 ? (
        <EmptyState title="No dated public events found">
          No recent dated announcements or reported events were returned for this confirmed
          entity.
        </EmptyState>
      ) : (
        <>
          <ol className="flex flex-col">
            {events.map((event, index) => (
              <TimelineEvent
                key={event.id}
                event={event}
                index={index}
                last={index === events.length - 1}
              />
            ))}
          </ol>
          <p className="max-w-(--layout-prose-max) text-xs text-ink-secondary">
            An announcement of a plan is worded as a plan. It becomes a confirmed occurrence
            only when an independent record or document shows it happened.
          </p>
        </>
      )}
    </div>
  );
}
