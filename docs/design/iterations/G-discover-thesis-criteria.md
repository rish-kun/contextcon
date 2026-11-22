# Iteration G: Discover steps 1 and 2, thesis and criteria

Date: 22 November 2026. Scope: `/app/discover/new` and the Criteria state of `/app/discover/[thesisId]`. Step 3 (the live run and the shortlist) is unchanged and stays with iteration D.

The user looked at the live Criteria step for the thesis "Cold chain technology" and said it needs to be updated. The screen showed one preference row, zero must-haves, a table header over one row, an open square that reads as a checkbox, a policy footnote and a lone `Run search` button. It gives no sense of what the search will do or find.

Read with: the PRD §6.1, `design-direction.md` §11.4, B §2 (page frame, panels), C §1.1 and §3 (motion), D §1.10 (starting a run), E §2 (personalisation map rows "Screenings · step 1" and "step 2"), `app-microcopy-v2.md` §2.

---

## 0. The short version

1. **The problem is not styling. The screen hides what the system knows.** The backend already knows which criteria become search filters, which keep blank records in, which can never be scored at screening, what the run will call and roughly what it will cost. None of it is on the page.
2. **The Criteria step becomes a brief sheet with eight fixed dimension rows** (geography, ownership, sector and activity, customer type, size, stage, growth signals, founded). A row is never blank: it holds what the thesis stated, or a suggestion marked `Suggested, not in your thesis`, or `Any`.
3. **A criterion is a sentence with editable tokens**, not three input boxes: `Headquartered in [India]`. The kind is a two-way switch on the row.
4. **Each criterion says how it will be assessed**, using four modes the code already has, plus the data source and a coverage figure that is either measured from Crustdata or says `Not measured`.
5. **A search plan rail sits beside the sheet**: the calls in order, the pool count where one exists, the credit range against the budget, an opt-in five-company preview with its price, and a small diagram of what must-have and preference do to a company.
6. **Step 1 reads the thesis back**: after submit, each phrase that became a criterion is underlined in the user's own text. While typing, a rule-based rough read shows which of the eight dimensions are covered.
7. **One real defect surfaced by the research**: a thesis whose only criterion is assessed from evidence produces a shortlist where every company shows `Fit unavailable`, because nothing can be scored at screening. "Cold chain technology" is exactly this case. The sheet says so before the run and offers the suggestion that fixes it.

---

## 1. Audit of the current screen

Signs found, per the unslop pass. The screen is light on slop and heavy on emptiness, so this is a restructure of content, not a restyle. Tokens, type, colour and the accent stay as `design-direction.md` sets them.

| # | Where | Sign |
| --- | --- | --- |
| 1 | Preference row, leading mark | The open 8px square is the "preference" bullet, but next to an input it reads as an unchecked checkbox |
| 2 | Row body | Three bordered inputs for one phrase. Label and value repeat each other (`Cold chain technology` / `cold chain technology`) |
| 3 | Table header band | Four column headers over a single row. Structure that encodes nothing at this size |
| 4 | Weight column | `1` in its own column. Weight follows kind, so it is the kind restated as a number |
| 5 | Must have group | `No must-haves. No company will be removed` then `Add criterion`: an empty state with no direction |
| 6 | Footer | A scoring-policy sentence explaining the weight column. It explains the UI, not the search |
| 7 | Action row | `Run search` alone at the right edge under 300px of nothing, with no estimate. `design-direction.md` §11.4 already requires "the search button states the estimated credit cost before anything is spent"; the build dropped it |
| 8 | Assessed from | `No search field covers this; unknown until evidence is read` is accurate and stops short of the consequence: nothing on this thesis can be scored |
| 9 | Whole page | Content capped at the thesis card's width logic, right half of a 1440 viewport unused |
| 10 | Step 1 | Example chips are bare noun phrases (`Cold chain technology`). Picking one produces the thin thesis the user then sees in step 2 |

The industry values, counts and suggestion wording in the mocks below are illustrative. Stored industry names come from the autocomplete endpoint at build time and were not looked up for this document.

Template check: swap the product name and step 2 would fit any CRUD settings page. After this iteration it should not: the sheet and the rail show Crustdata fields, the tri-state gate and credit arithmetic, which belong to this product only.

### Direction for these two steps

The five lines in `design-direction.md` §1 hold. Two additions for this surface:

- **Moment.** The search plan rail. It is the one place on these steps with drawn structure: an ordered list of real calls and one meter. The sheet beside it stays plain text on paper.
- **Signature.** The source line already ends every fact. Here it ends every criterion: `[▤ Crustdata · locations.country]` and a coverage readout. A criterion with no field gets the hatched "not checked" chip the product already uses, because that is what it is.

What is taken from the Dealroom screenshots: the density of a labelled key and value grid (Ownership, Headcount, Funding rounds each a small titled panel with a right-aligned meta line), and header stat figures with a small label under a mono number. What is not taken: the treemap colours, flame emoji, uppercase tracked labels, pill badges, the donut.

---

## 2. Step 1: thesis

### 2.1 Layout

Two columns from `lg`. The composer keeps the left column at the current `max-w-3xl`; the right column is the read panel. The page no longer leaves the right half empty.

```
 Discover
 1 Thesis ─── 2 Criteria ─── 3 Shortlist

 ┌ Describe what you are looking for ──────────────────────┐  ┌ What DealProof can read from it ──────┐
 │ Write it the way you would say it. Say where, what      │  │ Rough read while you type. The full   │
 │ they do, who they sell to and how big.                  │  │ read happens when you continue        │
 │ ┌─────────────────────────────────────────────────────┐ │  │                                       │
 │ │ Privately held Indian warehousing and supply-chain  │ │  │ ▪ Geography          India            │
 │ │ software companies that serve enterprise customers  │ │  │ ▪ Ownership          privately held   │
 │ │ and show recent expansion                           │ │  │ ▪ Sector and activity warehousing,    │
 │ │                                                     │ │  │                      supply-chain     │
 │ └─────────────────────────────────────────────────────┘ │  │                      software         │
 │ 141 of 4,000                                            │  │ ▪ Customer type      enterprise       │
 │                                                         │  │ ▫ Size               not stated       │
 │ Start from                                              │  │ ▫ Stage              not stated       │
 │ [ Your default thesis ] [ Same, any size ]              │  │ ▪ Growth signals     recent expansion │
 │ [ Same, in South-East Asia ]                            │  │ ▫ Founded            not stated       │
 │                                                         │  │                                       │
 │ ─────────────────────────────────────────────────────── │  │ 5 of 8 stated. The rest are suggested │
 │ No credits are spent at this step   [ Read the thesis ] │  │ on the next step, never applied       │
 └─────────────────────────────────────────────────────────┘  │ for you                               │
                                                              └───────────────────────────────────────┘
```

### 2.2 The composer

- Label `Describe what you are looking for`. Hint: `Write it the way you would say it. Say where, what they do, who they sell to and how big.` The hint names four dimensions so a first-time user does not write two words.
- Textarea as today (5 rows, `text-base`), with a mono character count `141 of 4,000` under it at the left. The API minimum is 10 characters; below it the error is `Error: write at least a few words before continuing`.
- Primary button changes from `Turn into criteria` to `Read the thesis`, pending label `Reading the thesis`. The button names what happens; the result on the next screen is a read-back, so the verb matches (the old label stays valid in `app-microcopy-v2.md` §2 until that doc is updated; see §8).
- Status line: `No credits are spent at this step`. This replaces `Nothing is searched at this step`, which is true but leaves the cost question open. The read uses the language model only.
- `⌘ Enter` submits. Shown as a keycap beside the button from `sm` up.

### 2.3 Starting points

Three chips under the textarea, labelled `Start from`.

**With a profile** (E is on main as a design; the row "Screenings · step 1 Thesis" in E §2 is the contract). The textarea starts with the draft from `GET /profile/defaults`, with E's `ProfileNote` and `Clear`. The chips are E's variations of the user's own thesis: `Your default thesis`, `Same, any size`, `Same, in {next geography}`. Each chip replaces the text; none submits.

