# DealProof v1 (ContextCon) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan checkpoint by checkpoint. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy the PRD's "First version, at ContextCon" row: thesis → shortlist, business → investor shortlist, identity-first verification with a claim ledger, five separate rule-based judgments with a disposition, an approved send-once seller request, and re-checks that keep earlier assessment versions. Every case is resumable and records what it cost.

**Architecture:** Next.js App Router web app (`apps/web`) talks only to its own `/api/*` proxy route, which forwards to a FastAPI service (`apps/api`). The API runs the pipelines as persisted Runs/Steps in Neon Postgres, with an in-process worker. All external calls (Crustdata REST, Anthropic Messages API, Resend) go through metered, cached clients. Deterministic rule modules decide every status, score and disposition. The LLM only extracts and drafts. Both services run on Cloud Run (`asia-south1`). Uploads go to GCS, and deployed secrets come from Secret Manager.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2 (async, psycopg 3), Alembic, httpx, pydantic v2 / pydantic-settings, `anthropic` SDK, pytest. Next.js 16 App Router, React 19, TypeScript, Tailwind, Motion, `openapi-typescript`. Neon Postgres, GCS, Secret Manager, Cloud Build, Cloud Run.

**Spec:** `docs/superpowers/specs/2026-11-22-dealproof-v1-design.md` (HOW) and `DealProof product description.md` (WHAT; the PRD wins any disagreement). Every worker reads both before starting.

---

## Process rules (every worker reads this first)

1. **Small checkpoints.** One checkpoint = one worker = one commit that is pushed to `main`. Commit protocol at the end of every checkpoint:
   ```bash
   git add <only the paths this checkpoint owns>
   git commit -m "<type>: <checkpoint id> <summary>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"   # use your own model's attribution line
   git pull --rebase origin main
   <re-run this checkpoint's verification commands>
   git push origin main
   ```
   Several agents share one checkout. If `index.lock` exists, wait a few seconds and retry. Never `git add -A`. Never touch files owned by another in-flight checkpoint.
2. **Review at every checkpoint.** When a checkpoint is pushed, a **GPT-6.2 Sol** agent code-reviews that commit while the next worker starts. Sol findings become a fix-up commit by the original owner type before the dependent checkpoint merges. **GPT-6.2 Astra** reviews product adherence (PRD fit, not code) at the end of each phase. A **Gemini 4 Neon** agent may do an occasional independent end-to-end pass.
3. **Fable owns all design, UI and UX.** Any checkpoint marked `Fable design` goes to a Fable (`claude-fable-5-2`) agent. Opus agents never make visual or layout decisions: if a backend change needs UI, they leave a note for Fable. Implementation, infra, pipelines and rules are `Opus implementation` (`claude-opus-5-5`).
4. **UI passes use the `unslop` skill, every time.** Inspiration: dealroom.co, dealroom.net, and the sarvam.ai home page. Follow `docs/design/` (written by checkpoint 0b) as the source of truth for tokens and direction.
5. **Browser and computer use** (Playwright debugging by hand, visual checks, the demo walkthrough) runs on **GPT-6.1 Terra at medium or high reasoning effort, normal speed only** (never fast mode), per the user's global instructions.
6. **Secrets.** Never read, print or commit `.env`. Refer to variable names only. Scripts that load secrets do it with `set -a; source .env; set +a` inside the script and never echo values.
7. **Installs.** Project-local `uv add` / `pnpm add` are pre-approved. Anything global, Homebrew, browser binaries (e.g. `playwright install`) or uncached `npx`/`uvx` tools need the user's explicit OK first: stop and ask. Subagents inherit this rule. Do not use LibreOffice.
8. **No fabricated companies.** Fixtures use obviously fictional names that end in "(fixture)". The PRD's Pune example may appear only as a labelled illustration. Production builds never load fixtures.
9. **Crustdata credits are real money** (about 15.2k credits on the account). Unit tests use recorded fixtures. Live calls happen only in gated smoke tests (`RUN_LIVE_SMOKE=1`) and in the demo checkpoints.
10. **Dependency and migration serialisation.** CP-01 adds every planned backend dependency and CP-09 adds the planned web dependencies. If a later checkpoint must add a dependency, it must be the only dependency change in flight: after the rebase, run `uv lock` / `pnpm install` again and commit the lockfile. Only CP-02 creates the initial Alembic revision. Any later revision must be the only migration in flight, and its `down_revision` must equal the current head after the rebase.

---

## Open questions for the user (not blocking; defaults in force)

| # | Question | Default we proceed with |
|---|---|---|
| Q1 | Is simple email + password sign-in OK for named approvers? There is no public sign-up: accounts are created with a CLI. | Yes. Argon2-hashed passwords, a signed session cookie, and accounts made with `python -m app.cli create-user`. |
| Q2 | Which verified Resend sender address and domain should we use? | `EMAIL_SEND_ENABLED=false` until one is provided. Every send is recorded as "suppressed (test mode)". |
| Q3 | Is a per-case Crustdata budget of 150 credits OK, with 60 for each discover run and 60 for each investor search? | Yes. Configurable through `CASE_CREDIT_BUDGET`, `DISCOVER_CREDIT_BUDGET` and `INVESTOR_CREDIT_BUDGET`. |
| Q4 | Do you need a custom domain, or are the default `*.run.app` URLs fine for the demo? | Default `run.app` URLs. |
| Q5 | Should the PRD's Pune illustration appear only on the marketing page, or also as a read-only, clearly labelled sample case inside the app? | Marketing page only, labelled "Illustration, not a real company". |
| Q6 | Should the app be public, with anyone holding the URL able to reach the sign-in page, or IP/allow-listed? | Public sign-in page; everything behind sign-in except the marketing page. |

---

## Builder calls (design gaps I settled; reviewers check against these)

