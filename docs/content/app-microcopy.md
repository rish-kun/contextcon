# DealProof application microcopy

Source of truth: `DealProof product description.md` and `docs/design/design-direction.md`.

Conventions:
- Sentence case everywhere.
- Headings, nav labels, tabs, tooltips headers, and buttons end without a period. Multi-word explanations and paragraphs keep their periods.
- Dates: `14 Oct 2026` (or `Oct 2026` when only the month is known). Times: `22 Nov 2026, 16:42 IST`.
- Placeholders use `{braces}` so engineers can wire dynamic values directly.
- Never alter the exact product vocabulary: `Supported`, `Partially corroborated`, `Conflicting evidence`, `Contradicted`, `Cannot verify`, `Not checked`; `Prioritise`, `Investigate further`, `Deprioritise`, `Cannot assess`; `Estimate`, `Signal`.

---

## 1. Navigation and app shell

### Sidebar

- Wordmark: `DealProof`
- Primary navigation:
  - `Cases`
  - `Discover`
  - `Investors`
- Section heading: `Recent`
- Footer navigation:
  - `Scoring policy`
  - `Settings`
- Mobile drawer trigger aria-label: `Open navigation`
- Collapse sidebar tooltip: `Collapse sidebar` / `Expand sidebar`

### Top bar

- Breadcrumb roots:
  - `Cases`
  - `Cases / {company_name}`
  - `Discover / {thesis_title}`
  - `Investors`
  - `Scoring policy`
  - `Settings`
- Test-mode badge (shown on every page while `EMAIL_SEND_ENABLED` is false):
  - Label: `Test mode`
  - Tooltip: `Email sending is off. Approvals are recorded, and no email leaves DealProof.`
- Command menu trigger: `⌘K` (aria-label: `Open command menu`)
- User menu:
  - Display: `{user_name}`
  - Menu items: `Settings`, `Sign out`

### Command menu (`⌘K`)

- Input placeholder: `Jump to a case, thesis, or action`
- Group headings: `Actions`, `Recent cases`, `Navigation`
- Actions:
  - `New thesis`
  - `New case`
  - `Find investors`
  - `View scoring policy`
- No match: `No matching cases or actions.`

---

## 2. Page titles, subtitles, and tabs

### Cases dashboard

- Title: `Cases`
- Summary line:
  - Default: `{total} cases · {active} running or waiting on you`
  - When none active: `{total} cases`
- Filter controls: `Disposition`, `Status`, `Thesis`
- Search input placeholder: `Search by company or city`
- Table column headers: `Company`, `Disposition`, `Fit · assessable`, `Claims`, `Updated`, `Cost`
- Second-line status cues:
  - Confirmed identity: `{city} · Identity confirmed`
  - Unresolved identity: `Identity unresolved · {n} candidates`
  - Pending approval: `Request awaiting approval`
  - Live run: `{workflow} running · step {current} of {total}`

### Discover (New thesis → Criteria → Shortlist)

- Page title: `Discover`
- Three-step header: `1 Thesis`, `2 Criteria`, `3 Shortlist`
- Step 1 heading: `Describe what you are looking for`
- Step 1 input placeholder: `Privately held Indian warehousing and supply-chain software companies that serve enterprise customers and show recent expansion`
- Step 1 example chips: `Regional 3PL operators`, `Cold chain technology`, `Warehousing software in India`
- Step 2 heading: `Criteria`
- Step 2 helper note: `Edit before searching. Nothing runs yet.`
- Step 2 group labels: `Must have`, `Preference`
- Step 2 column headers: `Criterion`, `Condition`, `Weight`, `Assessed from`
- Step 2 `Assessed from` values: `Company record`, `Evidence`, `Signal`
- Step 3 heading: `Shortlist · {n} companies`
- Step 3 removed count toggle: `{n} removed for failing a must-have` (`Show` / `Hide`)
- Shortlist row section labels: `Why it is here`, `Unknown`

### Investor discovery

