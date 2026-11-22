# DealProof scoring and verification policy

Policy version: **2026-11-22.9** (`POLICY_VERSION` in `app/rules/policy.py`).

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
- **Disputed fields are unknown.** When sources disagree on a field (another
  source gives a value with a different result, or the field's evidence is part
  of a claim with conflicting evidence), the criterion is unknown, never fail.
- **Country codes are country names.** A record's ISO code ("IND") is compared as
  the country it names ("India"); an unknown code is unknown, never a fail.
  Cases assessed under an earlier policy are re-assessed on start-up with the reason
  "policy fix: country code normalisation".
- **Stale fields never exclude.** A field whose record is more than 730 days old
  still counts toward fit, but a fail on it is not verified, so it can neither
  exclude a company nor lead to Deprioritise.
- **In a case, criteria are recomputed from screened evidence.** A field counts
  only when its record is bound to the confirmed company on a corroborating
  identifier (section 2) and comes from a source that can answer a criterion: a
  company announcement or the seller's own statement cannot. A profile-based
  figure counts as an estimate. Anything else is unknown.
- **Activity is read from the company's own text.** A criterion on the activity or
  sector with no provider field passes when the Crustdata description, industries or
  categories state it (the passage is quoted). It fails only when a description of at
  least 12 words never mentions it; otherwise it is unknown. A text match is an
  estimate, so it never excludes a company.
- **Recent expansion is a signal.** It passes when the headcount series grew at least
  10% over about 12 months (the earlier point within 60 days of 12 months back) or
  there are at least 5 open roles (openings count, or postings dated in the last
  180 days). It fails only when both were measured and fell short; otherwise unknown.
  It is labelled a signal from profile headcount and job postings, never confirmed
  expansion, and never excludes a company.
- **Ranking:** fit (unavailable last), then assessable share, then the number of
  sourced signals (headcount, headcount series, growth, openings, recent titles,
  last fundraise date, dated rounds, dated postings, derived signals with evidence),
  then name.

## 2. Verify: claim statuses

A claim is split into components. For example, "Incorporated in 2014, based in
Pune" has an incorporation year and a city. Each component is checked only
against the kinds of source that can answer that question (table below).

**Per component**

1. Facts are screened first. A value is rejected when it cannot be read from its
   quoted text or record field, or when the record is about a different company or
   person. Rejected facts are listed but never decide anything.
   - **Identity binding.** A record counts only when it is attached to one of the
     claim's entities on a corroborating identifier: `case_upload`, `cin`,
     `crustdata_id`, `domain`, `founded_year`, `hq_city`, `profile_url` or
     `registry_id`. A matching name alone is never enough. A claim with no
     corroborated entity accepts no facts and stays Not checked (identity unresolved).
   - **Exact reading.** Values are read with their sign, scale, unit and currency:
     "5 million" is not 5, "-12%" is not 12, and "250" is never read inside "1250".
     Dates may not be more precise than the source: a month or day the source does
     not state is rejected. Yes/no values must match the wording's polarity ("no
     debt"), and negated or future wording ("has not opened", "will be operational")
     never shows that something is operating. No tolerance applies here;
     tolerances belong to comparing a fact with a claim.
2. Copies of the same item (the same press release on several sites) count as
   **one origin**. A set of copies is only as strong as its weakest copy, so a
   republished announcement is still an announcement.
3. Only adequate sources can settle a component. A seller document is adequate
   only when it is the right kind of document for the question (see the table),
   and a payroll count also needs a dated payroll record. A pitch deck or other
   generic document never settles anything.
4. Every adequate independent origin counts, whatever its tier. When they all
   agree with the claim the component is **matched**. When some agree and others
   disagree, or when they disagree with each other, it is **conflicting**: a
   registry and a registry mirror that disagree are conflicting, never ranked
   away. When they agree with each other against the claim it is
   **contradicted**. No adequate source = **unsettled**.
5. A component matched only by company announcements is marked *announced only*,
   so later steps (the memo, the request list) keep saying it was announced.

**Combining components (first that applies wins)**

