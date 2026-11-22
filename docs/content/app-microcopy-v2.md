# DealProof application microcopy (v2)

Companion to [app-microcopy.md](./app-microcopy.md). Covers the v2 sidebar architecture, the new workspace and research screens, the updated directories, and the not-found and error pages defined in [B-app-consistency.md](../design/iterations/B-app-consistency.md).

Conventions:
- Sentence case everywhere.
- Headings, nav labels, tabs, column headers, filter labels, tooltips headings, and buttons end without a period. Multi-word explanations and paragraphs keep their periods.
- Dates: `14 Oct 2026` (or `Oct 2026` when only the month is known). Times: `22 Nov 2026, 16:42 IST`.
- Placeholders use `{braces}` for dynamic values.
- Missing values in tables render as an en dash `–`, never `N/A` and never blank.
- Middle dots join items only inside mono meta lines and fixed readouts (`Fit 82 · 70% of criteria assessable`). Sentences use commas.
- Exact product vocabulary never changes: `Supported`, `Partially corroborated`, `Conflicting evidence`, `Contradicted`, `Cannot verify`, `Not checked`; `Prioritise`, `Investigate further`, `Deprioritise`, `Cannot assess`; `Estimate`, `Signal`.
- Credits and model usage are two separate currencies and are never summed.
- `Not checked` is never folded into a settled total.

---

## 0. Shell, navigation, and v2 vocabulary updates

Changes from `app-microcopy.md` §1–§6:

### Unified vocabulary

- One name per destination, shared across the sidebar, breadcrumb, `h1`, and `<title>`:
  - `Overview` (`/app`)
  - `Pipeline` (`/app/pipeline`)
  - `Approvals` (`/app/approvals`)
  - `Companies` (`/app/companies`)
  - `Screenings` (`/app/discover`)
  - `Compare` (`/app/compare`)
  - `Signals` (`/app/signals`)
  - `Investors` (`/app/investors`)
  - `Scoring policy` (`/app/policy`)
  - `Settings` (`/app/settings`)
- Action labels (removed from the nav list and grouped under one `+ New` button):
  - Trigger button: `New` (with `+` icon)
  - Menu items: `New screening`, `Verify a company`, `Find investors`
- Sidebar groups:
  - `Workspace`: `Overview`, `Pipeline`, `Approvals` (with right-aligned mono draft count `{n}` when `n > 0`)
  - `Research`: `Companies`, `Screenings`, `Compare`, `Signals`, `Investors`
  - `Recent`: last 5 cases by update time
  - Footer: `Scoring policy`, `Settings`
- Command menu (`⌘K`) updates:
  - Input placeholder: `Jump to a company, screening, or action`
  - Actions: `New screening`, `Verify a company`, `Find investors`, `Compare cases`, `View approvals`, `View scoring policy`
  - No match: `No matching pages, companies, or actions.`
- Run header label (replaces `Analyst working` on non-live-stream headers): `{workflow} running · {subject}`
- Standard read-error pattern everywhere: `{Thing} did not load` + reason + `Try again`.
- Session-expired error (`401`):
  - Title: `Your session has ended`
  - Body: `Sign in again to continue. Nothing was changed.`
  - Action: `Log in`
- Loading fallback after 2 seconds (inside `LoadingState`): `Still working`
- Search placeholder correction (matches company name only): `Search by company`

### Login page facts panel (replaces marketing copy)

- Heading: `Before you sign in`
- Points:
  - `There is no sign-up page. An admin creates workspace accounts from the command line.`
  - `Your signed-in name is recorded on every request you approve.`
  - `Every fact in a case keeps its source and the date it was true.`
- Test-mode line (shown when `EMAIL_SEND_ENABLED` is false):
  - `Test mode is on. Approvals are recorded and no email leaves DealProof.`

---

## 1. Overview (`/app`)

### Page header and stat row

- Page title (`h1` / nav / breadcrumb / `<title>`): `Overview`
- Meta line:
  - Default: `{cases} cases · {screenings} screenings · last updated {timestamp}`
  - No cases yet: `No cases yet`
