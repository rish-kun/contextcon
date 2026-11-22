# DealProof finished case memo template

Source of truth: `DealProof product description.md` ("What a finished case contains") and `docs/design/design-direction.md` (Sections 11.6 and 11.7).

This template defines the exact section order, headings, and boilerplate for the screening memo rendered in the Case `Overview` tab and printed to A4 PDF.

### Formatting and rendering rules

- Every factual statement ends with a numbered citation (`[1]`, `[2]`) linked to an interactive source chip on screen and a footnote/entry in `Sources` in print. If a sentence states a figure without a source, omit it.
- Dates use `14 Oct 2026` (or `Oct 2026`). Timestamps use `22 Nov 2026, 16:42 IST`.
- Estimates always carry a leading tilde and the word `Estimate` (for example, `~180 people Estimate`). Observable operating indicators carry `Signal`.
- Claim statuses render with both glyph and full label in the fixed order: `Supported`, `Partially corroborated`, `Conflicting evidence`, `Contradicted`, `Cannot verify`, `Not checked`.
- `Not checked` items always retain their dashed border, hatch pattern, and reason, and are never omitted from the first-page summary.
- When a memo prints for an illustrative demo case, display `Illustration, not a real company` directly under the title.

---

## Print running header and footer

- **Running header (9pt):**
  - Left: `DealProof · Screening memo`
  - Right: `{company_legal_name}`
- **Running footer (9pt):**
  - Left: `Screening only. Not financial, legal or tax due diligence.`
  - Right: `Page {page_number} of {total_pages}`

---

## Cover and first-page summary

```markdown
Screening memo

# {company_legal_name}

Version {version} · {generated_date} · Policy {policy_version} · Prepared for {client_or_team_name}
```

*Conditional line for demo cases only:*
`Illustration, not a real company`

### Summary block (always on page 1)

- **Screening disposition:** `{disposition_stamp}`
  - Reasons:
    - `{reason_1}` (rests on `{claim_or_criteria_refs}`)
    - `{reason_2}` (rests on `{claim_or_criteria_refs}`)
- **Opportunity fit:** `Fit {fit_score} · {assessable_pct}% of criteria assessable`
  - `{assessed_count} of {total_criteria} criteria assessable · {unknown_count} unknown: {unknown_criteria_list}`
  - *Caveat:* `Fit measures match to your criteria. It says nothing about returns.`
- **Evidence sufficiency:** `{settled_count} of {total_checks} checks settled · {not_checked_count} not checked`
  - *Conditional warning (shown whenever `not_checked_count > 0`):* `{not_checked_count} checks were not run ({not_checked_reasons}). Results are incomplete where marked Not checked.`
- **Case cost:** `{credits_used} of {credits_budget} credits · {model_cost} model usage`
- **Scope notice:** `First-pass screening before formal due diligence. Every finding rests on the dated sources recorded at the end of this memo.`

---

## Conditional section: What changed since version {previous_version}

*Include directly after the first-page summary whenever `version > 1`. Omit for `version 1`.*

```markdown
## What changed since version {previous_version}

Updated on {updated_timestamp} after receiving "{trigger_document_name}" from the seller. Version {previous_version} remains archived and readable in full.

- **Claim {claim_number} ("{claim_text}"):** {old_status} → {new_status}
  Because: {change_reason} [{citation_id}]
- **Evidence sufficiency:** {old_settled} of {total} settled → {new_settled} of {total} settled
- **Screening disposition:** {old_disposition} → {new_disposition}
  Because: {disposition_change_reason}

{unchanged_count} claims unchanged since version {previous_version}.
```

---

## 1. The opportunity

```markdown
## 1. The opportunity

### Investment thesis
{thesis_statement}

### Why this company is relevant
{two_to_four_sentences_linking_confirmed_company_facts_to_thesis_criteria_with_citations}

### Criteria summary
- **Criteria met ({met_count}):** {met_criteria_with_citations}
- **Criteria not met ({not_met_count}):** {not_met_criteria_with_citations}
- **Criteria unknown ({unknown_count}):** {unknown_criteria_list}

*Evaluation lens:* {evaluation_lens_note}
```

