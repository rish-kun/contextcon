/**
 * The run activity event, as `docs/design/iterations/D-live-run-experience.md` §2 defines
 * it. These are hand-written from the spec until the API's `ActivityOut` lands in
 * `lib/api/schema.ts`; swap the aliases over then and delete the bodies.
 *
 * An activity is a fact about what a run did. The stream holds public lookup information
 * and the user's own criteria only: never claim text, document text or model output.
 */

export type ActivityKind = "status" | "call" | "source" | "model" | "finding" | "notice";

export type ActivitySubject =
  | "company"
  | "claim"
  | "investor"
  | "round"
  | "identity"
  | "event"
  | "peer"
  | "assessment"
  | "request_list";

export type ActivityEndpoint =
  | "company_identify"
  | "company_search"
  | "company_enrich"
  | "person_search"
  | "job_search"
  | "web_search"
  | "web_fetch"
  | "messages";

export type SourceFailReason =
  | "http_403"
  | "timeout"
  | "robots"
  | "empty"
  | "too_large"
  | "budget";

/** A public page or a Crustdata record. Never an uploaded document's content. */
export interface ActivitySource {
  type: "web_page" | "crustdata_record" | "seller_document";
  /** Registrable host, lower case. Null for anything that is not a web page. */
  domain: string | null;
  url: string | null;
  title: string | null;
  source_class: string;
  /** Date of the fact. Null reads as "no date". */
  as_of: string | null;
  state: "read" | "failed" | "skipped";
  reason: SourceFailReason | string | null;
}

/** One external call, in its final state. */
export interface ActivityCall {
  provider: "crustdata" | "anthropic";
  endpoint: ActivityEndpoint | string;
  ok: boolean;
  error: string | null;
  from_cache: boolean;
  attempts: number;
  duration_ms: number | null;
  /** This call. 0 on a cache hit, null when the provider did not report. */
  credits: number | null;
  usd: number | null;
  /** Run totals after this call, so a replay can redraw the meter. */
  credits_total: number | null;
  usd_total: number | null;
}

export type MarkState = "pending" | "found" | "none" | "not_checked";

/**
 * A preview row inside a `finding`. Later stages send only the fields that changed, so
 * every field past `id` and `stage` is optional and rows are merged by id.
 */
export interface ActivityItem {
  id: string;
  stage: string;
  name?: string | null;
  domain?: string | null;
  location?: string | null;
  headcount?: number | null;
  headcount_is_estimate?: boolean | null;
  reason?: string | null;
  marks?: { funding?: MarkState; headcount?: MarkState; hiring?: MarkState } | null;
  highlight?: string | null;
  fit?: number | null;
  /** A share between 0 and 1. */
  assessable?: number | null;
  rank?: number | null;
  /** Discover `explained`: why the company is on the list. */
  why?: string | null;
  /* claim */
  category?: string | null;
  status?: string | null;
  previous_status?: string | null;
  evidence_count?: number | null;
  snippet?: string | null;
  gap?: string | null;
  /* identity */
  matched_keys?: string[] | null;
  /* round */
  company?: string | null;
  company_id?: string | null;
  round?: string | null;
  date?: string | null;
  amount_usd?: number | null;
  investors?: { key: string; name: string }[] | null;
  /* investor */
  comparable_rounds?: number | null;
  last_round_date?: string | null;
  /* event */
  event_kind?: string | null;
  title?: string | null;
  /* assessment */
  version?: number | null;
  disposition?: string | null;
  previous_disposition?: string | null;
}

export interface Activity {
  /** Per run, strictly increasing from 1. Also the SSE `id:`. */
  seq: number;
  run_id: string;
  step_id: string | null;
  step_key: string | null;
  kind: ActivityKind;
  /** When it happened (UTC). Not when it was sent. */
  at: string;
  label: string;
  detail: string | null;
  progress: { done: number; total: number } | null;
  source: ActivitySource | null;
  call: ActivityCall | null;
  counts: Record<string, number | null> | null;
  highlights: string[] | null;
  items: ActivityItem[] | null;
  subject: ActivitySubject | null;
  code: string | null;
  ref: { type: string; id: string } | null;
}

/** `GET /runs/{id}/activity`. */
export interface ActivityPage {
  items: Activity[];
  next_after: number | null;
}
