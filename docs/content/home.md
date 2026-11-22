# DealProof marketing home page copy

Source of truth: `DealProof product description.md` and `docs/design/design-direction.md` (Section 11.1).

Copy conventions for implementation:
- Sentence case everywhere.
- Headings, navigation links, labels, and buttons end without a period. Paragraphs keep their periods.
- No exclamation marks, no emoji, no invented statistics, customer logos, or testimonials.
- Always use the product's exact terms: `Supported`, `Partially corroborated`, `Conflicting evidence`, `Contradicted`, `Cannot verify`, `Not checked`; `Prioritise`, `Investigate further`, `Deprioritise`, `Cannot assess`; `Estimate`, `Signal`; `Fit X · Y% of criteria assessable`.
- Every illustrative company or investor example carries the label `Illustration, not a real company` (or `Illustration, not a real investor`).

---

## 1. Navigation bar

- Wordmark: `DealProof`
- Links:
  - `How it works`
  - `The claim ledger`
  - `Principles`
- Actions:
  - Text link: `Log in`
  - Primary button: `Open app`

---

## 2. Hero

Layout: centred serif headline (`Newsreader`, 64px desktop / 44px mobile) over `paper-warm`, one-line eyebrow above, plain sans subhead (max 36rem) and two buttons below, handing directly into the illustrative claim-ledger window running past the fold.

### Eyebrow

```text
First-pass screening for investors and acquirers
```

### Headline options (ranked)

1. **Recommended pick:**
   ```text
   Know what is proven before the second meeting
   ```
   *Why this ranks first:* It names the exact moment an associate, corporate development analyst, or CFO office cares about — walking into the second meeting knowing which seller claims hold up and which remain open. It breaks cleanly into two short lines at 64px serif and pairs directly with the subhead below.

2. **Second option (PRD tagline):**
   ```text
   Discover opportunities. Verify the evidence. Evaluate with confidence.
   ```
   *Note:* Faithful to the PRD tagline. Works well if the team wants the three core steps named in the hero itself. Slightly wider across two lines at 64px; drop the final period only if strictly enforcing the no-period heading rule, or keep all three periods for symmetry.

3. **Third option:**
   ```text
   Screen acquisition targets with every claim checked
   ```
   *Note:* Plain, direct, and clear about what the product does and for whom. Ranks third because it centres only on acquisition screening and leaves out investor discovery and the decision timeline.

### Subhead

```text
DealProof finds companies that match your thesis, checks each claim against dated, independent evidence, and says plainly what it could not verify.
```

### Hero actions

- Primary button: `Start a screening`
- Secondary button: `See a finished case`

### Hero product window (above and past the fold)