- Primary action: `New` (opens `New screening`, `Verify a company`, `Find investors`)
- Stat row tiles (5 hairline-divided tiles, each links to its filtered view):
  - Tile 1 label: `Cases` · value: `{total_cases}` · note: `{running} running` (or `{assessed} assessed` when none running)
  - Tile 2 label: `Needs you` · value: `{needs_you}` · note: `{approvals} approvals` (or `{identity} identity · {failed} failed` when no approvals waiting)
  - Tile 3 label: `Prioritise` · value: `{prioritise}` · note: `of {assessed} assessed`
  - Tile 4 label: `Not checked` · value: `{not_checked_claims}` · note: `across {not_checked_cases} cases`
  - Tile 5 label: `Spent` · value: `{credits} cr` · note: `{model_cost} model`

### Panels and column headers

- Panel 1: `Needs you` · meta: `{n}` (or `{n} · from {m} most recently updated cases` when capped)
  - Column headers: `Company`, `What is waiting`, `Since`
  - `What is waiting` cell strings:
    - Draft request: `Request awaiting approval`
    - Unresolved identity: `Identity unresolved · {n} candidates`
    - Ambiguous identity: `Identity ambiguous · {n} candidates`
    - Failed run: `Verification failed`
    - Unchecked claims: `{n} checks not run` (singular: `1 check not run`)
  - Footer link (when truncated): `View all {n} in pipeline`
- Panel 2: `By disposition` · meta: `{total} cases`
  - Rows (fixed order):
    - `Prioritise`
    - `Investigate further`
    - `Deprioritise`
    - `Cannot assess`
    - (below hairline) `No disposition yet`
- Panel 3: `Recently updated cases` · meta: `{shown}`
  - Column headers: `Company`, `Disposition`, `Fit · assessable`, `Claims`, `Updated`
  - Footer link: `View all {total} companies`
- Panel 4: `Screenings` · meta: `{n}`
  - Row meta: `{status} · {shortlisted} shortlisted`
  - Footer link: `View all screenings`
- Panel 5: `Investor searches` · meta: `{n}`
  - Row meta: `{sector} · {stage} · {investors} investors`
  - Footer link: `View all investors`

### Filter labels

- Overview has no page-level filters. Clicking any stat tile or disposition row opens the matching filtered view in Companies, Pipeline, or Approvals.

### Empty states

- Page empty (no cases yet; stat row omitted):
  - Title: `No cases yet`
  - Body: `A case holds a company's confirmed identity, checked claims, sources, and screening memo. Start with a screening thesis or verify a company you already have in mind.`
  - Actions: `New screening` (primary), `Verify a company` (secondary)
- `Needs you` panel empty:
  - Title: `Nothing waiting on you`
  - Body: `No requests are awaiting approval, no identities are unresolved, and no active cases have failed or unchecked items.`
- `Screenings` panel empty (inline):
  - Text: `No screenings yet.` + link `New screening`
- `Investor searches` panel empty (inline):
  - Text: `No investor searches yet.` + link `Find investors`

### Loading states

- Page loading: `LoadingState` (`aria-label="Loading overview"`, shape `tiles` + `rows`)
- Panel loading: `LoadingState` (`aria-label="Loading {panel_name}"`, shape `rows`, density matching table)
- After 2 seconds: `Still working`

### Error states

- Page error:
  - Title: `Overview did not load`
  - Body: `{reason}. Nothing was changed.`
  - Action: `Try again`
- Panel error (for `Needs you`, `Recently updated cases`, `Screenings`, `Investor searches`):
  - Title: `{Panel} did not load`
  - Body: `{reason}. Nothing was changed.`
  - Action: `Try again`

### Tooltips

- `Needs you` tile: `Cases with a draft request awaiting approval, unresolved identity, a failed verification step, or checks marked Not checked.`
- `Prioritise` tile: `Cases whose current assessment disposition is Prioritise under the active scoring policy.`
- `Not checked` tile: `Claims whose check was not run because of budget, an unavailable source, or a failed step. Never counted as settled.`
- `Spent` tile: `External data credits and language-model spend across workspace cases. The two currencies are never summed.`
- `No disposition yet` row: `Cases still running or waiting for identity confirmation before an assessment can be written.`

### Button labels

- `New` (primary dropdown)
- `New screening`
- `Verify a company`
- `Find investors`
- `View all {total} companies`
- `View all {n} in pipeline`
- `View all screenings`
- `View all investors`
- `Try again`

---

## 2. Screenings (`/app/discover`)

### Page header

- Page title (`h1` / nav / breadcrumb / `<title>`): `Screenings`
- Meta line: `{total} screenings · {running} running` (or `{total} screenings` when none running)
- Header figures:
  - `{total}` — `Screenings`
  - `{shortlisted_total}` — `Shortlisted`
- Primary action: `New screening`