**Boilerplate for `{evaluation_lens_note}` (choose one):**
- For a young startup: `Evaluated as an early-stage business on thesis fit, founder relevance, team development, and funding history.`
- For an established business: `Evaluated as an established business on strategic fit, identity, operating scale, financial performance, commercial position, and leadership continuity.`

---

## 2. Identity and profile

```markdown
## 2. Identity and profile
```

### State A: Identity confirmed

```markdown
**Identity confirmed.** Records in this case were attached using the following verified keys, not on a matching name alone:

| Identity key | Confirmed value | Source |
| --- | --- | --- |
| Legal name | {legal_name} | [{citation_id}] |
| Registration number | {registration_number} | [{citation_id}] |
| Domain | {domain} | [{citation_id}] |
| Registered city | {registered_city} | [{citation_id}] |
| Incorporated | {incorporation_date} | [{citation_id}] |
```

### State B: Identity unresolved

```markdown
**Identity unresolved.** DealProof found {candidate_count} candidate legal entities matching "{submitted_name}" and did not attach unconfirmed records. Screening disposition remains Cannot assess until the entity is confirmed.

| Candidate entity | Matching keys | Differing keys | Source |
| --- | --- | --- | --- |
| {candidate_1_name} | {matching_keys} | {differing_keys} | [{citation_id}] |
| {candidate_2_name} | {matching_keys} | {differing_keys} | [{citation_id}] |
```

### Company profile (when identity is confirmed)

```markdown
### Public profile

| Field | Value | Source |
| --- | --- | --- |
| Business and industry | {business_description} | [{citation_id}] |
| Headquarters | {hq_location} | [{citation_id}] |
| Ownership | {ownership_status} | [{citation_id}] |
| Funding history | {funding_summary} | [{citation_id}] |

### Leadership and founders
{leadership_rows_with_role_dates_match_key_and_citation}

*Matching rule:* Career records are attached only where matched on company identifier and name. Name-only matches are excluded from this table.

### Operating signals
{dated_operating_signals_each_marked_Estimate_or_Signal_with_basis_and_citation}

*Note:* Operating signals and profile-based headcount estimates are indirect indicators. They are not payroll counts and are never treated as proof of revenue.
```

---

## 3. Claims

```markdown
## 3. Claims

Summary: {supported_count} Supported · {partial_count} Partially corroborated · {conflicting_count} Conflicting evidence · {contradicted_count} Contradicted · {cannot_verify_count} Cannot verify · {not_checked_count} Not checked.

| # | Seller said | Status | What the record shows | What would settle it |
| --- | --- | --- | --- | --- |
| {n} | "{seller_claim}" ({claim_category}, {claim_source}) | {status} | {evidence_summary} [{citation_id}] | {document_needed_or_dash} |
```

**Boilerplate rules for the table:**
- For `Partially corroborated`, state both `Supported: {supported_part}` and `Not supported: {unsupported_part}` in the record column.
- For `Conflicting evidence`, name both disagreeing sources and what each states.
- For `Cannot verify`, always name the specific document in `What would settle it`.
- For `Not checked`, print the reason (`Not checked · budget reached`, `Not checked · source unavailable`, or `Not checked · step failed`) and state `No search was run for this claim.`

**Footnote beneath table:**
`Cannot verify is a finished screening result where available records cannot settle the question. Not checked indicates that a check did not run and is excluded from settled counts.`

---

## 4. Recent events

```markdown
## 4. Recent events

Dated public events recorded for {company_legal_name}, newest first.

| Date | Event | Nature | Source |
| --- | --- | --- | --- |
| {event_date} | {one_sentence_event_summary} | {Announced / Reported / Recorded} | [{citation_id}] |
```

**Boilerplate notes:**
- When no dated events were found: `No recent dated public events were returned on record for this confirmed entity.`
- Plan-announcement rule: `Company announcements describing planned launches or expansions are worded as plans unless independent records confirm execution.`
- Conditional subsection when undated items exist:
  ```markdown
  ### Undated items
  The following items had no reliable date on record and are listed separately from the dated timeline:
  - {undated_item} [{citation_id}]
  ```

---

## 5. Comparable companies

### State A: Fair comparison exists

```markdown
## 5. Comparable companies

Basis of comparison: {comparison_basis} (for example, same activity, region, and size band). Informational only — comparables are not scored.

| Company | Activity | Region | Size band | Funding stage | Source |
| --- | --- | --- | --- | --- | --- |
| {peer_name} | {activity} | {region} | ~{size_band} Estimate | {stage} | [{citation_id}] |
```

