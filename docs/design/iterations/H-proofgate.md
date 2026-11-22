# H. ProofGate

Risk-adaptive, claim-level validation inside the existing verify pipeline. Refines `H-proofgate-brief.md` into something three builders can start on today.

Read against: the brief, `F-decisionflip.md`, `apps/api/app/rules/` (policy `2026-11-22.3`, `POLICY.md`), `apps/api/app/pipelines/verify/checks/` and `tests/rules/prd_fixtures.py`. There is no standalone PRD file in the repo; "PRD" below means the principles those files cite.

## 0. What ProofGate is, in one page

Today every claim gets the same treatment: one gatherer per category, and five categories (`customer_partnership`, `financials`, `debt_security`, `litigation`, `other`) go to `gather_nothing`, which is why Mahindra's Q2 FY27 revenue came back Cannot verify with no search made.

ProofGate adds three things and replaces nothing:

1. **A score pair per claim component.** *Evidence Assurance* says how well the evidence we already hold stands up. *Verification Priority* says how much a further check is worth. Both are heuristics that order work. Neither is a verdict.
2. **A gate.** Priority ≥ 65, or one of five forced triggers, earns the claim up to two targeted lookups, in parallel, inside a time and credit budget.
3. **A stricter reading of what comes back.** Each returned fact is tested on entity, value, unit, period and semantics before the existing rules see it, and copies of one report count once.

The verdict is still `rules.decide_claim_status`, unchanged, returning the existing six `ClaimStatus` values. ProofGate only changes which facts reach it and in what order claims are worked.

Rules that hold everywhere in this spec:

- A score never sets a status. No "assurance ≥ 80 ⇒ Supported".
- Conflicting values are shown side by side, never averaged, never resolved by majority.
- A lookup that fails, times out or is refused by the budget leaves the claim `cannot_verify` or `not_checked` with a reason. Nothing is guessed.
- ProofGate creates no approval, message or send.
- Public sources are searched first for every claim category, whatever was uploaded (§5.1).

---

## 1. Data model

Migration `0010_proofgate.py`. Three additions, all beside existing rows; `claim_checks` stays append-only and remains the only place a status lives.

### 1.1 `evidence`: three nullable columns

The brief's stored fields map onto what exists, except unit and period.

| Brief field | Where it lives |
| --- | --- |
| entity ID | `evidence.entity_ref` (existing) |
| claim type | `claims.category` + component name (existing) |
| original value | `evidence.value` for evidence; `claims.components[*].value` for the claim (existing) |
| units | **new** `evidence.unit` `varchar(32)`; claim side in `claims.components[*].unit` |
| period | **new** `evidence.period` `jsonb`; claim side in `claims.components[*].period` |
| source | `sources` row (existing: provider, url, class, publisher) |
| source field | `evidence.field_path`, `span`, `page` (existing) |
| record date | `evidence.as_of` (existing) |
| retrieval time | `sources.retrieved_at` (existing) |

Also **new** `evidence.semantics` `varchar(48)`: the metric definition the source used (§6.5).

`unit`: `{currency|null}:{scale}` for money (`INR:crore`, `USD:million`), `count`, `percent`, or null. `value` keeps the number as written; `value_base` (inside the `period`-sibling JSON, see below) keeps the normalised absolute number so comparisons never re-parse text.

`period`:

```json
{"type": "quarter|half|year|ttm|point|range|unknown",
 "start": "2026-07-01", "end": "2026-09-30",
 "label": "Q2 FY27", "fiscal_year_end_month": 3,
 "value_base": 1234500000000}
```

Claim components gain the same `unit`, `period` and `semantics` keys in their JSONB. Old rows without them read as `unknown`, which is safe (§6).

### 1.2 `proofgate_validations`

One row per claim component per round. This is the restart-safe state and the audit record.

```
proofgate_validations
  id                  uuid pk
  workspace_id        fk workspaces
  case_id             fk cases, indexed
  claim_id            fk claims, indexed
  component           varchar(64)
  entity_ref          varchar(500)
  claim_type          varchar(64)          -- claims.category at the time
  claimed             jsonb                -- {value, unit, period, semantics, source: {document_id, page, origin}, record_date}
  round               smallint             -- 1 = in the claim check, 2 = after DecisionFlip
  plan_key            varchar(64)          -- sha256, §10
  state               varchar(24)          -- planned | running | decided | skipped | failed
  skip_reason         varchar(32) null     -- below_threshold | budget_exhausted | claim_cap | no_playbook | identity_unresolved
  triggers            jsonb                -- ["priority", "mandatory_criterion", ...]
  scores              jsonb                -- §2.4, inputs and results, before and after
  priority            numeric(5,1)         -- column copy for ordering
  assurance_before    smallint
  assurance_after     smallint null
  dimensions          jsonb null           -- per lookup: entity/value/unit/period/semantics
  claim_check_id      fk claim_checks null -- the outcome this validation fed
  status_before       varchar(32) null
  status_after        varchar(32) null
  credits             numeric              -- sum of its lookups
  latency_ms          int null             -- wall clock, plan to decided
  policy_version      varchar(64)
  proofgate_version   varchar(32)
  sensitivity_source  varchar(16)          -- analysis | previous_version | default
  flip_analysis_id    fk decision_flip_analyses null
  run_id, step_id     fk null
  created_at, updated_at
  unique (claim_id, component, plan_key)
```

`claimed` holds a claim value, so the row gets `delete_after` and `scrubbed_at` like `claims`, and the purge job nulls `claimed` and `dimensions`. `scores` holds numbers and enums only.

### 1.3 `proofgate_lookups`

One row per targeted lookup. At most two per validation.

```
proofgate_lookups
  id               uuid pk
  validation_id    fk proofgate_validations, indexed
  slot             smallint               -- 1 | 2
  playbook         varchar(48)            -- §5 id, e.g. "financials.listed.exchange_filing"
  request_key      varchar(64)            -- sha256(provider, endpoint, canonical params)
  state            varchar(24)            -- planned | running | ok | empty | error | timeout | budget
  source_id        fk sources null
  origin_key       varchar(200) null      -- §7 cluster key
  facts            smallint               -- facts that passed all five dimensions
  rejected         smallint
  credits          numeric
  usd              numeric
  cached           boolean
  latency_ms       int null
  error            varchar(200) null      -- class and short message, no payload
  call_attempt_ids uuid[]
  started_at, finished_at
  unique (validation_id, slot)
```

Costs are still written by the existing recorder to `cost_entries`; the lookup row copies the totals so the UI needs no join.