1. **No `temperature` on LLM calls.** Claude Haiku 5.5 rejects non-default sampling parameters with a 400. Determinism comes from caching every LLM call by request hash (a resumed or repeated run replays the same output) and from rules making every decision. Extraction calls send `output_config.effort="low"`. Prefill is not supported, so structured output uses `client.messages.parse(..., output_format=<PydanticModel>)`.
2. **`company_identify` is not free.** It costs 0.2 credits per identifier that matches. The design said "free"; the ledger records the cost.
3. **Rate limits per endpoint** (Crustdata defaults): identify, search, person search and job search 30 rpm; enrich 15 rpm; web search and web fetch 10 rpm. The client keeps one token bucket per endpoint and backs off on 429 using `x-ratelimit-reset`.
4. **Enrich in one call.** `/company/enrich` takes up to 25 ids per request at 2 credits per returned match, so discover enriches its top 15 in one call by `crustdata_company_ids`. Always call identify first, then enrich by id, never by name or domain, because fuzzy matches multiply cost.
5. **Hiring activity in discover** comes from enrich's `hiring` group (`openings_count`, `recent_openings`, `open_jobs_timeseries`), which costs nothing extra. Verify additionally calls `/job/search` (0.03 credits per result, limit 10) for dated postings (`metadata.date_added`).
6. **Natural-language company search** (`search: {query, mode}`) is enabled per account and has not been verified on this key, because verifying it costs credits. The CP-12 live smoke test checks it (limit 1, about 0.03 credits). On a 403 `permission_error` the client raises `SemanticSearchUnavailable`, and discover falls back to filters only, using industry and category values resolved through the free autocomplete endpoint.
7. **Discover search fields** request only `basic_info`, `locations` and `taxonomy`, which costs about 0.13 credits per result, for up to 50 results. Funding, headcount and hiring come from enrich on the top 15. Expected discover spend is about 37 credits.
8. **Leadership people search** filters on `experience.employment_details.current.company_id` OR `...past.company_id` = confirmed id, AND title `(.)` one of founder, CEO, COO, CFO, CTO, director, head. `fields: ["crustdata_person_id","basic_profile","experience","social_handles"]`, limit 25. Never request the plan-gated fields (`years_of_experience*`, `basic_profile.first_name/last_name`, `*.last_updated`): naming them returns 403 for the whole call. Founders and CXOs from enrich `people` are used first.
9. **Registry evidence**: no official MCA API is reachable. Use `web_search_live` (`location:"IN"`, query `"<legal name>" CIN incorporated`) and then `web_enrich_live` on the top 2 results. Reliability is `registry_official` only if the host is `mca.gov.in`; any other host is `registry_mirror`.
10. **HTML to text**: `web_enrich_live` returns raw HTML. Convert it with BeautifulSoup (`lxml`): drop script, style, nav and footer, then collapse whitespace. Text longer than 40,000 characters is split into chunks and every chunk is processed. Never truncate silently.
11. **Quote verification is mandatory.** Every LLM-extracted claim or fact must carry a `quote` that appears verbatim in the source text after whitespace normalisation and case-folding. Items that fail are dropped and counted in the step's log. This enforces principle 1, "nothing from AI memory".
12. **Worker runs in-process.** The API's FastAPI lifespan starts the worker loop when `WORKER_IN_PROCESS=true` (the default). Cloud Run `dealproof-api` runs with `--min-instances=1 --no-cpu-throttling`. Steps are claimed with `SELECT … FOR UPDATE SKIP LOCKED`, so a second instance stays safe.
13. **SSE by DB polling.** `GET /runs/{id}/events` polls the steps table every 1 s and emits changes. This works across instances without pub/sub. The web client falls back to polling `GET /runs/{id}` every 2 s if the EventSource fails.
14. **Same-origin web → API.** The browser calls only `apps/web/app/api/[...path]/route.ts`, which streams requests and responses to `API_BASE_URL` and passes cookies and `Set-Cookie` through. That avoids cross-site cookies between the two `run.app` hosts.
15. **Auth:** see Q1. Session cookie `dp_session`, signed with `SESSION_SECRET` (itsdangerous), HttpOnly, SameSite=Lax, Secure in prod, valid 7 days.
16. **Uploads** are limited to 25 MB each (Cloud Run's request limit is 32 MB). Accepted types: PDF (pypdf, page = PDF page), PPTX (python-pptx, page = slide number) and DOCX (python-docx, page = null, paragraph index kept). Objects are stored at `cases/<case_id>/<document_id>/<filename>`.
17. **Retention**: a GCS lifecycle rule deletes objects after `UPLOAD_RETENTION_DAYS` (30). An hourly worker sweep deletes `documents.extracted_text` and marks documents `purged` once `delete_after` has passed. The case UI shows each document's deletion date.
18. **PII stripping**: deterministic regex redaction runs before storage and before any LLM call. It covers emails, phone numbers (+91 and 10-digit), PAN (`[A-Z]{5}[0-9]{4}[A-Z]`), Aadhaar (12 digits, optionally grouped 4-4-4) and IFSC plus account-number patterns. The claim-extraction prompt also tells the model to omit personal details that the claim does not need. Redacted spans are replaced by `[redacted:<kind>]`.
19. **Company type rule**: `startup` if `year_founded >= today.year - 10` and (`headcount <= 500` or `last_round_type` is in {pre_seed, seed, series_a, series_b, series_c}). Otherwise `established`. If the founding year is unknown: `established` if headcount > 500, else `startup`.
20. **Fit and policy constants** (the "scoring policy", served by `GET /policy` and rendered on the policy page): must-have weight 2, preference weight 1; `fit = round(100 × Σw(pass) / Σw(pass ∪ fail))`, and `None` when nothing is assessable; `assessable% = round(100 × |pass ∪ fail| / |all|)`. Disposition thresholds: prioritise at fit ≥ 70, sufficiency ≥ 80% and no contradicted or conflicting required check; deprioritise on a verified must-have failure, or on fit < 40 with assessable ≥ 60%; cannot assess when identity is not confirmed or assessable < 30%; otherwise investigate further. `POLICY_VERSION = "2026-11-22.1"`.
21. **Evidence sufficiency** = settled required checks / required checks, where settled means `supported` or `contradicted`. Required checks for a startup: identity_incorporation, leadership_history, team_size, funding. For an established company: identity_incorporation, location, team_size, leadership_history, financials, customer_partnership.
22. **Investor ranking**: only rounds with a date and a named investor count. `score = Σ 0.5 ** (years_since_round / 2)` over comparable rounds in the last 6 years. Ties break by count, then by latest date. Investors merge on `investors_detailed.uuid`, else on the exact normalised name (lowercase, punctuation and the suffixes "capital", "ventures", "partners", "fund", "llp", "llc" stripped only for *flagging* possible duplicates, never for merging).
23. **Comparables, "where a fair comparison exists"**: same top industry, same HQ country, and a headcount band within ×0.5–×2 of the subject's. If fewer than 2 qualify, show "No fair comparison found" rather than looser peers.
24. **Seller documents as evidence**: an uploaded seller response is linked by the user to the request items it answers. It becomes `seller_document` evidence for those claims. A rule table decides which categories a seller document can settle (payroll summary → team_size; lease or occupancy evidence → dated_event stage; lender statements → debt_security).
25. **Crustdata funding milestone date** = `funding_date` if present, else `date`. The inner shapes of `people.founders` / `people.cxos` are not documented, so CP-12 records a live fixture and the parser reads `name`, `title` and `linkedin_profile_url`/`profile_url` defensively.
26. **TS types are generated** from FastAPI's OpenAPI into `apps/web/lib/api/schema.ts` with `openapi-typescript` (project-local dev dependency) and committed. `pnpm --filter web gen:api` regenerates them.
27. **Deploy is driven by script** (`infra/deploy.sh`) from an agent's machine. CI only runs lint and tests. GitHub → GCP federation is out of scope for v1.
28. **Cloudflare is not used in v1.** The design allowed it; Cloud Run covers everything.

---

## Global constraints (every checkpoint implicitly includes these)

- The LLM is only the Anthropic Messages API: `anthropic` Python SDK, key `ANTHROPIC_API_KEY`, model `ANTHROPIC_MODEL` (default `claude-haiku-5-5`), `ANTHROPIC_MAX_TOKENS` (default 4096). No Vertex or Bedrock.
- Env names (complete list; CP-01 makes `.env.example` match): `CRUSTDATA_API_KEY`, `CRUSTDATA_BASE_URL` (default `https://api.crustdata.com`), `CRUSTDATA_API_VERSION` (default `2025-11-01`), `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `ANTHROPIC_MAX_TOKENS`, `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_SEND_ENABLED` (default false), `DATABASE_URL`, `TEST_DATABASE_URL`, `GCS_BUCKET`, `UPLOAD_RETENTION_DAYS` (30), `MAX_UPLOAD_MB` (25), `CASE_CREDIT_BUDGET` (150), `DISCOVER_CREDIT_BUDGET` (60), `INVESTOR_CREDIT_BUDGET` (60), `SESSION_SECRET`, `WEB_ORIGIN`, `WORKER_IN_PROCESS` (true), `RUN_LIVE_SMOKE` (unset), and on the web side `API_BASE_URL` and `NEXT_PUBLIC_API_MODE` (`live` | `fixtures`, default `live`).
- Every displayed fact traces to an `evidence` row, which traces to a `sources` row with `retrieved_at` and an as-of date.
- Headcount and hiring are labelled `estimate` / `signal` everywhere and never feed revenue or the financial assessment.
- `unknown` never lowers fit and never causes `deprioritise`.
- `not_checked` always carries a reason and never renders like a clean result.
- An email leaves only after approval by a named user, and only once.
- GCP project `cc-g527-showproduct`, region `asia-south1`.

## Review focus (failure modes no single happy-path test covers; each has a pinned test in its owning checkpoint)

1. **Two companies with the same name** (for example, two "Shree Logistics" entities): identity must not auto-confirm. It shows `ambiguous`, and identity-dependent checks are `not_checked` with reason "identity unresolved". Test: CP-19 `test_identity_ambiguous_on_close_scores`.
2. **Budget runs out mid-verify**: the remaining claim checks become `not_checked` ("budget reached"), and the disposition can still never be `prioritise` on them. Test: CP-21 `test_budget_exhaustion_marks_not_checked`.
3. **Double-clicked or retried send**: exactly one provider call and one `sent` row. Test: CP-23 `test_send_twice_sends_once`.
4. **Worker killed mid-run**: after the lease expires the step runs again, and its paid calls replay from the cache at 0 new credits. Test: CP-11 `test_resume_after_lease_expiry` and CP-12 `test_cached_call_costs_zero`.
5. **The LLM invents a quote** that is not in the document or page: the item is dropped and never becomes a claim or fact. Tests: CP-15 `test_quote_must_appear_verbatim`, and CP-20 `test_unquoted_claims_dropped`.

---

## External APIs (verified 2026-11-22; sources in brackets)

All Crustdata facts below come from the Crustdata docs filesystem and `get_schema` (free; no credits spent), plus the free `/account/endpoints` call for this key's access.

### Crustdata REST, common
- **Base URL** `https://api.crustdata.com`. **Headers**: `authorization: Bearer $CRUSTDATA_API_KEY`, `x-api-version: 2025-11-01` (required; a request without it gets 400), `content-type: application/json`. [docs: openapi-specs/2025-11-01/introduction#authentication; general/permissions#endpoint]
- **Per-call credits**: the `X-Credits-Used` response header on every billed response, including search, enrich, web and autocomplete. Free endpoints send no header, so record 0. The usage events API exposes the same number as `credits_used`. [docs: general/credits "Per-call usage: the X-Credits-Used header"; general/usage]
- **Rate-limit headers**: `x-ratelimit-remaining`, `x-ratelimit-reset` (seconds). [docs: openapi-specs/2025-11-01/best-practices]
- **Errors**: `{ "error": { "type": "invalid_request" | "authentication…" | …, "message": … } }`. 402 means out of credits, 403 means not on plan (`permission_error`), 429 means rate limited. [api-reference company identify, 400 schema; MCP tool notes]
- **Access on this key** (`GET /account/endpoints`, free, run 2026-11-22): **enabled**: `/company/identify`, `/company/enrich`, `/company/search`, `/company/search/autocomplete`, `/job/search`, `/person/search`, `/person/enrich`, `/person/identify`, `/person/search/autocomplete`, `/social_post/search`, `/web/search/live`, `/web/enrich/live`, `/agent/query`. **Disabled**: all `/batch/*`, `/company/professional_network/search/live`, `/job/professional_network/search/live`, `/person/professional_network/*` (live person search/enrich), `/person/contact/enrich`, `/dev_platform/enrich`, `/employee_review/enrich`, live social endpoints. The design uses none of the disabled endpoints.

### Company identify: `POST /company/identify`
- Body: exactly one of `names[]`, `domains[]`, `crustdata_company_ids[]`, `professional_network_profile_urls[]`, plus optional `fields` (only `crustdata_company_id`, `basic_info`, `social_profiles`) and `exact_match: bool|null`.
- Response: a top-level array with one entry per identifier, `{matched_on, match_type, matches: [{confidence_score, company_data: {crustdata_company_id, basic_info: {name, primary_domain, all_domains, website, professional_network_url, profile_name, description, company_type, year_founded, employee_count_range, markets, industries}}}]}`.
- Cost 0.2 credits per *matched* identifier (unmatched are free). 30 rpm. [api-reference/company-apis/identify-a-company-from-name-domain-id-or-profile-url.mdx]

### Company enrich: `POST /company/enrich`
- Body: the same identifier keys (≤25 per request), `fields` (groups: `basic_info, revenue, headcount, funding, hiring, web_traffic, seo, competitors, employee_reviews, people, locations, taxonomy, followers, news, software_reviews, social_profiles, reviews, public_launches, market_intel, metadata, crustdata_company_id, updated_at, indexed_at`). Omitting `fields` returns only id and `basic_info`. `exact_match`.
- Response: the same array shape as identify, with `matches[].company_data` holding:
  - `funding`: `total_investment_usd, last_round_amount_usd, last_fundraise_date, last_round_type, investors[], investors_detailed[]{name, uuid, permalink, type, categories, crunchbase_profile_url}, milestones[]{round_type, date, funding_date, amount_usd, investors[], lead_investors, investors_detailed[]{…}, is_fund, permalink}, num_funding_rounds, acquisitions[], acquired_by`
  - `headcount`: `total, timeseries[]{date, employee_count}, growth_percent{mom,qoq,six_months,yoy,two_years}, growth_absolute{…}, by_role_*, by_region_*, largest_headcount_country`
  - `hiring`: `openings_count, openings_growth_percent, recent_openings[], recent_titles_csv, open_jobs_timeseries[], by_function_qoq_pct`
  - `people`: `founders[], cxos[], decision_makers[]` (inner shape undocumented; see builder call 25)
  - `locations`: `headquarters, country, state, street_address, all_office_addresses`
  - `taxonomy`: `professional_network_industry, professional_network_industries, categories, primary_naics_detail, sic_detail_list`
  - `news[]`: `article_title, article_url, article_publish_date, article_publisher_name, publisher_domain, confidence_score, source`
- Cost 2 credits per *returned match* (more for technographics, which we never request). 15 rpm. [api-reference/company-apis/get-full-company-enrichment.mdx; company-docs/enrichment/introduction.mdx; get_schema groups funding, headcount, news]

### Company search: `POST /company/search` (includes natural-language mode)
- Body: `filters` (a leaf `{field, type, value}` or a group `{op: "and"|"or", conditions: [...]}`; operators `= != < > =< => in not_in is_null is_not_null (.) (!) geo_distance geo_exclude`), `search: {query, mode: "hybrid"|"lexical"|"semantic"}`, `limit` (≤1000 filter-only, ≤100 with `search`), `cursor`, `sorts: [{field, order}]` (rejected alongside `search`), `fields` (a response whitelist; groups `crustdata_company_id, metadata, basic_info, revenue, headcount, software_reviews, funding, hiring, locations, social_profiles, taxonomy, followers, maps`).
- With `search`, filters act as hard constraints applied first. Results come back relevance-ordered in one window, with `total_count` and `next_cursor` null and no score.
- Common filter columns: `basic_info.industries`, `basic_info.year_founded`, `basic_info.employee_count_range`, `basic_info.company_type`, `headcount.total`, `funding.last_round_type` (lowercase snake_case such as `series_a`; `in` is exact), `funding.total_investment_usd`, `locations.country`, `locations.headquarters`, `taxonomy.categories`. Categorical values must be resolved through `/company/search/autocomplete` (free).
- Response `{companies: [{crustdata_company_id, basic_info{…}, locations{…}, taxonomy{…}, funding{…}, headcount{…}, …}], next_cursor, total_count}`.
- Cost 0.03 credits per result, plus 0.1 per result for `taxonomy` and 0.2 for `funding`/`headcount`/`hiring`, charged on each side (filter and response). NL search adds no surcharge but is "enabled per account"; a 403 `permission_error` means it is not enabled. 30 rpm. [api-reference/company-apis/search-companies-with-indexed-fields-only.mdx; get_schema company_search]

### Person search: `POST /person/search`
- Body: `filters` (same grammar), `fields`, `limit`, `cursor`, `sorts`, optional `search: {query, mode}`. Use filters only.
- Filter columns we use: `experience.employment_details.current.company_id`, `experience.employment_details.past.company_id`, `experience.employment_details.current.title` (categorical: use `(.)` for word match), `experience.employment_details.current.seniority_level`.
- Response `{profiles: [{crustdata_person_id, basic_profile{name, headline, current_title, location{…}}, experience{employment_details{current[], past[] each {name, crustdata_company_id, title, start_date, end_date, seniority_level, company_website, …}}}, social_handles{professional_network_identifier{profile_url}}}], next_cursor, total_count}`.
- Cost 0.03 per result, plus 0.1 per result for `experience` on each side. Plan-gated (403 if named): `years_of_experience`, `years_of_experience_raw`, `basic_profile.first_name`, `basic_profile.last_name`, `*.last_updated`. 30 rpm. [api-reference/person-apis/search-people-using-filters-and-sorting.mdx; get_schema person_search + group experience]

### Job search: `POST /job/search`
- Body: `filters` (e.g. `company.basic_info.company_id = <id>`), `fields` (`job_details, company, location, content, metadata`), `limit`, `cursor`, `sorts`.
- Response `{job_listings: [{crustdata_job_id, job_details{title, category, workplace_type, url, number_of_openings}, location{raw, city, …}, metadata{date_added, date_updated}}], next_cursor, total_count}`.
- Cost about 0.03 per result. 30 rpm. [api-reference/job-apis/search-the-indexed-job-dataset.mdx; get_schema job_search]

### Web search live: `POST /web/search/live`
- Body: `query` (required; supports `site:`), `location` (ISO alpha-2; we use `"IN"`), `sources[]` (`news, web, scholar-articles, scholar-articles-enriched, scholar-author, ai, social`), `site`, `start_date` / `end_date` (unix **seconds**), `page` (≤15; >1 requires exactly one source; 1 credit per page).
- Response `{success, query, timestamp (ms), results: [{source, title, url, snippet, position, …}], metadata{total_results, failed_pages, empty_pages}}`.
- 1 credit per page. 10 rpm. [api-reference/web-apis/web-search.mdx; web-docs/search/introduction]

### Web fetch live: `POST /web/enrich/live`
- Body `{urls: [≤10], human_mode?: bool}`. Response: a top-level array `[{success, url, timestamp (s), title, content (HTML)}]`. Failed entries have `url: null`, so failures are found by set difference against the requested URLs.
- 1 credit per page. 10 rpm. [api-reference/web-apis/web-fetch.mdx; web-docs/fetch/introduction]

### Anthropic Messages API (Python SDK `anthropic`)
- `AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())`. Structured extraction: `await client.messages.parse(model=…, max_tokens=…, system=…, messages=[…], output_format=<PydanticModel>, output_config={"effort": "low"})` returns `.parsed_output`, `.usage.input_tokens`, `.usage.output_tokens` and `.stop_reason`. Check `refusal` and `max_tokens` before using the output. Drafting uses `messages.create` and reads text blocks. Haiku 5.5: no `temperature`/`top_p`/`top_k` (a non-default value returns 400), thinking adaptive by default, default effort `medium`, no assistant prefill. Price $0.10 / $0.50 per MTok of input / output for prompts up to 100K tokens, and $0.50 / $2.50 above that. [claude-api skill: Current Models table (cached 2026-11-03), Thinking & Effort table, python/claude-api/tool-use.md "messages.parse"]
- If `messages.parse` rejects `output_config` alongside `output_format` in the installed SDK version, call `messages.create` with `output_config={"effort": "low", "format": {"type": "json_schema", "schema": Model.model_json_schema()}}` and validate with `Model.model_validate_json`. Use one code path behind `LlmClient.extract`.

### Resend
- `POST https://api.resend.com/emails` with `Authorization: Bearer $RESEND_API_KEY` and `Idempotency-Key: <key>` (honoured for 24 h). Body `{from, to, subject, html | text, reply_to?}`. Success returns `{id}`. Called with httpx; no SDK needed. [resend.com/docs/api-reference/emails/send-email]

---

## File structure (ownership map)

```
apps/api/
  app/domain/enums.py, types.py         CP-01  shared vocabulary + rule I/O dataclasses
  app/settings.py                        CP-01 (extend)  new env names
  app/db/base.py, models.py, session.py  CP-02
  alembic/, alembic.ini                  CP-02
  app/api/router.py, schemas.py          CP-03  all routes registered; schemas = API contract
  app/api/{auth,theses,investors,cases,claims,documents,requests,runs,policy}.py  CP-03 stubs → filled by owners
  app/rules/fit.py                       CP-04
  app/rules/claim_status.py              CP-05
  app/rules/evaluate.py, diff.py         CP-06
  app/rules/investors.py, requests.py    CP-07
  app/policy.py                          CP-04 (constants used by CP-05/06/07 read-only)
  app/jobs/engine.py, worker.py, events.py   CP-11
  app/pipelines/*.py                     CP-11 creates stubs; one owner per module (below)
  app/clients/crustdata.py               CP-12
  app/clients/llm.py, prompts/*.md       CP-13
  app/clients/email.py, storage.py       CP-14
  app/documents/{extract,redact,quotes,html}.py  CP-15
  app/auth/{passwords,sessions,deps}.py, app/cli.py  CP-16
  app/cache.py, app/ledger.py            CP-12 (cache) / CP-12 (ledger, shared with CP-13 via interface)
apps/web/
  lib/api/schema.ts (generated), client.ts, fixtures/*  CP-03
  app/api/[...path]/route.ts             CP-03
  components/ui/*, app/globals.css, tailwind config     CP-09
  app/(marketing)/**                     CP-10
  app/(auth)/**, app/(app)/layout.tsx, app/(app)/cases/page.tsx   CP-26
  app/(app)/discover/**                  CP-27
  app/(app)/investors/**                 CP-28
  app/(app)/cases/[id]/layout.tsx + overview, identity, claims, sources   CP-29
  app/(app)/cases/[id]/{events,comparables,assessment,cost}  CP-30
  app/(app)/cases/[id]/act/**            CP-31
  app/(app)/policy/**, app/print.css     CP-32
infra/gcp/*.sh, infra/deploy.sh, apps/web/Dockerfile   CP-08 / CP-34 / CP-35
```

Pipeline module owners: `discover.py` CP-17, `investors.py` CP-18, `verify_identity.py` CP-19, `claims_intake.py` CP-20, `evidence.py` CP-21, `evaluate.py` CP-22, `act.py` CP-23, `recheck.py` CP-24, `maintenance.py` CP-25.

---

## Parallel waves (same checkout, no file conflicts within a wave)

| Wave | Starts when | Checkpoints in parallel |
|---|---|---|
| W1 | 0a + 0b pushed | CP-01 (Opus), CP-08 (Opus), CP-09 (Fable) |
| W2 | CP-01 pushed (CP-02 also needs CP-08) | CP-02, CP-03, CP-04, CP-05, CP-06, CP-07, CP-15 (all Opus); CP-10 (Fable, after CP-09) |
| W3 | CP-02 pushed | CP-11 (needs CP-03), CP-12, CP-13, CP-14 (Opus); CP-16 (Opus, needs CP-03); CP-26 (Fable, needs CP-03 + CP-09) |
| W4 | its listed deps | CP-17, CP-18, CP-19 (Opus); CP-27, CP-28, CP-29 (Fable) |
| W5 | its listed deps | CP-20 → CP-21 → CP-22 → {CP-23, CP-25} → CP-24 (Opus chain); CP-30, CP-31, CP-32 (Fable) |
| W6 | all of the above | CP-33 → CP-34 → CP-35 → CP-36 → CP-37 → CP-38 → CP-39 |

Notes: W2 rule checkpoints (CP-04 to CP-07) touch only their own files plus `app/policy.py`. **CP-04 creates `app/policy.py`; CP-05/06/07 append their own constant blocks to it** (append-only, each under its own `# --- <CP id> ---` header; rebase conflicts are trivial). If that is awkward, they may hold constants in their own module and CP-25 re-exports them. Fable UI checkpoints run on fixtures (`NEXT_PUBLIC_API_MODE=fixtures`), so they don't wait for backend checkpoints. Live wiring is verified in CP-33.

---

# Phase 1: Foundations

### CP-01: Backend vocabulary + dependency set
- **Owner:** Opus implementation · **Deps:** 0a · **Parallel with:** CP-08, CP-09
- **Goal:** Create one shared vocabulary that every rule, model and schema imports, add every planned backend dependency at once, and complete the env list.
- **Paths:** `apps/api/app/domain/__init__.py`, `apps/api/app/domain/enums.py`, `apps/api/app/domain/types.py`, `apps/api/app/settings.py`, `apps/api/pyproject.toml`, `apps/api/uv.lock`, `.env.example`, `apps/api/tests/domain/test_vocabulary.py`, `apps/api/tests/test_settings.py`
- **Interfaces produced** (`StrEnum`s in `enums.py`; values are snake_case of the names):
  - `ClaimStatus`: supported, contradicted, partially_corroborated, conflicting_evidence, cannot_verify, not_checked
  - `ClaimCategory`: identity_incorporation, location, team_size, leadership_history, funding, dated_event, customer_partnership, financials, debt_security, other
  - `SourceClass`: registry_official, registry_mirror, audited_statement, counterparty_confirmation, company_announcement, funding_database, professional_profile, headcount_estimate, data_provider_profile, news, seller_document, seller_statement, user_typed
  - `CriterionKind`: must, preference · `TriState`: pass, fail, unknown · `Disposition`: prioritise, investigate_further, deprioritise, cannot_assess · `CompanyType`: startup, established · `IdentityState`: confirmed, ambiguous, not_found
  - `RunKind`: discover, investor_discover, verify, evaluate, recheck · `StepState`: pending, running, done, failed, skipped_budget · `RequestStatus`: draft, approved, sent, suppressed_test_mode, failed · `DocumentKind`: seller_deck, seller_response, other · `CriterionDimension`: geography, ownership, industry_activity, customer_type, size, growth_signal, funding_stage, founded_year, other
  - `types.py` (frozen dataclasses, the rule inputs and outputs): `Criterion(id, label, kind, dimension, operator, value, crustdata_filter: dict|None)`, `CriterionResult(criterion_id, state: TriState, evidence_ids: list[str], reason: str)`, `EvidenceFact(evidence_id, source_class, as_of: date|None, component: str, value: Any, relation: Literal["match","conflict","unrelated"])`, `ClaimInput(claim_id, category, components: dict[str, Any], material: bool)`, `ClaimOutcome(claim_id, status, reason, evidence_ids, settle_with: str|None)`
- **Settings additions:** `crustdata_base_url`, `crustdata_api_version`, `test_database_url`, `max_upload_mb`, `discover_credit_budget`, `investor_credit_budget`, `session_secret: SecretStr`, `worker_in_process: bool = True`, using the defaults from Global constraints.
- **Dependencies to add** (`uv add`): `sqlalchemy[asyncio]>=2`, `alembic`, `psycopg[binary]>=3`, `httpx`, `anthropic`, `google-cloud-storage`, `argon2-cffi`, `itsdangerous`, `python-multipart`, `pypdf`, `python-pptx`, `python-docx`, `beautifulsoup4`, `lxml`. Dev: `pytest-asyncio`, `respx`. (`httpx2` already present from 0a stays as is.)
- **Tests:** `test_status_values_are_prd_six` asserts the set of `ClaimStatus` values equals the six above. `test_settings_defaults` asserts `anthropic_model == "claude-haiku-5-5"`, `email_send_enabled is False`, `case_credit_budget == 150` and `discover_credit_budget == 60` with an empty env (monkeypatch `env_file=None`). `test_env_example_lists_every_setting` parses `.env.example` names and checks they are a superset of the `Settings` fields, uppercased.
- **Verify:** `cd apps/api && uv run pytest tests/domain tests/test_settings.py -q && uv run ruff check .` all pass.
- **Acceptance:** the tests above pass, `uv lock` is clean, and `.env.example` has every name with no values.

### CP-02: Database schema + migrations + session
- **Owner:** Opus implementation · **Deps:** CP-01, CP-08 (Neon dev/test branches) · **Parallel with:** CP-03 to CP-07, CP-10
- **Goal:** Create the full v1 schema in one Alembic revision, plus an async session factory and a test-database fixture.
- **Paths:** `apps/api/app/db/{base.py,models.py,session.py}`, `apps/api/alembic.ini`, `apps/api/alembic/{env.py,script.py.mako,versions/0001_initial.py}`, `apps/api/tests/conftest.py`, `apps/api/tests/db/test_schema.py`, `.github/workflows/*` (add a `postgres:17` service + `TEST_DATABASE_URL` for the api job only)
- **Tables** (UUID pk `id`, `created_at`; JSONB where noted):
  - `users(email unique, display_name, password_hash)`, `sessions(user_id, expires_at)`
  - `theses(owner_id, text, status)`, `criteria(thesis_id, position, label, kind, dimension, operator, value jsonb, crustdata_filter jsonb null, edited bool)`, `shortlist_items(thesis_id, crustdata_company_id, rank, fit int null, assessable_pct int, criterion_results jsonb, card jsonb, excluded bool, exclusion_reason)`
  - `investor_searches(owner_id, profile jsonb, status)`, `investor_entries(search_id, investor_key, investor_name, investor_uuid null, score float, rank, comparable_rounds jsonb, possible_duplicate_of null, unknowns jsonb)`
  - `companies(crustdata_company_id unique, snapshot jsonb, fetched_at)`
  - `cases(owner_id, thesis_id null, shortlist_item_id null, input_name, input_website, crustdata_company_id null, identity_state, identity_candidates jsonb, company_type null, credit_budget int, status)`
  - `sources(case_id null, run_id null, provider, endpoint_or_url, request jsonb, retrieved_at, source_class, title null, publisher null)`, `evidence(source_id, case_id null, entity_ref, field_path null, quote null, value jsonb, as_of date null, identity_confidence float null)`
  - `documents(case_id, kind, filename, gcs_path, mime, pages int null, extracted_text text null, redaction_counts jsonb, delete_after, purged bool, answers_request_item_ids jsonb)`
  - `claims(case_id, document_id null, text, category, components jsonb, quote null, page null, material bool, origin: "document"|"typed")`, `claim_checks(claim_id, run_id, status, reason, evidence_ids jsonb, settle_with null, created_at)` (append-only history; latest row = current)
  - `events(case_id, event_date, title, kind, evidence_id)`, `comparables(case_id, crustdata_company_id, basis jsonb)`
  - `assessment_versions(case_id, version int, policy_version, inputs_hash, judgments jsonb, disposition, reasons jsonb, diff_from_previous jsonb null, trigger, unique(case_id, version))`
  - `seller_requests(case_id, assessment_version_id, items jsonb, recipient_email null, subject, body, status, idempotency_key unique, approved_by null, approved_by_name null, approved_at null, sent_at null, provider_message_id null, error null)`
  - `runs(kind, case_id null, thesis_id null, investor_search_id null, state, created_by, budget_credits, error null)`, `steps(run_id, key, position, state, attempts int, lease_until null, input jsonb, output jsonb null, error null, unique(run_id, key))`
  - `api_cache(request_hash unique, provider, endpoint, request jsonb, response jsonb, status_code, credits_used numeric, created_at)`
  - `cost_entries(case_id null, run_id null, step_id null, provider, endpoint, credits numeric, input_tokens int, output_tokens int, usd numeric, cached bool)`
- **Interfaces produced:** `app.db.session.get_session() -> AsyncIterator[AsyncSession]` (FastAPI dependency), `app.db.session.session_scope() -> AsyncContextManager[AsyncSession]` (worker use), and every ORM class in `app.db.models` named in singular PascalCase (`Thesis`, `Criterion`, `ShortlistItem`, …, `CostEntry`).
- **Tests:** `test_migration_upgrade_downgrade` (upgrade head, downgrade base, upgrade head on `TEST_DATABASE_URL`); `test_claim_check_history_is_append_only` (two checks for one claim, latest by `created_at`); `test_request_idempotency_key_unique` (a duplicate insert raises `IntegrityError`).
- **Verify:** `cd apps/api && uv run alembic upgrade head` (against the Neon dev branch via `DATABASE_URL`) and `uv run pytest tests/db -q`.
- **Acceptance:** migrations apply cleanly on Neon dev and in CI Postgres; tests pass.

### CP-03: API contract, route stubs, typed web client, same-origin proxy
- **Owner:** Opus implementation · **Deps:** CP-01 · **Parallel with:** CP-02, CP-04 to CP-07, CP-10
- **Goal:** Fix every request and response shape now, so backend and Fable UI work proceed in parallel against one contract.
- **Paths:** `apps/api/app/api/router.py`, `apps/api/app/api/schemas.py`, `apps/api/app/api/{auth,theses,investors,cases,claims,documents,requests,runs,policy}.py`, `apps/api/app/main.py` (include `router` only), `apps/api/scripts/export_openapi.py`, `apps/api/tests/api/test_contract.py`, `apps/web/lib/api/{schema.ts,client.ts}`, `apps/web/lib/api/fixtures/{theses,investors,cases,runs,policy}.ts`, `apps/web/app/api/[...path]/route.ts`, `apps/web/package.json` (scripts `gen:api`; dev dep `openapi-typescript`)
- **Endpoints** (stubs return 501 until their owner checkpoint fills them):
  - Auth (CP-16): `POST /auth/login {email,password} → UserOut`, `POST /auth/logout`, `GET /auth/me → UserOut`
  - Discover (CP-17): `POST /theses {text} → ThesisOut` (criteria extracted synchronously), `PUT /theses/{id}/criteria [CriterionIn] → ThesisOut`, `POST /theses/{id}/search → RunOut`, `GET /theses → [ThesisSummary]`, `GET /theses/{id} → ThesisOut` (includes `shortlist: [ShortlistItemOut]`)
  - Investors (CP-18): `POST /investor-searches {sector, location, stage, size, funding_sought} → InvestorSearchOut` (includes `run`), `GET /investor-searches/{id} → InvestorSearchOut` (includes `entries`)
  - Cases (CP-19/25): `POST /cases {shortlist_item_id?|name+website, thesis_id?} → CaseOut` (includes `run`), `GET /cases → [CaseSummary]`, `GET /cases/{id} → CaseDetail` (memo aggregate), `POST /cases/{id}/identity {crustdata_company_id} → CaseOut`, `POST /cases/{id}/verify → RunOut`
  - Claims and docs (CP-20): `POST /cases/{id}/claims {text} → ClaimOut`, `POST /cases/{id}/documents` (multipart: `file`, `kind`, `answers_request_item_ids[]`) `→ DocumentOut` (includes `run`)
  - Assessments (CP-22): `GET /cases/{id}/assessments → [AssessmentVersionOut]`
  - Act (CP-23): `POST /cases/{id}/requests → SellerRequestOut`, `PATCH /requests/{id} {recipient_email?, subject?, body?}`, `POST /requests/{id}/approve`, `POST /requests/{id}/send → SellerRequestOut`
  - Runs (CP-11): `GET /runs/{id} → RunOut` (includes `steps: [StepOut]`), `GET /runs/{id}/events` (SSE `event: step`, data `StepOut`; `event: run`, data `RunOut`), `POST /runs/{id}/resume → RunOut`
  - Policy (CP-25): `GET /policy → PolicyOut`
- **Schema rules:** every fact-bearing field in the schemas is a `Fact[T] = {value: T, source: SourceRef, as_of: date|None, is_estimate: bool}` with `SourceRef = {source_id, provider, label, url_or_endpoint, retrieved_at, source_class}`. Claims expose `status`, `reason`, `settle_with`, `evidence: [EvidenceOut]` and `history: [ClaimCheckOut]`. `CaseDetail.cost = {crustdata_credits, llm_usd, by_step: [...]}`. `ShortlistItemOut.fit` is `int|None`, plus `assessable_pct: int`.
- **Proxy:** `route.ts` handles GET/POST/PUT/PATCH/DELETE. It forwards path, query, body stream, `cookie` and `content-type` to `${API_BASE_URL}`, and streams the response body back with `set-cookie` and `content-type` (SSE must not be buffered). `export const dynamic = "force-dynamic"`.
- **Client:** `client.ts` exports typed functions (`createThesis`, `updateCriteria`, `startSearch`, `getThesis`, `listCases`, `getCase`, `createCase`, `uploadDocument`, `addClaim`, `createRequest`, `updateRequest`, `approveRequest`, `sendRequest`, `getRun`, `subscribeRun(runId, onEvent) → unsubscribe` with EventSource and polling fallback, `getPolicy`, `login`, `logout`, `me`). When `NEXT_PUBLIC_API_MODE === "fixtures"` it resolves from `fixtures/*` instead. Fixture companies are fictional and named "… (fixture)".
- **Tests:** `test_openapi_has_all_routes` (every path above is in `app.openapi()`); `test_stub_returns_501`; `test_fact_schema_requires_source`. Web: `pnpm --filter web exec tsc --noEmit`.
- **Verify:** `uv run pytest tests/api -q`; `uv run python scripts/export_openapi.py > ../web/openapi.json && pnpm --filter web gen:api && git diff --exit-code apps/web/lib/api/schema.ts` (the generated file is up to date); `pnpm --filter web build`.
- **Acceptance:** the contract is committed, the web builds, and the proxy streams (manual check: `curl -N localhost:3000/api/runs/x/events` connects through to the API stub).

### CP-04: Rules: criteria tri-state, fit, assessable %
- **Owner:** Opus implementation · **Deps:** CP-01 · **Parallel with:** CP-02, CP-03, CP-05 to CP-07, CP-10
- **Paths:** `apps/api/app/policy.py` (create; `POLICY_VERSION`, `MUST_WEIGHT=2`, `PREF_WEIGHT=1`, thresholds from builder call 20), `apps/api/app/rules/fit.py`, `apps/api/tests/rules/test_fit.py`
- **Interfaces:** `evaluate_criterion(c: Criterion, company: dict) -> CriterionResult` (it reads `company` in the normalised shape produced by `app.clients.crustdata.normalise_company`, defined in CP-12; for this checkpoint use the dict keys `name, country, hq_city, industries, year_founded, headcount, headcount_growth_yoy_pct, last_round_type, total_funding_usd, description, ownership`); `must_have_gate(results) -> tuple[bool, list[str]]` (excluded only on a `fail` of a must); `fit_score(criteria, results) -> tuple[int|None, int]` (fit, assessable_pct).
- **Operators:** `eq, in, gte, lte, between, contains_any` (case-insensitive word match over `industries`/`description`), `is_true`. A missing company value gives `unknown`. A criterion of dimension `customer_type` or `growth_signal` with no `crustdata_filter` returns `unknown` with reason "assessed from evidence" (CP-21 may later upgrade it).
- **Tests:** `test_unknown_does_not_lower_fit` (the same company with one criterion changed from pass to unknown keeps fit at 100 and lowers assessable%); `test_fail_of_must_excludes`; `test_unknown_must_keeps`; `test_fit_none_when_nothing_assessable`; `test_weights` (must pass + pref fail → fit 67); `test_headcount_never_used_as_revenue` (a revenue criterion with only headcount present → unknown).
- **Verify:** `uv run pytest tests/rules/test_fit.py -q`.

### CP-05: Rules: claim status per category (PRD illustration encoded)
- **Owner:** Opus implementation · **Deps:** CP-01 · **Parallel with:** CP-02 to CP-04, CP-06, CP-07, CP-10
- **Paths:** `apps/api/app/rules/claim_status.py`, `apps/api/app/policy.py` (append the `ADEQUATE_SOURCES` and `SETTLE_WITH` tables under `# --- CP-05 ---`), `apps/api/tests/rules/test_claim_status.py`, `apps/api/tests/fixtures/prd_illustration.py`
- **Interface:** `decide_status(claim: ClaimInput, facts: list[EvidenceFact], check_ran: bool, not_run_reason: str|None) -> ClaimOutcome`
- **Tables:** `ADEQUATE_SOURCES[category][component] -> set[SourceClass]`. Minimum entries: identity_incorporation {registry_official, registry_mirror}; location {registry_official, registry_mirror, data_provider_profile, seller_document}; team_size {seller_document, audited_statement} (headcount_estimate is never adequate); leadership_history {professional_profile}; funding {funding_database, registry_official, news} (company_announcement adequate only for the component `announced`); dated_event: components `event`/`date` → {company_announcement, news}, component `stage=operating` → {news, seller_document, registry_official}; customer_partnership {counterparty_confirmation, seller_document}; financials {audited_statement, registry_official}; debt_security {audited_statement, seller_document}, where a registry charge is a fact of relation `unrelated` for "no debt". `SETTLE_WITH[category]`: team_size → "Dated payroll summary"; debt_security → "Lender statements"; dated_event → "Lease or occupancy evidence for the facility"; financials → "Audited financial statements"; customer_partnership → "Customer confirmation or signed contract"; identity_incorporation → "Certificate of incorporation"; leadership_history → "Founder CV with dates"; funding → "Share allotment filing or term sheet".
- **Algorithm** (not determined by the tests alone, so it is written down here):
  1. `not check_ran` → `not_checked` with `not_run_reason` (required, non-empty).
  2. For each claim component, keep facts whose `source_class` is adequate for (category, component).
  3. If any component has adequate facts that both `match` and `conflict` → `conflicting_evidence`.
  4. Else if any component has only `conflict` adequate facts → `contradicted`.
  5. Else if every component has an adequate `match` → `supported`.
  6. Else if at least one component has an adequate `match` → `partially_corroborated`, with `settle_with` from the table.
  7. Else → `cannot_verify`, with `settle_with` and a reason naming what was found (for example "profile-based estimate of 140; profiles under-count warehouse staff").
  8. `evidence_ids` = every fact considered, adequate or not.
- **Tests:** one test per PRD illustration row, using fixture facts: `test_prd_incorporated_2014_pune_supported`; `test_prd_250_employees_cannot_verify` (a headcount_estimate of 140 that conflicts is still `cannot_verify`, settle_with "Dated payroll summary"); `test_prd_founder_history_supported`; `test_prd_funding_2025_supported` (funding_database + company_announcement); `test_prd_facility_partially_corroborated` (an announcement with stage planned; the stage component is unmatched); `test_prd_no_debt_cannot_verify` (a registry charge exists, settle_with "Lender statements"). Plus `test_not_checked_requires_reason`, `test_conflicting_sources`, `test_contradicted_by_registry_year`.
- **Verify:** `uv run pytest tests/rules/test_claim_status.py -q`.

### CP-06: Rules: evaluation, disposition, version diff
- **Owner:** Opus implementation · **Deps:** CP-01 · **Parallel with:** CP-02 to CP-05, CP-07, CP-10
- **Paths:** `apps/api/app/rules/evaluate.py`, `apps/api/app/rules/diff.py`, `apps/api/app/policy.py` (append `REQUIRED_CHECKS` and the thresholds under `# --- CP-06 ---`), `apps/api/tests/rules/test_evaluate.py`, `apps/api/tests/rules/test_diff.py`
- **Interfaces:** `classify_company(year_founded, headcount, last_round_type, today) -> CompanyType` (builder call 19); `evidence_sufficiency(company_type, outcomes: list[ClaimOutcome], claim_categories: dict[str, ClaimCategory]) -> {"pct": int, "settled": [...], "gaps": [{category, status, settle_with}]}` (a required category with no claim counts as a gap "not claimed / not checked"); `business_assessment(company_snapshot) -> {"signals": [{label, value, is_estimate: True, evidence_id}]}` (headcount trend, open roles, locations, dated expansions; never revenue); `financial_assessment(outcomes) -> {"assessed": False, "reason": "No reliable financial inputs"}` unless a `financials` claim is `supported` by audited_statement or registry_official; `disposition(identity_state, fit, assessable_pct, sufficiency_pct, must_fail: bool, required_outcomes) -> tuple[Disposition, list[str]]` (builder call 20, evaluated in order: cannot_assess, deprioritise, prioritise, investigate_further); `evaluate_case(inputs: EvaluationInputs) -> EvaluationResult` (all five judgments + disposition + reasons + `inputs_hash` = sha256 of canonical JSON). `diff.py`: `diff_versions(prev: EvaluationResult, new: EvaluationResult, claim_texts, evidence_labels) -> list[DiffLine]`, where `DiffLine = {kind: "claim"|"judgment"|"disposition", subject, before, after, because}`.
- **Tests:** `test_prd_example_investigate_further` (strong fit 85, 3 of 6 supported, identity confirmed → investigate_further, sufficiency 50); `test_missing_evidence_never_deprioritises` (fit None, assessable 20 → cannot_assess, never deprioritise; fit 90 with everything cannot_verify → investigate_further); `test_must_fail_deprioritises`; `test_identity_unresolved_cannot_assess`; `test_prioritise_requires_sufficiency`; `test_financial_not_assessed_by_default`; `test_judgments_never_blended` (the result has five separate keys and no combined score); `test_same_inputs_same_hash`; `test_diff_reports_status_change_with_reason`.
- **Verify:** `uv run pytest tests/rules/test_evaluate.py tests/rules/test_diff.py -q`.

### CP-07: Rules: investor ranking + request list
- **Owner:** Opus implementation · **Deps:** CP-01 · **Parallel with:** CP-02 to CP-06, CP-10
- **Paths:** `apps/api/app/rules/investors.py`, `apps/api/app/rules/requests.py`, `apps/api/app/policy.py` (append under `# --- CP-07 ---`), `apps/api/tests/rules/test_investors.py`, `apps/api/tests/rules/test_requests.py`
- **Interfaces:** `collect_rounds(companies: list[dict]) -> list[Round]` (drops rounds without a date or without a named investor; date per builder call 25); `group_by_investor(rounds) -> list[InvestorGroup]` (merge on uuid, else on the exact lowercased name; `possible_duplicate_of` set by suffix-stripped name equality, never merged); `rank_investors(groups, today, lookback_years=6) -> list[RankedInvestor]` (builder call 22; each entry carries `comparable_rounds[{company_id, company_name, round_type, date, amount_usd|None, source_ref}]`, `last_sector_investment`, `why` (generated text listing the count and sectors, no LLM), and `unknowns`, e.g. "Cheque size unknown" when amounts are missing). `build_request_items(outcomes, claims) -> list[RequestItem{id, claim_ids, category, document, reason}]`: one item per distinct `settle_with` over claims in cannot_verify, partially_corroborated or conflicting_evidence; it never includes not_checked (those are re-runs, not seller asks).
- **Tests:** `test_round_without_date_excluded`; `test_uuid_merge_and_name_flag`; `test_recency_weighting` (two rounds 2025 vs one round 2019 → the first ranks higher); `test_prd_request_list_three_documents` (from the PRD illustration outcomes → exactly payroll summary, lease or occupancy evidence, lender statements).
- **Verify:** `uv run pytest tests/rules/test_investors.py tests/rules/test_requests.py -q`.

### CP-08: GCP + Neon bootstrap
- **Owner:** Opus implementation · **Deps:** 0a · **Parallel with:** CP-01, CP-09 (and the W2 checkpoints)
- **Goal:** Idempotent infrastructure scripts, plus the Neon project and branches. No app deploy yet.
- **Paths:** `infra/gcp/bootstrap.sh`, `infra/gcp/lifecycle.json`, `infra/gcp/push-secrets.sh`, `infra/README.md`
- **Steps:**
  - `bootstrap.sh`: sets project `cc-g527-showproduct`; enables run, cloudbuild, artifactregistry, secretmanager and storage; creates Artifact Registry `dealproof` (docker, asia-south1); creates bucket `gs://cc-g527-showproduct-dealproof-uploads` (asia-south1, uniform access, public access prevention, lifecycle `{"rule":[{"action":{"type":"Delete"},"condition":{"age":30}}]}`); creates service account `dealproof-api@…` with `roles/storage.objectAdmin` on the bucket and `roles/secretmanager.secretAccessor`. Each command is guarded with a describe-or-create.
  - `push-secrets.sh`: for each name in `CRUSTDATA_API_KEY ANTHROPIC_API_KEY RESEND_API_KEY DATABASE_URL SESSION_SECRET`, creates the secret if missing and adds a version from the env var read from `.env` via `printf %s "$VAL" | gcloud secrets versions add NAME --data-file=-`. It never echoes values and skips empty ones with a warning.
  - Neon (via the Neon MCP): project `dealproof` in the region nearest Mumbai (check `list_regions`; prefer an `ap-south-1` region, else `aws-ap-southeast-1`). Branches `main` (prod), `dev` and `test`. Write `DATABASE_URL` (dev) and `TEST_DATABASE_URL` (test) into the local `.env` without printing them. Record the project id and branch names (not credentials) in `infra/README.md`.
- **Verify:** run `bash infra/gcp/bootstrap.sh` twice; the second run makes no changes. `gcloud storage buckets describe gs://cc-g527-showproduct-dealproof-uploads --format='value(lifecycle_config)'` shows the age-30 delete rule. `gcloud secrets list --filter='name~CRUSTDATA_API_KEY'` returns 1 row.
- **Acceptance:** the scripts are committed and the resources exist. `.env` is untouched in git.

### CP-09: Design system in code
- **Owner:** Fable design · **Deps:** 0b (`docs/design/`) · **Parallel with:** CP-01, CP-08, then the W2 Opus checkpoints
- **Goal:** Turn 0b's tokens and direction into Tailwind theme and primitives that every page reuses. Use the `unslop` skill. Inspiration: dealroom.co, dealroom.net, sarvam.ai home.
- **Paths:** `apps/web/app/globals.css`, Tailwind config/theme files, `apps/web/components/ui/*`, `apps/web/lib/motion.ts`, `apps/web/app/(dev)/kitchen-sink/page.tsx`, `apps/web/package.json` (add `motion` and any icon set chosen in `docs/design/`)
- **Primitives required** (the names are the contract later pages import): `Button`, `Input`, `Textarea`, `Select`, `Card`, `Tabs`, `Table`, `Dialog`, `Toast`, `Skeleton`, `SourceChip` (provider label + as-of date; click opens a popover with quote/field, URL and retrieved_at), `ClaimStatusBadge` (all six statuses, colour **and** text/shape; `not_checked` visually distinct from every clean status, e.g. hatched or outlined with its reason), `DispositionBadge` (four outcomes), `FitMeter` (always renders "Fit 82 · 70% of criteria assessable"; "Fit — · 0% assessable" when null), `EstimateTag` ("estimate" or "signal" label), `CriterionChip` (must/preference, pass/fail/unknown), `RunProgress` (step list driven by `StepOut[]`, animated, respects `prefers-reduced-motion`), `EmptyState`, `DiffLine`.
- **Acceptance:** `/kitchen-sink` renders every primitive in every state, including all six claim statuses side by side. A keyboard focus ring is visible. Reduced motion disables non-essential animation. The unslop checklist is applied and its findings are noted in the commit body.
- **Verify:** `pnpm --filter web lint && pnpm --filter web build`; a Terra browser check of `/kitchen-sink` at 375 px and 1440 px (screenshots attached to the review).

### CP-10: Marketing home page
- **Owner:** Fable design · **Deps:** CP-09 · **Parallel with:** W2 Opus checkpoints, CP-26
- **Goal:** A home page inspired by sarvam.ai's home. It explains Discover → Verify → Evaluate → Act, shows a claim ledger built from the PRD illustration and labelled "Illustration, not a real company", and has CTAs to sign in and start a thesis. Copy comes from the PRD (tagline: "Discover opportunities. Verify the evidence. Evaluate with confidence."). No invented metrics or customer logos.
- **Paths:** `apps/web/app/(marketing)/page.tsx`, `apps/web/app/(marketing)/layout.tsx`, `apps/web/components/marketing/*`
- **Acceptance:** unslop pass done; the illustration label is visible next to the ledger; it is responsive and passes a Lighthouse accessibility score ≥ 95 (Terra run).
- **Verify:** `pnpm --filter web build`; Terra browser pass.

---

# Phase 2: Platform services

### CP-11: Job engine: runs, steps, worker, SSE, resume
- **Owner:** Opus implementation · **Deps:** CP-02, CP-03 · **Parallel with:** CP-12 to CP-16, CP-26
- **Paths:** `apps/api/app/jobs/{__init__,engine,worker,events}.py`, `apps/api/app/pipelines/{discover,investors,verify_identity,claims_intake,evidence,evaluate,act,recheck,maintenance}.py` (stub modules with a docstring and an empty `register()`), `apps/api/app/pipelines/registry.py`, `apps/api/app/api/runs.py`, `apps/api/app/main.py` (lifespan only), `apps/api/tests/jobs/*`
- **Interfaces:**
  - `@step_handler("discover.search")` decorator registers `async def handler(ctx: StepContext) -> dict`.
  - `StepContext` has `run`, `step`, `session`, `crustdata` (a budget-bound client), `llm`, `ledger`, `log(msg)`, and `budget_remaining() -> float`.
  - `create_run(session, kind, *, case_id=None, thesis_id=None, investor_search_id=None, steps: list[StepSpec], budget_credits, created_by) -> Run`. `StepSpec(key, input, depends_on: list[str])`.
  - `append_steps(session, run_id, steps)` lets handlers fan out, e.g. one evidence step per claim.
  - Worker: `async def worker_loop(stop: asyncio.Event)` claims one ready step (pending, all deps done) with `FOR UPDATE SKIP LOCKED`, sets `lease_until = now()+120s`, renews it every 30 s, and marks the step done or failed (up to 3 attempts with exponential backoff). A `BudgetExceeded` exception marks the step `skipped_budget`. On boot it re-queues `running` steps whose lease has expired. A run is `done` when every step is terminal.
  - `registry.py` imports every pipeline module and calls `register()`.
- **Tests:** `test_steps_run_in_dependency_order`; `test_resume_after_lease_expiry` (simulate a crash: the step is left `running` with an expired lease, a new worker picks it up, and the handler sees `attempts == 2`); `test_skip_locked_two_workers_no_double_claim`; `test_budget_exceeded_marks_skipped`; `test_sse_emits_step_changes` (httpx AsyncClient reads 2 events).
- **Verify:** `uv run pytest tests/jobs -q`.

### CP-12: Crustdata client (cached, metered, budgeted, rate-limited)
- **Owner:** Opus implementation · **Deps:** CP-02 · **Parallel with:** CP-11, CP-13 to CP-16
- **Paths:** `apps/api/app/clients/crustdata.py`, `apps/api/app/cache.py`, `apps/api/app/ledger.py`, `apps/api/tests/clients/test_crustdata.py`, `apps/api/tests/fixtures/crustdata/*.json`, `apps/api/tests/live/test_crustdata_smoke.py`
- **Interfaces:**
  - `ledger.record(session, *, provider, endpoint, credits=0, input_tokens=0, output_tokens=0, usd=0, cached, case_id, run_id, step_id) -> None`; `ledger.case_totals(session, case_id) -> CostTotals`; `ledger.spent(session, run_id) -> float`.
  - `cache.get_or_call(session, provider, endpoint, request: dict, call: Callable[[], Awaitable[CachedResponse]]) -> CachedResponse`. The hash is sha256 of canonical JSON of (provider, endpoint, request). A cache hit costs 0 credits.
  - `CrustdataClient(session, settings, *, budget: Budget, ctx_ids)` with methods: `identify(*, domains=None, names=None) -> list[IdentifyResult]`; `enrich(ids: list[int], fields: list[str]) -> list[dict]`; `search(*, filters=None, query=None, mode="hybrid", fields, limit) -> SearchPage`; `autocomplete(field, query) -> list[str]` (free); `person_search(filters, fields, limit) -> list[dict]`; `job_search(company_id, limit=10) -> list[dict]`; `web_search(query, *, sources, location="IN", start_date=None, end_date=None, site=None) -> list[WebResult]`; `web_fetch(urls: list[str]) -> list[FetchResult]`. Every method records `X-Credits-Used` (absent means 0), writes a `sources` row (provider "crustdata", endpoint, request, retrieved_at) and returns the `source_id` alongside its data.
  - `Budget(limit, spent)`: estimate cost before a call (identify 0.2 × ids; enrich 2 × ids; search per-result price × limit; web 1 × pages/urls). Raise `BudgetExceeded` when the estimate exceeds the remainder. After the call, the actual header value is recorded.
  - `normalise_company(company_data: dict) -> dict` returns the keys listed in CP-04 plus `crustdata_company_id`, `domain`, `website`, `headcount_series`, `funding_rounds`, `investors`, `hiring`, `people`, `news`, `locations`, `field_sources`: a map from key to Crustdata field path, so evidence rows can cite it.
  - Errors: `CrustdataPlanError` (403), `CrustdataCreditsError` (402), `SemanticSearchUnavailable` (403 with "semantic search"), retry with backoff on 429/5xx (max 4). The per-endpoint token bucket follows builder call 3.
- **Tests** (respx mocks plus recorded fixtures): `test_headers_sent` (bearer + `x-api-version: 2025-11-01`); `test_credits_header_recorded`; `test_cached_call_costs_zero`; `test_budget_blocks_before_call`; `test_semantic_403_raises_specific_error`; `test_web_fetch_failure_correlation` (`url: null` entries map back to the requested URL); `test_normalise_company_funding_date_fallback`.
- **Live smoke** (`RUN_LIVE_SMOKE=1` only; total about 2.5 credits): identify one well-known Indian logistics domain; enrich that id with `["basic_info","funding","headcount","people","hiring","locations","news"]` and save the JSON to `tests/fixtures/crustdata/enrich_live_sample.json` (scrub nothing personal beyond what the response has; it is public company data); run an NL `search` with limit 1. Record in the commit body whether NL search is enabled for this key.
- **Verify:** `uv run pytest tests/clients/test_crustdata.py -q`; for the smoke, `RUN_LIVE_SMOKE=1 uv run pytest tests/live -q`.

### CP-13: LLM client + prompts
- **Owner:** Opus implementation · **Deps:** CP-02 (ledger from CP-12: depend on the `ledger.record` signature above; if CP-12 is not merged yet, add `ledger.py` only if missing, with exactly that signature, and coordinate on rebase) · **Parallel with:** CP-11, CP-12, CP-14 to CP-16
- **Paths:** `apps/api/app/clients/llm.py`, `apps/api/app/clients/prompts/{criteria.md,claims.md,facts.md,seller_email.md,redaction_note.md}`, `apps/api/app/clients/llm_models.py` (Pydantic output models), `apps/api/tests/clients/test_llm.py`
- **Interfaces:** `LlmClient(session, settings, ctx_ids)`; `extract(prompt_name: str, variables: dict, output: type[T]) -> T` (cached through `cache.get_or_call` with provider "anthropic"; records tokens and USD from the `PRICES` table `{"claude-haiku-5-5": (0.10, 0.50, 0.50, 2.50)}` = (input, output, input above 100K, output above 100K) per MTok; raises `LlmRefusal` on `stop_reason == "refusal"` and `LlmTruncated` on `max_tokens`); `draft(prompt_name, variables) -> str`.
- **Output models:** `CriteriaOut{criteria: [CriterionDraft{label, kind, dimension, operator, value, crustdata_filter|None}]}`; `ClaimsOut{claims: [ClaimDraft{text, category, components: dict, quote, page|None, material: bool}]}`; `FactsOut{facts: [FactDraft{component, value, relation, quote, as_of|None, stage|None}]}`.
- **Prompt rules:** system prompts say to use only the supplied text, return verbatim quotes, and never use outside knowledge. The criteria prompt includes the CP-04 operator list, the allowed Crustdata filter fields (from External APIs) and the rule "if not mappable, set crustdata_filter null". No few-shot examples with real company names.
- **Tests:** `test_model_from_env` (uses `settings.anthropic_model`); `test_no_temperature_sent` (inspect the mocked request body); `test_usage_recorded_with_usd`; `test_cache_hit_no_call`; `test_refusal_raises`.
- **Live smoke** (`RUN_LIVE_SMOKE=1`): `extract("criteria", {thesis: <the PRD logistics thesis>}, CriteriaOut)` returns at least 3 criteria, at least one of them `must`.
- **Verify:** `uv run pytest tests/clients/test_llm.py -q`.

### CP-14: Email + storage clients
- **Owner:** Opus implementation · **Deps:** CP-02 · **Parallel with:** CP-11 to CP-13, CP-15, CP-16
- **Paths:** `apps/api/app/clients/email.py`, `apps/api/app/clients/storage.py`, `apps/api/tests/clients/test_email.py`, `apps/api/tests/clients/test_storage.py`
- **Interfaces:** `EmailClient(settings).send(*, to, subject, text, html=None, reply_to=None, idempotency_key) -> EmailResult{status: "sent"|"suppressed_test_mode"|"failed", provider_message_id|None, error|None}`. When `EMAIL_SEND_ENABLED` is false it makes no network call and returns `suppressed_test_mode`. Otherwise it sends `POST https://api.resend.com/emails` with an `Idempotency-Key` header. `Storage(settings).put(path, data: bytes, content_type) -> str`, `.get(path) -> bytes`, `.delete(path)`. If `GCS_BUCKET` is empty, a local-disk backend under `apps/api/.data/uploads/` is used for development (git-ignored).
- **Tests:** `test_disabled_flag_makes_no_http_call` (respx asserts zero calls); `test_idempotency_header_sent`; `test_provider_error_returns_failed`; `test_local_storage_roundtrip`.
- **Verify:** `uv run pytest tests/clients/test_email.py tests/clients/test_storage.py -q`.

### CP-15: Document text, PII redaction, quote verification, HTML to text
- **Owner:** Opus implementation · **Deps:** CP-01 · **Parallel with:** CP-02 to CP-07 (W2) and CP-11 to CP-14, CP-16 (W3)
- **Paths:** `apps/api/app/documents/{__init__,extract,redact,quotes,html}.py`, `apps/api/tests/documents/*`, `apps/api/tests/fixtures/docs/` (small generated PDF/PPTX/DOCX built in test setup with fictional text; no binary blobs from the internet)
- **Interfaces:** `extract_text(data: bytes, mime: str) -> list[PageText{page: int|None, text: str}]`; `redact(text) -> tuple[str, dict[str, int]]` (builder call 18); `quote_in(quote: str, text: str) -> bool` (whitespace-normalised, case-folded, typographic quotes and dashes unified); `html_to_text(html: str) -> str`; `chunk(text, max_chars=40000) -> list[str]` (splits on paragraph boundaries).
- **Tests:** `test_pdf_pages`, `test_pptx_slide_numbers`, `test_docx_paragraphs`; `test_redacts_email_phone_pan_aadhaar` (each kind is counted); `test_quote_must_appear_verbatim` (an invented quote returns False, a whitespace-variant quote returns True); `test_html_strips_nav_script`; `test_chunk_never_drops_text` (the joined chunks equal the original).
- **Verify:** `uv run pytest tests/documents -q`.

### CP-16: Auth (named users, sessions)
- **Owner:** Opus implementation · **Deps:** CP-02, CP-03 · **Parallel with:** CP-11 to CP-15, CP-26
- **Paths:** `apps/api/app/auth/{__init__,passwords,sessions,deps}.py`, `apps/api/app/api/auth.py`, `apps/api/app/cli.py`, `apps/api/tests/auth/*`
- **Interfaces:** `current_user` FastAPI dependency (401 without a valid `dp_session`); `python -m app.cli create-user --email E --name N` (prompts for the password with `getpass`; never takes it as an argument). Every non-auth router except `/health` and `/policy` depends on `current_user`. This checkpoint adds that dependency in `router.py` at include time, which is the only `router.py` edit.
- **Tests:** `test_login_sets_cookie`; `test_bad_password_401`; `test_protected_route_requires_session`; `test_logout_invalidates`.
- **Verify:** `uv run pytest tests/auth -q`.

---

# Phase 3: Pipelines (all Opus implementation)

Every pipeline step that creates a displayed fact writes `evidence` rows that link to the `sources` row returned by the client.

### CP-17: Discover pipeline (thesis → shortlist)
- **Deps:** CP-04, CP-11, CP-12, CP-13 · **Parallel with:** CP-18, CP-19, UI checkpoints
- **Paths:** `apps/api/app/pipelines/discover.py`, `apps/api/app/api/theses.py`, `apps/api/tests/pipelines/test_discover.py`, `apps/api/tests/fixtures/crustdata/discover_*.json`
- **Flow:**
  - `POST /theses` calls `llm.extract("criteria")`, stores the criteria and returns the thesis. `PUT /theses/{id}/criteria` replaces them and marks them `edited`.
  - `POST /theses/{id}/search` creates run `discover` with steps:
    1. `discover.search`: build filters from must-haves that have a `crustdata_filter` (combined with `and`) and `query` = the thesis text; limit 50; fields `basic_info, locations, taxonomy`. If fewer than 15 results, a second query drops the preference filters. On `SemanticSearchUnavailable`, use filters only, with `basic_info.industries` values resolved through autocomplete.
    2. `discover.dedupe_gate`: dedupe by id, then by domain; `must_have_gate` on the search fields.
    3. `discover.enrich`: preliminary rank by fit; enrich the top 15 in one call with fields `basic_info, funding, headcount, hiring, locations, taxonomy, news`.
    4. `discover.score`: re-run the criteria on the enriched data; compute fit and assessable%.
    5. `discover.cards`: write `shortlist_items` with a card holding business, location, headcount + growth as `Fact` with `is_estimate`, funding rounds, hiring activity, reasons (criteria met, with evidence ids), unknowns (criteria unknown, plus missing fields) and per-item `as_of`/`retrieved_at`.
  - Budget `DISCOVER_CREDIT_BUDGET`.
- **Tests** (fixtures, no live calls): `test_shortlist_ranked_by_fit_then_assessable`; `test_failed_must_excluded_with_reason`; `test_unknown_must_kept`; `test_every_card_fact_has_source` (walk the card and assert every `Fact` has a source_id that exists); `test_semantic_fallback_path`; `test_spend_under_budget` (sum of ledger ≤ 60 in the fixture run).
- **Verify:** `uv run pytest tests/pipelines/test_discover.py -q`.

### CP-18: Investor discovery pipeline
- **Deps:** CP-07, CP-11, CP-12 · **Parallel with:** CP-17, CP-19
- **Paths:** `apps/api/app/pipelines/investors.py`, `apps/api/app/api/investors.py`, `apps/api/tests/pipelines/test_investors.py`
- **Flow:** steps
  1. `investors.comparables`: `company_search` with filters for industry (autocomplete-resolved), `locations.country`, headcount band from size, and `funding.last_round_type in <stage and the adjacent stages>`; `query` = the sector text; limit 50; fields `basic_info, locations`.
  2. `investors.enrich`: enrich the top 25 by id with `funding` and `basic_info`.
  3. `investors.rank`: `collect_rounds` → `group_by_investor` → `rank_investors` → write `investor_entries`.
  - No contact details are fetched (person endpoints are never called here). Budget `INVESTOR_CREDIT_BUDGET`.
- **Tests:** `test_only_dated_named_rounds`; `test_entry_lists_backing_evidence` (every comparable round has a source_ref); `test_no_person_endpoints_called` (respx asserts no `/person/*`).
- **Verify:** `uv run pytest tests/pipelines/test_investors.py -q`.

### CP-19: Verify A: case creation, identity, registry evidence, profile
- **Deps:** CP-11, CP-12, CP-13, CP-15 · **Parallel with:** CP-17, CP-18
- **Paths:** `apps/api/app/pipelines/verify_identity.py`, `apps/api/app/api/cases.py` (create, list, identity select, verify), `apps/api/tests/pipelines/test_verify_identity.py`
- **Flow:** `POST /cases` creates the case and run `verify` with steps:
  1. `verify.identity`: `identify(domains=[website domain])`, then `identify(names=[name])` if needed. **Confirmed** only when the top match's `confidence_score ≥ 0.85`, the next match is below 0.6, and the domain-based and name-based top ids agree (or one input was not given). Otherwise `ambiguous`, with candidates stored. If nothing matches, `not_found`.
  2. `verify.registry` (runs only when confirmed): builder call 9; facts extracted with `llm.extract("facts")` against the claim-independent components `legal_name, incorporation_date, incorporation_place, cin`, with quotes checked by `quote_in`.
  3. `verify.profile`: enrich by id with `basic_info, headcount, funding, people, hiring, locations, taxonomy, news`; snapshot stored in `companies`; `company_type` via `classify_company`.
  4. `verify.people`: leadership people search (builder call 8), matched by company id only.
  5. `verify.jobs`: job search (10 results).
  - When identity is ambiguous, steps 2–5 are created only after `POST /cases/{id}/identity` picks a candidate. Until then those checks are `not_checked` with reason "identity unresolved".
- **Tests:** `test_identity_confirmed_by_domain_and_name`; `test_identity_ambiguous_on_close_scores` (two candidates at 0.82 / 0.79 → ambiguous, no enrich call made); `test_name_only_match_not_confirmed_if_domain_disagrees`; `test_registry_mirror_classification` (`zaubacorp.com` → registry_mirror, `mca.gov.in` → registry_official); `test_people_matched_by_company_id_not_name`.
- **Verify:** `uv run pytest tests/pipelines/test_verify_identity.py -q`.

### CP-20: Verify B: claim intake (documents + typed claims)
- **Deps:** CP-13, CP-14, CP-15, CP-19 · **Parallel with:** UI checkpoints
- **Paths:** `apps/api/app/pipelines/claims_intake.py`, `apps/api/app/api/documents.py`, `apps/api/app/api/claims.py`, `apps/api/tests/pipelines/test_claims_intake.py`
- **Flow:**
  - `POST /cases/{id}/documents`: checks size against `MAX_UPLOAD_MB` and the mime type; stores the file at `cases/<case>/<doc>/<filename>`; `delete_after = now + UPLOAD_RETENTION_DAYS`. Then it appends steps to the case's active verify run, or creates a `recheck` run when kind is `seller_response` (CP-24 owns the recheck steps):
    1. `claims.extract_text:<doc>`: extract text, redact, store the redacted text and redaction counts.
    2. `claims.extract:<doc>`: per chunk, `llm.extract("claims")`. Keep a claim only if `quote_in(quote, page_text)`. Dedupe near-identical claims by normalised text.
  - `POST /cases/{id}/claims` stores a typed claim (origin `typed`; category and components via `llm.extract("claims")` on the single sentence, with the quote being the sentence itself).
  - Claims in categories with no v1 source (customer_partnership, financials, debt_security) are still created, never dropped.
- **Tests:** `test_unquoted_claims_dropped`; `test_pii_redacted_before_llm` (the mocked LLM request body contains no email or phone); `test_upload_too_large_413`; `test_unsupported_type_415`; `test_all_categories_kept`.
- **Verify:** `uv run pytest tests/pipelines/test_claims_intake.py -q`.

### CP-21: Verify C: evidence gathering, fact extraction, statuses, events, comparables
- **Deps:** CP-05, CP-19, CP-20 · **Parallel with:** UI checkpoints
- **Paths:** `apps/api/app/pipelines/evidence.py`, `apps/api/tests/pipelines/test_evidence.py`
- **Flow:**
  - After intake, fan out one `evidence.claim:<claim_id>` step per claim. The category routes to:
    - team_size → headcount Facts (`headcount_estimate`)
    - leadership_history → people/profile experience (`professional_profile`) for the named person, matched within confirmed-company results by person id plus name
    - funding → enrich milestones (`funding_database`), plus `web_search(sources=["news"])` for the round (`news` or `company_announcement`, decided by whether the publisher domain equals the company domain)
    - dated_event → `web_search` news + `web_fetch` on the top 2 (publish date as `as_of`)
    - identity_incorporation / location → registry facts + profile HQ
    - customer_partnership / financials / debt_security → one `web_search`; if nothing adequate turns up, the outcome is `cannot_verify` with `settle_with`
  - Evidence text goes to `llm.extract("facts")` with the claim's components; quotes are verified.
  - Facts are converted to `EvidenceFact`, then `decide_status` runs and a `claim_checks` row is appended. On `BudgetExceeded` or source failure the outcome is `not_checked` with reason "budget reached" or "source unavailable: <endpoint>".
  - `evidence.events`: dated items from enrich `news[]` plus fetched articles → `events` (each with an evidence id). `evidence.comparables` follows builder call 23 using one `company_search` (limit 10) with filters only.
- **Tests:** `test_budget_exhaustion_marks_not_checked`; `test_team_size_estimate_never_supports_payroll_claim`; `test_leadership_requires_company_id_match`; `test_funding_news_classified_announcement_vs_news`; `test_events_have_dates_and_evidence`; `test_no_fair_comparison_returns_empty_with_reason`.
- **Verify:** `uv run pytest tests/pipelines/test_evidence.py -q`.

### CP-22: Evaluate pipeline + assessment versions
- **Deps:** CP-06, CP-21 · **Parallel with:** UI checkpoints
- **Paths:** `apps/api/app/pipelines/evaluate.py`, `apps/api/app/api/cases.py` (the `GET /cases/{id}/assessments` handler only; coordinate with CP-19's file by appending a handler, with no edits to existing handlers), `apps/api/tests/pipelines/test_evaluate_pipeline.py`
- **Flow:**
  - The step `evaluate.assess` runs last in verify and recheck runs. It builds `EvaluationInputs` from the latest claim checks, identity state, company snapshot and thesis criteria (fit is recomputed with case evidence; without a thesis, fit is "n/a: no thesis" and is not counted in the disposition thresholds, so prioritise is impossible and investigate_further is the ceiling).
  - It calls `evaluate_case`. If `inputs_hash` equals the latest version's, it writes nothing (idempotent). Otherwise it inserts an `AssessmentVersion` with `version = prev + 1`, `diff_from_previous = diff_versions(...)` and `trigger` ("initial verify" | "seller documents <names>" | "manual re-run").
- **Tests:** `test_first_version_created`; `test_same_inputs_no_new_version`; `test_new_evidence_new_version_with_diff_and_prior_kept`; `test_no_thesis_caps_at_investigate_further`.
- **Verify:** `uv run pytest tests/pipelines/test_evaluate_pipeline.py -q`.

### CP-23: Act: request list, draft, named approval, send once
- **Deps:** CP-07, CP-14, CP-16, CP-22 · **Parallel with:** CP-25, UI checkpoints
- **Paths:** `apps/api/app/pipelines/act.py`, `apps/api/app/api/requests.py`, `apps/api/tests/pipelines/test_act.py`
- **Flow:**
  - `POST /cases/{id}/requests` builds items with `build_request_items` from the latest version and drafts `subject`/`body` with `llm.draft("seller_email", {company, items})`. The body lists each document and why it is needed, and contains no unverified facts. Status `draft`, `idempotency_key = uuid4`.
  - `PATCH` is allowed only in `draft` (409 otherwise).
  - `approve` requires `current_user`, a `recipient_email` and a non-empty body. It records `approved_by`, `approved_by_name` and `approved_at`, and sets status `approved`.
  - `send`: in one transaction, `SELECT … FOR UPDATE` the row. If status is not `approved`, return the current state (no second send). Call `EmailClient.send(idempotency_key=…)`, then set `sent`, `suppressed_test_mode` or `failed`. A `failed` request can be retried with the **same** key.
- **Tests:** `test_cannot_send_unapproved`; `test_send_twice_sends_once` (two concurrent `send` calls → one provider call); `test_test_mode_suppressed_status`; `test_approval_records_name_and_time`; `test_draft_contains_every_item`.
- **Verify:** `uv run pytest tests/pipelines/test_act.py -q`.

### CP-24: Recheck on seller documents
- **Deps:** CP-20, CP-22, CP-23
- **Paths:** `apps/api/app/pipelines/recheck.py`, `apps/api/tests/pipelines/test_recheck.py`
- **Flow:** a `recheck` run for an uploaded `seller_response`:
  1. Extract text and claims (reusing the CP-20 handlers).
  2. For each request item the document answers (`answers_request_item_ids`), run `llm.extract("facts")` for each linked claim against the document text. The facts get class `seller_document` and the document's page quotes.
  3. Run `decide_status` again for the affected claims only, appending `claim_checks`.
  4. Run `evaluate.assess` → a new version with a diff whose `because` cites "<filename>, p. N".
- **Tests:** `test_payroll_doc_moves_team_size_to_supported` (the PRD 250-employees claim plus a fixture payroll page that states 250 → supported; disposition change recorded); `test_unrelated_claims_untouched`; `test_previous_version_still_readable`.
- **Verify:** `uv run pytest tests/pipelines/test_recheck.py -q`.

### CP-25: Case memo aggregate, cost summary, policy endpoint, retention sweep
- **Deps:** CP-22 · **Parallel with:** CP-23, CP-24
- **Paths:** `apps/api/app/pipelines/maintenance.py`, `apps/api/app/api/policy.py`, `apps/api/app/services/case_detail.py`, `apps/api/app/api/cases.py` (the `GET /cases/{id}` handler only, appended), `apps/api/tests/test_case_detail.py`, `apps/api/tests/test_retention.py`
- **Flow:**
  - `build_case_detail(session, case_id) -> CaseDetail`, sections in PRD order: opportunity and thesis relevance (criteria results); identity/profile; claim ledger with history; events; comparables or the "no fair comparison" reason; financial evaluation, or its absence reason; risks/assumptions/unknowns (gaps + estimates used + not_checked list); recommended next step and reasons (latest disposition); request list; full source record (every `sources` row with request/URL and retrieved_at); cost (`ledger.case_totals`); documents with their `delete_after`.
  - `GET /policy` serialises `app.policy` (weights, thresholds, adequacy table, required checks, company-type rule text, `POLICY_VERSION`).
  - Maintenance: the worker loop calls `retention_sweep()` hourly. It purges `extracted_text` past `delete_after` and deletes the storage object (idempotent).
- **Tests:** `test_case_detail_sections_complete`; `test_every_fact_in_detail_has_source` (a recursive walk); `test_cost_totals_match_ledger`; `test_retention_purges_text_and_object`.
- **Verify:** `uv run pytest tests/test_case_detail.py tests/test_retention.py -q`.

---

# Phase 4: Product UI (all Fable design; `unslop` on every pass; fixtures first)

Shared acceptance for every UI checkpoint:
- Builds with `pnpm --filter web build`.
- Uses only `components/ui` primitives plus its own area components.
- Every fact renders a `SourceChip`. Every estimate renders an `EstimateTag`. `FitMeter` always shows assessable %.
- Statuses use colour **and** text.
- Works at 375 px and 1440 px. Respects reduced motion.
- Loading, empty and error states are designed.
- A Terra browser pass (GPT-6.1 Terra, medium or high effort) attaches screenshots to the review.
- Runs on fixtures (`NEXT_PUBLIC_API_MODE=fixtures pnpm --filter web dev`). If the backend checkpoint for the page is merged, it also runs live.

### CP-26: App shell, sign-in, cases dashboard
- **Deps:** CP-03, CP-09 · **Parallel with:** W3
- **Paths:** `apps/web/app/(auth)/login/page.tsx`, `apps/web/app/(app)/layout.tsx`, `apps/web/app/(app)/cases/page.tsx`, `apps/web/components/shell/*`, `apps/web/components/cases/CaseList*.tsx`, `apps/web/middleware.ts` (redirects to `/login` when `/api/auth/me` returns 401)
- **Goal:** Navigation (Discover, Investors, Cases, Scoring policy) and the signed-in user's name, which also appears in approvals. The cases list shows disposition, fit + assessable and cost per case.

### CP-27: Discover UI (thesis → criteria editor → live progress → shortlist)
- **Deps:** CP-26 · **Parallel with:** CP-28, CP-29
- **Paths:** `apps/web/app/(app)/discover/**`, `apps/web/components/discover/*`
- **Goal:** Write a thesis; review and edit criteria (must vs preference, value, "assessed from evidence" marker); start the search; watch `RunProgress` over SSE; open the shortlist as cards (business, location, size and growth estimates, funding history, hiring, reasons with evidence, unknowns, last updated). "Open case" on a card calls `createCase({shortlist_item_id})`.

### CP-28: Investor discovery UI
- **Deps:** CP-26 · **Parallel with:** CP-27, CP-29
- **Paths:** `apps/web/app/(app)/investors/**`, `apps/web/components/investors/*`
- **Goal:** A business profile form (sector, location, stage, size, funding sought) → progress → ranked investors. Each entry shows its comparable companies, round and date with source, last sector investment, why, and unknowns. Visible note: "Ranking describes past behaviour, not a prediction. No personal contact details are collected."

### CP-29: Case view A: layout, overview (memo), identity, claim ledger, sources
- **Deps:** CP-26 · **Parallel with:** CP-27, CP-28
- **Paths:** `apps/web/app/(app)/cases/[id]/layout.tsx` (tabs: Overview, Identity, Claims, Events, Comparables, Assessment, Act, Sources, Cost; it owns the tab list), `apps/web/app/(app)/cases/[id]/{page.tsx,identity,claims,sources}/**`, `apps/web/components/case/{Memo,Identity,ClaimLedger,SourceRecord}*.tsx`, `apps/web/app/(app)/cases/new/page.tsx` (name + website entry)
- **Goal:**
  - The overview reads as the memo in the PRD's "finished case" order.
  - Identity shows the matching keys, or, when ambiguous, a candidate picker that calls `POST /cases/{id}/identity`.
  - The claim ledger lists each claim with status badge, reason, exact evidence quotes with dates, settle-with, and expandable history. `not_checked` rows are visually distinct and show their reason.
  - Sources is the reproducible record table.
  - Claim upload and typed-claim entry live on the Claims tab.

### CP-30: Case view B: events, comparables, assessment + history diff, cost
- **Deps:** CP-29 · **Parallel with:** CP-31, CP-32
- **Paths:** `apps/web/app/(app)/cases/[id]/{events,comparables,assessment,cost}/**`, `apps/web/components/case/{Timeline,Comparables,Assessment,VersionDiff,CostPanel}*.tsx`
- **Goal:** The five judgments as five separate panels (never one combined score). A disposition with reasons. A version picker with an animated diff ("Partially corroborated → Supported because <document, page>"). Cost: "This case cost N Crustdata credits, $X model usage", with a per-step breakdown.

### CP-31: Act UI: request list, draft editing, named approval, send, seller upload + recheck
- **Deps:** CP-29 · **Parallel with:** CP-30, CP-32
- **Paths:** `apps/web/app/(app)/cases/[id]/act/**`, `apps/web/components/act/*`
- **Goal:**
  - Request items, each with its reason.
  - An editable draft with a recipient field the user types in.
  - An approve button that shows "Approved by <name> at <time>".
  - A send button that disables itself and shows the terminal state. `suppressed_test_mode` displays "Not sent: test mode is on".
  - A "Seller documents arrived" upload that lets the user tick the request items each document answers, then shows recheck progress and links to the new assessment diff.

### CP-32: Scoring policy page + print-friendly memo
- **Deps:** CP-26 · **Parallel with:** CP-30, CP-31
- **Paths:** `apps/web/app/(app)/policy/**`, `apps/web/app/print.css` (imported by the case layout), `apps/web/components/policy/*`
- **Goal:** Render `GET /policy` in readable form: weights, thresholds, adequacy table, required checks, company-type rule and policy version. Print CSS produces a clean memo PDF through the browser's print dialog (tabs flattened, chips print their source text).

---

# Phase 5: Integrate, deploy, demo

### CP-33: Live integration pass (local, real APIs)
- **Owner:** Opus implementation · **Deps:** CP-17 to CP-32
- **Goal:** Run the full flow locally (`pnpm dev` for both apps, `NEXT_PUBLIC_API_MODE=live`) on the PRD logistics thesis: discover → open the top case → verify → request → approve → send (test mode) → upload a fictional "(fixture)" payroll PDF → recheck → diff. Fix backend and contract mismatches. Every UI defect goes into `docs/superpowers/plans/ui-issues.md` for Fable (CP-38). Expected spend is at most 250 credits; stop and report if it exceeds 300.
- **Paths:** backend files as needed (smallest fixes), `apps/web/lib/api/schema.ts` (regenerated), `docs/superpowers/plans/ui-issues.md`
- **Verify:** `uv run pytest -q` and `pnpm --filter web build` both green. A Terra browser walkthrough records every page reached with live data.

### CP-34: Deploy API to Cloud Run
- **Owner:** Opus implementation · **Deps:** CP-08, CP-33
- **Paths:** `infra/deploy.sh` (api part), `apps/api/Dockerfile` (adjust only if needed), `infra/README.md`
- **Steps:**
  - Run `infra/gcp/push-secrets.sh` with the Neon **main** branch `DATABASE_URL` (via the Neon MCP; written to a temporary env file deleted afterwards).
  - Build with `gcloud builds submit apps/api --tag asia-south1-docker.pkg.dev/cc-g527-showproduct/dealproof/api:$GIT_SHA`.
  - Run migrations as a one-off Cloud Run job, `dealproof-migrate` (`alembic upgrade head`).
  - `gcloud run deploy dealproof-api --region asia-south1 --service-account dealproof-api@… --min-instances 1 --no-cpu-throttling --timeout 3600 --set-secrets CRUSTDATA_API_KEY=CRUSTDATA_API_KEY:latest,…` with env `EMAIL_SEND_ENABLED=false`, `GCS_BUCKET`, `ANTHROPIC_MODEL=claude-haiku-5-5`, `WEB_ORIGIN=<web url>` (updated after CP-35) and `--allow-unauthenticated`.
  - Create the first user with `python -m app.cli create-user` run as a Cloud Run job, or locally against the prod DB URL without printing it.
- **Risk:** if org policy blocks `allUsers`, stop and ask the user (alternatives: IAP, or putting web and api behind one load balancer).
- **Verify:** `curl -fsS <api-url>/health` returns `{"status":"ok"}`; `curl -fsS <api-url>/policy` returns the policy version.

### CP-35: Deploy web to Cloud Run
- **Owner:** Opus implementation · **Deps:** CP-34
- **Paths:** `apps/web/Dockerfile` (Next `output: "standalone"`), `apps/web/next.config.*` (standalone only), `infra/deploy.sh` (web part)
- **Steps:** build with Cloud Build; `gcloud run deploy dealproof-web --region asia-south1 --set-env-vars API_BASE_URL=<api-url>,NEXT_PUBLIC_API_MODE=live --allow-unauthenticated`. Then update the API's `WEB_ORIGIN`.
- **Verify:** `curl -fsS <web-url>/` returns 200; `curl -fsS <web-url>/api/policy` passes through. A Terra pass signs in on prod. Check that the fixtures bundle is absent: `grep -r "(fixture)" .next/` in the image build log returns nothing, because fixtures are only imported when the mode is `fixtures`, via dynamic import.

### CP-36: Playwright smoke suite
- **Owner:** Opus implementation · **Deps:** CP-35. **Ask the user first** before downloading Playwright browser binaries (builder call / process rule 7). If declined, Terra browser passes stand in.
- **Paths:** `apps/web/e2e/*.spec.ts`, `apps/web/playwright.config.ts`, `apps/web/package.json` (dev dep `@playwright/test`)
- **Tests** (fixture mode, locally and in CI): sign-in; thesis → criteria → shortlist; open case → ledger shows all six status styles; approve → send shows test-mode suppressed; policy page renders.
- **Verify:** `pnpm --filter web exec playwright test`.

### CP-37: Production demo run (logistics thesis)
- **Owner:** Opus implementation, with a Terra browser pass · **Deps:** CP-35
- **Goal:** On prod, run the ContextCon flow end to end with live data and leave the resulting cases in place for the demo. Capture screenshots in `docs/demo/` and a short `docs/demo/runbook.md` (click path, expected timings, credit cost per case from the cost panel). No fabricated companies. If the shortlist is thin, adjust criteria in the UI, not the data.
- **Verify:** the runbook lists the real case URLs and costs. The Astra product-adherence review runs against the PRD here.

### CP-38: Polish pass
- **Owner:** Fable design · **Deps:** CP-37 (and `ui-issues.md`)
- **Goal:** Run `unslop` over every page. Resolve `ui-issues.md`. Tune motion (run progress, ledger reveal, assessment diff). Tighten copy to the PRD's voice and check consistency against `docs/design/`. Primitive files may be edited here.
- **Verify:** `pnpm --filter web build`, the Playwright smoke (if installed), and a Terra pass at 375 px and 1440 px on prod after redeploying web via `infra/deploy.sh web`.

### CP-39: Final review + release tag
- **Owner:** Opus implementation · **Deps:** CP-38
- **Goal:**
  - Run a whole-repo GPT-6.2 Sol review and fix its findings.
  - Confirm every anti-goal in spec §2 has a test or check, and list them in `docs/superpowers/plans/release-checklist.md`.
  - Redeploy both services and tag `v1-contextcon`.
- **Verify:** `uv run pytest -q`, `pnpm -r lint`, `pnpm -r build`, and prod `/health` all green; the tag is pushed.

---

## Self-review notes (run by the planner)

- **Spec coverage:** §6.1 → CP-04, CP-17, CP-27; §6.2 → CP-07, CP-18, CP-28; §6.3 → CP-05, CP-15, CP-19, CP-20, CP-21, CP-29; §6.4 → CP-06, CP-22, CP-30; §6.5 → CP-07, CP-14, CP-23, CP-24, CP-31; §6.6 → CP-25, CP-29, CP-32; §5.1 → CP-11; §5.2 → CP-12, CP-13, CP-25, CP-30; §5.3 → CP-02, CP-03, CP-12; §7 → CP-08, CP-15, CP-25; §8 → CP-09, CP-10, CP-26 to CP-32, CP-38; §9 → the tests in each CP, CP-36; §10 → Process rules. Investor outreach drafts (optional in spec §6.2) are not built in v1; the investor shortlist is the deliverable.
- **Type consistency:** `ClaimOutcome`, `EvidenceFact`, `Criterion`, `CriterionResult` (CP-01) are used unchanged by CP-04/05/06/07/17/21/22. `normalise_company` (CP-12) produces the keys CP-04 consumes. `ledger.record` (CP-12) is shared with CP-13. `StepContext` (CP-11) is used by every pipeline.
