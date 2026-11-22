"use client";

import { useState } from "react";
import { SourceLine } from "@/components/dealproof";
import {
  EVENT_TOPIC_LABEL,
  EVENT_TOPICS,
  type EventTopic,
  eventTopic,
  EventTimeline,
} from "@/components/insight";
import { Segmented } from "@/components/ui";
import { EVENT_NATURE_MEANING, eventNature, toEvidence } from "./adapt";
import { useCaseDetail } from "./case-context";
import { BlockedByIdentity, TabEmpty, TabSection } from "./parts";

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

  if (detail.identity.state !== "confirmed") {
    return <BlockedByIdentity what="Events are attached to a legal entity, not to a name" />;
  }
  if (events.length === 0) {
    return <TabEmpty title="No dated events found">The sources searched returned none for this entity</TabEmpty>;
  }

  return (
    <TabSection
      title="Events"
      meta={`${events.length} dated · ${confirmed} recorded · ${events.length - confirmed} announced or reported`}
      whyLabel="Recorded?"
      why={
        <dl className="flex flex-col gap-2">
          {(Object.keys(EVENT_NATURE_MEANING) as (keyof typeof EVENT_NATURE_MEANING)[]).map((nature) => (
            <div key={nature} className="flex flex-col">
              <dt className="font-medium text-ink">{nature}</dt>
              <dd>{EVENT_NATURE_MEANING[nature]}</dd>
            </div>
          ))}
        </dl>
      }
      action={
        topics.length > 1 ? (
          <Segmented
            label="Filter events by topic"
            value={topic}
            onChange={setTopic}
            options={(["all", ...topics] as const).map((option) => ({
              value: option,
              label: option === "all" ? "All" : EVENT_TOPIC_LABEL[option],
              count:
                option === "all"
                  ? events.length
                  : events.filter((event) => eventTopic(event.kind) === option).length,
            }))}
          />
        ) : undefined
      }
    >
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
    </TabSection>
  );
}
