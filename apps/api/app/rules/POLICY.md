# DealProof scoring and verification policy

Policy version: **2026-11-22.1** (`POLICY_VERSION` in `app/rules/policy.py`).

DealProof's rules decide every status, score and recommendation. The AI only reads
documents and pulls out values; it never decides. The same records under the same
policy always give the same assessment. When this policy changes, its version
changes, and every assessment records the version it was made under.

## 1. Discover: fit and must-haves

Each criterion gets one of three results: **pass**, **fail** or **unknown**.
No record = unknown.

- **Weights.** A must-have counts 2 and a preference counts 1.
- **Fit** = weight of passed criteria ÷ weight of assessable criteria × 100.
  A criterion is assessable when it passed or failed. When nothing is assessable,
  fit is shown as *unavailable*, never as 0.
- **Assessable share** = assessable criteria ÷ all criteria. Fit always appears with
  it, for example "Fit 82 out of 100, with 70% of the criteria assessable".
- **Missing data never lowers fit.** An unknown lowers the assessable share, not the fit.
- **Only a verified fail excludes a company.** A must-have excludes a company only
  when it fails on a sourced value that is not an estimate. An unknown, or a fail
  that rests on an estimate such as profile-based headcount, keeps the company in.
- The must-have check runs again after enrichment, so a company kept on an
  unknown is removed when a verified failure appears later.
- **Ranking:** fit (unavailable last), then assessable share, then name.

## 2. Verify: claim statuses

A claim is split into components. For example, "Incorporated in 2014, based in
Pune" has an incorporation year and a city. Each component is checked only
against the kinds of source that can answer that question (table below).

**Per component**

1. Facts are screened first. A value is rejected when it cannot be read from its
   quoted text or record field, or when the record is about a different company or
   person. Rejected facts are listed but never decide anything.
2. Copies of the same item (the same press release on several sites) count as
   **one origin**. A set of copies is only as strong as its weakest copy, so a
   republished announcement is still an announcement.
3. Only adequate sources can settle a component. Among those, the most
   authoritative tier present decides:
   tier 1 registry, audited statement, counterparty confirmation;
   tier 2 registry mirror, seller document;
   tier 3 data provider, news, professional profile;
   tier 4 company announcement; tier 5 seller statement.
   Agreement in the deciding tier = **matched**, disagreement with the claim =
   **contradicted**, disagreement among sources in that tier = **conflicting**.
   No adequate source = **unsettled**.

**Combining components (first that applies wins)**

| Order | Status | When |
| --- | --- | --- |
| 1 | Not checked | The check did not run. A reason is always given (budget, source error, source unavailable, no source in scope, identity unresolved). |
| 2 | Contradicted | Any component is contradicted. |
| 3 | Conflicting evidence | Any component has sources that disagree. |
| 4 | Supported | Every component is matched. |
| 5 | Partially corroborated | Some components matched, the rest unsettled. |
| 6 | Cannot verify | Nothing adequate settles any component. |

Every status except Supported names what would settle it, as a document or record type.

**Rules that matter most**

- A company announcement shows that the company announced something, not that it
  happened. It can establish *what was announced*, never *when or whether it happened*.
  A planned facility in an announcement makes "we opened a facility" Partially corroborated.
- Headcount from professional profiles or data providers is a signal. It can never
  support or contradict a payroll count.
- A registered charge shows that security was given, not that money is owed. It is
  shown next to a "no debt" claim but cannot settle it.
- An adequate source that was read and says nothing gives Cannot verify, never Supported.
- A record showing an earlier stage ("planned") contradicts "it is operating" only
  if it is dated after the claimed date.
- Tolerances: headcounts within 5%, money within 2%, percentages within 2 points.

**Which sources are adequate for which question**

