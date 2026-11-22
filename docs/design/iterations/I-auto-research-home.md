# I. Auto-research and the personalised home

Nov 22, 2026 · design only, nothing built

Builds on [E](E-onboarding-personalisation.md) (org profile, auto-fill), [D](D-live-run-experience.md) (live runs), [G](G-discover-thesis-criteria.md) (thesis and criteria), [F](F-decisionflip.md) (next best action) and [B](B-app-consistency.md) (Overview IA, panel and table patterns). Reuses `apps/api/app/pipelines/discover/` and `pipelines/investors/` as they are.

The request, in the user's words: after onboarding, the agent should preprocess the company's details, go through the net, and come back with the best-fit companies to acquire and the best funds to reach out to, shown visually on the home page.

## 0. The short version

- Finishing onboarding starts one **research run** for the workspace. It reads the confirmed profile and the user's own company record, looks at the market around it, derives a thesis or a set of comparables, and launches the existing Discover run, the existing investor search, or both, in parallel.
- Overview (`/app`) becomes the place where that work appears: live while it runs, then as five panels. `Your company`, `Best acquisition fits`, `Funds to approach`, `Market signals`, `Next`.
- Every recommendation carries a **rationale built from pairs of sourced facts**: one about the user's company, one about the other party. Rules decide which reasons apply. Haiku only words them, and its sentence is checked against the facts it was given.
- No new search logic. The new backend is: a derivation step, a rationale step, an orchestration row, one read endpoint.
- The PRD rules hold without exception: fit is not a prediction, investor ranking describes past behaviour, every fact has a source and a date, unknowns are printed, nothing is sent without a named person's approval.
- One thing changes in B: Overview's first screenful is now research, and the book-of-work panels (Needs you, By disposition, Recently updated) move below it.

Dependency found while reading the code: `org_profiles` and the `/profile` routes from E are not in `apps/api/app` yet. Chunk B0 below is the slice of E this feature cannot run without.

## 1. The flow

### 1.1 From onboarding to a running research

```
Step 4 of onboarding (Approvals and notices)
┌──────────────────────────────────────────────────────────────────────────┐
│ …existing fields…                                                        │
│                                                                          │
│ When you finish                                                          │
│ [✓] Research acquisition targets and funds for Acme Freight              │
│     Reads your confirmed profile and public company data.                │
│     Up to 120 credits · usually 2 to 4 minutes · nothing is sent         │
│     to anyone.                                                           │
│                                                    [ Back ]  [ Finish ]  │
└──────────────────────────────────────────────────────────────────────────┘
```

- The checkbox is on by default and the cost ceiling is printed before the spend. "Starts automatically" means the user does not have to go and find a button. It does not mean credits are spent without being told.
- `Finish` calls `POST /profile/onboarding` then `POST /profile/research`, and routes to `/app`. The home page opens with the research already running.
- Unchecked, or onboarding exited early: home shows the `Your company` card and one `EmptyState` with `Research targets and funds · up to 120 credits`.
- No confirmed own company (`own_company_match` is `none`, `rejected`, `failed` or `not_run`): the research still runs from stated fields. Everything that would have needed the record is listed under `Not used` (§2.4). It is never filled with a guess.

### 1.2 Which research runs

Decided by rule from the profile, never by the model.

| Profile | Mode | What runs |
| --- | --- | --- |
| `org_type = investor_acquirer` | `acquire` | (a) acquisition fits |
| `org_type = business`, any `raise_*` set | `raise` | (b) funds |
| `org_type = business`, `thesis_deal_types` set and `raise_*` set | `both` | (a) and (b) in parallel |
| `org_type = business`, neither set | `raise` | (b), with a notice that no raise details were stated |
| `org_type = adviser`, `acts_for = buyers` / `businesses` / `both` | `acquire` / `raise` / `both` | as above, about the adviser's stated client thesis. The adviser's own record is not used as the subject |

The home header has a mode control (`Acquire · Raise · Both`) that changes the mode for the next run. It does not start one.

### 1.3 The run, step by step

One new run kind, `RunKind.ORG_RESEARCH`, plus the two existing kinds as children. The parent owns derivation and rationale; the children are the pipelines as they exist today.

```
research.profile ─► research.market ─► research.derive ─► research.launch
                                                               │
                              ┌────────────────────────────────┴───────────────┐
                              ▼                                                ▼
                 RunKind.DISCOVER (existing)                RunKind.INVESTOR_DISCOVER (existing)
                 search → gate → enrich → score → explain    spec → comparables → enrich → rank
                              └────────────────────────────────┬───────────────┘
                                                               ▼
                                        research.rationale ─► research.signals
                                        (second ORG_RESEARCH run, phase = "finish")
```

| Step | What it does | Calls | Cost |
| --- | --- | --- | --- |
| `research.profile` | Loads `ProfileContext` at run creation and freezes it on the row. If `record_retrieved_at` is older than 30 days, re-enriches the own company (same reduced field list as auto-fill) | `company_enrich` × 0–1 | 0–2 cr |
| `research.market` | Peer set: companies with the same industry and country, within two size bands of the user's. Search fields only. Reads acquisitions and investors off the peers' records **when those fields are present** | `company_search` × 1 (limit 25) | about 6 cr |
| `research.derive` | Haiku proposes theses or comparable descriptions from the frozen profile and the peer set. Rules validate (§4.3) | `messages` × 1 | about $0.01 |
| `research.launch` | Creates the thesis and criteria and calls `start_search`; builds `InvestorSearchIn` and calls `start_investor_search` with `use_own_company`. Idempotent | none | 0 |
| children | Unchanged. Discover drops the user's own company from the shortlist (E §4.7) | as today | budgets below |
| `research.rationale` | For the top 10 targets and top 8 funds: rules build reason rows from fact pairs, Haiku writes one sentence per row, the sentence is quote-checked | `messages` × 2 (batched) | about $0.02 |
| `research.signals` | Collects dated events from records the run already holds. No new calls | none | 0 |

Acquisition theses come from four **angles**. Each is a rule-defined shape the model fills in, so the user sees why a company was looked for, not only that it was found.

