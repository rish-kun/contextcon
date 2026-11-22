"use client";

import { Fragment } from "react";
import type { RunOut } from "@/lib/api/client";
import { formatCredits, plural } from "@/lib/format";
import type { RunActivityView, TallyRow } from "@/lib/run/activity-store";
import { cn } from "@/lib/utils";
import { NumberTween } from "@/components/dealproof/number-tween";
import { Panel, PanelHeader } from "@/components/ui/card";
import { ENDPOINTS_BY_KIND, ENDPOINT_LABEL, enrichBreakdown, modelUsd, tallyPhrase } from "./wording";

interface Clause {
  value: number;
  before?: string;
  after: string;
}

const sum = (row: TallyRow | undefined, key: string) => row?.counts[key] ?? 0;

/** Up to four clauses, chosen per pipeline. Every number is a sum of event counts. */
function headline(kind: RunOut["kind"], view: RunActivityView): Clause[] {
  const row = (endpoint: string) => view.tally.rows.get(endpoint);
  const search = row("company_search");
  const enrich = row("company_enrich");
  const facts = view.tally.model.counts.facts ?? 0;
  const pages = sum(row("web_fetch"), "read");
  let clauses: Clause[];
  switch (kind) {
    case "discover":
      clauses = [
        { value: sum(search, "new") || sum(search, "returned"), after: "companies matched" },
        { value: sum(enrich, "returned"), after: "enriched" },
        { value: sum(enrich, "with_headcount_series"), before: "headcount series for", after: "" },
        { value: sum(row("job_search"), "postings"), after: "job postings" },
      ];
      break;
    case "investor_discover":
      clauses = [
        { value: sum(search, "new") || sum(search, "returned"), after: "comparable companies" },
        { value: view.rounds.counts.rounds ?? sum(enrich, "funding_rounds"), after: "funding rounds read" },
        { value: view.rounds.counts.investors ?? 0, after: "investors named" },
        { value: view.rounds.counts.rounds_dated ?? 0, after: "rounds with a date" },
      ];
      break;
    case "verify":
      clauses = [
        { value: sum(row("company_identify"), "candidates"), after: "identity candidates" },
        { value: sum(row("person_search"), "returned"), after: "people records" },
        { value: pages, after: "pages read" },
        { value: facts, after: "facts extracted" },
      ];
      break;
    default: {
      const claims = [...view.claims.values()];
      clauses = [
        { value: claims.filter((c) => c.stage === "settled").length, after: "claims rechecked" },
        { value: pages, after: "pages read" },
        { value: facts, after: "facts extracted" },
        {
          value: claims.filter((c) => c.stage === "settled" && c.previousStatus && c.status !== c.previousStatus).length,
          after: "statuses changed",
        },
      ];
    }
  }
  return clauses.filter((clause) => clause.value > 0);
}

function modelLine(view: RunActivityView): string | null {
  const { reads, usd, counts } = view.tally.model;
  if (reads === 0) return null;
  const parts = [plural(reads, "read")];
  if (counts.facts) parts.push(`${plural(counts.facts, "fact")} extracted`);
  if (counts.claims) parts.push(`${plural(counts.claims, "claim")} read`);
  if (counts.explained) parts.push(`${counts.explained} explained`);
  if (counts.rejected_no_span) parts.push(`${counts.rejected_no_span} discarded: no matching passage`);
  if (usd > 0) parts.push(modelUsd(usd));
  return parts.join(" · ");
}

