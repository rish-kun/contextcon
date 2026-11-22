import {
  Banknote,
  Building2,
  CalendarDays,
  FileCheck,
  Handshake,
  type LucideIcon,
  Megaphone,
  Newspaper,
  Package,
  UserRound,
} from "lucide-react";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Icon } from "@/components/ui/icon";

/** How an event is known. Only a record or a document confirms that it happened. */
export type EventNature = "Announced" | "Reported" | "Recorded";

export const EVENT_NATURE_MEANING: Record<EventNature, string> = {
  Announced: "The company said so. Not confirmed to have happened",
  Reported: "An outlet reported it. Not independently confirmed",
  Recorded: "Confirmed occurrence: a record or document shows it",
};

const NATURE_ICON: Record<EventNature, LucideIcon> = {
  Announced: Megaphone,
  Reported: Newspaper,
  Recorded: FileCheck,
};

/** The words on the tag. Only a record counts as a confirmed occurrence. */
export const NATURE_TAG: Record<EventNature, string> = {
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

/** What an event is about. The API sends a free word; these are the groups a reader filters by. */
export const EVENT_TOPICS = ["funding", "leadership", "expansion", "launch", "partnership", "other"] as const;
export type EventTopic = (typeof EVENT_TOPICS)[number];

export const EVENT_TOPIC_LABEL: Record<EventTopic, string> = {
  funding: "Funding",
  leadership: "Leadership",
  expansion: "Expansion",
  launch: "Launch",
  partnership: "Partnership",
  other: "Other",
};

const TOPIC_ICON: Record<EventTopic, LucideIcon> = {
  funding: Banknote,
  leadership: UserRound,
  expansion: Building2,
  launch: Package,
  partnership: Handshake,
  other: CalendarDays,
};

/** Reads the API's event kind ("facility", "funding", "appointment") into a topic. */
export function eventTopic(kind: string): EventTopic {
  const k = kind.toLowerCase();
  if (/fund|round|invest|rais|acqui/.test(k)) return "funding";
  if (/leader|appoint|hire|founder|executive|ceo|cfo|board/.test(k)) return "leadership";
  if (/facilit|expan|open|warehouse|office|site|capacity/.test(k)) return "expansion";
  if (/launch|product|release/.test(k)) return "launch";
  if (/partner|customer|contract|alliance/.test(k)) return "partnership";
  return "other";
}

/** The topic of an event as a quiet tag: an icon and a word, no colour of its own. */
export function TopicTag({ kind, className }: { kind: string; className?: string }) {
  const topic = eventTopic(kind);
  const word =
    topic === "other" && kind
      ? kind.charAt(0).toUpperCase() + kind.slice(1).replace(/[_-]+/g, " ")
      : EVENT_TOPIC_LABEL[topic];
  return (
    <span
      className={cn(
        "inline-flex h-6 shrink-0 items-center gap-1 rounded-xs bg-surface-sunken px-2 text-xs whitespace-nowrap text-ink-secondary",
        className,
      )}
    >
      <Icon icon={TOPIC_ICON[topic]} size={14} />
      {word}
    </span>
  );
}

export interface TimelineItem {
  id: string;
  /** ISO date of the event. */
  date: string;
  title: string;
  /** The API's event kind: "funding", "facility", "launch". */
  kind: string;
  nature: EventNature;
  /** The exact words taken from the source. */
  quote?: string | null;
  /** The source chip. Required. */
  source: React.ReactNode;
  /** A line above the title, for a feed that mixes companies: the company and a link to its case. */
  context?: React.ReactNode;
}

function Entry({ item, alternate, side, last }: { item: TimelineItem; alternate: boolean; side: "left" | "right"; last: boolean }) {
  const confirmed = item.nature === "Recorded";
  const flipped = alternate && side === "left";

  const date = (
    <time
      dateTime={item.date}
      className={cn(
        "col-span-2 pb-1 font-mono text-xs text-ink sm:col-span-1 sm:pt-0.5 sm:pb-0 sm:text-right",
        alternate && (flipped ? "lg:col-start-3 lg:row-start-1 lg:text-left" : "lg:col-start-1 lg:row-start-1 lg:text-right"),
      )}
    >
      {formatDate(item.date)}
    </time>
  );

  return (
    <li
      className={cn(
        "grid grid-cols-[1rem_minmax(0,1fr)] gap-x-4 sm:grid-cols-[7rem_1rem_minmax(0,1fr)]",
        alternate && "lg:grid-cols-[minmax(0,1fr)_1rem_minmax(0,1fr)]",
      )}
    >
      {date}
      {/* The rail: a filled node for a confirmed occurrence, an open one otherwise. */}
      <div className={cn("flex flex-col items-center", alternate && "lg:col-start-2 lg:row-start-1")} aria-hidden>
        <span
          className={cn(
            "mt-1 size-2.5 shrink-0 rounded-full border-stamp border-ink",
            confirmed ? "bg-ink" : "bg-paper",
          )}
        />
        {last ? null : <span className="w-px flex-1 bg-line-strong" />}
      </div>
      <div
        className={cn(
          "flex min-w-0 flex-col items-start gap-2",
          last ? "pb-0" : "pb-8",
          alternate && (flipped ? "lg:col-start-1 lg:row-start-1 lg:items-end lg:text-right" : "lg:col-start-3 lg:row-start-1"),
        )}
      >
        {item.context ? <div className="text-xs text-ink-secondary">{item.context}</div> : null}
        <p className="text-sm text-ink">{item.title}</p>
        <div className={cn("flex flex-wrap items-center gap-x-2 gap-y-1", flipped && "lg:justify-end")}>
          <TopicTag kind={item.kind} />
          <NatureTag nature={item.nature} />
        </div>
        {item.quote ? (
          <blockquote className="max-w-(--layout-prose-max) border-l-2 border-line-strong pl-3 text-left text-dense text-ink-secondary">
            “{item.quote}”
          </blockquote>
        ) : null}
        {item.source}
      </div>
    </li>
  );
}

/**
 * Dated events on a rail, newest first. Every entry carries two tags that answer two
 * different questions: what it is about (funding, leadership, expansion) and how it is
 * known (announcement, report, confirmed occurrence). The rail node repeats the second:
 * filled only for a confirmed occurrence.
 *
 * `layout="alternating"` places entries on either side of the rail from 1024px up; below
 * that, and with `layout="single"`, it is one column with the date on the left.
 */
export function EventTimeline({
  items,
  layout = "single",
  className,
}: {
  items: TimelineItem[];
  layout?: "single" | "alternating";
  className?: string;
}) {
  const sorted = [...items].sort((a, b) => b.date.localeCompare(a.date));
  return (
    <ol className={cn("flex flex-col", className)}>
      {sorted.map((item, index) => (
        <Entry
          key={item.id}
          item={item}
          alternate={layout === "alternating"}
          side={index % 2 === 0 ? "right" : "left"}
          last={index === sorted.length - 1}
        />
      ))}
    </ol>
  );
}
