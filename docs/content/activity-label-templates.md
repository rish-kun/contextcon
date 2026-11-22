# DealProof live-run activity label templates

Source of truth: [D-live-run-experience.md](../design/iterations/D-live-run-experience.md) (§1–§4) and [DealProof product description.md](../../DealProof%20product%20description.md).

This file defines the allowlisted templates for every persisted `run_activities` event, the header "now line", and run notices. Backend emission in `apps/api/app/jobs/activity.py` builds every `label` and `detail` strictly from this list.

---

## 1. Confidentiality rules and placeholder allowlist

Activities are stored and replayed, so they hold **public lookup information and the user's own criteria only**.

### Allowed placeholders (public or user-criteria values only)

| Placeholder | Allowed source | Notes |
| --- | --- | --- |
| `{n}`, `{m}`, `{current}`, `{total}` | Integer counts | Never estimated; both numbers must be real |
| `{company}` | Confirmed public entity name, or candidate company name from public search | In case runs before identity is confirmed, always `"the company"` |
| `{other_company}` | Confirmed or public candidate company name | Used for duplicate notes in Discover |
| `{city}` | Public city or location string | E.g. `Pune`, `Bengaluru` |
| `{domain}` | Registrable host, lowercase | E.g. `economictimes.indiatimes.com`; never full path or query string |
| `{criterion}` | User's own criterion label from the thesis | Discover runs only |
| `{filters}` | User's own criteria summarised in words | Discover and Investor runs only, e.g. `India · warehousing` |
| `{claim_category}` | Allowlisted claim category label (see §1.2) | Never the claim text |
| `{claim_number}` | Positive integer ledger index | E.g. `1`, `4` |
| `{status}` | Allowlisted claim status label | `Supported`, `Partially corroborated`, `Conflicting evidence`, `Contradicted`, `Cannot verify`, `Not checked` |
| `{old_status}` | Previous allowlisted claim status label | Recheck runs only |
| `{disposition}` | Allowlisted disposition label | `Prioritise`, `Investigate further`, `Deprioritise`, `Cannot assess` |
| `{version}` | Positive integer assessment version | E.g. `1`, `2` |
| `{investor}` | Public investor organisation name | Never a person's contact details |
| `{round}` | Public funding round label | E.g. `Seed`, `Series A`, `Series B` |
| `{date}` | Formatted public date | E.g. `5 Jun 2025`, `Mar 2025` |
| `{event_kind}` | Allowlisted public event kind label | E.g. `funding`, `expansion`, `leadership`, `launch`, `partnership` |
| `{document_kind}` | Allowlisted generic document kind (see §1.3) | Never the uploaded filename |
| `{step}` | Allowlisted step display label | Never includes a filename |
| `{provider}` | Allowlisted provider name | `Crustdata`, `the model` |
| `{error_reason}` | Allowlisted failure reason in words (see §4.2) | Never raw stack traces or provider bodies |
| `{keys}` | Matched identity key names in words | E.g. `domain and registration number` |
| `{seconds}` | Elapsed idle seconds | Integer |
| `{duration}` | Formatted run duration | E.g. `2 min 51 s` |
| `{credits}`, `{budget}` | Credit totals | Tabular numbers |
| `{usd}` | Model spend formatted in USD | E.g. `$0.04` |
| `{workflow}` | Allowlisted workflow name | `Discover`, `Investor search`, `Verify`, `Recheck`, `Evaluate` |
| `{subject}` | Public run subject | Confirmed company name, `"the company"`, thesis title, or business profile summary |
| `{timestamp}` | Formatted clock or date-time | E.g. `16:51`, `22 Nov 2026, 16:42 IST` |

### Forbidden in all activity fields

Never emit any of the following in `label`, `detail`, `highlights`, `source.title`, or `items`:
- Claim text from a seller deck or typed by an analyst
- Any excerpt or text from an uploaded confidential document
- Uploaded document filenames
- Prompts or unvalidated model outputs
- Search queries or filter bodies generated from confidential case claims
- Request-list item text or email draft text
- Personal contact details (emails, phone numbers, personal addresses)