| Order | Status | When |
| --- | --- | --- |
| 1 | Not checked | The check did not run, or the claim has no corroborated entity. A reason is always given (budget, source error, source unavailable, no source in scope, identity unresolved). |
| 2 | Conflicting evidence | Any component has adequate sources that disagree. |
| 3 | Contradicted | Any component is contradicted. |
| 4 | Supported | Every component is matched. |
| 5 | Partially corroborated | Some components matched, the rest unsettled. |
| 6 | Cannot verify | Nothing adequate settles any component. |

Every status except Supported names what would settle it, as a document or record type.

**Rules that matter most**

- A company announcement shows that the company announced something, not that it
  happened. It can establish *what was announced*, never *when or whether it happened*.
  A planned facility in an announcement makes "we opened a facility" Partially corroborated.
- A dated-event claim always asserts whether the event happened. When it has no
  stage component, one is added from its wording ("opened" → operating), so it can
  be Supported only by evidence that the event happened or the facility operates.
  A seller deck or an announcement never shows that.
- A completed funding round needs a share allotment, a closing statement or a
  receipt of the funds. A term sheet is only an offer.
- The round type is part of a funding claim: a seed round does not support "growth
  funding". The scope of a founder's former employer ("a national logistics firm")
  needs a record about that employer, bound to it by an identifier; the word
  "National" in its name is not evidence of national scope.
- Headcount from professional profiles or data providers is a signal. It can never
  support or contradict a payroll count.
- A registered charge shows that security was given, not that money is owed. It is
  shown next to a "no debt" claim but cannot settle it.
- An adequate source that was read and says nothing gives Cannot verify, never Supported.
- Partnerships, customers, certifications and trademarks (since 2026-11-22.6): the
  company's own page, press release or trust page counts, but a claim matched only by
  the company's own statements is at most Partially corroborated ("the company says
  so"). Supported needs the other party's record: the partner's directory or
  newsroom, the certification body's register, or a trademark registry or its mirror.
- Public search first (since 2026-11-22.6): customer, partnership, certification and
  trademark claims each get at most two targeted public lookups before they can read
  Cannot verify. A lookup carries only the confirmed company name, one public name
  from the claim's structured components (the partner, certifier or mark) and fixed
  words, never the seller's wording. Every lookup is listed on the result
  ("Searched: ..."), and a seller document is asked for only for what they did not find.
- Certifications (since 2026-11-22.7) match on the standard itself: "ISO/IEC
  27001:2022" on a register states "ISO 27001", "SOC 2 Type I" does not state "SOC 2
  Type II". A claim naming several standards is checked once per standard, and each
  standard also asserts that its certificate is current (`certificate_valid_until` on
  or after today), settled only by a validity date from a source that names that
  standard: a current ISO 9001 record says nothing about ISO 27001. The register, the certification
  body's record, or the certificate or auditor's report settle that; the company's own
  page never does. An expired certificate on a register contradicts the claim.
- Trademarks (since 2026-11-22.9): a register page found by search is a copy of the
  register's record (`registry_mirror`) and counts only when the fetched page has a
  labelled proprietor field that is exactly the confirmed company's name, next to the
  mark and a class, and carries a second identifier (address city or domain). A claim
  about a trademark or other IP asks for the trademark registration certificate or IP
  assignment records, not the certificate of incorporation, even when its owner was
  read as `legal_name`; only a mark component routes it to the register lookup.
- Customer counts and satisfaction figures (since 2026-11-22.9): one public lookup for
  the company's customer case studies; named customers found are kept as evidence,
  but no public page counts customers, so the claim stays Cannot verify until a dated
  customer list or reference letters (under NDA) arrive.
  A lookup the case budget refuses is skipped; if all are refused the claim reads
  Not checked (budget). A count of customers is the company's own figure and stays
  Cannot verify unless a dated customer list or audited note settles it.
- A record showing an earlier stage ("planned") contradicts "it is operating" only
  if it is dated after the claimed date.
- Tolerances when comparing with a claim: headcounts within 5%, money within 2%,
  percentages within 2 points.

**Which sources are adequate for which question**

A seller document counts only when it is one of the document types listed; "dated" means it must also carry a date. Questions marked "analyst" cannot be resolved by the seller and are followed up by the analyst.