### Table column headers (list page, `default` density)

- `Thesis`
- `Status`
- `Criteria`
- `Shortlisted`
- `Started`

Status cell values:
- `Draft criteria`
- `Searching`
- `Ready`
- `Failed`
- `Budget reached`

### Three-step screening flow (`/app/discover/[thesisId]`)

- Breadcrumb: `Screenings / {thesis_title}`
- Back link: `Screenings`
- Step header: `1 Thesis`, `2 Criteria`, `3 Shortlist`
- Step 1 heading: `Describe what you are looking for`
- Step 1 placeholder: `Privately held Indian warehousing and supply-chain software companies that serve enterprise customers and show recent expansion`
- Step 2 heading: `Criteria` · meta: `{must_have} must-have · {preference} preferences`
- Step 2 lead: `Edit before searching. Nothing runs yet.`
- Step 2 column headers: `Criterion`, `Condition`, `Weight`, `Assessed from`
- Step 3 heading: `Shortlist` · meta: `{ranked} ranked · {removed} removed`
- Step 3 caveat: `Fit measures match to your criteria. It says nothing about returns.`

### Filter labels

- Search input placeholder: `Search screenings`
- Status filter: `Status` (`All`, `Ready`, `Searching`, `Draft criteria`, `Failed`)
- Toolbar count: `{shown} of {total}` (or `{total}`)

### Empty states

- No screenings yet (`size="page"`):
  - Title: `No screenings yet`
  - Body: `A screening turns an investment thesis in plain words into editable must-haves and preferences, searches live company records, and ranks the shortlist with fit and assessable share.`
  - Actions: `New screening` (primary)
- Filters return nothing (`size="panel"`):
  - Title: `No screenings match these filters`
  - Body: `Clear the status filter or change your search term.`
  - Action: `Reset filters`
- Shortlist has no matches (`size="panel"`):
  - Title: `No companies matched all must-haves`
  - Body: `{removed} candidates were removed for failing a must-have criterion. Review the removed companies or edit your criteria.`
  - Actions: `Show removed`, `Edit criteria`

### Loading states

- List loading: `LoadingState` (`aria-label="Loading screenings"`, shape `rows`, density `default`)
- Screening detail loading: `LoadingState` (`aria-label="Loading screening"`, shape `lines`)
- After 2 seconds: `Still working`

### Error states

- List error:
  - Title: `Screenings did not load`
  - Body: `{reason}. Nothing was changed.`
  - Action: `Try again`
- Screening detail error:
  - Title: `Screening did not load`
  - Body: `{reason}. Nothing was changed.`
  - Action: `Try again`

### Tooltips

- `Criteria` column: `Count of must-have requirements and weighted preferences applied to the search.`
- `Shortlisted` column: `Companies that passed all assessable must-haves and were ranked by fit.`
- `Draft criteria` status: `Criteria have been parsed and can be edited. No company search has run yet.`
- `Budget reached` status: `The credit budget was reached during enrichment. Companies already scored remain on the shortlist.`

### Button labels

- `New screening`
- `Turn into criteria`
- `Add criterion`
- `Move to must have` / `Move to preference`
- `Remove criterion`
- `Search`
- `Edit criteria`
- `Open case`
- `Show removed` / `Hide removed`
- `Run log`
- `Reset filters`
- `Try again`

---

## 3. Pipeline board (`/app/pipeline`)

### Page header

- Page title (`h1` / nav / breadcrumb / `<title>`): `Pipeline`
- Meta line: `{total} cases · derived from each case record`
- Header figures:
  - `{total}` — `Cases`
  - `{needs_action}` — `Waiting`
  - `{running}` — `Verifying`
- Actions:
  - Segmented view switch: `Board` | `Table`
  - Primary button: `Verify a company`

### Board column headers (fixed order, non-draggable)

1. `Identity` · count: `{n}`
2. `Verifying` · count: `{n}`
3. `Failed` · count: `{n}`
4. `Assessed` · count: `{n}`
5. `Request drafted` · count: `{n}`
6. `Request sent` · count: `{n}`

### Card content lines (max 5 lines)

- Line 1: `{company_name}`
- Line 2: disposition stamp (`size="sm"`) or identity cue (`Identity unresolved · {n} candidates` / `Identity ambiguous · {n} candidates`) or run cue (`Verifying · step {current} of {total}`) or send cue (`Suppressed (test mode) · not sent` / `Sent once`)
- Line 3: `{score} · {pct}%` (or `–` when fit is unavailable)
- Line 4: status counts (`●{s} ◐{p} ◇{cf} ⬣{ct} ?{cv} ◌{nc}`)
- Line 5: `{updated_date}` (mono)