### 1.2 Allowlisted `{claim_category}` labels

| Key | Display label |
| --- | --- |
| `identity` | `Identity` |
| `incorporation` | `Incorporation` |
| `business_model` | `Business model` |
| `funding` | `Funding` |
| `team_size` | `Team size` |
| `leadership` | `Leadership` |
| `dated_event` | `Dated event` |
| `facility` | `Facility` |
| `customer` | `Customer` |
| `partnership` | `Partnership` |
| `debt` | `Debt` |
| `security_interest` | `Security interest` |
| `litigation` | `Litigation` |
| `financial` | `Financial` |
| `other` | `General` |

### 1.3 Allowlisted `{document_kind}` labels

Used when referencing uploaded files so filenames never enter `run_activities`:

- `presentation`
- `document`
- `spreadsheet`
- `statement`
- `uploaded file`

---

## 2. The "now line" and header phrasing

The header "now line" shows the current work in present participle, plain words, no trailing ellipsis, and no trailing period.

### Header title

- Live run: `Analyst working · {workflow} · {subject}`
- Reduced-motion indicator replacement: `Working`

### Lifecycle states of the now line

| Situation | Template |
| --- | --- |
| Run accepted, before first event | `Starting` |
| Waiting for worker pickup (`≥ 2 s`) | `Waiting for a worker · {seconds} s` |
| Active work | The `label` of the latest `status` event (see §3) |
| Idle gap `8–29 s` (appended to active line) | `{current_now_line} · {seconds} s` |
| Open external call `≥ 30 s` (appended to active line) | `{current_now_line} · still waiting on {provider}` |
| Resumed run tag (beside elapsed clock) | `Resumed {timestamp}` |
| Paused updates control | `Pause updates` / `Resume updates` · chip: `{n} new` |

### Cost meter phrasing

- Default: `{credits} of {budget} cr · {usd}`
- Credit delta cue: `+{n}`
- Cache hit cue: `+0 · cache`
- At 80% of budget: `{credits} of {budget} cr · {usd} · {pct}% left`
- At 100% of budget (hatched): `Budget reached · {credits} of {budget} cr · {usd}`

### Terminal header lines (replace the now line)

| Outcome | Template |
| --- | --- |
| Finished, all checks run | `{workflow} finished · {duration} · {credits} of {budget} credits · {usd}` |
| Finished, with `Not checked` items | `{workflow} finished · {duration} · {credits} of {budget} credits · {usd} · {n} checks not run` |
| Finished, 1 check not run | `{workflow} finished · {duration} · {credits} of {budget} credits · {usd} · 1 check not run` |
| Stopped with failure | `Run stopped · {step} did not finish: {error_reason}` |
| Stopped at identity | `Verify paused · identity needs confirmation before continuing` |
| Replay mode banner (always visible during replay) | `Replay of the run from {timestamp} · nothing is being fetched and no credits are spent` |
| Older run with no stored activity | `Detailed activity was not recorded for this run.` |

---

## 3. Kind `status` templates

Emitted at the start of a unit of work. Drives the now line and the running step's sub-line. Present participle, no trailing ellipsis, no trailing period.

### Discover (`discover.*`)

| Step key | Template (`label`) | Optional `detail` |
| --- | --- | --- |
| `discover.search` | `Resolving filter values` | — |
| `discover.search` | `Searching companies matching {n} criteria` | `{filters}` |
| `discover.search` | `Searching companies with relaxed preferences` | `{filters}` |
| `discover.gate` | `Removing duplicates and must-have failures` | — |
| `discover.enrich` | `Enriching {n} companies` | `funding, headcount, and web traffic` |
| `discover.enrich` | `Reading job postings for {company}` | — |
| `discover.score` | `Applying your criteria to {n} companies` | — |
| `discover.explain` | `Writing why each company is on the list` | — |

### Investor search (`investors.*`)