**Without a profile** (today, and any workspace that skipped onboarding). Three full-sentence examples, each covering at least four dimensions, shown as two-line buttons rather than noun chips:

| Chip title | Text it inserts |
| --- | --- |
| `Warehousing software, India` | `Privately held Indian warehousing and supply-chain software companies that serve enterprise customers and show recent expansion` |
| `Cold chain, India, growing` | `Indian cold chain technology companies, privately held, 50 to 500 people, founded after 2015, with headcount growing over the last year` |
| `Regional 3PL operators` | `Third-party logistics operators headquartered in India or South-East Asia with fewer than 1,000 people, serving manufacturers, not yet acquired` |

The bare `Cold chain technology` example is removed. It taught the thin thesis.

### 2.4 The rough read (while typing)

A right-hand panel with the eight dimensions as a fixed list. Each line shows a filled square and the matched words when the text states the dimension, or an open square and `not stated`.

- **It is rules, in the browser, and says so.** Heading meta: `Rough read while you type. The full read happens when you continue`. No model call, no network call, no cost.
- Rules, one small lexicon file (`lib/discover/rough-read.ts`): country and region names (the list in `pipelines/discover/countries.py`, exported to a JSON the web imports); ownership words (`private`, `privately held`, `public`, `listed`, `acquired`, `family-owned`, `bootstrapped`); customer words (`enterprise`, `SMB`, `B2B`, `B2C`, `government`, `manufacturers`, `retailers`, `D2C`); size (a number followed by `people`, `employees`, `staff`, `headcount`, or `revenue` with a currency); stage (`seed`, `pre-seed`, `series a` to `series f`, `bootstrapped`, `venture-backed`, `pre-revenue`); growth (`growing`, `expansion`, `hiring`, `expanding`, `raised`, `new facility`); founded (a four-digit year 1950 to this year near `founded`, `since`, `after`, `before`, `started`). Sector and activity is whatever content words remain after the other seven are removed and stop words dropped; it counts as stated when at least one remains.
- The read updates 300ms after the last keystroke. A line that changes from `not stated` to stated gets the C §1.1 `highlight` tint once; nothing else moves.
- Footer: `{n} of 8 stated. The rest are suggested on the next step, never applied for you`.
- It never blocks submit and never claims to be the criteria. When the model's read later disagrees (it will, sometimes), the sheet in step 2 is the authority and the rough read is gone from the screen.
- Mobile: the panel collapses to a single line under the textarea: `Stated: geography, ownership, sector, customers, growth · 5 of 8`, with the unstated ones in muted ink. This is a mono meta line, so the middle dot is allowed by the copy rules.

### 2.5 The read-back (on submit)

When `POST /theses` returns, the page moves to step 2 and the thesis card at the top stops being a grey summary and becomes the read-back:

```
 Thesis                                                                              [ Edit thesis ]
 Privately held Indian warehousing and supply-chain software companies that serve enterprise
 ‾‾‾‾‾‾‾‾‾‾‾‾‾‾ ‾‾‾‾‾‾ ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾                      ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾
 customers and show recent expansion
 ‾‾‾‾‾‾‾‾‾          ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾
 5 criteria read from 5 phrases · 1 phrase dropped  [Why]
```

- Each underlined span is a `thesis_quote` the extraction already produces and already verifies against the text (`extraction/criteria.py`, `span_in`). Today the quote is thrown away after the check. Storing and returning it is backend chunk B1.
- Hovering or focusing a span highlights its criterion row in the sheet, and the reverse. Keyboard: each span is a button with `aria-describedby` pointing to the row.
- `1 phrase dropped` opens a popover listing `dropped` items with the reason in plain words (`The phrase was not found in your text, so it was not kept` for `quote not found in source text`; `Said twice` for `duplicate`). This data is already stored in `criteria_snapshot.dropped`.
- When no quote exists (older theses, user-added rows), the card shows the plain text with no underlines and no count line. No fake spans.

---

## 3. Step 2: the brief sheet

### 3.1 Desktop layout

Content width follows B §2.1 (fluid, capped). Main column plus a 352px rail from `xl`; from `lg` to `xl` the rail is 304px; below `lg` see §6.

```
 Discover                                                                                  [ New thesis ]
 Cold chain technology
 1 Thesis ─── 2 Criteria ─── 3 Shortlist

 ┌ Thesis ───────────────────────────────────────────────────────────────────────── [ Edit thesis ] ┐
 │ Cold chain technology                                                                            │
 │ ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾                                                                            │
 │ 1 criterion read from 1 phrase                                                                   │
 └──────────────────────────────────────────────────────────────────────────────────────────────────┘

 ┌ ! Nothing here can be scored yet ────────────────────────────────────────────────────────────────┐
 │ The only criterion is read from evidence, and screening does not read evidence. Every company    │
 │ would show Fit unavailable. Accept one suggestion that uses a company record to get a fit score. │
 └──────────────────────────────────────────────────────────────────────────────────────────────────┘

 Criteria   0 must-have · 1 preference · 7 suggested              ┌ What this search will do ─────────┐
 ───────────────────────────────────────────────────────────────  │ Updated for your last edit        │
 Ranked by    companies whose description matches                 │                                   │
              [ cold chain technology ]                           │ Plan                              │
              Natural-language ranking · no coverage limit        │ 1 Rank by description     6.5 cr  │
 ───────────────────────────────────────────────────────────────  │   company search · top 50         │
 Sector and   ▫ Mentions [ cold chain technology ]     Preference │ 2 Remove duplicates and           │
 activity       ╱╱ Read from evidence · not scored at screening   │   verified must-have failures     │
                                                                  │   rules · free                    │
              ┄ Suggested, not in your thesis ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  │ 3 Enrich the top 15      30.0 cr  │
              ▫ Industry is one of [ Transportation, Logistics,   │   company enrich · funding,       │
                Supply Chain and Storage ] [ Food and Beverage    │   headcount, hiring               │
                Services ]                             [ Accept ] │   then job search         2.3 cr  │
                Company record · basic_info.industries            │ 4 Re-check must-haves, rank       │
                Filled for nearly every company                   │   rules · free                    │
 ───────────────────────────────────────────────────────────────  │ 5 Explain each company            │
 Geography    ┄ Suggested, not in your thesis ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  │   language model · no credits     │
              ▫ Headquartered in [ India ]             [ Accept ] │                                   │
                From your profile · Search filter if must-have    │ Pool                              │
                Filled for nearly every company                   │ No count for this search          │
 ───────────────────────────────────────────────────────────────  │ It ranks by description, and the  │
 Ownership    ┄ Suggested, not in your thesis ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  │ data source returns no total for  │
              ▫ Is [ privately held ]                  [ Accept ] │ ranked searches. It reads the top │
                Company record · basic_info.company_type          │ 50.                               │
                Known for 58% of companies in India  Measured     │                                   │
                22 Nov 2026                                       │ Cost                              │
 ───────────────────────────────────────────────────────────────  │ About 39 credits of a 60 budget   │
 Customer     ┄ Suggested, not in your thesis ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  │ ▮▮▮▮▮▮▮▮▮▮▮▮▮▯▯▯▯▯▯▯              │
 type         ▫ Serves [ food and pharma distributors ] [ Accept ]│ search 6.5 · enrich 30 · jobs 2.3 │
                ╱╱ Read from evidence · not scored at screening   │                                   │
 ───────────────────────────────────────────────────────────────  │ Preview                           │
 Size         ▫ Team of [ 50 ] to [ 500 ] people       [ Accept ] │ [ Preview 5 matches · 0.15 cr ]   │
              …                                                   │ A small live search. Charged to   │
 Stage        ▫ Last round is one of [ seed ] [ series A ] …      │ this screening.                   │
 Growth       ▫ Headcount up at least [ 10% ] in 12 months …      │                                   │
 Founded      ▫ Founded in or after [ 2015 ]           [ Accept ] │ How a company is treated          │
 ───────────────────────────────────────────────────────────────  │ (diagram, §4.5)                   │
 [ + Add a criterion ]                                            │                                   │
                                                                  │ [ Run search · about 39 credits ] │
                                                                  └───────────────────────────────────┘
```

### 3.2 Anatomy of the sheet