- Page title: `Find investors`
- Form section label: `Your business`
- Field labels and placeholders:
  - `Sector` — placeholder: `Warehousing technology`
  - `Location` — placeholder: `India`
  - `Stage` — placeholder: `Series A`
  - `Size` — placeholder: `50 to 200 people`
  - `Funding sought` — placeholder: `Growth equity`
- Results summary: `{n} investors · from {m} comparable companies with dated rounds`
- Row section labels: `Comparable companies backed`, `Why they fit`, `Unknown`
- Fixed footer caveat: `This ranking describes past investments. It does not predict whether an investor will invest.`

### Case view

- Case header elements:
  - Company name (`{company_legal_name}` or `{submitted_name}`)
  - Version and date: `v{version} · {date}`
  - Cost compact readout: `{credits} cr · {model_cost}`
  - Persistent Not checked banner (whenever count > 0): `{n} checks were not run` + link `View`
- Case tabs:
  - `Overview`
  - `Identity`
  - `Claims {count}`
  - `Events {count}`
  - `Comparables`
  - `Assessment`
  - `Request` (with dot indicator when approval is waiting; aria-label: `Request, awaiting approval`)
  - `Sources {count}`
  - `Cost`
- Sticky assessment rail:
  - Heading: `Assessment · v{version}`
  - Rows: `Fit {score} · {assessable}%`, `{settled} of {total} settled · {not_checked} not checked`, `Signals: {count}`, `Financial: {status}`
  - Next-step cue: `Next: approve request` / `Next: resolve identity` / `Next: review open claims` / `Next: print memo`

### New case modal / page (direct to Verify)

- Title: `New case`
- Subtitle: `Start verification for a company you already have in mind.`
- Fields:
  - `Company name` — placeholder: `Meridian Warehousing Pvt Ltd`
  - `Website` — placeholder: `https://example.in`
  - `Thesis (optional)` — placeholder: `Select an existing thesis or leave blank`
  - `Seller documents (optional)` — helper: `PDF or presentation slides`
  - `Individual claims (optional)` — placeholder: `Type one claim per line`

### Scoring policy page

- Title: `Scoring policy`
- Subtitle: `Policy {version} · The rules DealProof applies to every case. The same records under the same policy produce the same assessment every time.`

### Settings page

- Title: `Settings`
- Sections: `Account`, `Preferences`, `Data and confidentiality`

---

## 3. Button labels

### Global and navigation

- `Open app`
- `Log in`
- `Sign out`
- `New case`
- `New thesis`

### Discover and Investors

- `Turn into criteria`
- `Add criterion`
- `Move to must have`
- `Move to preference`
- `Remove criterion`
- `Search`
- `Open case`
- `Show removed` / `Hide removed`
- `Find investors`
- `Draft outreach`

### Case header and memo

- `Print memo`
- `Export source record`
- `View`
- `More actions` (overflow `⋯` aria-label)
- `Re-run verification`
- `Archive case`
- `Delete case` (destructive; requires confirmation)

### Identity and Claims

- `Choose the entity`
- `Add a claim`
- `Upload documents`
- `Run check` (with credit estimate: `Run check · about {n} credits`)
- `Add to request` / `Remove from request`
- `Show all` / `Reset filters`

### Assessment and History

- `Compare v{a} and v{b}`
- `Show` / `Hide` (for unchanged claims)
- `Open current version`
- `Read scoring policy`

### Request and Approval

- Live mode: `Approve and send once`
- Live confirmation dialog: `Send once` | `Go back`
- Test mode: `Approve (test mode, nothing is sent)`
- Test confirmation dialog: `Record approval` | `Go back`
- Post-send: `View message` | `Upload seller response`

### Run recovery

- `Retry step`
- `Resume run`
- `View run log`

---

## 4. Empty states

### Cases dashboard (no cases yet)

- Heading: `No cases yet`
- Body: `A case holds a company's confirmed identity, checked claims, sources, and screening memo. Start with an investment thesis or open a case for a company you already have in mind.`
- Actions: `New thesis` (primary), `New case` (secondary)
- Tertiary link: `Open illustration case (not a real company)`

### Cases dashboard (filters return nothing)