### Table view column headers (`two-line` density, grouped by pipeline state)

- `Company`
- `Stage`
- `Disposition`
- `Fit · assessable`
- `Claims`
- `Updated`

### Filter labels

- Search input placeholder: `Search by company`
- Filter dropdowns:
  - `Disposition` (`All`, `Prioritise`, `Investigate further`, `Deprioritise`, `Cannot assess`, `No disposition yet`)
  - `Screening` (`All screenings`, `{thesis_title}…`)
- Toggle: `Only with Not checked`
- Toolbar count: `{shown} of {total}`

### Empty states

- No cases yet (`size="page"`):
  - Title: `No cases in the pipeline`
  - Body: `Cases move across pipeline columns automatically as DealProof confirms identity, verifies claims, writes an assessment, and records approved requests.`
  - Actions: `New screening` (primary), `Verify a company` (secondary)
- Filters return nothing (`size="panel"`):
  - Title: `No cases match these filters`
  - Body: `Clear a filter or change your search term to see the full board.`
  - Action: `Reset filters`
- Empty board column (column stays visible): `None`

### Loading states

- Board loading: `LoadingState` (`aria-label="Loading pipeline"`, shape `rows`, density `two-line`)
- After 2 seconds: `Still working`

### Error states

- Page error:
  - Title: `Pipeline did not load`
  - Body: `{reason}. Nothing was changed.`
  - Action: `Try again`

### Tooltips

- Board header info / stage explanation: `Pipeline columns reflect each case's verified record. Cases cannot be dragged between stages.`
- `Identity` column: `Cases waiting for legal-entity confirmation before records are attached.`
- `Verifying` column: `Cases with a live verification or recheck run in progress.`
- `Failed` column: `Cases where a run step stopped with an error and can be retried.`
- `Assessed` column: `Cases with a written assessment and no seller request drafted yet.`
- `Request drafted` column: `Cases with a drafted or approved seller request that has not been sent or suppressed.`
- `Request sent` column: `Cases with a sent request, or a request recorded as suppressed in test mode.`
- Suppressed card label: `Email sending is off. Approval was recorded and no message left DealProof.`

### Button labels

- `Board` / `Table`
- `Verify a company`
- `New screening`
- `Reset filters`
- `Try again`

---

## 4. Companies directory (`/app/companies`)

### Page header

- Page title (`h1` / nav / breadcrumb / `<title>`): `Companies`
- Meta line: `{total} companies · {with_case} with a case · {shortlisted_only} shortlisted only`
- Header figures:
  - `{total}` — `Companies`
  - `{with_case}` — `With a case`
  - `{confirmed}` — `Identity confirmed`
- Primary action: `Verify a company`

### Table column headers (fixed order, `two-line` density)

- Selection checkbox column (`aria-label="Select company to compare"`)
- `Company` (line 2: `{domain} · Identity confirmed`, `Identity unresolved · {n} candidates`, or `Shortlisted in "{thesis_title}"`)
- `Disposition` (`No case` in muted ink for shortlisted companies without a case)
- `Fit · assessable`
- `Claims`
- `Size` (`~{headcount} Estimate` or `–`)
- `Updated`
- `Cost` (`{credits} cr` or `–`)

### Filter labels

- Search input placeholder: `Search by company`
- Filter dropdowns:
  - `Disposition` (`All`, `Prioritise`, `Investigate further`, `Deprioritise`, `Cannot assess`, `No disposition yet`, `No case`)
  - `Identity` (`All`, `Confirmed`, `Ambiguous`, `Unresolved`, `Not started`)
  - `Source` (`All`, `Cases`, `Shortlists`)
  - `Screening` (`All screenings`, `{thesis_title}…`)
- Selection toolbar action (enabled when 2 to 4 rows with a case are selected): `Compare ({n})`
- Selection helper (when 1 selected): `Select 1 to 3 more cases to compare`
- Selection limit notice (when 4 selected): `Maximum 4 cases per comparison`
- Toolbar count: `{shown} of {total}`

### Empty states

- No companies yet (`size="page"`):
  - Title: `No companies on file yet`
  - Body: `Companies appear here when a screening returns a shortlist or when you start verification for a company directly.`
  - Actions: `New screening` (primary), `Verify a company` (secondary)
