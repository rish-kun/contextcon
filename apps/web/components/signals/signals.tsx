"use client";

import Link from "next/link";
import { caseHref, useShell } from "@/components/app-shell";
import { SourceLine } from "@/components/dealproof";
import { toEvidence } from "@/components/discover/adapt";
import {
  EVENT_NATURE_MEANING,
  EVENT_TOPIC_LABEL,
  EVENT_TOPICS,
  eventTopic,
  NATURE_TAG,
  NatureTag,
  TopicTag,
  type EventNature,
  type EventTopic,
} from "@/components/insight";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  Page,
  PageHeader,
  Panel,
  PanelBody,
  PanelHeader,
  RowLink,
  Segmented,
  Toolbar,
  Tooltip,
} from "@/components/ui";
import { FilterSelect } from "@/components/workspace/filter-select";
import type { CaseDetail } from "@/lib/api/client";
import { formatDate, formatTime, plural } from "@/lib/format";
import { CLAIM_STATUS_LABEL, DISPOSITION_LABEL } from "@/lib/labels";
import type { Evidence } from "@/lib/types";
import { useUrlState } from "@/lib/url-state";
import { coverageNote, useWorkspace, type Workspace } from "@/lib/workspace";

const CATEGORIES = ["event", "assessment", "document"] as const;
type Category = (typeof CATEGORIES)[number];
const NATURES: EventNature[] = ["Announced", "Reported", "Recorded"];

interface Signal {
  id: string;
  caseId: string;
  company: string;
  /** When it happened: an ISO date of any precision, or a timestamp. Null when undated. */
  date: string | null;
  /** True when the record carries a time of day, not only a date. */
  timed: boolean;
  category: Category;
  /** How a company event is known. Null for DealProof's own records. */
  nature: EventNature | null;
  /** The API's event kind, for the topic tag. */
  kind: string | null;
  text: string;
  /** Second line: the cause of a change, or who uploaded a document. */
  detail: string | null;
  evidence: Evidence[];
}

/** How an event is known, read from the class of the source it rests on. */
function natureOf(event: CaseDetail["events"][number]): EventNature {
  const sourceClass = event.evidence.source.source_class;
  if (sourceClass === "company_announcement" || sourceClass === "seller_statement") return "Announced";
  return sourceClass === "news" ? "Reported" : "Recorded";
}

const WORDS: Record<string, string> = { ...CLAIM_STATUS_LABEL, ...DISPOSITION_LABEL };
/** A status or disposition key in the product's words; anything else as written. */
const word = (value: string) => WORDS[value] ?? value;

function signalsOf(workspace: Workspace): Signal[] {
  const out: Signal[] = [];
  for (const item of workspace.cases) {
    const detail = workspace.details[item.id];
    if (!detail) continue;
    const base = { caseId: item.id, company: item.name };

    for (const event of detail.events) {
      out.push({
        ...base,
        id: `event:${event.id}`,
        date: event.event_date || null,
        timed: false,
        category: "event",
        nature: natureOf(event),
        kind: event.kind,
        text: event.title,
        detail: null,
        evidence: [toEvidence(event.evidence)],
      });
    }

    const assessment = detail.assessment;
    if (assessment) {
      const lines = assessment.diff_from_previous ?? [];
      const disposition = assessment.judgments.screening_disposition.disposition;
      const moved = lines.find((line) => line.kind === "disposition");
      out.push({
        ...base,
        id: `assessment:${assessment.id}`,
        date: assessment.created_at,
        timed: true,
        category: "assessment",
        nature: null,
        kind: null,
        text:
          moved && moved.before
            ? `Assessment v${assessment.version} · ${word(moved.before)} → ${word(moved.after)}`
            : `Assessment v${assessment.version} · ${DISPOSITION_LABEL[disposition]}`,
        detail: moved?.because ? `Because: ${moved.because}` : null,
        evidence: (moved?.evidence ?? []).map(toEvidence),
      });
      lines
        .filter((line) => line.kind === "claim")
        .forEach((line, index) => {
          out.push({
            ...base,
            id: `claim:${assessment.id}:${line.subject_id ?? index}`,
            date: assessment.created_at,
            timed: true,
            category: "assessment",
            nature: null,
            kind: null,
            text: `${line.subject} · ${line.before ? `${word(line.before)} → ` : ""}${word(line.after)}`,
            detail: line.because ? `Because: ${line.because}` : null,
            evidence: line.evidence.map(toEvidence),
          });
        });
    }

    for (const document of detail.documents) {
      out.push({
        ...base,
        id: `document:${document.id}`,
        date: document.uploaded_at,
        timed: true,
        category: "document",
        nature: null,
        kind: null,
        text: `Document received · ${document.filename}`,
        detail: [
          document.uploaded_by_name ? `Uploaded by ${document.uploaded_by_name}` : null,
          document.claims_extracted > 0 ? `${plural(document.claims_extracted, "claim")} read from it` : null,
          document.purged ? "File since deleted" : null,
        ]
          .filter(Boolean)
          .join(" · ") || null,
        evidence: [],
      });
    }
  }
  return out.sort((a, b) => (b.date ?? "").localeCompare(a.date ?? ""));
}