| Angle | Derived from | Example for a warehousing and transport operator |
| --- | --- | --- |
| `adjacent_capability` | own activity categories vs. categories common among peers that the own record lacks | "Transport management software for 3PLs" |
| `geographic_expansion` | own HQ and locations vs. stated `thesis_geographies` | "Warehousing operators in Tamil Nadu and Karnataka" |
| `same_customers` | own stated customer segment (`one_line`, `thesis_note`) | "Supply-chain software sold to enterprise shippers" |
| `peer_precedent` | acquisitions on peers' records, only when at least two dated ones exist | "Cold-chain operators, as acquired by two peers since 2024" |

The demo runs **one** Discover run whose thesis merges the top two angles (criteria tagged with their angle). Running one Discover run per angle is the same code and a larger budget; it is chunk B5 and can be cut.

For (b), `research.derive` produces the `InvestorSearchIn` (sector wording, stage, size band, funding kind) from the enriched record, so the comparable search uses the record's activity categories and real headcount instead of form text.

### 1.4 Budget and cost display

| Bucket | Credits | Notes |
| --- | --- | --- |
| Derivation (`profile` + `market`) | 10 | hard cap; over it `market` is skipped and a notice says so |
| Discover child | 70 | `budget_credits` passed to `create_run`; the existing default of 100 is for user-started screenings |
| Investor child | 40 | passed through `start_investor_search(budget_credits=…)` |
| **Ceiling, mode `both`** | **120** | `acquire` 80, `raise` 50 |

- New setting `research_credit_budget` (default 120) with the three sub-budgets beside it in `jobs/config.py`.
- Charged to the workspace like any run. The auto-fill lookup stays on the platform's onboarding budget as E specifies.
- Display follows D: one cost meter on the home run band, `63 of 120 cr · $0.03`. Credits and model dollars are never added. The band's disclosure shows the three buckets.
- At budget, steps stop and the affected rows read `Not checked · budget reached`. A fund or target that was not enriched is listed as such, never dropped silently and never shown as a clean result.
- After the run the `Your company` card keeps a line: `Research · 22 Nov 2026, 16:42 IST · 63 cr · $0.03 · Run log`.

### 1.5 Re-run rules

- **Automatic start happens once per workspace**, at onboarding finish. Never on login, never on a timer.
- **Stale** is a state, not a trigger. The research is stale when the profile's `version` moved and any thesis, raise or record field differs from the frozen inputs, or when it is older than 30 days. Home then shows one line above the panels: `Your profile changed since this research (sector, deal size). Re-run · up to 120 credits`. The old results stay on screen, dated.
- **Manual re-run** from the run band's menu. Refused with 409 while one is running. Limit: one start per 10 minutes, five per workspace per day.
- A re-run reuses `api_cache`, so unchanged calls cost 0 and the meter shows `+0 · cache`.
- Each research is a new row. Home shows the latest finished one, with `Previous research` (date, counts) one click away. Nothing is overwritten.
- A failed child leaves the other child's results on the page; the failed panel shows the error state from B §2.6 with `Retry this part`.

### 1.6 Live progress on the home page

While any of the runs is going, the research region of Overview is a live view built from D's components, fed by the three event streams merged client-side by `at`.

```
Overview                                                                       [ + New ▾ ]
Acme Freight · Corporate development · Pune, India

 ◍  Analyst working · Research for Acme Freight
    Enriching 15 warehousing companies in South India          1 min 42 s   ▮▮▮▮▮▯▯▯▯▯ 63 of 120 cr · $0.03

┌ Steps ───────────────────┐ ┌ Acquisition fits · assembling ─────────┐ ┌ From Crustdata ─────────┐
│ ✓ Read your profile      │ │ candidate-stream rows (D §1.6)         │ │ 41 companies searched   │
│ ✓ Looked at 25 peers     │ │ Stellar Logistics   passed must-haves  │ │ 15 enriched             │
│ ✓ Derived 2 theses       │ │ Northline Freight   enriching…         │ │ 112 funding rounds read │
│ ◍ Acquisition fits  3/5  │ ├ Funds · assembling ────────────────────┤ ├ Sources ────────────────┤
│ ◍ Funds             2/4  │ │ investor-stream rows (D §1.8)          │ │ ticker (D §1.5)         │
│ ○ Write the reasons      │ │ Lightrock · 3 comparable rounds        │ │                         │
└──────────────────────────┘ └────────────────────────────────────────┘ └─────────────────────────┘
```

- The step list is grouped: the parent's steps, with each child shown as one row carrying its own `done/total` step count and a disclosure for its steps.
- `research.derive` emits a `finding` with `subject: "assessment"` whose items are the derived theses, so the user reads what is being searched for before results arrive. Each has `Edit thesis` linking to the G brief sheet; editing does not interrupt the running search, and the edit applies to the next run.
- The `Your company` card is static and present from the first frame. It is the one panel that needs no run.
- On finish the streams fold into the result panels the way D §1.11 describes: Discover rows become ranked rows in place, the investor stream is replaced by the list-and-detail with a fade.
- The user can leave. The run continues, the sidebar's Overview item shows the running dot, and returning replays from persisted activities.

## 2. The rationale

### 2.1 The rule

A reason is a **pair of facts and a relation**: something sourced about the user's company, something sourced about the other party, and a rule that says they relate. If either fact is missing the reason is not asserted. It appears as `unknown` with what would settle it.

```
Stellar Logistics · fit 78 of 100 · 70% of criteria assessable

 Adjacent capability                                                    supported
   You   Warehousing and storage; contract logistics     [Crustdata · as of 1 Nov 2026]
   Them  Transport management software for 3PLs          [Crustdata · as of 14 Oct 2026]
   Their product covers transport planning, which your record does not list.

 Same region                                                            supported
   You   HQ Pune; locations in Bengaluru, Chennai        [Crustdata · as of 1 Nov 2026]
   Them  HQ Coimbatore, Tamil Nadu                       [Crustdata · as of 14 Oct 2026]

 Shared customers                                                       unknown
   No public page naming customers was read for either company.
   Would settle it: a customer list from the seller, or named case studies.

 Size within your stated range                                          supported · estimate
   You   Looking for 51 to 500 people                    [Stated in your profile · 22 Nov 2026]
   Them  About 140 people, from professional profiles    [Crustdata · as of Oct 2026 · estimate]

 Deal size                                                              unknown
   You   Looking for $2M to $10M                         [Stated in your profile]
   Them  No valuation or revenue is on public record. Team size is not used as a stand-in.

Fit measures how well this company matches what you said you are looking for.
It is not a forecast of returns or of whether a deal can be done.
```