| Step key | Template (`label`) | Optional `detail` |
| --- | --- | --- |
| `investors.spec` | `Reading the business profile` | — |
| `investors.comparables` | `Searching for comparable companies that raised money` | `{filters}` |
| `investors.enrich` | `Reading funding rounds of {n} companies` | — |
| `investors.rank` | `Grouping investors and ranking by dated comparable rounds` | — |

### Verify (`verify.*`, `claims.*`, `checks.*`, `evaluate`, `request_list`)

| Step key | Template (`label`) | Optional `detail` |
| --- | --- | --- |
| `verify.identity` | `Matching the domain {domain}` | — |
| `verify.identity` | `Matching the company name` | — |
| `verify.profile` | `Reading the company record` | — |
| `verify.registry` | `Searching public registry records` | — |
| `verify.registry` | `Reading {domain}` | — |
| `verify.events` | `Searching dated public events` | — |
| `verify.events` | `Reading {domain}` | — |
| `verify.comparables` | `Searching for comparable companies` | — |
| `claims.extract:*` | `Reading the uploaded {document_kind}` | `page {current} of {total}` |
| `checks.claim:*` | `Checking {claim_category} claim {claim_number}` | — |
| `checks.claim:*` | `Searching professional records for {claim_category} claim {claim_number}` | — |
| `checks.claim:*` | `Searching public records for {claim_category} claim {claim_number}` | — |
| `checks.claim:*` | `Reading {domain}` | `for {claim_category} claim {claim_number}` |
| `checks.claim:*` | `Applying status rules to {claim_category} claim {claim_number}` | — |
| `evaluate` | `Applying the screening rules` | — |
| `request_list` | `Drafting the document request` | — |

### Recheck and Evaluate

| Step key | Template (`label`) | Optional `detail` |
| --- | --- | --- |
| `claims.extract:*` | `Reading the uploaded {document_kind}` | `page {current} of {total}` |
| `checks.claim:*` | `Rechecking {claim_category} claim {claim_number}` | — |
| `checks.claim:*` | `Applying status rules to {claim_category} claim {claim_number}` | — |
| `evaluate` | `Applying the screening rules` | — |

---

## 4. Kind `call` templates

Emitted when an external Crustdata call finishes, returns from cache, or fails. Drives the Crustdata tally and the cost meter. Past tense, plain words.

### 4.1 Successful calls (one per Crustdata endpoint)

| Endpoint | `label` template | `detail` template |
| --- | --- | --- |
| `company_identify` | `Matched {n} identity candidates` (singular: `Matched 1 identity candidate`) | — |
| `company_identify` (0 hits) | `No identity candidates matched` | — |
| `company_search` | `Matched {n} companies` (singular: `Matched 1 company`) | `{filters}` (Discover/Investors) or `null` (Verify) |
| `company_search` (0 hits) | `No companies matched this pass` | `{filters}` or `null` |
| `company_enrich` | `Enriched {n} companies` (singular: `Enriched 1 company`) | `funding, headcount, and web traffic` |
| `company_enrich` (single company) | `Read the company record for {company}` | `{n} field groups` |
| `person_search` | `Read {n} people records` (singular: `Read 1 person record`) | `{m} current leadership` |
| `person_search` (0 hits) | `No people records matched` | — |
| `job_search` | `Read {n} job postings for {company}` (singular: `Read 1 job posting for {company}`) | — |
| `job_search` (0 hits) | `No open job postings found for {company}` | — |
| `web_search` | `Found {n} search results` (singular: `Found 1 search result`) | `{m} news` (when `news_hits > 0`) |
| `web_search` (0 hits) | `No search results found` | — |
| `web_fetch` | `Fetched {n} of {m} pages` | `{k} could not be read` (when `failed > 0`) |

Cache-hit suffix (shown by UI when `call.from_cache` is true): `from cache · 0 cr`.

### 4.2 Failed calls (one per Crustdata endpoint)