- Window title: `Meridian Warehousing · Claims`
- Right-aligned label (required): `Illustration, not a real company`
- Table headers: `Seller said` | `Status` | `The record shows`
- Preview rows (first four claims from the PRD's Pune illustration; Meridian Warehousing is an illustrative placeholder name):

| Seller said | Status | The record shows |
| --- | --- | --- |
| "Incorporated in 2014, based in Pune" | `Supported` | Company registry record states both. Source chip: `Registry mirror · as of 12 Mar 2014` |
| "We employ 250 people" | `Cannot verify` | `~180 people Estimate` — warehouse staff rarely have professional profiles. What would settle it: dated payroll summary. Source chip: `Crustdata profiles · as of Oct 2026` |
| "We opened a new facility in October 2026" | `Partially corroborated` | Dated announcement describes a planned facility. Nothing found shows it is operating. Source chip: `Company announcement · as of 9 Sep 2026` |
| "We have no debt" | `Cannot verify` | A lender's registered security is on record, which shows security was given, not that money is owed. What would settle it: lender statements. Source chip: `Registry mirror · as of 18 Aug 2025` |

---

## 3. The problem

Layout: section heading, short lead paragraph, and a structured three-column table drawn directly from the PRD.

### Heading

```text
Why first-pass screening breaks down
```

### Lead

```text
Today, screening a private company is spread across databases, registry lookups, seller presentations, and an analyst's spreadsheet. Between the first call and the memo, eight things routinely go wrong.
```

### Problem table

| What goes wrong | What it costs | What DealProof does |
| --- | --- | --- |
| Company information is scattered | Slow, repeated research across disconnected tools | One connected search and research flow |
| Companies are compared inconsistently | Subjective screening from one target to the next | The same criteria applied to every candidate |
| Growth signals are mistaken for real traction | Overconfident conclusions | Keeps observed signals apart from confirmed results |
| Seller presentations go unchecked | Decisions rest on unverified claims | Checks each claim and shows the evidence |
| Similar names cause mix-ups | The wrong company's or person's record is attached | Confirms identity first, and says so when it cannot |
| Financial information is missing | Valuations built on guesses | Says what is missing instead of filling the gap |
| Reports take days to assemble | Analyst time spent compiling instead of judging | Produces the screening memo itself |
| Open questions are never followed up | Screening stays incomplete | Lists exactly what to ask the seller for |

---

## 4. Four steps, one case

Layout: tabbed section (`Discover`, `Verify`, `Evaluate`, `Act`). Left side holds the short summary and `What you give` / `What it does` / `What you get`; right side renders the live component preview.

### Section heading

```text
Four steps, one case
```

### Section subhead

```text
Start with an investment thesis, or go straight to a company you already have in mind.
```

---

### Tab 1: Discover

**Headline:** `Turn a thesis into a shortlist of real companies`

**Lead:** `Describe what you are looking for in plain words. DealProof returns companies that match your criteria and explains why each one is on the list.`

- **What you give:** An investment thesis in plain words. For example: "privately held Indian warehousing and supply-chain software companies that serve enterprise customers and show recent expansion."
- **What it does:** Turns the thesis into clear criteria, separating must-haves from preferences. Lets you edit them before anything runs, searches live company data, removes duplicates, drops companies that fail a must-have, and ranks the rest by fit.
- **What you get:** A shortlist with each company's business, location, size and growth estimates, funding history, hiring activity, reasons for inclusion, and what is still unknown. Every item shows its source and date.

**Note under preview:** `The fit score measures how well a company matches your requirements. It says nothing about expected returns. Hiring and headcount growth are never treated as proof of revenue.`

*Preview component:* Criteria editor (`Must have` vs `Preference`) and three shortlist rows with the criteria strip.

---

### Tab 2: Verify

**Headline:** `Check every claim against independent records`

**Lead:** `Pick a company from the shortlist, or enter a name and website directly. DealProof confirms the legal entity and checks each claim one by one.`

- **What you give:** A shortlisted company, or a company name and website. You can upload the seller's presentation and documents, or type in individual claims.
- **What it does:** Confirms which legal entity you are looking at, builds a public profile, tests each factual claim against independent evidence, compares seller documents with each other, gathers recent dated events, and places the company beside comparable firms.
- **What you get:** A claim ledger. Every claim carries a status, the exact evidence, the date of that evidence, and the document needed if it could not be settled.

**What it checks first:** `Identity, business and industry, funding events, team size and growth, leadership and founders' career history, and dated public events such as launches and expansions. Where reliable records can be reached, it also covers registered security interests, directorships, litigation, customer and partnership claims, and financial filings.`

*Preview component:* Live run panel (`Confirm identity`, `Build public profile`, `Read seller deck`, `Gather evidence`) above settling ledger rows.

---

### Tab 3: Evaluate

**Headline:** `Keep five judgments separate`

**Lead:** `DealProof turns what it found into a screening assessment you can defend to a decision-maker. It never blends separate judgments into one score.`

- **Opportunity fit:** How well does this company match our strategy?
- **Evidence sufficiency:** Do the available records support what we need to know?
- **Business assessment:** What do observable operating indicators suggest?
- **Financial assessment:** What do reliable financial inputs show, under stated assumptions? Shown only when such inputs exist.
- **Screening disposition:** What should we do next? One of four outcomes: `Prioritise`, `Investigate further`, `Deprioritise`, or `Cannot assess`.

**Adaptation note:** `The evaluation adapts to the company. A young startup is judged on thesis fit, founder relevance, team development, and funding history. An established business is judged on strategic fit, identity, operating scale, financial performance, commercial position, and leadership continuity.`

*Preview component:* The five-judgment panel showing `Opportunity fit`, `Evidence sufficiency`, `Business assessment`, `Financial assessment` (hatched `Not assessed`), and `Screening disposition` (`Investigate further`).

---

### Tab 4: Act

**Headline:** `Ask for what is missing, once, after approval`

**Lead:** `DealProof works out which documents would settle each open question and drafts one consolidated request to the seller.`

- **What you give:** Your review, the recipient address, and a named person's approval.
- **What it does:** Lists the exact documents tied to open claims, waits until a named approver signs off, and sends the request once. When the seller's documents arrive, they attach to the same case.
- **What you get:** Re-checked claims, an updated assessment, and an open diff showing what changed, what was believed before, and why it changed.

*Preview component:* Request list tied to open claims beside an approval receipt (`Approved by Asha Rao · Sent once`).

---

## 5. The claim ledger and its six answers

Layout: full illustrative case (PRD's Pune example) followed by the six-status legend grid and two unequal callout cells (`Cannot verify is a real answer` and `Not checked never looks clean`).

### Section heading

```text
What a claim ledger looks like
```

### Illustration notice (always visible)

```text
Illustration, not a real company
```

### Case context

```text
A mid-sized Indian logistics company's CFO office is reviewing a regional warehousing operator in Pune after a first meeting. DealProof checks six claims from the meeting and seller presentation against independent records.
```

### Full illustrative ledger

| Seller said | Status | What DealProof reports | What would settle it |
| --- | --- | --- | --- |
| "Incorporated in 2014, based in Pune" | `Supported` | The company registry record states both. | — |
| "We employ 250 people" | `Cannot verify` | A profile-based estimate is lower, but warehouse staff rarely have professional profiles. | Dated payroll summary |
| "Our founder ran operations at a national logistics firm" | `Supported` | A professional record shows the role and the years. | — |
| "We raised growth funding in 2025" | `Supported` | A funding record and a dated announcement agree. | — |
| "We opened a new facility in October 2026" | `Partially corroborated` | A dated announcement describes a planned facility. Nothing found shows it is operating. | Lease or occupancy record |
| "We have no debt" | `Cannot verify` | A lender's registered security is on record, which shows security was given, not that money is owed. | Lender statements |

### Resulting screening summary

```text
Strong fit with the client's strategy, with three of six claims supported and three open. Disposition: Investigate further. A consolidated request list of three documents waits for the manager's approval.
```

---

### Subsection: Six answers, including the honest ones

**Legend (fixed order):**

- **Supported:** Adequate evidence directly supports the claim.
- **Partially corroborated:** Evidence supports part of the claim, not all of it.
- **Conflicting evidence:** Relevant sources disagree with each other.
- **Contradicted:** Reliable evidence directly conflicts with the precise claim.
- **Cannot verify:** Available evidence cannot settle the question. DealProof names what would.
- **Not checked:** The check was not run, for example because a source was unavailable or the budget ran out.

**Wide left callout:**
- Heading: `Cannot verify is a real answer`
- Body: `Private company records in India rarely cover payroll, customer contracts, or current debt balances. When available evidence cannot settle a claim, DealProof says so plainly and names the document that would.`

**Right callout (shown with hatched row preview):**
- Heading: `Not checked never looks clean`
- Body: `A check that was not run is marked with a dashed border, a hatched fill, and the reason it stopped — such as budget reached or source unavailable. It is never counted as settled and never hidden from the summary.`

---

## 6. Fit is not evidence

Layout: two shortlist rows side by side replacing a traditional marketing metrics band.

### Heading

```text
Fit is not evidence
```

### Lead

```text
Next to every fit score, DealProof shows how much of your thesis it could actually assess. A company with thin public records never looks as ready as one with full records, and missing evidence never triggers Deprioritise on its own.
```

### Side-by-side comparison (labelled `Illustration, not real companies`)

- **Left row:**
  - Readout: `Fit 82 · 70% of criteria assessable`
  - Detail: `7 of 10 criteria assessable · 3 unknown: ownership, customer type, revenue band`
  - Caption: `Attractive on what is known, with three criteria still open.`
- **Right row:**
  - Readout: `Fit 82 · 100% of criteria assessable`
  - Detail: `10 of 10 criteria assessable · 0 unknown`
  - Caption: `Same fit score, backed by complete criteria coverage.`

---

## 7. For businesses raising money

Layout: one concise section with an illustrative investor shortlist row preview.

### Heading

```text
For businesses raising money
```

### Lead

```text
DealProof also works in the other direction. Small and mid-sized businesses looking for capital — and the advisers representing them — often spend months approaching investors who do not back their sector or stage.
```

### Body

```text
Describe your sector, location, stage, size, and the funding you are seeking. DealProof finds comparable companies that have raised money, reads who invested in them and when, and ranks investors by how many comparable investments they have made and how recently.
```

### What each shortlist entry shows

- Comparable companies the investor backed, with the round and the date.
- When the investor last invested in the sector.
- Why they fit your profile, and what is still unknown.

### Guardrails (shown directly beneath the preview row)

```text
An investor appears only when a dated funding record supports it. The ranking describes past investments and does not predict whether an investor will invest. DealProof does not collect investors' personal contact details, and any message to an investor waits for a person's approval.
```

### Preview row (`Illustration, not a real investor`)

- Name: `Northgate Ventures`
- Summary: `4 comparable investments · last in sector Aug 2026`
- Backed companies: `Cold Chain Logix · Series A · 12 Aug 2026` (`Funding record · as of 12 Aug 2026`); `Fleetwise · Seed · 3 Mar 2025` (`Funding record · as of 3 Mar 2025`)
- Why they fit: `4 rounds in warehousing technology in India since 2024`
- Unknown: `Current fund status, cheque size`

---

## 8. Principles

Layout: numbered expandable rows (`01` to `09`), matching `docs/design/design-direction.md`.

### Heading

```text
How DealProof decides
```

### Lead

```text
A company can be attractive while its claims remain unverified. DealProof keeps those two things apart.
```

### Numbered principles

- **01 · Every fact has a source and a date**
  Nothing comes from the AI's memory. If no record states it, DealProof does not say it.
- **02 · The right source for the right question**
  A company registry is strong on incorporation. An audited statement is strong on past revenue. A customer's own confirmation is strong on a customer relationship. A company's announcement shows that it announced something, not that it happened.
- **03 · Estimates are labelled as estimates**
  Team size drawn from professional profiles is a signal, not a payroll count. Every inferred figure carries the `Estimate` or `Signal` label and its basis.
- **04 · Identity comes first**
  DealProof does not attach a record to a company or a person on a matching name alone. When it cannot tell two apart, it says so.
- **05 · Gaps are stated, not filled**
  Missing information stays missing, and it is never counted against a company as poor performance.
- **06 · Rules decide, not AI confidence**
  The same records under the same policy give the same assessment every time.
- **07 · A person approves anything that leaves**
  No message goes to a seller or investor without a named approver.
- **08 · Confidential documents stay confidential**
  Uploaded files are used only for that case. They are not used to train AI, not shared across customers, stripped of personal details that are not needed, and deleted on a set schedule.
- **09 · New evidence changes the assessment in the open**
  The earlier view is kept, and the reason for the change is shown.

---

## 9. What it is not

Layout: two-column list of six boundaries from the PRD.

### Heading

```text
What it is not
```

### Lead

```text
DealProof is the screening that happens before formal due diligence. It makes that later work better aimed. It does not replace it.
```

### Six boundaries (two columns, three per column)

1. **Not financial, legal, or tax due diligence**
   Formal diligence rests on the seller's confidential books and on signed professional opinions. DealProof does the first-pass research that comes before accountants and lawyers step in.
2. **Not a return predictor**
   DealProof measures fit against your criteria and checks factual claims. It does not predict returns or say whether an investment will succeed.
3. **Not a valuation**
   Where reliable financial figures are supplied, DealProof can run stated scenarios under stated assumptions. It never produces a verified fair value.
4. **Not legal advice or deal terms**
   DealProof does not give legal advice, draft contracts, or recommend deal structure or terms.
5. **Not a judgment on people**
   DealProof reports what records show about roles, career history, and dates. It does not score or judge individuals.
6. **Not a window into private records**
   DealProof cannot see what is not on record. Private company financials, tax positions, and many customer relationships are not public in India, and DealProof says so case by case.

---

## 10. How it differs

Layout: calm comparison table across categories. No named competitors disparaged.

### Heading

```text
How it differs from what exists
```

### Lead

```text
DealProof does not compete on how many companies it lists or how many metrics it shows. It competes on the quality of the finished screening job.
```

### Category comparison table

| Existing category | What it does well | What DealProof adds |
| --- | --- | --- |
| Company discovery platforms | Finding companies, building market maps, and surfacing growth signals | Checks the claims behind a company, not only its profile |
| M&A workflow platforms | Managing pipelines, document rooms, and diligence teams | Does the first-pass research itself against outside evidence |
| Company registry reports | Giving a static profile of what is on file for an entity | Starts from what the seller claimed and reconciles each claim one by one |
| Pitch-deck screening tools | Summarising a seller presentation quickly | Indian records, a dated source on every finding, and `Cannot verify` as a real answer |
| An analyst working by hand | Judgment, nuance, and context | The same checks every time, in minutes, with every source attached |

### Closing note

```text
The difference is the connection: discovery, independent verification, and transparent evaluation in one reproducible case.
```

---

## 11. Who it is for

Layout: primary customer statement followed by a compact two-column table of additional fits.

### Heading

```text
Who it is for
```

### Primary audience

```text
Built first for small M&A advisory firms and corporate development teams — including mid-market CFO offices screening regional targets in sectors such as logistics, warehousing, and supply-chain technology — that review acquisition opportunities every month with only a few analysts.
```

### Supporting paragraph

```text
The primary user is an investment associate or corporate development analyst who wants to spend less time compiling and be more certain of what they pass upward: no wrong facts in the memo, no recommendation they cannot back up, and no confidential file ending up where it should not.
```

### Also a fit

| Team | What they need most |
| --- | --- |
| Private equity funds | Screening established businesses consistently |
| Early-stage venture funds | Finding startups that match a thesis, and checking founders and traction |
| Roll-up operators | Assessing many similar targets against one strategy |
| Family offices | Independent checks on private businesses |
| Search funds | Finding and first-pass screening of acquisition targets |
| Business brokers | Credible, evidence-backed company profiles |
| Businesses raising money and their advisers | A shortlist of relevant investors backed by dated funding records |

---

## 12. Closing CTA and footer

### Closing CTA

- Heading: `Screen your next target with the evidence attached`
- Body: `Every investment or acquisition opportunity that reaches a decision-maker should arrive with its claims already checked and its unknowns already named.`
- Primary button: `Start a screening`
- Secondary button: `See a finished case`

### Footer

- Left: `DealProof` · `Built at ContextCon 2026`
- Links:
  - `Scoring policy`
  - `Confidentiality`
  - `GitHub`
- Scope line: `Screening only. Not financial, legal or tax due diligence.`