- Filters return nothing (`size="panel"`):
  - Title: `No companies match these filters`
  - Body: `Try clearing one or more filters or changing your search term.`
  - Action: `Reset filters`

### Loading states

- Directory loading: `LoadingState` (`aria-label="Loading companies"`, shape `rows`, density `two-line`)
- After 2 seconds: `Still working`

### Error states

- Directory error:
  - Title: `Companies did not load`
  - Body: `{reason}. Nothing was changed.`
  - Action: `Try again`

### Tooltips

- `Disposition` column: `Screening disposition from the latest assessment. Shortlisted companies without a case show No case.`
- `Fit · assessable` column: `Fit score paired with the share of thesis criteria that had enough evidence to assess.`
- `Claims` column: `Claim counts by status in fixed order: Supported, Partially corroborated, Conflicting evidence, Contradicted, Cannot verify, Not checked.`
- `Size` column: `Headcount estimate from professional profiles, not a payroll count. Shown as a dash when absent.`
- `Cost` column: `External data credits spent on this case. Model usage is shown inside the case's Cost tab.`
- Disabled checkbox on a shortlisted row without a case: `Open a case for this company before comparing it.`
- `Compare ({n})` button when fewer than 2 selected: `Select two to four cases to compare side by side.`

### Button labels

- `Verify a company`
- `Compare ({n})`
- `Clear selection`
- `Open case` (row action on shortlisted companies with no case)
- `New screening`
- `Reset filters`
- `Try again`

---

## 5. Compare (`/app/compare`)

### Page header

- Page title (`h1` / nav / breadcrumb / `<title>`): `Compare`
- Meta line:
  - When cases selected: `{n} cases side by side` (with `· shared thesis: {thesis_title}` when all share one thesis)
  - When empty: `Select two to four cases`
- Actions:
  - `Add a case` (dropdown picker, disabled at 4 cases)
  - `Print` (secondary)

### Matrix group headers and row labels (`compact` density, sticky first column)

- Column headers: `{company_name}` (links to case) + remove icon button (`aria-label="Remove {company_name} from comparison"`)
- Top summary rows:
  - `Disposition`
  - `Identity` (`Confirmed · {n} keys`, `Ambiguous · {n} candidates`, `Unresolved · {n} candidates`)
  - `Fit · assessable`
- Group `Criteria`:
  - One row per shared criterion: `{criterion_name}` (cell values: `Met`, `Not met`, `Unknown`)
  - Replacement row when theses differ: `These cases were scored against different criteria, so fit is not comparable row by row.`
- Group `Claims`:
  - `Settled` (`{settled} of {total}`)
  - `By status` (inline `StatusCounts`)
- Group `Operating signals`:
  - `People` (`~{headcount} Estimate` or `–`)
  - `Latest dated event` (`{event_title}` over `{event_date}`, or `–`)
- Group `Record`:
  - `Sources` (`{source_count}`)
  - `Assessment` (`v{version} · {date}` or `–`)
  - `Cost` (`{credits} cr · {model_cost}`)

### Filter and picker labels

- Case picker search placeholder: `Search cases to add`
- Case picker helper: `Choose two to four cases.`
- Case picker already-selected tag: `Selected`

### Empty states

- Fewer than 2 cases selected (`size="page"`):
  - Title: `Choose two to four cases to compare`
  - Body: `Compare puts each case's disposition, identity, criteria, claim counts, operating signals, and cost side by side without collapsing the five judgments into one winner.`
  - Action: `Add a case` (primary), `Browse companies` (secondary)
- Workspace has fewer than 2 cases total (`size="page"`):
  - Title: `At least two cases are needed to compare`
  - Body: `You currently have {n} case on file. Start another verification or open a case from a screening shortlist.`
  - Actions: `New screening` (primary), `Verify a company` (secondary)

### Loading states

- Matrix loading: `LoadingState` (`aria-label="Loading comparison"`, shape `rows`, density `compact`)
- After 2 seconds: `Still working`

### Error states

- Page error:
  - Title: `Comparison did not load`
  - Body: `{reason}. Nothing was changed.`
  - Action: `Try again`
- Single case missing or deleted from URL query:
  - Inline notice above matrix: `One case in this link is no longer available and was omitted.` + `Copy updated link`

### Tooltips