### 2.2 Reason kinds

Targets:

| Kind | Rule (deterministic) | Own fact | Their fact |
| --- | --- | --- | --- |
| `adjacent_capability` | their categories ∩ the derived adjacency set ≠ ∅ and ∩ own categories = ∅ | own categories | their categories |
| `same_activity` | category overlap ≥ 1 | own categories | their categories |
| `same_region` / `new_region` | their HQ country or state in own locations / in `thesis_geographies` but not in own locations | own locations or stated geographies | their HQ |
| `size_in_range` | headcount inside `thesis_size_min..max` | stated range | headcount, always marked estimate |
| `ownership_match` | matches `thesis_ownership` | stated | company type |
| `shared_customers` | a customer name appears on a read public page of both | page excerpt | page excerpt. `unknown` unless both pages were read |
| `shared_investor` | an investor key on both funding records | own dated round | their dated round |
| `peer_precedent` | ≥ 2 peers hold a dated acquisition in the target's category | peer acquisition records | their category |
| `recent_activity` | a dated event in the last 12 months | none | the event. Labelled an observed signal, never traction |
| `deal_size` | never supported from public data | stated band | `unknown`, always printed |

Funds:

| Kind | Rule | Facts |
| --- | --- | --- |
| `comparable_rounds` | n dated rounds in comparable companies | each round: company, round type, date, source |
| `recency` | date of the latest comparable round | that round |
| `stage_fit` | share of their comparable rounds within one stage of the user's | stage of each round; own stage from the latest dated own round |
| `cheque_fit` | median disclosed round amount of the comparables vs. `raise_amount_band`. Round totals are not the investor's cheque, and the row says so | amounts where disclosed; `unknown` when fewer than 2 are |
| `invested_in_you` | investor key on the own record's dated rounds | own round |
| `geography` | comparables in the user's country | comparable HQs |

The fund ranking stays what `rank_step` computes today: a recency-weighted count of comparable rounds. Stage and cheque fit are **shown beside** the rank as their own columns. They do not enter the score in this iteration, so the phrase "ranked by past comparable investments" stays exactly true. Folding them into the score is an open decision (§7).

Fixed sentence under the fund list: `Ranked by past investments in comparable companies. This describes what each fund has done. It does not predict whether they will invest.`

### 2.3 How a reason is written

1. Rules build the reason rows with their fact pairs and state. This alone is enough to render.
2. Haiku receives, per company, only those rows and writes one sentence per supported row (max 160 characters) and one headline (max 120).
3. Each sentence is checked: every company name, number, place and date in it must appear in the row's facts (the same quote check `extract_criteria` uses). A failing sentence is dropped and the row renders with facts only. A headline that fails falls back to the template `{kind label}: {own value} + {their value}`.
4. The model never adds a reason, changes a state or sees anything it was not given. `unknown` rows get no sentence; their text is a template.

### 2.4 What was not used

Each panel ends with a `Not used` disclosure listing inputs the research wanted and lacked, in plain words: `Your customer segment was not stated`, `No acquisitions are on record for the 25 peers read`, `4 of 15 companies were not enriched: budget reached`. This is the home-page form of "unknowns are stated".

### 2.5 Approval

- `Verify` on a target opens a case and starts identity. It contacts nobody.
- `Draft approach` on a fund creates a draft in Approvals. Sending needs a named approver, is done once, and the recipient address is typed by the user. DealProof does not look up investors' contact details, and the draft screen says so.

## 3. Overview as the command centre

### 3.1 Desktop (≥ 1280px), mode `both`

