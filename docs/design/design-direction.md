# DealProof design direction

Checkpoint 0b · 2026-11-22 · design-system foundation for `apps/web`

This document sets how DealProof looks, moves and reads. The product is defined in `DealProof product description.md` and the build in `docs/superpowers/specs/2026-11-22-dealproof-v1-design.md`; nothing here changes either. Token values live in [`tokens.css`](tokens.css) and [`tokens.json`](tokens.json). Where a value appears in this document and in the tokens, the tokens win.

The `unslop` skill was used to derive the direction and its rules are applied throughout (unslop by Damir Sokolovsky, [@heydamir](https://x.com/heydamir), CC BY 4.0). No screen exists yet, so there was nothing to audit; the skill's direction step and nine passes are used here as constraints on what gets built.

## 1. Direction

**Product.** DealProof finds companies that match an investment thesis, checks each claim about them against dated, independent evidence, and tells an analyst which ones deserve a closer look and why.

**Who uses it.** An investment associate or corporate-development analyst at a small M&A advisory firm, and at ContextCon the CFO office of a mid-sized Indian logistics company. They read dense material for hours, pass conclusions upward, and are afraid of three things: a wrong fact in a memo, a recommendation they cannot back up, and a confidential document leaking. The second reader is the decision-maker, who gets the memo, often printed, and has minutes.

**Character.** Exact, sober, quietly assured. The interface should feel like a well-kept diligence file, not a dashboard that is excited about itself. Confidence comes from showing the evidence and the gaps with the same care.

**World.** The diligence file: a ledger with a claim on one side and the record on the other, registry extracts, a memo with footnotes, an approval signature. Paper and ink. This sets grey paper surfaces, near-black ink, one registrar-blue accent, a serif for the memo's voice and a mono for dates and figures.

**Moments.** Two places carry the richness; everything else is quiet.

1. The **claim ledger**: what the seller said, set against what the record shows, with a status mark on the spine between them.
2. The **criteria strip**: the fit score drawn on a track that is visibly shortened by whatever could not be assessed.

**Signature.** The **source line**: every fact ends in a small chip naming where it came from and a mono as-of date, like a footnote that is always attached. It appears on every fact and nowhere as decoration.

### What the direction rules out

- A single blended score, a gauge, a traffic light for the whole case, or any "confidence %" from the model.
- Green as a default. Green means one thing: a claim is Supported, or the disposition is Prioritise.
- A flat, tidy rendering of anything that was not checked.
- Gradients across hues, glows, gradient text, glass, floating blobs, emoji as icons, uppercase tracked labels, pill-shaped everything, bouncy springs.
- Invented proof: customer logos, testimonials, usage numbers. DealProof has none yet, so the home page shows the product instead.

## 2. References: what is taken and what is not

Pages were read with Firecrawl (markdown, extracted branding and first-screen screenshots). No interactive browser was used, so hover states, scroll behaviour and the motion on the component sites were read from their descriptions, not watched. `animbits.dev` did not load (proxy error on the scraper) and is not reflected here.

### Primary

| Reference | Taking | Not taking |
| --- | --- | --- |
| **dealroom.co** (company intelligence) | The hero that hands straight over to a working product window marked "Illustrative platform tour". Dense, calm tables: 13px cells, company in the first column, figure with its change stacked under it, a quiet left nav of views. Honest labelling of demo data. Light grey page with white cards. | The signal-score bar with a blue-to-teal gradient and a single 0 to 99 number per company, which is the blended score DealProof refuses to show. Emoji in the navigation menus. "+320%" growth figures presented without a source, the "LIVE" pulse dot, the "NEW" badges. A bright blue button with a coloured glow shadow. |
| **dealroom.net** (M&A workflow) | Vocabulary and structure an M&A reader already knows: pipeline stages, a diligence request list, status tags on deal cards. A module rail beside the product window that switches what the window shows, reused for Discover / Verify / Evaluate / Act on the home page. A "request list" as a first-class object. | The dark navy hero with grid lines and sparkles. Poppins at heavy weights. The "AI-powered operating system" tone, trademarked taglines, testimonial cards with large unverifiable numbers, a promotional top banner. Status tags that rely on fill colour alone. |
| **sarvam.ai** (home page) | A centred, short serif headline with a one-line eyebrow above it and two buttons below; large calm margins; body text in a plain sans. A tabbed product section where each tab shows the real interface doing a job, with a numbered step list ("1. Web: searching official notices") and an "Illustrative" caption. Numbered feature rows (01 to 05) that expand. Dark fill for the primary button with a quiet outlined secondary. A restrained footer. | The orange-to-blue gradient wash behind the hero, the ornamental motif, the customer-logo marquee, fully round pill buttons, the announcement bar, "trusted by" claims. Its accent sits in the indigo-violet range; DealProof's is a darker, bluer ink. |

### Secondary

| Reference | Taking | Not taking |
| --- | --- | --- |
| **aicss.dev** (UI for AI agents) | Patterns, rebuilt on our own primitives: the thinking and step list for the run panel, inline numbered citations with a source list (the basis of the source line and the printed footnotes), the approval card for approve-and-send, a file-diff presentation for the assessment diff. | Its Pro components are licensed and the site asks agents not to reconstruct them from previews; none of its source is to be copied. Chat-bubble framing: DealProof is a case file, not a conversation. |
| **orbs.jakubantalik.com** (now `libraries.dev/orbs`, package `thinking-orbs`, MIT) | One small "analyst working" indicator in the run header, in the searching or thinking state, in ink. See section 9 and the open decisions. | Orbs as decoration, large orbs, coloured or glowing orbs, an orb on every loading state. |
| **loading.dev** | A single small, linear loader shape (Scan or Trace style) as the fallback for the run indicator and for inline row loading. | The other thirty-odd shapes. One loader in the whole product. |
| **cuelume-site.pages.dev** (interaction sounds, about 9 kB, synthesised) | At most three cues, off by default: run finished, request approved and sent, error. See section 9. | Tap, type, toggle and navigation sounds. An analyst's office and a CFO's meeting are not places for a clicking interface. |
| **blocks.so** | shadcn-based blocks as starting structure for the sidebar, command menu, dialogs, tables and file upload, restyled with these tokens. | Any block used unstyled. |
| **beui.dev, rareui.com, amicro.vercel.app, ui.watermelon.sh** | Small Motion-based mechanics only: number tween, list stagger, a button that settles into a receipt, an animated tab indicator. Take the mechanics and write them with our easing and durations. | 3D cards, gravity letters, morphing blobs, text effects, hover scales, anything springy. |
| **glimm.dev** (shader page transitions) | Nothing in the app. Its own guidance says to keep the sweep for significant events, and none of ours needs a WebGL band. | Route transitions with a shader sweep. |
| **canvasui.dev** | Nothing. | ASCII objects, liquid, VHS, glass refraction. They say nothing about evidence. |
| **originkit.dev** | Nothing specific; it is a Framer-oriented catalogue of decorative effects. | All of it. |
| **inspora.design, collectui.com, bestdesignsonx.com** | General calibration for table density, empty states and settings layouts. | Trend-led visual styles. |

## 3. Typography

Three families from two type systems. IBM Plex Sans and IBM Plex Mono are one superfamily and are treated as the interface face and its figure face; Newsreader is the single partner.

| Role | Family | Used for |
| --- | --- | --- |
| Interface | **IBM Plex Sans** (400, 500, 600) | Everything in the app: navigation, tables, forms, buttons, body text |
| Figures and meta | **IBM Plex Mono** (400, 500) | As-of dates, retrieved-at times, counts, credits, currency, source ids, version labels, keycaps |
| Voice | **Newsreader** (400, 500, optical sizes on) | Marketing headlines, the memo title and its section heads, the printed memo. 24px and up only; never labels, buttons or table text |

Why these: Plex was drawn for technical and institutional documents, has true tabular figures and reads well at 13px in a table; it also avoids the look of the default sans every generated interface ships with. Newsreader is a text serif built for long reading on screens, which gives the memo the voice of a written opinion and prints well. All three are free and load through `next/font/google`, which needs no extra package.

### Scale

| Token | Size / line | Weight | Use |
| --- | --- | --- | --- |
| `text-2xs` | 11 / 16 | 400 mono | The floor. Meta inside source chips |
| `text-xs` | 12 / 16 | 400 to 500 | Table headers, counts, captions |
| `text-dense` | 13 / 20 | 400 | Ledger and table cells, secondary text |
| `text-sm` | 14 / 20 | 400 to 500 | Interface body, nav, buttons, inputs |
| `text-base` | 16 / 24 | 400 | Reading body: memo prose, marketing body |
| `text-lg` | 18 / 28 | 400 | Lead paragraph, hero subhead (ink-secondary, max 36rem) |
| `text-xl` | 20 / 28 | 500 | Card title, section head in the app |
| `text-2xl` | 24 / 32 | 500 | Page title in the app |
| `text-3xl` | 32 / 40 | 500 sans tabular, or 400 serif | Key figure; memo title |
| `text-4xl` | 44 / 48 | 400 serif | Marketing section head; hero on mobile |
| `text-5xl` | 64 / 68 | 400 serif | Hero on desktop |

Rules

- Hierarchy comes from size and ink role, not weight. 600 appears in two places: the disposition stamp and a key figure.
- Sentence case everywhere. No uppercase tracked labels. No italics for emphasis. Newsreader italic is allowed only for a quoted seller claim in the printed memo.
- Letter spacing is 0 below 44px; `-0.02em` at 44px and above.
- All numerals use `font-variant-numeric: tabular-nums`. Dates are written one way everywhere: `14 Oct 2026`, and `Oct 2026` when only the month is known. Times are `14 Oct 2026, 16:42 IST`. Currency follows the source's currency and never mixes precision in one column.
- Tailwind's `text-sm`, `text-base`, `text-lg`, `text-xl`, `text-2xl` and `text-xs` keep their usual sizes so shadcn components are not silently resized. `text-2xs` and `text-dense` are additions; `text-3xl` to `text-5xl` are redefined.

## 4. Colour

Light theme only in v1. **Dark is out of scope**: the memo is printed, the demo is projected, and one theme done exactly is worth more than two done loosely. Tokens are semantic (paper, ink, line, status roles), so a dark theme is a second set of values later, not a refactor. See the open decisions.

### Neutrals

| Token | Value | Role |
| --- | --- | --- |
| `paper` | `#F7F7F5` | App page background |
| `paper-warm` | `#F5F2EA` | Marketing page and printed memo cover only |
| `surface` | `#FFFFFF` | Cards, tables, sheets |
| `surface-raised` | `#F0F0ED` | Active row, hover, input fill |
| `surface-sunken` | `#EBEBE7` | Wells, table header band |
| `ink` | `#16181D` | Primary text; primary button fill |
| `ink-secondary` | `#454A54` | Secondary text |
| `ink-muted` | `#626771` | Meta, captions, icons |
| `line` | ink at 9% | Hairlines |
| `line-strong` | ink at 18% | Input borders, rules that must survive printing |

App surfaces stay grey. The world shows in the accent, the status marks and the two moments, never in a tinted background.

### Accent

`accent` `#24408E`, a registrar's ink blue. It marks links, the selected row and nav item (with `accent-tint` `#E9EDF8`), the focus ring, and at most one figure per screen. The **primary button is ink, not accent**: `ink` fill with white text. The secondary button is `surface` with a `line-strong` border.

The accent is deliberately not a status colour. Blue never means "good".

### Contrast, measured

| Pair | Ratio |
| --- | --- |
| ink on paper | 16.6 : 1 |
| ink-secondary on paper | 8.3 : 1 |
| ink-muted on paper / surface / surface-raised / surface-sunken | 5.3 / 5.7 / 5.0 / 4.8 : 1 |
| white on ink (primary button) | 17.8 : 1 |
| white on accent | 9.6 : 1 |
| accent on paper | 8.9 : 1 |
| each status ink on its own tint | 5.7 to 8.4 : 1 |
| each status ink on white | 6.3 to 9.6 : 1 |

Status border colours are decorative (1.5 to 1.8 : 1) and never carry meaning alone; the glyph and the label do. The Not checked border is the exception at 3.1 : 1, because its dashes are part of the signal.

## 5. Spacing, radii, elevation, grid

**Spacing.** A 4px grid. Tokens: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96, 128. Inside a control 4 to 12; between related rows 0 to 8; between groups 12 to 24; between app sections 32 to 48; between marketing sections 96 to 128. Space inside a group is always smaller than the space around it. One-off values such as 13 or 11 are not used.

**Row heights.** 32 compact (nav rows, dense tables), 36 default (controls, ledger rows collapsed to one line), 44 touch and hero buttons.

**Radii.** 4 source chip, tag, keycap · 6 status mark, disposition stamp · 8 button, input, row · 12 card · 16 panel, dialog, the product window on the home page. Inner radius = outer radius minus the padding between them, never below 4. Round is reserved for avatars and the run pulse dot.

**Elevation.** Three levels and hairlines.

| Level | Token | Use |
| --- | --- | --- |
| 0 | `line` border, no shadow | Most things: tables, cards in a grid, the ledger |
| 1 | `shadow-xs` | Buttons, a card that is the main object of a page |
| 2 | `shadow-md` | Popovers, the evidence drawer, the sticky assessment rail when content scrolls under it |
| 3 | `shadow-lg` | Dialogs; the product window on the home page |

Shadows are neutral ink at low opacity. No coloured shadows.

**Grid and breakpoints.**

| Breakpoint | Width | App | Marketing |
| --- | --- | --- | --- |
| base | under 640 | Sidebar becomes a menu sheet; single column; ledger rows stack claim over evidence; page padding 16 | 4 columns, 16 padding |
| `sm` | 640 | Same, two-column stat rows | 8 columns |
| `md` | 768 | Sidebar collapsed to 56 icons; page padding 24 | 8 columns, 24 padding |
| `lg` | 1024 | Sidebar 248; 12 columns, 24 gutter; page padding 32; assessment rail drops below content | 12 columns |
| `xl` | 1280 | Assessment rail 320 beside content | Content capped at 1200 |
| `2xl` | 1536 | Content capped at 1440, left-aligned next to the sidebar | Same |

The app fills the viewport: sidebar plus fluid content. It is never shrunk into a centred narrow column. Memo prose is the one place with a reading measure, capped at 680px.

## 6. The status system

The rule for the whole system: **meaning is carried by shape and words; colour only reinforces.** Every status renders as glyph + label, and each glyph has a different silhouette so the set reads in greyscale, in print and for colour-blind readers.

### 6.1 Claim statuses

| Status | Glyph (16px, custom set; lucide fallback) | Silhouette | Ink / tint | Border | Fill |
| --- | --- | --- | --- | --- | --- |
| **Supported** | Check in a filled circle (`circle-check`) | Solid circle | `#17663A` / `#EAF5EE` | Solid | Flat |
| **Contradicted** | Cross in a filled octagon (`octagon-x`) | Solid octagon | `#A3241C` / `#FBECEA` | Solid | Flat |
| **Partially corroborated** | Circle, left half filled (`contrast`) | Half-filled circle | `#7D4B00` / `#FBF1DC` | Solid | Flat |
| **Conflicting evidence** | Diamond with two opposed arrows (`diamond` + `arrow-left-right`) | Diamond | `#7A2E86` / `#F6EBF7` | Solid | Flat |
| **Cannot verify** | Question mark in an open ring (`circle-help`) | Open ring, solid stroke | `#3B4656` / `#EDF0F4` | Solid | Flat |
| **Not checked** | Dashed ring, empty (`circle-dashed`) | Broken ring | `#5C6068` / hatch over `#F4F4F1` | **Dashed** | **Hatched** |

A custom six-glyph SVG set should be drawn at the next checkpoint so stroke weight and optical size match; the lucide names are the fallback and must be checked against the installed lucide version (some were renamed between releases).

Three forms, one component (`StatusMark`):

- **Mark**: glyph only, 16px, with an accessible name. Used on the ledger spine and in dense tables, always with a legend or a tooltip and with the label present in the row's expanded view.
- **Tag**: glyph + label, 24px tall, radius 6, tint fill, 1px border. The default.
- **Count**: glyph + mono number, for summaries ("3 Supported").

Ordering in any summary is fixed: Supported, Partially corroborated, Conflicting evidence, Contradicted, Cannot verify, Not checked. Not checked is always last and always set apart.

**Cannot verify is a finished answer.** It gets a solid border and a flat fill like the other settled statuses, and it must always be followed by "What would settle it" naming the document. It is never styled as an error and never greyed out.

**Not checked must look incomplete.** All of the following, together:

- A dashed border and a diagonal hatch fill (`--pattern-hatch`). No other status uses either.
- No hue. It never borrows green, and it never borrows the Cannot verify slate.
- The reason is always visible next to it, in words: "Not checked · budget reached", "Not checked · source unavailable", "Not checked · step failed".
- In any distribution bar its segment is hatched and sits after a visible gap, so the bar reads as unfinished.
- It is excluded from every "settled" count, and the count says so: "9 of 12 checks settled · 3 not checked".
- A case with any Not checked claim shows a persistent line in the case header: "3 checks were not run" with a link to them. No summary surface (dashboard row, memo first page, printed header) may omit it.
- Where a Not checked item can be retried, the row offers "Run check", which costs credits and says so.

### 6.2 Dispositions

A disposition is a **stamp**, not a tag: 32px tall (40px in the case header), radius 6, 1.5px solid border in its ink, tint fill, label at 14px weight 600, glyph on the left. The stamp form appears only for dispositions, so a disposition is never mistaken for a claim status even where the hue is shared.

| Disposition | Glyph (lucide) | Ink / tint | Notes |
| --- | --- | --- | --- |
| **Prioritise** | `arrow-up-right` | `#17663A` / `#EAF5EE` | |
| **Investigate further** | `search` | `#7D4B00` / `#FBF1DC` | |
| **Deprioritise** | `arrow-down-right` | `#3A3D44` / `#EBEBE7` | Graphite, not red. Red means a claim was Contradicted; Deprioritise can follow from poor fit on good evidence |
| **Cannot assess** | `circle-help` | `#3B4656` / `#EDF0F4` | Same family as Cannot verify. Solid border: it is a real outcome |

A stamp never appears without its reasons directly beneath it (one to three lines, each with a source line or a link to the claims it rests on) and the policy version that produced it. Because missing evidence alone never yields Deprioritise, a Deprioritise stamp must name the requirement that verifiably failed or the evidence the poor fit rests on.

### 6.3 Estimates and signals

Any value that is not a recorded fact is marked in three ways at once:

- A leading tilde: `~180`.
- A dotted underline in `estimate` ink.
- A word tag right after it in mono 11px: `Estimate` or `Signal`, with the basis on hover and in the expanded row: "Estimate · from professional profiles, not a payroll count".

`Estimate` is for a number inferred from indirect data (team size from profiles). `Signal` is for an observation that suggests something without proving it (hiring activity, headcount trend). In charts, an estimated series is a dashed line and the legend repeats the word. Hiring and headcount never appear under a heading that implies revenue or traction; their section is titled "Operating signals".

### 6.4 Identity

Identity is shown before anything else in a case, as a band under the case title.

- **Identity confirmed**: `badge-check` glyph, ink text on `surface`, followed by the matching keys that confirmed it, each with a source line: domain, legal name, registration number, registered city, founded year. No green wash; the keys are the proof.
- **Identity unresolved**: `circle-help` glyph in Cannot verify slate, a solid-bordered band across the top of the case, the candidate entities listed side by side with the keys that match and the keys that differ, and one action: "Choose the entity". Until resolved, identity-dependent tabs show their content area replaced by "Waiting on identity" with the same glyph, and the disposition is Cannot assess. Nothing is attached to a company on a name match, and the interface says which key was used for each attachment.
- For people (founders, leadership): the same pattern in miniature. A career record carries "matched on company id + name"; a name-only match is not shown as a record at all, only as "possible match, not attached".

### 6.5 The source line

Every rendered fact ends in a source line. It is the signature of the product.

```
Incorporated 2014, Pune   [▤ Registry mirror · as of 12 Mar 2014]
~180 people  Estimate     [◔ Crustdata profiles · as of Oct 2026]
Raised Series A           [▤ Funding record · 3 Jun 2025] [✎ Announcement · 5 Jun 2025]
```

Anatomy of the chip (22px tall, radius 4, `surface-raised` fill, `line` border, 12px text):

1. **Class glyph**, 14px, one per reliability class from the spec: registry, audited statement, counterparty confirmation, company announcement, professional-profile signal, news, seller document, seller statement.
2. **Source name** in Plex Sans 12px: short, human ("Registry mirror", "Crustdata profiles", "Seller deck p. 7").
3. **As-of date** in Plex Mono 11px, always prefixed "as of": the date of the underlying fact, not the retrieval.

Behaviour

- Click or Enter opens the **evidence popover** (the drawer on small screens): the exact quote or field path and value, the reliability class in words with what that class is strong and weak on ("A company announcement shows that it announced something, not that it happened"), the URL or request, `retrieved 22 Nov 2026, 16:42 IST`, and the entity it was attached to with the identity key used.
- Several sources for one fact sit side by side, at most two visible and then "+2".
- A secondary mirror of a registry says so in the name ("Registry mirror"), never "Registry".
- When the as-of date is unknown, the chip reads "as of unknown date" in muted ink. It is not left blank.
- **No source, no render.** The `Fact` component takes a required evidence reference. In development a missing one renders a visible "Unsourced" error block; in production the fact is omitted and the omission logged. Memo prose drafted by the model uses numbered citations that resolve to the same chips; a sentence with a figure and no citation fails rendering in the same way.

## 7. Core patterns

### 7.1 Fit and assessable: the criteria strip

The two numbers are one component (`FitReadout`) and cannot be rendered apart. Text form, always in this order and wording:

```
Fit 82 · 70% of criteria assessable
```

Visual form: one track whose full width is all criteria, weighted. Each criterion is a cell.

```
 Fit 82                                   70% of criteria assessable
 ┌────┬────┬────┬────┬──┬──────┬────┬╌╌╌╌╌╌┬╌╌╌╌┬╌╌╌╌╌╌╌┐
 │████│████│████│████│  │██████│████│╱╱╱╱╱╱│╱╱╱╱│╱╱╱╱╱╱╱│
 └────┴────┴────┴────┴──┴──────┴────┴╌╌╌╌╌╌┴╌╌╌╌┴╌╌╌╌╌╌╌┘
  met  met  met  met  not  met   met   unknown · could not assess
                      met
  7 of 10 criteria assessable · 3 unknown: ownership, customer type, revenue band
```

- Met: ink fill. Not met: empty cell with a solid border. Unknown: hatched with a dashed border, grouped at the right end.
- Must-have criteria carry a small notch on their top edge; a failed must-have never appears here because a verifiable fail removes the company from the shortlist.
- Hover or focus on a cell names the criterion, its verdict and its source line.
- "Fit 82" is set in mono 500; "70% of criteria assessable" is the same size and the same ink. The second number is never smaller, lighter or hidden behind a tooltip.
- Compact form for shortlist rows: the strip at 6px tall with the text beside it. The hatch survives at that size through `--pattern-hatch-dense`.
- Fit says how well the company matches the requirements. The label under the strip on the case page says so: "Fit measures match to your criteria. It says nothing about returns".

### 7.2 The five-judgment panel

Five judgments, five different shapes, no sum. They sit in one panel so they are read together, and they are drawn differently so they cannot be averaged by eye.

```
┌─ Assessment · version 2 · policy 1.0 · 22 Nov 2026, 16:42 IST ───────────────────────────┐
│                                                                                           │
│  Opportunity fit            Evidence sufficiency          Business assessment             │
│  Fit 82 · 70% assessable    9 of 12 required checks       Operating signals               │
│  [criteria strip]           settled · 3 not checked       ~180 people  Estimate           │
│                             [●●●●●●◐◐◇ ?? ╱╱╱]            Headcount up over 12 months     │
│                             Gaps: payroll, lender         Signal                          │
│                             statement, occupancy          2 open roles  Signal            │
│                                                           Planned facility, Oct 2026      │
│  ───────────────────────────────────────────────────────────────────────────────────     │
│  Financial assessment                        Screening disposition                        │
│  ┌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┐        ┌──────────────────────────┐                 │
│  ╎ Not assessed                     ╎        │ ⌕ Investigate further    │                 │
│  ╎ No reliable financial inputs     ╎        └──────────────────────────┘                 │
│  ╎ Would need: audited statements   ╎        Strong fit; 3 of 6 claims open.              │
│  └╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┘        Rests on: claims 2, 5, 6                      │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

- Opportunity fit: the criteria strip. A number with its assessable share.
- Evidence sufficiency: a count ("9 of 12 required checks settled"), a distribution bar of status glyphs in the fixed order with the Not checked segment hatched after a gap, and the named gaps. Not a percentage ring.
- Business assessment: a short list of dated signals, each labelled Signal or Estimate, each with a source line. No score.
- Financial assessment: when inputs are missing, a dashed, hatched block reading "Not assessed · no reliable financial inputs" and what would be needed. It keeps its place in the panel so its absence is seen.
- Screening disposition: the stamp, its reasons, the claims it rests on.

The panel has no overall heading score, no colour for the panel as a whole, and no ordering that implies one judgment is the total of the others. In the sticky rail of the case view it compresses to five one-line rows in the same order.

### 7.3 The claim ledger row

A ledger with two sides and a spine. This is the main moment of the product.

```
     Seller said                         │      │  The record shows
─────────────────────────────────────────┼──────┼────────────────────────────────────────────────
 1   "Incorporated in 2014, based        │  ●   │  Incorporated 2014, registered office Pune
      in Pune"                           │ Sup- │  [▤ Registry mirror · as of 12 Mar 2014]
      Identity · [Seller deck p. 2]      │ ported│
─────────────────────────────────────────┼──────┼────────────────────────────────────────────────
 2   "We employ 250 people"              │  ?   │  ~180 people  Estimate
      Team size · [Seller deck p. 4]     │Cannot│  [◔ Crustdata profiles · as of Oct 2026]
                                         │verify│  Warehouse staff rarely have professional profiles
                                         │      │  What would settle it: dated payroll summary
─────────────────────────────────────────┼──────┼────────────────────────────────────────────────
 5   "We opened a new facility in        │  ◐   │  Announcement describes a planned facility
      October 2026"                      │Partly│  [✎ Company announcement · 9 Sep 2026]
      Dated events · [Seller deck p. 9]  │ corr.│  Supported: a facility was announced
                                         │      │  Not supported: that it is operating
─────────────────────────────────────────┼──────┼────────────────────────────────────────────────
 7 ╱╱"Our top customer is a national ╱╱╱ ┊  ◌   ┊  Not checked · budget reached
   ╱╱ retailer"╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱╱ ┊ Not  ┊  No search was run for this claim
      Customers · [Seller deck p. 11]    ┊checked┊  [Run check · about 4 credits]
```

- **Left, 5 columns**: the claim in the seller's words in quotation marks, its category, and a source line pointing at the document and page (or "Typed by Asha Rao, 22 Nov 2026").
- **Spine, fixed 96px**: the status mark with its label under it. The spine is a continuous vertical band down the ledger, so scanning it gives the shape of the case. On a Not checked row the spine cell is hatched and its borders are dashed.
- **Right, 7 columns**: what the record shows, in DealProof's words, each statement with its source line. For Partially corroborated the right side is split into "Supported" and "Not supported". For Conflicting evidence the disagreeing sources sit side by side with what each says. For Cannot verify and Partially corroborated it ends with "What would settle it" and the document name, which is also what feeds the request list.
- Rows are 13px, padded 12 vertically, separated by hairlines. Collapsed to two lines per side by default; Enter or click expands in place.
- Row states are distinct: hover is `surface-raised`; keyboard focus is a 2px accent ring inside the row; selected (for adding to the request) is `accent-tint` with a 2px accent bar on the left edge; a row changed in the current assessment version carries a small "Changed in v2" mono tag that links to the diff.
- Above the ledger: a filter by status (the six tags as toggles, with counts), a filter by category, and a legend line for the glyphs. Not checked rows cannot be filtered out of the default view.
- Under 1024px each row stacks: claim, then status tag, then the record.

### 7.4 Assessment version diff

New evidence changes the assessment in the open; the earlier view stays readable.

```
 Assessment history
 ○ v1 · 20 Nov 2026, 11:05 IST · initial screening
 │
 ● v2 · 22 Nov 2026, 16:42 IST · after "Lease agreement.pdf" from seller
 
 What changed in v2                                           [Compare v1 and v2 ▾]
 ──────────────────────────────────────────────────────────────────────────────────────
 Claim 5  "We opened a new facility in October 2026"
          ◐ Partially corroborated  →  ● Supported
          Because: lease start 1 Oct 2026 and occupancy certificate
          [▣ Seller document · Lease agreement p. 3 · as of 1 Oct 2026]
 
 Evidence sufficiency   9 of 12 settled  →  10 of 12 settled
 Screening disposition  [⌕ Investigate further]  →  [↗ Prioritise]
          Because: the facility claim was the last open required check for fit
 
 11 claims unchanged  [Show]
```

- A vertical version rail with dated nodes; the current version is a filled node. Any version can be opened read-only, with a banner "You are reading version 1. Version 2 is current".
- A change is always shown as **old → new** with both rendered in full: the old value keeps its real status mark with the label struck through on a `diff-removed` background; the new one sits on `diff-added`. The arrow is a glyph and the words "changed from" are in the accessible name.
- Every change carries "Because" and a source line. A change with no stated cause is a bug and renders as an error block.
- Unchanged items are collapsed into a count. A downgrade (for example Supported to Conflicting evidence) is presented identically to an upgrade: no celebration for good news and no softening of bad news.
- The same change summary heads the memo when the current version is not the first.

### 7.5 Approve and send once

```
 Request to seller                                    Draft → Approved → Sent
 ┌─ Test mode ─────────────────────────────────────────────────────────────────────┐
 ╎ ╱╱ Email sending is off. Approving records the approval. Nothing will leave. ╱╱ ╎
 └╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┘
 Documents requested (3)                       Message
 ☑ Dated payroll summary      ← claim 2        To      [ seller address, typed by you    ]
 ☑ Lender statements          ← claim 6        Subject [ Information request: ...        ]
 ☑ Lease or occupancy record  ← claim 5        [ editable draft                          ]
 
 Approver  Asha Rao (signed in)                [ Approve and send once ]
 This sends one email. It cannot be sent again from this case.
```

1. **Draft.** The request list on the left, each document tied to the claim it would settle. The drafted message on the right, editable, marked "Drafted by DealProof, edit before approving". The recipient field is empty until a person types it; DealProof does not suggest an address.
2. **Approve.** The button reads "Approve and send once" and is enabled only for a signed-in named user with a recipient entered. It opens a confirmation dialog that restates the recipient, the three documents and the approver's name, with "Send once" and "Go back". This is the one place a dialog interrupts.
3. **After.** The button is removed, not disabled. In its place is a receipt, which is permanent and read-only:

```
 ┌──────────────────────────────────────────────────────────────┐
 │ ✓ Sent once                                                  │
 │ Approved by Asha Rao · 22 Nov 2026, 16:48 IST                │
 │ To seller address · 3 documents requested · [View message]   │
 └──────────────────────────────────────────────────────────────┘
```

**Test mode, shown honestly.**

- While `EMAIL_SEND_ENABLED` is false, a hatched, dashed banner sits at the top of the Request tab and a "Test mode" tag sits in the app top bar on every page.
- The button reads "Approve (test mode, nothing is sent)".
- The receipt is hatched and dashed, uses the Not checked visual family and a struck-through envelope glyph, and reads: "Suppressed (test mode) · not sent · Approved by Asha Rao · 22 Nov 2026, 16:48 IST". It never shows a check mark, never uses green and never uses the word "Sent" on its own.
- The stepper's last step reads "Suppressed" in place of "Sent".
- A failed send reads "Failed · not sent" with the provider's reason and no automatic retry; retrying is a new, explicit approval.

### 7.6 Run progress: the analyst working

Runs are made of persisted steps, streamed over SSE. The interface shows the work, in order, as it happens, in a panel docked at the top of the page that started it.

```
 ◍ Analyst working · Verify · Meridian Warehousing            2 min 14 s · 38 of 150 credits
 ────────────────────────────────────────────────────────────────────────────────────────────
 ✓ Confirm identity                    matched on domain + registration number        0 cr
 ✓ Build public profile                Crustdata company record                       4 cr
 ✓ Read seller deck                    12 claims extracted from 14 pages              $0.03
 ▸ Gather evidence                     claim 7 of 12 · searching dated announcements
 ○ Extract facts
 ○ Apply status rules
 ○ Evaluate
```

- Step states: pending (open ring), running (the indicator and a live sub-line), done (check, with a one-line result and its cost), failed (cross, reason, "Retry step"), skipped for budget (dashed ring, hatched row, "Skipped · budget reached", which becomes Not checked on the claims).
- The header carries the single "working" indicator, elapsed time and the live credit count against the budget.
- As evidence arrives, ledger rows below fill in: a row appears with its claim on the left, a pending spine, and the status mark settles when the rule fires. The page is usable while the run continues.
- **Resume is visible.** After an interruption the panel reads "Resumed 16:51 IST · 5 steps kept, continuing from Gather evidence" and replayed steps show "from cache · 0 cr".
- When the run ends the panel collapses to one line, "Verify finished · 2 min 51 s · 61 credits · 2 checks not run", and stays on the page as a link to the full run log.
- Steps are a live region (`aria-live="polite"`), announced once per step change, not per sub-line.
- No fake progress bar and no percentage: the step list is the progress.

### 7.7 Cost of the case

```
 This case cost
 86 of 150 credits                $0.42 model usage
 [████████████████████░░░░░░░░░░░░░░]   57% of the credit budget
 
 Run              Step                    Credits    Model      When
 Verify           Build public profile        4        –        22 Nov, 16:39
 Verify           Gather evidence            48        –        22 Nov, 16:40
 Verify           Extract facts               –      $0.18      22 Nov, 16:41
 Verify (resumed) Gather evidence      0 · cache       –        22 Nov, 16:51
 ...
 Total                                       86      $0.42
```

- One sentence first, in mono figures: "86 of 150 credits · $0.42 model usage". The two currencies are never added together.
- A single progress bar for credits against the budget. This is a legitimate use of a bar: a goal with a limit.
- A table by run and step, numbers right-aligned in one column each, cached calls shown as "0 · cache".
- When the budget is reached the bar is full, the sentence reads "Budget reached · 3 checks not run", and it links to the Not checked claims. The colour does not turn red; running out of budget is a stated limit, not an error.
- The compact form ("86 cr · $0.42") sits in the case header and the dashboard row.

## 8. Components and libraries

So implementation stays consistent, the web app uses this set and nothing else for the same job. All are project-local dependencies of `apps/web`; none is installed by this checkpoint.

| Job | Use | Notes |
| --- | --- | --- |
| Styling | **Tailwind CSS v4** with `@theme` from `tokens.css` | No arbitrary colour or spacing values in components; if a value is missing, add a token |
| Primitives | **shadcn/ui** (Radix-based), copied into `apps/web/components/ui` | Restyled once with these tokens: Button, Input, Textarea, Select, Checkbox, Tabs, Dialog, Popover, Tooltip, Sheet, DropdownMenu, Command, Table, Badge, Separator, ScrollArea, Skeleton, Sonner |
| Icons | **lucide-react**, 16px, stroke 1.5, in the ink role of the adjacent text | Plus the custom six-glyph status set and the source-class glyphs as local SVG components |
| Motion | **Motion** (`motion`, imported from `motion/react`) | One shared `transitions.ts` exporting the easing and durations from the tokens; `MotionConfig reducedMotion="user"` at the root |
| Tables | Plain semantic tables through the shadcn Table; **TanStack Table** only for the shortlist, which needs sorting and column control | The ledger is a custom grid, not a data table |
| Chart | **Recharts** through the shadcn chart wrapper, for the one headcount series | One chart type in v1: a line, dashed when the series is an estimate |
| Command menu | shadcn Command (cmdk) | `⌘K`: jump to case, new thesis, new case |
| Toasts | Sonner | Confirmations only. A send result is a receipt on the page, never only a toast |
| Fonts | `next/font/google` | IBM Plex Sans, IBM Plex Mono, Newsreader, exposed as `--font-plex-sans-face`, `--font-plex-mono-face`, `--font-newsreader-face` |
| Run indicator | `thinking-orbs` (MIT) in one place, or the plain CSS loader | Pending the open decision |
| Sounds | `cuelume`, off by default, or none | Pending the open decision |

Product components to build on top (names fixed now so pages can be planned against them): `SourceLine`, `EvidencePopover`, `Fact`, `StatusMark`, `StatusDistribution`, `DispositionStamp`, `EstimateValue`, `IdentityBand`, `FitReadout` (criteria strip), `JudgmentPanel`, `ClaimLedger` / `ClaimRow`, `VersionRail`, `AssessmentDiff`, `RequestList`, `ApprovalReceipt`, `TestModeBanner`, `RunPanel`, `CostReadout`, `CriteriaEditor`, `ShortlistRow`, `InvestorRow`, `MemoPage`.

Controls: buttons are 36px tall in the app (32 in dense toolbars, 44 on the home page), radius 8, side padding 16. Primary is ink with white text and `shadow-xs`. Secondary is `surface` with a `line-strong` border. A quiet text button exists for tertiary actions. Destructive actions use the Contradicted ink as text on a secondary button, with a confirmation. Every interactive element has a hover state and a visible 2px accent focus ring with a 2px offset.

## 9. Motion and sound

### Principles

1. **Motion reports work or change. It never decorates.** If nothing happened, nothing moves.
2. One curve, `cubic-bezier(0.22, 1, 0.36, 1)`, and three durations: 140ms for feedback, 200ms for small state changes, 360ms for entrances and layout.
3. Only `opacity`, `transform`, `color`, `background-color` and `border-color` animate, named explicitly. No `transition-all`, no animated width, height or margins (layout changes go through Motion's `layout`).
4. Nothing loops except the single run indicator while a run is live.
5. Good and bad news move the same way.

### Specific animations

| Where | Motion | Reduced motion |
| --- | --- | --- |
| Page load | Main content fades and rises 8px over 360ms, once. Sidebar and top bar do not animate | Appears instantly |
| Ledger reveal | Rows fade and rise 8px, 40ms apart, first six only; the rest appear with the sixth | All rows appear at once |
| Status mark settling | When a claim's rule fires during a run: the pending ring fades out, the mark fades in and scales from 0.9 to 1 over 200ms. The label crossfades | Mark and label swap instantly |
| Criteria strip | Cells fill left to right, 40ms apart, hatched cells last; "Fit" counts up to its value over 360ms | Final state drawn, number shown at its value |
| Run steps | The running step's indicator is live; on completion its check draws in over 200ms and the next step's row lifts to ink from muted | State changes without transition; indicator replaced by the word "Working" |
| Credit counter and figures that change | Number tweens to the new value over 360ms with tabular figures so width does not jump | Jumps to the value |
| Assessment diff | On opening a new version, each changed row gets a one-time `accent-tint` background that fades over 1200ms; old value slides 8px left and new value fades in | Changed rows keep a static "Changed" tag; no fade |
| Approve and send | On success the button's container changes shape into the receipt through a shared layout animation over 360ms; the receipt text fades in | Button is replaced by the receipt instantly |
| Popover, drawer, dialog | Fade and 4px rise from the trigger over 200ms; the evidence drawer slides 16px with a fade over 360ms; scrim fades | Fade only, 0ms |
| Hover and press | Background or border colour over 140ms; press scales to 0.98 | Colour change only, instant |
| Tabs in the case view | The underline indicator moves to the new tab over 200ms; content crossfades | Indicator and content swap instantly |
| Home page | The hero ledger's status marks settle once, in order, 200ms apart, after the page has loaded; step tabs crossfade. Nothing else scrolls into view with an effect | Ledger drawn in its final state |

Not used anywhere: pulsing or pinging dots, shimmer on headings, skeleton shimmer longer than two seconds (after that a skeleton becomes a static "Still working" line), parallax, floating elements, hover scale on cards, spring overshoot, shader page transitions, typewriter text.

### The "analyst working" indicator

One indicator in the product, in the run panel header only, 16 to 20px, in ink. The recommendation is the `thinking-orbs` component in its searching or thinking state, monochrome, because it was suggested and because a small moving mark that means "work is happening right now" is information. It must be removed when the run ends, must not appear on the home page as decoration, and under reduced motion it is replaced by the word "Working". If the dependency is not wanted, a 16px linear CSS loader in the Scan style does the same job.

### Sound

Interaction sounds mostly do not fit. The product is used in shared offices and shown in meetings, and a sober tool does not click. The recommendation:

- **Off by default.** A setting, "Sounds for finished runs and sends", per user.
- When on, three cues only: a run finished, a request was approved and sent (or suppressed, which uses the neutral cue, not the success cue), and an error that needs attention. No tap, type, toggle, hover or navigation sounds.
- Never the only signal: every cue accompanies a visible, announced state change.
- For the ContextCon demo it may be worth turning on for the run-finished cue alone, since a judge hears the analyst finish. That is a presentation choice; see the open decisions.

## 10. Copy rules

- Headlines say what the product does for whom. No hype words, no "AI-powered" as a label, no exclamation marks, no greeting headlines.
- Headings, labels and buttons end without a period. Paragraphs keep theirs.
- Labels are short: "Search", "New thesis", "Run check".
- The product's own terms are used exactly and never varied: Supported, Contradicted, Partially corroborated, Conflicting evidence, Cannot verify, Not checked; Prioritise, Investigate further, Deprioritise, Cannot assess; Estimate, Signal; Fit, assessable.
- Uncertainty is stated in plain words with what would resolve it. "Cannot verify. A dated payroll summary would settle it" and never "Unable to confirm at this time".
- Illustrations are labelled. The PRD's Pune example appears only under "Illustration, not a real company".
- No claims about customers, accuracy or speed that are not measured.

## 11. Page inventory

Layouts are low fidelity. Widths refer to the `xl` breakpoint unless noted.

Every company, investor and person named in these layouts is a placeholder to show density and wording. The app shows only records returned by live sources, and the one invented case (the PRD's Pune example) appears only under the label "Illustration, not a real company".

### 11.1 Marketing home page

Inspired by sarvam.ai's structure: a centred serif hero, then the product shown working, then numbered explanations. Background `paper-warm`; the product window is the one bright element.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ DealProof            How it works   The claim ledger   Principles        Log in  [Open app] │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                              │
│                         First-pass screening for investors and acquirers                     │
│                                                                                              │
│                          Know what is proven before                                          │
│                              the second meeting                         (Newsreader 64)      │
│                                                                                              │
│          DealProof finds companies that match your thesis, checks each claim against         │
│          dated, independent evidence, and says plainly what it could not verify              │
│                                                                                              │
│                         [ Start a screening ]   [ See a finished case ]                      │
│                                                                                              │
│      ┌─ Meridian Warehousing · Claims ───────────── Illustration, not a real company ─┐      │
│      │  Seller said                    │      │  The record shows                      │      │
│      │  "Incorporated in 2014, Pune"   │  ●   │  Registry record states both  [▤ …]    │      │
│      │  "We employ 250 people"         │  ?   │  ~180 Estimate · request payroll [◔ …] │      │
│      │  "Opened a facility Oct 2026"   │  ◐   │  Announced as planned  [✎ …]           │      │
│      │  "We have no debt"              │  ?   │  A registered security is on record    │      │
│      └─────────────────────────────────┴──────┴────────────── runs past the fold ─────┘      │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│  Four steps, one case                                                                        │
│  ┌ Discover ┬ Verify ┬ Evaluate ┬ Act ┐   (tabs; each shows the real component)              │
│  │ left: 2 sentences + what you give / what you get     right: live component preview       │
│  │ Discover → criteria editor + 3 shortlist rows with the criteria strip                    │
│  │ Verify   → run panel + ledger rows settling                                              │
│  │ Evaluate → five-judgment panel                                                           │
│  │ Act      → request list + approval receipt                                               │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│  Six answers, including the honest ones                                                      │
│  ● Supported   ◐ Partially corroborated   ◇ Conflicting evidence                             │
│  ⬣ Contradicted   ? Cannot verify   ◌ Not checked (hatched)                                  │
│  wide left cell: "Cannot verify is a real answer"   right cell: "Not checked never looks     │
│  clean", shown with the hatched row                                                          │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│  Fit is not evidence                                                                         │
│  two shortlist rows side by side: Fit 82 · 70% assessable  vs  Fit 82 · 100% assessable      │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│  How DealProof decides          01 Every fact has a source and a date                        │
│  (numbered rows, expand)        02 The right source for the right question                   │
│                                 03 Estimates are labelled as estimates   …  09               │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│  What it is not      short two-column list from the PRD: not due diligence, not a valuation  │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│  For businesses raising money     one paragraph + investor shortlist row preview             │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│                   Screen your next target with the evidence attached                         │
│                                  [ Start a screening ]                                       │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ DealProof   Built at ContextCon 2026   Scoring policy   Confidentiality   GitHub             │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

Notes

- The hero text is centred because it is two short lines; it sits in the space between the navigation and the top of the product window, and the window runs past the bottom of the first screen so the page invites a scroll.
- One primary and one secondary action. "Log in" is a text link.
- No logo strip, testimonials, counters or badges. The "Fit is not evidence" section replaces the usual statistics row with the product's actual argument.
- Sections alternate in shape (window, tabs with split, legend grid with two unequal cells, side-by-side rows, numbered list) so the page has no repeated card grid.
- Mobile: headline 44px, actions stacked full width, the hero ledger shows three stacked rows, tabs become a horizontal scroll list, nothing below 11px.

### 11.2 App shell and navigation

```
┌────────────────┬─────────────────────────────────────────────────────────────────────────────┐
│ DealProof      │  Cases / Meridian Warehousing                 [Test mode]  ⌘K   Asha Rao ▾  │ 56
│                ├─────────────────────────────────────────────────────────────────────────────┤
│ ▢ Cases        │                                                                             │
│ ⌕ Discover     │   page content, padded 32, capped at 1440                                   │
│ ◎ Investors    │                                                                             │
│                │                                                                             │
│ Recent         │                                                                             │
│  Meridian Wa…  │                                                                             │
│  Cold chain …  │                                                                             │
│                │                                                                             │
│ ─────────────  │                                                                             │
│ Scoring policy │                                                                             │
│ Settings       │                                                                             │
└────────────────┴─────────────────────────────────────────────────────────────────────────────┘
  248
```

- Sidebar on `paper`, content on `paper`, separated by a hairline. Nav rows 32px tall with 2px between, icons in one 16px column, labels on one line. Section label "Recent" sits 24 above and 8 below. The active item is `accent-tint` with accent text, no bar and no glow.
- Three destinations: Cases, Discover (thesis to shortlist), Investors. "Scoring policy" is a readable page of the rule weights and tables, linked from every score.
- Top bar: breadcrumb on the left; on the right the Test mode tag when sending is off, the command-menu keycap, and the signed-in user (needed for the named approver).
- The wordmark is "DealProof" in Plex Sans 500 at 16px. No logo tile, no sparkle. A mark, if one is wanted, is a later decision.
- Collapses to 56px icons at `md`, to a menu sheet below.

### 11.3 Cases dashboard

```
 Cases                                                         [ New case ]  [ New thesis ]
 12 cases · 3 running or waiting on you
 
 Filter: Disposition ▾   Status ▾   Thesis ▾                              Search
 ───────────────────────────────────────────────────────────────────────────────────────────────
 Company                Disposition              Fit · assessable        Claims            Updated      Cost
 Meridian Warehousing   [⌕ Investigate further]  82 · 70%  ▮▮▮▮▯▮▮╱╱╱   ●3 ◐1 ?2 ◌0       22 Nov 2026  86 cr · $0.42
 Pune · Identity ✓                                                       Request awaiting approval
 Cold Chain Logix       [? Cannot assess]        –                       –                 21 Nov 2026  12 cr · $0.04
 Identity unresolved · 2 candidates
 Northline Freight      ◍ Verify running · step 4 of 7                   ●2 ◌…             just now     38 cr
 ───────────────────────────────────────────────────────────────────────────────────────────────
```

- A table, not a card grid: cases are compared row by row. Two-line rows, 56px.
- Claim counts use the Count form in the fixed order; a non-zero Not checked count is always shown, hatched.
- "Waiting on you" items (request awaiting approval, identity to resolve) are stated in words on the second line and filterable.
- No stat cards with sparklines. The one summary line is text.
- Empty state: one sentence on what a case is, the two actions, and a link to open the labelled illustration case.

### 11.4 New thesis → criteria editor → shortlist

Three states of one page, with a quiet three-step header (Thesis, Criteria, Shortlist).

```
 1 Thesis
 ┌──────────────────────────────────────────────────────────────────────────────────┐
 │ Describe what you are looking for                                                │
 │ [ privately held Indian warehousing and supply-chain software companies that     │
 │   serve enterprise customers and show recent expansion                        ]  │
 │ Examples: [ Regional 3PL operators ]  [ Cold chain technology ]                  │
 │                                                           [ Turn into criteria ] │
 └──────────────────────────────────────────────────────────────────────────────────┘

 2 Criteria                                        Edit before searching. Nothing runs yet
 Must have                                                                Assessed from
 ▪ Headquartered in India                 [ is ] [ India           ]      Company record
 ▪ Privately held                         [ is ] [ private         ]      Evidence
 Preference                                                     Weight
 ▫ Serves enterprise customers            [ is ] [ enterprise ]  ●●○      Evidence
 ▫ Recent expansion                       [ within ] [ 12 months ] ●●●    Signal
 [ + Add criterion ]                       Estimated cost: about 40 credits   [ Search ]

 3 Shortlist · 14 companies · 6 removed for failing a must-have [Show]     ◍ run panel while searching
 ──────────────────────────────────────────────────────────────────────────────────────────────
 Meridian Warehousing        Fit 82 · 70% of criteria assessable   ▮▮▮▮▯▮▮╱╱╱        [ Open case ]
 Contract warehousing, Pune  [▤ Crustdata · as of Nov 2026]
 ~180 people Estimate · Series A, 2025 · 2 open roles Signal
 Why it is here: India HQ, private, warehousing activity, facility announced Sep 2026
 Unknown: customer type, revenue band
 ──────────────────────────────────────────────────────────────────────────────────────────────
```

- Criteria rows are editable in place; must-have and preference are separate groups with different bullets (filled and open square), and a row can be dragged or toggled between them. Each row says how it will be assessed: from a company record field, from evidence, or as a signal.
- The search button states the estimated credit cost before anything is spent.
- While searching, the run panel shows the steps and shortlist rows appear as they are enriched.
- A shortlist row is a ledger-like row, not a card: name and one-line business, the fit readout, labelled size and growth, funding and hiring, "Why it is here" (criteria met, each with its source line on expand) and "Unknown". Sorting by fit, ties by assessable share, as the rules define.
- Removed companies are available behind "6 removed for failing a must-have", each with the failed criterion and its evidence. Companies with unknown must-haves stay in and say so.

### 11.5 Investor discovery

```
 Find investors                                       Your business
 Sector [ Warehousing technology ]  Location [ India ]  Stage [ Series A ]
 Size [ 50 to 200 people ]  Funding sought [ Growth equity ]              [ Find investors ]

 9 investors · from 23 comparable companies with dated rounds
 ──────────────────────────────────────────────────────────────────────────────────────────────
 Northgate Ventures                      4 comparable investments · last in sector Aug 2026
 Comparable companies backed
   Cold Chain Logix    Series A   12 Aug 2026   [▤ Funding record · as of 12 Aug 2026]
   Fleetwise           Seed       3 Mar 2025    [▤ Funding record · as of 3 Mar 2025]
   + 2 more
 Why they fit: 4 rounds in warehousing technology in India since 2024
 Unknown: current fund status, cheque size
 Possible duplicate of "Northgate Capital" · not merged                    [ Draft outreach ]
 ──────────────────────────────────────────────────────────────────────────────────────────────
 This ranking describes past investments. It does not predict whether an investor will invest
```

- The same row language as the company shortlist. The count of comparable investments and the last date in the sector are the two leading facts; each backed company is a dated record with a source line. An investor with no dated record is not listed.
- Possible duplicates are flagged, not merged.
- No contact details appear anywhere. "Draft outreach" leads into the same approval pattern as the seller request.
- The ranking caveat is a fixed line under the list.

### 11.6 Case view

A case header, a tab row, the content and, from `xl`, a sticky assessment rail.

```
 Cases / Meridian Warehousing
 Meridian Warehousing Pvt Ltd                         [⌕ Investigate further]     v2 · 22 Nov 2026
 ✓ Identity confirmed · domain, registration number   Fit 82 · 70% assessable     86 cr · $0.42
 3 checks were not run [View]                                             [ Print memo ] [ ⋯ ]
 ───────────────────────────────────────────────────────────────────────────────────────────────
 Overview  Identity  Claims 12  Events 5  Comparables  Assessment  Request ●  Sources 31  Cost
 ───────────────────────────────────────────────────────────────────────┬───────────────────────
                                                                        │ Assessment · v2
   tab content                                                          │ Fit 82 · 70%
                                                                        │ 9 of 12 settled · 3 ◌
                                                                        │ Signals: 4
                                                                        │ Financial: not assessed
                                                                        │ [⌕ Investigate further]
                                                                        │ Next: approve request
                                                                        └───────────────────────
```

Tabs carry mono counts; "Request ●" shows a small dot when an approval is waiting. The header's "not run" line appears whenever any claim is Not checked.

**Overview / memo.** The memo as a reading page: prose at 16px in a 680px measure, Newsreader for the title and section heads, with the structured components inline.

```
   Screening memo                                     version 2 · 22 Nov 2026 · policy 1.0
   Meridian Warehousing Pvt Ltd                       (Newsreader 32)
   What changed since version 1  (when applicable; the diff summary)
   1 The opportunity          prose with numbered citations [1][2]
   2 Identity and profile     identity band + profile facts with source lines
   3 Claims                   compact ledger: claim · status · one-line record
   4 Recent events            5 dated events
   5 Comparable companies     table, or "No fair comparison found" and why
   6 Financial evaluation     hatched "Not assessed" block, or figures with stated assumptions
   7 Risks, assumptions, unknowns     three short lists
   8 Recommended next step    disposition stamp + reasons
   9 Information to request   the request list
   Sources                    numbered list: every source, URL or request, retrieved at
```

**Identity.** The identity band at full size. Confirmed: the matching keys as a two-column table (key, value, source line). Unresolved: candidates side by side with matching and differing keys and "Choose the entity". Below: legal name, registration, registered office, founded, key people, each a fact with a source line; people show how they were matched.

**Claims.** The ledger from 7.3 at full width, with the status and category filters, the legend, and "Add a claim" (typed claims are attributed to the person who typed them). Upload area for seller documents with the per-case confidentiality line and the deletion date: "Used only for this case · deleted on 22 Dec 2026".

**Events.** A dated vertical timeline, newest first: date in mono in a fixed left column, the event in one sentence, a tag for its nature (Announced, Reported, Recorded) and source lines. An announcement of a plan is worded as a plan. Events without a date are listed separately under "Undated".

**Comparables.** A table: company, activity, region, size band (Estimate), funding stage, each cell sourced. Headed by the basis of comparison: "Same activity, region and size band". When no fair comparison exists the tab says so and why; it does not show a weaker list. Informational only, and labelled as not scored.

**Assessment + history.** The five-judgment panel from 7.2 at full size, then the version rail and the diff from 7.4. A link to the scoring policy sits under the panel.

**Request & approval.** The flow from 7.5. After sending: the receipt, then "Seller documents" with an upload area; each uploaded document lists the claims it affected and links to the version it produced.

**Sources.** The full record, so the case can be reproduced: a table of every source with class glyph and name, URL or request parameters, as-of date, retrieved-at time, and how many facts rest on it. Filter by class. Each row expands to the evidence taken from it. An "Export source record" action.

**Cost.** The readout from 7.7.

### 11.7 Print and PDF memo

The memo is printed from the Overview tab through the browser, with a print stylesheet. It has to work in black and white on an office printer.

```
 ┌──────────────────────────────────────────────────────────────┐
 │ DealProof · Screening memo            Meridian Warehousing   │  running header, 9pt
 │                                                              │
 │ Screening memo                                               │
 │ Meridian Warehousing Pvt Ltd            (Newsreader 22pt)    │
 │ Version 2 · 22 Nov 2026 · policy 1.0 · prepared for …        │
 │                                                              │
 │ ┌──────────────────────────┐  Fit 82 · 70% of criteria       │
 │ │ ⌕ Investigate further    │  assessable                     │
 │ └──────────────────────────┘  9 of 12 checks settled ·       │
 │                               3 not checked                  │
 │ 1 The opportunity                                            │
 │ Body text 10.5pt Plex Sans with footnote numbers ¹ ²         │
 │                                                              │
 │ 3 Claims                                                     │
 │ ● Supported   "Incorporated in 2014 …"  Registry record ¹    │
 │ ? Cannot verify  "We employ 250 people"  Estimate ~180 ³     │
 │ ◌ Not checked ╱╱ "Our top customer …"   budget reached       │
 │                                                              │
 │ ¹ Registry mirror, as of 12 Mar 2014, retrieved 22 Nov 2026  │
 │ Screening only. Not financial, legal or tax due diligence    │  running footer
 │                                                    Page 1/4  │
 └──────────────────────────────────────────────────────────────┘
```

- A4, margins 18mm (22mm inner edge if bound), body Plex Sans 10.5pt on 15pt, headings Newsreader, figures Plex Mono 9.5pt. White paper; no background tints are required for meaning.
- App chrome, tabs, the rail, buttons and the run panel are hidden. Motion is irrelevant.
- **Statuses print as glyph + full label.** The glyph shapes differ, so they read without colour. Tints are dropped; borders are kept. Not checked keeps its dashed border and hatch, printed in black at 20%, with the reason.
- Source lines become numbered footnotes at the foot of the page, with the complete numbered source record as the last section, including URLs printed in full and retrieved-at times.
- The first page always carries: disposition stamp with reasons, the fit readout with its assessable share, the sufficiency count including Not checked, the version and date, and the "what changed" summary when the version is above 1.
- Estimates keep the tilde and the word. The criteria strip prints with solid, empty and hatched cells.
- Running header with product and company; running footer with page x of y and the fixed line "Screening only. Not financial, legal or tax due diligence".
- Page-break rules: a claim row, a judgment block and a heading with its first paragraph never split.
- A test-mode request prints as "Suppressed (test mode) · not sent".

## 12. Accessibility

- Colour is never the only carrier of meaning: every status and disposition has a distinct glyph shape and its name in text.
- Text contrast is 4.5 : 1 or better everywhere, measured in section 4.
- Everything is reachable and operable by keyboard: the ledger is a grid with arrow-key row movement and Enter to expand; source chips are buttons; the criteria strip cells are focusable.
- Visible focus: 2px accent ring, 2px offset, on every interactive element.
- Run progress and status changes are announced through polite live regions, once per change.
- `prefers-reduced-motion` is honoured through the token overrides and `MotionConfig`; no information depends on an animation having played.
- Touch targets are 44px on small screens. No text below 11px.
- Glyph-only marks have accessible names ("Status: Cannot verify").

## 13. Open decisions for the user

1. **Dark theme.** Recommended: out of scope for v1, light only. The tokens allow it later.
2. **The "analyst working" indicator.** Recommended: `thinking-orbs` (MIT, no runtime dependencies) in the run header only, in ink, 16 to 20px. Alternative: a plain CSS loader and no new dependency. Needs approval as an install either way.
3. **Sounds.** Recommended: built but off by default, three cues at most, using `cuelume`; turned on for the run-finished cue during the demo if wanted. Alternative: no sound at all, which costs nothing and loses little.
4. **Typefaces.** IBM Plex Sans + IBM Plex Mono + Newsreader. If a single-superfamily look is preferred, the fallback is IBM Plex Sans, Mono and Plex Serif.
5. **Accent.** Registrar ink blue `#24408E`, with ink-black primary buttons. Both reference products use a brighter blue button; this is deliberately quieter and keeps blue from reading as a status.
6. **Deprioritise in graphite, not red.** Recommended so red keeps one meaning (Contradicted). If judges are expected to want a red "no", this can change, at the cost of that clarity.
7. **Home page headline.** Proposed: "Know what is proven before the second meeting". The PRD's own line, "Discover opportunities. Verify the evidence. Evaluate with confidence", is the alternative.
8. **A logo mark.** Not designed here. The wordmark alone is enough for the hackathon; a simple mark could come from the ledger spine.
9. **Stale evidence.** Should an as-of date older than some threshold be flagged on the source line? That is a policy rule, not a styling choice, so it is left out until decided.