- `Compare` header info: `No column is marked as a winner. Each judgment stays separate so evidence gaps remain visible.`
- Dash cell (`–`) on `Fit · assessable`: `Fit is unavailable because identity is unresolved or no thesis is attached.`
- Dash cell (`–`) on `People`: `No profile-based headcount estimate on record.`
- Dash cell (`–`) on `Latest dated event`: `No dated public event found for this confirmed entity.`
- Dash cell (`–`) on `Assessment`: `No assessment has been written yet.`
- `Add a case` when 4 cases are loaded: `Remove a case before adding another. A comparison holds up to four cases.`

### Button labels

- `Add a case`
- `Remove` (per column header)
- `Print`
- `Browse companies`
- `Copy updated link`
- `New screening`
- `Verify a company`
- `Try again`

---

## 6. Signals feed (`/app/signals`)

### Page header

- Page title (`h1` / nav / breadcrumb / `<title>`): `Signals`
- Meta line: `{total} items · from {cases} cases` (or `{total} items · from the {cap} most recently updated cases` when capped)
- Header figures:
  - `{events}` — `Company events`
  - `{changes}` — `Assessment changes`
  - `{documents}` — `Documents`

### Feed group headers and row anatomy

- Date group headings: `{date}` (mono, e.g. `22 Nov 2026`, newest first by event date)
- Undated group heading (always last, when undated items exist): `Undated`
  - Group helper: `These items have no reliable date on record and are listed separately.`
- Row structure (no column headers; left-aligned feed in flush panel):
  - Time (`{HH:MM}` when exact time is recorded, blank for date-only events)
  - Company (`{company_name}`, links to case)
  - Entry text:
    - Assessment change: `Assessment v{version} · {old_disposition} → {new_disposition}` (or `Assessment v1 · {disposition}`) + line 2 `Because: {cause}` + source chip
    - Claim status change: `Claim {n} ({claim_category}) · {old_status} → {new_status}` + line 2 `Because: {cause}` + source chip
    - Document received: `Document received · {document_kind}` (or `{filename}` for workspace-scoped case record)
    - Company event: `{event_sentence}` + source chip
  - Nature tag (right-aligned neutral badge): `Announced`, `Reported`, `Recorded`, `Assessment`, `Document`, `Signal`

### Filter labels

- Segmented category filter: `All` | `Company events` | `Assessment changes` | `Documents`
- Dropdown filters:
  - `Company` (`All companies`, `{company_name}…`)
  - `Nature` (`All natures`, `Announced`, `Reported`, `Recorded`, `Assessment`, `Document`, `Signal`)
- Toolbar count: `{shown} of {total}`

### Empty states

- No signals yet (`size="page"`):
  - Title: `No dated signals recorded yet`
  - Body: `Dated public events, assessment version changes, and received documents appear here across your cases as soon as verification runs.`
  - Actions: `New screening` (primary), `Verify a company` (secondary)
- Filters return nothing (`size="panel"`):
  - Title: `No signals match these filters`
  - Body: `Clear a filter or switch back to All to view every recorded item.`
  - Action: `Reset filters`

### Loading states

- Feed loading: `LoadingState` (`aria-label="Loading signals"`, shape `rows`, density `default`)
- After 2 seconds: `Still working`

### Error states

- Feed error:
  - Title: `Signals did not load`
  - Body: `{reason}. Nothing was changed.`
  - Action: `Try again`

### Tooltips

- `Announced` tag: `Published by the company itself. Shows that the company announced something, not that it has happened.`
- `Reported` tag: `Reported by independent press or a third-party publication as of the stated date.`
- `Recorded` tag: `Captured in a registry, funding database, or structured filing as of the stated date.`
- `Assessment` tag: `A versioned change written by DealProof rules after new evidence arrived.`
- `Document` tag: `A file attached to a case in your workspace.`
- `Signal` tag: `An observable indicator such as hiring or headcount movement. Never treated as confirmed revenue.`
- Date sort note: `Ordered by the date the event happened, not when DealProof retrieved it.`

### Button labels

- `All` / `Company events` / `Assessment changes` / `Documents`
- `Reset filters`
- `New screening`
- `Verify a company`
- `Try again`

---

## 7. Investors directory (`/app/investors`)

### Page header

- Page title (`h1` / nav / breadcrumb / `<title>`): `Investors`
- Meta line: `{searches} searches · {investors} investors listed across dated rounds`
- Header figures:
  - `{searches}` — `Searches`
  - `{investors}` — `Investors listed`
- Primary action: `Find investors`

### Searches list column headers (`/app/investors`, `default` density)