| Component | Check | Adequate source classes | What would settle it |
| --- | --- | --- | --- |
| `legal_name` | identity incorporation | audited_statement, registry, registry_mirror | Certificate of incorporation |
| `cin` | identity incorporation | registry, registry_mirror | Certificate of incorporation |
| `incorporation_year` | identity incorporation | audited_statement, registry, registry_mirror | Certificate of incorporation |
| `incorporation_date` | identity incorporation | audited_statement, registry, registry_mirror | Certificate of incorporation |
| `registered_city` | location | registry, registry_mirror | Certificate of incorporation |
| `hq_city` | location | audited_statement, data_provider, registry, registry_mirror, seller_document | Registered-office filing or premises lease |
| `country` | location | audited_statement, data_provider, registry, registry_mirror | Certificate of incorporation |
| `operating_city` | location | counterparty_confirmation, news, registry, seller_document | Registered-office filing or premises lease |
| `employee_count` | team size | audited_statement, registry, seller_document | Dated payroll summary |
| `headcount_growth_pct` | team size | audited_statement, seller_document | Dated payroll summaries for both dates |
| `person_name` | leadership history | news, professional_profile_signal, registry, registry_mirror, seller_document | Founder CV with dates, or an employer's confirmation |
| `role` | leadership history | news, professional_profile_signal, registry, registry_mirror, seller_document | Founder CV with dates, or an employer's confirmation |
| `employer` | leadership history | news, professional_profile_signal, registry, registry_mirror, seller_document | Founder CV with dates, or an employer's confirmation |
| `employer_industry` | leadership history | data_provider, news, professional_profile_signal, registry, registry_mirror, seller_document | Founder CV with dates, or an employer's confirmation |
| `start_year` | leadership history | news, professional_profile_signal, registry, registry_mirror, seller_document | Founder CV with dates, or an employer's confirmation |
| `end_year` | leadership history | news, professional_profile_signal, registry, registry_mirror, seller_document | Founder CV with dates, or an employer's confirmation |
| `raised` | funding | audited_statement, counterparty_confirmation, data_provider, news, registry, registry_mirror, seller_document | Share allotment filing or signed term sheet |
| `round_year` | funding | audited_statement, counterparty_confirmation, data_provider, news, registry, registry_mirror, seller_document | Share allotment filing or signed term sheet |
| `round_date` | funding | audited_statement, counterparty_confirmation, data_provider, news, registry, registry_mirror, seller_document | Share allotment filing or signed term sheet |
| `round_type` | funding | audited_statement, counterparty_confirmation, data_provider, news, registry, registry_mirror, seller_document | Share allotment filing or signed term sheet |
| `amount_usd` | funding | audited_statement, counterparty_confirmation, data_provider, news, registry, registry_mirror, seller_document | Share allotment filing or signed term sheet |
| `investor` | funding | audited_statement, counterparty_confirmation, data_provider, news, registry, registry_mirror, seller_document | Share allotment filing or signed term sheet |
| `announced` | funding | company_announcement, news | Dated company announcement |
| `event` | dated event | company_announcement, counterparty_confirmation, news, registry, seller_document | Dated document showing the event took place |
| `event_date` | dated event | counterparty_confirmation, news, registry, seller_document | Dated document showing the event took place |
| `stage` | dated event | counterparty_confirmation, news, registry, seller_document | Dated document showing the event took place |
| `counterparty` | customer partnership | audited_statement, counterparty_confirmation, seller_document | Customer confirmation or signed contract |
| `relationship` | customer partnership | audited_statement, counterparty_confirmation, seller_document | Customer confirmation or signed contract |
| `since_year` | customer partnership | audited_statement, counterparty_confirmation, seller_document | Customer confirmation or signed contract |
| `contract_value` | customer partnership | audited_statement, counterparty_confirmation, seller_document | Customer confirmation or signed contract |
| `revenue` | financials | audited_statement, registry | Audited financial statements |
| `profit` | financials | audited_statement, registry | Audited financial statements |
| `ebitda` | financials | audited_statement, registry | Audited financial statements |
| `revenue_growth_pct` | financials | audited_statement, registry | Audited financial statements |
| `fiscal_year` | financials | audited_statement, registry | Audited financial statements |
| `has_debt` | debt security | audited_statement, counterparty_confirmation, seller_document | Lender statements |
| `debt_amount` | debt security | audited_statement, counterparty_confirmation, seller_document | Lender statements |
| `security_registered` | debt security | registry, registry_mirror | Registry charge record |
| `lender` | debt security | audited_statement, counterparty_confirmation, registry, registry_mirror, seller_document | Lender statements |
| `has_litigation` | litigation | audited_statement, registry | Litigation disclosure signed by counsel |
| `case_reference` | litigation | registry | Litigation disclosure signed by counsel |