### 1.4 Domain types (`app/domain/types.py`)

```python
class Period(Model): type; start; end; label; fiscal_year_end_month
class Quantity(Model): value; unit; value_base; period; semantics
class DimensionCheck(Model): entity; value; unit; period; semantics   # each: match | mismatch | unknown
class AssuranceInputs(Model): ...   # §2.1, one field per input
class PriorityScore(Model): materiality; assurance; sensitivity; staleness; priority; triggers; forced
class ValidationPlan(Model): claim_id; component; score; lookups: list[LookupSpec]; skip_reason
```

---

## 2. Evidence Assurance

A 0–100 heuristic for one claim component, computed from the facts already attached to it. It answers "how much would a careful reader lean on this evidence", not "how likely is the claim true". The UI always labels it so (§11).

Pure function, `rules/proofgate.py: assurance(component, facts, identity, today) -> AssuranceScore`. No I/O, no clock (today is passed in), like the rest of `rules/`.

### 2.1 Inputs and weights

Weights sum to 100. Constants live in `policy.py` under `ASSURANCE_WEIGHTS`.

| Input | Weight | Scoring |
| --- | --- | --- |
| **Source class** | 35 | Best fact's class against the component's `ComponentRule.adequate`: in `adequate` → 35. Otherwise by class: `exchange_filing`, `registry`, `audited_statement`, `counterparty_confirmation` 28 · `company_announcement` 20 · `news` 16 · `data_provider` 14 · `professional_profile_signal` 10 · `seller_document` 7 · `seller_statement` 0 |
| **Independent origins** | 20 | Distinct origin clusters (§7) that state a matching value, seller-controlled sources excluded: 0 → 0, 1 → 10, 2 or more → 20 |
| **Entity binding** | 15 | A corroborating identifier on the source (`policy.CORROBORATING_IDENTIFIERS`, plus ticker and ISIN) → 15. Provider id attached to the confirmed entity → 10. Name only → 0 |
| **Value, unit, period agreement** | 15 | Value within the kind's tolerance 7 · unit stated and equal after normalisation 4 · period stated and equal 4. `unknown` scores 0, not partial |
| **Freshness** | 10 | `10 × (1 − staleness/100)` using §3.2 |
| **Extraction integrity** | 5 | Value found verbatim in the stored span (`validation.value_in_span`) or read from a structured field → 5 |

### 2.2 Caps

Applied after the sum. The lowest cap wins. Each cap that fired is listed in `scores.caps`.

| Condition | Cap |
| --- | --- |
| Case identity not `confirmed` | 20 |
| Only seller-controlled sources (`seller_document`, `seller_statement`) | 25 |
| Independent origins disagree on the value | 30 |
| Any matching fact has `semantics: mismatch` | 40 |
| Unit or period `unknown` on every matching fact | 60 |
| No fact at all | 0 |

### 2.3 Bands

`Low` 0–39 · `Moderate` 40–69 · `High` 70–100. Bands are display only. No code branches on a band.

### 2.4 The stored document

```json
{"assurance": {"score": 46, "band": "moderate",
               "inputs": {"source_class": 16, "origins": 10, "entity": 15, "agreement": 0, "freshness": 0, "integrity": 5},
               "caps": ["unit_or_period_unknown"]},
 "materiality": {"score": 100, "basis": "mandatory_criterion", "criterion_id": "…"},
 "sensitivity": {"score": 85, "basis": "in_minimum_evidence", "source": "analysis"},
 "staleness":   {"score": 100, "basis": "no_dated_evidence", "window_days": 135},
 "priority": 82.2, "threshold": 65, "forced": ["mandatory_criterion"]}
```

---

## 3. Materiality and staleness

### 3.1 Materiality (0–100)

How much the decision rests on this component. Deterministic, the maximum of the rows that apply.

| Situation | Score | Basis id |
| --- | --- | --- |
| Component maps (`policy.COMPONENT_CRITERION_DIMENSIONS`) to a **must-have** criterion of the case's thesis | 100 | `mandatory_criterion` |
| Category is `identity_incorporation` | 100 | `identity` |
| Harmful allegation (§4.2) | 90 | `harmful_allegation` |
| Category is a required check for the company type (`rules.required_checks`) | 80 | `required_check` |
| Component maps to a **preference** criterion | 60 | `preference_criterion` |
| `claims.material` is true, none of the above | 50 | `material` |
| `claims.material` is false | 15 | `not_material` |

### 3.2 Staleness (0–100)

How out of date the best evidence is for what the claim asserts. Two kinds of claim:

- **Event claims** state something that happened once (a round closed, a company was incorporated, a person held a past role). Dated evidence of an event does not age: staleness 0. With no dated evidence: 100.
- **State claims** describe now or a named period (headcount, current role, revenue, debt outstanding, open litigation, customers). Staleness rises with the age of the newest matching evidence, measured from `as_of` to today:

```
age ≤ W/2          → 0
W/2 < age < 2W     → 100 × (age − W/2) / (1.5 × W)
age ≥ 2W           → 100
no as_of at all    → 100
```

For a claim about a **named past period** ("FY25 revenue"), age is measured only until evidence for that exact period exists; once it does, staleness is 0. For "latest" or an unlabelled period, the window applies and the claim's own record date is compared with the newest period available publicly.

Windows `W`, in `policy.STALENESS_WINDOW_DAYS`:

| Claim type | Kind | W (days) |
| --- | --- | --- |
| Team size / headcount | state | 180 |
| Leadership, current role | state | 365 |
| Leadership, past role | event | — |
| Funding round | event | — |
| Total funding to date | state | 365 |
| Revenue or other financials, quarterly | state | 135 (a quarter plus filing lag) |
| Revenue or other financials, annual | state | 550 |
| Debt and security | state | 180 |
| Litigation | state | 90 |
| Customer or partnership | state | 365 |
| Location, facilities | state | 365 |
| Identity, incorporation | event | — |
| Dated event | event | — |

Existing `FIELD_STALE_AFTER_DAYS = 730` for criteria fields is untouched.

