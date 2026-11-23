// Run with `pnpm --filter web test` (Node's built-in runner; Node strips the TS types).
// The cross-case screens used to derive their states from full case records
// (`GET /cases/{id}`); they now read `GET /workspace`. These tests keep the old
// derivations, applied to full records, and check the new ones give the same answers.
import assert from "node:assert/strict";
import { test } from "node:test";

import data from "./api/fixtures.json" with { type: "json" };
import {
  attention,
  claimCounts,
  claimTotal,
  countClaims,
  pipelineColumn,
  requestState,
  withAssessment,
} from "./workspace-state.ts";

const STATUSES = [
  "supported",
  "partially_corroborated",
  "conflicting_evidence",
  "contradicted",
  "cannot_verify",
  "not_checked",
];

/* ───────────── The derivations as they were, on a full record ───────────── */

const old = {
  claimCounts(detail) {
    if (!detail) return null;
    const counts = Object.fromEntries(STATUSES.map((status) => [status, 0]));
    for (const claim of detail.claims) counts[claim.status] += 1;
    return counts;
  },
  requestState(detail) {
    if (!detail) return "none";
    const status = detail.message?.status;
    if (!status) return (detail.request_list?.items.length ?? 0) > 0 ? "draft" : "none";
    return status === "suppressed_test_mode" ? "suppressed" : status;
  },
  attention(item, detail) {
    const out = [];
    if (item.identity_state !== "confirmed") {
      const candidates = detail?.identity.candidates.length ?? 0;
      out.push({
        what: `Identity ${item.identity_state === "ambiguous" ? "ambiguous" : "unresolved"}${candidates ? ` · ${candidates} ${candidates === 1 ? "candidate" : "candidates"}` : ""}`,
        segment: "identity",
      });
    }
    if (item.status === "failed") out.push({ what: "Verification did not finish", segment: "cost" });
    const request = old.requestState(detail);
    if (request === "draft") out.push({ what: "Request awaiting approval", segment: "request" });
    if (request === "approved") out.push({ what: "Request approved, not sent yet", segment: "request" });
    if (request === "failed") out.push({ what: "Request failed · not sent", segment: "request" });
    if (request === "unknown") out.push({ what: "Send result unknown", segment: "request" });
    const notChecked = old.claimCounts(detail)?.not_checked ?? 0;
    if (notChecked > 0) {
      out.push({
        what: notChecked === 1 ? "1 check was not run" : `${notChecked} checks were not run`,
        segment: "claims?status=not_checked",
      });
    }
    return out;
  },
  pipelineColumn(item, detail) {
    if (item.identity_state !== "confirmed") return "identity";
    if (item.status === "verifying") return "verifying";
    if (item.status === "failed") return "failed";
    const request = old.requestState(detail);
    if (request === "sent" || request === "suppressed") return "sent";
    if (request !== "none") return "drafted";
    return "assessed";
  },
  withAssessment(item, detail) {
    if (!detail) return item;
    const judgments = detail.assessment?.judgments;
    const fit = judgments?.opportunity_fit;
    return {
      ...item,
      disposition: item.disposition ?? judgments?.screening_disposition.disposition ?? null,
      fit_state: item.fit_state ?? fit?.state ?? detail.opportunity.fit_state ?? null,
      fit: item.fit ?? fit?.fit ?? detail.opportunity.fit ?? null,
      assessable_pct: item.assessable_pct ?? fit?.assessable_pct ?? detail.opportunity.assessable_pct ?? null,
    };
  },
};

/* ───────────── `record_from_detail` (apps/api/app/api/workspace_records.py) ───────────── */