- Heading: `No cases match these filters`
- Body: `Try clearing one or more filters or changing your search term.`
- Action: `Reset filters`

### Discover shortlist (no matches)

- Heading: `No companies matched all must-haves`
- Body: `{removed_count} candidates were removed for failing a must-have criterion. Review the removed companies or adjust your criteria.`
- Actions: `Show removed companies`, `Edit criteria`

### Investor discovery (no results)

- Heading: `No investors found with dated comparable rounds`
- Body: `DealProof lists an investor only when a dated funding record connects them to a comparable company. Broaden the sector or stage and search again.`
- Action: `Edit search`

### Claims tab (no claims added yet)

- Heading: `No claims on file yet`
- Body: `Upload the seller's presentation or documents, or type individual claims to check them against independent evidence.`
- Actions: `Upload documents`, `Add a claim`

### Events tab (no dated events)

- Heading: `No dated public events found`
- Body: `No recent dated announcements or reported events were returned for this confirmed entity.`
- Undated subsection heading (when undated items exist): `Undated`
- Undated helper note: `These items have no reliable date on record and are listed separately.`

### Comparables tab (no fair comparison)

- Heading: `No fair comparison found`
- Body: `Available records did not return peers matching the same activity, region, and size band. DealProof does not substitute a weaker list.`
- Header note when comparables exist: `Same activity, region, and size band. Informational only — not scored.`

### Financial assessment (when reliable inputs are absent)

- Heading: `Not assessed`
- Body: `No reliable financial inputs.`
- Resolution line: `Would need: {needed_documents}` (default: `Would need: audited financial statements`)

### Request tab (no open items to request)

- Heading: `Nothing to request right now`
- Body: `All checked claims are settled, or no open claim requires a document from the seller. You can still select a claim from the ledger to add a document request.`
- Action: `Go to claims`

### Sources tab (no sources yet)

- Heading: `No sources recorded yet`
- Body: `Sources appear here with their dates and retrieval times as soon as verification begins.`

### Cost tab (no billable steps yet)

- Heading: `No usage recorded yet`
- Body: `Credits and model usage appear here once a search or verification step runs.`

---

## 5. Loading states and run-progress step labels

### Run panel header

- Live state: `Analyst working · {workflow} · {subject}`
- Reduced-motion fallback (replaces indicator): `Working`
- Metadata (right-aligned, mono): `{elapsed} · {used} of {budget} credits`
- Collapsed finished line:
  - All checks run: `{workflow} finished · {duration} · {credits} credits`
  - With Not checked items: `{workflow} finished · {duration} · {credits} credits · {not_checked} checks not run`
- Inline skeleton fallback (after 2 seconds): `Still working`

### Step states

- Pending: `{step_label}`
- Running: `{step_label}` + live sub-line (e.g. `claim {current} of {total} · searching dated announcements`)
- Done: `{step_label}` · `{one_line_result}` · `{cost}`
- Cached (after resume): `{step_label}` · `from cache · 0 cr`
- Failed: `{step_label}` · `Step failed · {reason}` + button `Retry step`
- Skipped for budget: `{step_label}` · `Skipped · budget reached`

### Resume notice (after interruption)

- Banner: `Resumed {time} · {kept} steps kept, continuing from {step_label}`

### Standard step labels by workflow

#### Discover (company shortlist)

1. `Parse thesis` — sub-line: `Separating must-haves from preferences`
2. `Search company records` — sub-line: `Querying live company data`
3. `Deduplicate candidates` — sub-line: `Merging matching entity records`
4. `Apply must-haves` — sub-line: `Checking verifiable exclusions`
5. `Score fit and coverage` — sub-line: `Calculating fit and assessable criteria share`

#### Discover investors

1. `Find comparable companies` — sub-line: `Matching sector, location, and stage`
2. `Read dated funding rounds` — sub-line: `Extracting investors from dated records`
3. `Group by investor` — sub-line: `Counting comparable rounds and flagging possible duplicates`
4. `Rank by activity and recency` — sub-line: `Ordering by comparable investments and last sector date`