- `Business profile` (`{sector} · {location}`)
- `Stage`
- `Funding sought`
- `Investors`
- `Updated`

### Search detail two-pane view (`/app/investors/[id]`)

- Breadcrumb: `Investors / {sector} · {stage}`
- Back link: `Investors`
- Header meta: `{investors} investors · from {companies} comparable companies · {rounds_read} rounds read, {rounds_excluded} excluded`
- Left pane (ranked list):
  - Panel heading: `Ranked investors` · meta: `{ranked}`
  - Row lines: `{rank}`, `{investor_name}`, `{n} comparable rounds · last in sector {month_year}`
  - Unranked footer group (when present): `Not ranked · no dated round` (`{n}`)
  - Fixed caveat under list: `This ranking describes past investments. It does not predict whether an investor will invest. DealProof does not collect personal contact details.`
- Right pane (selected investor detail, four panels):
  - Panel 1: `Comparable rounds` · meta: `{n} dated`
    - Column headers (`compact` density): `Company`, `Round`, `Date`, `Source`
  - Panel 2: `Why they fit`
    - Ranking basis note: `Ranked by comparable rounds and recency in this sector.`
  - Panel 3: `Unknown`
  - Panel 4 (only when applicable): `Possible duplicates`
    - Inline flag: `Possible duplicate of "{other_name}" · not merged`

### Filter labels

- List search placeholder: `Search investor searches`
- Detail filter (in search view):
  - Search input placeholder: `Filter investors by name`
  - Filter dropdown: `Stage` (`All stages`, `Pre-seed`, `Seed`, `Series A`, `Series B`, `Growth`)
  - Toggle: `Only with recent round (18 months)`
- Toolbar count: `{shown} of {total}`

### Empty states

- No investor searches yet (`size="page"`):
  - Title: `No investor searches yet`
  - Body: `Describe a business raising money to find investors who have backed comparable companies, supported by dated funding records.`
  - Action: `Find investors` (primary)
- Search returned no ranked investors (`size="panel"`):
  - Title: `No investors found with dated comparable rounds`
  - Body: `DealProof lists an investor only when a dated funding record connects them to a comparable company. Broaden the sector or stage and search again.`
  - Action: `Edit search`
- Filter returns nothing (`size="panel"`):
  - Title: `No investors match these filters`
  - Body: `Clear the search or stage filter to view the full shortlist.`
  - Action: `Reset filters`
- Right pane when no row selected (`size="panel"`):
  - Title: `Select an investor`
  - Body: `Choose an investor from the list to inspect their dated comparable rounds, fit summary, and unknowns.`

### Loading states

- Searches list loading: `LoadingState` (`aria-label="Loading investor searches"`, shape `rows`, density `default`)
- Search detail loading: `LoadingState` (`aria-label="Loading investor shortlist"`, shape `rows`, density `default`)
- After 2 seconds: `Still working`

### Error states

- Searches list error:
  - Title: `Investor searches did not load`
  - Body: `{reason}. Nothing was changed.`
  - Action: `Try again`
- Search detail error:
  - Title: `Investor shortlist did not load`
  - Body: `{reason}. Nothing was changed.`
  - Action: `Try again`

### Tooltips

- `Comparable rounds` column / heading: `Dated funding rounds in companies matching the sector, location, and stage of this search.`
- `Not ranked · no dated round` group: `An investor appears in the ranking only when at least one dated funding record supports it.`
- `Possible duplicate` flag: `These names may refer to the same firm. DealProof keeps them separate unless confirmed.`
- `Draft outreach` button: `Creates a draft message for a named person to review and approve. DealProof does not collect personal contact details.`

### Button labels

- `Find investors`
- `Edit search`
- `Draft outreach`
- `Run log`
- `Reset filters`
- `Try again`

---

## 8. Approvals inbox (`/app/approvals`)

### Page header

- Page title (`h1` / nav / breadcrumb / `<title>`): `Approvals`
- Meta line:
  - Live mode: `{awaiting} awaiting approval · {total} total`
  - Test mode: `{awaiting} awaiting approval · {total} total · Test mode: nothing is sent`
- Header figures:
  - `{awaiting}` — `Awaiting approval`
  - `{sent}` — `Sent` (live mode) or `{suppressed}` — `Suppressed` (test mode)
  - `{failed}` — `Failed`

### Table column headers (`default` density, flush panel)