### State B: No fair comparison exists

```markdown
## 5. Comparable companies

**No fair comparison found.** {reason_no_fair_comparison_exists}

DealProof does not substitute a weaker peer list when records do not support a fair comparison.
```

---

## 6. Financial evaluation

### State A: No reliable financial inputs exist

```markdown
## 6. Financial evaluation

**Not assessed · no reliable financial inputs.**

Public records for private companies in India do not provide complete current financial statements for this entity, and no audited statements were supplied for this case. DealProof does not fill missing financial inputs with guesses.

- **Would need:** {needed_financial_documents} (for example, audited financial statements for the last three financial years and current management accounts).
```

### State B: Reliable financial inputs exist

```markdown
## 6. Financial evaluation

### Reliable inputs on file
{table_of_supplied_or_filed_figures_with_currency_period_and_citations}

### Stated assumptions
- {assumption_1}
- {assumption_2}

### Scenario outputs
{scenario_table_under_stated_assumptions}

*Scope note:* These figures reflect stated scenarios from the supplied inputs under the assumptions listed above. They are not a valuation, a verified fair value, or financial due diligence.
```

---

## 7. Risks, assumptions and unknowns

```markdown
## 7. Risks, assumptions and unknowns

Missing information is stated plainly and is not treated as negative performance.

### Risks observed on record
- {risk_item_with_citation}

### Assumptions stated
- {assumption_item}

### Unknowns remaining
- {unknown_item_and_what_would_resolve_it}
```

*Fallback when a list has no items:*
- Risks: `No material risks were identified within the sources checked. Refer to unknowns and any Not checked items below.`
- Assumptions: `No financial or operating assumptions were applied in this screening.`
- Unknowns: `No material unknowns remain within the criteria and claims checked.`

---

## 8. Recommended next step

```markdown
## 8. Recommended next step

**Disposition:** {disposition_stamp} (Policy {policy_version})

### Reasons
1. {reason_1_with_claim_or_criteria_ref}
2. {reason_2_with_claim_or_criteria_ref}

### Recommended action
{concrete_next_step_for_the_team}

*Decision note:* This disposition is produced by stated rules under Policy {policy_version} from the records attached to this case. It is a first-pass screening recommendation, not a prediction of returns, legal advice, or formal due diligence.
```

---

## 9. Information to request from the seller

```markdown
## 9. Information to request from the seller

The following documents would settle the open claims in this case:

1. **{document_1}** — settles Claim {claim_number} ("{short_claim_ref}")
2. **{document_2}** — settles Claim {claim_number} ("{short_claim_ref}")
3. **{document_3}** — settles Claim {claim_number} ("{short_claim_ref}")
```

### Request approval and delivery status (choose one)

- **Draft (awaiting approval):**
  `Request status: Draft. Waiting for review and approval by a named person. Nothing has been sent.`
- **Sent once (live mode):**
  `Request status: Sent once. Approved by {approver_name} on {approved_timestamp}. Sent to {recipient_address} requesting {document_count} documents.`
- **Suppressed (test mode):**
  `Request status: Suppressed (test mode) · not sent. Approved by {approver_name} on {approved_timestamp}. Email sending was off; nothing left DealProof.`
- **Failed (not sent):**
  `Request status: Failed · not sent. Attempted after approval by {approver_name} on {approved_timestamp}. Provider error: {provider_reason}. No automatic retry occurred.`
- **No request needed:**
  `No seller request is required at this stage.`

---

## 10. Sources

```markdown
## 10. Sources

Complete record of every source used in this case so all findings can be audited and reproduced.

| # | Source class | Source name | URL or request parameters | As-of date | Retrieved at |
| --- | --- | --- | --- | --- | --- |
| [1] | {source_class} | {source_name} | {url_or_request} | {as_of_date_or_unknown} | {retrieved_timestamp} |
```

### Printed page footnote format

```text
¹ {source_name}, as of {as_of_date}, retrieved {retrieved_timestamp}
```

### Document confidentiality footer (when seller files were uploaded)

```text
Confidentiality: Uploaded seller documents were used only for this case, were not used to train AI models, were not shared across customers, and are scheduled for deletion on {deletion_date}.
```