## 3. Evaluate: five separate judgments

The five judgments are never blended into one score.

1. **Opportunity fit:** fit and assessable share, as in section 1.
2. **Evidence sufficiency:** share of the required checks for this type of company
   that adequate evidence settled (supported or contradicted). Whether evidence was
   adequate is recorded separately from what it showed, and each gap is listed with
   the document that would close it.
3. **Business assessment:** observed signals such as headcount estimates and trend,
   open roles, locations and dated events. They are labelled as signals and never
   treated as revenue.
4. **Financial assessment:** made only from figures in audited statements or registry
   filings whose quotes check out. Otherwise "Not assessed: no reliable financial inputs".
5. **Screening disposition:** section 5.

## 4. Company type

- **Startup:** founded within the last 10 years, unless it has more than 500 people
  *and* is past the venture stages (pre-seed to Series C).
- **Established:** founded more than 10 years ago, or young but large and past the
  venture stages. If the founding year is unknown, a company is established only
  when it has more than 500 people.
- The headcount floor of a band is used, for example 201 for "201-500".

| Type | Judged on | Required checks |
| --- | --- | --- |
| Startup | thesis fit, founder relevance, team development, funding history | identity, leadership history, team size, funding |
| Established | strategic fit, identity, operating scale, financial performance, commercial position, leadership continuity | identity, location, team size, leadership history, financials, customers and partnerships |

## 5. Screening disposition

The checks run in this order, and the first one that applies decides.

| Order | Outcome | Rule | When |
| --- | --- | --- | --- |
| 1 | Cannot assess | `identity_uncertain` | Identity is ambiguous or unresolved |
| 1 | Cannot assess | `essential_information_missing` | Fit unavailable, or less than 30% of criteria assessable |
| 2 | Deprioritise | `requirement_failed` | A must-have you set verifiably failed |
| 2 | Deprioritise | `poor_fit_on_good_evidence` | Counting verified results only: fit below 40 with at least 60% of criteria verified |
| 3 | Prioritise | `strong_fit_checks_satisfied` | Fit at least 70, at least 80% of required checks settled, and no required check contradicted, conflicting or not checked |
| 4 | Investigate further | `evidence_incomplete` | Anything else |

**Missing evidence alone never leads to Deprioritise.** An unknown never fails a
criterion, estimate-based results are left out of the poor-fit test, and claim
statuses do not feed the Deprioritise rules.

## 6. Requests

Each open question maps to the document that would settle it: every claim that is
not Supported, an unresolved identity, missing financial inputs for an established
company, and checks that could not run because no reachable source covers them.
Documents are listed once, with links to every question they answer. Checks
skipped for budget or source errors go on a separate list for the analyst to
re-run. They are not asked of the seller.

## 7. Versions and changes

Each assessment records the policy version and a SHA-256 hash of its inputs.
When new evidence arrives, a new version is created and the earlier one is kept.
The comparison lists every claim status change with the evidence that caused it,
every judgment change, and any change in disposition.

## 8. Investors

- Only funding rounds that have a date and a named investor count.
- Records are merged only on the same investor ID, or on the exact same name plus
  a matching website domain, or the same country and investor type. Names that are
  only similar, such as "Orbit" and "Orbit Ventures", are flagged as possible
  duplicates and never merged.
- Score = sum over comparable rounds in the last 6 years of 0.5 ^ (years since the
  round ÷ 2). A round from 2 years ago counts half as much as one from today.
  Ties are broken by number of comparable rounds, then by latest date.
- Each investor shows its latest comparable investment and the search scope it was
  found in. Funding-kind compatibility is *compatible*, *incompatible* or *unknown*.
- The ranking describes past behaviour. It does not predict whether an investor will invest.
