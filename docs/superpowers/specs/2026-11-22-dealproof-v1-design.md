# DealProof v1 (ContextCon) — design

Status: draft for approval (Anthropic: direct API, Haiku 5.5 default) · 2026-11-22 · revised after product-adherence review (see "Review changes" at the end)
Source of truth for *what* to build: `DealProof product description.md` (the PRD). This doc decides *how*. Where this doc and the PRD disagree, the PRD wins.

## 1. Intent

Build the PRD's **"First version, at ContextCon"** row, completely, as a deployed web app:

- Thesis → shortlist of real companies (Discover), with editable must-haves / preferences.
- Business profile → shortlist of investors backed by dated funding records (Discover investors).
- Confirm a company's identity; check claims about team, leadership, funding and dated events (Verify).
- Show fit and evidence side by side, five separate judgments, one of four dispositions (Evaluate).
- Prepare the seller request, approve by a named person, send once (Act). Seller documents re-attach to the case and re-check affected claims, producing a new assessment version with a visible diff and keeping prior versions (owner's call, see §2 Scope decisions).
- Resume interrupted work; record what each case and each run cost.

It is a hackathon demo, so presentation is a first-class requirement: the UI must make "claims vs evidence", "fit vs evidence sufficiency", and "cannot verify / not checked" instantly legible to a judge who has never seen the product.

## 2. Goals / non-goals / anti-goals

**Goals**
- Every visible fact carries a source and an as-of date (PRD principle 1).
- Deterministic rules decide statuses, fit, sufficiency and disposition (principle 6). The LLM only *extracts* (criteria from a thesis, atomic claims from a deck, structured facts from evidence text) and *drafts* (memo prose, seller email). Every extraction is validated against its evidence span before rules use it (§6.3 step 5).
- Live data from Crustdata for companies, people, funding, headcount, hiring, and live web/news search/fetch.
- Professional, consistent, animated UI built with the `unslop` skill; inspiration from dealroom.co, dealroom.net, sarvam.ai (home page) and the user's component-site list.

**Scope decisions (owner)**
- **In v1:** re-checking claims when seller documents arrive, with a new AssessmentVersion and a visible diff. The PRD lists "re-evaluates when new evidence arrives" under *Next*, but its Act section and its final aim ("new evidence can change an assessment without hiding what was believed before, or why it changed") require it, so the owner keeps it in v1. It is built late in the plan (§10).
- **Deferred to Next:** dedicated registered-security-interest checks and litigation checks. Claims in those categories (e.g. "we have no debt", "no pending litigation") still appear in the ledger with their actual status — `cannot_verify` or `not_checked` — plus what would settle them (e.g. lender statements, a registered-charges extract, a litigation search report). They are never dropped.
- **In v1:** the marketing home page (the owner asked for it explicitly).

**Non-goals (v1)** — straight from the PRD's "Next/Later" rows: cross-document consistency checks between seller documents, peer benchmarking as a scored feature, multi-target comparison, financial scenarios, monitoring/alerts, deal tracking, data-room/CRM integrations, dedicated registered-security-interest and litigation checks. (A simple "comparable companies" list *is* in the finished-case contents, shown only where a fair comparison exists; it is informational, not scored — §6.6.)

**Anti-goals** (failure even if it "works")
- Any fact rendered without a source/date, or produced from model memory.
- Headcount/hiring treated as revenue or as proof of payroll.
- Records attached by name match alone — for companies, people or investors, at any stage of a case.
- Missing evidence lowering fit or causing "Deprioritise".
- "Not checked" rendered like a clean result.
- An email leaving without a named approver, leaving twice, or leaving with content other than what was approved.
- Confidential claim text sent to a web search provider, or one case's files/evidence/cache visible from another case.
- Fabricated example companies presented as real. (The PRD's Pune example may appear only as a clearly labelled illustration.)
- Changing the product idea.

## 3. Constraints

- Hosting (decided): **Cloud Run in `asia-south1`** (GCP project `cc-g527-showproduct`) at the smallest size that runs (min instances 0, lowest CPU/memory tier, small max-instances cap), **Neon Postgres**, and a **GCS bucket with a lifecycle delete rule**. Cloudflare Workers is not used in v1.
- Crustdata plan: sync endpoints available (identify, search, enrich, person search, job search, web_search_live, web_enrich_live, etc.); **batch endpoints and some person fields are not on the plan** — design around sync calls with bounded fan-out. ~15k credits; each case has a credit budget.
- LLM: **Anthropic Messages API called directly with the user's API key** (official `anthropic` Python SDK), so usage falls under the console category *"Agent SDK, API, Batch API, Playground, Managed Agents"*. Not Vertex, not Bedrock, not a Claude subscription. Default model **`claude-haiku-5-5`** (demo, keep it cheap); model id, max tokens and temperature are configurable via env (`ANTHROPIC_MODEL`, etc.) / a config file. One LLM client module, so every call goes through the same configuration and metering.
- Keys live in `.env` at the repo root (user adds `ANTHROPIC_API_KEY`, `CRUSTDATA_API_KEY`; email key later). `.env` is git-ignored; `.env.example` documents every variable. Deployed services read the same names from Secret Manager.
- Email: real sending, with `EMAIL_SEND_ENABLED` flag; when false (test mode) the send is recorded as "suppressed (test mode)" and nothing leaves.
- Project-local dependency installs approved; nothing global without asking.
- Confidential uploads: per-case only, never used for training, personal details not needed are stripped from stored text, deleted on a schedule together with every derivative (§7).

## 4. Approaches considered

| | Approach | Trade-off |
|---|---|---|
| **A (picked)** | **Next.js web app + Python FastAPI service + worker, both on Cloud Run; Postgres on Neon; GCS for uploads** | Long-running verification jobs fit Cloud Run (no 30s/CPU caps); Python gives clean deterministic rule code + tests and good PDF tooling; two deployables to manage. |
| B | All-TypeScript on Cloudflare Workers (Workflows/Durable Objects for jobs, D1 or Neon) | Great edge latency, but long multi-minute agent runs need Workflows/DO orchestration and PDF parsing is awkward in Workers; more novel infra risk for a demo. |
| C | Single Next.js full-stack app on Cloud Run doing jobs in route handlers | Fewest moving parts, but mixes long jobs into the web tier and makes resumability fragile. |

The user handed over the "how"; A is the pick because "picks up where it left off if interrupted" and multi-minute verification are the riskiest requirements, and A handles them with the least novel infrastructure.

## 5. Architecture

```
Browser ── Next.js (apps/web, Cloud Run) ──HTTPS/JSON+SSE── FastAPI (apps/api, Cloud Run)
                                                              │  ├─ job runner (same image, worker mode)
                                                              │  ├─ Crustdata REST client (cached, metered)
                                                              │  ├─ Anthropic client (usage-category tagged, metered)
                                                              │  └─ Email client (flag-gated, idempotent)
                                                              ├─ Neon Postgres (all state, versions, ledger)
                                                              └─ GCS bucket (uploads, lifecycle delete)
```

- Monorepo: `apps/web` (Next.js App Router, TypeScript, Tailwind, Framer Motion / Motion, shadcn-style primitives), `apps/api` (FastAPI, SQLAlchemy/SQLModel + Alembic, httpx, pydantic, pytest), `packages/` only if shared types are needed (OpenAPI-generated TS client from FastAPI).
- Config: local `.env` (git-ignored) for dev; GCP Secret Manager for deploys. Names: `CRUSTDATA_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (default `claude-haiku-5-5`), `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_SEND_ENABLED`, `DATABASE_URL`, `CASE_CREDIT_BUDGET`, `UPLOAD_RETENTION_DAYS`.
- Region: `asia-south1` (Mumbai) for Cloud Run + GCS; Neon in the nearest available region (Singapore / Mumbai if available).
- Auth: lightweight named users (needed for "named approver" and case authorization). Neon Auth or a simple email-link/session auth; builder's call, but every approval records user id, display name and timestamp.

### 5.0 Shared vocabulary (all code must use these values exactly)

| Enum | Values |
|---|---|
| Claim status | `supported`, `contradicted`, `partially_corroborated`, `conflicting_evidence`, `cannot_verify`, `not_checked` |
| Disposition | `prioritise`, `investigate_further`, `deprioritise`, `cannot_assess` |
| Criterion kind | `must`, `preference` |
| Criterion result | `pass`, `fail`, `unknown` |
| Identity | `confirmed`, `unresolved`, `ambiguous` |

Defined once in the API (Python enums + DB check constraints) and exported to the web app through the generated client. UI labels ("Partially corroborated", "Investigate further", …) are a display mapping over these values, never stored. Identity meanings: `confirmed` = one candidate backed by a corroborating identifier (§5.4); `ambiguous` = two or more plausible candidates; `unresolved` = no candidate, or a candidate without corroboration.

### 5.1 Jobs and resumability
- Every pipeline (discover, investor discover, verify, evaluate, recheck) is a **Run** made of **Steps** persisted in Postgres (`pending → running → done | failed | skipped_budget`).
- Each step is idempotent; external calls go through a request-hash cache table, so a resumed run replays cached Crustdata/LLM responses instead of re-paying. Cache entries whose inputs include private case text are scoped to that case (§7).
- Worker claims steps with `SELECT … FOR UPDATE SKIP LOCKED` and a lease. **Expired leases are reclaimed during normal operation**: every claim query also picks up `running` steps whose lease has expired, and a periodic sweep re-queues them — not only at boot (on a scale-to-zero Cloud Run service, boot may be rare). UI reconnects and shows the run continuing.
- **Call attempts are persisted before the call:** each external call writes a `call_attempt` row (`started`, with provider, request hash, case/run/step) before dispatch, then updates it to `succeeded | failed | unknown`. On resume, a `started` attempt with no result is reconciled (cache hit, provider lookup where one exists) before the call is retried.
- Progress streams to the UI via SSE (fallback: polling), so the demo shows the analyst "working" step by step.

### 5.2 Cost ledger
- Every Crustdata call records `credits_used` (returned per call) and every LLM call records input/output tokens and computed USD, keyed to case + run + step + call attempt.
- **Reconcile provider usage:** cost comes from the provider's own response (Crustdata `credits_used`, Anthropic `usage`). When the response is lost or lacks usage, the attempt's cost is stored as **unknown** — never as zero — and the UI shows "N credits + 1 call of unknown cost". Where the provider exposes a usage report, a reconciliation step compares totals and flags drift.
- **Every run has its own cost.** Discovery and investor-discovery runs show their cost on the run page. A case page shows "This case cost: N Crustdata credits, $X model usage" for its own runs; when the case was opened from a shortlist, the discovery cost is shown separately as "shared, from run X" and is **not** added to the case total (no double counting across the cases opened from one shortlist).
- Per-case credit budget (configurable, default e.g. 150 credits); when exhausted, remaining checks become `not_checked` with reason "budget reached".

### 5.3 Provenance model
Every fact displayed comes from an **Evidence** row → **Source** row:
- `Source`: provider (crustdata endpoint / web page / uploaded document / user-typed), request params or URL, retrieved_at, reliability class (registry, audited statement, counterparty confirmation, company announcement, professional-profile signal, news, seller document, seller statement), and **origin id**: syndicated or copied versions of the same announcement share one origin and count as one source for status rules.
- `Evidence`: source_id, the **exact evidence span** (quote with offsets/page, or field path + value), the **effective date** of the underlying fact (not just retrieval), the **entity** it is attached to and the identity basis for that attachment (§5.4), and the extraction it supports.
- `Claim`: keeps the **original assertion** verbatim (seller's wording, document, page) alongside its normalised atomic form.
- The UI renders a source chip + date on every fact; clicking opens the exact quote/field.

### 5.4 Identity guard (applies everywhere)
- **No attachment on name alone.** Every record attached to a company, person or investor — including records found after initial confirmation (people results, news articles, registry pages, funding rounds, investor records) — needs at least one corroborating identifier or distinguishing attribute matching the confirmed entity: domain, profile URL, Crustdata id, HQ city, founded year, registry id (e.g. CIN). Records without one are kept as *unattached candidates*, visible in the Sources tab, and never feed a status, criterion or memo line.
- **Manual identity pick shows its evidence.** When the user picks among candidates, the UI shows, per candidate, which identifiers matched and which did not; the pick records the user, timestamp and that evidence.
- **Ambiguous entities stay separate.** Possible duplicate companies, people with the same name, and investor names that may refer to different firms are flagged as possible duplicates, never merged without a shared identifier.
- **Identity-dependent conclusions are blocked while identity is not `confirmed`:** identity-dependent claim checks stay `not_checked` (reason "identity unresolved"), no fit score, business assessment or memo conclusion is issued, the disposition is `cannot_assess`, and the request list asks for what would resolve identity.

## 6. Pipelines

### 6.1 Discover (thesis → shortlist)
1. **Criteria extraction (LLM, structured output):** thesis → list of criteria, each `{label, kind: must|preference, dimension (geography, ownership, industry/activity, customer type, size, growth signal, funding stage, founded year…), operator, value, mapped Crustdata filter (if mappable) or "assessed from evidence"}`. Shown as editable chips/rows before search runs.
2. **Search:** Crustdata `company_search` combining structured filters with its natural-language `search` mode for activity description; widen with a second query if few results. Dedupe by Crustdata company id, then domain.
   - A must-have is pushed as a **hard provider filter only when its field is reliably populated** (builder keeps a documented list after checking real responses). Where the field may be missing (ownership, customer type, founded year, funding stage…), use an unknown-inclusive query (filter *or* field empty) if the provider supports it, otherwise a bounded supplemental search without that filter (capped result count), so companies with a missing field are not silently excluded.
3. **Must-have gate (rules):** each must-have evaluated tri-state `pass | fail | unknown` from fields. Only a verified `fail` removes a company. `unknown` keeps it and lowers *assessable %*, not fit.
4. **Enrich top N** (bounded, e.g. 15) with `company_enrich` (funding rounds + investors, headcount and its time series, locations, description, founded year) and `job_search` for hiring activity.
5. **Re-gate after enrichment, before ranking:** the must-have gate runs again on the enriched record. An `unknown` that enrichment resolves to `fail` removes the candidate; one that stays `unknown` survives with reduced coverage.
6. **Fit score (rules):** `fit = Σ weight(met preferences & must-haves) / Σ weight(assessable criteria) × 100`; `assessable% = assessable criteria / all criteria`. Displayed together always: "Fit 82 · 70% of criteria assessable". **When zero criteria are assessable, fit shows as "unavailable", not a number.** Ranking uses fit, ties broken by assessable%; candidates with fit unavailable rank last and say why.
7. **Shortlist card:** business, location, size + growth *estimates* (labelled), funding history, hiring activity, reasons for inclusion (which criteria met, with evidence), unknowns, source chip + last-updated on each item.

### 6.2 Discover investors
1. Business profile form: sector, location, stage, size, **kind of funding sought** (e.g. equity seed/venture/growth, debt).
2. Find comparable companies via `company_search` (industry/activity, geography, size band, funding stage) with funding data.
3. Read funding rounds (round type, date, investors) from enrich/search funding fields; keep only rounds with a date and named investor. **Personal contact fields (emails, phone numbers, personal profile links) are dropped at ingestion**, before anything is stored.
4. Group by investor under the identity guard (§5.4): merge only on a shared identifier (Crustdata investor id, domain) or exact normalised name *plus* a corroborating attribute; otherwise flag possible duplicates and keep them separate.
5. Rank (rules): count of comparable investments, recency-weighted. Ranking is described in the UI as **historical** ("ranked by comparable investments found in the record"), never as a likelihood of investing.
6. Entry: comparable companies backed + round + date (each with source), why they fit, unknowns, and:
   - **Funding-kind compatibility:** explained where dated records show the investor making rounds of the kind sought ("led 3 growth-equity rounds, latest 2025-08"); otherwise "compatibility with <kind> unknown".
   - **"Latest sector investment found: <date>"**, always with the search date and scope ("searched 2026-11-22 across 40 comparable companies") — never an absolute "last invested".
   - Any outreach draft requires approval (same Act machinery); v1 can stop at the shortlist + optional draft.

### 6.3 Verify (case)
Entry: from a shortlist item, or name + website directly. Optional deck/document uploads (PDF; also DOCX/PPTX→text if cheap) and typed claims.

1. **Identity (first, blocking):** `company_identify` (free) by domain, then name. If one match is backed by a corroborating identifier → `confirmed`, showing the matching keys (domain, profile URL, HQ, founded, registry id). Several plausible matches → `ambiguous`; no match or no corroboration, or a domain/name mismatch → `unresolved`. In either case the user picks with evidence shown (§5.4), or the case proceeds with identity-dependent conclusions blocked. Registry evidence (incorporation date/place, legal name, CIN) via `web_search_live` + `web_enrich_live` on public registry-mirroring pages, recorded with reliability "registry (secondary mirror)" unless the page is the official registry.
2. **Profile:** `company_enrich` by Crustdata id → business, industry, locations, founded, headcount + series, funding rounds, key people.
3. **Claim intake:** LLM extracts atomic factual claims from uploaded documents (`{original_text, normalised_text, category, quote, page}`), plus typed claims. Categories in v1: identity/incorporation, location, team size/growth, leadership & founder history, funding events, dated events (launches/expansions/facilities), customers/partnerships, financials, debt/security, litigation. Categories without a reliable v1 source still appear — as `cannot_verify` (with "what would settle it") or `not_checked` (with reason), never dropped.
4. **Evidence gathering per claim category** (bounded fan-out, budget-aware; web queries use public lookup terms only, §7):
   - team size → enrich headcount (signal) + time series
   - leadership/founders → `person_search` for people currently/previously at the *confirmed company id* in leadership titles; career history with dates; attach only with company id + name, never name alone
   - funding → enrich funding rounds + dated news via `web_search_live`
   - dated events → `web_search_live` (news) + `web_enrich_live` to read the article; record publish date and origin
   - incorporation/location → registry evidence from step 1 + enrich HQ
   - customers/partnerships, financials → web search where it can reach something; otherwise `cannot_verify` with the named document to request
   - debt/security, litigation → no dedicated check in v1 (Next); `cannot_verify` or `not_checked` with what would settle it
5. **Fact extraction (LLM) + validation (rules):** from each evidence text, extract structured facts relevant to the claim (e.g., `{founded_year: 2014, city: "Pune"}`, `{event: "new facility", stage: planned|operating, date}`), temperature 0, cached by (evidence hash, claim id). Each extraction carries the exact span it came from. **Decisive fields are validated against that span:** the value must appear in the span or be derivable from it by a deterministic transform (date formats, number/unit normalisation, name normalisation); otherwise the extraction is rejected and logged, and it never reaches the rules. Accepted extractions are versioned with the policy version and extractor (model + prompt) version.
6. **Status (rules):** each claim records **evidence adequacy** (was an adequate source class for this question reached and read?) and the **substantive result** (supports / conflicts / partial / silent) as separate fields; the status is derived from both by a per-category rule table. Evidence items sharing an origin collapse to one before rules run. Precedence, first match wins:
   1. `not_checked` — the check did not run (source unavailable, budget, error, identity unresolved). Rendered visually distinct from all clean outcomes.
   2. `conflicting_evidence` — adequate sources from different origins disagree.
   3. `contradicted` — an adequate, reliable source directly conflicts with the precise claim and none supports it.
   4. `supported` — adequate evidence directly supports every component.
   5. `partially_corroborated` — adequate evidence supports some components; others are unsupported (e.g., announced ≠ operating).
   6. `cannot_verify` — no adequate source class reachable, only inadequate sources (e.g., payroll count from profile estimates; "no debt" from a registered charge), or an adequate source was read and is silent. Silence is never contradiction. Always lists what would settle it.

   Fixtures (pytest) cover all six rows of the PRD's illustration plus: a **copied announcement** (three syndicated copies of one press release = one origin; cannot produce `conflicting_evidence` with each other or count as independent corroboration), **sources that disagree**, an **adequate source read but silent** (`cannot_verify`), and a **skipped check** (`not_checked`).
7. **Dated events timeline** and **comparable companies** (only fair peers, §6.6) are gathered alongside.

### 6.4 Evaluate (rules, versioned)
Five separate judgments, never blended:
- **Opportunity fit** — thesis fit score + assessable% (from 6.1, re-computed with case evidence); "unavailable" when zero criteria are assessable. **Direct Verify (no thesis):** claim checks run immediately; the case asks the user for strategy criteria before issuing any fit score, and fit shows "awaiting strategy criteria" until then.
- **Evidence sufficiency** — share of *required* checks (per company type) that reached a settled status; lists gaps. Evidence adequacy is reported separately from the substantive results.
- **Business assessment** — observable operating indicators (headcount trend, hiring, locations, dated expansions), labelled as signals.
- **Financial assessment** — shown only when reliable financial inputs exist (period, figures, assumptions, bounded conclusion; §6.6); otherwise "Not assessed — no reliable financial inputs" (v1 normally ends here).
- **Screening disposition** — four values, decided by these predicates in this precedence (first match wins):
  1. `cannot_assess` — identity is not `confirmed`, or essential information is too uncertain to judge (including fit unavailable or awaiting strategy criteria). Essential identity uncertainty overrides every other signal, including a must-have failure.
  2. `deprioritise` — a must-have has verifiably failed (`fail` on adequate evidence for the confirmed entity), or fit is below the poor-fit threshold *and* assessable% is at or above the good-evidence threshold. Missing evidence alone never reaches this row; a must-have with conflicting evidence is `unknown`, not `fail`.
  3. `prioritise` — fit at or above the strong-fit threshold, required checks satisfied (sufficiency complete within what v1 covers), and no material claim `contradicted` or `conflicting_evidence`.
  4. `investigate_further` — everything else (attractive but incomplete, or open contradictions).

  Thresholds live in the visible scoring policy. Tests cover each predicate and the conflicts between them: identity ambiguous + must-have fail → `cannot_assess`; must-have fail + high fit → `deprioritise`; poor fit on thin evidence → `investigate_further`; high fit + a contradicted claim → `investigate_further`; conflicting signals on a must-have → not `deprioritise`; zero assessable criteria → `cannot_assess` with fit "unavailable".

Company-type profile chosen by rule (founded year, headcount, funding stage): **startup** criteria (thesis fit, founder relevance, team development, funding history) vs **established** (strategic fit, identity, operating scale, financial performance, commercial position, leadership continuity).

Each evaluation is an immutable **AssessmentVersion** (policy version, inputs snapshot hash, accepted-extraction versions, judgments, disposition, reasons). Re-evaluation creates a new version with a computed diff ("Claim 'opened facility Oct 2026' moved Partially corroborated → Supported because <document, page>; disposition Investigate further → Prioritise").

### 6.5 Act
1. **Request list (rules):** built from **unresolved questions** and the evidence each needs, not from status alone. Sources of questions:
   - claims in `cannot_verify`, `partially_corroborated`, `conflicting_evidence`, and `contradicted` where the seller can respond;
   - seller-resolvable gaps regardless of status: identity ambiguity (certificate of incorporation / CIN), missing financial inputs (audited statements, management accounts), and `not_checked` checks a document could resolve;
   - each question maps to the specific document that would settle it (category → document table, e.g. team size → dated payroll summary; debt → lender statements; facility → lease/occupancy evidence).
   Documents are **deduplicated** (one payroll summary covers team size and team growth), and each requested document links to the questions it resolves. **Analyst-side retries** (budget reached, provider error, source unavailable) are listed separately as "to re-run" and never sent to the seller.
2. **Draft (LLM):** one consolidated, polite request email to the seller from the list; editable.
3. **Approve:** a named signed-in user approves a specific **immutable message revision** (body + recipient + subject, stored with a content hash). Recipient address entered by the user (DealProof does not scrape contact details). Any edit creates a new revision and requires fresh approval; an approval never carries over to edited content.
4. **Send once:**
   - Status: `draft → approved → sending → sent | suppressed_test_mode | failed | unknown`.
   - A **send key** (request id + approved revision id) is persisted with a unique constraint *before* dispatch and passed to the email provider as its idempotency key. Two concurrent send requests resolve to one dispatch.
   - On an unknown outcome (timeout, lost response), the system **reconciles with the provider** (lookup by idempotency key / message id) before any resend; a resend, if any, reuses the same send key.
   - With `EMAIL_SEND_ENABLED=false`, status becomes `suppressed_test_mode` and the UI says so plainly. Metrics count **real provider acceptance** (`sent`) separately from test-mode suppression; a suppressed send is never shown or counted as sent.
   - Tests: concurrent sends (exactly one dispatch), a lost provider response after acceptance (reconciled to `sent`, no second dispatch), an edit after approval (send refused until re-approved).
5. **Seller documents arrive (built late, §10):** uploaded to the same case (v1: manual upload; inbound email parsing not required) → claim extraction on the new docs → affected claims re-checked → new AssessmentVersion with diff shown; earlier version kept and viewable.

### 6.6 The finished case (memo)
A case page that reads in minutes and audits in full: opportunity & thesis relevance; confirmed identity/profile; claim ledger; dated events; comparables (where fair); financial evaluation (where inputs exist); risks/assumptions/unknowns; recommended next step + reasons; request list; full source record (reproducible: every request/URL + retrieved_at). Print-friendly CSS for PDF export via the browser.
- **Comparables:** only fair peers. The section states the shared comparison basis (same activity + region + size band, with the values) and gives a sourced, dated observation for each company. No fair peer → "No fair comparison found" with the basis tried.
- **Financials:** when reliable financials are supplied, show the period, the figures (each cited), the assumptions, and a bounded conclusion ("on these statements, FY25 revenue grew 18%"), never a valuation.
- **Citations:** every memo assertion traces to accepted facts. Each citation links to the exact evidence excerpt or the versioned field it used. A post-draft check rejects memo sentences whose figures, dates or names are not in a cited accepted fact. Subject to retention: a citation to a deleted excerpt shows its deletion record (§7).

## 7. Confidentiality
- **Case authorization everywhere:** every read path for files, evidence, quotes, cache entries and exports (memo print view, source record) checks that the signed-in user has access to the case. GCS objects are reached only through short-lived, case-scoped signed URLs. Cache entries whose request includes private case text are keyed by case and never served to another case; only public-lookup calls share cache.
- Uploads go to a private GCS bucket under `cases/<case_id>/`; a lifecycle rule deletes them after a configured period (default 30 days), and the case shows the deletion date.
- **Minimise before external processing:** text is PII-stripped (regex for emails/phones/IDs + LLM-assisted redaction of personal details not needed for the claims) before storage, and LLM calls receive only the excerpts a step needs. **Web search queries are built from public lookup terms only** — company name, domain, people names — through a query builder with an allowlist; confidential claim text never goes into a search query (tested).
- **Retention covers derivatives:** the deletion schedule applies to extracted text, stored quotes from uploads, cached LLM requests/responses containing upload text, and assessment input snapshots, through a scheduled DB sweep alongside the GCS lifecycle rule. Neon history retention is set no longer than the retention period.
- **Dated deletion record:** each deletion writes `{case, artifact kind, artifact id, original filename, deleted_at, reason}` so an older AssessmentVersion can explain "Attachment 'deck.pdf' deleted 2026-12-22 under the 30-day retention schedule" instead of a broken link.
- Anthropic API calls only (no training on API data); documents are never shared across workspaces/cases.

## 8. UI / UX (direction owned by Fable design agents)
Pages:
- **Home (marketing):** inspired by sarvam.ai home; explains Discover → Verify → Evaluate → Act; clearly labelled illustration of a claim ledger; CTA into the app.
- **App:** cases dashboard; New thesis (criteria editor → live search progress → shortlist); Investor discovery; Case view (Overview/memo, Identity, Claims ledger, Events, Comparables, Assessment + history, Request & approval, Sources, Cost).

Decisions with the owner:
- **Light theme only.**
- **Interaction sounds off by default**, with a toggle for the demo.
- **Status colours:** Deprioritise is shown in graphite; red is reserved for Contradicted.
- **Page copy** lives in `docs/content/` and is written by a Gemini Neon agent; UI code reads from it rather than inventing copy.

Rules for designers: use the `unslop` skill on every UI pass; one design system (tokens, type scale, spacing, status palette) used everywhere; statuses use colour **and** text/shape (never colour alone); "Not checked" visually distinct from every clean status; estimates visibly labelled; fit "unavailable" never rendered as a number; source chip + date pattern consistent everywhere; motion purposeful (run progress, ledger reveal, assessment diff), respecting reduced-motion.

## 9. Testing
- Rules engine (fit incl. "unavailable", must-have tri-state, claim status precedence per category, extraction-span validation, sufficiency, disposition precedence, diffs) — pytest, including the PRD illustration and the §6.3/§6.4 fixtures.
- Discover gate: an `unknown` must-have survives with reduced coverage; a later verified `fail` after enrichment removes the candidate.
- Identity: name-only matches are not attached (company, person, investor); ambiguous candidates stay separate; unresolved identity blocks fit/disposition.
- Act: concurrent sends, lost provider response, edit-after-approval, test-mode suppression counted separately.
- Confidentiality: cross-case access denied for files/evidence/cache/exports; search queries contain no claim text; retention sweep deletes derivatives and writes deletion records.
- Resume/cost: expired lease reclaimed without restart; `started` call attempt reconciled before retry; unknown cost shown as unknown; shared discovery cost not double-counted.
- Crustdata and Anthropic clients behind interfaces with recorded fixtures for tests; a small live smoke test gated by env.
- Web: Playwright smoke over the main path; Gemini Neon / Terra-driven browser passes at milestones.

## 10. Delivery process (agreed with user)
- Small checkpoints; commit + push to `main` on GitHub after each.
- At each checkpoint, GPT-6.2 Sol reviews the code while the next worker starts; GPT-6.2 Astra reviews product adherence/ideation (not code); occasional Gemini 4 Neon end-to-end pass.
- Design/UI/UX work only by Fable subagents; implementation by Opus subagents; page copy by a Gemini Neon agent into `docs/content/`.

Proposed checkpoint order (refined in the implementation plan):
1. Repo scaffold, CI, design system foundations (tokens, primitives) — Fable on design system in parallel with Opus scaffold.
2. API skeleton: DB schema (shared enums §5.0), runs/steps/resume with lease reclaim, call attempts, cost ledger, Crustdata + Anthropic clients with case-scoped cache.
3. Discover pipeline + rules + tests.
4. Verify: identity guard + profile + claim intake + evidence + extraction validation + status rules + tests.
5. Evaluate + versioning + diffs.
6. Act: request list, draft, revision-bound approval, send-once.
7. Investor discovery.
8. Web: home page; app shell; discover UI; case UI; investor UI (Fable-led, parallel tracks).
9. Re-check on seller documents: new AssessmentVersion + visible diff (late, per owner).
10. Deploy to Cloud Run (asia-south1) + Neon + GCS (lifecycle rule) + Secret Manager; end-to-end demo run on the logistics thesis.
11. Polish pass (unslop, motion, copy), final reviews.

## 11. Left to the builder
Exact libraries within the chosen stack, schema column details, retry/backoff policy, auth implementation, rule weights and disposition thresholds (must be documented in a visible "scoring policy" page/section), the list of reliably populated Crustdata fields usable as hard filters, Crustdata query shapes (verify against `get_schema` / docs), per-case budget default.

## 12. Open items awaiting the user
- User adds `ANTHROPIC_API_KEY` and `CRUSTDATA_API_KEY` to `.env`.
- Email provider key (Resend proposed; it must accept an idempotency key) + a verified sender address; until then `EMAIL_SEND_ENABLED=false`.

## Review changes (2026-11-22, product-adherence review by GPT-6.2 Astra)
1. **Identity:** new §5.4 identity guard — corroborating identifier for every attached record, including later ones; evidence shown for manual picks; ambiguous entities/people/investors kept separate; identity-dependent conclusions blocked. Identity enum added.
2. **Confidentiality:** §7 adds case authorization on files/evidence/caches/exports, minimisation before external processing, public-terms-only web queries, retention for derivatives, dated deletion records.
3. **Send once:** §6.5 binds approval to an immutable message revision, persists a send key used as the provider idempotency key, reconciles unknown outcomes, tests concurrency and lost responses, counts provider acceptance apart from test-mode suppression.
4. **Scope:** re-check on seller documents kept in v1 (owner's call; PRD Act section and final aim), built late (§10 step 9); dedicated security-interest and litigation checks deferred to Next with those claims still in the ledger; marketing home page stays.
5. **Dispositions:** evidence adequacy separate from substantive result; disposition predicate precedence specified and tested; fit "unavailable" at zero assessable criteria; direct Verify asks for strategy criteria before any fit score.
6. **Status rules:** provenance keeps original assertion, evidence span, entity, effective date, origin; decisive extracted fields validated against the span; extractions versioned; status precedence with fixtures (copied announcement, disagreement, silent adequate source, skipped check); memo assertions trace to accepted facts.
7. **Discover gate:** no hard provider filters on fields that may be missing; unknown-inclusive or bounded supplemental search; gate reapplied after enrichment and before ranking, with tests.
8. **Request list:** built from unresolved questions, includes seller-resolvable gaps regardless of status, separates analyst retries, deduplicates documents and links each to its questions.
9. **Investors:** funding kind sought drives compatibility (or "unknown"); "latest sector investment found" with search date and scope; ranking described as historical; personal contact fields dropped at ingestion.
10. **Finished case:** fair peers with shared basis and sourced observations; bounded financial conclusion with period/figures/assumptions; citations to exact excerpts or versioned fields, subject to retention.
11. **Resume and cost:** lease reclaim during normal operation; call attempts persisted before calls; provider usage reconciled, unknown costs explicit; per-run costs, with shared discovery cost shown once and not double-counted.

Owner decisions recorded: light theme only; sounds off by default with a demo toggle; Deprioritise in graphite (red only for Contradicted); page copy in `docs/content/` by a Gemini Neon agent; Cloud Run asia-south1 at the smallest size with Neon Postgres and a GCS bucket with a lifecycle rule; direct Anthropic API with `claude-haiku-5-5` by default; shared enum values (§5.0).