```
Overview                                                                              [ + New ▾ ]
Acme Freight · Corporate development · Pune, India                      Mode  Acquire · Raise · [Both]
Research 22 Nov 2026, 16:42 IST · 63 cr · $0.03 · Run log · Re-run ▾

┌ Your company ─────────────────────────────────────────────────────────────────────── span 12 ┐
│ Acme Freight Pvt Ltd   acmefreight.example   [Crustdata · as of 1 Nov 2026]          Edit    │
│ Warehousing and contract logistics for enterprise shippers.                                  │
│ ┌ People ───────┬ Founded ──┬ Stage ───────┬ Raised ───────┬ Looking for ──────────────────┐ │
│ │ ~180          │ 2014      │ Series A     │ $12.4M        │ Warehousing, SC software      │ │
│ │ estimate      │           │ 3 Jun 2025   │ 2 rounds      │ India · 51–500 · $2–10M       │ │
│ │ ▁▂▃▄▅ 24 mo   │           │              │               │ stated 22 Nov 2026            │ │
│ └───────────────┴───────────┴──────────────┴───────────────┴───────────────────────────────┘ │
│ Searched for  [Adjacent: transport software for 3PLs] [New region: Tamil Nadu, Karnataka]    │
└──────────────────────────────────────────────────────────────────────────────────────────────┘

┌ Best acquisition fits 12 ───────────────────────────────── span 8 ┐ ┌ Where they are ── span 4 ┐
│ #  Company            Fit · assessable        Why                 │ │ Tamil Nadu     ▇▇▇▇▇  5  │
│ 1  Stellar Logistics  78 ▇▇▇▇▇▇▇▇░░  70% ▒▒▒▒▒▒▒░░░               │ │ Karnataka      ▇▇▇    3  │
│    Coimbatore · ~140  Adjacent: your warehousing + their TMS      │ │ Maharashtra    ▇▇     2  │
│                       [Adjacent][Same region][Size]   [ Verify ]  │ │ Telangana      ▇      1  │
│ 2  Northline Freight  74 ▇▇▇▇▇▇▇░░░  85% ▒▒▒▒▒▒▒▒▒░               │ │ Not on record  ▇      1  │
│    Chennai · ~320     New region: no Acme location in Chennai     │ │ ● you are in Maharashtra │
│                       [New region][Same activity]     [ Verify ]  │ ├ Why they fit ────────────┤
│ 3  Cold Chain Logix   71 ▇▇▇▇▇▇▇░░░  55% ▒▒▒▒▒▒░░░░               │ │        Adj Reg Siz Cus Pr│
│    Hyderabad · ~90    Peers acquired 2 cold-chain operators       │ │ Stell   ●   ●   ●   ○  – │
│                       [Peer precedent][Size]          [ Verify ]  │ │ North   –   ●   ●   ○  – │
│ …5 rows                                                           │ │ ColdC   –   –   ●   ○  ● │
│ Fit is a match to your stated criteria, not a forecast.           │ │ ● supported ○ unknown    │
│ View all 12 · Edit thesis · Not used (3)                          │ │ – does not apply         │
└───────────────────────────────────────────────────────────────────┘ └──────────────────────────┘

┌ Funds to approach 9 ─────────────── span 5 ┐ ┌ Lightrock India ───────────────────── span 7 ┐
│ #  Fund             Rounds  Latest   Stage │ │ 4 comparable rounds · latest 12 Aug 2026      │
│ 1  Lightrock India    4     Aug 2026  ●●●○ │ │                                               │
│ 2  Elevation Capital  3     Mar 2026  ●●○○ │ │ 2023        2024        2025        2026      │
│ 3  Sixth Sense        3     Nov 2025  ●○○○ │ │ ──┼──────────┼─────●─────┼──●────────┼─●─●─▏  │
│ 4  Fireside           2     Jun 2026  ●●○○ │ │            Series A    Series B   A   A  now  │
│ …6 rows                                    │ │ ▲ your stage: Series A                        │
│ Ranked by past investments in comparable   │ │ Shiprocket    Series B  14 Feb 2025  $32M [▪] │
│ companies. It does not predict whether     │ │ LetsTransport Series A  12 Aug 2026  $8M  [▪] │
│ they will invest.                          │ │ Stage fit 3 of 4 · Median round $9M of 3      │
│ View all 9 · Not used (1)                  │ │ disclosed · your ask $2–10M                   │
│                                            │ │ Unknown: fund size, current mandate           │
│                                            │ │                 [ Draft approach · approval ] │
└────────────────────────────────────────────┘ └───────────────────────────────────────────────┘

┌ Market signals 8 ───────────────────────────────────────── span 8 ┐ ┌ Next ──────────── span 4 ┐
│ 12 Aug 2026  LetsTransport  Series A, $8M, led by Lightrock  [▪]  │ │ Verify Stellar Logistics │
│  9 Sep 2026  Meridian Ware… Announcement of a planned facility[✎] │ │ top fit, not yet a case  │
│ Oct 2026     Northline      Headcount ~320, up from ~260 · est[▪] │ │ Draft approach to        │
│ …            In warehousing and logistics · India · last 12 months│ │ Lightrock · needs Asha   │
│ View all in Signals                                               │ │ State your customer      │
└───────────────────────────────────────────────────────────────────┘ │ segment · unlocks 1 check│
                                                                      └──────────────────────────┘
── Your work ────────────────────────────────────────────────────────────────────────────────────
  stat row · Needs you · By disposition · Recently updated cases · Screenings     (B §4.2, unchanged)
```

Panel notes:

- **Your company.** Every tile is a `Fact` with its chip. Record values use the Crustdata chip, stated values a `Stated` chip with the confirmation date. The headcount tile has a sparkline only when the record holds a dated series; otherwise the tile is the number and `estimate`. `Raised` is absent, not zero, when no dated round exists. `Searched for` shows the derived angles as chips that open the thesis.
- **Best acquisition fits.** Two strips per row, deliberately different: fit is a solid ink bar, assessable is hatched, so a 78 with 55% assessable never reads like a 78 with 90%. Five rows on home, sorted by fit then assessable. The `Why` line is the top supported reason's headline. Chips are the supported reason kinds, at most three. `Verify` is one click: it creates the case from the candidate and navigates to it with identity running. A row that is already a case shows its disposition tag and `Open case`.
- **Where they are.** Region bars, not a map. The data is an HQ string per company; a map would imply coverage and precision the record does not have. Bars are one neutral series (B's ranked-list bar). `Not on record` is its own row. The user's own region is marked. Clicking a bar filters the list. Grouping is by state when ≥ 60% of rows share a country, else by country.
- **Why they fit.** The reason matrix: rows are the listed companies, columns the reason kinds present in this result (max 6). Three marks only: `●` supported, `○` unknown, `–` does not apply. Column headers have tooltips with the rule in a sentence. Hovering a cell highlights the row in the list; clicking opens the rationale popover from §2.1. The matrix makes unknowns visible as a column pattern ("we know nothing about customers for anyone"), which a list hides.
- **Funds to approach.** List and detail, the existing investor component. The home list adds a stage-fit dot scale (filled dots = comparable rounds within one stage of the user's, out of 4) and keeps the rank as computed. The detail's timeline plots each comparable round on a real time axis, one dot per round, labelled by round type, with `now` at the right edge and the user's stage as a marker below the axis. The dot is positioned by date only. Amount is in the table beneath, not encoded in dot size, because half the amounts are usually undisclosed. `invested_in_you` shows as a tag on the row.
- **Market signals.** Dated events from records this research already read: funding rounds of comparables and candidates, headcount changes (labelled estimate), announcements. Sub-line states the filter. Events link to the company row above when it is on the page. Empty means the panel is absent.
- **Next.** At most three rows, chosen by rule in this order: verify the top fit that is not a case; draft an approach to the top fund (shows who must approve); state one missing profile field that would turn an `unknown` reason column into an assessable one; re-run when stale. When cases exist, F's next best action rows take precedence over the first.

Mode `acquire` drops the funds row and lets `Best acquisition fits` show eight rows. Mode `raise` drops the fits row; `Funds to approach` moves up and `Your company` gains an `Invested in you` line.

### 3.2 Tablet (768–1279px)

Each span-8 / span-4 pair stacks, list first. The fund detail opens beneath the selected row as an inline expansion. The matrix keeps its columns and scrolls horizontally inside its panel with the company column sticky.

### 3.3 Mobile (< 768px)

```
┌──────────────────────────────┐
│ Overview              [ + ]  │
│ Acme Freight · Corp dev      │
│ [Acquire][Raise][Both]       │
│ Research 22 Nov · 63 cr      │
├ Your company ────────────────┤
│ Warehousing and contract…    │
│ ~180 est │ Series A │ $12.4M │  ← 3 tiles, swipe for 2 more
│ Searched for [Adjacent…] +1  │
├ Next ────────────────────────┤
│ Verify Stellar Logistics   › │
│ Draft approach · Lightrock › │
├ Best acquisition fits 12 ────┤
│ 1 Stellar Logistics          │
│   78 ▇▇▇▇▇▇▇▇░░ 70% ▒▒▒▒▒▒▒░ │
│   Adjacent: your warehousing │
│   + their TMS                │
│   [Adjacent][Region] ●●●○–   │  ← matrix row folded into the card
│   [ Verify ]                 │
│ 2 Northline Freight …        │
│ View all 12                  │
├ Where they are ──────────────┤
│ Tamil Nadu  ▇▇▇▇▇ 5          │
│ Karnataka   ▇▇▇   3   +3     │
├ Funds to approach 9 ─────────┤
│ 1 Lightrock India            │
│   4 rounds · Aug 2026 · ●●●○ │
│   ─●────●──────●─●▏          │  ← timeline, no labels; tap for detail sheet
│ 2 Elevation Capital …        │
│ Ranked by past investments…  │
├ Market signals 8 ────────────┤
│ 12 Aug 2026 · LetsTransport  │
│ Series A, $8M           [▪]  │
├ Your work ───────────────────┤
│ Needs you 4 · Cases 14     › │
└──────────────────────────────┘
```

- `Next` moves to second place: on a phone the action is what the user came for.
- The matrix has no room as a table. Each card carries its own row of marks, with the legend once under the panel title.
- Fund detail is a bottom sheet with the full timeline and the rounds table.
- While running: run band, then the collapsed step line (`Step 4 of 6 · Acquisition fits · enriching`), then the two streams stacked, as D's mobile layout.

### 3.4 States

| State | What shows |
| --- | --- |
| No research yet | `Your company` + one page-size empty state with the start button and the ceiling |
| Running | §1.6. Panels for a finished child appear as soon as that child finishes; the other stays live |
| Finished, no targets | Panel with `No company passed your must-haves` and the two loosest must-haves named, `Edit thesis` |
| Finished, fewer than 8 comparables | Funds panel with the investor pipeline's existing scope note (`MIN_COMPARABLES`) and what was widened |
| One child failed | That panel in error state with `Retry this part`; the other normal |
| Stale | Stale line above panels; results dated and unchanged |
| Profile not confirmed | `Your company` shows `Confirm your profile` and research is offered from stated fields only |

### 3.5 Motion, only on real events

| Event | Motion |
| --- | --- |
| `activity` arrives during a run | D's rules unchanged: NOW line cross-fade 200ms, cost tween 360ms, stream rows enter in paced batches |
| A child run finishes | Its stream folds into the result panel (D §1.11). Fit strips draw left to right once, 360ms, staggered 40ms per row, max 8 rows |
| `research.rationale` finishes | Reason chips and matrix marks fade in, 200ms. No stagger: they arrive as one fact |
| User selects a fund | Detail cross-fades 160ms; timeline dots do not re-animate |
| User clicks a region bar | List filters with a 160ms opacity change; no reflow animation |
| Stale line appears | No motion. It is there on load |

Nothing loops, nothing pulses, nothing animates on load of a finished page. Reduced motion: all of the above become instant, and the cost number updates without a tween.

### 3.6 Vocabulary

`Best acquisition fits` and `Funds to approach` are the panel titles. "Recommended", "top picks", "for you", "likely to invest", "match score" (for funds) and "AI" as a label do not appear. A fund has a rank and counts, never a percentage.

## 4. API and backend

### 4.1 Persistence

```
org_research                                   -- one row per research attempt
  id                    uuid pk
  workspace_id          uuid fk, indexed
  created_by            uuid null fk users.id
  mode                  text not null          -- acquire | raise | both
  trigger               text not null          -- onboarding | manual | retry
  profile_version       int not null
  inputs                jsonb not null         -- frozen ProfileContext + record snapshot ids
  inputs_hash           text not null          -- sha256 of canonical inputs; stale check and dedupe
  market                jsonb null             -- peer set summary, source ids
  derivation            jsonb null             -- angles, proposed and validated, dropped proposals with reasons
  thesis_id             uuid null fk theses.id
  discovery_run_id      uuid null fk discovery_runs.id
  investor_run_id       uuid null fk investor_runs.id
  status                text not null          -- deriving | searching | finishing | ready | partial | failed
  budget_credits        numeric not null
  created_at, finished_at timestamptz
  unique (workspace_id) where status in ('deriving','searching','finishing')   -- one live research

research_reasons                               -- the rationale, one row per reason
  id                    uuid pk                -- uuid5(research_id, subject_type, subject_key, kind)
  research_id           uuid fk, indexed
  subject_type          text                   -- target | fund
  subject_key           text                   -- crustdata company id | investor_key
  kind                  text                   -- §2.2
  state                 text                   -- supported | unknown | not_applicable
  position              smallint
  own_fact              jsonb null             -- { value, source_id | "stated", as_of, is_estimate }
  their_fact            jsonb null
  text                  text null              -- checked sentence, or null → template
  would_settle          text null              -- unknown rows only
```

`runs` gains `org_research_id uuid null` and `RunKind.ORG_RESEARCH`. `theses` gains `origin text` (`user | research`) and `org_research_id`. Headlines live in `org_research.derivation.headlines[subject_key]`. Sources reuse the `sources` table, so every chip on home resolves the way case chips do.

### 4.2 Endpoints

All scoped by `current_workspace_id`, under E's `/profile` prefix. (`/org/profile/research` in the brief is this route; one prefix, not two.)

**`POST /profile/research`** → `202`

```jsonc
// request (all optional)
{ "mode": "both",                 // default: derived from the profile (§1.2)
  "trigger": "onboarding",        // onboarding | manual | retry
  "retry_part": null,             // "acquire" | "raise": re-launch one failed child of the latest research
  "base_profile_version": 3 }     // 409 if the profile moved, so the UI's stated cost and inputs are the ones used

// response
{ "research": { "id": "…", "mode": "both", "status": "deriving", "trigger": "onboarding",
                "profile_version": 3, "created_at": "2026-11-22T11:12:41Z",
                "budget": { "credits": 120, "derive": 10, "acquire": 70, "raise": 40 } },
  "runs": { "research": { …RunOut… }, "discover": null, "investors": null } }
```

Errors: `409 research_running` (returns the live one), `409 profile_changed`, `422 profile_incomplete` with `missing: ["sector"]` when neither a record nor a stated sector exists, `429` on the rate limits in §1.5, `402 budget` when the workspace cannot cover the ceiling.

**`GET /profile/research/latest`** → the same `research` + `runs` object, for polling fallbacks and the run log header. `GET /profile/research` lists past ones (id, mode, status, dates, counts).

**`GET /home`** → everything Overview's research region renders, in one read.

```jsonc
{ "generated_at": "2026-11-22T11:16:02Z",
  "profile_version": 3,
  "company": {
    "name": { …Fact… }, "domain": "acmefreight.example", "one_line": { …Fact… },
    "kpis": [
      { "key": "headcount", "label": "People", "fact": { "value": 180, "is_estimate": true, "source": {…}, "as_of": "2026-10-01" },
        "series": [ { "at": "2024-11-01", "value": 122 }, … ] },          // null when no dated series
      { "key": "founded_year", "label": "Founded", "fact": {…} },
      { "key": "stage", "label": "Stage", "fact": {…}, "sub": "3 Jun 2025" },
      { "key": "total_funding_usd", "label": "Raised", "fact": {…}, "sub": "2 rounds" },
      { "key": "looking_for", "label": "Looking for", "fact": { "value": "…", "origin": "stated", "confirmed_at": "…" } } ],
    "absent": ["revenue_band"] },
  "research": {
    "id": "…", "mode": "both", "status": "ready",       // null when none has run
    "stale": { "is_stale": false, "changed_fields": [], "age_days": 0 },
    "created_at": "…", "finished_at": "…",
    "cost": { "credits": 63.0, "budget_credits": 120, "usd": 0.03 },
    "runs": { "research": {…RunOut…}, "discover": {…RunOut…}, "investors": {…RunOut…}, "finish": {…RunOut…} },
    "angles": [ { "key": "adjacent_capability", "label": "Adjacent: transport software for 3PLs",
                  "basis": [ { …Fact… } ], "thesis_id": "…" } ],
    "not_used": [ { "scope": "acquire", "code": "no_customer_segment", "text": "Your customer segment was not stated" } ] },
  "targets": {
    "status": "ready",                                   // absent | running | ready | empty | failed
    "thesis_id": "…", "total": 12,
    "reason_kinds": ["adjacent_capability", "same_region", "size_in_range", "shared_customers", "peer_precedent"],
    "regions": [ { "label": "Tamil Nadu", "level": "state", "count": 5, "is_own": false },
                 { "label": "Not on record", "level": null, "count": 1, "is_own": false } ],
    "items": [
      { "candidate_id": "…", "crustdata_company_id": 4411, "name": "Stellar Logistics",
        "location": { …Fact… }, "headcount": { …Fact, is_estimate… },
        "fit": 78, "assessable_pct": 70,
        "headline": "Adjacent: your warehousing + their TMS",
        "reasons": [
          { "kind": "adjacent_capability", "state": "supported", "text": "Their product covers transport planning, which your record does not list.",
            "own": { "label": "You", "fact": {…} }, "theirs": { "label": "Them", "fact": {…} } },
          { "kind": "shared_customers", "state": "unknown", "text": null,
            "would_settle": "A customer list from the seller, or named case studies." } ],
        "unknowns": ["Revenue", "Deal size"],
        "case": null,                                    // or { "id": "…", "disposition": "investigate_further" }
        "actions": { "verify": { "method": "POST", "path": "/theses/{thesis_id}/candidates/{candidate_id}/case" } } } ] },
  "funds": {
    "status": "ready", "investor_search_id": "…", "total": 9,
    "ranking_basis": "Recency-weighted count of dated rounds in comparable companies",
    "scope_note": "…", "own_stage": "series_a", "ask_band": "2m_10m",
    "timeline": { "from": "2023-01-01", "to": "2026-11-22" },
    "items": [
      { "entry_id": "…", "rank": 1, "investor_name": "Lightrock India", "investor_key": "lightrock-india",
        "comparable_rounds": [ { …ComparableRoundOut, + "stage": "series_a", "in_stage_window": true… } ],
        "latest_comparable": "2026-08-12",
        "stage_fit": { "in_window": 3, "of": 4 },
        "cheque_fit": { "state": "supported", "median_round_usd": 9000000, "disclosed": 3, "of": 4,
                        "note": "Round totals, not this fund's own cheque" },
        "invested_in_you": null,
        "headline": "4 comparable rounds, latest Aug 2026; 3 at your stage",
        "reasons": [ … ], "unknowns": ["Fund size", "Current mandate"],
        "actions": { "draft_approach": { "method": "POST", "path": "/investor-searches/{id}/entries/{entry_id}/approach", "needs_approval": true } } } ] },
  "signals": {
    "filter": { "sectors": ["Warehousing", "Logistics"], "countries": ["India"], "months": 12 },
    "items": [ { "at": "2026-08-12", "precision": "day", "kind": "funding_round", "company_name": "LetsTransport",
                 "crustdata_company_id": 9920, "text": "Series A, $8M, led by Lightrock India",
                 "is_estimate": false, "source": {…SourceRef…}, "on_page": "fund:lightrock-india" } ] },
  "next": [
    { "kind": "verify_target", "label": "Verify Stellar Logistics", "sub": "Top fit, not yet a case", "action": {…} },
    { "kind": "draft_approach", "label": "Draft approach to Lightrock India", "sub": "Needs approval from Asha Rao", "action": {…} },
    { "kind": "complete_profile", "label": "State your customer segment", "sub": "Makes 1 reason assessable", "href": "/app/settings/profile#one_line" } ],
  "work": { "cases": 14, "needs_you": 4 }               // the rest of B's Overview keeps its existing calls
}
```

Rules for the shape: every displayed value is a `Fact` with a `SourceRef` or `origin: "stated"`, and the serializer drops any `record` fact whose source row is missing (as `load_investor_search` already does for rounds). `targets.items` is capped at 8 and `funds.items` at 8; "View all" goes to the existing screening and investor search pages, which stay the full views. While running, `targets.status` / `funds.status` are `running` and the client uses the run ids for SSE.

Two small action routes, both thin:

- `POST /theses/{thesis_id}/candidates/{candidate_id}/case` → `201 CaseOut`. If the existing shortlist-to-case route already does this, `actions.verify` points at it and nothing new is added.
- `POST /investor-searches/{id}/entries/{entry_id}/approach` → `201` draft message in `draft` state, listed in Approvals. Body built by the existing drafting module from the fund's reason rows; no recipient is filled in.

Live transport is unchanged: three `GET /runs/{id}/events` streams. No aggregate stream is added; the client merges by `at`.

### 4.3 Deriving the thesis: the model proposes, rules validate

Model: Haiku (`settings.anthropic_model`, `claude-haiku-5-5`), one call, structured output, through the existing recorder and cache so cost lands on the research run.

Input, and nothing else: the frozen profile fields (each tagged `record` or `stated`), the own record's categories, locations and one-line, and a table of the peer set (name, categories, HQ, headcount band, and acquisitions where present).

Output schema:

```jsonc
{ "angles": [
    { "key": "adjacent_capability",                 // enum of the four angles
      "thesis_text": "Privately held transport management software companies in India serving 3PLs, 51 to 500 people",
      "basis": [ { "field": "own.categories", "quote": "Warehousing and storage" },
                 { "field": "peers[3].categories", "quote": "Transport management software" } ],
      "adjacency_categories": ["Transport management software", "Fleet telematics"] } ],
  "investor_profile": { "sector": "…", "stage": "series_a", "size": "51-200", "funding_sought": "growth equity",
                        "basis": [ … ] } }
```

Validation, deterministic, in `app/research/derive.py`:

| Rule | On failure |
| --- | --- |
| Every `basis.quote` is a substring of the named input field | angle dropped, reason recorded |
| `adjacency_categories` ⊆ categories seen in the peer set or resolvable through Discover's `resolve_values` autocomplete | unresolved ones removed; none left → angle dropped |
| Geography ⊆ `thesis_geographies` ∪ own countries, normalised by `countries.py` | replaced with the stated geographies |
| Size, ownership, deal types are taken **from the profile**, not from the model's text | profile wins; the text is regenerated from E's fixed sentence template with the angle's sector phrase |
| `peer_precedent` needs ≥ 2 dated peer acquisitions | dropped; `not_used` gains `no_peer_acquisitions` |
| `stage` and `size` in `investor_profile` equal the deterministic values from the record when a record exists | record wins |
| At most 3 angles; ranked by number of basis facts, ties by angle order in §1.3 | truncate |

If the call fails or nothing survives, the fallback is E's `thesis_draft(ctx)` and `investor_search_prefill(ctx)`. They are pure functions of the profile, so the research never fails because the model did. The derivation JSON keeps both the proposals and what was dropped, so the run log can show it.

The criteria come from the existing `extract_criteria` on the validated thesis text (already quote-checked), then E's `criteria_split` sets must-have versus preference from the profile. The research adds nothing to criteria extraction.

### 4.4 Reuse map

| Need | Existing code | Change |
| --- | --- | --- |
| Create thesis and criteria | `discover.service.create_thesis` | accepts `origin="research"`, `org_research_id`; cost context points at the research run |
| Run the target search | `discover.service.start_search`, `steps.step_specs` | accepts `budget_credits` and an `enrich_top` override (15 for research) |
| Drop own company from shortlist | `discover.steps.gate_step` (E §4.7) | none beyond E |
| Target facts and unknowns | `discover.cards.build_card`, `met_reasons`, `unknowns` | read by the rationale step as its `their_fact` source |
| Run the fund search | `investors.service.start_investor_search` | already takes `budget_credits`, `search_limit`, `enrich_limit` |
| Comparables from own record | `investors.profile.build_plan` with `use_own_company` (E §4.7) | none beyond E |
| Rounds, sources, scrubbing | `investors.ingest`, `load_investor_search` | `stage` and `in_stage_window` added per round using `normalize_stage` and `stage_window` |
| Live events | `jobs` activity emit, `GET /runs/{id}/events` | new step keys `research.*`, labels from templates (D §2.10) |
| Own-company facts | E's `own_reference(ctx)` | extended with the KPI list |
| Signals | records held in `sources` / candidate and comparable snapshots | a pure collector, no calls |

New code is confined to `app/research/` (`service.py`, `steps.py`, `derive.py`, `reasons.py`, `signals.py`, `home.py`) and `api/profile_research.py`, `api/home.py`.

### 4.5 Restart safety

- **Frozen inputs.** `research.profile` writes `inputs` once; every later step and both children read from the row, never the live profile. A resumed run sees what the first attempt saw.
- **Idempotent launch.** The thesis id is `uuid5(research_id, "thesis")`, the discovery run `uuid5(research_id, "discover")`, the investor run `uuid5(research_id, "investors")`. `research.launch` inserts with `on conflict do nothing` and then starts whichever child has no run row. Re-running the step after a crash between the two launches starts only the missing one.
- **The finish phase.** When a child run reaches a terminal state, the worker's run-finished hook calls `research.maybe_finish(research_id)`: if every launched child is terminal and no finish run exists, create it with id `uuid5(research_id, "finish")`. The same function runs at worker start for every research in `searching`, so a crash between "child done" and "finish created" heals itself. `GET /home` never creates runs.
- **Rationale writes** are upserts on the deterministic `research_reasons.id`. A retried step overwrites row by row and cannot duplicate.
- **Model calls** go through `DbCache`, so a retried derive or rationale step replays from cache at zero cost and gives the same text.
- **Partial results.** `status = partial` when one child failed and the other finished; the finish phase runs for the part that exists. `retry_part` launches a new child run for the failed part against the same frozen inputs.
- **One live research per workspace** is enforced by the partial unique index, so a double-click on Finish or two tabs cannot start two.
- **Budget.** Each child's cap is its own `budget_credits`; the parent's ledger sums all three through `org_research_id`, and that sum is what the home meter shows.

## 5. Implementation chunks

Ordered for speed. Opus builds backend, Fable builds frontend. F chunks start against fixtures on day one; `GET /home` has a fixture mode like `fixture_activity.py`.

### Backend (Opus)

| # | Chunk | Contents | Unblocks |
| --- | --- | --- | --- |
| **B0** | Profile slice (only if E chunk 1 has not landed) | `org_profiles` table, `GET/PATCH /profile`, `POST /profile/autofill`, `ProfileContext`, `thesis_draft`, `investor_search_prefill`, `own_reference`. No revisions, no analytics | everything |
| **B1** | Research orchestration | `org_research` table, `RunKind.ORG_RESEARCH`, `research.profile` and `research.launch` steps using the **deterministic fallback** thesis and prefill, child budgets, idempotent ids, `maybe_finish` hook and startup reconcile, `POST /profile/research`, `GET /profile/research/latest` | a real auto-run end to end |
| **B2** | `GET /home` | `home.py` assembling company KPIs, targets from the discovery run's cards, funds from `load_investor_search` plus stage window and cheque fit, regions, stale check, `next`. Reasons from rules only (§2.2), no model text. Fixture mode | the whole home page on real data |
| **B3** | Derivation | `research.market` peer search, `research.derive` with Haiku and the validation table, angles on the row, `finding` activity for the derived theses | the "it understood my company" moment |
| **B4** | Rationale text and signals | `research_reasons` table, `research.rationale` (batched Haiku, quote check, template fallback), `research.signals`, `not_used` | sentences, headlines, the signals panel |
| **B5** | Actions and extras (cuttable) | candidate-to-case route if missing, fund approach draft into Approvals, `retry_part`, rate limits, one Discover run per angle, `shared_customers` via page reads | one-click verify, drafts |

### Frontend (Fable)

| # | Chunk | Contents | Depends on |
| --- | --- | --- | --- |
| **F1** | Home panels on fixtures | `components/home/`: `company-card`, `fit-list` (reuses the fit and assessable strips), `region-bars`, `reason-matrix`, `fund-list` + `fund-detail` with `round-timeline`, `signals-panel`, `next-panel`. Overview re-laid out per §3.1 with B's panels under `Your work`. Desktop, tablet, mobile. All states in §3.4 in the `/design` gallery | fixture JSON of §4.2 |
| **F2** | Live home | Onboarding step 4 checkbox and ceiling copy, `POST /profile/research` on finish, the home run band and grouped step list, merged activity store over three run ids (extends `use-run-activity`), embedding `candidate-stream` and `investor-stream`, fold into panels | B1; D components as built |
| **F3** | Rationale and actions | Rationale popover (§2.1), matrix cell and row linking, region filter, `Verify` and `Draft approach` wiring, stale line, re-run menu, mode control, `Not used` disclosures, run log link | B2, B4, B5 |

### Order and parallelism

```
Opus:   B0 ─► B1 ─► B2 ─► B3 ─► B4 ─► B5
Fable:  F1 (fixtures) ───► F2 (needs B1) ─► F3 (needs B2, then B4)
```

### Minimum to demo

**B0 (if needed) + B1 + B2 + F1 + F2.** That gives: finish onboarding, land on home with the research already running live, watch both streams assemble, and end on a home page with the company card, ranked fits with fit and assessable strips, region bars, a rule-built reason matrix, ranked funds with the rounds timeline, and one-click links into the existing screening and investor pages. The thesis is the deterministic one from the profile and reasons are fact pairs without sentences. It is honest and complete without a single new model call.

**B3 is the first thing to add** if time allows: derived angles are what make the result read as being about this company. Then B4 for sentences and signals, then F3. B5 last.

Demo script for the ContextCon customer: sign up as the logistics company's CFO office, confirm the Crustdata record, state "warehousing and supply-chain software, India, 51 to 500 people, $2M to $10M", finish, and watch home fill in.

## 6. Acceptance checks

- Finishing onboarding with the box checked starts exactly one research; a double submit returns the same one.
- The ceiling shown before start equals `budget.credits` in the response, and the run never exceeds it.
- Killing the worker during `research.launch` and restarting yields one thesis, one discovery run, one investor run.
- Every value on home with a record origin opens a source popover with a date. Removing a source row removes the value from `GET /home`.
- No target row shows a fit without its assessable percentage beside it.
- The fund panel shows no percentage and contains its fixed "does not predict" sentence in every state with rows.
- `deal_size` and `shared_customers` render as unknown, with what would settle them, when no supporting record exists.
- A model sentence containing a name or number not in its fact pair never reaches the page (unit test on the quote check).
- With the model unreachable the research finishes with status `ready` using the fallback thesis and template reasons.
- Changing a thesis field in the profile shows the stale line and spends nothing until Re-run is pressed.
- `Draft approach` creates a draft and sends nothing. No investor contact detail is stored or shown anywhere.
- Home at 375px has no horizontal page scroll. With reduced motion set, no element animates.

## 7. Open decisions

1. **Should stage and cheque fit enter the fund score?** This design shows them beside an unchanged rank so the ranking sentence stays literally true. Folding them in needs a new stated basis and a policy weight.
2. **One merged Discover run or one per angle?** Merged is 70 credits and one list. Per-angle is clearer about why each company appeared and costs up to 3×.
3. **Who pays for the first research?** Charged to the workspace here. Putting the first one on the platform's onboarding budget is friendlier and costs up to 120 credits per signup.
4. **Scheduled refresh.** None in this design; stale is shown and the user decides. A weekly refresh would need a spend consent stored on the profile.
5. **Shared customers.** Needs page reads on both companies' sites, which is new spend per target. In B5 and off by default.
6. **Advisers with several clients.** One profile means one research. Per-client research needs a client entity that does not exist yet.