| Endpoint | `label` template | `detail` template |
| --- | --- | --- |
| `company_identify` | `Identity lookup did not return` | `Crustdata {error_reason} after {n} tries` |
| `company_search` | `Company search did not return` | `Crustdata {error_reason} after {n} tries` |
| `company_enrich` | `Company enrich did not return` | `Crustdata {error_reason} after {n} tries` |
| `person_search` | `People search did not return` | `Crustdata {error_reason} after {n} tries` |
| `job_search` | `Job search did not return` | `Crustdata {error_reason} after {n} tries` |
| `web_search` | `Web search did not return` | `Crustdata {error_reason} after {n} tries` |
| `web_fetch` | `Page fetch did not return` | `Crustdata {error_reason} after {n} tries` |

Allowlisted `{error_reason}` values:
- `timeout` → `timed out`
- `rate_limit` → `hit a rate limit`
- `http_5xx` → `returned a server error`
- `http_4xx` → `rejected the request`
- `network` → `could not be reached`
- `invalid_response` → `returned an unreadable response`

### 4.3 Tally highlight and headline templates

Tally row highlight templates (`highlights[]`, public fields only, max 2 per row):
- Funding: `{company} · {round} · {date}`
- Headcount: `{company} · headcount {delta} in 12 months`
- Jobs: `most open roles: {company} {n}`
- Enrich coverage: `funding rounds for {n} · headcount series for {m}`

Tally headline templates (top of the Crustdata card):
- Discover: `{matched} companies matched · {enriched} enriched · headcount series for {series} · {postings} job postings`
- Investor search: `{companies} comparable companies · {rounds} funding rounds read · {investors} investors named · {dated} rounds with a date`
- Verify: `{candidates} identity candidates · {fields} profile fields · {people} people records · {pages} pages read · {facts} facts extracted`
- Recheck / Evaluate: `{rechecked} claims rechecked · {pages} pages read · {facts} facts extracted · {changed} statuses changed`

---

## 5. Kind `source` templates

Emitted once per page or record read, failed, or skipped. Drives the source ticker (public sources only) and the step sub-line.

### 5.1 By source type and state

| `source.type` | `source.state` | `label` template | `detail` template | Where shown |
| --- | --- | --- | --- | --- |
| `web_page` | `read` | `Read {domain}` | — | Source ticker and run log |
| `web_page` | `failed` | `Could not read {domain}` | `{source_reason}` | Source ticker (muted) and run log |
| `web_page` | `skipped` | `Skipped {domain}` | `{source_reason}` | Run log |
| `crustdata_record` | `read` | `Read company record for {company}` | `{n} field groups` | Source ticker and run log |
| `crustdata_record` (funding) | `read` | `Read funding record for {company}` | `{n} rounds` | Source ticker and run log |
| `crustdata_record` (people) | `read` | `Read leadership records for {company}` | `{n} records` | Source ticker and run log |
| `crustdata_record` (jobs) | `read` | `Read job postings for {company}` | `{n} postings` | Source ticker and run log |
| `crustdata_record` | `failed` | `Could not read Crustdata record for {company}` | `{source_reason}` | Source ticker (muted) and run log |
| `seller_document` | `read` | `Read the uploaded {document_kind}` | `{n} pages` | Step list and run log only (never in source ticker) |
| `seller_document` | `failed` | `Could not read the uploaded {document_kind}` | `{source_reason}` | Step list and run log only (never in source ticker) |

### 5.2 Allowlisted `source.reason` labels

| Code | Display label |
| --- | --- |
| `http_403` | `could not be read · 403` |
| `timeout` | `could not be read · timed out` |
| `robots` | `skipped · blocked by robots` |
| `empty` | `could not be read · no readable text` |
| `too_large` | `skipped · page too large` |
| `budget` | `skipped · budget reached` |

---

## 6. Kind `model` templates

Emitted when a language-model call finishes or fails. Carries counts only; never prompt or completion text.

