# DealProof v1 (ContextCon) — design

Status: draft for approval (Anthropic: direct API, Haiku 5.5 default) · 2026-11-22
Source of truth for *what* to build: `DealProof product description.md` (the PRD). This doc decides *how*. Where this doc and the PRD disagree, the PRD wins.

## 1. Intent

Build the PRD's **"First version, at ContextCon"** row, completely, as a deployed web app:

- Thesis → shortlist of real companies (Discover), with editable must-haves / preferences.
- Business profile → shortlist of investors backed by dated funding records (Discover investors).
- Confirm a company's identity; check claims about team, leadership, funding and dated events (Verify).
- Show fit and evidence side by side, five separate judgments, one of four dispositions (Evaluate).
- Prepare the seller request, approve by a named person, send once (Act). Seller documents re-attach to the case and re-check affected claims, keeping prior assessment versions.
- Resume interrupted work; record what each case cost.

It is a hackathon demo, so presentation is a first-class requirement: the UI must make "claims vs evidence", "fit vs evidence sufficiency", and "cannot verify / not checked" instantly legible to a judge who has never seen the product.

## 2. Goals / non-goals / anti-goals

**Goals**
- Every visible fact carries a source and an as-of date (PRD principle 1).
- Deterministic rules decide statuses, fit, sufficiency and disposition (principle 6). The LLM only *extracts* (criteria from a thesis, atomic claims from a deck, structured facts from evidence text) and *drafts* (memo prose, seller email).
- Live data from Crustdata for companies, people, funding, headcount, hiring, and live web/news search/fetch.
- Professional, consistent, animated UI built with the `unslop` skill; inspiration from dealroom.co, dealroom.net, sarvam.ai (home page) and the user's component-site list.

**Non-goals (v1)** — straight from the PRD's "Next/Later" rows: cross-document consistency checks between seller documents, peer benchmarking as a scored feature, multi-target comparison, financial scenarios, monitoring/alerts, deal tracking, data-room/CRM integrations. (A simple "comparable companies" list *is* in the finished-case contents, shown "where a fair comparison exists"; it is informational, not scored.)