**Effect on the verdict (policy change, version bump):** for a state component, a matching fact older than `2W` no longer settles it. The component becomes `unsettled` with the caveat "Evidence is as of {date}", so the claim reads Partially corroborated rather than Supported. This is a rule, not a score: it is implemented in `decide_claim_status` behind the new policy version and covered by the freshness test. See [open decision 1](#15-open-decisions).

---

## 4. Verification Priority and triggers

### 4.1 The formula

Exactly as given by the product owner:

```
Verification Priority = 0.45 × materiality
                      + 0.30 × (100 − evidence assurance)
                      + 0.15 × DecisionFlip sensitivity
                      + 0.10 × staleness
```

All four terms are 0–100, so the result is 0–100. The comparison uses the unrounded value; one decimal is stored and shown. Weights are `policy.PRIORITY_WEIGHTS = (0.45, 0.30, 0.15, 0.10)` and the threshold is `policy.PRIORITY_THRESHOLD = 65`.

`rules/proofgate.py: priority(materiality, assurance, sensitivity, staleness) -> float`. Pure.

Worked example, the Mahindra case before any lookup: materiality 100 (revenue is a must-have), assurance 0 (no fact), sensitivity 85, staleness 100 → `45 + 30 + 12.75 + 10 = 97.75`. Validate.

A supported, registry-backed incorporation date on a non-blocking claim: materiality 100, assurance 90, sensitivity 0, staleness 0 → `45 + 3 + 0 + 0 = 48`. Below threshold, and identity is confirmed, so no lookup.

### 4.2 Triggers

A component is validated when **priority ≥ 65**, or **always** when any forced trigger holds, whatever the score:

| Forced trigger | Id | Holds when |
| --- | --- | --- |
| Uncertain identity | `uncertain_identity` | `case.identity_status` is not `confirmed`; or the only matching facts are bound by name alone; or two candidate entities share the name. The validation targets the identity component first. Dependent claims stay `not_checked: identity_unresolved` until it settles, as today |
| Conflicting sources | `conflicting_sources` | Any component state is `conflicting`, the claim status is `conflicting_evidence`, or two origin clusters give values outside tolerance |
| Mandatory criteria | `mandatory_criterion` | The component maps to a must-have criterion |
| Harmful allegations | `harmful_allegation` | Category `litigation`, or `debt_security` asserting default or insolvency, or the claim or any attached fact matches `policy.HARM_TERMS` (fraud, default, insolvency, regulatory action, raid, arrest, misconduct, sanction, blacklisting) about the company or a named person. Such a statement is never shown as Supported from `news` alone; it needs a court, regulator or registry record, or stays Partially corroborated with the source named |
| Consequential actions | `consequential_action` | The claim id appears in the reasons of a Deprioritise decision, in `next_best_action.item_ids`, or in a request item with priority `blocker` awaiting approval |

"Always" means always *planned and attempted first*. If the budget is gone the row is `skipped: budget_exhausted` and the claim says so; a forced trigger does not overspend.

### 4.3 Order of work

Within a run, validations are sorted by `(forced desc, priority desc, claim_id)` and worked in that order until the claim cap or the run budget ends. So decision-critical claims are checked first and the ones that miss out are the least important. Everything skipped is recorded with its score, so the UI can say "Not validated: priority 41, below 65".

---

## 5. Source playbooks

`pipelines/verify/proofgate/playbooks.py`. A playbook maps `(claim type, component, listing status)` to **at most two** `LookupSpec`s, run in parallel. No third lookup, no fallback chain: if both return nothing the claim is Cannot verify, with both sources listed as read.

### 5.1 The public-search-first rule

Standing owner rule, implemented here:

1. For **every** claim category, including the five that go to `gather_nothing` today, at least one public lookup is planned before a claim may be reported as `cannot_verify` or `not_checked: no_source_in_scope`. `gather_nothing` stays only for `other` claims with no extractable component.
2. Uploads do not suppress the search. A seller document that already states the figure is one more fact, of class `seller_document`.
3. Seller documents are requested only for what public sources cannot show. `what_would_settle` names a seller document only after the public lookup ran and came back empty.
4. A test fails if any category's playbook list is empty for a listed company.

### 5.2 Listed-company detection

`proofgate/listing.py: listing_status(case) -> listed | unlisted | unknown`, cached on the case entity JSON with its basis. Free signals first, in order:

1. CIN first letter: `L` listed, `U` unlisted (Indian companies).
2. A ticker, ISIN or exchange on the Crustdata company record.
3. Company type "Public Company" on the record plus an exchange name.
4. Otherwise `unknown`: treated as unlisted, and slot 1 of a financials lookup is spent on a search that would find an exchange filing if one exists.

A listed parent with an unlisted subsidiary: the claim's entity decides, not the group. A subsidiary's revenue is not the parent's (§6.1).

### 5.3 Playbooks

Slot 1 is the primary source for that claim type; slot 2 is the best independent second origin. Query strings are built with the existing `checks/query.py` so only public terms leave the system.

| Claim type | Slot 1 | Slot 2 | Class of a hit | Best verdict from these alone |
| --- | --- | --- | --- | --- |
| **Revenue, profit, other financials — listed** | Exchange filing: results, annual report or investor presentation on `bseindia.com`, `nseindia.com` or the company's investor-relations pages, for the claimed period | Company press release for the same results | `exchange_filing`; `company_announcement` | Supported (filing is adequate) |
| **Financials — unlisted** | Registry financial filing (MCA AOC-4 or equivalent) through the allowed registry hosts in `verify/registry.py` | News reporting the filed figures (Entrackr, Inc42 and similar report from filings) | `registry` / `registry_mirror`; `news` | Supported from the filing; Partially corroborated from news |
| **Funding round** | The original announcement: company newsroom or the lead investor's post | Entrackr or Inc42 (`site:entrackr.com OR site:inc42.com`), which often report from regulatory filings | `company_announcement`; `news` | Partially corroborated, with `ANNOUNCEMENT_CAVEAT`. Supported still needs the allotment filing or closing statement, as policy says now |
| **Total funding, investors** | Crustdata funding milestones (existing `gather_funding`) | Entrackr / Inc42 | `data_provider`; `news` | Partially corroborated |
| **People: role, tenure, history** | Crustdata person profile (existing `gather_leadership`) | The relevant professional record: MCA director record (DIN) for directors, the professional body's register where the claim names a qualification, or the employer's leadership page | `professional_profile_signal`; `registry` or `company_announcement` | Supported for directorships from the registry; otherwise Partially corroborated |
| **Headcount** | Crustdata headcount (LinkedIn-derived), stored as "LinkedIn member count, as of {date}" | Listed: annual report employee count. Unlisted: none, slot left empty | `professional_profile_signal`; `exchange_filing` | Partially corroborated with `HEADCOUNT_SIGNAL_CAVEAT`. Never Supported from LinkedIn alone; payroll or annual report settles it |
| **Legal identity, incorporation** | Authorised registry (existing `verify.registry`) | Exchange listing page if listed | `registry`; `exchange_filing` | Supported |
| **Customer or partnership** | The counterparty's own announcement or page naming the company | The company's press release, or an exchange disclosure if listed | `counterparty_confirmation`; `company_announcement` | Supported from the counterparty; a one-sided company statement is Partially corroborated |
| **Debt and security** | Registry charge records | Listed: annual report borrowings note. Rating agency rationale where one exists | `registry`; `exchange_filing` | Partially corroborated (`CHARGE_CAVEAT`: a charge shows security, not a balance) |
| **Litigation** | Court or tribunal record search (NCLT, eCourts) by legal name | Listed: exchange disclosure of material litigation; otherwise news | `registry`; `exchange_filing` / `news` | A found case is evidence it exists. "No litigation" is never Supported from an empty search: Cannot verify, naming what was searched |
| **Compliance, facilities, dated events** | Regulator or exchange disclosure; for facilities the existing `gather_identity_location` | News (`gather_dated_event`) | as above | per existing rules |

New enum value `SourceReliability.EXCHANGE_FILING`, added to `_FINANCIAL_SOURCES`, with caveat text for quarterly results: "Limited-review quarterly results, not audited". If PG-B wants zero enum change for the first cut, map exchange filings to `registry` in `_CLASS_ALIASES` and keep the caveat; see [open decision 2](#15-open-decisions).

### 5.4 Qualified LinkedIn data

Headcount from LinkedIn is stored and shown qualified, never bare: the number, "LinkedIn member count", the as-of date, and the fact that it counts profiles, not payroll. It can contradict a claim only outside a wide band (`policy.HEADCOUNT_SIGNAL_BAND = 0.30` relative), because contractors, non-members and stale profiles move it. Inside the band it is a signal that agrees, not a match.

---

## 6. Verifying entity, value, unit, period and semantics

`pipelines/verify/proofgate/dimensions.py` produces a `DimensionCheck` per fact; `rules/proofgate.py: admit(fact, check)` decides what the rules may do with it. Each dimension is `match`, `mismatch` or `unknown`.

### 6.1 Entity

- `match`: the source carries a corroborating identifier for the confirmed entity (existing `entity_binding_corroborated`), extended with ticker and ISIN.
- `mismatch`: an identifier for a different entity, or the text names a parent, subsidiary, group or namesake. "Mahindra Group", "Mahindra & Mahindra Ltd" and "Tech Mahindra" are three entities. Consolidated versus standalone is handled in semantics, not here.
- `unknown`: name only.

Mismatch or unknown: the record is stored unattached (`attached: false`, as today) and produces no fact.

### 6.2 Value

Compared on `value_base` with the existing tolerances (`COUNT_TOLERANCE`, `MONEY_TOLERANCE`, `PERCENT_TOLERANCE_POINTS`). Rounded claims are honoured: "over ₹1,000 crore" is a lower bound; "about" widens to the rounding implied by the claim's own precision, not beyond.

### 6.3 Unit

Currency and scale are parsed from the span, not assumed: crore, lakh, million, billion, thousand, "mn", "bn", "cr". The unit must be stated in the span or the table header the span came from.

- Same currency: normalise scale, compare.
- Different currency: `unknown`. **No conversion with a looked-up or assumed rate.** If the source itself states both, the stated figure is used.
- Unit missing: `unknown`.

### 6.4 Period

Normalised to `Period`. Indian fiscal years end 31 March by default (`fiscal_year_end_month = 3`), overridden when the source states otherwise. "Q2 FY27" is 1 July–30 September 2026; "FY27" is 1 April 2026–31 March 2027; "CY26" is the calendar year.

- `match`: same type and same end date.
- `mismatch`: a different period (Q2 against H1, FY26 against FY27, quarter against trailing twelve months).
- `unknown`: no period in the span.

A different period never contradicts. It is stored as related evidence with the note "Reports {label}, the claim is about {label}".

### 6.5 Semantics

Whether the source measures the thing the claim asserts. A closed vocabulary per claim type, in `policy.SEMANTICS`:

- Financials: `revenue_from_operations`, `total_income`, `gmv`, `arr`, `bookings`, `ebitda`, `pat`; each with `consolidated | standalone`.
- Funding: `round_amount`, `total_raised`, `valuation`, `committed_not_closed`, `debt_round`.
- Headcount: `employees`, `team_including_contractors`, `linkedin_members`.
- Customers: `signed_customer`, `pilot`, `partner`, `logo_only`.
- People: `current_role`, `past_role`, `advisor`, `board`.

The extractor proposes a label from the list; a deterministic cue check on the span confirms it (the same style as `validation.stage_stated`). No cue found → `unknown`. GMV offered for a revenue claim, valuation for an amount raised, a pilot for a customer, standalone for consolidated: `mismatch`.

### 6.6 What the rules do with it

| Entity | Value | Unit | Period | Semantics | Fact reaches `decide_claim_status` as |
| --- | --- | --- | --- | --- | --- |
| match | match | match | match | match | a matching fact |
| match | mismatch | match | match | match | a contradicting fact |
| match | any | any | **mismatch** | any | related only: neither supports nor contradicts |
| match | any | any | any | **mismatch** | related only, with the semantics note |
| match | any | **unknown** or mismatch | any | any | related only: "unit not stated" |
| match | any | match | **unknown** | match | related only for state claims; admitted for event claims that carry `as_of` |
| mismatch / unknown | — | — | — | — | not a fact; source kept unattached |

So a contradiction requires all of entity, unit, period and semantics to match. That is deliberately harder to reach than "the numbers differ".

---

## 7. Origin de-duplication

Syndicated copies are one origin. Extends `checks/sources.py: syndication_origin` and the `origin_key` already kept on `sources.request`.

A fact's **origin cluster key** is the first of these that applies:

1. **Cited origin.** The text attributes the figure ("according to a company statement", "regulatory filings show", "as per the exchange filing", "PTI", "ANI", "Reuters", "IANS", "Press release"). The cluster is that origin: `announcement:{entity}:{date}`, `filing:{entity}:{period}`, `wire:{agency}:{date}`.
2. **Same text.** `span_key` equal, or the normalised headline equal after stripping the publisher suffix (existing).
3. **Canonical URL.** `rel=canonical` or the URL without tracking parameters.
4. **Publisher group.** Two hosts owned by one publisher are one origin (`policy.PUBLISHER_GROUPS`).
5. Otherwise the host.

Rules:

- Independent-origin counts in assurance and in `_origin_adequacy` use clusters, never URLs.
- A data-provider funding record that lists a news URL as its source joins that article's cluster.
- An article that reports a filing joins the filing's cluster and keeps class `news`; it does not become a filing.
- A press release and an article quoting it are one origin of class `company_announcement`.
- When clusters disagree, both values are stored and shown with their origins. Status is `conflicting_evidence`. **No averaging, no majority, no "latest wins".** The existing precedence (an adequate-class fact outranks a non-adequate one) is the only tie-break, and it is a policy rule, not arithmetic.
- The detail view lists collapsed copies under their origin ("3 outlets carried this announcement").

---

## 8. Budgets and timeouts

Config in `app/settings.py`, defaults in `policy.PROOFGATE_LIMITS`, the effective values copied into each validation row's `scores.limits`.

| Setting | Default | Meaning |
| --- | --- | --- |
| `PG_MAX_PARALLEL_LOOKUPS` | 2 | Lookups per claim component per round. Hard-capped at 2 in code; a higher setting is rejected at start-up |
| `PG_LOOKUP_TIMEOUT_S` | 20 | Per lookup, search plus fetch plus extraction |
| `PG_CLAIM_TIMEOUT_S` | 45 | Per validation, both lookups and the dimension checks |
| `PG_CLAIM_CREDITS` | 4.0 | Per validation. A lookup is one search (1.0) plus at most one page fetch (1.0) |
| `PG_RUN_CREDITS` | 24.0 | All validations in one run, and never more than the case budget has left |
| `PG_MAX_CLAIMS_PER_RUN` | 12 | Validations per run |
| `PG_MAX_ROUNDS` | 2 | Round 1 inside the check, round 2 after DecisionFlip. No third |

Behaviour:

- Credits are reserved before dispatch through the existing recorder and `CreditBudget`. A refused reservation marks the lookup `budget` and the validation `skipped: budget_exhausted`; the claim reads Not checked (`budget_exhausted`), which already offers an analyst retry (`ANALYST_RETRY_REASONS`).
- One lookup refused and one allowed: the allowed one runs. Partial evidence is kept.
- A timeout cancels the task, records `timeout` with the elapsed time, and counts as `source_error`. The other lookup's facts are kept. Charges already incurred are recorded.
- A cache hit (`api_cache`) costs nothing and is recorded as `cached: true`, with the original retrieval time shown.
- The baseline gatherers are unchanged and are not counted in the two-lookup cap; they are the existing check. ProofGate's lookups are the two targeted ones on top.
- LLM extraction on a fetched page goes through the existing `llm_factory` and cost context, inside the lookup timeout.

---

## 9. DecisionFlip linkage

DecisionFlip is not modified. ProofGate reads its stored analysis and feeds the real pipeline, exactly as F §4 requires ("new evidence is only ever processed by the real pipeline").

### 9.1 Sensitivity in

`rules/proofgate.py: sensitivity(claim_id, component, analysis) -> (score, basis)`, read from the latest `DecisionFlipAnalysis` item `claim:<id>`, or the `criterion:<id>` item the component maps to. Maximum of the rows that apply:

| Item fact | Score | Basis id |
| --- | --- | --- |
| `flips_alone` or `required_in_every_path` | 100 | `flips_alone` / `every_path` |
| In `minimum_evidence.item_ids` | 85 | `in_minimum_evidence` |
| `disqualifier_risk` | 80 | `disqualifier_risk` |
| `decision_blocker` in another minimal set | 70 | `blocker_alt` |
| `locks_target` | 60 | `locks_target` |
| Listed, `non_blocking` | 20 | `non_blocking` |
| Not an item (already supported) | 0 | `settled` |
| No analysis for this case yet | 50 | `default` |

Verify runs before evaluate, so the first run has no analysis. Hence two rounds:

- **Round 1**, inside each claim check: sensitivity comes from the previous assessment version's analysis if the case has one (`previous_version`), else the neutral 50 (`default`). Forced triggers and high-materiality claims already clear the gate without it.
- **Round 2**, a new step `verify.proofgate.followup` after `evaluate.decision_flip`: priorities are recomputed with the real analysis. Components now at ≥ 65 or newly forced, and not yet validated under the same evidence, are validated in priority order with whatever budget round 1 left. Blockers therefore go first.

`sensitivity_source` is stored and shown, so a 50 is never mistaken for a computed value.

### 9.2 Affected-outcome recalculation out

When a validation changes a claim's status, only what depends on that claim is recomputed, and no other claim is re-gathered or re-validated.

`rules/proofgate.py: affected(changed_claim_ids, base) -> Affected` returns the dependency closure, from data the rules already hold:

```
changed claim
  → its CheckOutcome
  → the CheckSufficiency of its category
  → criteria whose dimension the changed components map to (COMPONENT_CRITERION_DIMENSIONS)
  → fit and evidence sufficiency, if any of those moved
  → disposition (rules.redecide)
  → DecisionFlip analysis (a new inputs_hash gives a new analysis_key; nothing to invalidate)
  → request items linked to those claims (request_item_claims)
```

Mechanics:

- The follow-up step ends by enqueueing the existing tail (`ensure_assessment_tail`: `evaluate.assess` → `evaluate.decision_flip` → `act.request_list`) **only if** at least one status changed. `evaluate.assess` is pure and keyed by `inputs_hash`, so unchanged inputs write no new version.
- No I/O is repeated: the saving is in lookups and model calls, which are the cost. The pure rules pass is milliseconds.
- `Affected` is stored on the validation row and returned by the API, so the UI can say "Recalculated: Revenue criterion, Financials check, disposition. Unchanged: 11 other claims."
- A test asserts that every outcome outside `Affected` is byte-identical before and after.
- **Loop guard.** The tail that follows round 2 does not start round 3. `PG_MAX_ROUNDS` is enforced by counting `round` values for the run. A later seller upload starts a new run and so a new round 1, as today's recheck does.

Step order in a verify run:

```
claims.extract → checks.claim × N (baseline gather → score → gate → ≤2 lookups → decide)
              → evaluate.assess → evaluate.decision_flip → verify.proofgate.followup
              → [only if a status changed] evaluate.assess → evaluate.decision_flip
              → act.request_list
```

`verify.proofgate.followup`: `depends_on=("decision_flip",)`, `uses_budget=True`, `tolerate_failed_deps=True` (no analysis → it validates nothing new and passes). `act.request_list` gains it as a tolerated dependency so a failed follow-up never blocks Act.

---

## 10. Restart safety

The existing step leasing already makes `checks.claim:` steps re-claimable. ProofGate adds idempotent rows so a re-claimed step neither repeats a paid call nor writes a second verdict.

- **`plan_key`** = `sha256(claim_id, component, round, policy_version, proofgate_version, evidence_fingerprint, flip_analysis_key)`, where `evidence_fingerprint` is the sorted list of `(source_id, origin_key)` attached at planning time. Same inputs, same key, same row (`ON CONFLICT DO NOTHING`, then load).
- **State machine** on the validation: `planned → running → decided`, or `→ skipped`, or `→ failed`. Lookups: `planned → running → ok | empty | error | timeout | budget`.
- **Every transition commits with its evidence.** A lookup's source row, evidence rows and state change to `ok` are one transaction. Evidence upserts on `(source_id, origin_key)` as today.

Crash points and what the retry does:

| Killed | On retry |
| --- | --- |
| Before the plan row | Recomputes scores (pure) and inserts |
| After `planned`, before any dispatch | Loads the row, dispatches |
| A lookup `running`, call in flight | The row is `running` with `started_at` older than the lease: re-dispatch with the same `request_key`. The recorder's `call_attempts` and `api_cache` return the stored response if the call completed, so no second charge |
| One lookup `ok`, the other not started | Skips the finished one, runs the other |
| Both lookups terminal, before the decision | Re-reads stored evidence, runs dimensions and `decide_claim_status` (pure), writes the `claim_checks` row |
| After `claim_checks` insert, before `decided` | The validation has no `claim_check_id`; the retry finds the check written by this `step_id` and links it. No second check row |
| After `decided` | Returns the stored output, `created: false` |

- **Policy versions.** `policy.POLICY_VERSION` is bumped (weights, threshold, windows, semantics lists, staleness rule). `PROOFGATE_VERSION = "proofgate-1"` covers the algorithm. Both are stored on every validation. A new version gives a new `plan_key`, so old rows stay as the record of what was decided under the old policy, and readers take the newest.
- **Decisions** are the validation row itself: scores with their inputs, triggers, skip reason, limits in force, lookups made, dimension results, status before and after.
- **Usage** is on the lookup rows and, as now, in `cost_entries` by `step_id`.

---

## 11. UI

Lives on the existing Claims tab (`apps/web/app/(app)/app/cases/[id]/claims/page.tsx`) and its showcase twin. No new page. Existing `StatusMark` and tokens from `docs/design/tokens.css`; no new colour is needed, since assurance and priority are numbers with a quiet bar, not statuses.

Principles for the builder:

- **The verdict leads.** `StatusMark` stays the strongest element in the row. Assurance and priority sit after it, smaller, so nobody reads "assurance 82" as "true".
- **Say what the number is.** Assurance always carries the words "heuristic" on first appearance in the detail and a tooltip in the row: "How well the evidence stands up. Not a probability that the claim is true."
- **Conflicts show both values**, each with its origin. Never a single blended figure.
- **Skipped is a state.** "Not validated · priority 41, below 65" and "Not checked · budget reached" are written out, not hidden.
- Sorting defaults to the existing order; a "Priority" sort is added. Filter chips: Validated, Skipped, Forced.

### 11.1 Claim row (desktop)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ CLAIM                         CLAIMED          EVIDENCE            VERDICT          ASSURANCE  PRIORITY  COST · TIME │
├──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Q2 FY27 revenue of ₹X cr      ₹X cr            ₹X cr               ● Supported      82 High    97.8      3.0 cr · 6.2s│
│ Financials · Deck p.4         Q2 FY27 · consol Exchange filing     ━━━━━━━━░░       ▲ must-have          2 lookups   │
│                                                · 5 Nov 2026                                                         │
├──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ Raised $20M Series B          $20M             $20M · $18M         ◐ Conflicting    30 Low     88.0      4.0 cr · 11s │
│ Funding · Deck p.2            Series B · 2025  2 origins disagree  ━━━░░░░░░░       ▲ conflict           2 lookups   │
├──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ 450 employees                 450              412 LinkedIn        ◔ Partially      41 Moderate 58.3     — · —       │
│ Team size · typed             now              members · Oct 2026  ━━━━░░░░░░                            Not validated│
├──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ No pending litigation         none             —                   ○ Not checked    0  Low     91.5      0 cr · —    │
│ Litigation · Deck p.9                          Budget reached      ░░░░░░░░░░       ▲ allegation         Retry       │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Row anatomy, left to right:

1. **Claim**: text (two lines, truncated), then category and where it was stated.
2. **Claimed**: value with unit on line one; period and semantics on line two.
3. **Evidence**: the best fact's value with unit; source class and record date beneath. A conflict shows both values. Nothing found shows "—" and the reason.
4. **Verdict**: `StatusMark`, existing vocabulary only.
5. **Assurance**: number, band word, a thin ten-segment bar.
6. **Priority**: number to one decimal; a forced-trigger tag (`▲ must-have`, `▲ conflict`, `▲ identity`, `▲ allegation`, `▲ action`) when one applies.
7. **Cost · time**: credits and wall-clock latency of the validation; lookup count beneath. "Not validated" or an action ("Retry") when it did not run.

Mobile: the row becomes a card. Line 1 claim; line 2 verdict mark plus claimed → evidence; line 3 a single meta line "Assurance 82 · Priority 97.8 · 3.0 cr · 6.2s".

### 11.2 Claim detail (drawer or expanded row)

```
┌─ Q2 FY27 revenue of ₹X crore ─────────────────────────────────────────── ● Supported ─┐
│ Financials · stated in Pitch deck, p.4 · entity Mahindra & Mahindra Ltd (L…)          │
│                                                                                        │
│ CLAIMED                              │ BEST EVIDENCE                                   │
│ ₹X crore                             │ ₹X crore                                        │
│ Q2 FY27 (1 Jul–30 Sep 2026)          │ Q2 FY27 (quarter ended 30 Sep 2026)             │
│ Revenue from operations, consolidated│ Revenue from operations, consolidated           │
│ Record date 12 Nov 2026              │ Exchange filing · record date 5 Nov 2026        │
│                                      │ Retrieved 22 Nov 2026, 14:02 · field "Revenue   │
│                                      │ from operations", p.2                           │
│                                                                                        │
│ CHECKS ON THIS EVIDENCE    Entity ✓   Value ✓   Unit ✓   Period ✓   Meaning ✓          │
│                                                                                        │
│ EVIDENCE (2 origins, 4 sources)                                                        │
│ 1  Exchange filing · bseindia.com · 5 Nov 2026            ₹X cr       matches          │
│    "Revenue from operations … " ▸                                                      │
│ 2  Company announcement · 5 Nov 2026                      ₹X cr       matches          │
│    + 3 outlets carried this announcement ▸                (counted once)               │
│ –  Annual report FY26                                     ₹Y cr       different period │
│                                                                                        │
│ EVIDENCE ASSURANCE   82 · High      heuristic, not a probability the claim is true     │
│ Source class 35/35 · Independent origins 20/20 · Entity 15/15 · Agreement 15/15        │
│ Freshness 10/10 · Extraction 5/5 · cap: none … shown as  before 0 → after 82           │
│                                                                                        │
│ VERIFICATION PRIORITY   97.8   (validate at 65 or above)                               │
│ 0.45 × materiality 100 + 0.30 × (100 − assurance 0) + 0.15 × sensitivity 85            │
│ + 0.10 × staleness 100                                                                 │
│ Always validated because: must-have criterion "Revenue ≥ …"                            │
│ Sensitivity from DecisionFlip: in the minimum set of checks ▸                          │
│                                                                                        │
│ VALIDATION RUN   round 1 · 2 lookups · 3.0 credits · 6.2 s · policy 2026-11-22.4       │
│ 1  Exchange filing search      ok      2.0 cr   4.1 s                                  │
│ 2  Company press release       ok      1.0 cr   6.2 s   (cached page)                  │
│                                                                                        │
│ WHAT THIS CHANGED   Cannot verify → Supported                                          │
│ Recalculated: Revenue criterion, Financials check, disposition. 11 other claims        │
│ unchanged.                                                                             │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

Detail states to design:

- **Conflicting**: the two-column header becomes "Claimed" against a stacked list of each origin's value. The line under it reads "Sources disagree. Values are shown as reported and are not averaged."
- **Dimension failure**: the failing chip is spelled out ("Period ✕ reports FY26, the claim is about Q2 FY27") and the fact is listed under "Related, does not settle the claim".
- **Wrong entity**: under "Not attached to this company", with the reason, as the Sources tab does now.
- **Cannot verify after lookups**: "Searched: exchange filings, company press releases. Neither states Q2 FY27 revenue." then what would settle it.
- **Not checked**: the reason (budget reached, timed out after 20 s, source error) and a Retry button for analyst-retry reasons. Retry calls `POST …/validate`.
- **Not validated (below threshold)**: the priority breakdown and a "Validate anyway" button, budget permitting.
- **Running**: lookup rows appear as they start, using the existing run-activity stream (`checks/activity.py`), with new keys `status.proofgate_planning`, `status.proofgate_lookup`.
- **Sensitivity default**: "Sensitivity 50 · not yet computed for this case" in muted text.

### 11.3 Run summary strip

Above the table, one line: "ProofGate validated 7 of 19 claims · 18.0 of 24.0 credits · 3 skipped for budget · 9 below threshold". It links to the existing cost panel, which gains a "Validation" line.

### 11.4 API for the UI

- `ClaimOut` gains `proofgate: {assurance, assurance_band, priority, triggers, forced, state, skip_reason, credits, latency_ms, lookups, claimed: {value, unit, period, semantics}, best_evidence: {...}} | null`, built in `claims/ledger.py`. Null for cases never run under ProofGate, and the UI then renders today's row unchanged.
- `GET /cases/{id}/claims/{claim_id}/validation` → the full detail: scores with inputs, lookups, dimension results per fact, origin clusters, `affected`.
- `POST /cases/{id}/claims/{claim_id}/validate` → a budgeted single-claim run (analyst retry or "Validate anyway"). 409 when the budget is spent.
- `GET /policy` gains the ProofGate weights, threshold, windows and limits, so the Settings page can show them read-only.
- Fixtures mode returns canned rows for the four states in §11.1 so PG-UI can start before PG-A lands.

---

## 12. Test list

The eight the brief names, each with what it must show, then the rest.

| # | Test | Setup | Must hold |
| --- | --- | --- | --- |
| 1 | **Mismatch** | Claim ₹500 cr; an adequate source says ₹420 cr; same entity, unit, period, semantics | Contradicted; both values stored; no averaged figure anywhere in the output |
| 2 | **Freshness** | Headcount claim; the only matching fact is 400 days old (W = 180) | Staleness 100; component unsettled, claim Partially corroborated with "as of" caveat; priority crosses 65 and a lookup is planned |
| 3 | **Wrong entity** | Search returns a namesake or the parent group's figures | Record stored unattached, no fact, assurance unchanged, verdict not Supported |
| 4 | **Different periods** | Claim Q2 FY27; source gives FY26 and H1 FY27 | Both stored as related; neither supports nor contradicts; Cannot verify with a period note |
| 5 | **Duplicate-source origin** | Five articles reprinting one press release, plus the release | One origin cluster; origins input 10, not 20; not "independently corroborated" |
| 6 | **Source failure** | Slot 1 raises, slot 2 returns | Slot 2's facts kept; lookup 1 `error`; if both fail, Not checked `source_error` with retry offered; step does not fail |
| 7 | **Budget exhaustion** | Run budget covers two of four triggered claims | The two highest-priority run; the others `skipped: budget_exhausted`, Not checked with reason; no overspend; forced triggers still ordered first |
| 8 | **Restart** | Kill the worker at each crash point in §10 | One validation row, one `claim_checks` row, no second charge, identical final output |

Further:

- **Formula**: table-driven check of the priority arithmetic, including the two worked examples in §4.1 and the boundary (64.99 no, 65.00 yes).
- **Forced triggers**: each of the five validates at a priority below 65.
- **Score never verifies**: assurance 100 with a non-adequate class does not produce Supported.
- **Assurance caps**: each cap in §2.2.
- **Unit**: crore against million normalised; INR against USD gives `unknown`, no conversion.
- **Semantics**: GMV for revenue, valuation for amount raised, pilot for customer, standalone for consolidated: all related-only.
- **Listed detection**: CIN `L…` listed, `U…` unlisted, ticker present, none → unknown.
- **Public-search-first**: a listed-company revenue claim with no upload plans an exchange-filing lookup (the Mahindra regression). Every category has a non-empty playbook.
- **Headcount qualification**: LinkedIn count inside the band never gives Supported and never Contradicted.
- **Harmful allegation**: a news-only allegation is never Supported; an empty litigation search never supports "no litigation".
- **Two-lookup cap**: no playbook yields three; a setting of 3 is rejected.
- **Timeout**: a lookup sleeping past the limit is cancelled and recorded.
- **Sensitivity mapping**: each row of §9.1 from a fixture analysis; no analysis gives 50 with source `default`.
- **Round 2 ordering**: blockers validated before non-blocking items.
- **Affected only**: after one claim changes, outcomes outside `affected()` are byte-identical; no new version when nothing changed.
- **Loop guard**: no round 3.
- **Purity and determinism**: `rules/proofgate.py` imports no I/O; same inputs, same scores.
- **Confidentiality**: `scores` JSON contains no claim text (marker-string test, as F does).
- **Regression**: the existing rules and verify suites pass unchanged except where the staleness rule is deliberately versioned; a case with no ProofGate rows renders as today.
- **Web**: row and detail render each state in §11 from fixtures; a null `proofgate` renders the old row.

---

## 13. Implementation chunks

Three builders in parallel. PG-A pushes its interface first so the other two can code against it.

### PG-A. Core (Opus, backend)

Files: `app/rules/proofgate.py`, `app/rules/policy.py`, `app/domain/types.py`, `app/domain/enums.py`, `alembic/versions/0010_proofgate.py`, `app/db/models.py`, `app/pipelines/verify/proofgate/{plan,persist,followup}.py`, `app/pipelines/verify/checks/run.py`, `app/pipelines/verify/tail.py`.

1. **A1, interface first (push within the first 30 minutes).** Domain types (§1.4); `rules/proofgate.py` signatures with real `priority()` and stubbed others; the `LookupSpec` / `LookupResult` protocol PG-B implements; the `ClaimOut.proofgate` schema plus fixtures for PG-UI.
2. **A2, scoring.** `assurance`, `materiality`, `staleness`, `sensitivity`, `triggers`, `plan_order`. Policy constants and version bump. Tests: formula, caps, triggers, sensitivity mapping.
3. **A3, persistence.** Migration, models, `plan_key`, state machine, idempotent writes. Restart tests.
4. **A4, wiring.** In `check_claim`: baseline gather → score → gate → call PG-B → admit facts → `decide_all` → persist. Budget reservation and skip reasons.
5. **A5, DecisionFlip linkage.** `verify.proofgate.followup` step, round 2, `affected()`, conditional tail, loop guard.
6. **A6, API.** Ledger fields, detail endpoint, validate endpoint, policy endpoint.

### PG-B. Sources (Opus, backend)

Files: `app/pipelines/verify/proofgate/{playbooks,lookup,listing,dimensions,origins,periods,units}.py`, `app/pipelines/verify/checks/{gather,sources}.py`.

1. **B1, listing and the financials playbook.** `listing_status`; exchange-filing and press-release lookups for listed companies; this alone fixes the Mahindra failure.
2. **B2, lookup runner.** Two tasks under `asyncio.wait` with per-lookup and per-claim timeouts, budget reservation, `LookupResult` per slot, never raising.
3. **B3, dimensions.** Units and scales, fiscal periods, semantics vocabulary with cue checks, entity extension (ticker, ISIN). Returns `DimensionCheck` per fact.
4. **B4, origins.** Cluster key, cited-origin detection, publisher groups.
5. **B5, remaining playbooks.** Funding (announcement plus Entrackr/Inc42), people records, headcount qualification, customers, debt, litigation.
6. Tests 1, 3, 4, 5, 6 and the unit, semantics, listing and public-search-first tests.

### PG-UI (Fable, web)

Files: `apps/web/app/(app)/app/cases/[id]/claims/page.tsx`, the showcase claims page, `components/case-b/*` claim components, `cost-panel.tsx`.

1. **U1.** Row columns (§11.1) against fixtures, with the null fallback.
2. **U2.** Detail (§11.2): claimed against evidence, dimension chips, origin-grouped evidence, the assurance and priority breakdowns, the validation run table.
3. **U3.** States: conflicting, skipped, not checked with retry, running, default sensitivity. Summary strip and cost-panel line.
4. **U4.** Mobile card, priority sort, filter chips. Then switch from fixtures to the live endpoints.

Dependencies: PG-B needs A1. PG-UI needs A1's schema and fixtures. A4 needs B2. Nothing else blocks.

---

## 14. If there are only two hours

Ranked. Stop wherever time runs out; each line leaves the product working.

1. **Public search for listed-company financials** (B1, cut down): `listing_status` from the CIN letter and ticker; replace `gather_nothing` for `financials` with one exchange-filing search and one press-release search. Fixes the failure the owner named. Largest visible gain for the least code.
2. **The priority formula and triggers as a pure function** (A2, cut down): `priority()`, `materiality()`, the five forced triggers, with assurance from source class, origin count and entity binding only. Computed and stored on the check step's output metadata, no new table yet.
3. **The gate with a two-lookup cap and budget skip** (B2 plus A4): run lookups only for claims at ≥ 65 or forced, in priority order, with timeouts; refusals become Not checked `budget_exhausted`.
4. **Period and unit checks** (B3, cut down): fiscal quarter and year normalisation, crore/lakh/million/billion; a different period or unknown unit is related-only. Prevents the worst false Supported and false Contradicted.
5. **Row columns in the UI** (U1): claimed, evidence, verdict, assurance, priority, cost, latency, read from the step metadata.
6. **Origin clustering on cited origin and same text** (B4, cut down). The existing `syndication_origin` already covers the headline case.
7. **`proofgate_validations` table and restart-safe state** (A3). Until then the existing step idempotency and `api_cache` give "no double charge" but not a full audit row.
8. **DecisionFlip sensitivity and round 2** (A5). Until then sensitivity is the neutral 50, labelled as default.
9. **Detail view, remaining playbooks, semantics vocabulary** (U2, B5, the rest of B3).

Cut entirely under this budget: the staleness verdict rule (keep staleness as a priority input only), the validate-anyway endpoint, mobile polish.

---

## 15. Open decisions

1. **Staleness changing the verdict.** §3.2 proposes that evidence older than `2W` cannot settle a state claim. It is honest, and it will move some existing Supported claims to Partially corroborated. Recommended: yes, under the new policy version. Alternative: staleness affects priority only.
2. **`exchange_filing` as a new source class**, or aliased to `registry`. Recommended: new class, because quarterly results are unaudited and deserve their own caveat.
3. **Round 2 budget.** Recommended: whatever round 1 left of `PG_RUN_CREDITS`. Alternative: hold back a third of the run budget for round 2 so blockers found late are never starved.
4. **Headcount band** of 30% for LinkedIn counts. A guess; tune against real cases.
5. **Harm terms list.** A lexicon is blunt. It errs toward validating more, which is the safe direction, but the list needs an owner's read.