function EndpointRow({ endpoint, row }: { endpoint: string; row: TallyRow | undefined }) {
  const label = ENDPOINT_LABEL[endpoint] ?? endpoint.replace(/_/g, " ");
  if (!row) {
    return (
      <tr className="text-ink-muted">
        <th scope="row" className="py-1 pr-2 text-left font-normal">
          {label}
        </th>
        <td className="py-1 pr-2 font-mono text-xs" colSpan={3}>
          0
        </td>
      </tr>
    );
  }
  const breakdown = enrichBreakdown(row);
  const notes = [breakdown, row.highlights.length > 0 ? row.highlights.join(" · ") : null].filter(Boolean);
  return (
    <>
      <tr className="text-ink">
        <th scope="row" className="py-1 pr-2 text-left align-top font-normal">
          {label}
        </th>
        <td className="py-1 pr-2 align-top font-mono text-xs whitespace-nowrap text-ink-secondary">
          {plural(row.calls, "call")}
        </td>
        <td className="py-1 pr-2 align-top">
          {tallyPhrase(row)}
          {row.failed > 0 ? <span className="text-contradicted"> · {row.failed} failed</span> : null}
          {row.retried > 0 ? <span className="text-ink-secondary"> · {row.retried} retried</span> : null}
          {row.fromCache > 0 ? <span className="text-ink-secondary"> · {row.fromCache} from cache</span> : null}
        </td>
        <td className="py-1 text-right align-top font-mono text-xs whitespace-nowrap text-ink-secondary">
          {formatCredits(row.credits)} cr
        </td>
      </tr>
      {notes.map((note) => (
        <tr key={note}>
          <td colSpan={4} className="pb-1 pl-3 text-xs text-ink-secondary">
            {note}
          </td>
        </tr>
      ))}
    </>
  );
}

export interface CrustdataTallyProps {
  kind: RunOut["kind"];
  view: RunActivityView;
  /** `line` is the one-row form for short runs and narrow screens. */
  form?: "panel" | "line";
  className?: string;
}

/**
 * A running summary of what the data API returned, built by adding up the `counts` on
 * the run's call events. Endpoint families this kind of run can use are listed from the
 * start with a muted 0, so what is still to come is visible without a promise of progress.
 */
export function CrustdataTally({ kind, view, form = "panel", className }: CrustdataTallyProps) {
  const { tally } = view;
  const clauses = headline(kind, view);
  const model = modelLine(view);
  const expected = ENDPOINTS_BY_KIND[kind];
  const endpoints = [...expected, ...[...tally.rows.keys()].filter((key) => !expected.includes(key))];
  const sources = view.sourceCounts.read + view.sourceCounts.failed;

  if (form === "line") {
    return (
      <p className={cn("text-xs text-ink-secondary", className)}>
        <span className="text-ink">From Crustdata:</span>{" "}
        {tally.calls === 0
          ? kind === "recheck" || kind === "evaluate"
            ? "0 calls (rechecks read seller documents)"
            : "0 calls"
          : `${plural(tally.calls, "call")} · ${formatCredits(tally.credits)} cr`}
        {model ? ` · Model: ${model}` : null} · Sources: {sources} public
      </p>
    );
  }

  return (
    <Panel aria-label="What Crustdata returned" className={className}>
      <PanelHeader
        title="From Crustdata"
        meta={
          tally.calls > 0
            ? `${formatCredits(tally.credits)} cr · ${plural(tally.calls, "call")}${
                tally.fromCache > 0 ? ` · ${tally.fromCache} from cache` : ""
              }`
            : undefined
        }
      />
      <p className="border-b border-line px-4 py-3 text-dense text-ink">
        {clauses.length === 0 ? (
          <span className="text-ink-muted">Nothing returned yet</span>
        ) : (
          clauses.map((clause, index) => (
            <Fragment key={clause.after || clause.before}>
              {index > 0 ? <span className="text-ink-muted"> · </span> : null}
              <span className="whitespace-nowrap">
                {clause.before ? `${clause.before} ` : null}
                <NumberTween value={clause.value} className="font-mono font-medium" />
                {clause.after ? ` ${clause.after}` : null}
              </span>
            </Fragment>
          ))
        )}
      </p>
      {endpoints.length > 0 ? (
        <div className="px-4 py-2">
          <table className="w-full text-dense">
            <tbody>
              {endpoints.map((endpoint) => (
                <EndpointRow key={endpoint} endpoint={endpoint} row={tally.rows.get(endpoint)} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="px-4 py-3 text-dense text-ink-muted">
          0 calls. A recheck reads seller documents, not Crustdata
        </p>
      )}
      {model ? (
        <p className="border-t border-line px-4 py-2 text-xs text-ink-secondary">
          <span className="text-ink">Model:</span> {model}
        </p>
      ) : null}
    </Panel>
  );
}