One panel, hairline rows, no header band and no column headers. Left gutter 128px holds the dimension name (`text-sm`, secondary ink), so the eight names form one aligned column down the page, the way Dealroom's profile lays out Ownership, Headcount and Funding. This is the density lesson: label column, value column, meta line.

**Row zero, `Ranked by`.** The activity query (`criteria_snapshot.activity_query`) is the thing the natural-language search ranks on, and today it is invisible. It gets the first row, as an editable token. Meta: `Natural-language ranking · no coverage limit`. If the account falls back to filter-only search, the run says so (it already records the note); this row does not predict it.

**Dimension rows, in fixed order:** Geography, Ownership, Sector and activity, Customer type, Size, Stage, Growth signals, Founded. `Other` appears ninth only when a criterion with `dimension = other` exists. For a thin thesis the order is adjusted by one rule: dimensions that hold a stated criterion come first, in the fixed order; the rest follow in the fixed order. So "Cold chain technology" opens on its own row, not on an empty Geography.

Each dimension row contains, in order:

1. **Stated and accepted criteria** (0 or more), each a criterion line (§3.3).
2. **One suggestion** (0 or 1), under a dashed rule labelled `Suggested, not in your thesis` (§3.5).
3. If neither: the line `Any. Not part of this search` in muted ink with a quiet `Add` button. Never a blank row.

Heading meta, right of `Criteria`: `{m} must-have · {p} preference · {s} suggested` in mono, replacing `Edit before searching. Nothing runs yet`. That sentence moves to the rail's first line in a truer form (§4.1).

### 3.3 A criterion line

```
 ▪ Headquartered in [ India ]                              [ Must have | Preference ]   ×
   [▤ Crustdata · locations.country]  Search filter · companies elsewhere are never returned
   Filled for nearly every company
```

- **Mark.** Filled 8px square for must-have, open for preference, as `design-direction.md` §11.4 sets. It sits at the start of a sentence, not beside an input, so it stops reading as a checkbox. It is `aria-hidden`; the kind is carried by the switch.
- **Sentence.** A fixed lead-in chosen by dimension and operator, then one or more tokens. The lead-in is not editable text; the tokens are. Templates:

| Dimension | Operator | Sentence |
| --- | --- | --- |
| Geography | `eq`, `in` | `Headquartered in [India] [Singapore] +` |
| Ownership | `eq`, `in` | `Is [privately held]` |
| Sector and activity | `in` (mapped) | `Industry is one of [Transportation, Logistics…] +` |
| Sector and activity | `contains_any` | `Mentions [cold chain] [reefer] +` |
| Customer type | `contains_any` | `Serves [enterprise] +` |
| Size | `between`, `gte`, `lte` | `Team of [50] to [500] people`, `Team of at least [50] people`, `Team of at most [500] people` |
| Stage | `in` | `Last round is one of [seed] [series A] +` |
| Growth signals | `gte` | `Headcount up at least [10%] in [12 months]` |
| Founded | `gte`, `lte`, `between` | `Founded in or after [2015]`, `Founded in or before [2020]`, `Founded between [2015] and [2020]` |
| Other | any | `{label}: {operator words} [value]` (today's wording, kept as the fallback) |

- **Tokens.** A token looks like text with a 1px bottom border in `line-strong` and 2px horizontal padding; on hover the surface steps to `surface-raised`; on focus it gets the standard focus ring. Clicking opens a popover editor anchored to the token:
  - categorical fields (country, industry, company type, round type): a combobox backed by the free autocomplete endpoint through `GET /theses/values` (§7.5), so the user picks a stored value and the filter can never silently match nothing. Free text that resolves to no stored value is kept but flips the line to `Read from evidence` with the reason `"{value}" is not a value the data source stores`.
  - numbers and years: a number field with stepper, `inputmode="numeric"`.
  - free phrases: a text field; Enter commits, Escape cancels.
  - `+` adds a value to a list; Backspace on an empty new token removes it. A list token has a small `×` on hover and focus.
- **The lead-in is a menu.** Clicking the lead-in words (`Team of`, `Founded in or after`) opens the list of operators valid for that dimension, each written as its sentence. This replaces the raw `Select` with seven operators, most of which are nonsense for a given dimension.
- **Kind switch.** A two-segment control `Must have | Preference`, 28px tall, on the same line at the right. It replaces the up and down arrow buttons and the Weight column. Tooltip on `Must have`: `Counts double. A company is removed only when a record shows it fails`. Tooltip on `Preference`: `Counts once. Never removes a company`. The weight numbers appear there and in the rail diagram, nowhere else.
- **Remove.** A quiet `×` icon button, visible on row hover and always visible on touch and on keyboard focus.
- **Label.** The free-text label input is gone from the default view. The label sent to the API is composed from the sentence (`Headquartered in India`). `Rename` in the row's overflow menu opens a text field for users who want their own wording in the shortlist.

### 3.4 The assessment line

Under each criterion, one or two lines of `text-xs` that answer: how is this checked, from what, and how often is the data there. This is the source line applied to a criterion.

Four modes. They are not invented for the UI; they are the four branches of `build_filters` and `rule_criterion` in `pipelines/discover/criteria.py`.

| Mode | When (code) | Chip and sentence |
| --- | --- | --- |
| `filter` | must-have, mapped, field in `RELIABLE_FILTER_FIELDS` | `[▤ Crustdata · {field}]` `Search filter · companies that do not match are never returned` |
| `filter_keep_unknown` | must-have, mapped, field not reliable | `[▤ Crustdata · {field}]` `Search filter that keeps blanks · a company with no value stays in and shows Unknown` |
| `record_score` | preference, mapped | `[▤ Crustdata · {field}]` `Scored from the company record · never removes a company` and, for `headcount.*` and `funding.*` fields, `Read for the top 15 after enrichment; Unknown for the rest` |
| `evidence` | no mapping, or the value did not resolve | hatched chip `╱╱ Read from evidence` `Not scored at screening. Checked when you open a case` |

The third line is coverage:

- Measured: `Known for 58% of companies in India` then mono `Measured 22 Nov 2026`. The number is `1 − null share` from a Crustdata `is_null` count (§7.4). The one figure that exists today is this one: `basic_info.company_type` is empty on about 1.38M of 3.3M Indian rows, so ownership is known for 58%. It is recorded in `criteria.py` and was checked live on 22 November 2026.
- Reliable fields (`locations.country`, `headcount.largest_headcount_country`, `basic_info.industries`, `taxonomy.professional_network_industry`): `Filled for nearly every company`, with the tooltip `On the list of fields DealProof treats as reliably filled. Not a measured percentage`. No number is shown until one is measured.
- Not yet measured: `Coverage not measured`, muted. Never a guessed percentage. The user's example "funding stage is known for ~60% of Indian companies" becomes real only after chunk B3 runs the count; until then the line reads `Coverage not measured`.
- Scope of the figure follows the sheet: if a geography criterion is present (stated or accepted), coverage is for that country; otherwise `all companies`.
- Evidence mode has no coverage line. There is no field to measure.

Changing a criterion's kind changes its mode, and the sentence updates in place (must-have on `locations.country` reads `Search filter`; flipped to preference it reads `Scored from the company record`). This is the single most useful thing the row teaches.

### 3.5 Suggestions

Every dimension with no stated criterion shows one suggestion. It is visibly not applied:

- A dashed top rule with the inline label `Suggested, not in your thesis`.
- The sentence in secondary ink with an open square, tokens not yet editable.
- An `Accept` button (default variant, `sm`) at the right, and a quiet `Dismiss` in the overflow.
- One line of basis in muted ink, one of three:
  - `From your profile` (E's default thesis fields; same wording E uses).
  - `A common default` (a fixed rule, §7.2).
  - `Suggested by the model from your thesis` (Haiku).
- The assessment line it would have, in the conditional: `Would be a search filter if must-have`.

Rules:

1. **Never auto-applied.** A suggestion is not sent in `PUT /criteria`, is not in the plan, the count, the cost or the preview until accepted.
2. **Accept adds it as a preference.** Always. The user promotes it to must-have with the switch. A suggestion can therefore never remove a company without a second deliberate act. Exception: none. Profile geography and ownership, which E starts as must-haves in the default thesis, still arrive here as preferences because this thesis's text did not state them.
3. **Accepted rows are ordinary rows** with `origin = "suggestion"` and a quiet `Suggested` word tag beside the kind switch, so a later reader of the frozen snapshot can tell stated from suggested. The tag has a tooltip: `Not in the thesis text. Accepted by {user} on {date}`.
4. **Dismiss** collapses the suggestion to `Any. Not part of this search` with an `Undo` for the session. Dismissed suggestions are remembered per thesis (`localStorage`, try/catch) and not re-offered on reload; the API does not need to know.
5. **`Accept all`** is not offered. Seven one-click accepts are a deliberate cost: each is a decision about what the search means.
6. Suggestions for a dimension disappear when the user adds their own criterion to it.
7. Suggestion text values are resolved to stored values before they are shown (industry, country, company type, round type), so accepting never produces an unresolved filter.

Loading: suggestions arrive after the sheet renders. Until they do, each empty dimension shows `Any. Not part of this search` and the heading meta reads `Looking for suggestions`. When they arrive, they land per C §1.1 (event: the response). If the request fails, the heading meta reads `Suggestions unavailable` with `Try again`, and the sheet is fully usable.

### 3.6 Thin and empty states

| State | What the sheet shows |
| --- | --- |
| **One criterion, read from evidence** ("Cold chain technology") | The notice in §3.1: title `Nothing here can be scored yet`, body `The only criterion is read from evidence, and screening does not read evidence. Every company would show Fit unavailable. Accept one suggestion that uses a company record to get a fit score.` The first suggestion that maps to a field is scrolled into view on first render only if it is below the fold. `Run search` stays enabled: the search still finds and ranks 50 companies by description, and that is a legitimate thing to want |
| **Criteria exist, none can be scored at screening** | Same notice, `None of these can be scored yet` |
| **Some scorable** | No notice. Heading meta adds `{k} of {n} can be scored at screening` |
| **No must-haves** | No empty group and no `No must-haves` sentence. The rail's diagram shows the gate with `No must-haves. No company will be removed` (§4.5) |
| **Zero criteria** (extraction returned none, or the user removed all) | Notice `Add at least one criterion, or accept a suggestion`, `Run search` disabled. The `Ranked by` row alone is not enough to start, because the API rejects a thesis with no criteria |
| **A must-have whose value did not resolve** | The line flips to `Read from evidence` with `"{value}" is not a value the data source stores. Pick one from the list to make this a search filter`, and the token gets the `aria-invalid` treatment. The run would otherwise skip the filter silently (today it only notes it afterwards) |
| **Two must-haves that cannot both hold** (for example founded after 2020 and founded before 2015) | Not detected in v1. The count, when one is run, returns 0 and the Pool section says `0 companies pass these filters. Loosen a must-have` |

### 3.7 Add a criterion

`Add a criterion` at the foot opens a small menu of the eight dimensions plus `Something else`. Choosing one inserts that dimension's default sentence with an empty first token focused and its editor open. `Something else` inserts an `Other` row with the free-text fallback. Each dimension row with content also has a quiet `+` at its right edge that adds a second criterion to that dimension.

---

## 4. The search plan rail

A sticky panel (`top` under the page header, max height the viewport, own scroll). Title `What this search will do`. Every figure in it comes from `POST /theses/{id}/plan` (§7.1), recomputed 600ms after the last edit to the sheet. No figure is computed in the browser, so the rail cannot disagree with the run.

### 4.1 Status line

Under the title, one line:

- Idle: `Nothing has run. No credits spent` or, once a preview or count has been run, `Nothing has run. {x} credits spent on previews`.
- Recomputing: `Updating the plan`. Static text; no spinner (C §3 rule 3 allows one loop, and this is not it).
- Failed: `The plan could not be worked out. The search can still run` with `Try again`. `Run search` falls back to the label `Run search` with no figure and the caption `Budget 60 credits`.

### 4.2 Plan

An ordered list. It is numbered because it is a real sequence, the same five steps `step_specs` registers, in the words the run panel uses so the list the user reads before the run is the list they watch during it.

```
 Plan
 1  Find companies                                   at most 6.5 cr
    Crustdata company search, ranked by description, top 50
    Filters sent: none
 2  Remove duplicates and must-have failures                   free
    Rules. Only a recorded failure removes a company
 3  Enrich the top 15                               at most 32.3 cr
    Crustdata company enrich: funding, headcount, hiring
    Crustdata job search: 5 dated postings per company
 4  Re-check must-haves and rank by fit                        free
    Rules
 5  Explain why each company is on the shortlist       no credits
    Language model. Billed in dollars, shown after the run
```

- Step 1 lists the real filter set: `Filters sent: locations.country = India` and, for unknown-inclusive ones, `basic_info.company_type = Privately Held, or blank`. Field paths in mono. This is the "which endpoints, in what order" requirement, and it is also the first time the user can see that a preference is not a filter.
- A conditional sub-line appears when it can happen: `If fewer than 15 come back: one wider search without the blank-keeping filters, top 25, at most {x} cr`. It appears only when the plan has soft filters, because that is the only case the code widens.
- A free resolve step is folded into step 1 as `Values checked against the data source's lists first. Free`, shown only when at least one criterion needs resolution.
- Each priced step shows `at most`, because Crustdata bills per result returned and the plan assumes full pages.

### 4.3 Pool

The estimated result count. The research answer, stated plainly:

- **Crustdata has no count-only or `limit: 0` option that we could find.** `get_schema` for `company_search` (read 22 November 2026) lists `filters, search, cursor, limit, sorts, fields` and nothing else. `docs/crustdata-contextcon-notes.md` mentions an "example person search count" at 0.03 credits, which is a one-result search read for its total, not a separate endpoint.
- **A filter-only search returns `total_count`.** So a count costs one result: `limit: 1`, `fields: ["crustdata_company_id"]`, about 0.03 credits, plus the filter-side premium if a filter touches `taxonomy` (0.1) or `headcount`/`funding` (0.2). At most 0.33 credits.
- **A ranked (natural-language) search returns `total_count: null`.** The plan's External APIs section says so and `get_schema` confirms it. So the count can only describe the companies that pass the filters, before ranking by description. It cannot count "cold chain technology companies".

Therefore three states:

| State | Copy |
| --- | --- |
| No filters in the plan (the thin thesis) | `No count for this search` / `It ranks companies by description, and the data source returns no total for ranked searches. It reads the top 50.` No button |
| Filters present, not counted | `{n} filters narrow the pool` / button `Count the pool · 0.03 cr` / `Counts companies that pass the filters, before ranking by description` |
| Counted | Mono figure (for example `212,480`; illustrative, not a measured number) with label `companies pass the filters` / `The search ranks these by description and reads the top 50` / mono `Counted 22 Nov 2026, 14:02 · 0.03 cr` / `Count again` appears only after the filters change, with the old figure struck through per C's "superseded stays readable" |

The count is never run automatically. It is cheap, but the product's rule is that nothing is spent without a click, and D §1.10 holds the same line for starting a run.

Whether `total_count` is populated with `limit: 1` and a single projected field has not been verified with a live call (no API calls were made for this design). Chunk B3 starts with that one call. If it returns null, the Pool section ships with only the first state and this section's button is dropped; no estimate is substituted.

### 4.4 Cost

```
 Cost
 About 39 credits of a 60 budget
 ▮▮▮▮▮▮▮▮▮▮▮▮▮▯▯▯▯▯▯▯
 search 6.5 · enrich 30.0 · hiring 2.3
 The run stops spending at 60 and says what it skipped
```

- The meter is the cost meter from C §2.5 in its pre-run state: the estimate is drawn hatched (not done), the budget is the track. If a range exists, the low end is hatched solid and the low-to-high span is a lighter hatch.
- Headline: `About {n} credits` when low and high round to the same integer, else `{low} to {high} credits`, then `of a {budget} budget`.
- The breakdown is a mono meta line (middle dots allowed).
- When `high > budget`: `May reach the budget. Enrichment is cut first, and those companies show Not checked`. That is what `enrich_step` does today.
- Worked figures from the constants in `steps.py` (prices on this key, 22 November 2026):

| Thesis | Search | Enrich | Hiring | Total |
| --- | --- | --- | --- | --- |
| Cold chain technology, as extracted | 50 × 0.13 = 6.5 | 15 × 2 = 30 | 15 × 5 × 0.03 = 2.25 | about 39 |
| Plus `India` as must-have (reliable, no premium) | 6.5 | 30 | 2.25 | about 39 |
| Plus `Last round is seed or series A` as must-have (soft, funding filter +0.2) | 50 × 0.33 = 16.5, widen 25 × 0.33 = 8.25 | 30 | 2.25 | 49 to 57 |

- Model cost is not in credits. One line under the meter: `Language model use is billed separately and shown on the run`. No dollar estimate before the run; there is no cheap honest one.

### 4.5 How a company is treated

A small static diagram, the visual explanation of must-have and preference. It is drawn from this thesis's own rows, not a generic legend.

```
 How a company is treated

 ▪ Must have · counts double
   Headquartered in India
   ├ record says India ........ stays, counts toward fit
   ├ record says elsewhere .... removed, with the record shown
   └ no record ................ stays, shown as Unknown

 ▫ Preference · counts once
   Team of 50 to 500 people
   ├ met ...................... raises fit
   ├ not met .................. lowers fit
   └ no record ................ leaves fit alone, lowers the assessable share

 Fit 82 · 70% of criteria assessable
 ▮▮▮▮▯▮▮╱╱╱
```

- The three outcomes per kind are the tri-state gate (`pass | fail | unknown`). The marks at the left of each outcome are the product's existing result marks, so the diagram teaches the criteria strip the user will see on every shortlist row.
- It uses the first must-have and the first preference on the sheet as its examples. With no must-have, the first block reads `▪ Must have · none set` / `No company will be removed`.
- The strip at the bottom is the real `CriteriaStrip` component in an illustrative state, labelled `Example` in mono. It is the only place on these steps that shows a made-up number, and it is tagged as one.
- Collapsed by default below `xl` height of 900px, behind `How a company is treated` as a disclosure; open by default otherwise, and its open state is remembered (`localStorage`).

### 4.6 Preview matches

Opt-in. A button `Preview 5 matches · {x} cr`, where `x` comes from the plan (`preview.credits_max`, 0.15 for a filter-free thesis, up to 1.65 with premium filters).

- Caption before: `A small live search with these criteria. Charged to this screening`.
- On click the button reads `Searching` and is disabled; no spinner. On return the list lands (C: stagger 40ms, five items):

```
 Preview                                    0.15 cr · 14:02
 Example Coldworks Pvt Ltd Mumbai, India
 Temperature-controlled warehousing and distribution
 Example Reefer Systems    Gurugram, India
 Cold chain monitoring for food retail
 …3 more
 The top 5 of the same search the run makes. The run reads 50
 and enriches 15. Nothing here is scored yet.
 [ Preview again · 0.15 cr ]   appears only after an edit
```

- Each row: name, HQ from `locations`, one line of `basic_info.description` truncated to one line, and the source chip `[▤ Crustdata · as of {date}]` on the group, not per row. No fit, no criteria strip: the preview does not gate or score, and saying so prevents a preview row being read as a shortlist row. (The company names in this mock are invented for the layout; the built panel shows only what the API returns.)
- A preview is stale as soon as the sheet changes. Stale previews stay visible with the heading meta `For the criteria before your last edit` and muted ink.
- Empty result: `No companies came back. Loosen a must-have or change the description` and the charge line still shows what was billed (usually 0).
- Spend is real: the rail's status line and the Cost section's caption update to `{x} credits spent on previews`, and the run's budget is unaffected (preview spend is recorded on the discovery run's ledger, outside the run's own 60-credit budget; see §7.3). Server-side cap: 10 previews and 10 counts per thesis.
- Failure: `The preview did not run. Nothing was charged` or, when the provider billed before failing, `The preview failed after {x} credits were charged`. The ledger decides which.

### 4.7 The action

`Run search · about 39 credits` is the rail's last element and the page's only primary button. On `lg` and up it is pinned to the rail's foot. `Keep current shortlist` (when the thesis already has one) sits beside it as today. Pending labels unchanged: `Saving criteria`, `Starting the search`. D §1.10 takes over from the click.

---

## 5. Motion

C governs. Every animation below names its event; anything present at route load renders in its final state.

| Event | What moves | Tokens |
| --- | --- | --- |
| Rough read: a dimension becomes stated | That line's value gets the one-time tint | `highlight` 1200ms |
| `POST /theses` returns | Step header advances; the read-back underlines draw left to right, staggered, six at most; sheet rows land | `draw` 360ms, `stagger` 40ms, `rise` 8px |
| Suggestions response arrives | Suggestion lines fade in, in place, no rise (they are not established facts, so they do not "land") | `base` 200ms, opacity only |
| `Accept` clicked | The suggestion's dashed rule and label fade out; the same line becomes a criterion via `layout` (it does not travel; it is already in its row); the mark stays open | exit `fast` 140ms, `layout` 360ms |
| Kind switch flipped | The square fills or empties; the assessment sentence crossfades | `base` 200ms |
| Plan response differs from the last | Only the figures that changed get the tint; the meter redraws with `scaleX` | `highlight`, `draw` |
| Count returns | The figure appears in place with the tint. No count-up: a number that climbs on a timer is a progress claim the data did not make (C rule 8) | `base`, `highlight` |
| Preview returns | Rows land, staggered | `slow`, `stagger`, `rise` 8px |
| Criterion removed | Row fades out, list closes via `layout` | exit `fast`, `layout` 360ms |

Not animated: the rail on load; the diagram; hover on tokens beyond a colour step; the `Updating the plan` line. No loops anywhere on these two steps. Reduced motion: every entry becomes an instant state change; the tint becomes a 1px left border on the changed value that is removed after 1200ms.

---

## 6. Mobile (below `lg`)

The sheet is the page. The rail becomes a bottom bar plus a sheet.

```
 ┌───────────────────────────────────────┐
 │ Discover                              │
 │ Cold chain technology                 │
 │ 1 Thesis — 2 Criteria — 3 Shortlist   │
 ├───────────────────────────────────────┤
 │ Thesis                         [Edit] │
 │ Cold chain technology                 │
 │ ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾                 │
 ├───────────────────────────────────────┤
 │ ! Nothing here can be scored yet      │
 │ Accept one suggestion that uses a     │
 │ company record to get a fit score.    │
 ├───────────────────────────────────────┤
 │ Criteria                              │
 │ 0 must-have · 1 preference · 7 sugg.  │
 │                                       │
 │ Ranked by                             │
 │ companies whose description matches   │
 │ [ cold chain technology ]             │
 │ ───────────────────────────────────── │
 │ Sector and activity                   │
 │ ▫ Mentions [ cold chain technology ]  │
 │   [ Must have | Preference ]       ×  │
 │   ╱╱ Read from evidence               │
 │   Not scored at screening             │
 │ ┄ Suggested, not in your thesis ┄┄┄┄┄ │
 │ ▫ Industry is one of [ Transportation,│
 │   Logistics, Supply Chain and Storage]│
 │   Company record · filled for nearly  │
 │   every company                       │
 │   [ Accept ]                          │
 │ ───────────────────────────────────── │
 │ Geography                             │
 │ ┄ Suggested, not in your thesis ┄┄┄┄┄ │
 │ ▫ Headquartered in [ India ]          │
 │   From your profile        [ Accept ] │
 │ …                                     │
 │ [ + Add a criterion ]                 │
 │                                       │
 ├───────────────────────────────────────┤
 │ About 39 of 60 cr · 5 steps  [ Plan ] │  ← sticky bottom bar, 56px
 │ [ Run search · about 39 credits     ] │
 └───────────────────────────────────────┘
```

- The dimension name moves from a left gutter to a small heading above its rows.
- The kind switch drops to its own line under the sentence, full touch height (44px).
- Token editors open as bottom sheets, not popovers. The combobox gets the full sheet height.
- `Plan` opens the rail as a full-height sheet with the same sections in the same order: Plan, Pool, Cost, Preview, How a company is treated. `Run search` is repeated at its foot.
- The bottom bar's first line is a mono meta line and respects the safe-area inset.
- Step 1 on mobile: composer, the one-line rough read, starting points stacked full width, then the button full width.
- Nothing below 11px. The assessment line stays 12px.

---

## 7. Backend needs

All routes are under the existing `/theses` router, workspace-scoped, and follow the existing error envelope. `cr` values are floats in Crustdata credits. New response fields are additive.

### 7.0 Changes to existing shapes

`CriterionOut` gains:

```json
{
  "id": "c_01",
  "position": 0,
  "label": "Headquartered in India",
  "kind": "must",
  "dimension": "geography",
  "operator": "eq",
  "value": "India",
  "crustdata_filter": {"field": "locations.country", "type": "=", "value": "India"},
  "assessed_from_evidence": false,
  "edited": false,
  "origin": "thesis",
  "thesis_quote": "Indian"
}
```

- `origin`: `"thesis" | "suggestion" | "profile" | "user"`. `thesis` for extracted rows; `user` for rows added by hand; `suggestion` for accepted suggestions (set from `CriterionIn.origin`); `profile` is E's value and is unchanged.
- `thesis_quote`: the verified span, or null. Stored in a new nullable `criteria.thesis_quote` column; `from_extraction` already has it in hand.

`CriterionIn` gains optional `origin` (`"suggestion" | "user"`, default `user` for rows without an id) and optional `suggestion_basis` (`"profile" | "rule" | "model"`), both stored.

`ThesisOut` gains:

```json
{
  "activity_query": "cold chain technology",
  "dropped": [{"label": "Profitable", "reason": "quote not found in source text"}]
}
```

`PUT /theses/{id}/criteria` accepts an optional top-level `activity_query` (string, 3 to 300 characters) beside the list. To stay compatible, the body becomes either the bare list (today) or `{"criteria": [...], "activity_query": "..."}`.

### 7.1 `POST /theses/{thesis_id}/plan`

A dry run. Spends no credits: it uses only the free autocomplete endpoint for value resolution (bounded by the existing `MAX_AUTOCOMPLETE_CALLS`, cached) and local arithmetic. It takes the unsaved sheet so the rail can update while the user edits.

Request:

```json
{
  "activity_query": "cold chain technology",
  "criteria": [
    {"id": "c_01", "label": "Mentions cold chain technology", "kind": "preference",
     "dimension": "industry_activity", "operator": "contains_any",
     "value": ["cold chain technology"], "crustdata_filter": null},
    {"id": null, "label": "Headquartered in India", "kind": "must",
     "dimension": "geography", "operator": "eq", "value": "India",
     "crustdata_filter": {"field": "locations.country", "type": "=", "value": "India"}}
  ]
}
```

`criteria` items are `CriterionIn`. A row without an id carries a client `key` (string) that is echoed back so the rail and sheet can be joined.

Response `200`:

```json
{
  "plan_hash": "9f2c…",
  "natural_language": true,
  "criteria": [
    {
      "id": "c_01", "key": null,
      "mode": "evidence",
      "field": null,
      "resolution": {"status": "not_needed", "values": null, "unmatched": []},
      "scored_at_screening": false,
      "needs_enrichment": false,
      "coverage": null
    },
    {
      "id": null, "key": "new-1",
      "mode": "filter",
      "field": "locations.country",
      "resolution": {"status": "resolved", "values": ["India"], "unmatched": []},
      "scored_at_screening": true,
      "needs_enrichment": false,
      "coverage": {"status": "reliable", "known_pct": null, "scope": "all", "measured_at": null}
    }
  ],
  "assessable": {"scored_at_screening": 1, "total": 2},
  "steps": [
    {"key": "search", "label": "Find companies", "endpoint": "/company/search",
     "detail": "Ranked by description, top 50", "limit": 50,
     "filters_sent": [
       {"field": "locations.country", "type": "=", "value": ["India"], "keeps_blank": false}
     ],
     "credits_max": 6.5, "conditional": false},
    {"key": "search_widen", "label": "Wider search if fewer than 15 come back",
     "endpoint": "/company/search", "limit": 25, "filters_sent": [],
     "credits_max": 0.0, "conditional": true, "applies": false},
    {"key": "gate", "label": "Remove duplicates and must-have failures",
     "endpoint": null, "credits_max": 0.0, "conditional": false},
    {"key": "enrich", "label": "Enrich the top 15", "endpoint": "/company/enrich",
     "detail": "funding, headcount, hiring", "limit": 15, "credits_max": 30.0, "conditional": false},
    {"key": "jobs", "label": "Dated job postings, 5 per company", "endpoint": "/job/search",
     "limit": 75, "credits_max": 2.25, "conditional": false},
    {"key": "score", "label": "Re-check must-haves and rank by fit",
     "endpoint": null, "credits_max": 0.0, "conditional": false},
    {"key": "explain", "label": "Explain why each company is on the shortlist",
     "endpoint": "anthropic", "credits_max": 0.0, "conditional": false}
  ],
  "cost": {
    "credits_low": 38.75, "credits_high": 38.75, "budget": 60,
    "breakdown": {"search": 6.5, "enrich": 30.0, "jobs": 2.25},
    "may_reach_budget": false
  },
  "count": {"available": true, "reason": null, "credits": 0.03},
  "preview": {"limit": 5, "credits_max": 0.15},
  "spent": {"credits": 0.0, "previews_left": 10, "counts_left": 10}
}
```

- `mode`: `"filter" | "filter_keep_unknown" | "record_score" | "evidence"`, derived exactly as `build_filters` and `rule_criterion` decide, so the label cannot drift from the run. Implement by extracting the decision into one function both the plan and the run call.
- `scored_at_screening`: false for `evidence`; true otherwise. `needs_enrichment`: true when the field's group is `headcount`, `funding` or `hiring` (those are not in `SEARCH_FIELDS`, so only the top 15 get a value).
- `coverage.status`: `"measured" | "reliable" | "unmeasured"`. `known_pct` is an integer only when `measured`. `scope`: a resolved country name or `"all"`.
- `count.available` is false with `reason: "ranked_search_no_filters"` when the plan sends no filters.
- `cost.credits_low` assumes no conditional step; `credits_high` adds every conditional step that `applies`. Both use the same price function as `_Searcher.price()` and the `PRICE_*` constants, moved to a shared module.
- `plan_hash` is a hash of the normalised request. Preview and count echo it so the UI can tell stale results.
- Errors: `422` with the `InvalidCriteria` message for an unknown field or bad operand, same as `PUT /criteria`.

### 7.2 `POST /theses/{thesis_id}/suggest-criteria`

One suggestion per dimension that has no criterion. Three sources, tried in this order per dimension; the first that produces a value wins.

1. **Profile** (when E's profile exists): `thesis.geographies`, `thesis.ownership`, `thesis.size_*`, `thesis.sectors`. Basis `profile`.
2. **Model** (Haiku, `claude-haiku-5-5`, the client's default): one structured call with the thesis text and the list of empty dimensions, asking for at most one criterion per dimension that an analyst would usually want for this kind of company, and a one-line reason. Sector and customer type come from here. Industry, company-type and round-type values are then resolved through the free autocomplete; a value that does not resolve is dropped for filterable dimensions. Basis `model`. The prompt forbids company names and outside facts; it proposes criteria, not companies.
3. **Rule** (fixed defaults when the model gives nothing or is unavailable): ownership `Is privately held`; founded `Founded in or after {this year − 10}`; growth `Headcount up at least 10% in 12 months`; stage `Last round is one of seed, series A, series B`; size `Team of 11 to 500 people`. Geography and sector have no rule default: with no profile and no model answer, those rows show `Any`. Basis `rule`.

Cost: no Crustdata credits. The Haiku call is recorded on the draft discovery run's ledger like the extraction call. Results are cached by (thesis text, present dimensions, profile version).

Request:

```json
{"present_dimensions": ["industry_activity"]}
```

`present_dimensions` is what the sheet currently holds, so a dimension the user filled by hand is not suggested.

Response `200`:

```json
{
  "suggestions": [
    {
      "key": "sg_geography",
      "dimension": "geography",
      "label": "Headquartered in India",
      "operator": "eq",
      "value": "India",
      "crustdata_filter": {"field": "locations.country", "type": "=", "value": "India"},
      "basis": "profile",
      "reason": "Your default thesis is set to India",
      "mode_if_must": "filter",
      "mode_if_preference": "record_score",
      "coverage": {"status": "reliable", "known_pct": null, "scope": "all", "measured_at": null}
    },
    {
      "key": "sg_customer_type",
      "dimension": "customer_type",
      "label": "Serves food and pharma distributors",
      "operator": "contains_any",
      "value": ["food distributors", "pharma distributors"],
      "crustdata_filter": null,
      "basis": "model",
      "reason": "Cold chain buyers are usually food and pharmaceutical distributors",
      "mode_if_must": "evidence",
      "mode_if_preference": "evidence",
      "coverage": null
    }
  ],
  "model": {"used": true, "name": "claude-haiku-5-5"},
  "credits_used": 0.0
}
```

- A suggestion has no `kind`. The client adds it as `preference`.
- `reason` for `model` suggestions is model text. It is shown under the label `Suggested by the model from your thesis` and never styled as a fact; it carries no source chip. If that is judged too close to "AI memory" (PRD principle 1), drop `reason` for `model` and show only the basis label. This is open decision 2.
- When the model call fails: `200` with profile and rule suggestions only and `"model": {"used": false, "error": "unavailable"}`.

### 7.3 `POST /theses/{thesis_id}/preview`

A tiny paid search: the run's primary query at `limit: 5` with `fields: ["crustdata_company_id", "basic_info", "locations"]` (no premium response groups, so the base 0.03 per result plus any filter-side premium).

Request: the same body as `/plan`, plus the hash the user saw.

```json
{"activity_query": "cold chain technology", "criteria": [], "plan_hash": "9f2c…", "limit": 5}
```

`limit` is 3 to 5, default 5.

Response `200`:

```json
{
  "plan_hash": "9f2c…",
  "natural_language": true,
  "companies": [
    {
      "crustdata_company_id": 123456,
      "name": "…",
      "domain": "…",
      "headquarters": "Mumbai, Maharashtra, India",
      "country": "India",
      "description": "…",
      "year_founded": 1993,
      "employee_count_range": "1001-5000"
    }
  ],
  "returned": 5,
  "total_count": null,
  "source": {"id": "src_…", "provider": "crustdata", "endpoint": "/company/search",
             "retrieved_at": "2026-11-22T14:02:11Z"},
  "credits_used": 0.15,
  "from_cache": false,
  "spent": {"credits": 0.15, "previews_left": 9, "counts_left": 10},
  "notes": []
}
```

- Recorded through the same recorder and cache as the run, on the thesis's draft discovery run (created at `POST /theses`; if the latest run is finished, a new draft is created to hold it). It writes a `sources` row, so the preview has a real source chip.
- Not charged against the run's 60-credit budget: `create_run` sets that budget for the run's own steps. The discovery run's cost page shows preview and count spend as their own lines, `Before the run`.
- `total_count` is passed through; it is null for ranked searches.
- `notes` carries the existing fallback note when natural-language search is not enabled.
- `409` when a search is running on the thesis. `429` with `{"error": "preview_limit", "previews_left": 0}` after 10. `402`/`403` from the provider map to the existing error text.
- No gating, no scoring, no evidence rows. Preview companies are not candidates.

### 7.4 `POST /theses/{thesis_id}/count` and coverage

**Count.** Filter-only `company_search`, `limit: 1`, `fields: ["crustdata_company_id"]`, no `search` block, reading `total_count`. Same request body as `/plan`.

```json
{
  "plan_hash": "9f2c…",
  "total_count": 212480,
  "filters_counted": [
    {"field": "locations.country", "type": "=", "value": ["India"], "keeps_blank": false}
  ],
  "counted_at": "2026-11-22T14:02:40Z",
  "credits_used": 0.03,
  "spent": {"credits": 0.18, "previews_left": 9, "counts_left": 9}
}
```

`422` with `{"error": "no_filters"}` when the plan sends no filters. If the provider returns `total_count: null`, respond `200` with `"total_count": null` and `"reason": "provider_returned_no_total"`; the UI then shows the no-count state.

**Coverage.** A table `field_coverage(field, scope, known_count, total_count, measured_at)`, filled by a CLI command, not by user traffic: `python -m app.cli measure-coverage --scope India --scope all`. For each mapped field in `CRUSTDATA_FIELDS` and each scope it runs two counts (scope total; scope and `field is_null`) and stores `known = total − null`. Cost per field per scope: two one-result searches, 0.06 credits for base fields, up to 0.46 for `funding.*` and `headcount.*` filters. Seventeen fields, two scopes: under 10 credits. `/plan` and `/suggest-criteria` read the table; a missing row is `unmeasured`. Figures older than 30 days are still shown, with their date.

The one row that can be inserted without a call: `basic_info.company_type`, scope `India`, known 1.92M of 3.3M (58%), measured 22 November 2026, from the note in `criteria.py`.

### 7.5 `GET /theses/values?field={field}&q={text}`

A thin pass-through to the free autocomplete for the four categorical fields plus the two country fields (`RESOLVE_FIELDS`), so token editors offer stored values.

```json
{"field": "basic_info.industries", "q": "cold", "values": ["Transportation, Logistics, Supply Chain and Storage"], "credits_used": 0.0}
```

Debounced 250ms on the client, cached server-side, rate-limited per workspace (the endpoint is free but has a per-minute limit). `422` for a field outside the set.

### 7.6 What does not change

`POST /theses`, `POST /theses/{id}/search`, the step specs, the gate, the budget and the scoring policy. A run started from the new sheet freezes the same snapshot shape, with `origin` and `thesis_quote` riding along.

---

## 8. Copy

Sentence case, no exclamation marks, no trailing period on short strings. Additions and replacements to `app-microcopy-v2.md` §2:

| Place | Was | Now |
| --- | --- | --- |
| Step 1 hint | `Write it the way you would say it. DealProof separates the must-haves from the preferences, and you edit them before anything is searched.` | `Write it the way you would say it. Say where, what they do, who they sell to and how big.` |
| Step 1 button | `Turn into criteria` / `Reading the thesis` | `Read the thesis` / `Reading the thesis` |
| Step 1 status | `Nothing is searched at this step` | `No credits are spent at this step` |
| Step 1 chips label | `Examples` | `Start from` |
| Rough read title | new | `What DealProof can read from it` |
| Rough read meta | new | `Rough read while you type. The full read happens when you continue` |
| Rough read foot | new | `{n} of 8 stated. The rest are suggested on the next step, never applied for you` |
| Read-back count | new | `{n} criteria read from {m} phrases` · `{d} phrase dropped` |
| Step 2 meta | `Edit before searching. Nothing runs yet.` | `{m} must-have · {p} preference · {s} suggested` |
| Column headers | `Criterion`, `Condition`, `Weight`, `Assessed from` | removed |
| Suggestion label | new | `Suggested, not in your thesis` |
| Suggestion bases | new | `From your profile` · `A common default` · `Suggested by the model from your thesis` |
| Suggestion actions | new | `Accept` · `Dismiss` · `Undo` |
| Accepted tag | new | `Suggested` |
| Empty dimension | new | `Any. Not part of this search` |
| Modes | `Company record` / `Assessed from evidence` | `Search filter` · `Search filter that keeps blanks` · `Scored from the company record` · `Read from evidence` |
| Evidence sub-line | `No search field covers this; unknown until evidence is read` | `Not scored at screening. Checked when you open a case` |
| Coverage | new | `Known for {n}% of companies in {scope}` · `Filled for nearly every company` · `Coverage not measured` |
| Thin notice | new | `Nothing here can be scored yet` + body in §3.6 |
| Footer policy line | `Weight follows the kind under the scoring policy…` | removed; the kind switch tooltips and the diagram carry it |
| Rail title | new | `What this search will do` |
| Rail status | `Running the search spends credits against the run budget` | `Nothing has run. No credits spent` |
| Pool, no count | new | `No count for this search` |
| Pool button | new | `Count the pool · {x} cr` |
| Cost headline | new | `About {n} credits of a {budget} budget` |
| Preview button | new | `Preview 5 matches · {x} cr` |
| Preview foot | new | `The top 5 of the same search the run makes. The run reads 50 and enriches 15. Nothing here is scored yet.` |
| Primary action | `Run search` | `Run search · about {n} credits` |
| Add | `Add criterion` | `Add a criterion` |

Vocabulary: `credits` in sentences, `cr` only in mono figures. `Pool` is new and means the companies that pass the filters before ranking; it is used only in the rail. `Brief sheet` is this document's name for the layout and never appears in the UI.

---

## 9. Implementation chunks

Three backend chunks (Opus) and three frontend chunks (Fable). File ownership is exclusive within a wave. Frontend chunks can start against fixtures in `apps/api/app/api/fixtures.py` style mocks and the shapes in §7.

### Backend (Opus)

**B1. Provenance, activity query and the plan.** Lands first; F2 and F3 depend on its shapes.

- Owns: `apps/api/app/pipelines/discover/plan.py` (new), `apps/api/app/pipelines/discover/pricing.py` (new; `PRICE_*` and the per-result price function moved out of `steps.py`), `apps/api/app/pipelines/discover/criteria.py` (extract `assessment_mode()` used by both plan and run; keep `thesis_quote` in `from_extraction`), `apps/api/app/pipelines/discover/service.py`, `apps/api/app/pipelines/discover/steps.py` (import the moved constants only), `apps/api/app/api/theses.py`, `apps/api/app/api/theses_views.py`, `apps/api/app/api/schemas/theses.py`, `apps/api/app/db/models.py` plus one migration (`criteria.thesis_quote`, `criteria.origin`, `criteria.suggestion_basis`), tests under `apps/api/tests/` for the plan.
- Delivers: §7.0, §7.1, §7.5.
- Pinned tests: plan mode equals run behaviour for each of the four branches; plan cost equals the sum of `require_budget` calls a recorded run makes; `count.available` false without filters; a row whose value does not resolve reports `evidence`.

**B2. Suggestions.**

- Owns: `apps/api/app/extraction/suggest.py` (new), `apps/api/app/extraction/prompts.py` (one new prompt, bump `PROMPT_VERSION`), `apps/api/app/pipelines/discover/suggest.py` (new; profile and rule sources, resolution, ordering), route and schema additions in the two `theses` files after B1 merges.
- Delivers: §7.2.
- Pinned tests: no suggestion for a present dimension; unresolved categorical values dropped; model failure still returns rule suggestions; nothing is written to `criteria`.

**B3. Preview, count and coverage.**

- Owns: `apps/api/app/pipelines/discover/preview.py` (new), `apps/api/app/pipelines/discover/coverage.py` (new), `apps/api/app/cli.py` (the `measure-coverage` command), one migration (`field_coverage`), route and schema additions after B1.
- First task: one live `limit: 1` filter-only call to confirm `total_count` is populated (about 0.03 credits; needs the user's go-ahead as a live spend). If it is null, the count endpoint is not built and §4.3 ships in its first state only.
- Delivers: §7.3, §7.4. Seeds the measured ownership row.
- Pinned tests: preview writes a source and a ledger row and no candidates; caps enforced; preview spend is not deducted from the run budget; coverage `unmeasured` when no row.

### Frontend (Fable)

**F1. Thesis composer and read-back.** Independent of the backend except for `thesis_quote` (degrades to plain text without it).

- Owns: `apps/web/components/discover/thesis-form.tsx`, `apps/web/components/discover/rough-read.tsx` (new), `apps/web/lib/discover/rough-read.ts` (new) with its unit test, `apps/web/lib/discover/countries.json` (generated from `countries.py`), `apps/web/components/discover/thesis-readback.tsx` (new), the thesis card in `new-thesis.tsx` and `thesis-view.tsx`.
- Delivers: §2.

**F2. The brief sheet.** After B1's shapes are in the typed client.

- Owns: `apps/web/components/discover/criteria-editor.tsx` (becomes a thin container), `apps/web/components/discover/criteria/` (new: `dimension-row.tsx`, `criterion-line.tsx`, `criterion-sentence.ts` for the templates in §3.3, `token.tsx`, `token-editor.tsx`, `kind-switch.tsx`, `assessment-line.tsx`, `suggestion-line.tsx`, `thin-notice.tsx`), `apps/web/components/discover/adapt.ts`, `apps/web/lib/api/client.ts` additions for `/plan`, `/suggest-criteria`, `/values`.
- Delivers: §3. Holds the sheet state (rows, accepted and dismissed suggestions) and exposes it to F3 through one context or a lifted hook, `useCriteriaSheet`.

**F3. The search plan rail, mobile bar and gallery.** After F2's state hook exists.

- Owns: `apps/web/components/discover/plan/` (new: `search-plan-rail.tsx`, `plan-steps.tsx`, `pool-count.tsx`, `cost-range.tsx` wrapping the C §2.5 cost meter in its pre-run state, `preview-matches.tsx`, `gate-diagram.tsx`, `plan-bar.tsx` for mobile), the two-column layout in `new-thesis.tsx` and `thesis-view.tsx` (coordinate with F1 on these two files: F1 lands first, F3 edits only the wrapper), `apps/web/lib/api/client.ts` additions for `/preview` and `/count`, the `/design` gallery entries for every state in §3.6 and §4, and the `app-microcopy-v2.md` §2 update from §8.
- Delivers: §4, §5, §6.

### Order

```
 B1 ──┬── B2
      └── B3
 F1 (parallel with B1)
 F2 (after B1 shapes) ── F3
```

If time is short, cut in this order: the count (§4.3 ships as "no count" everywhere), measured coverage beyond the seeded row, the rough read. Do not cut: the assessment modes, the thin notice, the suggestions, the cost figure on the button.

---

## 10. Acceptance checks

1. The thesis "Cold chain technology" shows one stated criterion, seven suggestions or `Any` rows, the thin notice, and a rail with five steps and `About 39 credits of a 60 budget`. No blank table.
2. No suggestion appears in the request body of `PUT /criteria`, `/plan`, `/preview` or `/count` until `Accept` is clicked.
3. An accepted suggestion is a preference and is tagged `Suggested`.
4. Flipping a criterion's kind changes its assessment sentence, the plan's `Filters sent` line and, where prices differ, the cost.
5. No percentage appears anywhere without `Measured {date}` beside it.
6. Loading `/app/discover/[thesisId]` in the Criteria state fires no network call that spends credits. The network log shows `/plan` and `/suggest-criteria` only.
7. Every preview and count shows its charge after it returns, and the ledger for the discovery run lists it.
8. With `prefers-reduced-motion`, nothing animates and nothing is lost.
9. At 375px wide: no horizontal scroll, every token editor reachable, `Run search` visible without scrolling the sheet to its end.
10. Keyboard: Tab reaches every token, the kind switch, `Accept`, and the rail's buttons in reading order; every popover closes on Escape and returns focus to its token.

---

## 11. Open decisions

1. **Live spend to verify the count.** One 0.03-credit call in B3 decides whether §4.3's button exists. Default: make the call.
2. **Model reason text on suggestions.** Shown, labelled as the model's (default), or omitted so no unsourced sentence appears on the sheet.
3. **Accepting profile geography and ownership as preferences.** E starts them as must-haves in the default thesis. This design keeps every accepted suggestion a preference, for one rule with no exceptions. If the user wants profile must-haves honoured, rule 2 in §3.5 gains one exception and the suggestion line says `Must-have in your default thesis`.
4. **`Read the thesis` versus `Turn into criteria`.** A label change in a shipped flow. Default: change it, and update `app-microcopy-v2.md` in F3.
5. **Preview spend outside the run budget.** Default: outside, capped at 10 previews and 10 counts per thesis (worst case about 20 credits, typical under 2). The alternative is to reduce the run's budget by what previews spent, which makes the cost meter harder to read.
