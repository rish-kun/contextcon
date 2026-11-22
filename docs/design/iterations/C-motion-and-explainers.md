# Iteration C: motion system and "how it works" explainers

Design brainstorm, lens C · 22 Nov 2026 · docs only, nothing here is built yet

This builds on [`../design-direction.md`](../design-direction.md) and changes none of it. The direction (a diligence file: paper, ink, one registrar blue, the source line as signature) stands. Section 9 of that document already sets one curve and three durations, and they are in the code as `apps/web/lib/transitions.ts` and the `--duration-*` tokens in `apps/web/app/globals.css`. This iteration does two things on top:

1. Turns the motion table into a full catalogue, one entry per real state change, so two builders animate the same event the same way.
2. Adds five explainers: views that show how a conclusion was reached, drawn from the case's own records.

`unslop` rules apply throughout (unslop by Damir Sokolovsky, [@heydamir](https://x.com/heydamir), CC BY 4.0), in particular its motion pass: keep motion that explains something, remove loops, one curve, no animated layout properties.

## 0. Why it reads as gimmicky, and the fix

The feedback is that the current UX feels gimmicky. Reading the components, the motion itself is restrained. The cause is more likely this:

- **Motion is attached to mounting, not to events.** `animate-row-in`, `animate-cell-in` and `animate-fade-in` play whenever a component appears, including on a plain page visit where nothing happened. Rows rising into place on a finished case is decoration by the document's own first principle. Motion should play when the record changes, and a page that is merely opened should simply be there.
- **The product says what it concluded, and shows little of how.** A status mark, a fit number and a stamp are outcomes. The chain behind them (which sources, which dated facts, which rule) is in the data and one click away in a popover, but it is never drawn. Without it the animated parts read as effects on top of a result.

So the direction for this iteration: **less entrance motion, and more drawn reasoning.** The richness moves out of transitions and into five views that only this product could have. Each of them is static by default and moves only when a run or a new version changes what it shows.

## 1. Motion catalogue

### 1.1 The language

One idea: **ink lands and stays.** A thing that has just been established appears in place with a short fade and settles; it does not travel, bounce or draw attention again. A thing that has been superseded is struck through and stays readable.

| Token | Value | Use |
| --- | --- | --- |
| `ease` | `cubic-bezier(0.22, 1, 0.36, 1)` | Every animation. No second curve, no springs |
| `fast` | 140ms | Hover, press, every exit |
| `base` | 200ms | A small thing changing state: a mark settling, a popover, a tab |
| `slow` | 360ms | A thing arriving or changing shape: a row, a drawer, a layout change, a route morph |
| `highlight` | 1200ms | The one-time tint on a changed value, fading out |
| `stagger` | 40ms, six items at most | Items that arrived together |
| `rise` | 8px (4px for overlays) | Entrance distance |

All of these exist already. Two additions are proposed to `transitions.ts`, both derived from the above so no new numbers enter the system:

- `transition.exit` = `fast`. Exits are always quicker than entrances and never travel.
- `draw` = `{ duration: slow, ease }` on `scaleX` with `transform-origin: left` (or `pathLength` on an SVG line). Used for connectors and meters so a line can grow without animating width.

**Entrance rule, the main change.** An element animates in only if it did not exist a moment ago *because of an event the user is watching*: a streamed step, an arriving fact, a new version, an action they just took. Content that is present when a route loads renders in its final state, with at most the single page-level fade described in 1.10.

### 1.2 A run starting, and each step progressing

Component: `RunProgress` (`components/dealproof/run-progress.tsx`). Inspired by the step list on aicss.dev (thinking and tool-call states, pattern only) and the "status word per loader" idea on loader-buttons.appllama.io.

| Moment | Animation | Reduced motion |
| --- | --- | --- |
| User presses the button that starts a run | Button goes pending (1.9). The run panel enters above the content: fade and 8px rise, `slow`. Content below moves down through Motion `layout`, `slow`, never an animated height | Panel appears; no movement |
| Steps listed | All steps render at once as pending. No stagger: the steps are a plan, and they exist together | Same |
| A step begins | Its glyph swaps from the open ring to the chevron with a crossfade, `base`. Its label goes from muted to ink, `base`. The live sub-line fades in | Instant swap |
| Sub-line updates ("claim 7 of 12") | Text swaps with no animation. It changes too often to animate, and animating it would be the loop the rules forbid | Same |
| A step completes | Check draws in (`pathLength` 0 to 1, `base`). The result line fades in, `base`. The cost figure fades in at the right, and the header credit count tweens (`NumberTween`, `slow`) | Instant; figure jumps |
| A step fails | Cross fades in, `base`. Same timing and distance as success. No shake, no red flash | Instant |
| A step is skipped for budget | The row takes the hatch and dashed border with a `base` fade of the pattern layer | Instant |
| Resume after an interruption | The "Resumed 16:51 IST" band fades in, `base`. Kept steps show "from cache · 0 cr" already settled; they do not replay their completion | Instant |
| Run finishes | The step list collapses to the one-line summary through a shared `layout` animation, `slow`; the summary text fades in over the last 140ms | Swapped instantly |

The `thinking-orbs` indicator in the header is the one looping element in the product. It mounts when `run.status === "running"` and unmounts on finish or failure with a `fast` fade.

Elapsed time ticks as plain text. It does not tween.

### 1.3 Evidence arriving, and a claim status settling

Component: `ClaimLedgerRow` (`components/dealproof/claim-ledger.tsx`), `StatusMark`. This is the product's main moment, so it gets the most careful choreography and still fits in under half a second.

1. **Claim extracted.** The row enters with the left side filled and the spine pending: fade and 8px rise, `slow`, 40ms apart, six at most (existing behaviour, kept, because extraction is an event).
2. **A fact arrives.** The record statement fades in on the right, `base`, with no rise. Its source chip follows 40ms later. The order matters: the statement, then where it came from.
3. **The rule fires.** The pending ring fades out (`fast`); the status glyph fades in and scales 0.9 to 1 (`base`); the label crossfades. The spine cell's tint fades in with the glyph.
4. **Nothing else moves.** The row does not flash, and no toast is raised. A screen reader hears one polite announcement: "Claim 5: Partially corroborated".

Rules for this entry:

- Every status settles identically. Contradicted does not arrive harder than Supported.
- A claim that ends as Not checked does not "settle": the hatch fades in over `base` and the reason appears with it. There is no scale, because nothing was established.
- On a page visit to a finished case, none of this plays. The ledger is drawn settled.
- If more than six claims settle within one 200ms window (a cached replay), they change together with no stagger.

Reduced motion: glyph, label and statement swap instantly.

### 1.4 Fit strip filling

Component: `CriteriaStrip` (`criteria-strip.tsx`). Today `animate-cell-in` plays on every mount, including in every shortlist row.

| Context | Animation |
| --- | --- |
| Evaluate has just produced the fit (the user watched the run) | Cells fade in left to right, 40ms apart, assessed cells first; then a 120ms pause; then the unknown group fades in together as one block. "Fit" tweens to its value over `slow`. The pause is the point: the eye registers the assessed part before seeing what is missing |
| A criterion changes verdict in a new version | Only that cell crossfades, `base`, and takes the 1200ms highlight. The number tweens |
| Page visit, shortlist rows, dashboard rows, print | Drawn in the final state. No animation |

The assessable share never animates on its own and is never shown before the fit number: the two appear together (they are one component for this reason).

Reduced motion: final state.

### 1.5 Judgment panel revealing

Component: `JudgmentPanel`. Five judgments, drawn differently so they are not averaged by eye. The reveal must not undo that by presenting them as one unit arriving.

- When Evaluate finishes, the five blocks fade in in their fixed reading order, 40ms apart, `slow`, with no rise. The disposition stamp is last.
- The stamp appears like every other block. It does not thump down or scale from large like an inked stamp; a stamp animation on Prioritise would be a celebration, and the same animation on Deprioritise would be a verdict delivered with a flourish. Both are wrong.
- "Not assessed" for the financial judgment fades in with its hatch at the same time and for the same duration as its neighbours, so its absence is as visible as their presence.
- In the sticky rail the five one-line rows update in place: the changed line gets the 1200ms highlight, and nothing reorders.

Reduced motion: all five present at once.

### 1.6 Assessment version diff

Components: `VersionRail`, `VersionDiff` (`version-diff.tsx`). Inspired by file-diff presentation on aicss.dev (pattern only).

| Moment | Animation | Reduced motion |
| --- | --- | --- |
| A new version arrives while the page is open | A new node enters at the end of the rail: the connector draws down (`draw`), then the node fades in and fills, `base`. The previous node empties with a `base` crossfade | Rail redrawn |
| The diff opens for a version the reader has not seen | Each changed row: the old value is already there; the arrow fades in (`fast`); the new value fades in with a 4px move from the left (`base`); the row takes the accent tint, which fades over 1200ms. Rows 40ms apart, six at most | Static "Changed" tag, as now |
| The same diff reopened later | No animation. `highlight` is true only once per version per reader | Same |
| "Show unchanged" | The list grows through `grid-template-rows` 0fr to 1fr, `slow`; rows fade in | Instant |
| Opening an earlier version read-only | Content crossfades (`base`); the "You are reading version 1" banner fades in. The whole page takes no tint | Instant |

Upgrades and downgrades are animated identically. The implementation should take the highlight flag from a "seen versions" record (local to the reader), not from a mount.

### 1.7 Approve, then send once

Component: `ApprovalBlock` (`approval-block.tsx`). Inspired by the "button that settles into a receipt" mechanic from beui.dev and amicro, written with our curve.

1. **Press "Approve and send once".** The dialog opens: scrim fades, panel fades and rises 4px, `base`.
2. **Press "Send once".** The button goes pending (1.9). The dialog stays until the server answers; the approval is recorded server-side and nothing is shown as sent before then. This is the one place optimistic UI is wrong.
3. **Answer arrives.** The dialog closes (`fast`). On the page, the button's container morphs into the receipt through a shared `layoutId`, `slow`; the receipt's lines fade in over the last 140ms. The stepper's indicator moves to the last step, `base`.
4. **The button is gone.** It is unmounted, not disabled.

**Test mode, animated honestly.** While sending is off, the same sequence runs with these differences, and they are the point:

- The morph ends in the hatched, dashed receipt reading "Suppressed (test mode) · not sent". The hatch fades in with the text.
- No check draws in. The envelope glyph is struck through from the first frame; it is never shown un-struck and then crossed out, which would read for a moment as a real send.
- The stepper's last step reads "Suppressed", and the indicator moves to it with the same `base` timing.
- Sound, if on, plays the neutral run-finished cue, never the success cue (already in `lib/sound.tsx`).

A failed send: the button returns from pending to idle with a `fast` fade, and a "Failed · not sent" block fades in above it, `base`, with the provider's reason. No shake.

Reduced motion: the button is replaced by the receipt instantly.

### 1.8 Page and route transitions inside the app

Approach: the browser View Transitions API through React's `<ViewTransition>` (see section 4). No shader sweep. glimm.dev's own guidance was read again for this: it says to keep a sweep for milestones and to skip it for every internal navigation, loading states and repeated actions. DealProof's milestones (a run finishing, a send) are reported by a receipt and a summary line that stay on the page, which serves the reader better than a band crossing the screen. So glimm stays out, as the direction document already decided.

| Navigation | Transition | Why |
| --- | --- | --- |
| Between sections (Cases, Discover, Investors, Settings) | Content area only: old fades out `fast`, new fades in `base`. Sidebar and top bar are excluded from the transition and do not move | A change of place; nothing persists |
| Between tabs of a case | The underline indicator moves (`base`, existing `layoutId`). The tab content crossfades, `fast` out and `base` in, with no rise. The case header and the assessment rail are excluded and stay perfectly still | The case is the same object; only the view of it changes |
| Shortlist or dashboard row into a case | Shared-element morph (1.8.1) | The same company continues |
| Case back to the list | The morph in reverse, at `base` instead of `slow` | Returning should be quicker than arriving |
| Opening an earlier assessment version | Crossfade of the assessment content only | Same place, different time |
| Any navigation while a run is live | The run indicator and panel carry their own `view-transition-name` so they are never part of a crossfade and never restart | A live indicator must not blink |

Reduced motion: view transitions are switched off in CSS, and every navigation is an instant swap:

```css
@media (prefers-reduced-motion: reduce) {
  ::view-transition-group(*),
  ::view-transition-old(*),
  ::view-transition-new(*) { animation: none !important; }
}
```

#### 1.8.1 Expanding a shortlist card into a case

The reference for this was animbits.dev's expanding-card transition. That page could not be read (the host fails DNS resolution from the scraper, as it did at checkpoint 0b), so this spec is built from the Next.js view-transitions guide shipped in `node_modules/next/dist/docs/01-app/02-guides/view-transitions.md` and the general pattern: name the elements that persist, and let the browser move them.

What persists between `ShortlistCard` and `CaseHeader`, and so what gets a shared name:

| Element | `name` | Behaviour |
| --- | --- | --- |
| Company name | `case-name-{id}` | Moves and scales from row size (14px) to title size (24px). Text morphs can blur mid-flight, so the group animates position and the old and new text crossfade over the middle 140ms |
| Fit readout (text and strip) | `case-fit-{id}` | Moves to its place in the case header. Same component on both ends, so it reads as one object |
| Disposition stamp, when the row has one | `case-stamp-{id}` | Moves to the header |
| Everything else | none | Old page fades out `fast`; new content fades in `base`, starting 100ms after the morph begins |

Duration `slow` (360ms), the single curve. Three named elements is the cap: more than that and the screen reads as pieces flying.

Honest limits:

- If the case is not yet loaded, the header skeleton carries the same names so the morph still lands on something, and the content arrives by the skeleton rule (1.10).
- The dashboard row links to the same case; it uses the same names so both entry points behave the same.
- A browser without support shows a plain navigation. Nothing depends on the morph.

### 1.9 Loading buttons

Inspired by loader-buttons.appllama.io, from which exactly one idea is taken: each of its twenty-five buttons pairs the motion with a status word ("Gathering", "Mapping", "Tracing"). The word is the useful part. The WebGL metaballs, caustics and voxels are not used; a button in a diligence tool is not a place for a physics demo.

`Button` gains a `pending` state:

- Width is locked at its idle width so nothing around it shifts.
- The label crossfades (`fast`) to a present-participle form supplied by the caller: "Search" to "Searching", "Approve and send once" to "Sending", "Turn into criteria" to "Reading the thesis". Not a generic "Loading".
- A 2px ink line along the bottom inside edge draws left to right once (`draw`, 360ms) and holds. It reports that the request left. It does not loop, sweep back or pulse.
- The button is `aria-busy` and not clickable, at full opacity (a pending button is working, not disabled).
- After two seconds with no answer the label changes once more to its "Still …" form ("Still searching"), with no further motion. This is the same rule as the skeleton.
- On success the line fades (`fast`) and the label returns or the button is replaced by what it produced. On failure the label returns and the error is stated next to the button in words.

A button that starts a run is pending only until the run panel appears (usually under a second), after which the run indicator is the progress display and the button is replaced by the panel.

Reduced motion: label swaps instantly; the line appears fully drawn.

### 1.10 Skeleton to content

Component: `Skeleton` (`components/ui/skeleton.tsx`), which already fades twice and then holds still.

- A skeleton has the shape of what is coming: ledger rows with a spine column, a strip-shaped block, a table header band. A reader should be able to tell which page they are on from the skeleton alone.
- If data arrives within 150ms, no skeleton is shown at all. A skeleton that flashes for 80ms is worse than a blank frame.
- Content replaces the skeleton with a crossfade, `base`, in place, with no rise and no stagger. It was a load, not an event, so the entrance rule in 1.1 applies.
- After two seconds the skeleton stops fading and a line of text appears beside it: "Still loading the claims". After ten, the line offers "Retry".
- Skeletons are never used for run output. Work in progress is shown as the run's steps and as pending spines, which are true statements about state; a skeleton would be a guess at a result that may come back Not checked.

Reduced motion: no fade; a static block, then content.

### 1.11 Toasts

There is no toast component in `apps/web` today, and Sonner (named in the direction document) is not in `package.json`. Recommendation: do not install it. Build one small `Notice` stack on Motion's `AnimatePresence`, about eighty lines.

- **What a toast is for:** confirming a small action whose result is not otherwise visible where the reader is looking. "Criteria saved", "Claim added", "Source record exported".
- **What it is never for:** a run finishing (the run panel's summary line), a send or a suppressed send (the receipt), an error that needs a decision (an inline block next to the cause), or anything in test mode that could be read as a real send.
- Position bottom right, above the page padding. 13px, ink text on `surface`, hairline border, `shadow-md`, radius 8. A glyph only when it carries meaning.
- Enter: fade and 8px rise, `base`. Exit: fade only, `fast`. A second toast pushes the first up through `layout`, `base`. Three at most; a fourth replaces the oldest.
- Four seconds, paused while hovered or focused. Dismiss with a close button or Escape. No swipe, no drag physics, no progress bar counting down.
- `role="status"`, polite. One action at most ("Undo"), and only when undo is real.

Reduced motion: appears and disappears with no movement.

### 1.12 Summary table

| State change | Easing | Duration | Reference |
| --- | --- | --- | --- |
| Run panel enters | standard | 360 | aicss step list |
| Step begins / completes | standard | 200 | aicss tool-call state |
| Row extracted | standard | 360, 40 apart, 6 max | watermelon list stagger |
| Fact arrives | standard | 200 | — |
| Status settles | standard | 140 out, 200 in | — |
| Fit strip after Evaluate | standard | 40 apart, 120 pause, tween 360 | beui number tween |
| Judgment panel reveal | standard | 360, 40 apart | — |
| Version node and diff row | standard | draw 360, row 200, tint 1200 | aicss diff |
| Button into receipt | standard | 360 | beui / amicro morph |
| Tab change | standard | 140 out, 200 in | watermelon tabs |
| Section change | standard | 140 out, 200 in | Next view transitions |
| Row into case | standard | 360 (back: 200) | animbits expanding card (unread), Next view transitions |
| Pending button | standard | 140 label, 360 line, once | loader-buttons status words |
| Skeleton to content | standard | 200 | — |
| Toast | standard | 200 in, 140 out | — |
| Run indicator | — | loops while live | thinking-orbs |

## 2. "How it works" explainers

Five views. Each one answers a question an analyst will be asked by the person reading the memo, and each is drawn only from records the case already holds. None has an illustrative mode inside the app: with no data, it shows an empty state that says what would fill it.

Shared rules:

- Built from the existing vocabulary: status glyphs, source chips, the hatch for anything not done, mono for dates and figures. No new colours and no new icon style.
- Static by default. They animate only when the underlying record changes while the reader is watching, using the catalogue above.
- Every mark is a button or sits next to one: a node opens the evidence popover, a cell filters the ledger, a segment links to its claims.
- Each prints in black and white.

### 2.1 Evidence trail

**Question it answers:** "Why does this claim say Partially corroborated?"

**Where it lives:** inside an expanded ledger row on the Claims tab, replacing the plain list of statements in the expanded state; and as a full panel when a claim is opened from the memo or the diff.

**Data:** `Claim.text`, `Claim.stated_in`, `Claim.record[]` (each `RecordStatement.text`, `.part`, `.estimate`, `.evidence[]`), each `Evidence.source` (`label`, `reliability`, `as_of`, `retrieved_at`), `Claim.status`, `Claim.note`, `Claim.what_would_settle`. The rule line needs the text of the status rule that fired. If the API does not yet return it per claim, the fallback is the status's fixed definition from the PRD ("What each claim status means"), and that should be flagged as an API follow-up.

```
 Claim 5 · Dated events
 ┌─────────────────────┐   ┌──────────────────────┐   ┌─────────────────────────────┐   ┌───────────────────────────┐   ┌────────────────┐
 │ Seller said         │   │ Sources              │   │ Dated facts                 │   │ Rule                      │   │ Status         │
 │                     │   │                      │   │                             │   │                           │   │                │
 │ "We opened a new    ├──▶│ ✎ Company            ├──▶│ 9 Sep 2026                  ├──▶│ A dated announcement      ├──▶│ ◐ Partially    │
 │  facility in        │   │   announcement       │   │ Facility announced as       │   │ supports that it was      │   │   corroborated │
 │  October 2026"      │   │   as of 9 Sep 2026   │   │ planned                     │   │ announced, not that it    │   │                │
 │                     │   │                      │   │   Supported: a facility     │   │ happened                  │   │ What would     │
 │ Seller deck p. 9    │   │ ◔ Crustdata profiles ├──▶│ Oct 2026                    │   │                           │   │ settle it:     │
 │                     │   │   as of Oct 2026     │   │ 2 open roles at the new     │   │ No registry, lease or     │   │ lease or       │
 │                     │   │                      │   │ site   Signal               │   │ occupancy record found    │   │ occupancy      │
 │                     │   │ ╎ ▤ Registry        ╎╌╌▶│ ╎ nothing found           ╎ │   │                           │   │ record         │
 │                     │   │ ╎   searched, no    ╎   │ ╎                         ╎ │   │                           │   │                │
 │                     │   │ ╎   record          ╎   │                             │   │                           │   │                │
 └─────────────────────┘   └──────────────────────┘   └─────────────────────────────┘   └───────────────────────────┘   └────────────────┘
```

What makes it teach:

- **Five columns, always in this order**, so after two claims the reader knows where to look. Claim, where we looked, what was found and when, the rule, the answer.
- **Searches that found nothing are drawn**, dashed and hatched, in the same family as Not checked. "We looked in the registry and found no record" is part of the reasoning and is the difference between Cannot verify and Not checked.
- **The date is the heading of each fact**, in mono, because the as-of date is what the rule reads. A fact with an unknown date says "unknown date" there.
- **Connectors are hairlines**, solid when a fact was taken from a source, dashed when a search returned nothing. For Conflicting evidence the two disagreeing facts are stacked with a small "disagree" marker between them and both lead into the rule.
- Under 1024px the columns stack vertically with the connector running down the left edge, like the version rail.

Motion: on a finished claim, none. During a run the trail builds in the order the work happens (1.3): source node, then its fact, then the connector into the rule draws (`draw`), then the status settles.

### 2.2 Pipeline rail

**Question it answers:** "Where is this case, and what happens next?"

**Where it lives:** in the case header, under the identity line, as one row. A read-only copy heads the memo. The marketing page's Discover / Verify / Evaluate / Act tabs use the same drawing, so the product explains itself in the same picture it uses inside.

**Data:** the case's runs by `Run.kind` and `Run.status` (discover, verify, evaluate, recheck), their `checks_not_run`, the claim status counts, the current assessment version, and `SellerRequest.status`. Each stage's sentence is computed from those, never written by hand.

```
 ●━━━━━━━━━━━━━━━━━━━●━━━━━━━━━━━━━━━━━━━●━━━━━━━━━━━━━━━━━━━○╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 Discover             Verify               Evaluate             Act
 From thesis          12 claims            Version 2            Request drafted
 "Indian 3PL"         9 settled · 3 ◌      Investigate further  Awaiting your approval
 21 Nov 2026          22 Nov 2026, 16:42   22 Nov 2026, 16:42   →  Review request
```

- Four fixed stations. A station is filled when its stage has produced a result, open when it has not, and carries the run indicator in place of its dot while that stage's run is live.
- The connector between two stations is solid ink when the earlier stage completed in full, and **hatched for the share that was not done**: a Verify with three checks not run shows the last quarter of its segment hatched. The rail therefore cannot look complete when the case is not.
- Under each station: the stage name, what it produced in one line, and when. The current stage carries the next action as a link. That link is the only accent on the rail.
- A case made directly (not from a thesis) shows Discover as "Added directly by Asha Rao" with an open station. A case with identity unresolved shows Verify as "Waiting on identity" and nothing after it filled.
- A re-check after seller documents does not add a fifth station. Verify and Evaluate show the latest pass and "2nd pass" in mono, with the history in the version timeline (2.4).
- It is a rail, not a stepper to click through: stations link to their tabs, and nothing can be advanced from here.

Motion: a station fills (`base`) and its connector draws (`draw`) when its run finishes while the page is open. Otherwise static.

### 2.3 Source-coverage map

**Question it answers:** "What did you actually look at, and where is the case thin?"

**Where it lives:** at the top of the Sources tab, above the table, and as a compact block in the Evidence sufficiency judgment.

**Data:** claims grouped by `Claim.category` (rows); `Evidence.source.reliability` across each claim's `record[].evidence[]` (columns, in the fixed order of `RELIABILITY_CLASSES`, strongest first); per cell, the count of dated facts and the most recent `as_of`. `seller_document` and `seller_statement` sit at the right, set apart, because the seller's own material is not independent evidence. A cell can only be marked "searched, nothing found" if the run records empty searches per claim and source class; if it does not, that state is left out until it does, and no cell is ever inferred.

```
 What the evidence for each kind of claim rests on                       Independent ────────────────▶   Seller's own
                    Registry   Audited     Counter-   Company    Profile    News      │  Seller    Seller
                               statement   party      announce.  signals              │  document  statement
 Identity      2    ■ 2        ·           ·          ·          ·          ·         │  ▫ 1       ·
 Team size     1    ·          ·           ·          ·          ■ 1        ·         │  ·         ▫ 1
 Dated events  3    ╎∅╎        ·           ·          ■ 2        ■ 1        ■ 1       │  ▫ 1       ·
 Funding       2    ·          ·           ·          ■ 1        ·          ■ 2       │  ·         ▫ 2
 Customers     2    ╱╱         ╱╱          ╱╱         ╱╱         ╱╱         ╱╱        │  ·         ▫ 2
 Financials    2    ╎∅╎        ╎∅╎         ·          ·          ·          ·         │  ▫ 1       ▫ 1

 ■ dated fact found, with count    ╎∅╎ searched, nothing found    ╱╱ not searched (budget reached)    · not a source for this question
```

What makes it teach:

- It shows the principle "the right source for the right question" as a picture. A reader sees at once that team size rests only on profile signals, which is why claim 2 is Cannot verify, and that Customers was never searched at all.
- **Four cell states with four different shapes**, so it reads without colour: filled square with a count, dashed empty box, hatch, and a small dot. A cell is filled only by a dated fact; there is no shading by "strength" and no heat scale, which would be a score by another name.
- Rows carry the claim count and their status counts on hover. Selecting a cell filters the sources table and the ledger to those claims.
- The right-hand group uses an open square, not a filled one: the seller's own document is where the claim came from, and it does not count toward coverage.
- Compact form for the judgment panel: one row per category, cells at 8px, no column headers, with the sentence "Customers: not searched · Team size: profile signals only".

Motion: none on load. During a run, a cell fills (`base`) when its first fact arrives.

### 2.4 "What changed and why" timeline

**Question it answers:** "This said Investigate further on Friday. Why does it say Prioritise now?"

**Where it lives:** the Assessment tab, replacing the separate rail and diff with one joined view; its top entry also heads the memo when the version is above 1.

**Data:** `AssessmentVersionMeta[]` (`version`, `created_at`, `trigger`), and `AssessmentDiff` between each adjacent pair (`changes[]` with `before`, `after`, `reason`, `evidence`; `unchanged_claims`).

```
 v1 ○  20 Nov 2026, 11:05 IST · initial screening
    │     12 claims · 9 settled · 3 ◌ not checked          [⌕ Investigate further]
    │
    │  ▣ "Lease agreement.pdf" received from seller · 22 Nov 2026, 16:31 IST
    │     └─ read against claims 5 and 6
    │
 v2 ●  22 Nov 2026, 16:42 IST · current
    ├─ Claim 5   ◐ Partially corroborated  →  ● Supported
    │            Because: lease start 1 Oct 2026 and occupancy certificate
    │            [▣ Seller document · Lease agreement p. 3 · as of 1 Oct 2026]
    │        ╰─▶ Evidence sufficiency   9 of 12 settled  →  10 of 12 settled
    │        ╰─▶ Screening disposition  [⌕ Investigate further]  →  [↗ Prioritise]
    │            Because: the facility claim was the last open required check for fit
    │
    └─ 11 claims unchanged  [Show]
```

What is new compared with today's `VersionRail` plus `VersionDiff`:

- **The cause sits on the rail between the two versions.** What arrived, when, and which claims it was read against. Today the trigger is a phrase on the version node; here it is its own entry, because the cause is the thing a reader is looking for.
- **Consequences are drawn as consequences.** A claim change is the root; the sufficiency count and the disposition that moved because of it hang beneath it with a connector. The reader sees that one document moved one claim, which moved the count, which moved the stamp. Today the three are siblings in a list.
- A change whose cause cannot be linked to a claim change is listed at the version's root with its own "Because", so the tree never invents a link.
- Each version node carries a one-line state (claims, settled, not checked, stamp), so the history can be read down the left without opening anything.
- Old to new, both drawn in full, the old struck through, exactly as section 7.4 of the direction document requires. Upgrades and downgrades look the same.

The consequence links need to come from the data. If `AssessmentChange` cannot say which claim change caused a derived change, the first version of this view groups derived changes under "As a result" beneath all claim changes of that version, and the per-claim link is an API follow-up.

Motion: 1.6.

### 2.5 Cost meter

**Question it answers:** "What did this cost, what is it spending right now, and what did the budget stop us from checking?"

**Where it lives:** in the run panel header while a run is live; in the case header in its compact form; at full size on the Cost tab.

**Data:** `Run.credits_used`, `Run.credit_budget`, `Run.steps[].credits_used`, `.model_usd`, `.from_cache`; `CaseCost` (`credits_used`, `credit_budget`, `model_usd`, `checks_not_run`, `lines[]`).

```
 Credits   86 of 150                                                    Model usage   $0.42
 ┌────┬──────────────────────────┬────┬───┬─────────────────────────┐
 │▓▓▓▓│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│▒▒▒▒│   │                         │   150
 └────┴──────────────────────────┴────┴───┴─────────────────────────┘
  Profile  Gather evidence        Now                 64 left
  4        48                     34 so far

 From cache: 5 steps · 0 credits                    Budget would stop: after about 2 more claims
```

- **One bar, segmented by step**, so the bar says where the credits went and not only how many. Segments are in run order; the running step's segment is a lighter ink and grows.
- Credits and model dollars are separate figures, never one bar and never a sum. Model usage is a number with its own small table on the Cost tab.
- Cached steps are listed as text under the bar. They cost nothing, so they take no width.
- When the budget is reached, the bar is full and the remaining checks are drawn **after the end of the track** as hatched blocks, one per check not run, labelled "3 checks not run". The bar does not turn red. The hatch is the consequence of the limit, shown where the limit is.
- The "would stop after about N more claims" line appears only when a per-claim estimate exists (`retry_credits_estimate` or the run's own average) and is marked `Estimate`.
- Compact form: "86 cr · $0.42" with a 48px, 4px-tall bar, in the case header and dashboard row.

Motion: during a run the running segment grows with `scaleX` (`draw`) each time the credit figure changes, and the number tweens with it. A finished step's segment takes ink with a `base` crossfade. On a page visit the meter is drawn at its value. Reduced motion: values jump.

### 2.6 How the five fit together

| Explainer | Surface | Reads from |
| --- | --- | --- |
| Pipeline rail | Case header (every tab), memo head, marketing steps | Runs, claims counts, version, request |
| Evidence trail | Claims tab, expanded row | One claim and its evidence |
| Coverage map | Sources tab; compact in Evidence sufficiency | All claims' evidence, by category and class |
| Change timeline | Assessment tab; memo head | Versions and diffs |
| Cost meter | Run panel, case header, Cost tab | Run and case cost |

**What each one replaces.** These are not five more panels on top of the current screens. Each takes the place of something that shows the same records with less structure, so the case gets clearer without getting longer.

| Explainer | Replaces | Net effect on the page |
| --- | --- | --- |
| Pipeline rail | The loose status phrases in the case header ("Request awaiting approval", run state) | One row in place of scattered lines |
| Evidence trail | The plain statement list in an expanded ledger row | Same height, ordered into five columns |
| Coverage map | Nothing today; it sits above the sources table and doubles as its filter | Adds about 200px; removes the class filter control |
| Change timeline | `VersionRail` and `VersionDiff` as two separate blocks in `assessment-view.tsx` | Two blocks become one |
| Cost meter | The plain credit bar in `CostReadout` and the cost panel | Same footprint, segmented |

**Empty and partial states.** Each is a sentence about the record, in the hatch family where work was not done, and never a sample drawing.

| Explainer | State | Reads |
| --- | --- | --- |
| Pipeline rail | New case, nothing run | Four open stations; under Verify: "Not started · Run verify" |
| Evidence trail | Claim Not checked | Claim column filled; the other four are one hatched block: "Not checked · budget reached. No search was run for this claim" with "Run check · about 4 credits" |
| Evidence trail | Checked, no evidence found | Source nodes dashed, "nothing found"; rule column states the rule; status Cannot verify |
| Coverage map | No claims yet | "No claims to cover yet. Add seller claims or upload a document" |
| Coverage map | Identity unresolved | Rows listed, all cells hatched: "Waiting on identity" |
| Change timeline | One version only | The single node and its state line, then "No later versions. New evidence will be recorded here" |
| Cost meter | Nothing spent | Empty track, "0 of 150 credits" |

A reader moves between them along real links: a hatched segment on the rail goes to the Not checked claims; a claim's trail names the source class; the coverage map shows that class thin across the category; the timeline shows what a new document changed; the meter shows what the budget left undone. That loop is the explanation of how DealProof works.

## 3. Rules that keep it from feeling gimmicky

1. **One motion language.** One curve, four durations, 8px. A value not in `transitions.ts` or the `--duration-*` tokens is a bug. No springs, no bounce, no overshoot.
2. **Motion on state change only.** An animation needs an event: something arrived, settled, changed or was done by the user. Opening a page is not an event. Scrolling is not an event inside the app (the marketing page keeps its single in-view reveal).
3. **One loop.** The run indicator, while `run.status === "running"`, in the run panel header (and standing in for the current station on the pipeline rail). Nothing else repeats: no pulsing dots, no shimmer, no breathing, no skeleton that fades more than twice, no pending-button spinner.
4. **Durations capped.** Nothing the reader waits on exceeds 360ms. The 1200ms highlight is a fade the reader does not wait for. A whole choreography (a row settling, a diff opening) finishes within 600ms including stagger.
5. **Stagger capped at six, 40ms.** Past six, the rest arrive with the sixth.
6. **Nothing travels far.** 8px for entrances, 4px for overlays. The only element that crosses the screen is a shared element in the row-to-case morph, and at most three do.
7. **Good and bad news move the same.** Supported and Contradicted, Prioritise and Deprioritise, sent and failed: same duration, same distance, same curve.
8. **Never animate a claim of completion before it is true.** No optimistic receipt, no check mark before the server answers, no progress bar that advances on a timer. In test mode the suppressed state is the first and only state shown.
9. **Not done never animates like done.** Hatch fades in; it does not settle, draw or fill.
10. **Transform, opacity and colour only.** Layout changes go through Motion's `layout` or view transitions. No animated width, height, margin, blur or shadow.
11. **No decoration.** No shaders, glows, gradients, particles, 3D tilt, cursor effects, text effects or hover scale. From metalforge.xyz, canvasui.dev and originkit.dev, nothing is taken.
12. **Sound off by default.** Three cues at most, behind the existing setting, never the only signal, and the neutral cue for a suppressed send. No tap, type, toggle or navigation sounds.
13. **Reduced motion is a complete product.** Every entry above has a fallback, and no information exists only in an animation.
14. **Explainers draw records, not illustrations.** Every mark maps to a row in the database. An empty explainer says what would fill it. Nothing is interpolated, smoothed or estimated without the word `Estimate`.
15. **The test for any new animation:** name the event it reports. If the answer is "the component mounted", remove it.

### What to remove from the current build

- `animate-cell-in` on `CriteriaStrip` cells when the strip is mounted on a page visit or in a list row.
- `animate-row-in` on `ClaimLedgerRow` when the ledger loads for a finished case.
- `animate-fade-in` on the case tab content wrapper in `case-shell.tsx`, once view transitions handle the crossfade (otherwise the two stack).
- The `motion.article` entrance on `ShortlistCard` when the shortlist is loaded from a finished run, as opposed to rows arriving during a live one.

Each needs a way to tell "arrived just now" from "was already there": a `live` or `arrived` prop set by the stream handler, not a default on mount.

## 4. Library choices

| Job | Use | Status |
| --- | --- | --- |
| Component animation, shared layout, presence | `motion` 14 (`motion/react`) | Installed |
| Run indicator | `thinking-orbs` 0.3, `state="searching"`, 20px, light theme | Installed, one use |
| Sound cues | `cuelume` 0.2, lazy-loaded, behind the setting | Installed |
| Route and shared-element transitions | React's built-in `<ViewTransition>` and `transitionTypes` on `next/link` | **No install.** React 19.3 and Next 16.4 are in `package.json`, and the bundled Next guide states view transitions work in the App Router with no configuration |
| Toasts | A small local `Notice` stack on `AnimatePresence` | No install; Sonner is not added |
| Explainer drawings | HTML grid and inline SVG for connectors | No install; no chart or graph library |
| Pending button, skeleton, connectors | CSS with the existing tokens | No install |

Nothing new is recommended. The one addition considered was a view-transitions helper, and the framework already provides it. Not adopted, with reasons: glimm (a sweep on navigation contradicts rule 2, and its own guidance advises against per-navigation use), loading.dev's spinner set (rule 3 leaves room for one loop, already taken), any loader-button package, canvasui, metalforge, originkit.

Two cautions for the builders:

- `apps/web/AGENTS.md` says this Next version differs from older ones. Read `node_modules/next/dist/docs/01-app/02-guides/view-transitions.md` before writing the route work, and follow it over memory.
- `<ViewTransition>` animates only updates inside a transition, Suspense reveal or deferred value; a plain `setState` does not trigger it. In-page changes (a status settling, a diff row) stay on Motion. View transitions are for navigation only, which keeps the two systems from overlapping.

Reference notes for this pass. Pages were read with Firecrawl as markdown or summaries; no browser was used, so motion was read from descriptions and not watched. `animbits.dev` failed DNS resolution. `orbs.jakubantalik.com` now redirects to `libraries.dev/orbs`; the package is unchanged. `rareui.com`, `beui.dev`, `amicro.vercel.app` and `ui.watermelon.sh` were read at catalogue level: the mechanics taken from them (list stagger, tab indicator, number tween, button into receipt) are generic patterns written with our own curve, and no source is copied. aicss.dev asks agents not to reconstruct its licensed components, so only the pattern names are used.

## 5. Implementation plan

Three chunks with no shared files, so three builders can work at once. Chunk 1 owns every shared primitive; chunks 2 and 3 only import from it.

### Chunk 1: motion foundation, navigation and controls

Owns:

- `apps/web/lib/transitions.ts` (add `transition.exit`, `draw`)
- `apps/web/app/globals.css` (view-transition CSS, reduced-motion block, pending-line keyframe; remove nothing other builders use)
- `apps/web/components/ui/button.tsx` (`pending`, `pendingLabel`, `stillLabel`)
- `apps/web/components/ui/skeleton.tsx` (150ms show delay, "Still loading" line)
- `apps/web/components/ui/notice.tsx` (new: the toast stack) and its provider line in `apps/web/components/providers.tsx`
- `apps/web/components/app-shell/*` (exclude sidebar and top bar from transitions; content-area crossfade)
- `apps/web/components/case/case-shell.tsx`, `case-header.tsx` (tab crossfade, shared-element names on the header, remove the stacked `animate-fade-in`)
- `apps/web/components/discover/shortlist-card.tsx`, `apps/web/components/dashboard/cases-section.tsx` (shared-element names on the row; entrance only when `arrived`)

Delivers: 1.8, 1.8.1, 1.9, 1.10, 1.11 and the entrance rule for shortlist rows.

### Chunk 2: event-driven motion inside the dealproof components

Owns:

- `apps/web/components/dealproof/run-progress.tsx` (1.2)
- `apps/web/components/dealproof/claim-ledger.tsx`, `status-mark.tsx` (1.3; `arrived` prop; no entrance on a finished ledger)
- `apps/web/components/dealproof/criteria-strip.tsx`, `number-tween.tsx` (1.4)
- `apps/web/components/dealproof/judgment-panel.tsx` (1.5)
- `apps/web/components/dealproof/approval-block.tsx` (1.7, including the test-mode sequence)
- `apps/web/app/design/gallery.tsx` (a "replay event" control per component, so each animation can be reviewed without a live run)

Delivers: the catalogue entries that report run and approval events. Uses the pending button from chunk 1 by prop only; until chunk 1 lands, the props are passed and ignored.

### Chunk 3: the five explainers

Owns a new folder and the three places they mount:

- `apps/web/components/explainers/evidence-trail.tsx`
- `apps/web/components/explainers/pipeline-rail.tsx`
- `apps/web/components/explainers/coverage-map.tsx`
- `apps/web/components/explainers/change-timeline.tsx`
- `apps/web/components/explainers/cost-meter.tsx`
- `apps/web/components/explainers/derive.ts` (pure functions from `lib/types.ts` records to each view's rows, with unit-testable inputs and outputs) and `index.ts`
- `apps/web/components/dealproof/version-diff.tsx` and `cost-readout.tsx` (the timeline and meter supersede parts of these; this chunk owns them to avoid a conflict with chunk 2)
- Mount points: `apps/web/components/case-b/tabs.tsx`, `sources-table.tsx`, `cost-panel.tsx`, `assessment-view.tsx`

Two mounts touch files owned by other chunks, and are handed over as one-line insertions at the end rather than edited in parallel:

- the pipeline rail into `case-header.tsx` (chunk 1)
- the evidence trail into the expanded row of `claim-ledger.tsx` (chunk 2)

Delivers: section 2, static first, then the run-time motion from the catalogue once chunk 2's `arrived` convention exists.

### Order and dependencies

```
 Chunk 1  transitions.ts tokens ──▶ button, skeleton, notice ──▶ view transitions ──▶ row-to-case morph
 Chunk 2  run-progress, ledger, strip, panel, approval  (independent of 1 except the Button props)
 Chunk 3  derive.ts ──▶ five static explainers ──▶ mounts ──▶ two handed-over insertions ──▶ run-time motion
```

Chunk 1 should land its `transitions.ts` change first, as a single small commit, since the other two import from it.

`derive.ts` in chunk 3 should take the types the pages already load (the case detail's `runs`, the cost panel's `CaseCostOut` from `lib/api`, the assessment view's versions and diffs), not new fetches. If a view needs a field the API does not return, it uses the fallback named in section 2 and the gap goes on the follow-up list below.

### If time is short

This is a hackathon build, so the order matters more than completeness. By value to someone watching a demo and to an analyst defending a memo:

1. **Remove mount-time entrances** (section 3, "What to remove"). It is mostly deletion, and it addresses the gimmicky feedback directly.
2. **Evidence trail.** It is the product's argument in one picture and needs no new API field for a first version.
3. **Pipeline rail** in the case header. It orients every tab.
4. **Change timeline**, with the cause on the rail, grouped "As a result" until the causal link exists.
5. **Cost meter**, segmented, with the hatched checks past the budget.
6. **Coverage map**, without the "searched, nothing found" state until empty searches are recorded.
7. **Row-to-case morph and tab crossfade.** Pleasant, and the least informative item here, so it goes last.

Pending buttons, the notice stack and the skeleton delay are small and can ride along with whichever chunk-1 work is in progress.

### API follow-ups this design depends on

None blocks a first version; each has a stated fallback above.

1. The status rule that fired, as text per claim (evidence trail, rule column).
2. Empty searches recorded per claim and source class (coverage map, "searched, nothing found"; evidence trail, dashed source nodes).
3. A link from a derived change to the claim change that caused it (change timeline, consequence connectors).
4. The document or event that triggered a version, as a structured record with a time, not only the `trigger` phrase (change timeline, cause entry).

### Review checklist for each chunk

- Every animation names its event (rule 15).
- Nothing loops except the run indicator.
- With `prefers-reduced-motion` on, every state is reachable and readable.
- A finished case opened cold shows no entrance motion beyond the page-level fade.
- Test mode never shows a check, the word "Sent" alone, or green.
- Each explainer with empty data shows what would fill it, and never a sample.
