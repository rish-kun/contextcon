# F. DecisionFlip

Design iteration · 2026-11-22 · docs only, nothing here is built yet

DealProof already says "Investigate further" and lists every open question. DecisionFlip answers the next question: **which of those open questions actually stand between this company and the next disposition, and what is the least evidence that would settle them?** It does this by re-running the rules with one item at a time forced to a hypothetical state, never by asking a model.

Contents: [1 Concept](#1-concept-and-naming) · [2 Algorithm](#2-the-deterministic-algorithm) · [3 Request prioritisation](#3-evidence-request-prioritisation) · [4 The loop](#4-the-loop) · [5 Optional LLM](#5-optional-llm) · [6 UI](#6-ui-panel-design) · [7 API and data](#7-api-and-data) · [8 Tests](#8-test-plan) · [9 Chunks](#9-implementation-chunks) · [10 Open decisions](#10-open-decisions)

Three things in the current policy shape this design and differ from the pitch screenshot. They are stated up front so nobody builds the screenshot literally:

1. **A contradicted claim never leads to Deprioritise.** `POLICY.md` §5: "claim statuses do not feed the Deprioritise rules". A contradicted material claim *locks the case at Investigate further*. Only a must-have criterion that verifiably fails (`requirement_failed`), or poor fit on verified evidence, gives Deprioritise. So the "if contradicted" card usually reads "Stays Investigate further, and Prioritise is out of reach while this stands", and reads "Deprioritise" only for criteria.
2. **Financials and customer checks do not block Prioritise** (not in `V1_COVERED_CHECKS`). They will come out `non_blocking`. The evaluator computes this; it is not hard-coded.
3. **Some cases are not evidence-limited.** If fit is below 70 with every criterion known, no document moves the disposition. The panel must say so instead of inventing blockers.

## Amendments (2026-11-22, reviewer feedback, built in B1)

These supersede the text below where they differ. Policy `2026-11-22.3`.

**A. Policy-driven disqualification.** `policy.DISPOSITION_TABLE` (POLICY.md §5) is now the source of truth, and the rules read it:

| Situation | Leads to |
| --- | --- |
| Unverified optional claim | Investigate further, if material |
| Unverified mandatory criterion | Decision blocker (blocks Prioritise, never Deprioritise) |
| Contradicted non-mandatory claim | Investigate further, materiality assessed |
| Verified failure of a mandatory criterion | Deprioritise |
| Poor thesis fit despite sufficient evidence | Deprioritise |
| Unresolved identity | Cannot assess |

Two real-rule changes follow: an unknown must-have and an unverified material claim outside the v1-covered required checks now block Prioritise (so the PRD fixture has three blockers, not one). A claim component maps to a criterion dimension (`policy.COMPONENT_CRITERION_DIMENSIONS`, plus a new `ownership` component). A Contradicted claim on that component is a verified failure of a must-have of that dimension when the claimed value is exactly what the criterion requires (equality, one allowed value, or "is true"); a contradicted number never fails a threshold. So "privately held" contradicted by a registry fails a "privately held" must-have, and an unresolved claim like that is a `disqualifier_risk`. A disqualifier risk is any item whose contradicted branch gives Deprioritise under `requirement_failed`. Note 1 above now reads: a contradicted claim leads to Deprioritise only through this mapping.

**B. Label honestly.** The chosen set is the fewest checks, not the cheapest: `selection_basis: "fewest_checks"`, `selection_label: "Minimum set of checks required to change the screening outcome"`. Each item has `est_effort` (`low | medium | high`, from `policy.DOCUMENT_EFFORT`). Sets are ordered by (number of checks, summed effort, documents, analyst-only items, ids), so effort only breaks ties. `decision_flip.SELECTION_KEYS` is the extension point for a later minimum-total-cost basis. This replaces the documents-first ordering in §2.5.

**C. Evidence availability ≠ favourable evidence.** Criteria and financial items carry `conditional_action`, which always states both branches ("Obtain a sourced record for Headcount. If the verified figure is at least 100, Headcount passes; otherwise it fails. Hypothetically, a pass gives Prioritise and a fail gives Deprioritise."). The chosen set's conditions are appended to `next_best_action.text` and listed in `next_best_action.conditions`. No template words an action as if obtaining a document makes the company qualify.

Built names (B1): `analyse()` returns `DecisionFlipAnalysis` (§7.1's `DecisionFlip`), with `UnresolvedItem`, `ItemOutcome`, `MinimalSet`, `SettleDocument`, `NextBestAction`, and state `has_blockers` for §7.1's `blockers`.

---

## 1. Concept and naming

| Thing | Name in the UI | Notes |
| --- | --- | --- |
| The feature | **DecisionFlip** | Panel title. Lead line: "Which open items would change the screening disposition." |
| Dispositions | Prioritise · Investigate further · Deprioritise · Cannot assess | PRD names, via the existing `DispositionStamp` for the *real* one only |
| An item that must be settled to advance | **Decision blocker** | |
| An item whose failure would lead to Deprioritise | **Disqualifier risk** | Only criteria can be this under policy 5 |
| An item that changes nothing | **Non-blocking** | Shown collapsed, with a count |
| A simulated result | **Hypothetical** | Always this word. Never "would be verified", never "predicted", never a percentage |
| The smallest set of evidence that advances the case | **Minimum evidence to advance** | Counted in documents, not claims |
| The one thing to do next | **Next best action** | |

Where it lives:

- **Case Overview tab:** a compact panel between `ProfilePanels` and the memo. Current disposition, blocker count, minimum evidence, next best action. Links to the full panel.
- **Case Assessment tab:** the full panel under the judgment panel and above the version diff: every item, both outcome cards, the request link.
- **Pipeline board / cases table card:** one line under the disposition, "1 blocker to Prioritise" (or "2 blockers to Investigate further", "Not evidence-limited", nothing at all for Prioritise).
- **Request tab:** requested documents grouped "Settles a decision blocker" / "Other open questions" ([§3](#3-evidence-request-prioritisation)).
- **Live run view:** one extra step and one extra line ([§6.6](#66-live-run-view)).
- **Home page:** one showcase block with illustrative data ([§6.7](#67-home-page-showcase)).

---

## 2. The deterministic algorithm

A new pure module `apps/api/app/rules/decision_flip.py`. No I/O, no LLM, no clock, same contract as the rest of `app.rules`.

### 2.1 Input and the one code path

```python
def decision_flip(assessment: AssessmentVersion, claims: dict[str, Claim]) -> DecisionFlip
```

It takes the **stored assessment version** (outcomes, criterion evaluations, identity, financial assessment, company type) plus the claims (for `material` and `document_for`). It does not reload case records. That makes the analysis reproducible from the version alone, including for old versions and after retention has scrubbed the text (the skeleton keeps every status and id).

To guarantee the simulation uses the real rules, split the tail of `rules.assess` into one function that both callers use:

```python
# rules/evaluate.py
def redecide(
    *, identity_status, company_type, outcomes, evaluations, criteria_meta,
    financial, claims,
) -> tuple[OpportunityFit, EvidenceSufficiency, DispositionDecision]:
    fit         = fit_from_evaluations(...)          # exists in rules/fit.py
    must_fail   = [e.reason for e in must_have_failures(evaluations)]
    sufficiency = evidence_sufficiency(company_type, outcomes, claims)
    decision    = decide_disposition(identity_status, fit, sufficiency, must_fail,
                                     outcomes=outcomes, claims=claims)
```

`assess` calls `redecide` with the real values; `decision_flip` calls it with one or more values overridden. `decide_disposition`, `evidence_sufficiency` and `fit_from_evaluations` are **not** modified. A regression test asserts `redecide(real values).disposition == assessment.disposition` for every fixture, so a hypothetical and a real result can never come from different logic.

"Everything else the same" is literal: forcing a claim does not re-evaluate criteria (a criterion made unknown by disputed evidence stays its own item). This is a stated limit, shown in the panel footer.

### 2.2 Unresolved items

Stable ids, so versions can be compared.

| Kind | Id | Enumerated when | Force **supported** | Force **contradicted** |
| --- | --- | --- | --- | --- |
| `claim` | `claim:<claim_id>` | outcome status is not `supported` | status `supported`, every component `matched`, `not_checked_reason` cleared | status `contradicted`, every non-matched component `contradicted` |
| `check_gap` | `check:<category>` | a required check has no claim at all (`CheckSufficiency.result is None`) | add a synthetic outcome `hyp:<category>` with one `matched` component of that check | same, `contradicted` |
| `criterion` | `criterion:<criterion_id>` | evaluation result is `unknown` (must-have **and** preference; preferences move fit across 70) | result `pass`, `verified=True` | result `fail`, `verified=True` |
| `identity` | `identity` | `identity_status` is not `confirmed` | `confirmed` | not simulated (an unresolved identity is already Cannot assess) |
| `financial_inputs` | `financial_inputs` | financials required for the company type and `financial.assessed` is false | `assessed=True` | not simulated |

Each item also records `current_state` (e.g. `cannot_verify`, `contradicted`, `unknown`, `absent`), `seller_resolvable`, and `settle_with` (documents, from `document_for` / `policy.CATEGORY_DOCUMENTS` / `DOC_IDENTITY` / `DOC_FINANCIAL_INPUTS`, the same mapping `build_request_list` uses). The state an item already holds is not simulated again (a contradicted claim gets only the "if supported" run).

Claims that are `not_checked` because identity is unresolved stay `not_checked` when only `identity` is forced. That is honest: confirming identity lets the checks run; it does not pass them. They are marked `depends_on: ["identity"]`.

Items are sorted by `(kind order, id)` everywhere. No dict or set iteration order reaches the output.

### 2.3 Ladder and target

Rank: `cannot_assess` 0 < `investigate_further` 1 < `prioritise` 2. `deprioritise` is off the ladder.

```
current  = redecide(real)                       # must equal assessment.disposition
ceiling  = redecide(all items forced supported)
target   = the lowest rung above current that is reachable, i.e.
           investigate_further if current is cannot_assess and ceiling >= investigate_further
           prioritise          if current is investigate_further and ceiling == prioritise
           none                otherwise
```

Outcomes when `target` is none:

- `current == prioritise` → `state: "no_blockers"`.
- `current == deprioritise` → `state: "disqualified"`, with the firing rule and reasons copied from the real decision. Nothing is simulated to "undo" a verified failure.
- otherwise → `state: "not_evidence_limited"` (e.g. fit below 70 with all criteria known). `ceiling` and its reasons are shown.

`ceiling` is always reported, so a Cannot assess case can say "the identity document moves this to Investigate further; Prioritise would also need 3 more items".

### 2.4 Single-item runs

For every item `i`, with all other items left as they really are:

- `if_supported[i]  = redecide(real + i supported)`
- `if_contradicted[i] = redecide(real + i contradicted)` (where simulated)

and with all *other* items forced supported:

- `needed[i]   = redecide(all supported except i).rank < target.rank`  → the item is necessary
- `locks[i]    = redecide(all others supported, i contradicted).rank < target.rank` → its contradiction rules the target out even if everything else comes good

That is at most `3n + 2` rule evaluations.

### 2.5 Minimal sets (multi-blocker combinations)

With two blockers neither flips the disposition alone, so single-item runs are not enough.

- Candidates `C` = items where forcing supported is defined. `n = len(C)`.
- **n ≤ 6:** enumerate all subsets in order of size (at most 64 evaluations). A subset *reaches* if `redecide(real + subset supported).rank >= target.rank`. Keep every reaching subset that has no reaching proper subset: the **minimal sets**.
- **n > 6:** deletion greedy. Start from `C` (reaches, by definition of `target`). Walk items in reverse priority order (non-seller-resolvable first, then most documents, then id); drop an item if the set still reaches without it. The result is irreducible (no item can be removed), though not guaranteed to be the smallest. Flag `search: "greedy"` so the UI can say "a sufficient set" instead of "the minimum". Blocker membership in this mode is `needed[i] or i in chosen set`.
- **Choosing one set as "minimum evidence to advance":** sort minimal sets by `(number of distinct documents, number of analyst-only items, number of items, sorted ids)` and take the first. Measured in documents because one document (a share allotment) can settle several items.

### 2.6 Classification

Each item gets flags, then one primary class for display.

| Flag | Definition |
| --- | --- |
| `decision_blocker` | `target` exists and the item is in at least one minimal set |
| `required_in_every_path` | `needed[i]` (in every minimal set) |
| `flips_alone` | `if_supported[i].rank >= target.rank` |
| `disqualifier_risk` | `if_contradicted[i].disposition == deprioritise` |
| `locks_target` | `locks[i]` |

Primary `classification`: `decision_blocker` if that flag is set, else `disqualifier_risk` if set, else `non_blocking`. An item can carry both flags (an unknown must-have criterion on a case whose fit depends on it); the UI shows both chips.

### 2.7 Minimum evidence and next best action

`minimum_evidence`: the chosen set's items, and its documents deduplicated in request order, each with the item ids it settles and `seller_resolvable`.

`next_best_action` is picked by fixed rule, not written by a model:

| Condition (first match) | `action` | Template |
| --- | --- | --- |
| `state == no_blockers` | `none` | "No open item stands in the way of Prioritise." |
| `state == disqualified` | `review_disqualifier` | "Deprioritise rests on verified evidence: {rule}. No evidence request changes it." |
| `state == not_evidence_limited` | `none` | "More evidence will not change the disposition: {reason}." |
| chosen set contains `identity` | `resolve_identity` | "Confirm the legal entity first; {k} checks cannot run until then." |
| chosen set has items with `analyst_retry` | `rerun_checks` | "Re-run {k} checks that did not run. No seller document is needed for them." |
| chosen set has only analyst-resolvable items | `analyst_follow_up` | "Follow up {k} items the seller cannot resolve: {documents}." |
| otherwise | `request_documents` | "Request {d} documents that settle the {k} decision blockers, rather than everything open." |

### 2.8 Reproducibility

Every analysis carries:

```
hypothetical: true            (Literal[True] on the root and on every simulated outcome)
policy_version                from the assessment
inputs_hash                   the assessment's inputs hash
flip_version                  "decision-flip-1", bumped when this module's logic changes
analysis_key                  sha256(canonical JSON of {inputs_hash, policy_version, flip_version,
                                                         materiality: {claim_id: bool}})
search                        "exhaustive" | "greedy"
evaluations                   number of rule runs
```

Same assessment version and same claims' materiality give byte-identical output. No timestamps inside the hashed document.

---

## 3. Evidence request prioritisation

Nothing about *what* is requested changes: `rules.build_request_list` stays the single source of open questions and document mapping. DecisionFlip only adds an order and a label.

- `build_request_list_for_case` loads the analysis for the same assessment version (if present) and sets, per requested document, `priority`: `blocker` (settles an item in the chosen minimal set) → `blocker_alt` (settles a blocker in another minimal set) → `risk` (settles a disqualifier risk) → `other`. Items are stored and returned in that order; within a class, existing order is kept.
- New nullable column `request_items.priority` (migration 0006). Missing analysis → all `other`, behaviour as today.
- The drafted email lists blocker documents first under one plain sentence ("These settle the open points that decide the next step"). `fallback_email` gets the same ordering so the template path matches.
- Analyst-only items (`seller_resolvable=False`, e.g. a registry charge record) and re-runs never go into the seller email, as today. If they are decision blockers they appear in the DecisionFlip panel as "For you, not the seller".
- **Approval is unchanged.** The list is still a draft with no recipient; a person types the recipient, a manager approves, send happens once, and `email_send_enabled` still gates it. DecisionFlip never creates an approval and never sends. The panel's link reads "Evidence request prepared for approval" and goes to the Request tab; it is shown only when a request list exists for this version and has at least one `blocker` item. If the list is already approved or sent, the link text follows that state ("Evidence request sent 21 Nov").
- Optional, behind a decision ([§10](#10-open-decisions)): a "Request only the blockers" toggle on the Request tab that drafts the email from `blocker` items alone.

---

## 4. The loop

```
seller document or typed answers uploaded        POST /cases/{id}/documents   (existing)
        │  kind = seller_response  → recheck run (existing, budgeted, persisted)
        ▼
verify the affected claims  →  evaluate.assess  →  evaluate.decision_flip  →  act.request_list
                               new version N+1      analysis for N+1          re-prioritised draft
                               + diff from N        + resolution vs N
```

- New evidence is only ever processed by the **real** pipeline. DecisionFlip never writes a claim status, an evidence row or an assessment. The hypothetical for version N is not consulted when version N+1 is assessed.
- If the inputs did not change, `evaluate.assess` writes no new version and `evaluate.decision_flip` finds the existing analysis by `analysis_key` and writes nothing.
- The previous version and its analysis are kept. Both are immutable rows.
- **Resolution** is derived on read by comparing the analysis of N with the real assessment of N+1, by item id:

| In N | In N+1 | Shown as |
| --- | --- | --- |
| blocker `claim:c3` | claim supported (no longer an item) | "Resolved: supported by Seller document · payroll summary" |
| blocker `claim:c3` | still an item, `current_state: contradicted` | "Settled against the claim: contradicted" |
| blocker `claim:c3` | still an item, same state | "Still open" |
| any item | new id not in N | "New open item" |

  The evidence named comes from the existing `AssessmentDiff.claim_changes[].evidence_added`.

- The headline sentence is assembled from the diff, not generated: "This evidence resolved 1 decision blocker (team size). Disposition moved Investigate further → Prioritise." or "…resolved 1 of 2 decision blockers. Disposition is still Investigate further; 1 blocker left." When the real result differs from the hypothetical (say the claim came back contradicted) it says so: "The payroll summary contradicts the team size claim. Prioritise is out of reach while this stands."
- A hypothetical is never restyled as verified. When a blocker resolves, the hypothetical card is removed and the real `DispositionStamp` and `StatusMark` take its place.

---

## 5. Optional LLM

Off by default behind `DECISION_FLIP_NOTES` (settings), Haiku (`claude-haiku-5-5`), through the existing `llm_factory` so the call lands in the cost ledger under the run and step.

It may write exactly two things:

1. `how_to_obtain`: one or two sentences per requested document on how such a document is usually obtained ("Ask the company secretary for the PAS-3 allotment filing for the round").
2. `explanation`: one sentence per decision blocker restating the rule that makes it a blocker.

Rules:

- **Input** is the structured analysis only: item kind, check category, component names, current state, document type names, the firing rule id and the hypothetical dispositions. **No claim text and no evidence values** are sent, so nothing seller-confidential leaves and nothing needs retention handling.
- **Output** is a JSON object keyed by item id / document name. Each note must list `cites: [item ids]`; a note citing an id not in the analysis is dropped. Notes containing a digit followed by `%`, or the words "likely", "probably", "chance", "odds", "confidence", are dropped and replaced by the template.
- The model never receives a field it could alter: classification, dispositions, sets and next best action are computed before the call and are not read back from it.
- Failure, timeout, budget reached or flag off → template sentences from [§2.7](#27-minimum-evidence-and-next-best-action) and a fixed per-document line ("Settled by: {document}"). `notes_source: "template" | "model"` is stored and the UI shows "Drafted by a model" in muted text next to model-written notes.
- Notes are stored beside the analysis, not inside the hashed document, so the analysis hash does not depend on a model.

The pipeline is complete without this. Build it last.

---

## 6. UI panel design

### 6.1 The rule that matters: hypothetical is never mistaken for verified

| | Verified (existing) | Hypothetical (new) |
| --- | --- | --- |
| Container | solid 1px border, surface fill | **dashed** 1px border in `ink-muted`, diagonal hatch fill at ~6% ink |
| Label | none needed | the word **Hypothetical** in the card's top-left, always, in text (not only a pattern) |
| Disposition | `DispositionStamp` with its colour | plain text in body ink, prefixed "would be": "would be Prioritise". **No stamp, no status colour, no green/red** |
| Glyph | `StatusMark` | none. A neutral `→` only |
| Wording | "Supported", "Contradicted" | "If supported", "If contradicted" |
| Print / memo | printed | printed with the hatch replaced by a dashed box and the word "Hypothetical" kept |

The classification chips (Decision blocker, Disqualifier risk, Non-blocking) describe the item's role, not a verification result, so they use neutral outline chips: ink outline for blocker, ink outline with a small `!` for disqualifier risk, muted for non-blocking. They do not borrow the claim-status palette. Screen readers get "Hypothetical outcome" as the card's accessible name.

### 6.2 Assessment tab, desktop

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ DecisionFlip                                              Version 2 · policy 5 · a41c…9e  ⓘ  │
│ Which open items would change the screening disposition.                                     │
│                                                                                              │
│ Now   [ Investigate further ]          2 blockers to Prioritise · 7 open items               │
│ ──────────────────────────────────────────────────────────────────────────────────────────── │
│ Decision blockers                                                                            │
│  Team size · "120 employees"            Cannot verify      ▢ Decision blocker        ⌄       │
│     settled by  Dated payroll summary                                                        │
│  Funding · "Raised $8M Series A"        Partially corrob.  ▢ Decision blocker        ⌄       │
│     settled by  Share allotment filing, closing statement or bank receipt                    │
│ Disqualifier risks                                                                           │
│  Must-have · HQ in India                Unknown            ▢! Disqualifier risk      ⌄       │
│     settled by  Certificate of incorporation                                                 │
│ Non-blocking · 4                                                             Show  ⌄         │
│ ──────────────────────────────────────────────────────────────────────────────────────────── │
│ ┌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ┐   ┌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ┐     │
│ ╎ Hypothetical ░░░░░░░░░░░░░░░░░░░░░░░░ ╎   ╎ Hypothetical ░░░░░░░░░░░░░░░░░░░░░░░░░░ ╎     │
│ ╎ If both blockers are supported        ╎   ╎ If a blocker is contradicted            ╎     │
│ ╎ → would be Prioritise                 ╎   ╎ → stays Investigate further             ╎     │
│ ╎ Rule: strong fit, checks satisfied    ╎   ╎ Prioritise is out of reach while it     ╎     │
│ ╎ Not verified. Real evidence is        ╎   ╎ stands. If "HQ in India" fails          ╎     │
│ ╎ re-assessed under the same policy.    ╎   ╎ → would be Deprioritise                 ╎     │
│ └ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ┘   └ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ┘     │
│ ──────────────────────────────────────────────────────────────────────────────────────────── │
│ Minimum evidence to advance                    2 documents settle both blockers              │
│  1  Dated payroll summary                      settles Team size                             │
│  2  Share allotment filing                     settles Funding                               │
│                                                                                              │
│ Next best action                                                                             │
│  Request the 2 documents that settle the decision blockers, rather than everything open.     │
│  ▣ Evidence request prepared for approval  →                                                 │
│                                                                                              │
│ Simulated by re-running policy 5 with one item changed at a time. Nothing here is evidence.  │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Expanding a row (`⌄`) shows that item's own two hypothetical cards ("If supported: alone, stays Investigate further; with Funding, would be Prioritise" / "If contradicted: …"), its components and states, and "Open claim →".
- The two summary cards are the chosen minimal set (left) and the worst contradiction outcome across blockers and risks (right). When more than one minimal set exists, a line under the left card: "Another way: 1 other set of 3 documents. Show".
- `ⓘ` opens the method: the item kinds, the ladder, the number of rule runs, exhaustive or greedy, the policy and inputs hash.
- Reading an old version (the existing `ReadingOldVersionBanner`) shows that version's analysis, read-only.

States of the whole panel:

| State | Body |
| --- | --- |
| `no_blockers` (Prioritise) | One line: "Nothing open stands in the way. {n} non-blocking items remain." No hypothetical cards |
| `disqualified` | "Deprioritise rests on verified evidence: {reason}. No evidence request changes it." Reason links to the criterion |
| `not_evidence_limited` | "More evidence will not change this. Fit is 58; Prioritise needs 70 and every criterion is already known." |
| Cannot assess | Target is Investigate further; a second muted line gives the ceiling: "After that, 3 more items to Prioritise" |
| No analysis yet (old version, or step still queued) | Skeleton rows, then "Work out blockers" button (calls the POST) |
| Greedy search | "A sufficient set" replaces "Minimum evidence"; ⓘ explains |

### 6.3 Overview tab (compact), desktop

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ DecisionFlip      [ Investigate further ]   2 blockers to Prioritise                         │
│ Team size · Funding          settled by 2 documents                                          │
│ ╎ Hypothetical ░  if both are supported → would be Prioritise ╎                              │
│ Next: request the 2 documents.   ▣ Evidence request prepared for approval →    See analysis →│
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

It is excluded from the printed memo unless the memo's "include open items" option is on; when printed it keeps the Hypothetical label.

### 6.4 Mobile (Assessment tab)

```
┌──────────────────────────────────┐
│ DecisionFlip              v2  ⓘ  │
│ [ Investigate further ]          │
│ 2 blockers to Prioritise         │
│ ──────────────────────────────── │
│ Team size                      ⌄ │
│ Cannot verify                    │
│ ▢ Decision blocker               │
│ Dated payroll summary            │
│ ──────────────────────────────── │
│ Funding                        ⌄ │
│ Partially corroborated           │
│ ▢ Decision blocker               │
│ Share allotment filing           │
│ ──────────────────────────────── │
│ HQ in India · must-have        ⌄ │
│ Unknown   ▢! Disqualifier risk   │
│ ──────────────────────────────── │
│ Non-blocking · 4          Show ⌄ │
│ ┌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ┐  │
│ ╎ Hypothetical ░░░░░░░░░░░░░░ ╎  │
│ ╎ If both are supported       ╎  │
│ ╎ → would be Prioritise       ╎  │
│ └ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ┘  │
│ ┌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ┐  │
│ ╎ Hypothetical ░░░░░░░░░░░░░░ ╎  │
│ ╎ If a blocker is contradicted╎  │
│ ╎ → stays Investigate further ╎  │
│ └ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ╌ ┘  │
│ Minimum evidence · 2 documents   │
│ 1 Dated payroll summary          │
│ 2 Share allotment filing         │
│ Next: request these 2 documents. │
│ [ Evidence request for approval ]│
└──────────────────────────────────┘
```

Cards stack; the claim text is cut to one line and the full text is in the expanded row. The request link becomes a full-width button (44px tap target). No horizontal scroll.

### 6.5 Pipeline board card

```
┌───────────────────────────────┐      ┌───────────────────────────────┐
│ Meridian Warehousing          │      │ Northfield Robotics           │
│ [ Investigate further ]       │      │ [ Cannot assess ]             │
│ 1 blocker to Prioritise       │      │ Identity first · 3 after      │
│ Fit 82 · 70% assessable       │      │ Fit —                         │
└───────────────────────────────┘      └───────────────────────────────┘
```

One line in body ink, no chip, no colour. "Not evidence-limited" in muted ink. Sortable: fewest blockers first is the useful order for a manager ("which cases are one document away").

### 6.6 Live run view

Extends iteration D §1.9; uses real step keys.

- Step checklist gains one entry after "Update the assessment": **"Work out what would change the decision"** (key `decision_flip`), then "Draft the document request" (`request_list`). It runs for well under a second, so it shows as queued → done without a spinner dwell.
- NOW line while it runs: "Re-running the policy with one item changed at a time · 14 runs".
- In the recheck panel, one line under the "Assessment v2" row:

```
│  Assessment v2    Investigate further  →  Investigate further                                │
│  Decision blockers to Prioritise   2  →  1         resolved: Team size                       │
```

- One `finding` event from the step (`subject: "decision_flip"`, fields: `target`, `blockers_before`, `blockers_after`, `resolved_item_ids`, `state`). Ids and counts only, no claim text, consistent with D §2.10.
- When the run settles, this line becomes the headline sentence of [§4](#4-the-loop) in the version diff.

### 6.7 Motion when a blocker resolves

Follows iteration C's language (short, once, state-driven; nothing loops).

1. The resolved row's chip "Decision blocker" cross-fades to the real `StatusMark` (Supported) (160ms). The row then moves to a "Resolved in version 3" group at the bottom with a layout animation (240ms) and settles in muted ink.
2. The blocker count uses `NumberTween` 2 → 1.
3. If blockers remain: the left hypothetical card's title re-renders ("If the remaining blocker is supported"); its dashed border does **not** change. Nothing about a hypothetical ever animates towards a verified look.
4. If none remain and the real disposition moved: the hypothetical cards fade out (120ms) and the real `DispositionStamp` plays its existing stamp-in (C §1.5) with the headline sentence beside it. The hypothetical is removed, the verified result arrives; they are never the same element, so no morph between them.
5. If the evidence contradicted the claim: the row keeps its place, the chip becomes the real Contradicted mark, and the right card's sentence is replaced by the real statement. No shake, no red flash.
6. Reduced motion: steps 1 to 5 are instant state changes; the "Resolved" group still appears. Sound: the existing `success` cue once when the disposition advances, nothing for a partial resolution.

### 6.8 Home page showcase

One block in `components/marketing/sections.tsx`, after the evidence-trail explainer. Static sample data, labelled "Illustrative" in the corner (the existing convention for marketing samples), using the same component as the app at reduced width.

- Headline: "Not more information. The information the decision turns on."
- The panel shows a sample company at Investigate further with two blockers and one non-blocking item. On scroll into view, once: the two blocker rows appear, the hypothetical card draws its dashed outline, then the minimum-evidence line "2 documents" tweens in. No auto-playing resolution; a "See it resolve" button plays the §6.7 sequence against sample data on demand.
- The hypothetical card keeps its label and hatch on the marketing page too. The showcase must not show a green "Ready for meeting" badge like the pitch screenshot: that is exactly the verified-looking hypothetical this design forbids.

---

## 7. API and data

### 7.1 Schemas

Domain types in `app/domain/types.py` (rules output), mirrored by `…Out` models in `app/api/schemas`.

```python
class FlipOutcome(Model):
    hypothetical: Literal[True] = True
    disposition: Disposition
    rule: str                      # decide_disposition's rule id
    reasons: list[str]             # rule reasons; claim ids only, no claim text
    changes_disposition: bool

class FlipItem(Model):
    id: str                        # "claim:<id>" | "check:<category>" | "criterion:<id>" | "identity" | "financial_inputs"
    kind: Literal["claim", "check_gap", "criterion", "identity", "financial_inputs"]
    claim_id: str | None = None
    criterion_id: str | None = None
    check: ClaimCategory | None = None
    current_state: str
    classification: Literal["decision_blocker", "disqualifier_risk", "non_blocking"]
    decision_blocker: bool
    disqualifier_risk: bool
    required_in_every_path: bool
    flips_alone: bool
    locks_target: bool
    seller_resolvable: bool
    analyst_retry: bool
    depends_on: list[str] = []
    settle_with: list[str]         # document type names from policy
    if_supported: FlipOutcome | None
    if_contradicted: FlipOutcome | None

class FlipDocument(Model):
    document: str
    item_ids: list[str]
    seller_resolvable: bool

class FlipSet(Model):
    hypothetical: Literal[True] = True
    item_ids: list[str]
    documents: list[FlipDocument]
    outcome: FlipOutcome

class NextBestAction(Model):
    action: Literal["request_documents", "resolve_identity", "rerun_checks",
                    "analyst_follow_up", "review_disqualifier", "none"]
    text: str                      # from the fixed templates
    item_ids: list[str]
    documents: list[str]

class DecisionFlip(Model):
    hypothetical: Literal[True] = True
    case_id: str
    assessment_version: int
    policy_version: str
    inputs_hash: str
    flip_version: str
    analysis_key: str
    state: Literal["blockers", "no_blockers", "disqualified", "not_evidence_limited"]
    current: Disposition
    current_rule: str
    target: Disposition | None
    ceiling: Disposition
    items: list[FlipItem]
    minimal_sets: list[FlipSet]            # exhaustive: all; greedy: the one found
    minimum_evidence: FlipSet | None
    worst_if_contradicted: FlipOutcome | None
    next_best_action: NextBestAction
    search: Literal["exhaustive", "greedy"]
    evaluations: int
```

API additions on read (not in the hashed document): item `label` and `claim_text` rendered from the `claims` / criteria rows at read time (so retention scrubbing shows through, as the request list does), `notes` and `notes_source` ([§5](#5-optional-llm)), `request: {request_list_id, status, blocker_items} | null`, and `resolution` versus the previous version ([§4](#4-the-loop)).

### 7.2 Persistence

`assessment_versions` rows are immutable (an UPDATE is rejected by trigger), so the analysis goes **beside** them. Migration `0006_decision_flip.py`:

```
decision_flip_analyses
  id                     uuid pk
  workspace_id           fk workspaces
  case_id                fk cases, indexed
  assessment_version_id  fk assessment_versions (RESTRICT)
  analysis_key           varchar(128)
  policy_version         varchar(64)
  flip_version           varchar(32)
  state                  varchar(32)
  target                 varchar(32) null
  blocker_count          int            -- for the board, no JSON read needed
  analysis               jsonb          -- the DecisionFlip document
  notes                  jsonb null     -- §5, written at most once
  notes_source           varchar(16) null
  run_id                 fk runs null
  created_at
  unique (assessment_version_id, analysis_key)

request_items.priority   varchar(16) null
```

The `analysis` document holds ids, enums, policy document-type names and rule reasons that reference claim ids. It holds no claim text and no evidence values, so it needs no confidential payload and nothing for the purge job to scrub. A test asserts this by serialising an analysis for a fixture whose claim text contains a marker string.

A new `flip_version` or a claim's `material` flag changing gives a new `analysis_key` and a new row for the same assessment version; readers take the newest. Old rows stay.

### 7.3 Endpoints

| Route | Behaviour |
| --- | --- |
| `GET /cases/{id}` | New `decision_flip` section via `@section("decision_flip")`: the analysis for the latest assessment version, or `null` (no assessment yet, or not computed). Never computes on read |
| `GET /cases` | Summary field `decision_flip: {state, target, blocker_count} | null` via `@summary_field`, read from the columns, for the board card |
| `GET /cases/{id}/decision-flip?version=N` | The analysis for a version (default latest), with labels, notes, request link and resolution. 404 if the case has no assessment; `null` body state `not_computed` if the version has no analysis |
| `POST /cases/{id}/decision-flip` | Recompute for the latest version (body `{version?: int}`). Pure and millisecond-scale, so it runs in the request: no run, no credits, no LLM. Idempotent: returns the existing row (200) when the `analysis_key` matches, else inserts (201). 409 with a clear message if there is no assessment |

Fixtures mode (`fixtures_enabled()`) returns a canned analysis so the web app can be built before the backend lands.

### 7.4 The step, job persistence and restart recovery

```python
# app/pipelines/evaluate/flip_step.py
HANDLER = "evaluate.decision_flip";  STEP_KEY = "decision_flip"

StepSpec(key=STEP_KEY, handler=HANDLER,
         label="Work out what would change the decision",
         depends_on=("evaluate",), uses_budget=False, tolerate_failed_deps=False)
```

- Order: `evaluate.assess` → `evaluate.decision_flip` → `act.request_list`. `request_list_step` gains `depends_on=("evaluate", "decision_flip")` and `tolerate_failed_deps=True`, so a failed analysis degrades to an unprioritised request list instead of blocking Act.
- Added wherever `evaluate_step` is appended today (verify, recheck and the manual evaluate run in `pipelines/evaluate/cases.py`). Builder to confirm each plan site; `request_list_step` is defined but I did not find it in a run plan, so wiring it is part of this work.
- `uses_budget=False`: it spends no credits and runs after the budget is spent, like `evaluate.assess`. The optional notes call is the only cost; it goes through `llm_factory` with the step's `CostContext`, is skipped when the budget is reached, and never fails the step.
- **Idempotent by key.** The handler reads the latest assessment version, computes the analysis, and `INSERT … ON CONFLICT (assessment_version_id, analysis_key) DO NOTHING`, then returns `{analysis_id, analysis_key, state, target, blocker_count, created}`.
- **Restart recovery.** A worker killed before the insert: the step is re-claimed and recomputes the identical document. Killed after the insert but before the step is marked done: the retry hits the conflict, loads the existing row, and returns the same output with `created: false`. Killed between the insert and the notes write: the retry sees `notes is null` and writes them once (`UPDATE … WHERE notes IS NULL`). No path produces two rows or two charges for one version.
- A run that produced no new assessment version (`created: false` from evaluate) still runs the step; it finds the existing analysis and reports "No change".
- Approvals are untouched: the step creates no approval, message or send.

---

## 8. Test plan

Rules tests are pure (`tests/rules/test_decision_flip.py`), built from `AssessmentInputs` fixtures → `assess` → `decision_flip`.

| # | Case (user's six first) | Setup | Asserts |
| --- | --- | --- | --- |
| 1 | **No blockers** | Startup, fit ≥ 70, all required checks supported, one non-material claim cannot verify | `state == "no_blockers"`, `target is None`, no `decision_blocker`, `minimum_evidence is None`, action `none`; the open claim is `non_blocking` |
| 2 | **Multiple blockers** | Two required checks unsettled (team size cannot verify, funding partially corroborated) | neither `flips_alone`; both `required_in_every_path`; exactly one minimal set of both; `minimum_evidence.documents` has 2 deduplicated documents; outcome `prioritise` with `hypothetical is True` |
| 2b | Two claims, one document | Two funding claims settled by the same allotment | minimal set has 2 items, 1 document |
| 2c | Alternative paths | Fit 66, two unknown preference criteria, either lifts fit to ≥ 70 | two minimal sets of size 1; neither `required_in_every_path`; both `decision_blocker`; chosen set is deterministic |
| 3 | **Unsupported claims** | A material claim `contradicted`, and one `conflicting_evidence`, outside the required checks | each is an item with `if_contradicted is None` for the contradicted one; `if_supported` reaches target only with both; contradicted one is **not** `disqualifier_risk` (policy: claims never deprioritise); `locks_target` true for the conflicting one |
| 4 | **Missing evidence** | A required check never claimed (`check:<category>`), a claim `not_checked` (`source_unavailable`), one with `analyst_retry` | `check_gap` item present and a blocker; its `settle_with` is `policy.CATEGORY_DOCUMENTS[check]`; analyst-retry item gives action `rerun_checks`; established company missing financials yields `financial_inputs` item classified `non_blocking` |
| 5 | **Disqualifying criteria** | (a) unknown must-have criterion; (b) a must-have already failed on verified evidence | (a) `disqualifier_risk`, `if_contradicted.disposition == deprioritise`, rule `requirement_failed`; (b) `state == "disqualified"`, no simulation attempts to reverse it, action `review_disqualifier` |
| 6 | **Restart recovery** | Integration, see below | one row, identical output, no second cost row |
| 7 | Identity unresolved | `identity_status` ambiguous, claims `not_checked` identity_unresolved | current `cannot_assess`, target `investigate_further`, chosen set `["identity"]`, dependent claims carry `depends_on`, `ceiling` reported, action `resolve_identity` |
| 8 | Not evidence-limited | Fit 55, all criteria known, checks open | `state == "not_evidence_limited"`, no blockers |
| 9 | Greedy path | 8 open blocker candidates | `search == "greedy"`, set is irreducible (dropping any member no longer reaches), output identical across two runs and across shuffled input order |
| 10 | Determinism | Any fixture | `decision_flip(a, c) == decision_flip(a, c)`; byte-identical JSON; `analysis_key` stable; changes when `material` flips |
| 11 | One code path | Every fixture | `redecide(real)` equals the assessment's stored disposition, rule and reasons |
| 12 | Hypothetical marking | Any | every `FlipOutcome` and `FlipSet` has `hypothetical is True`; schema rejects `False` |
| 13 | No leakage | Claim text contains `"MARKER-9F"` | marker absent from the serialised analysis and from the LLM prompt payload |

Integration (`tests/pipelines/test_decision_flip_step.py`, `tests/api/test_decision_flip_api.py`):

- **Restart recovery (6):** run the step, then run the handler again with the same run/step as a re-claimed attempt → one `decision_flip_analyses` row, same `analysis_id`, `created: false`. Simulate a crash after insert (raise before step completion), let the engine retry → step ends `done`, one row. With notes enabled and a fake LLM: crash between insert and notes → retry writes notes once; cost ledger has exactly one model row.
- Step order: a recheck plan contains `evaluate` → `decision_flip` → `request_list`; with the budget exhausted the flip step still runs.
- Loop: v1 has 2 blockers; add evidence that supports one; recheck → v2 exists, v1 and its analysis untouched, v2 analysis has 1 blocker, API `resolution` names the resolved item and the evidence id; add the second → v3 `prioritise`, `state == "no_blockers"`.
- Unchanged inputs: re-run evaluate → no new version, no new analysis row.
- Request list: items ordered blocker → risk → other; analyst-only blockers absent from the seller email; no approval row and no send created by the step; `email_send_enabled` untouched.
- LLM guard: fake model returns a note with "70% likely" and a note citing an unknown id → both dropped, template used, `notes_source == "template"` for those.
- API: section present in `GET /cases/{id}`; summary field in `GET /cases`; `POST` twice → 201 then 200, same body; workspace isolation (another workspace's case → 404).

Web (component tests with fixtures): each panel state in §6.2 renders; a hypothetical card never contains a `DispositionStamp` or `StatusMark`; every hypothetical card contains the text "Hypothetical"; mobile width has no horizontal overflow.

---

## 9. Implementation chunks

Order is chosen so the whole pipeline works end to end as early as possible; polish and the LLM come last.

### B1. Rules evaluator (Opus) — first

Owns: `apps/api/app/rules/decision_flip.py` (new), `rules/evaluate.py` (extract `redecide`, no behaviour change), `rules/__init__.py`, `domain/types.py` (new models), `rules/POLICY.md` (new §9 "DecisionFlip"), `tests/rules/test_decision_flip.py`.
Done when: tests 1 to 5 and 7 to 13 pass and the existing rules tests are unchanged.

### B2. Persistence, step, API (Opus) — second, unblocks the UI for real data

Owns: `alembic/versions/0006_decision_flip.py`, `db/models.py`, `db/repo.py`, `pipelines/evaluate/flip.py` + `flip_step.py` (new), plan wiring next to each `evaluate_step`, `api/cases_sections.py` (section + summary field), `api/decision_flip.py` (new router) + `api/router.py`, `api/schemas`, `api/fixtures.py`, OpenAPI export.
Done when: a recheck run produces a version, an analysis and the API returns it; restart-recovery tests pass.

### B3. Request prioritisation (Opus) — third

Owns: `pipelines/act/request_list.py`, `pipelines/act/step.py`, `drafting/seller_email.py` (ordering only), `api/requests.py` + schema (`priority`).
Done when: the request list for a version with an analysis is ordered and labelled; approval and send tests are unchanged.

### F1. Panel and case integration (Fable) — starts in parallel with B1, against fixtures

The fixture JSON is agreed from §7.1 on day one so F1 does not wait for B2.
Owns: `apps/web/components/decision-flip/` (new: `panel.tsx`, `compact.tsx`, `hypothetical-card.tsx`, `item-row.tsx`, `adapt.ts`), `lib/api/client` types (regenerated), `components/case/overview-tab.tsx`, `components/case-b/assessment-view.tsx`, `components/case-b/request-list.tsx` (grouping), `globals.css` (hatch token).
Done when: all §6.2 states render from fixtures, desktop and mobile, and switch to the live API behind the same adapter.

### F2. Board, live run, motion, showcase (Fable) — after F1 and B2

Owns: `components/dashboard/case-cells.tsx` (blocker line + sort), `components/dealproof/run-progress.tsx` / the run view (step label, blocker line, `finding` handling), resolution motion (§6.7), `components/marketing/sections.tsx` + `content.ts` (showcase).

### B4. Optional notes (Opus, Haiku at runtime) — last, can be cut

Owns: `pipelines/evaluate/flip_notes.py`, settings flag, guard tests. F1 already renders `notes` when present.

```
day order:   B1 ──► B2 ──► B3 ──► B4
             F1 (fixtures) ─────► F1 (live) ──► F2
pipeline working end to end = B1 + B2 + F1; everything after is additive.
```

No two chunks edit the same file except `domain/types.py` and the API schemas, which B1 lands first.

---

## 10. Open decisions

1. **Should a contradicted material claim be a disqualifier?** The pitch shows "If a mandatory claim is contradicted → Review disqualifier". Policy 5 says it only blocks Prioritise. This design follows the policy. Changing it is a policy change (new `POLICY_VERSION`, re-assessing every case), not a DecisionFlip feature. Recommendation: keep the policy; the panel's "Prioritise is out of reach while this stands" already carries the message.
2. **"Request only the blockers" toggle** on the Request tab (§3). Recommendation: ship ordering and labels first; add the toggle only if managers ask, because a narrower email means a second round of requests later.
3. **Preference criteria as blockers.** Unknown preference criteria are included because they can move fit across 70. If that feels noisy in practice, restrict to must-haves plus any preference that appears in a minimal set (the output already supports that filter).
4. **Feature name in the product.** "DecisionFlip" is used as the panel title. If it should stay an internal name, the title becomes "What would change the decision" with no other change.