#### Verify and Evaluate

1. `Confirm identity` — sub-line: `Matching domain, legal name, and registration keys`
2. `Build public profile` — sub-line: `Reading company record and operating signals`
3. `Read seller deck` — sub-line: `Extracting factual claims from uploaded documents`
4. `Gather evidence` — sub-line: `Claim {current} of {total} · searching independent records`
5. `Extract facts` — sub-line: `Recording quotes, fields, and as-of dates`
6. `Apply status rules` — sub-line: `Assigning claim statuses under policy {version}`
7. `Evaluate` — sub-line: `Computing five separate judgments and draft request list`

#### Re-evaluate (after new seller documents arrive)

1. `Read seller response` — sub-line: `Extracting facts from {filename}`
2. `Recheck affected claims` — sub-line: `Updating {n} affected claims`
3. `Apply status rules` — sub-line: `Re-running policy {version}`
4. `Compute version diff` — sub-line: `Recording changes from v{prev} to v{next}`

---

## 6. Errors and stated limits

### Budget limit (stated limit, not an error)

- Banner: `Credit budget reached. {n} checks were not run and are marked Not checked.`
- Link: `View not checked claims`

### Source and step failures

- Source unavailable: `Source unavailable during this check. Claim marked Not checked.`
- Step failure: `{step_label} did not finish: {reason}. Previous steps are kept.` + `Retry step`
- SSE connection lost: `Connection interrupted. Reconnecting to the live run.`
- SSE reconnected: `Reconnected. Showing latest step state.`

### Document upload errors

- Unsupported file type: `This file format is not supported. Upload a PDF, presentation, or document file.`
- File too large: `This file exceeds the upload limit of {limit}.`
- Unreadable file: `DealProof could not read text from {filename}. Check that the file is not password-protected or damaged.`

### Approval and send errors

- Missing recipient: `Enter the recipient's email address before approving.`
- Invalid email: `Enter a valid email address.`
- Unsigned-in approver: `Sign in to approve. A named person must approve every request.`
- Send failure: `Failed · not sent` — detail: `{provider_reason}. Nothing was retried automatically. Review and approve again to retry.`

### System integrity guards (developer / production safety copy)

- Missing source on a fact: `Unsourced fact omitted.`
- Missing cause on a version change: `Version change is missing a stated cause and source.`

---

## 7. Claim statuses (tooltips and explanations)

Fixed order everywhere: `Supported`, `Partially corroborated`, `Conflicting evidence`, `Contradicted`, `Cannot verify`, `Not checked`.

| Status | Accessible name | Tooltip / plain-word explanation |
| --- | --- | --- |
| `Supported` | `Status: Supported` | Adequate independent evidence directly supports this claim. |
| `Partially corroborated` | `Status: Partially corroborated` | Evidence supports part of the claim, but not all of it. Both the supported part and the unsupported part are shown. |
| `Conflicting evidence` | `Status: Conflicting evidence` | Relevant sources disagree with each other. Both sources are shown side by side. |
| `Contradicted` | `Status: Contradicted` | Reliable evidence directly conflicts with the precise claim. |
| `Cannot verify` | `Status: Cannot verify` | Available evidence cannot settle this claim. This is a finished answer, not an error. DealProof names the document that would settle it. |
| `Not checked` | `Status: Not checked` | This check was not run, for example because a source was unavailable or the credit budget was reached. Never treated as a clean or settled result. |

### `Not checked` reason labels (always paired with the tag)

- `Not checked · budget reached`
- `Not checked · source unavailable`
- `Not checked · step failed`

### `Not checked` summary copy

- Sufficiency count: `{settled} of {total} checks settled · {not_checked} not checked`
- Case header persistent line: `{n} checks were not run` + `View`
- Retry row prompt: `No search was run for this claim.` + button `Run check · about {n} credits`

### Claim ledger row sub-labels

- Seller column header: `Seller said`
- Evidence column header: `The record shows`
- Partially corroborated sub-labels: `Supported`, `Not supported`
- Unsettled resolution prompt: `What would settle it:`
- Manually typed claim attribution: `Typed by {user_name}, {date}`