| Purpose | `label` template | `detail` template |
| --- | --- | --- |
| Fact extraction (`facts > 0`, `rejected_no_span == 0`) | `Extracted {n} dated facts` (singular: `Extracted 1 dated fact`) | — |
| Fact extraction (`facts > 0`, `rejected_no_span > 0`) | `Extracted {n} dated facts` | `{m} discarded: no matching passage` |
| Fact extraction (`facts == 0`) | `No dated facts found in this source` | `{m} discarded: no matching passage` (if `m > 0`) |
| Claim intake | `Recorded {n} claims from the uploaded {document_kind}` (singular: `Recorded 1 claim from the uploaded {document_kind}`) | `{m} pages` |
| Thesis parsing | `Parsed {n} criteria from the thesis` | — |
| Business profile parsing | `Parsed business profile criteria` | — |
| Shortlist explanation | `Wrote shortlist notes for {company}` | — |
| Request drafting | `Drafted request covering {n} documents` (singular: `Drafted request covering 1 document`) | — |
| Model failure | `Model step did not finish` | `Model {error_reason} after {n} tries` |

Model summary line (bottom of the tally card):
- `Model: {reads} reads · {facts} facts extracted · {usd}`
- When zero facts extracted yet: `Model: {reads} reads · {usd}`

---

## 7. Kind `finding` templates (one per subject and stage)

Emitted when a piece of the result is created or changes state. Drives the findings stream.

### 7.1 Subject `company`

| Stage | `label` template | `detail` template |
| --- | --- | --- |
| `found` (single) | `Found {company} in {city}` | `primary pass` or `relaxed pass` |
| `found` (batch, `n > 1`) | `Found {n} companies` | `primary pass` or `relaxed pass` |
| `dropped` (single, duplicate) | `Dropped {company}` | `Duplicate of {other_company}` |
| `dropped` (single, must-have) | `Dropped {company}` | `Failed must-have: {criterion}` |
| `dropped` (batch, `n > 1`) | `Dropped {n} companies` | `{dup} duplicates · {failed} failed a must-have` |
| `enriching` | `Enriching {company}` | — |
| `enriched` | `Enriched {company}` | — |
| `scored` | `Ranked {n} companies` | — |
| `explained` | `Explained shortlist fit for {company}` | — |

### 7.2 Subject `claim`

Claims are always referenced by `{claim_category}` and `{claim_number}`, never by claim text.

| Stage | `label` template | `detail` template |
| --- | --- | --- |
| `queued` (batch) | `Queued {n} claims to check` (singular: `Queued 1 claim to check`) | — |
| `queued` (single) | `Queued {claim_category} claim {claim_number}` | — |
| `checking` | `Checking {claim_category} claim {claim_number}` | — |
| `settled` (initial) | `{claim_category} claim settled: {status}` | `claim {claim_number}` |
| `settled` (recheck, changed) | `{claim_category} claim updated: {old_status} → {status}` | `claim {claim_number}` |
| `settled` (recheck, unchanged) | `{claim_category} claim unchanged: {status}` | `claim {claim_number}` |
| `not_checked` (budget) | `{claim_category} claim not checked: budget reached` | `claim {claim_number}` |
| `not_checked` (source unavailable) | `{claim_category} claim not checked: source unavailable` | `claim {claim_number}` |
| `not_checked` (step failed) | `{claim_category} claim not checked: step failed` | `claim {claim_number}` |
| `not_checked` (identity unresolved) | `{claim_category} claim not checked: waiting on identity` | `claim {claim_number}` |

### 7.3 Subject `identity`

| Stage | `label` template | `detail` template |
| --- | --- | --- |
| `confirmed` | `Identity confirmed: {company}` | `matched on {keys}` |
| `ambiguous` | `Identity ambiguous: {n} possible entities` | `select the legal entity to continue` |
| `unresolved` | `Identity unresolved` | `no matching entity confirmed` |

### 7.4 Subject `round`

| Stage | `label` template | `detail` template |
| --- | --- | --- |
| `found` (batch per company) | `Read {n} funding rounds of {company}` (singular: `Read 1 funding round of {company}`) | — |
| `found` (single dated round) | `Recorded {round} for {company} on {date}` | — |
| `found` (undated round) | `Found undated round for {company}` | `excluded from ranking` |