| Component | Check | Adequate source classes | Seller documents accepted | What would settle it |
| --- | --- | --- | --- | --- |
| `legal_name` | identity incorporation | audited_statement, registry, registry_mirror | none | Certificate of incorporation |
| `cin` | identity incorporation | registry, registry_mirror | none | Certificate of incorporation |
| `incorporation_year` | identity incorporation | audited_statement, registry, registry_mirror | none | Certificate of incorporation |
| `incorporation_date` | identity incorporation | audited_statement, registry, registry_mirror | none | Certificate of incorporation |
| `ownership` | identity incorporation | audited_statement, registry, registry_mirror | none | Certificate of incorporation |
| `registered_city` | location | registry, registry_mirror | none | Certificate of incorporation |
| `hq_city` | location | audited_statement, data_provider, registry, registry_mirror, seller_document | incorporation_certificate, lease, occupancy_evidence | Registered-office filing or premises lease |
| `country` | location | audited_statement, data_provider, registry, registry_mirror | none | Certificate of incorporation |
| `operating_city` | location | counterparty_confirmation, news, registry, seller_document | incorporation_certificate, lease, occupancy_evidence | Registered-office filing or premises lease |
| `employee_count` | team size | audited_statement, registry, seller_document | payroll_record (dated) | Dated payroll summary |
| `headcount_growth_pct` | team size | audited_statement, seller_document | payroll_record (dated) | Dated payroll summaries for both dates |
| `person_name` | leadership history | news, professional_profile_signal, registry, registry_mirror, seller_document | cv, employer_confirmation | Founder CV with dates, or an employer's confirmation |
| `role` | leadership history | news, professional_profile_signal, registry, registry_mirror, seller_document | cv, employer_confirmation | Founder CV with dates, or an employer's confirmation |
| `employer` | leadership history | news, professional_profile_signal, registry, registry_mirror, seller_document | cv, employer_confirmation | Founder CV with dates, or an employer's confirmation |
| `employer_industry` | leadership history | data_provider, news, professional_profile_signal, registry, registry_mirror, seller_document | cv, employer_confirmation | Founder CV with dates, or an employer's confirmation |
| `employer_scope` | leadership history | audited_statement, data_provider, news, registry, registry_mirror | none | Founder CV with dates, or an employer's confirmation |
| `start_year` | leadership history | news, professional_profile_signal, registry, registry_mirror, seller_document | cv, employer_confirmation | Founder CV with dates, or an employer's confirmation |
| `end_year` | leadership history | news, professional_profile_signal, registry, registry_mirror, seller_document | cv, employer_confirmation | Founder CV with dates, or an employer's confirmation |
| `raised` | funding | audited_statement, counterparty_confirmation, data_provider, news, registry, registry_mirror, seller_document | funding_closing, funds_receipt, share_allotment | Share allotment filing, closing statement or bank receipt of the funds |
| `round_year` | funding | audited_statement, counterparty_confirmation, data_provider, news, registry, registry_mirror, seller_document | funding_closing, funds_receipt, share_allotment | Share allotment filing, closing statement or bank receipt of the funds |
| `round_date` | funding | audited_statement, counterparty_confirmation, data_provider, news, registry, registry_mirror, seller_document | funding_closing, funds_receipt, share_allotment | Share allotment filing, closing statement or bank receipt of the funds |
| `round_type` | funding | audited_statement, counterparty_confirmation, data_provider, news, registry, registry_mirror, seller_document | funding_closing, funds_receipt, share_allotment | Share allotment filing, closing statement or bank receipt of the funds |
| `amount_usd` | funding | audited_statement, counterparty_confirmation, data_provider, news, registry, registry_mirror, seller_document | funding_closing, funds_receipt, share_allotment | Share allotment filing, closing statement or bank receipt of the funds |
| `investor` | funding | audited_statement, counterparty_confirmation, data_provider, news, registry, registry_mirror, seller_document | funding_closing, funds_receipt, share_allotment | Share allotment filing, closing statement or bank receipt of the funds |
| `announced` | funding | company_announcement, news | none | Dated company announcement |
| `event` | dated event | company_announcement, counterparty_confirmation, news, registry, seller_document | event_record, lease, occupancy_evidence | Dated document showing the event took place |
| `event_date` | dated event | counterparty_confirmation, news, registry, seller_document | event_record, occupancy_evidence | Dated document showing the event took place |
| `stage` | dated event | counterparty_confirmation, news, registry, seller_document | event_record, occupancy_evidence | Dated document showing the event took place |
| `counterparty` | customer partnership | audited_statement, company_announcement, counterparty_confirmation, seller_document | customer_confirmation, customer_contract | Customer confirmation or signed contract |
| `relationship` | customer partnership | audited_statement, company_announcement, counterparty_confirmation, seller_document | customer_confirmation, customer_contract | Customer confirmation or signed contract |
| `since_year` | customer partnership | audited_statement, company_announcement, counterparty_confirmation, seller_document | customer_confirmation, customer_contract | Customer confirmation or signed contract |
| `contract_value` | customer partnership | audited_statement, company_announcement, counterparty_confirmation, seller_document | customer_confirmation, customer_contract | Customer confirmation or signed contract |
| `customer_count` | customer partnership | audited_statement, seller_document | any | Dated customer list or customer reference letters (under NDA) |
| `country_count` | customer partnership | audited_statement, seller_document | any | Dated customer list or customer reference letters (under NDA) |
| `customer_satisfaction_pct` | customer partnership | audited_statement, seller_document | any | Dated customer list or customer reference letters (under NDA) |
| `certification` | compliance | company_announcement, counterparty_confirmation, registry, registry_mirror, seller_document | any | Certificate from the certification body, with its number, scope and validity, or the auditor's report under NDA |
| `certificate_valid_until` | compliance | counterparty_confirmation, registry, registry_mirror, seller_document | audit_report, compliance_certificate | Certificate from the certification body, with its number, scope and validity, or the auditor's report under NDA |
| `trademark` | intellectual property | company_announcement, registry, registry_mirror, seller_document | any | Trademark registration certificate or IP assignment records |
| `mark_owner` | intellectual property | company_announcement, registry, registry_mirror, seller_document | any | Trademark registration certificate or IP assignment records |
| `revenue` | financials | audited_statement, registry, registry_mirror | none | Audited financial statements |
| `profit` | financials | audited_statement, registry, registry_mirror | none | Audited financial statements |
| `ebitda` | financials | audited_statement, registry, registry_mirror | none | Audited financial statements |
| `revenue_growth_pct` | financials | audited_statement, registry, registry_mirror | none | Audited financial statements |
| `fiscal_year` | financials | audited_statement, registry, registry_mirror | none | Audited financial statements |
| `net_worth` | financials | audited_statement, registry, registry_mirror | none | Audited financial statements |
| `revenue_band` | financials | audited_statement, registry, registry_mirror | none | Audited financial statements |
| `has_debt` | debt security | audited_statement, counterparty_confirmation, seller_document | lender_statement | Lender statements |
| `debt_amount` | debt security | audited_statement, counterparty_confirmation, seller_document | lender_statement | Lender statements |
| `security_registered` | debt security | registry, registry_mirror | none | Registry charge record (analyst) |
| `lender` | debt security | audited_statement, counterparty_confirmation, registry, registry_mirror, seller_document | lender_statement | Lender statements |
| `has_litigation` | litigation | audited_statement, registry | none | Litigation disclosure signed by counsel |
| `case_reference` | litigation | registry | none | Litigation disclosure signed by counsel (analyst) |

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
4. **Financial assessment:** what reliable financial inputs show, under stated
   assumptions. After identity is confirmed, `verify.financials` runs for every case
   and makes at most 2 public lookups, from the confirmed name, CIN and fixed words
   only (never seller text): for a listed company (CIN beginning with `L`, a stock
   symbol or IPO date on the company record, or a "Public Company" type) the exchange
   filing and investor-relations results pages for the latest fiscal year; otherwise
   the registry pages already found, then one registry-mirror search on the name and
   CIN for the revenue band, net worth and last filed year. Each figure keeps its
   verbatim quote, period ("Q2 FY27", "FY24"), unit (crore, lakh, USD) and entity
   binding. The judgment then takes, in order:
   - **Reported figures** from audited statements, exchange or registry filings
     (`audited_statement`, `registry`, `registry_mirror`), or a listed company's own
     results page (`company_announcement`, listed companies only), whose quotes check
     out and whose records are bound to the company on a corroborating identifier:
     the same screen claims and fit use. Reported with the latest period, growth
     against the period of the same length a year earlier (or the one before it),
     margins in the same period and currency, the assumptions, and a bounded
     conclusion such as "Reported revenue ₹2,095 cr in Q2 FY27, +24% YoY (NSE
     filing)". Never a valuation, forecast or fair value.
   - Otherwise a data provider's revenue range, shown as **"Indicative (estimate)"**
     and never counted as assessed.
   - Otherwise, once the search ran, **"No public financials found — searched: …"**
     with what was searched and what would settle it. Before the search has run:
     "Not assessed: no reliable financial inputs".
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
| 2 | Deprioritise | `requirement_failed` | A must-have you set verifiably failed, including a Contradicted claim on that must-have (below) |
| 2 | Deprioritise | `poor_fit_on_good_evidence` | Counting verified results only: fit below 40 with at least 60% of criteria verified |
| 3 | Prioritise | `strong_fit_checks_satisfied` | Fit at least 70, every required check that v1 covers Supported on adequate evidence, no required check contradicted, conflicting or not checked, no material claim anywhere in the ledger contradicted or conflicting, no material claim outside those checks unverified, and no must-have criterion unknown |
| 4 | Investigate further | `evidence_incomplete` | Anything else |