---

## 8. Dispositions (tooltips and stamp copy)

| Disposition | Accessible name | Tooltip / plain-word explanation |
| --- | --- | --- |
| `Prioritise` | `Disposition: Prioritise` | Strong fit with your criteria, and the required checks are satisfied within what DealProof covers. |
| `Investigate further` | `Disposition: Investigate further` | Attractive fit, but important evidence is incomplete and needs follow-up. |
| `Deprioritise` | `Disposition: Deprioritise` | A requirement you set has verifiably failed, or the fit is poor on good evidence. Missing public evidence alone never produces Deprioritise. |
| `Cannot assess` | `Disposition: Cannot assess` | Company identity or other essential information is too uncertain to judge. |

### Stamp supporting lines

- Policy footer: `Policy {version}`
- Evidence reference: `Rests on: {claim_refs}`
- Deprioritise safeguard note: `Based on verified evidence — not missing public records.`

---

## 9. Five judgments (tooltips and panel copy)

Panel note (tooltip on panel info icon): `DealProof keeps five judgments separate and never blends them into one score.`

| Judgment | Tooltip / question it answers |
| --- | --- |
| `Opportunity fit` | How well does this company match your thesis criteria? Shown with the share of criteria that could be assessed. Says nothing about expected returns. |
| `Evidence sufficiency` | Do the available records support what you need to know? Shows how many required checks are settled, which remain open, and whether any were not run. |
| `Business assessment` | What do observable operating indicators suggest? Lists dated signals and estimates, never treated as confirmed revenue. |
| `Financial assessment` | What do reliable financial inputs show, under stated assumptions? Shown only when reliable financial inputs exist. |
| `Screening disposition` | What should you do next? Decided by policy rules from the records on file, not AI confidence. |

---

## 10. Fit and assessable share

- Standard readout (never split): `Fit {score} · {pct}% of criteria assessable`
- Compact table readout: `{score} · {pct}%`
- Detail line under criteria strip: `{assessed} of {total} criteria assessable · {unknown} unknown: {unknown_list}`
- Detail line when all assessable: `{total} of {total} criteria assessable · 0 unknown`
- Fixed caveat under strip on case page: `Fit measures match to your criteria. It says nothing about returns.`
- Tooltip for `Fit {score} · {pct}% of criteria assessable`:
  `Fit scores how well the company matches the criteria that could be checked. The assessable percentage shows how much of your thesis had enough evidence to judge. A company with thin evidence is never presented as equally ready.`
- Criteria strip legend:
  - Solid cell: `Met`
  - Empty bordered cell: `Not met`
  - Hatched dashed cell: `Unknown · could not assess`
  - Top notch: `Must-have criterion`
- Criterion cell hover template: `{criterion_name} · {verdict} · {source_chip}`
- Shortlist sort explanation: `Sorted by fit score, with ties broken by share of criteria assessable.`

---

## 11. Estimates and signals

- Inline figure format: `~{value}` + tag `Estimate`
- Inline observation tag: `Signal`
- Tooltips:
  - `Estimate`: `Inferred from indirect data, not a confirmed company record.`
  - `Estimate` (headcount specific): `Estimate · from professional profiles, not a payroll count.`
  - `Signal`: `An observable indicator that suggests activity without proving revenue or financial performance.`
- Section heading (never "Traction" or "Growth"): `Operating signals`
- Chart legend suffix (dashed series): `{metric_name} (Estimate)`
- Investor shortlist caveat: `This ranking describes past investments. It does not predict whether an investor will invest.`

---

## 12. Identity states

### Identity confirmed

- Band title: `Identity confirmed`
- Keys line: `Matched on {key_list}` (e.g. `Matched on domain, registration number`)
- Tooltip: `Every record in this case is attached using these verified identity keys, never on a matching name alone.`

### Identity unresolved

- Band title: `Identity unresolved`
- Description: `DealProof found {n} possible legal entities matching this name and will not attach records until you confirm which company this is.`
- Candidate card labels:
  - `Matching keys`
  - `Differing keys`
  - Button: `Choose the entity`