function recordOf(d) {
  const run = d.case.run;
  const a = d.assessment;
  const fit = a?.judgments.opportunity_fit;
  const p = d.profile;
  const rl = d.request_list;
  const m = d.message;
  return {
    case_id: d.case.id,
    owner: d.case.owner,
    run: run
      ? {
          kind: run.kind,
          state: run.state,
          steps: run.steps.length,
          steps_finished: run.steps.filter((s) => s.state !== "pending" && s.state !== "running").length,
        }
      : null,
    identity_candidates: d.identity.candidates.length,
    claim_counts: old.claimCounts(d),
    opportunity: {
      thesis_id: d.opportunity.thesis_id,
      thesis_text: d.opportunity.thesis_text,
      fit_state: d.opportunity.fit_state,
      fit: d.opportunity.fit,
      assessable_pct: d.opportunity.assessable_pct,
      criterion_results: d.opportunity.criterion_results.map(({ criterion_id, label, kind, weight, state }) => ({
        criterion_id,
        label,
        kind,
        weight,
        state,
      })),
    },
    assessment: a
      ? {
          id: a.id,
          version: a.version,
          created_at: a.created_at,
          disposition: a.judgments.screening_disposition.disposition,
          fit_state: fit.state,
          fit: fit.fit,
          assessable_pct: fit.assessable_pct,
          diff_from_previous: a.diff_from_previous,
        }
      : null,
    profile: p
      ? {
          domain: p.domain?.value ?? null,
          headquarters: p.headquarters?.value ?? null,
          country: p.country?.value ?? null,
          headcount: p.headcount?.value ?? null,
          headcount_basis: p.headcount?.estimate_basis ?? null,
        }
      : null,
    events: d.events,
    documents: d.documents.map(({ id, filename, uploaded_at, uploaded_by_name, purged, claims_extracted }) => ({
      id,
      filename,
      uploaded_at,
      uploaded_by_name,
      purged,
      claims_extracted,
    })),
    request_list: rl
      ? {
          items: rl.items.map(({ document, priority, group }) => ({ document, priority, group })),
          email_send_enabled: rl.email_send_enabled,
          created_at: rl.created_at,
        }
      : null,
    message: m
      ? {
          status: m.status,
          current_revision: {
            number: m.current_revision.number,
            recipient: m.current_revision.recipient,
            entered_by_user_id: m.current_revision.entered_by_user_id,
            created_at: m.current_revision.created_at,
          },
          approval: m.approval,
          send: m.send,
        }
      : null,
  };
}

const clone = (value) => structuredClone(value);
const summaries = data.cases;
const details = data.caseDetails;

test("the API's fixture records are the fixture case records cut down", () => {
  assert.deepEqual(
    data.workspace.records.map((r) => r.case_id),
    summaries.map((s) => s.id),
  );
  for (const record of data.workspace.records) {
    assert.deepEqual(record, recordOf(details[record.case_id]), record.case_id);
  }
});

/** Full records in every state the screens tell apart, built from the fixtures. */
function variants() {
  const out = [];
  for (const summary of summaries) {
    const base = details[summary.id];
    out.push(["as is", summary, base]);
    for (const status of ["draft", "approved", "sending", "sent", "suppressed_test_mode", "failed", "unknown"]) {
      const d = clone(base);
      const message = clone(data.message.draft);
      message.status = status;
      d.message = message;
      out.push([`message ${status}`, summary, d]);
    }
    const listed = clone(base);
    listed.message = null;
    listed.request_list = clone(data.requestList);
    out.push(["list, no message", summary, listed]);
    const emptyList = clone(listed);
    emptyList.request_list.items = [];
    out.push(["empty list", summary, emptyList]);
    const bare = clone(base);
    bare.message = null;
    bare.request_list = null;
    bare.claims = [];
    bare.assessment = null;
    out.push(["no request, claims or assessment", summary, bare]);
    const oneUnchecked = clone(base);
    oneUnchecked.claims = base.claims.filter((c) => c.status === "not_checked").slice(0, 1);
    out.push(["one check not run", summary, oneUnchecked]);
    for (const status of ["verifying", "failed", "assessed", "awaiting_identity"]) {
      for (const identity of ["confirmed", "ambiguous", "unresolved"]) {
        out.push([`${status} ${identity}`, { ...summary, status, identity_state: identity }, base]);
      }
    }
    out.push([
      "list without assessment fields",
      { ...summary, disposition: null, fit_state: null, fit: null, assessable_pct: null },
      base,
    ]);
    out.push([
      "list and record without assessment",
      { ...summary, disposition: null, fit_state: null, fit: null, assessable_pct: null },
      bare,
    ]);
  }
  return out;
}

test("the derived states match the old ones on full records", () => {
  for (const [name, item, detail] of variants()) {
    const record = recordOf(detail);
    assert.deepEqual(claimCounts(record), old.claimCounts(detail), name);
    assert.equal(claimTotal(record), detail.claims.length, name);
    assert.deepEqual(countClaims(detail.claims), old.claimCounts(detail), name);
    assert.equal(requestState(record), old.requestState(detail), name);
    assert.deepEqual(attention(item, record), old.attention(item, detail), name);
    assert.equal(pipelineColumn(item, record), old.pipelineColumn(item, detail), name);
    assert.deepEqual(withAssessment(item, record), old.withAssessment(item, detail), name);
  }
});

test("without a record, every state reads as nothing known", () => {
  const item = summaries[1];
  assert.equal(claimCounts(undefined), null);
  assert.equal(requestState(undefined), "none");
  assert.deepEqual(attention(item, undefined), old.attention(item, undefined));
  assert.equal(pipelineColumn(item, undefined), old.pipelineColumn(item, undefined));
  assert.equal(withAssessment(item, undefined), item);
});