### 7.5 Subject `investor`

| Stage | `label` template | `detail` template |
| --- | --- | --- |
| `ranked` | `Ranked {n} investors` (singular: `Ranked 1 investor`) | `{m} not ranked: no dated round` (when `m > 0`) |
| `not_ranked` | `Listed {n} investors without a dated round` | `not ranked` |

### 7.6 Subject `event`

| Stage | `label` template | `detail` template |
| --- | --- | --- |
| `found` (dated) | `Found dated {event_kind} event` | `{date} · {domain}` |
| `found` (undated) | `Found undated {event_kind} item` | `{domain} · listed separately` |

### 7.7 Subject `peer`

| Stage | `label` template | `detail` template |
| --- | --- | --- |
| `found` (batch) | `Found {n} comparable companies` (singular: `Found 1 comparable company`) | — |
| `found` (single) | `Found comparable company {company} in {city}` | — |
| `found` (none) | `No fair comparable companies found` | — |

### 7.8 Subject `assessment`

| Stage | `label` template | `detail` template |
| --- | --- | --- |
| `written` (v1) | `Assessment v1 written: {disposition}` | `{supported} supported · {open} open` |
| `written` (v2+, disposition unchanged) | `Assessment v{version} written: {disposition}` | `{changed} claims changed` |
| `written` (v2+, disposition changed) | `Assessment v{version} updated: {old_disposition} → {disposition}` | `{changed} claims changed` |

### 7.9 Subject `request_list`

| Stage | `label` template | `detail` template |
| --- | --- | --- |
| `drafted` (`n > 0`) | `Drafted a request for {n} documents` (singular: `Drafted a request for 1 document`) | `awaiting named approval` |
| `drafted` (`n == 0`) | `No seller documents needed` | — |

---

## 8. Kind `notice` templates

Fixed sentences per `code`, with counts and allowlisted labels as the only slots. Shown as a muted line under the step and in the run log.

| `code` | `label` template | `detail` template |
| --- | --- | --- |
| `search_widened` | `Widened the search` | `Strict filters returned {n} companies; preferences were relaxed.` |
| `budget_low` | `Credit budget at 80%` | `{credits} of {budget} credits used.` |
| `budget_reached` | `Budget reached, {n} checks not run` (singular: `Budget reached, 1 check not run`) | `Remaining checks are marked Not checked.` |
| `step_resumed` | `Resumed from checkpoint` | `{n} prior steps kept from cache.` |
| `served_from_cache` | `Served from cache` | `Previous result reused at 0 credits.` |
| `call_retried` | `Retried {provider} call` | `Attempt {current} of {total} after {error_reason}.` |
| `source_limit` | `Read cap reached` | `Read the first {n} of {m} search results.` |
| `identity_blocked` | `Run stopped at identity` | `Confirm which legal entity this is before attaching records.` |
| `nothing_to_check` | `No factual claims to check` | `Upload a seller document or add claims to run verification.` |
| `activity_cap_reached` | `Detailed log limit reached` | `Further status updates are summarised; findings and costs continue.` |

---

## 9. Accessibility live-region announcements

Polite `aria-live` region (`≤ 1` announcement every 2 seconds). Sources and counters are never announced.

| Trigger | Announcement template |
| --- | --- |
| Step finished | `{step}, done, {one_line_result}` |
| Step failed | `{step} failed: {error_reason}` |
| Step skipped | `{step}, skipped, budget reached` |
| Claim settled | `Claim {claim_number}, {claim_category}: {status}` |
| Shortlist ranked | `Shortlist ranked, {n} companies` |
| Investor list ranked | `Investor shortlist ranked, {n} investors` |
| Assessment written | `Assessment version {version}: {disposition}` |
| Run finished | `{workflow} finished, {duration}` |
| Run stopped | `Run stopped at {step}` |
