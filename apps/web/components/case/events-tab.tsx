"use client";

import { useState } from "react";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import { SourceLine } from "@/components/dealproof";
import {
  EVENT_TOPIC_LABEL,
  EVENT_TOPICS,
  type EventTopic,
  eventTopic,
  EventTimeline,
} from "@/components/insight";
import { eventNature, toEvidence } from "./adapt";
import { useCaseDetail } from "./case-context";
import { BlockedByIdentity, EmptyState, TabHeading } from "./parts";

export { NatureTag } from "@/components/insight";

/**
 * Dated events, newest first. Each says how it is known: an announcement is the company
 * saying something, a report is an outlet saying it, and only a record confirms that it
 * happened.
 */
export function EventsTab() {
  const detail = useCaseDetail();
  const events = [...detail.events].sort((a, b) => b.event_date.localeCompare(a.event_date));
  const confirmed = events.filter((event) => eventNature(event) === "Recorded").length;
  const [topic, setTopic] = useState<EventTopic | "all">("all");
  const topics = EVENT_TOPICS.filter((option) => events.some((event) => eventTopic(event.kind) === option));
  const shown = topic === "all" ? events : events.filter((event) => eventTopic(event.kind) === topic);

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
          {topics.length > 1 ? (
            <div role="group" aria-label="Filter events by topic" className="flex flex-wrap gap-2">
              {(["all", ...topics] as const).map((option) => {
                const count =
                  option === "all"
                    ? events.length
                    : events.filter((event) => eventTopic(event.kind) === option).length;
                const pressed = topic === option;
                return (
                  <button
                    key={option}
                    type="button"
                    aria-pressed={pressed}
                    onClick={() => setTopic(option)}
                    className={cn(
                      "inline-flex h-8 items-center gap-2 rounded-md border px-3 text-dense transition-colors",
                      pressed
                        ? "border-accent-line bg-accent-tint text-accent"
                        : "border-line-strong bg-surface text-ink-secondary hover:bg-surface-raised",
                    )}
                  >
                    {option === "all" ? "All" : EVENT_TOPIC_LABEL[option]}
                    <span className="font-mono text-2xs">{count}</span>
                  </button>
                );
              })}
            </div>
          ) : null}
          <EventTimeline
            layout="alternating"
            items={shown.map((event) => ({
              id: event.id,
              date: event.event_date,
              title: event.title,
              kind: event.kind,
              nature: eventNature(event),
              quote: event.evidence.deleted ? null : event.evidence.quote,
              source: <SourceLine evidence={[toEvidence(event.evidence)]} />,
            }))}
          />
          <p className="max-w-(--layout-prose-max) text-xs text-ink-secondary">
            An announcement of a plan is worded as a plan. It becomes a confirmed occurrence
            only when an independent record or document shows it happened.
          </p>
        </>
      )}
    </div>
  );
}