- Blocked-tab empty state (shown on Claims, Events, Comparables, Assessment, and Request until resolved):
  - Heading: `Waiting on identity`
  - Body: `Confirm which legal entity this case refers to before viewing or attaching records. Until identity is confirmed, the disposition remains Cannot assess.`
  - Action: `Resolve identity`

### People and leadership matching

- Confirmed match label: `Matched on company id + name`
- Unconfirmed name-only match (never attached as a fact): `Possible match, not attached`
- Tooltip: `Career records are attached only when both the person's name and company identifier match.`

### Investor duplicate flag

- Inline flag: `Possible duplicate of "{other_name}" · not merged`
- Tooltip: `These investor names may refer to the same firm, but DealProof keeps them separate unless confirmed.`

---

## 13. Source line and evidence popover

### Source chip format

- Dated source: `{source_name} · as of {as_of_date}`
- Unknown date: `{source_name} · as of unknown date`
- Overflow chip: `+{n}` (aria-label: `{n} more sources`)

### Evidence popover fields

- `Excerpt / field value`
- `Source class`
- `What this source can settle`
- `As-of date` (`{as_of_date}` or `Unknown date`)
- `Retrieved` (`{retrieved_timestamp}`)
- `Attached to` (`{entity_name} · matched on {identity_key}`)
- Link: `Open source` (when URL exists)

### Source reliability class explanations

| Class | Plain-word explanation |
| --- | --- |
| `Registry` | Official corporate filing. Strong on incorporation, legal name, registered office, directorships, and registered charges. |
| `Registry mirror` | Secondary mirror of official corporate filings. Reflects what the mirror held as of the stated date; confirm against primary filings during formal diligence. |
| `Audited statement` | Independently audited financial report. Strong on past revenue, margins, and balance-sheet position as of the reporting period. |
| `Counterparty confirmation` | Direct confirmation from a customer, lender, or partner. Strong on the existence and terms of that relationship. |
| `Company announcement` | Press release or public post from the company. Shows that the company announced something, not that it has happened. |
| `Professional-profile signal` | Aggregated public career or hiring profile data. Useful as an operating signal or headcount estimate, not a payroll count. |
| `News` | Independent press reporting. Useful for dated public events; verify material facts against primary records. |
| `Seller document` | Presentation or file supplied by the seller. States what the seller claims; reconciled against independent sources. |
| `Seller statement` | Statement made by the seller or entered manually by an analyst. Treated as a claim to check, not verified evidence. |

---

## 14. Approval and send-once flow

### Stepper

- Live mode: `Draft` → `Approved` → `Sent`
- Test mode: `Draft` → `Approved` → `Suppressed`

### Draft state

- Left column heading: `Documents requested ({n})`
- Claim mapping tag: `← claim {n}`
- Right column heading: `Message`
- Draft notice: `Drafted by DealProof, edit before approving.`
- Form labels:
  - `To` — placeholder: `Recipient email address, typed by you`
  - `To` helper: `DealProof does not suggest or collect personal contact details.`
  - `Subject` — placeholder: `Information request: {company_name}`
  - `Message` — editable textarea
- Approver readout: `Approver: {user_name} (signed in)`
- Send-once helper (live mode): `This sends one email. It cannot be sent again from this case.`

### Confirmation dialog (live mode)

- Title: `Approve and send once`
- Body: `You are approving one email to {recipient} requesting {n} documents. Once sent, this request cannot be sent again from this case.`
- Details list:
  - `Recipient`: `{recipient}`
  - `Documents`: `{document_list}`
  - `Approver`: `{user_name}`
- Buttons: `Send once` (primary), `Go back` (secondary)

### Permanent receipt (live mode, after sending)

- Status heading: `Sent once`
- Line 1: `Approved by {user_name} · {timestamp}`
- Line 2: `To {recipient} · {n} documents requested`
- Action: `View message`

### Honest test mode (`EMAIL_SEND_ENABLED` is false)