- `Company`
- `Documents requested` (`{n} · {short_list}`)
- `Drafted` (`{date_time}`)
- `State`
- `Approver` (`{approver_name}` or `–`)
- Action column (no header): `Review` (for `Draft` / `Approved` / `Failed`) or `View receipt` (for `Sent` / `Suppressed`)

State cell values:
- `Draft`
- `Approved`
- `Sent once`
- `Suppressed (test mode) · not sent` (hatched family, never green)
- `Failed · not sent`

### Filter labels

- Segmented filter tabs (live mode order):
  - `Awaiting approval {n}` (default)
  - `Approved {n}`
  - `Sent {n}`
  - `Suppressed {n}`
  - `Failed {n}`
- Segmented filter tabs (test mode order, `Suppressed` before `Sent`):
  - `Awaiting approval {n}` (default)
  - `Approved {n}`
  - `Suppressed {n}`
  - `Sent {n}`
  - `Failed {n}`
- Search input placeholder: `Search by company`
- Toolbar count: `{shown} of {total}`

### Empty states

- `Awaiting approval` empty (`size="panel"`):
  - Title: `Nothing is waiting for approval`
  - Body: `Requests appear here when a case has open claims a seller document would settle.`
  - Action: `View companies`
- Any other state tab empty (`size="panel"`):
  - Title: `No {state_label} requests`
  - Body: `No seller information requests are currently in the {state_label} state.`
- Search returns nothing (`size="panel"`):
  - Title: `No requests match this search`
  - Body: `Clear the search term or switch tabs to see other requests.`
  - Action: `Reset filters`

### Loading states

- Inbox loading: `LoadingState` (`aria-label="Loading approvals"`, shape `rows`, density `default`)
- After 2 seconds: `Still working`

### Error states

- Inbox error:
  - Title: `Approvals did not load`
  - Body: `{reason}. Nothing was changed.`
  - Action: `Try again`

### Tooltips

- `Review` action: `Opens the case's Request tab so you can check the document list, recipient, and message before approving. Requests are approved one at a time.`
- `Suppressed (test mode) · not sent` state: `Approval was recorded while email sending was off. No email left DealProof.`
- `Failed · not sent` state: `The email provider returned an error. Nothing was retried automatically.`
- `Approver` column: `The named, signed-in person who approved this request. Never automated.`
- Test-mode header notice: `Email sending is off. Approving records the approval and no message leaves DealProof.`

### Button labels

- `Review`
- `View receipt`
- `View companies`
- `Reset filters`
- `Try again`

Note: there is no bulk-approve button and no inline approve button in this table. Every send is one explicit, named decision inside the case's Request tab.

---

## 9. Not-found page (`app/not-found.tsx` and `app/(app)/app/not-found.tsx`)

Both versions sit on the light `paper` ground, left-aligned, never dark and never centred. The in-app version keeps the sidebar and top bar.

### Public not-found (`app/not-found.tsx`)

- Document `<title>`: `Page not found · DealProof`
- Mono label: `404`
- Page title (`h1`): `Page not found`
- Body: `No DealProof page exists at this address. Check the link or return to the home page.`
- Primary button: `Go to home page`
- Secondary button: `Open app`

### Signed-in app not-found (`app/(app)/app/not-found.tsx`)

- Document `<title>`: `Page not found · DealProof`
- Breadcrumb: `Not found`
- Mono label: `404`
- Page title (`h1`): `Page not found`
- Body: `This case, screening, or page does not exist in your workspace, or it may have been deleted.`
- Primary button: `Go to Overview`
- Secondary button: `Browse companies`

### Filters, columns, empty, loading, tooltips

- None. Static page state (`PageState`).

---

## 10. Error page (`app/error.tsx`)

Renders on the light `paper` ground, left-aligned, with neutral surface and `line-strong` border (`role="alert"`). Never uses Contradicted red for a runtime crash.

### Content

- Document `<title>`: `Something went wrong · DealProof`
- Mono label: `Application error` (plus `· reference {digest}` when `error.digest` is present)
- Page title (`h1`): `This page did not load`
- Body: `An unexpected error stopped DealProof from rendering this view. Your saved cases and records were not changed.`
- Detail disclosure (collapsed by default, technical message only when safe): `Technical details`
- Primary button: `Try again` (calls Next.js `reset()`)
- Secondary button: `Go to Overview` (when inside `/app`) or `Go to home page` (outside `/app`)

### Filters, columns, empty, loading, tooltips

- None. Static recovery state (`PageState`).