**Anti-goals** (failure even if it "works")
- Any fact rendered without a source/date, or produced from model memory.
- Headcount/hiring treated as revenue or as proof of payroll.
- Records attached by name match alone.
- Missing evidence lowering fit or causing "Deprioritise".
- "Not checked" rendered like a clean result.
- An email leaving without a named approver, or leaving twice.
- Fabricated example companies presented as real. (The PRD's Pune example may appear only as a clearly labelled illustration.)
- Changing the product idea.

## 3. Constraints

- Hosting: GCP project `cc-g527-showproduct` (gcloud authenticated) and/or Cloudflare Workers (wrangler install approved).
- Crustdata plan: sync endpoints available (identify, search, enrich, person search, job search, web_search_live, web_enrich_live, etc.); **batch endpoints and some person fields are not on the plan** — design around sync calls with bounded fan-out. ~15k credits; each case has a credit budget.
- LLM: **Anthropic Messages API called directly with the user's API key** (official `anthropic` Python SDK), so usage falls under the console category *"Agent SDK, API, Batch API, Playground, Managed Agents"*. Not Vertex, not Bedrock, not a Claude subscription. Default model **`claude-haiku-5-5`** (demo, keep it cheap); model id, max tokens and temperature are configurable via env (`ANTHROPIC_MODEL`, etc.) / a config file. One LLM client module, so every call goes through the same configuration and metering.
- Keys live in `.env` at the repo root (user adds `ANTHROPIC_API_KEY`, `CRUSTDATA_API_KEY`; email key later). `.env` is git-ignored; `.env.example` documents every variable. Deployed services read the same names from Secret Manager.
- Email: real sending, with `EMAIL_SEND_ENABLED` flag; when false (test mode) the send is recorded as "suppressed (test mode)" and nothing leaves.
- Project-local dependency installs approved; nothing global besides wrangler without asking.
- Confidential uploads: per-case only, never used for training, personal details not needed are stripped from stored text, deleted on a schedule.

## 4. Approaches considered

| | Approach | Trade-off |
|---|---|---|
| **A (picked)** | **Next.js web app + Python FastAPI service + worker, both on Cloud Run; Postgres on Neon; GCS for uploads** | Long-running verification jobs fit Cloud Run (no 30s/CPU caps); Python gives clean deterministic rule code + tests and good PDF tooling; two deployables to manage. |
| B | All-TypeScript on Cloudflare Workers (Workflows/Durable Objects for jobs, D1 or Neon) | Great edge latency, but long multi-minute agent runs need Workflows/DO orchestration and PDF parsing is awkward in Workers; more novel infra risk for a demo. |
| C | Single Next.js full-stack app on Cloud Run doing jobs in route handlers | Fewest moving parts, but mixes long jobs into the web tier and makes resumability fragile. |

The user handed over the "how"; A is the pick because "picks up where it left off if interrupted" and multi-minute verification are the riskiest requirements, and A handles them with the least novel infrastructure. Cloudflare can still front the web app later if wanted.

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
- Region: `asia-south1` (Mumbai) for Cloud Run + GCS; Neon in nearest AWS/Azure region (Singapore / Mumbai if available).
- Auth: lightweight named users (needed for "named approver"). Neon Auth or a simple email-link/session auth; builder's call, but every approval records user id, display name and timestamp.

### 5.1 Jobs and resumability
- Every pipeline (discover, investor discover, verify, evaluate, recheck) is a **Run** made of **Steps** persisted in Postgres (`pending → running → done | failed | skipped_budget`).
- Each step is idempotent; external calls go through a request-hash cache table, so a resumed run replays cached Crustdata/LLM responses instead of re-paying.
- Worker claims steps with `SELECT … FOR UPDATE SKIP LOCKED`; on boot it re-queues `running` steps whose lease expired. UI reconnects and shows the run continuing.
- Progress streams to the UI via SSE (fallback: polling), so the demo shows the analyst "working" step by step.

### 5.2 Cost ledger
Every Crustdata call records `credits_used` (returned per call) and every LLM call records input/output tokens and computed USD, keyed to case + run + step. Case page shows "This case cost: N Crustdata credits, $X model usage". Per-case credit budget (configurable, default e.g. 150 credits); when exhausted, remaining checks become **Not checked** with reason "budget reached".

### 5.3 Provenance model
Every fact displayed comes from an **Evidence** row → **Source** row:
- `Source`: provider (crustdata endpoint / web page / uploaded document / user-typed), request params or URL, retrieved_at, reliability class (registry, audited statement, counterparty confirmation, company announcement, professional-profile signal, news, seller document, seller statement).
- `Evidence`: source_id, exact quote or field path + value, as_of date of the underlying fact (not just retrieval), and which entity it was attached to (with identity confidence).
The UI renders a source chip + date on every fact; clicking opens the exact quote/field.

## 6. Pipelines

### 6.1 Discover (thesis → shortlist)
1. **Criteria extraction (LLM, structured output):** thesis → list of criteria, each `{label, kind: must|preference, dimension (geography, ownership, industry/activity, customer type, size, growth signal, funding stage, founded year…), operator, value, mapped Crustdata filter (if mappable) or "assessed from evidence"}`. Shown as editable chips/rows before search runs.
2. **Search:** Crustdata `company_search` combining structured filters (from mappable must-haves) with its natural-language `search` mode for activity description; widen with a second query if few results. Dedupe by Crustdata company id, then domain.
3. **Must-have gate (rules):** each must-have evaluated tri-state `pass | fail | unknown` from fields. Only verifiable `fail` removes a company. `unknown` keeps it and lowers *assessable %*, not fit.
4. **Enrich top N** (bounded, e.g. 15) with `company_enrich` (funding rounds + investors, headcount and its time series, locations, description, founded year) and `job_search` for hiring activity.
5. **Fit score (rules):** `fit = Σ weight(met preferences & must-haves) / Σ weight(assessable criteria) × 100`; `assessable% = assessable criteria / all criteria`. Displayed together always: "Fit 82 · 70% of criteria assessable". Ranking uses fit, ties broken by assessable%.
6. **Shortlist card:** business, location, size + growth *estimates* (labelled), funding history, hiring activity, reasons for inclusion (which criteria met, with evidence), unknowns, source chip + last-updated on each item.

### 6.2 Discover investors
1. Business profile form: sector, location, stage, size, funding sought.
2. Find comparable companies via `company_search` (industry/activity, geography, size band, funding stage) with funding data.
3. Read funding rounds (round type, date, investors) from enrich/search funding fields; keep only rounds with a date and named investor.
4. Group by investor (normalized name; identity-guarded — merge only on id/exact normalized name, flag possible duplicates rather than merging).
5. Rank (rules): count of comparable investments, recency-weighted; show last sector investment date.
6. Entry: comparable companies backed + round + date (each with source), why they fit, unknowns. No personal contact details collected. Any outreach draft requires approval (same Act machinery); v1 can stop at the shortlist + optional draft.

### 6.3 Verify (case)
Entry: from a shortlist item, or name + website directly. Optional deck/document uploads (PDF; also DOCX/PPTX→text if cheap) and typed claims.

1. **Identity (first, blocking):** `company_identify` (free) by domain, then name. If one confident match → confirm and show the matching keys (domain, profile URL, HQ, founded). If several plausible matches or mismatch between domain and name → **identity unresolved**: user picks, or case proceeds as "Cannot assess" for identity-dependent checks. Registry evidence (incorporation date/place, legal name, CIN) via `web_search_live` + `web_enrich_live` on public registry-mirroring pages, recorded with reliability "registry (secondary mirror)" unless the page is the official registry.
2. **Profile:** `company_enrich` by Crustdata id → business, industry, locations, founded, headcount + series, funding rounds, key people.
3. **Claim intake:** LLM extracts atomic factual claims from uploaded documents (`{text, category, quote, page}`), plus typed claims. Categories in v1: identity/incorporation, location, team size/growth, leadership & founder history, funding events, dated events (launches/expansions/facilities), customers/partnerships, financials, debt/security. Categories without a reliable v1 source still appear — as **Cannot verify** (with "what would settle it") or **Not checked** (with reason), never dropped.
4. **Evidence gathering per claim category** (bounded fan-out, budget-aware):
   - team size → enrich headcount (signal) + time series
   - leadership/founders → `person_search` for people currently/previously at the *confirmed company id* in leadership titles; career history with dates; match by company id + name, never name alone
   - funding → enrich funding rounds + dated news via `web_search_live`
   - dated events → `web_search_live` (news) + `web_enrich_live` to read the article; record publish date
   - incorporation/location → registry evidence from step 1 + enrich HQ
   - customers/partnerships, debt/charges, litigation, financials → web search where it can reach something; otherwise Cannot verify with the named document to request
5. **Fact extraction (LLM):** from each evidence text, extract structured facts relevant to the claim (e.g., `{founded_year: 2014, city: "Pune"}`, `{event: "new facility", stage: planned|operating, date}`), temperature 0, cached by (evidence hash, claim id).
6. **Status (rules):** a per-category rule table compares claim facts to evidence facts + source reliability:
   - Supported: adequate source class for this question directly matches.
   - Contradicted: reliable source directly conflicts with the precise claim.
   - Partially corroborated: some components match, others unsupported (e.g., announced ≠ operating).
   - Conflicting evidence: relevant sources disagree.
   - Cannot verify: no adequate source class reachable (e.g., payroll count from profile estimates; "no debt" from a registered charge); always lists what would settle it.
   - Not checked: step skipped (source unavailable, budget, error) — rendered visually distinct from all clean outcomes.
   Rule examples are encoded as unit tests, including all six rows of the PRD's illustration.
7. **Dated events timeline** and **comparable companies** (where a fair comparison exists: same activity + region + size band) are gathered alongside.

### 6.4 Evaluate (rules, versioned)
Five separate judgments, never blended:
- **Opportunity fit** — thesis fit score + assessable% (from 6.1, re-computed with case evidence).
- **Evidence sufficiency** — share of *required* checks (per company type) that reached a settled status; lists gaps.
- **Business assessment** — observable operating indicators (headcount trend, hiring, locations, dated expansions), labelled as signals.
- **Financial assessment** — shown only when reliable financial inputs exist; otherwise "Not assessed — no reliable financial inputs" (v1 normally ends here).
- **Screening disposition** — rule table exactly as PRD: Prioritise / Investigate further / Deprioritise / Cannot assess. Missing evidence alone never yields Deprioritise.

Company-type profile chosen by rule (founded year, headcount, funding stage): **startup** criteria (thesis fit, founder relevance, team development, funding history) vs **established** (strategic fit, identity, operating scale, financial performance, commercial position, leadership continuity).

Each evaluation is an immutable **AssessmentVersion** (policy version, inputs snapshot hash, judgments, disposition, reasons). Re-evaluation creates a new version with a computed diff ("Claim 'opened facility Oct 2026' moved Partially corroborated → Supported because <document, page>; disposition Investigate further → Prioritise").

### 6.5 Act
1. **Request list (rules):** every claim in Cannot verify / Partially corroborated / Conflicting maps to the specific document that would settle it (category → document table, e.g. team size → dated payroll summary; debt → lender statements; facility → lease/occupancy evidence).
2. **Draft (LLM):** one consolidated, polite request email to the seller from the list; editable.
3. **Approve:** a named signed-in user approves; stored with name + timestamp. Recipient address entered by the user (DealProof does not scrape contact details).
4. **Send once:** idempotency key per request; status `draft → approved → sent | suppressed_test_mode | failed`. A second send is impossible (DB unique constraint + UI). With `EMAIL_SEND_ENABLED=false`, status becomes `suppressed_test_mode` and the UI says so plainly.
5. **Seller documents arrive:** uploaded to the same case (v1: manual upload; inbound email parsing not required) → claim extraction on the new docs → affected claims re-checked → new AssessmentVersion with diff shown; earlier version kept and viewable.

### 6.6 The finished case (memo)
A case page that reads in minutes and audits in full: opportunity & thesis relevance; confirmed identity/profile; claim ledger; dated events; comparables (where fair); financial evaluation (where inputs exist); risks/assumptions/unknowns; recommended next step + reasons; request list; full source record (reproducible: every request/URL + retrieved_at). Print-friendly CSS for PDF export via the browser.

## 7. Confidentiality
- Uploads go to a private GCS bucket under `cases/<case_id>/`, lifecycle rule deletes after a configured period (default 30 days), and the case shows the deletion date.
- Extracted text is stored after a PII-stripping pass (regex for emails/phones/IDs + LLM-assisted redaction of personal details not needed for the claims).
- Anthropic API calls only (no training on API data); documents are never shared across workspaces/cases.

## 8. UI / UX (direction owned by Fable design agents)
Pages:
- **Home (marketing):** inspired by sarvam.ai home; explains Discover → Verify → Evaluate → Act; clearly labelled illustration of a claim ledger; CTA into the app.
- **App:** cases dashboard; New thesis (criteria editor → live search progress → shortlist); Investor discovery; Case view (Overview/memo, Identity, Claims ledger, Events, Comparables, Assessment + history, Request & approval, Sources, Cost).
Rules for designers: use the `unslop` skill on every UI pass; one design system (tokens, type scale, spacing, status palette) used everywhere; statuses use colour **and** text/shape (never colour alone); "Not checked" visually distinct from every clean status; estimates visibly labelled; source chip + date pattern consistent everywhere; motion purposeful (run progress, ledger reveal, assessment diff), respecting reduced-motion.

## 9. Testing
- Rules engine (fit, must-have tri-state, claim status per category, sufficiency, disposition, diffs) — pytest, including the PRD illustration as a fixture.
- Crustdata and Anthropic clients behind interfaces with recorded fixtures for tests; a small live smoke test gated by env.
- Web: Playwright smoke over the main path; Gemini Neon / Terra-driven browser passes at milestones.

## 10. Delivery process (agreed with user)
- Small checkpoints; commit + push to `main` on GitHub after each.
- At each checkpoint, GPT-6.2 Sol reviews the code while the next worker starts; GPT-6.2 Astra reviews product adherence/ideation (not code); occasional Gemini 4 Neon end-to-end pass.
- Design/UI/UX work only by Fable subagents; implementation by Opus subagents.

Proposed checkpoint order (refined in the implementation plan):
1. Repo scaffold, CI, design system foundations (tokens, primitives) — Fable on design system in parallel with Opus scaffold.
2. API skeleton: DB schema, runs/steps/resume, cost ledger, Crustdata + Anthropic clients with cache.
3. Discover pipeline + rules + tests.
4. Verify: identity + profile + claim intake + evidence + status rules + tests.
5. Evaluate + versioning + diffs.
6. Act: request list, draft, approval, send-once, recheck on upload.
7. Investor discovery.
8. Web: home page; app shell; discover UI; case UI; investor UI (Fable-led, parallel tracks).
9. Deploy to Cloud Run + Neon + GCS + Secret Manager; end-to-end demo run on the logistics thesis.
10. Polish pass (unslop, motion, copy), final reviews.

## 11. Left to the builder
Exact libraries within the chosen stack, schema column details, retry/backoff policy, auth implementation, rule weights (must be documented in a visible "scoring policy" page/section), Crustdata query shapes (verify against `get_schema` / docs), per-case budget default.

## 12. Open items awaiting the user
- User adds `ANTHROPIC_API_KEY` and `CRUSTDATA_API_KEY` to `.env`.
- Email provider key (Resend proposed) + a verified sender address; until then `EMAIL_SEND_ENABLED=false`.