- Hatched banner heading: `Test mode`
- Hatched banner body: `Email sending is off. Approving records the approval. Nothing will leave.`
- Submit button: `Approve (test mode, nothing is sent)`
- Confirmation dialog title: `Record approval in test mode`
- Confirmation dialog body: `Email sending is off. Confirming records your approval for {recipient} ({n} documents), and no email will be sent.`
- Confirmation buttons: `Record approval` (primary), `Go back` (secondary)
- Permanent hatched receipt (never green, no check mark, never "Sent" alone):
  - Status heading: `Suppressed (test mode) · not sent`
  - Line 1: `Approved by {user_name} · {timestamp}`
  - Line 2: `Recipient recorded: {recipient} · {n} documents listed`
  - Action: `View message`

### Failed send state

- Status heading: `Failed · not sent`
- Body: `The email provider returned an error: {provider_reason}. No automatic retry was attempted.`
- Action: `Review and approve again`

### Post-send seller response section

- Heading: `Seller documents`
- Helper: `When the seller replies, attach their documents here. DealProof rechecks the affected claims and records a new assessment version.`
- Attached document row: `{filename}` · `Affected {n} claims` · link `View v{version} diff`

---

## 15. Cost readout

- Heading: `This case cost`
- Primary sentence (credits and model usage are never summed): `{used} of {budget} credits · {model_cost} model usage`
- Progress bar caption: `{pct}% of the credit budget`
- Budget-reached headline (replaces primary sentence when full): `Budget reached · {not_checked} checks not run` + link `View not checked claims`
- Table headers: `Run`, `Step`, `Credits`, `Model`, `When`
- Cached step credit cell: `0 · cache`
- Total row label: `Total`
- Compact readout (case header and dashboard): `{used} cr · {model_cost}`
- Pre-search estimate (Criteria step): `Estimated cost: about {n} credits`
- Tooltip: `Credits track external data lookups against this case's budget. Model usage tracks language-model spend separately. Cached steps from resumed runs cost 0 credits.`

---

## 16. Version history and assessment diff

- Section heading: `Assessment history`
- Version node label:
  - Initial: `v1 · {timestamp} · initial screening`
  - Update: `v{n} · {timestamp} · after "{trigger_document}" from seller`
- Read-only banner (when viewing an older version):
  `You are reading version {viewing}. Version {current} is current.` + link `Open current version`
- Diff heading: `What changed in v{n}`
- Compare selector: `Compare v{a} and v{b}`
- Row badge in Claims ledger: `Changed in v{n}` (links to diff)
- Accessible status transition label: `Changed from {old_status} to {new_status}`
- Cause line label: `Because:` (always followed by reason and source line)
- Unchanged collapse line: `{n} claims unchanged` + `Show` / `Hide`
- Tooltip on `Assessment history`: `New evidence updates the assessment in the open. Earlier versions remain readable, and every change states its cause and source.`

---

## 17. Confidential-upload notice

### Inline upload strip (Claims tab, Request tab, New case form)

- Dropzone label: `Drop seller presentation or documents here, or choose files`
- Confidentiality strip (always visible beside upload): `Used only for this case · deleted on {deletion_date}`
- Info link: `Confidentiality details`

### Full confidentiality notice (popover and Confidentiality page)

- Heading: `How uploaded documents are handled`
- Points:
  - **Case-only use:** Uploaded files are read only to check claims and prepare the memo for this case.
  - **Never used for training:** Your documents are never used to train AI models.
  - **Not shared across customers:** Files and extracted claims stay isolated to your workspace.
  - **Personal details stripped:** Personal details that are not needed for screening are removed during processing.
  - **Scheduled deletion:** Files uploaded to this case are deleted on `{deletion_date}` under the retention schedule, or earlier if you delete the case.

---

## 18. Settings

- Sound toggle label: `Sounds for finished runs and sends`
- Sound toggle helper: `Off by default. Plays a quiet cue only when a run finishes, a request is sent or suppressed, or an error needs attention.`
- Approver identity note: `Your signed-in name ({user_name}) is recorded on every request you approve.`
