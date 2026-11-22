# Iteration A: the home page is one real case file, read top to bottom

22 Nov 2026 · design proposal · docs only, no code changed

Lens: the home page stops describing DealProof and becomes the record of one real run. A judge scrolls from a real thesis to a real decision and can open any fact on the way.

Builds on `docs/design/design-direction.md` (tokens, status system, motion rules) and replaces its section 11.1 layout. Copy in `docs/content/home.md` needs a rewrite to match; the strings that change are listed in section 9.

The `unslop` skill set the direction and the pass order (unslop by Damir Sokolovsky, [@heydamir](https://x.com/heydamir), CC BY 4.0).

## 0. What is wrong with the page today

An audit of `apps/web/app/page.tsx` and `components/marketing/` against the unslop signs and the user's "gimmicky" complaint.

| Where | Problem |
| --- | --- |
| `hero-ledger.tsx` | Rows render as "Checking" and settle on a timer. Nothing is being checked. It is a fake loading state on an invented company, which is the exact thing the product says it never does |
| `steps.tsx` | Four tabs, each a mock of a different screen with different invented data. A judge has to click to see the product, and what they see is not connected from tab to tab |
| `sections.tsx` | Twelve sections, eleven of them entering with the same fade and rise. Motion on everything means motion reports nothing |
| `sections.tsx` | Six "Illustration, not a real company" labels. The page keeps apologising for its own content |
| `fit-readout.tsx` | The strip remounts to replay its entrance when scrolled to. Decoration |
| Whole page | Reads as a feature list: problem table, principles accordion, limits list, comparison table, audience table. Five tables of claims about the product, and no proof |
| Whole page | Could be re-skinned for any "AI analyst" product by swapping the nouns. It fails the template check |

The components in `components/dealproof/` are good and stay. What changes is what they are fed and how the page is organised around them.

## 1. Direction

- **Product.** DealProof finds companies that match an investment thesis, checks each claim about them against dated evidence, and says which deserve a closer look.
- **Character.** Exact, sober, quietly assured. Unchanged.
- **World.** The diligence file. The page is the file: a cover sheet, numbered exhibits, notes in the margin, a signature block left unsigned, and the bill at the back.
- **Moments.** Two, both real data. (1) The claim ledger of one real company, with every source one click away. (2) The sieve: every company the search returned drawn as one mark, so the judge sees how many were dropped and why.
- **Signature.** The source line, unchanged. New supporting detail for this page only: the **docket rail**, a spine down the left edge that names the exhibit being read and the credits the run had spent by that point.

One sentence for the judge to remember: *this page is not a demo of the product, it is an output of the product.*

### The three structural ideas

1. **One run, one file.** Every exhibit is the same thesis, the same shortlist, the same company. Nothing on the page is a mock. Where the run produced nothing (no financial inputs, no second assessment version, a check that was not run), the page shows that gap in the product's own hatched form. It does not substitute an illustration.
2. **The conclusion is withheld until the evidence has been read.** A case bar pins under the navigation once the company is opened. Its disposition slot is an empty dashed box until the judge reaches the assessment exhibit. The page makes the judge do what the product asks an analyst to do.
3. **The page shows its own bill.** The docket rail carries cumulative credits, and the last exhibit is the cost table for the run. A marketing page that ends with what it cost to produce is hard to mistake for a mock.

## 2. The narrative, exhibit by exhibit

The page has a cover and seven exhibits, then a short close. Exhibit numbers are mono, in the rail and at each exhibit head.

| # | Exhibit | Data | What the judge learns |
| --- | --- | --- | --- |
| Cover | Headline and docket | `meta.json` | This is a real run, on a date, at a cost |
| 1 | The thesis and how it was read | `discovery.json` → `text`, `criteria` | Plain words became editable must-haves and preferences |
| 2 | The shortlist | `discovery.json` → `shortlist`, `run` | N records came back, some were dropped for stated reasons, the rest are ranked with fit and assessable share |
| 3 | One company, identity first | `case.json` → `identity`, `profile` | Which entity this is and which keys proved it |
| 4 | The claim ledger | `case.json` → `claims`, `sources` | What the company's website says, what the record shows, and what stayed open |
| 5 | The assessment | `case.json` → `assessment`, `risks` | Five judgments kept apart, then one disposition with its reasons |
| 6 | The request, awaiting approval | `case.json` → `request_list`, `message` | The open claims became a document list and a draft. Nothing was sent |
| 7 | The other direction: investors | `investors.json` | Investors ranked by dated rounds in comparable companies |
| Close | The bill, the limits, the action | `case.json` → `cost`, `runs` | What the run cost by step, what DealProof is not, start your own |

### Cover

Left-aligned serif headline in two lines, no product window. Beside it the **docket**: a small ruled block in mono that states the run facts. The first screen ends on a hairline with "Exhibit 1" just visible below it, so the page invites a scroll.

On load, one entrance: headline and docket fade and rise 8px, 40ms apart. Nothing else on the page animates on load.

Clickable: "Read the file" scrolls to Exhibit 1. "Start a screening" goes to `/app`. Each docket line that names a source is a source chip.

### Exhibit 1: the thesis and how it was read

A two-sided ledger with a spine, the same shape as the claim ledger. Left: the thesis in the analyst's words, in serif, in quotation marks. Right: the criteria it became, grouped as must-have and preference, each with how it is assessed (company record, evidence, signal). The spine carries one mark per criterion: a filled square for must-have, an open square for preference.

Using the ledger shape here teaches the judge the grammar of the page before the stakes rise: words on the left, what DealProof made of them on the right.

Motion: none beyond the exhibit rule (section 4.2). The criteria are simply there. They were written before the judge arrived.

Clickable: each criterion expands to its weight and its `reason`. A quiet link, "Criteria are edited before anything runs", opens the criteria editor in `/app/discover`.

### Exhibit 2: the shortlist

Two parts.

**The sieve.** One small square per company the search returned, in a wrapped row. This is a unit chart, so the count is true by construction. Squares for excluded companies are hollow and grouped at the end under their real reason ("failed must-have: headquartered in India"). Squares for shortlisted companies are ink, in rank order. Hatched squares mark companies kept with an unknown must-have. Above it, one sentence in mono built from the same counts: "41 records · 9 removed for failing a must-have · 32 ranked".

When the sieve scrolls into view, the squares start in the order the search returned them, then the excluded ones go hollow and the rest move into rank order. One pass, 600ms in total, moved with Motion's `layout`. It explains a real transformation: returned order to ranked order.

**The table.** Dealroom's ranked-list-and-detail layout (the "Top investors" screenshot): a dense ranked list on the left at 13px, and a detail pane on the right for the selected row. The company verified in this run is selected by default and carries a mono tag, "Verified in this run".

Each list row: rank, name, one-line business, `Fit 78 · 64% of criteria assessable`, the compact criteria strip. The detail pane: business, location, headcount with its Estimate label, funding rounds as dated records, hiring as Signal, "Why it is here" from `card.reasons`, "Unknown" from `card.unknowns`, `last_updated`. Every fact ends in its source line.

Clickable: any list row swaps the detail pane (a 200ms crossfade of the pane content, no slide). Hovering a square in the sieve highlights its row and the reverse. "9 removed" opens the removed list with each failed criterion and its evidence. Strip cells are focusable and name their criterion.

### Exhibit 3: one company, identity first

A hairline runs from the selected shortlist row down the left edge into this exhibit's head. From here to the end of Exhibit 6 the **case bar** is pinned under the navigation.

The exhibit itself is the identity band at full size: the entity name, then the matching keys as a two-column table (key, value, source line): domain, legal name, registration number where reached, registered city, founded year. Under it the profile facts. If identity was unresolved in the run, the candidates are shown side by side and the rest of the file says "Waiting on identity", exactly as the app would.

Motion: the case bar slides in 8px with a fade as it pins, once. Nothing else.

Clickable: every key's source chip. The company's domain is shown as text with the source line, not as an outbound marketing link.

### Exhibit 4: the claim ledger

The main moment, at full content width.

Column heads change from the app's default. The claims in this run were read from the company's public website, so the left head is **"The company's website says"**, not "Seller said". The ledger component needs a prop for this (section 9).

Each row is revealed in a fixed order as it crosses the reading line (60% of the viewport height):

1. The claim, in the company's words, with its `stated_in` source chip (the page and URL it was read from).
2. The evidence chips on the right, one after another, 80ms apart.
3. The record statement.
4. The status mark on the spine, last, with the settle keyframe (200ms).

Evidence before verdict is the order the pipeline works in, so the sequence explains a rule. It is driven by scroll position, not by a timer, so a presenter can stop on any row. It plays once per row and does not replay on scrolling back. There is no "Checking" text, no pending ring and no spinner: before a row is revealed its spine cell is simply empty.

As rows settle, the status counts in the case bar update with a number tween. These are real counts of real rows the judge has just seen.

Rows that ended `cannot_verify` or `partially_corroborated` are expanded by default and end with "What would settle it" and the document name. Those lines reappear in Exhibit 6, and the page draws that link (section 4.6). A `not_checked` row keeps its hatch, its dashed border and its reason. If the run has any, the case bar shows "2 checks were not run" for the rest of the file.

Clickable: every source chip opens the evidence popover with the real quote, the URL, the reliability class in words and the retrieved-at time. Every row expands in place. The status filter toggles work, and Not checked cannot be filtered out.

### Exhibit 5: the assessment

The five-judgment panel at full size, fed by `assessment.judgments`. Shown in reading order, each in its own shape:

- Opportunity fit: the criteria strip and `Fit 78 · 64% of criteria assessable`.
- Evidence sufficiency: the count, the distribution bar, the named gaps.
- Business assessment: dated signals, each labelled Signal or Estimate.
- Financial assessment: almost certainly "Not assessed · no reliable financial inputs", hatched and dashed. It keeps its place so the absence is seen.
- Screening disposition: the stamp, its reasons, the claims it rests on.

Motion: the four judgments are drawn. The stamp alone settles (opacity and scale 0.96 to 1, 200ms) when the panel's lower half crosses the reading line, and at the same moment the dashed slot in the case bar receives the same stamp through a shared layout animation. This is the one place two things move together, because it is the one conclusion in the file.

Under the panel, one line in mono: "policy 1.0 · inputs hash 3f9c… · the same records under the same policy give the same assessment".

Clickable: "Rests on claims 2, 5, 6" scrolls back to those ledger rows and gives each the one-time changed-highlight (1200ms accent tint fade). Each gap in evidence sufficiency links to its claim the same way. The policy version links to `/app/policy`.

### Exhibit 6: the request, awaiting approval

Left: `request_list.items`, each document with its reason and the claim numbers it would settle. Right: `request_list.draft`, the real subject and body, read-only, marked "Drafted by DealProof". Below: the approval block in its real, unapproved state.

- Recipient: empty, with the line "DealProof does not suggest an address".
- Approver: "No named approver. Approval needs a signed-in person".
- The button is not rendered. In its place, a dashed box: **"Draft · not approved · not sent"**.
- A fixed sentence under it: "This request was drafted during the run and never sent. DealProof did not contact the company."

This is the unsigned signature block of the file. It is more convincing than a fake "Sent once" receipt, and it is true.

Motion: none on entry. Hovering or focusing a requested document draws a 1px accent underline on it and scrolls nothing. Clicking it jumps to the claim it would settle and highlights that row.

If `diff_from_previous` is present (the run produced a second version), a short "What changed in version 2" block follows, using `VersionDiff` and the changed-highlight. If it is null, this block is absent. The page never shows an invented diff.

### Exhibit 7: the other direction, investors

Sets off with one sentence: "The same company, seen as a business raising money." Then the ranked-list-and-detail layout again, so the judge already knows how to read it.

List row: rank, investor name, "4 comparable rounds · last in sector Aug 2026". No score figure in the row: `score` orders the list and is shown in the detail pane with `ranking_basis` beside it. Detail pane: the round axis (`components/investors/round-axis.tsx`), each comparable round as a dated mark with its source line, `why`, `unknowns`, possible duplicates flagged and not merged. Under the list, the fixed caveat: "This ranking describes past investments. It does not predict whether an investor will invest". The line "rounds read 61 · excluded 14" comes from `rounds_read` and `rounds_excluded`.

Motion: the pane crossfade on selection. Nothing else.

### Close

Three short blocks, no tables of claims about the product.

1. **What this file cost.** `CostReadout` with the by-step table from `cost.by_step`: credits and model usage per step, cached calls as "0 · cache", totals. One sentence above: "Everything on this page came from one run."
2. **What this file is not.** The six limits from the PRD as a two-column list, plus the footer scope line. No animation.
3. **Start your own.** One serif line, one primary button, one secondary: "Start a screening", "Open this case in the app".

The current problem table, principles accordion, comparison table and audience table are removed from the page. The principles move into the margin (section 4.7), each beside the exhibit that demonstrates it. The comparison and audience content can live on a separate `/about` page later; they are not what a judge needs in the first ninety seconds.

## 3. What is pinned

| Element | When | Content |
| --- | --- | --- |
| Navigation, 56px | Always | Wordmark, three anchors (The file, The ledger, The bill), Log in, Open app |
| Docket rail, 184px, left | From Exhibit 1 to the close, `lg` and up | Exhibit list with the current one in ink, and under it the cumulative credits and model cost at this point in the run |
| Case bar, 44px, under the navigation | From Exhibit 3 to the end of Exhibit 6 | Company name · Identity confirmed · Fit and assessable · status counts · disposition slot |
| Detail pane | Within Exhibits 2 and 7 only | Sticky beside its list while the list scrolls |

Nothing else is pinned. The page never takes over the scroll wheel: pinning is `position: sticky`, and reveals are triggered by `IntersectionObserver` against the reading line. The page is as long as its content and scrolls at the judge's speed.

### The docket rail

```
 Exhibits
 ─────────────
   Cover
 ● 1 Thesis
 │ 2 Shortlist
 │ 3 Identity
 │ 4 Claims
 │ 5 Assessment
 │ 6 Request
 │ 7 Investors
   The bill
 ─────────────
 Spent so far
 38 credits
 $0.07 model
 of 150 budget
```

- The figures are cumulative sums of `runs[].cost` and `cost.by_step` up to the step that produced the current exhibit. They tween (360ms, tabular figures) from the previous exhibit's real value to this one's when the exhibit changes. Scrolling up tweens them back down. This is the page's main number tween, and every value it passes through to is real.
- Credits and dollars are never added together.
- Each exhibit name is a link. The rail is a `nav` with `aria-current` on the active item.

Borrowed from the Dealroom tour's segmented progress strip and its "07 / 09" counter, turned vertical and given something true to say.

### The case bar

```
 ┌──────────────────────────────────────────────────────────────────────────────────────────┐
 │ <Company> Pvt Ltd   ✓ Identity confirmed   Fit 78 · 64% assessable   ●3 ◐1 ?2 ◌0   ┌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┐ │
 │                                                                                    ╎ Not yet read ╎ │
 └────────────────────────────────────────────────────────────────────────────────────└╌╌╌╌╌╌╌╌╌╌╌╌╌╌┘─┘
```

- Fit and assessable appear when Exhibit 3 is reached (they came from discovery). Status counts start at zero and rise as ledger rows settle. The disposition slot is dashed and reads "Not yet read" until Exhibit 5, then holds the stamp.
- Under reduced motion and without script the bar is complete from the start.
- Layout borrows the Dealroom company header: name and descriptors left, the figure group right-aligned. DealProof's figures are a fit with its assessable share and a count by status, not a valuation and a growth percentage.

## 4. Effects and components

Every effect below is listed with the reference it borrows from, what it reports, and the component it is built on. If a row cannot say what it reports, it is not built.

### 4.1 Typographic hero

- **What.** Newsreader 400 at 64px (`text-5xl`), left-aligned, two lines, `-0.02em`. No product window, no image. The docket block beside it in Plex Mono is the visual.
- **Borrowed from.** sarvam.ai: a short serif headline with a one-line eyebrow, large calm margins, an ink primary button. Not taken: its centred stack, gradient wash, pill buttons and logo marquee.
- **Why.** The first screen has to say "serious" before any data is read. Type on warm paper with a ruled block of dated facts does that. A window full of rows at the top competes with the headline and is too small to read from the back of a room.
- **Build.** `Hero` rewritten; no new dependency.

### 4.2 Exhibit transitions

- **What.** Each exhibit opens with a mono number, a serif title and a `line-strong` rule that draws left to right (a `scaleX` transform from 0 to 1 with `transform-origin: left`, 360ms) when its head crosses the reading line. Content below the rule is already there.
- **Borrowed from.** The numbered rows on sarvam.ai (01 to 05) and the stage headers on dealroom.net. glimm.dev was considered for this and rejected: a WebGL band sweeping between sections reports nothing, and its own guidance keeps it for significant events. It also adds projector risk on demo day.
- **Why.** The rule draws once per exhibit and says "a new exhibit starts here". It is the only motion most exhibits have.
- **Build.** New `ExhibitHead`. Replaces every use of `Reveal` on the page. `reveal.tsx` is deleted.

### 4.3 Number tweens, real numbers only

- **What.** The existing `NumberTween`, used in exactly four places: rail credits, rail model cost, case-bar status counts, and the sieve sentence counts.
- **Borrowed from.** The number-tween mechanic on beui.dev and amicro.vercel.app, written with the project's one curve and 360ms.
- **Rule.** A number tweens only between two values that are both in the showcase JSON, and only when the judge's position changes which one applies. Nothing counts up from zero on entry unless zero is its true starting value (credits spent before the run, claims settled before the first row).
- **Changed from the direction doc.** Fit does not count up on this page. A score that spins to its value reads as a slot machine. Fit is drawn at its value and the strip cells are drawn filled.

### 4.4 The thinking orb

- **What.** `thinking-orbs` is installed and used in `WorkingIndicator`. On the home page it appears in one situation only: the visitor is signed in and has a run in progress, in which case the "Open app" button reads "Open app · 1 run working" with the 16px orb. Otherwise the home page has no orb, no loader and no pulsing dot.
- **Borrowed from.** orbs.jakubantalik.com (now libraries.dev/orbs).
- **Why.** Nothing on the home page is running. The run is over, and the page says when it finished and how long each step took. Recorded durations are shown as mono text in the bill: "Gather evidence · 1 min 12 s". An orb beside a recorded run would be a lie about time.
- **Build.** Optional. If the signed-in check adds any complexity, ship with no orb at all.

### 4.5 Source-chip reveal and the evidence popover

- **What.** In the ledger, chips arrive one after another as their row is revealed: opacity 0 to 1 and a 4px rise, 200ms each, 80ms apart, at most three, then "+2". Elsewhere chips are static. Clicking a chip opens the existing `EvidenceDetail` popover: quote or field path and value, class in words, URL, retrieved-at.
- **Addition.** In the popover, when `quote` is present, set it as a block quotation in Newsreader with the as-of date under it. This is the one place the serif appears inside a component, because it is the source's voice, not DealProof's.
- **Borrowed from.** aicss.dev's inline numbered citations and source list, as a pattern only. None of its code or Pro components.
- **Why.** The order of arrival (source, then statement, then status) is the argument of the product. And a judge who clicks one chip and sees a real URL with a real quote stops doubting the rest.
- **Build.** A `revealed` prop on the ledger row; `SourceChip` and `EvidenceDetail` unchanged apart from the quote treatment.

### 4.6 Ledger settle and cross-reference highlight

- **Settle.** The existing `--animate-settle` keyframe on the status mark. Order and trigger as in Exhibit 4.
- **Cross-reference.** The existing `--animate-changed` keyframe (1200ms accent-tint fade), repurposed on this page for "you were sent here": when a disposition reason, a sufficiency gap or a requested document links to a claim, the page scrolls to the row and the row takes the highlight once. The same keyframe is used for a real version diff if the run has one.
- **Borrowed from.** The diff presentation on aicss.dev, and the settle-into-place mechanic common to beui.dev and rareui.com, without their spring.
- **Why.** The file's parts refer to each other: a reason rests on claims, a request settles a claim. Showing that reference is the diff highlight earning its place without a diff having to exist.

### 4.7 Marginalia: the principles, where they are demonstrated

- **What.** On `xl` and up, a 232px right margin beside prose and narrow exhibits holds short notes in Newsreader 16px, each with a mono number and a hairline to the thing it annotates. Beside wide exhibits (shortlist, ledger, panel) the note sits above the exhibit as its caption.

| Note | Sits beside |
| --- | --- |
| 01 Every fact has a source and a date | The first source chip in the docket |
| 03 Estimates are labelled as estimates | The first `Estimate` in the shortlist detail pane |
| 04 Identity comes first | The identity keys table |
| 02 The right source for the right question | The first row whose source is a company announcement |
| 05 Gaps are stated, not filled | The first Cannot verify row |
| 06 Rules decide, not AI confidence | The policy and inputs-hash line |
| 07 A person approves anything that leaves | The unsigned approval block |
| 09 New evidence changes the assessment in the open | The version line, or the diff if present |

- Principle 08 (confidentiality) has nothing to point at in a public-data run. It appears in the limits block and is not forced into the margin.
- **Borrowed from.** No site. It comes from the world: an annotated file.
- **Why.** A principle stated next to the row that obeys it is evidence. The same principle in an accordion is a slogan.
- **Motion.** None.

### 4.8 The sieve

- **What.** Described in Exhibit 2. Squares are 10px with a 4px gap on desktop, on the 4px grid.
- **Borrowed from.** The idea of showing a whole population at once comes from Dealroom's sector map screenshot. Not taken: its treemap sized by money raised, its flame icons and its growth badges.
- **Why.** "Drops companies that fail a must-have" is a sentence in the PRD. One mark per company makes it something the judge can count.
- **Guard.** If the search returned more than 160 records, the sieve shows the count sentence and a single stacked bar with three segments and drops the unit marks. It never samples or rounds.

### 4.9 Not used

| Considered | Decision |
| --- | --- |
| glimm.dev shader sweep between sections or on the hand-off to the app | No. Reports nothing; WebGL risk on a demo laptop |
| canvasui.dev ASCII, liquid and VHS effects | No |
| originkit.dev decorative effects | No |
| rareui.com fluid orb, amicro 3D cards and text effects, watermelon animated cards | No. Only the small mechanics in 4.3 and 4.6 |
| loading.dev loaders | Not on this page. Nothing loads: the JSON is in the build |
| Autoplaying tour with a pause button (the Dealroom tour's pattern) | No. Autoplay takes pace away from the presenter and replays a recorded run as if it were live |
| Sound | Not on the home page |

Research note. Fetched this pass with Firecrawl, as page summaries: sarvam.ai, dealroom.net, glimm.dev, orbs.jakubantalik.com, ui.watermelon.sh, beui.dev, rareui.com, amicro.vercel.app, loading.dev. dealroom.co was read from the user's six screenshots. aicss.dev, canvasui.dev and originkit.dev were not re-fetched; the notes in `design-direction.md` section 2 are relied on. No site's motion was watched, so every mechanic above is specified from scratch in this project's own curve and durations.

### Information design taken from the Dealroom screenshots

| Screenshot | Taken | Left behind |
| --- | --- | --- |
| Company profile (Sea Limited) | A header row with the name left and a small group of figures right. Small titled blocks on a shared grid, each with a muted qualifier at top right ("5-year trend", "$ · est.") | Donut chart, coloured tags, growth chips, the "tracked live" dot |
| Top investors | Ranked list beside a detail pane; thin inline bars under dated rows | The large purple match score, the radar chart |
| Sector deep-dive | Whole population visible at once | Treemap, flames, uppercase tracked labels |
| Newsfeed | A dated vertical timeline with one event per row | Avatars, "5h ago" relative times (DealProof writes dates in full) |
| Tour frame | A caption under the window that names what you are looking at, with a position counter | Autoplay, the gradient progress segments, the chat bubble |
| All | "Illustrative platform tour" stated once in the frame, not on every card | The need for the word "illustrative" at all |

## 5. Anti-gimmick rules

Motion earns its place by passing one test: **it reports a change in real data, or a change in where the judge is in the file.** If neither, it is removed.

Do not:

1. Show any state that implies work is happening now. No "Checking", no pending rings, no spinners, no orb, no skeletons. The run is finished and dated.
2. Count a number up from zero for effect. See 4.3.
3. Render any company, investor, person, quote, figure or date that is not in the showcase JSON. No fallback illustration. If a file is missing at build time, the exhibit is not rendered and the build logs it.
4. Smooth over a gap. A null fit shows `fit_unavailable_reason`. A null assessment shows "Not assessed" with the reason. A `not_checked` claim shows its hatch.
5. Use a gradient across hues, a glow, gradient text, glass, grain, a blob, a 3D object, a sparkle, an emoji, or the words "AI-powered", "magic", "instantly", "seamless".
6. Add customer logos, testimonials, usage counts or a "trusted by" line.
7. Animate on a timer. Sequences advance with scroll position, play once, and never loop.
8. Take over the scroll wheel, snap sections, or pin an exhibit for longer than its own height.
9. Move anything on hover beyond a colour or border change. No hover scale, tilt or lift.
10. Give two neighbouring exhibits the same entrance beyond the rule draw.
11. Use more than one accent. Registrar blue marks links, selection and focus. Green appears only on Supported and Prioritise.
12. Celebrate the result. A Prioritise stamp settles exactly as a Cannot assess stamp does.
13. Put the same figure on the page twice in different precision or wording.
14. Label real data "illustrative", or illustrative data "real".

Motion budget for the whole page, counted: one load entrance, nine rule draws, one sieve reorder, the ledger row reveals, the stamp settle, the pane crossfades, the rail tweens. That is the complete list.

## 6. Showcase framing

Real data about a real, named company on a public page needs care in both directions: the judge must be sure it is real, and the company must be treated fairly.

### The docket

```
 Real run · 22 Nov 2026, 14:06 IST
 ────────────────────────────────────────────────
 Thesis       1, typed by the DealProof team
 Returned     41 companies  [▤ Crustdata · 22 Nov 2026]
 Shortlisted  32
 Verified     1 · <Company> Pvt Ltd
 Claims       8, read from the company's public website
 Spent        86 credits · $0.42 model usage
 Policy       1.0
 ────────────────────────────────────────────────
 Nothing on this page was written by hand.
```

- "Real run" is stated once, here, and once more in the footer. It is not repeated on every exhibit.
- The date is the run's date. If the page is viewed later, a second line appears: "Records may have changed since". The page never shows today's date as if it were the run's.
- Counts come from the JSON. If a count is zero or null the line says so.

### Fairness to the company

- A fixed sentence at the head of Exhibit 4: "These statuses describe what public records could settle on 22 Nov 2026. Cannot verify means the record is silent. It is not a finding about the company."
- The left column is "The company's website says" with the page URL as its source. The word "seller" is not used: the company is not selling anything and did not take part.
- People are shown by role and record only, as the app does. No photos, no contact details.
- The request exhibit states that nothing was sent and the company was not contacted.
- The company's name is plain text. No logo, no brand colour.
- The footer carries: "Screening only. Not financial, legal or tax due diligence", then "Showcase data: public records and one company's public website, retrieved 22 Nov 2026", then a contact line for corrections.

### Decision for the user

A `contradicted` status on a named real company, on a public home page, is a published statement about that company. Two options:

- **(Recommended)** Publish as run, with the fairness sentence, and check each Contradicted row by hand against its quoted evidence before deploy. Do not pick a different company to avoid it; that would be curating the result.
- Show the company as "Company A" with the domain masked. This costs most of the credibility the real run buys.

### Fields the page needs in `meta.json`

`meta.json` has no contract type. The page reads these and treats every one as optional:

| Field | Use |
| --- | --- |
| `run_started_at`, `run_finished_at` | Docket date, bill durations |
| `thesis_id`, `case_id`, `investor_search_id` | "Open this case in the app" links; hidden when the id is absent |
| `company_name`, `company_domain` | Docket, case bar |
| `claims_origin` | Left column head. Expected `"public_website"` |
| `credits_total`, `llm_usd_total`, `credit_budget` | Docket and rail. Must equal the sums in `case.json` and the two run objects; the loader asserts this and fails the build on a mismatch |
| `returned_count`, `excluded_count` | Sieve sentence; cross-checked against `shortlist.length` |
| `policy_version` | Docket |

If the showcase generator can attach one real public document after the first assessment and re-run, `diff_from_previous` becomes non-null and Exhibit 6 gains a real "What changed" block. Worth asking for. Not worth faking.

## 7. Mobile

Under `lg` (1024px):

- **Rail becomes a chapter bar.** A 44px sticky bar under the navigation: "4 of 7 · Claims" on the left, "38 cr · $0.07" on the right, a 2px progress hairline under it. Tapping it opens the exhibit list as a sheet. From Exhibit 3 the case bar's content replaces the right side: status counts and, after Exhibit 5, the disposition glyph.
- **Cover.** Headline 44px, docket full width under it, buttons stacked at 44px height.
- **Exhibit 1.** Thesis, then criteria under it. The spine marks become bullets.
- **Sieve.** Squares 12px so they can be tapped; a tap names the company in a line under the chart. Over 80 records it falls back to the stacked bar.
- **Shortlist and investors.** The list alone. Tapping a row expands its detail in place (grid-rows transition, 200ms). The verified company is expanded on load. Five rows shown, then "Show all 32".
- **Ledger.** Rows stack: claim, status tag, record. Reveal order is kept but the chip stagger drops to a single fade. The evidence popover becomes a bottom sheet.
- **Assessment.** One column in the fixed order. The stamp is full width.
- **Request.** Documents, then the draft collapsed to its subject with "Read the draft", then the unsigned block.
- **Marginalia.** Inline, as a hairline-bordered note directly above the thing it annotates.
- **Bill.** The table keeps Step, Credits and Model; When moves under Step.
- Nothing below 11px. Touch targets 44px. No horizontal scroll except inside the bill table if needed.

## 8. Reduced motion, no script, slow machines

- **Server render is the finished file.** The HTML sent to the browser has every row settled, every count final, the stamp in the case bar. This reverses the current approach in `hero-ledger.tsx`, where the server draws pending rows and script settles them. With the reversal, a failed script, a slow projector laptop and a crawler all get the complete, correct page.
- **Motion is opt-in after mount.** Once mounted, and only when `useReducedMotionPreference()` returns `false`, exhibits that are still below the viewport are put into their unrevealed state. Anything already on screen stays finished. A judge who loads the page scrolled halfway down sees no flash.
- **`prefers-reduced-motion: reduce`.** No rule draw, no sieve reorder, no chip stagger, no settle, no stamp transfer, no tweens, no smooth scroll on cross-reference links (the jump is instant and the target row gets a static 2px accent outline for as long as it holds focus). Pane changes swap instantly. The rail and case bar show exact values for the current exhibit.
- **No information depends on motion.** The reveal order of the ledger is also stated in words under the exhibit head: "For each claim: the sources found, what they state, then the status the rules give."
- **Live regions.** The case bar's counts are `aria-live="off"` during scroll; they would otherwise announce on every row. The exhibit name in the rail is the only thing announced, politely, on change.
- **Keyboard.** The rail, list rows, strip cells, chips and ledger rows are all in the tab order. A "Skip to the claim ledger" link sits after "Skip to content".

## 9. Section layouts

Widths at `xl`: rail 184, gap 32, main 720, gap 32, margin 232 = 1200. Wide exhibits span main and margin (984).

### Cover

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ DealProof                The file   The ledger   The bill            Log in   [ Open app ]   │ 56
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                              │
│  First-pass screening for investors and acquirers                                            │
│                                                                                              │
│  Know what is proven                    Real run · 22 Nov 2026, 14:06 IST                    │
│  before the second                      ───────────────────────────────────────              │
│  meeting            (Newsreader 64)     Thesis       1, typed by the DealProof team          │
│                                         Returned     41 companies  [▤ Crustdata · …]         │
│  Below is one screening, start to       Shortlisted  32                                      │
│  finish, exactly as DealProof           Verified     1 · <Company> Pvt Ltd                   │
│  produced it. Open any source.          Claims       8, from its public website              │
│                                         Spent        86 credits · $0.42 model usage          │
│  [ Read the file ]  [ Start a screening ]  ───────────────────────────────────────           │
│                                         Nothing on this page was written by hand.            │
│                                                                                              │
│ ──────────────────────────────────────────────────────────────────────────────────────────── │
│  1  The thesis and how it was read                                        (peeks at the fold)│
└──────────────────────────────────────────────────────────────────────────────────────────────┘
   7 columns headline                     5 columns docket
```

### Exhibit 1

```
 Exhibits      1  The thesis and how it was read                         ┆ 01 Every fact has
 ────────      ══════════════════════════════════════════════            ┆ a source and a date
 ● 1 Thesis                                                              ┆ ╌╌ (to the first chip)
 │ 2 Short…    The analyst wrote          │    │  DealProof read it as
 │ 3 Ident…    ───────────────────────────┼────┼──────────────────────────
 │ 4 Claims    "Privately held Indian     │ ▪  │  Headquartered in India      Must have
 │ 5 Asses…     warehousing and supply-   │    │  Assessed from: company record
 │ 6 Reque…     chain software companies  │ ▪  │  Privately held              Must have
 │ 7 Inves…     that serve enterprise     │    │  Assessed from: evidence
   The bill     customers and show        │ ▫  │  Serves enterprise customers Preference ●●○
 ────────       recent expansion"         │    │  Assessed from: evidence
 Spent so far   (Newsreader 24)           │ ▫  │  Recent expansion, 12 months Preference ●●●
 0 credits                                │    │  Assessed from: signal
 $0.01 model   Criteria are edited before anything runs  →
```

### Exhibit 2

```
               2  The shortlist
               ════════════════════════════════════════════════════════════════════════════
               41 records · 9 removed for failing a must-have · 32 ranked

               ■■■■■■■■■■■■■■■■■■■■■■■■■■■■■■▨▨   □□□□□□□□□
               ranked 1 → 32            2 with an    9 removed: headquartered
               ▲ verified in this run   unknown      outside India (6), not
                                        must-have    privately held (3)

               ┌──────────────────────────────────┬──────────────────────────────────────────┐
               │ 1  <Company A>                   │ <Company C> Pvt Ltd   Verified in this run│
               │    Warehouse management software │ Warehouse execution software, Bengaluru   │
               │    Fit 84 · 80% assessable ▮▮▮▮╱ │ [▤ Crustdata · as of Nov 2026]            │
               │ 2  <Company B>                   │                                           │
               │    Fit 81 · 70% assessable ▮▮▮╱╱ │ Fit 78 · 64% of criteria assessable       │
               │ 3  <Company C>         ◀ selected│ ▮▮▮▮▮▮▯▮╱╱╱╱                              │
               │    Fit 78 · 64% assessable ▮▮▮╱╱ │                                           │
               │ 4  <Company D>                   │ ~140 people  Estimate   [◔ profiles · …]  │
               │    Fit 74 · 90% assessable ▮▮▮▮▮ │ Series A · 3 Jun 2025   [▤ funding · …]   │
               │ 5  …                             │ 6 open roles  Signal    [◔ postings · …]  │
               │                                  │                                           │
               │ Show all 32                      │ Why it is here                            │
               │ 9 removed  [Show]                │  India HQ · private · warehousing software│
               │                                  │ Unknown                                   │
               │                                  │  customer type · revenue band             │
               │                                  │ Last updated 22 Nov 2026                  │
               └──────────────────────────────────┴──────────────────────────────────────────┘
                 4 of 10 columns, 13px rows         6 of 10 columns, sticky while list scrolls
               Fit measures match to the criteria. It says nothing about returns.
```

### Exhibit 3, with the case bar pinned

```
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ <Company C> Pvt Ltd  ✓ Identity confirmed  Fit 78 · 64% assessable  ●0 ◐0 ?0 ◌0  ┌╌Not yet read╌┐ │ 44
├──────────────────────────────────────────────────────────────────────────────────────────────┤
               3  One company, identity first                            ┆ 04 Identity comes
               ══════════════════════════════════════════════            ┆ first
               ✓ Identity confirmed on 3 keys                            ┆ ╌╌
               ──────────────────────────────────────────────
               Domain            <domain>          [▤ Crustdata · …]
               Legal name        <Company C> Pvt…  [▤ Crustdata · …]
               Registered city   Bengaluru         [▤ Crustdata · …]
               Registration no.  Not reached · no registry source in this run   (hatched)
               ──────────────────────────────────────────────
               Founded 2017 [▤ …]   ~140 people Estimate [◔ …]   2 founders, matched on
               company id + name [◔ …]
```

### Exhibit 4

```
               4  The claim ledger
               ════════════════════════════════════════════════════════════════════════════
               For each claim: the sources found, what they state, then the status the rules give.
               These statuses describe what public records could settle on 22 Nov 2026. Cannot
               verify means the record is silent. It is not a finding about the company.

               ● Supported 3  ◐ Partially 1  ◇ Conflicting 0  ⬣ Contradicted 0  ? Cannot verify 2  ◌ Not checked 2

                  The company's website says        │      │  The record shows
               ────────────────────────────────────┼──────┼─────────────────────────────────────
                1 "Founded in 2017 in Bengaluru"   │  ●   │  Founded 2017, Bengaluru
                  Identity · [✎ <domain>/about]    │ Sup- │  [▤ Crustdata · as of Nov 2026]
                                                   │ported│
               ────────────────────────────────────┼──────┼─────────────────────────────────────
                2 "A team of 200+"                 │  ?   │  ~140 people  Estimate
                  Team size · [✎ <domain>/careers] │Cannot│  [◔ Crustdata profiles · as of Nov 2026]
                                                   │verify│  Profiles undercount operations staff
                                                   │      │  What would settle it: dated payroll summary
               ────────────────────────────────────┼──────┼─────────────────────────────────────
                3 "Raised Series A in 2025"        │  ●   │  Series A recorded 3 Jun 2025
                  Funding · [✎ <domain>/news]      │      │  [▤ Funding record · …] [✎ Announcement · …]
               ────────────────────────────────────┼──────┼───── reading line ──────────────────
                4 "Serving 50+ enterprise          │      │                        (not yet revealed:
                   customers"                      │      │                         claim only, spine empty)
               ────────────────────────────────────┼──────┼─────────────────────────────────────
                7╱"Opened a second office in 2026" ┊  ◌   ┊  Not checked · budget reached
                 ╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱ ┊ Not  ┊  No search was run for this claim
                                                   ┊checked┊
```

Above the ledger sits the caption-form marginal note, "05 Gaps are stated, not filled", pointing at the first Cannot verify row.

### Exhibit 5

```
               5  The assessment
               ════════════════════════════════════════════════════════════════════════════
               ┌─ Assessment · version 1 · policy 1.0 · 22 Nov 2026, 14:11 IST ──────────────┐
               │ Opportunity fit          Evidence sufficiency       Business assessment     │
               │ Fit 78 · 64% assessable  5 of 8 required checks     Operating signals       │
               │ ▮▮▮▮▮▮▯▮╱╱╱╱             settled · 2 not checked    ~140 people  Estimate   │
               │                          ●●●◐ ?? ╱╱                 6 open roles  Signal    │
               │                          Gaps: payroll, customers   Headcount up, 12 mo Signal│
               │ ─────────────────────────────────────────────────────────────────────────── │
               │ Financial assessment               Screening disposition                    │
               │ ┌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┐    ┌────────────────────────┐               │
               │ ╎ Not assessed                ╎    │ ⌕ Investigate further  │  ← settles,   │
               │ ╎ No reliable financial inputs╎    └────────────────────────┘    then appears│
               │ ╎ Would need: audited accounts╎    Strong fit; 3 of 8 claims open  in case bar│
               │ └╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┘    Rests on: claims 2, 4, 7  (links, highlight)│
               └─────────────────────────────────────────────────────────────────────────────┘
               policy 1.0 · inputs hash 3f9c… · the same records under the same      ┆ 06 Rules decide,
               policy give the same assessment                                       ┆ not AI confidence
```

### Exhibit 6

```
               6  The request, awaiting approval                         ┆ 07 A person approves
               ══════════════════════════════════════════════            ┆ anything that leaves
               Documents requested (3)            Drafted by DealProof
               ────────────────────────────       ────────────────────────────────────────
               Dated payroll summary              Subject  Information request: …
                 would settle claim 2  →          Dear …,
               Customer list or two contracts     We are completing a first-pass screening…
                 would settle claim 4  →          (the real draft, read-only, 14px, 680 measure)
               Lease or occupancy record
                 would settle claim 7  →

               ┌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┐
               ╎ Draft · not approved · not sent                                             ╎
               ╎ Recipient   none. DealProof does not suggest an address                     ╎
               ╎ Approver    none. Approval needs a signed-in person                         ╎
               └╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┘
               This request was drafted during the run and never sent. DealProof did not
               contact the company.
               ─ case bar unpins here ─
```

### Exhibit 7

```
               7  The other direction: investors
               ════════════════════════════════════════════════════════════════════════════
               The same company, seen as a business raising money.
               11 investors · from 23 comparable companies · 61 rounds read, 14 excluded

               ┌──────────────────────────────────┬──────────────────────────────────────────┐
               │ 1  <Investor A>        ◀ selected│ <Investor A>                              │
               │    4 comparable rounds ·         │ 2023      2024      2025      2026        │
               │    last in sector Aug 2026       │ ──●─────────●────●──────────────●──       │
               │ 2  <Investor B>                  │ <Co X>  Series A  12 Aug 2026 [▤ …]       │
               │    3 comparable rounds ·         │ <Co Y>  Seed       3 Mar 2025 [▤ …]       │
               │    last in sector Feb 2026       │ + 2 more                                  │
               │ 3  …                             │ Why they fit   4 rounds in warehousing    │
               │                                  │                software in India since 2023│
               │                                  │ Unknown        fund status, cheque size   │
               │                                  │ Possible duplicate of "<Investor A> Capital"│
               │                                  │ · not merged                              │
               └──────────────────────────────────┴──────────────────────────────────────────┘
               This ranking describes past investments. It does not predict whether an investor
               will invest. No contact details are collected.
```

### Close

```
               The bill
               ════════════════════════════════════════════════════════════════════════════
               Everything on this page came from one run.
               86 of 150 credits · $0.42 model usage

               Run        Step                   Credits   Model    Took
               Discover   Read thesis                –     $0.01    4 s
               Discover   Search companies          22       –      18 s
               Verify     Confirm identity           2       –      3 s
               Verify     Gather evidence           48       –      1 min 12 s
               Verify     Extract facts              –     $0.18    41 s
               Investors  Read rounds               14       –      22 s
               Total                                86     $0.42    4 min 51 s

               What this file is not                     (two columns, six lines, no motion)
               Not financial, legal or tax diligence     Not legal advice or deal terms
               Not a return predictor                    Not a judgment on people
               Not a valuation                           Not a window into private records

                          Screen your next target with the evidence attached
                         [ Start a screening ]   [ Open this case in the app ]
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ DealProof · Built at ContextCon 2026        Scoring policy   Confidentiality   GitHub        │
│ Screening only. Not financial, legal or tax due diligence                                    │
│ Showcase data: public records and one company's public website, retrieved 22 Nov 2026        │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

All figures and names in these layouts are placeholders to show density. The built page prints only what the showcase JSON holds.

## 10. Implementation plan

Three chunks, each for one Fable builder, with no shared files. Chunk 1 lands a small first commit (the data module and empty exhibit files) so chunks 2 and 3 can start against fixed imports.

Rules for all three:

- `components/dealproof/*`, `components/ui/*`, `lib/types.ts` and `app/globals.css` are read-only, except the named edits below, each owned by one chunk.
- No new dependencies. Motion, `thinking-orbs` and the tokens already cover everything here.
- No arbitrary colour or spacing values. If a value is missing, the chunk owner asks chunk 1 to add a token.
- Exhibit components are server components that receive plain props. Only the pieces that move are client components.
- The showcase files may land late. Every exhibit must render nothing, and log at build time, when its data is absent.

### Step 0: the frozen interface (chunk 1's first commit)

`apps/web/lib/showcase/index.ts` exports one function per exhibit. Each returns view types from `lib/types.ts` where one exists, using the mappers already in `components/case/adapt.ts`, `components/discover/adapt.ts` and `components/investors/adapt.ts`.

| Export | Returns | Null when |
| --- | --- | --- |
| `getDocket()` | run date, counts, totals, company name, `claimsOrigin` | `meta.json` missing |
| `getThesis()` | `{ text, criteria }` | `discovery.json` missing |
| `getShortlist()` | `{ returned, removed[], ranked[], verifiedId }` with `FitResult` per row | same |
| `getIdentity()` | `Identity` plus profile facts | `case.json` missing |
| `getLedger()` | `Claim[]`, counts | same |
| `getAssessment()` | `Assessment`, version meta, diff or null | `assessment` null |
| `getRequest()` | request items with claim numbers, draft | `request_list` null |
| `getInvestors()` | entries, counts, ranking basis | `investors.json` missing |
| `getBill()` | `CaseCost`, per-step durations | `case.json` missing |
| `getSpendByExhibit()` | cumulative `{ credits, usd }` for each exhibit id | any file missing |

Exhibit ids, used for anchors and the rail: `thesis`, `shortlist`, `identity`, `claims`, `assessment`, `request`, `investors`, `bill`.

### Chunk 1: the frame and the data

Owns:

- `apps/web/lib/showcase/` (new): `index.ts`, `load.ts`, `spend.ts`, `checks.ts` (the build-time assertions from section 6)
- `apps/web/app/page.tsx`
- `apps/web/components/marketing/home/` (new): `shell.tsx`, `cover.tsx`, `docket.tsx`, `docket-rail.tsx`, `chapter-bar.tsx` (mobile), `case-bar.tsx`, `exhibit-head.tsx`, `margin-note.tsx`, `reading-line.tsx` (the context and hook that reports the current exhibit and revealed rows), `close.tsx`, `site-header.tsx`, `site-footer.tsx`
- `apps/web/components/marketing/content.ts`: remove the Pune data and the cut sections; keep nav, cover, limits, footer strings
- Deletes: `hero-ledger.tsx`, `steps.tsx`, `problem-ledger.tsx`, `reveal.tsx`, `fit-readout.tsx`, `sections.tsx`, `primitives.tsx` (after moving `Container` into `home/shell.tsx`)
- `docs/content/home.md`: rewrite to the new copy
- `docs/design/design-direction.md` section 11.1: replace with a pointer to this file

Delivers the page skeleton with all pinning, the rail tween, the case bar and its three states, mobile chapter bar, reduced-motion and no-script behaviour. `reading-line.tsx` exposes `useExhibit()`, `useRevealed(id)` and `markSettled(status)`; chunks 2 and 3 call these and do not write their own observers.

### Chunk 2: discovery and investors

Owns, all new, in `apps/web/components/marketing/home/`:

- `thesis-exhibit.tsx`
- `sieve.tsx`
- `shortlist-exhibit.tsx`, `ranked-list.tsx`, `detail-pane.tsx` (the list-and-pane shell, generic over row type)
- `investors-exhibit.tsx`

Reuses `CriteriaStrip`, `FitText`, `Fact`, `SourceChip`, `EstimateLabel`, and `components/investors/round-axis.tsx` unchanged. Delivers the sieve reorder, row selection with hover linking between sieve and list, the removed list, and the mobile accordion form.

### Chunk 3: the case

Owns, all new, in `apps/web/components/marketing/home/`:

- `identity-exhibit.tsx`
- `ledger-exhibit.tsx`
- `assessment-exhibit.tsx`
- `request-exhibit.tsx`
- `bill-exhibit.tsx`
- `cross-ref.tsx` (the scroll-to-claim link and highlight)

Owns these edits to shared components, and is the only chunk allowed to make them:

- `components/dealproof/claim-ledger.tsx`: a `claimHeading` prop on `ClaimLedger` (default "Seller said"), and a `revealed` prop on `ClaimLedgerRow` that stages chips, record and mark. The existing `pending` prop is left alone for the app.
- `components/dealproof/source-line.tsx`: the serif block-quote treatment in `EvidenceDetail`.
- `components/dealproof/approval-block.tsx`: a read-only "Draft · not approved · not sent" state, if the existing states cannot express it.

Delivers the ledger reveal against chunk 1's reading line, the stamp settle and its hand-off to the case bar (a shared `layoutId` agreed in step 0: `showcase-disposition`), the cross-reference highlight, the unsigned block and the bill.

### Order and merge

1. Chunk 1 pushes step 0: `lib/showcase` with real types and stub returns, plus empty exhibit files exporting components with their final prop types. About thirty minutes.
2. All three build in parallel. Each commits only inside its own file list.
3. Chunk 1 integrates last: it is the only one that touches `page.tsx`.
4. One pass by a single reviewer against section 5's rules and the motion budget, on a phone width and with reduced motion on.

### Open questions

1. Publish a named real company with whatever statuses the run gave, or mask it? Recommended: publish, after a hand check of any Contradicted row (section 6).
2. Is there a public, read-only route for "Open this case in the app", or does it go through login? If login only, the button reads "Log in to open this case".
3. Can the showcase generator produce a second assessment version from one real public document, so the diff is real?
4. Where do the comparison and audience tables go: an `/about` page, or cut for the hackathon? Recommended: cut for now.
5. The orb for a signed-in visitor with a live run (4.4): build, or leave the home page with none? Recommended: none for the demo.