What each situation leads to (`DISPOSITION_TABLE` in `policy.py`; the rules read it):

| Situation | Leads to |
| --- | --- |
| Unverified optional claim | Investigate further, if the claim is material |
| Unverified mandatory criterion | Decision blocker: blocks Prioritise until verified, never Deprioritise |
| Contradicted non-mandatory claim | Investigate further, if the claim is material |
| Verified failure of a mandatory criterion | Deprioritise |
| Poor thesis fit despite sufficient evidence | Deprioritise (verified results only) |
| Unresolved identity | Cannot assess |

"Optional" means outside the required checks v1 covers; inside them the required-check
rule applies. **A contradicted claim on a must-have.** A claim component maps to a
criterion dimension (`COMPONENT_CRITERION_DIMENSIONS`: `country` → geography,
`ownership` → ownership, `employee_count` → size, `headcount_growth_pct` → growth
signal, `round_type` → funding stage, `incorporation_year` → founded year). When a claim is
Contradicted on such a component, and the claimed value is exactly the one a
must-have of that dimension requires (an equality, a single allowed value, or "is
true"), the must-have has verifiably failed: a seller who claims "privately held"
against a registry that shows a listed company fails a "privately held" must-have.
A contradicted number never says on which side of a threshold the real figure lies,
so thresholds are never failed this way.

**Missing evidence alone never leads to Deprioritise.** An unknown never fails a
criterion, a disputed criterion is unknown, estimate-based and stale results are
left out of the poor-fit test, and claim statuses do not feed the Deprioritise rules
except through a contradicted claim on a must-have, as above.

**What v1 covers.** The first version checks identity, location, team size,
leadership history, funding and dated events. For Prioritise, every one of these
that is required for the company type must be complete; a required check that was
never claimed, or was skipped, is a gap and blocks Prioritise. Required checks v1
does not cover (financials and customers for an established company) are still
listed as gaps and requested, but do not block Prioritise. A material claim that is
Contradicted or Conflicting blocks Prioritise wherever it sits in the ledger, even
outside the required checks.

## 6. Requests

Each open question is about one unresolved component of a claim (for example the
date and the operating stage of an announced facility, not the facility itself) and
maps to the document that settles that component. Questions also come from an
unresolved identity, missing financial inputs for an established company, and checks
that could not run because no reachable source covers them.

A completed funding round is settled by a share allotment, a closing statement or a
bank receipt of the funds; a term sheet is never requested as proof.

Whether the seller can resolve a question is recorded separately from its status.
Questions only the analyst can follow up (such as a registry charge record) go on the
analyst's list and are never sent to the seller. Documents are listed once, with links
to every question they answer. Checks skipped for budget or source errors go on a
separate list for the analyst to re-run.

## 7. Versions and changes

Each assessment records the policy version and a SHA-256 hash of its inputs.
When new evidence arrives, a new version is created and the earlier one is kept.
The comparison lists every claim status change with the evidence that caused it,
every judgment change, and any change in disposition.

**Policy changes**

- 2026-11-22.7: certifications match on the standard itself and must be current:
  an expired certificate on a register contradicts the claim.
- 2026-11-22.6: public lookups for partnership, customer, certification and
  trademark claims; new categories `compliance` and `intellectual_property`; a
  company's own statement alone gives Partially corroborated in those categories;
  trademark claims ask for the registration certificate or IP assignment records.
- 2026-11-22.5: Discover reads activity and expansion signals; ties break on signals.
- 2026-11-22.4: country code normalisation.

## 8. Investors

- Only funding rounds that have a date and a named investor count.
- Records are merged on the same investor ID, or directly on the same website
  domain, or on the exact same name plus a matching country and investor type
  recorded on the *same* record as that name. A name on one record and a matching
  attribute on another is not enough. A known identifier that conflicts anywhere in
  the group (a different domain) blocks the merge. Names that are only similar, such
  as "Orbit" and "Orbit Ventures", are flagged as possible duplicates and never merged.
- Score = sum over comparable rounds in the last 6 years of 0.5 ^ (years since the
  round ÷ 2). A round from 2 years ago counts half as much as one from today.
  Ties are broken by number of comparable rounds, then by latest date.
- Each investor shows its latest comparable investment and the search scope it was
  found in.
- Funding-kind compatibility reads only dated rounds inside the searched scope, on or
  before the search date. It is *compatible* only when such a round of the kind
  sought exists; otherwise it is *unknown*. Not finding a matching round in a bounded
  search never makes an investor incompatible.
- The ranking describes past behaviour. It does not predict whether an investor will invest.

## 9. DecisionFlip

DecisionFlip answers which open items stand between a case and the next disposition.
It never asks a model: it re-runs the same disposition rules (`redecide`, the code
`assess` uses) with items forced to a hypothetical state. Nothing it produces is
evidence, and every result is labelled hypothetical.

- **Items.** A claim that is not Supported (`claim:<id>`), a required check never
  claimed (`check:<category>`), an unknown criterion (`criterion:<id>`), an
  unconfirmed identity (`identity`) and missing financial inputs (`financial_inputs`).
  Each is forced Supported (or pass, or confirmed) and, where it is not already in
  that state, Contradicted (or fail). Everything else stays as it really is; forcing
  a claim does not re-evaluate criteria.
- **Target.** The ladder is Cannot assess < Investigate further < Prioritise;
  Deprioritise is off it. The target is the next rung up, if forcing every item
  Supported reaches it. Otherwise the case has no blockers (Prioritise), is
  disqualified (Deprioritise rests on verified evidence; nothing is simulated to undo
  it), or is not evidence-limited (no evidence moves it).
- **Minimum set of checks required to change the screening outcome.** The smallest
  sets of items that, all Supported, reach the target, found by trying every subset
  when there are at most 6 items and by dropping items one by one otherwise (then it
  is a sufficient set, not necessarily the smallest). The set shown is the one with
  the fewest checks; ties go to lower estimated effort (`DOCUMENT_EFFORT`: low,
  medium or high per document), then fewer documents, then fewer analyst-only items.
  It is never described as the cheapest.
- **Classes.** A decision blocker is in a minimum set. A disqualifier risk is an item
  whose Contradicted branch gives Deprioritise under `requirement_failed`: an unknown
  must-have, or an unresolved claim on a must-have's dimension. Everything else is
  non-blocking.
- **Next best action** comes from fixed templates. For a criterion or a financial
  item it always states both branches ("If the verified figure is at least 100,
  Headcount passes; otherwise it fails"): obtaining a document settles a question, it
  does not make the company qualify.
- Every analysis records the policy version, the inputs hash, its own version and a
  key over those and each claim's materiality, so the same version gives the same
  analysis.