/* ───────────────────────── Activity by month ───────────────────────── */

interface Bucket {
  key: string;
  label: string;
  count: number;
}

const MAX_MONTHS = 36;

/** Dated items counted per month, or per year once the span is too long for months to read. */
function buckets(signals: Signal[]): Bucket[] {
  const months = signals.flatMap((signal) => (signal.date && /^\d{4}-\d{2}/.test(signal.date) ? [signal.date.slice(0, 7)] : []));
  if (months.length === 0) return [];
  const sorted = [...months].sort();
  const [firstYear, firstMonth] = sorted[0].split("-").map(Number);
  const [lastYear, lastMonth] = sorted[sorted.length - 1].split("-").map(Number);
  const span = (lastYear - firstYear) * 12 + (lastMonth - firstMonth) + 1;
  const counts = new Map<string, number>();
  const byYear = span > MAX_MONTHS;
  for (const month of months) {
    const key = byYear ? month.slice(0, 4) : month;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const out: Bucket[] = [];
  if (byYear) {
    for (let year = firstYear; year <= lastYear; year += 1) {
      const key = String(year);
      out.push({ key, label: key, count: counts.get(key) ?? 0 });
    }
    return out;
  }
  for (let index = 0; index < span; index += 1) {
    const total = firstMonth - 1 + index;
    const key = `${firstYear + Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, "0")}`;
    out.push({ key, label: formatDate(key) ?? key, count: counts.get(key) ?? 0 });
  }
  return out;
}

/**
 * One series, so one ink and no legend: how many items fall in each month. Every bar names
 * its month and count on hover and focus; the feed below is the table of the same data.
 */
function ActivityChart({ signals }: { signals: Signal[] }) {
  const data = buckets(signals);
  if (data.length < 3 || data.filter((bucket) => bucket.count > 0).length < 2) return null;
  const peak = Math.max(...data.map((bucket) => bucket.count));
  const busiest = data.find((bucket) => bucket.count === peak);
  return (
    <Panel>
      <PanelHeader
        title="Items by date"
        meta={`${data[0].label} to ${data[data.length - 1].label}${busiest ? ` · most in ${busiest.label}, ${busiest.count}` : ""}`}
      />
      <PanelBody>
        <ol aria-label="Items per period, oldest first" className="flex h-20 items-end gap-0.5 border-b border-line-strong">
          {data.map((bucket) => (
            <li key={bucket.key} className="flex h-full min-w-0 flex-1 items-end">
              <Tooltip content={`${bucket.label} · ${plural(bucket.count, "item")}`}>
                <button
                  type="button"
                  aria-label={`${bucket.label}: ${plural(bucket.count, "item")}`}
                  className="group flex h-full w-full items-end justify-center"
                >
                  <span
                    className={
                      bucket.count > 0
                        ? "w-full max-w-6 rounded-t-xs bg-ink-secondary transition-colors group-hover:bg-ink group-focus-visible:bg-ink"
                        : "w-full max-w-6"
                    }
                    style={{ height: bucket.count > 0 ? `${Math.max((bucket.count / peak) * 100, 6)}%` : 0 }}
                  />
                </button>
              </Tooltip>
            </li>
          ))}
        </ol>
        <p className="flex justify-between pt-1 font-mono text-2xs text-ink-muted">
          <span>{data[0].label}</span>
          <span>{data[data.length - 1].label}</span>
        </p>
      </PanelBody>
    </Panel>
  );
}

/* ───────────────────────── Feed ───────────────────────── */

const RECORD_TAG: Record<Exclude<Category, "event">, { label: string; meaning: string }> = {
  assessment: { label: "Assessment", meaning: "A versioned change DealProof wrote after new evidence arrived" },
  document: { label: "Document", meaning: "A file attached to a case in your workspace" },
};

function Row({ signal }: { signal: Signal }) {
  const time = signal.timed ? formatTime(signal.date)?.replace(" IST", "") : null;
  return (
    <li className="grid grid-cols-1 gap-x-4 gap-y-1 border-b border-line px-4 py-3 last:border-b-0 md:grid-cols-[3rem_12rem_minmax(0,1fr)_auto] md:items-start">
      <span className="font-mono text-xs text-ink-muted md:pt-0.5">
        {time ? <time dateTime={signal.date ?? undefined}>{time}</time> : null}
      </span>
      <RowLink href={caseHref(signal.caseId)} className="truncate text-dense">
        {signal.company}
      </RowLink>
      <div className="flex min-w-0 flex-col items-start gap-1">
        <p className="text-dense text-ink">{signal.text}</p>
        {signal.detail ? <p className="text-xs text-ink-secondary">{signal.detail}</p> : null}
        {signal.evidence.length > 0 ? <SourceLine evidence={signal.evidence} /> : null}
      </div>
      <div className="flex flex-wrap items-center gap-1 md:justify-end">
        {signal.kind ? <TopicTag kind={signal.kind} /> : null}
        {signal.nature ? (
          <NatureTag nature={signal.nature} />
        ) : signal.category !== "event" ? (
          <Badge title={RECORD_TAG[signal.category].meaning}>{RECORD_TAG[signal.category].label}</Badge>
        ) : null}
      </div>
    </li>
  );
}

function Feed({ signals }: { signals: Signal[] }) {
  const groups: { key: string; label: string; items: Signal[] }[] = [];
  for (const signal of signals) {
    const label = formatDate(signal.date) ?? "Undated";
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.items.push(signal);
    else groups.push({ key: `${label}:${signal.id}`, label, items: [signal] });
  }
  return (
    <div className="flex flex-col">
      {groups.map((group) => (
        <section key={group.key} aria-label={group.label}>
          <h3 className="flex items-baseline gap-2 border-b border-line bg-surface-sunken px-4 py-1.5 font-mono text-xs font-medium text-ink-secondary">
            {group.label}
            <span className="font-normal text-ink-muted">{group.items.length}</span>
            {group.label === "Undated" ? (
              <span className="font-sans font-normal text-ink-muted">No reliable date on record, so these are listed apart</span>
            ) : null}
          </h3>
          <ul>
            {group.items.map((signal) => (
              <Row key={signal.id} signal={signal} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

/**
 * `/app/signals`. One dated feed of what the record shows across cases: company events with
 * how each is known, DealProof's own assessment changes, and documents received. Ordered by
 * the date the thing happened, in absolute dates, so a line can be quoted.
 */
export function Signals() {
  const { openVerify } = useShell();
  const [state, retry] = useWorkspace();
  const [params, setParams, resetParams] = useUrlState();

  if (state.status === "loading") {
    return (
      <Page>
        <PageHeader title="Signals" />
        <Panel>
          <LoadingState label="Loading signals" shape="rows" count={6} />
        </Panel>
      </Page>
    );
  }
  if (state.status === "error") {
    return (
      <Page>
        <PageHeader title="Signals" />
        <ErrorState size="page" what="Signals" reason={state.message} status={state.code} onRetry={retry} />
      </Page>
    );
  }

  const workspace = state.data;
  const all = signalsOf(workspace);
  const count = (category: Category) => all.filter((signal) => signal.category === category).length;

  const view = CATEGORIES.find((category) => category === params.get("view")) ?? "all";
  const topic = EVENT_TOPICS.find((option) => option === params.get("topic")) ?? null;
  const nature = NATURES.find((option) => option === params.get("nature")) ?? null;
  const company = params.get("company");
  const filtered = view !== "all" || topic !== null || nature !== null || company !== null;

  const shown = all.filter((signal) => {
    if (view !== "all" && signal.category !== view) return false;
    if (topic && (signal.kind === null || eventTopic(signal.kind) !== topic)) return false;
    if (nature && signal.nature !== nature) return false;
    if (company && signal.caseId !== company) return false;
    return true;
  });

  const companies = [...new Map(all.map((signal) => [signal.caseId, signal.company])).entries()].sort((a, b) =>
    a[1].localeCompare(b[1]),
  );
  const topics = EVENT_TOPICS.filter((option: EventTopic) =>
    all.some((signal) => signal.kind !== null && eventTopic(signal.kind) === option),
  );
  const natures = NATURES.filter((option) => all.some((signal) => signal.nature === option));
  const coverage = coverageNote(workspace);

  return (
    <Page>
      <PageHeader
        title="Signals"
        meta={
          <>
            <span className="font-mono">{all.length}</span> {all.length === 1 ? "item" : "items"} · from{" "}
            <span className="font-mono">{companies.length}</span> {companies.length === 1 ? "case" : "cases"} · ordered by
            the date it happened, not the date it was retrieved
            {coverage ? <span className="font-mono text-xs text-ink-muted"> · {coverage}</span> : null}
          </>
        }
        figures={
          all.length > 0
            ? [
                { label: "Company events", value: count("event") },
                { label: "Assessment changes", value: count("assessment") },
                { label: "Documents", value: count("document") },
              ]
            : undefined
        }
      />

      {all.length === 0 ? (
        <EmptyState
          size="page"
          title="No dated signals recorded yet"
          actions={
            <>
              <Button asChild variant="primary" size="sm">
                <Link href="/app/discover/new">New screening</Link>
              </Button>
              <Button size="sm" onClick={openVerify}>
                Verify a company
              </Button>
            </>
          }
        >
          Dated public events, assessment version changes, and received documents appear here across
          your cases as soon as verification runs.
        </EmptyState>
      ) : (
        <>
          <Toolbar count={`${shown.length} of ${all.length}`}>
            <Segmented
              label="Filter by kind of item"
              value={view}
              onChange={(next) => setParams({ view: next === "all" ? null : next })}
              options={[
                { value: "all", label: "All", count: all.length },
                { value: "event", label: "Company events", count: count("event") },
                { value: "assessment", label: "Assessment changes", count: count("assessment") },
                { value: "document", label: "Documents", count: count("document") },
              ]}
            />
            <FilterSelect
              label="Filter by how the event is known"
              all="Any nature"
              value={nature}
              onChange={(next) => setParams({ nature: next })}
              options={natures.map((value) => ({ value, label: NATURE_TAG[value] }))}
            />
            <FilterSelect
              label="Filter by topic"
              all="Any topic"
              value={topic}
              onChange={(next) => setParams({ topic: next })}
              options={topics.map((value) => ({ value, label: EVENT_TOPIC_LABEL[value] }))}
            />
            <FilterSelect
              label="Filter by company"
              all="All companies"
              value={company}
              onChange={(next) => setParams({ company: next })}
              options={companies.map(([id, name]) => ({ value: id, label: name }))}
            />
          </Toolbar>

          <ActivityChart signals={shown} />

          <Panel>
            <PanelBody flush>
              {shown.length === 0 ? (
                <EmptyState
                  title="No signals match these filters"
                  actions={
                    filtered ? (
                      <Button size="sm" onClick={resetParams}>
                        Reset filters
                      </Button>
                    ) : undefined
                  }
                >
                  Clear a filter or switch back to All to view every recorded item.
                </EmptyState>
              ) : (
                <Feed signals={shown} />
              )}
            </PanelBody>
          </Panel>

          {natures.length > 0 ? (
            <dl className="grid gap-x-8 gap-y-2 text-xs text-ink-secondary sm:grid-cols-3">
              {natures.map((value) => (
                <div key={value} className="flex flex-col">
                  <dt className="font-medium text-ink">{NATURE_TAG[value]}</dt>
                  <dd>{EVENT_NATURE_MEANING[value]}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </>
      )}
    </Page>
  );
}
