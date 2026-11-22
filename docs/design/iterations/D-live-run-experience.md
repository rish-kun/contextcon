# D. The live run experience

Design iteration · 2026-11-22 · docs only, nothing here is built yet

The user's top UX priority, in their words: "The feel that the application is working should come from the website. If I give it a task I should be able to feel that something is going on in the background — the agent is researching something. I should see some of the live results, parts of it."

Today a run shows a list of five to twenty step labels and one sub-line per step. It is correct and it is too quiet: between "Search companies" turning on and turning off, a 48-company search, a 15-company enrich and 37 job-posting reads happen and the page shows none of them. This document specifies how to show that work as it happens, using only things that really happened.

It extends `docs/design/design-direction.md` §7.6 (run progress) and §9 (motion and sound). Where it changes a rule there, it says so in [§3.6](#36-changes-to-the-design-direction).

Contents: [0 Research](#0-what-the-research-says) · [1 The live run view](#1-the-live-run-view) · [2 Event schema](#2-the-event-schema) · [3 Motion and feel](#3-motion-and-feel) · [4 Replay](#4-replay-and-the-run-log) · [5 Implementation plan](#5-implementation-plan) · [6 Open decisions](#6-open-decisions)

---

## 0. What the research says

### How other products show an agent at work

These are from my own knowledge of the products, not from a fresh scrape. The patterns are what matter; none of the styling is taken.

| Product | What it shows while working | What DealProof takes |
| --- | --- | --- |
| Perplexity | A short plan of steps that tick off; under the active step, the search queries it ran and a row of source chips (favicon + domain) that fill in as pages are read; the answer then streams under the same header | Sources as favicon chips arriving one at a time. The steps and the result share one page |
| ChatGPT deep research | A side panel with two tabs, Activity and Sources. Activity is a plain-language log ("Searching for…", "Reading…"); Sources is a growing list with a count. The panel can be reopened after the report is done | Two streams kept apart: what it is doing, and what it has read. The log outlives the run |
| Claude research mode | A collapsed "researching" line with a live counter of sources and elapsed time; expanding it shows the queries and results per sub-task. The report replaces nothing: the trace stays collapsed above it | One always-visible "now" line with counts and a clock, and detail on demand |
| Devin | A step plan on one side, the live workspace on the other, and a timeline scrubber to replay the session | The work product is visible while it is being made, and a finished session can be replayed |

Shared lessons:

1. The single most reassuring element is a **"now" line in plain words that changes every few seconds**, next to a clock.
2. **Counts that go up** ("12 sources") read as progress without a progress bar.
3. **Partial results appear in the place the final result will live**, so finishing is a settling, not a page change.
4. Every one of them keeps the trace after the run. Trust comes from being able to look back.

### The reference sites

| Site | What it is | Used here |
| --- | --- | --- |
| aicss.dev | Components for agent conversations: thinking state, thinking + reasoning, to-do list, inline citations, data table, approval card | The inventory confirms the parts: a to-do list with per-item state, a thinking line, citations. Pattern only; its page asks that Pro component source not be reconstructed, and nothing here does |
| orbs.jakubantalik.com → libraries.dev/orbs | `thinking-orbs`, already a dependency. Nine states: working, searching, solving, listening, connecting, weaving, composing, breathing, shaping. Props: state, size, speed, dark, paused | The header orb changes state with the kind of work ([§1.2](#12-the-header-band)), and `paused` is the reduced-motion and finished state |
| loading.dev | 36 small React loaders (Arc, Ring, Scan, Steps, Trace…) | A 12px Arc/Ring style spinner for a running step, drawn in CSS, no new dependency |
| loader-buttons.appllama.io | 25 buttons that change into their own loader and status message | The start button becomes the run header through a shared layout animation ([§1.10](#110-starting-a-run)) |
| amicro.vercel.app, beui.dev, rareui.com, originkit.dev, ui.watermelon.sh | Motion + Tailwind micro-interaction registries (morph, text reveal, to-do list, approval card) | Check-draw and number-tween behaviour. No component is copied; the repo already has `NumberTween` and Motion |
| canvasui.dev, glimm.dev | WebGL canvas effects and shader page transitions | Not used. The design direction rules out shader transitions, and a sweep over arriving rows would hide the thing the user wants to see |
| cuelume-site.pages.dev | `cuelume`, already a dependency. 14 synthesized cues: tap, type, select, toggle, open, close, success, error, navigate, warning, loading, ready, attention, count | `ready`, `success`, `error`, and optionally `count` ([§3.5](#35-sound)) |
| inspora.design, collectui.com, bestdesignsonx.com | Inspiration galleries. collectui has Activity Feed, Status Update, Progress and Loading categories | General reference for feed density only. Nothing specific to agents was found on them |

---

## 1. The live run view

One component, `RunView`, renders every kind of run. It has the same five regions each time; only the **findings stream** in the middle differs by pipeline.

### 1.1 Anatomy

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ A  HEADER BAND   orb · what the run is · NOW line · elapsed · cost meter                    │
├──────────────────────┬───────────────────────────────────────────┬──────────────────────────┤
│ B  STEPS             │ C  FINDINGS STREAM                        │ D  FROM CRUSTDATA        │
│    animated          │    the result, being assembled            │    running tally         │
│    checklist         │    (differs per pipeline)                 ├──────────────────────────┤
│    280px, sticky     │    flexible, min 480px                    │ E  SOURCES               │
│                      │                                           │    live ticker, 320px    │
└──────────────────────┴───────────────────────────────────────────┴──────────────────────────┘
```

- **≥ 1280px:** three columns as drawn. B and the D/E column are sticky under the header; C scrolls with the page.
- **768–1279px:** B and C side by side; D and E become one row of two cards above C.
- **< 768px:** A, then B collapsed to its running step ("Step 3 of 5 · Enrich the top 15" with a disclosure), then D as one line, then C, then E as a horizontally scrolling strip of chips.

Every region is fed by real events ([§2](#2-the-event-schema)). A region with nothing to show yet says so in one muted line ("No pages read yet") and never shows a skeleton that implies content.

### 1.2 The header band

```
 ◍  Analyst working · Discover · "Indian warehousing and supply-chain software…"
    Reading job postings for Stellar Logistics                    1 min 42 s    ▮▮▮▮▮▯▯▯▯▯ 41 of 100 cr · $0.02
```

- **Orb.** The one `thinking-orbs` instance, 20px, in ink. Its `state` follows the kind of the most recent activity event: `searching` for a search call, `connecting` for a page fetch, `weaving` for a model read, `solving` while rules run, `composing` while text is drafted, `working` otherwise. This is information: the mark changes because the work changed. When the run ends it is removed, not paused on screen.
- **Title.** "Analyst working · {kind} · {subject}", as today.
- **NOW line.** One sentence in plain words, present participle, no trailing ellipsis: "Reading delhivery.com/about", "Searching companies in India · warehousing", "Comparing the funding record with the announcement". It is the `label` of the latest `status`, `call` or `source` event. When a new one arrives the old line fades out upward 4px and the new fades in, 200ms. No typewriter. If nothing has arrived for 8 s the line stays and a muted suffix appears: "· 8 s". That suffix is true (it is a clock) and tells the user a slow call is slow, not stuck. After 30 s: "· still waiting on Crustdata" or "· still waiting on the model", from the provider of the open call.
- **Elapsed.** Mono, tabular, ticks every second from `run.created_at` (after a resume, total elapsed stays; "Resumed 16:51" sits beside it).
- **Cost meter.** A 10-segment track plus "41 of 100 cr · $0.02". Credits and model dollars are two currencies and are never added. Each time a `call` event with a cost arrives, the number tweens (360ms) and a small "+3" in mono rises 8px beside it and fades (600ms, once). A cache hit shows "+0 · cache". Segments fill in ink; the segment that crosses 80% of budget fills in the Not checked colour and the text gains "· 20% left". At budget the meter is hatched and the text reads "Budget reached"; nothing turns red, because a stated limit is not an error.

### 1.3 The step checklist (B)

```
 Steps                         2 of 5
 ─────────────────────────────────────
 ✓ Search companies              3 cr
   48 matched in 3 passes
 ✓ Remove duplicates and         0 cr
   must-have failures
   27 kept · 21 dropped
 ◐ Enrich the top 15
   Reading job postings · 9 of 15
 ○ Re-check must-haves and rank
 ○ Explain why each company is on
   the shortlist
```

| State | Mark | Row | Transition in |
| --- | --- | --- | --- |
| pending | open ring, muted | label in muted ink | none |
| running | 12px arc spinner in ink (CSS, 900ms linear rotation) | label in medium ink; sub-line = latest `status` label for this step, with "n of m" when the event carries `progress` | ring crossfades to spinner 140ms; label lifts from muted to ink 200ms |
| done | check | one-line result; cost right-aligned in mono | spinner fades out; the check **draws in** left to right along its path over 200ms (SVG `pathLength` 0 → 1); result line fades in |
| done, from cache | check | result + "from cache · 0 cr" | check appears without the draw (nothing was run, so nothing is performed) |
| skipped (budget) | dashed ring | hatched row, "Skipped · budget reached" | ring's stroke becomes dashed, 200ms; no shake, no colour alarm |
| failed | cross in Contradicted ink | reason + "Retry step" | spinner fades, cross fades in 200ms; same motion as done (good and bad news move the same way) |

- Several steps can run at once (in Verify: registry, events and comparables; claim checks in parallel). Each gets its own spinner. The header orb remains the single orb.
- Clicking a step filters the sources ticker and the tally to that step, and scrolls the findings stream to what that step produced. Clicking again clears the filter.
- Long lists (Verify with 12 claims is ~20 steps): claim-check steps are grouped under one parent row, "Check 12 claims · 7 settled", expandable. The group's mark is a spinner until all are settled.
- The list is an `<ol>`; one polite live-region announcement per step change ("Enrich the top 15, done, 15 enriched").

### 1.4 The Crustdata tally (D)

A running summary of what the data API returned, built by adding up the `counts` on `call` events ([§2.4](#24-kind-call)). It is the answer to "a summarised list of what the Crustdata API has returned".

```
 From Crustdata                              41 cr · 22 calls · 3 from cache
 ───────────────────────────────────────────────────────────────────────────
 48 companies matched · 15 enriched · headcount series for 12 · 37 job postings
 ───────────────────────────────────────────────────────────────────────────
 Company search     3 calls    48 matched               3 cr
 Company enrich     1 call     15 of 15 returned       30 cr
   funding rounds for 9 · headcount series for 12 · web traffic for 4
 Job search        15 calls    37 postings              8 cr
   most open roles: Stellar Logistics 11 · Northwind WMS 7
 Web search         0
 Web fetch          0
```

- The **sentence** on top is the headline: up to four clauses, chosen per pipeline (below), each number tweening as it grows.
- The **table** has one row per endpoint family that this kind of run can use; rows this run has not reached are muted with "0", so the user sees what is still to come without a promise of progress.
- Under a row, one **highlights** line built from the events' `highlights` (never more than two per row, the two most recent replaced as better ones arrive).
- A call that failed adds "1 failed" to its row in Contradicted ink; a retried call that then succeeded shows "1 retried".
- Model work is not Crustdata's, so it sits in a single line below the table: "Model: 18 reads · 46 facts extracted · $0.04".

Headline clauses per pipeline:

| Run | Headline |
| --- | --- |
| Discover | companies matched · enriched · headcount series for n · job postings |
| Investor search | comparable companies · funding rounds read · investors named · rounds with a date |
| Verify | identity candidates · profile fields · people records · pages read · facts extracted |
| Recheck / Evaluate | claims rechecked · pages read · facts extracted · statuses changed |

### 1.5 The source ticker (E)

Every page or record the run reads, newest on top, as it is read.

```
 Sources                                   14 read · 2 could not be read
 ──────────────────────────────────────────────────────────────────────
 [f] economictimes.indiatimes.com                          read 2 s ago
     Meridian Warehousing raises Series A led by …      ✎ News · 5 Jun 2025
 [f] meridianwarehousing.example                           read 6 s ago
     About us                                    ▤ Company site · no date
 [◔] Crustdata · company record                           read 14 s ago
     Meridian Warehousing Pvt Ltd · 4 field groups        as of Oct 2026
 [f] zaubacorp.com                                        read 19 s ago
     MERIDIAN WAREHOUSING PRIVATE LIMITED          ▤ Registry mirror · 2014
 [!] linkedin.com                                could not be read · 403
 ─ 9 earlier ────────────────────────────────────────────────── Show all
```

- **Row:** favicon (16px, rounded 3px) · domain in ink · relative time in mono, right-aligned · second line: page title truncated to one line · the source-class glyph and as-of date in the same form as the product's source line. A Crustdata record has no favicon; it uses the profile-signal glyph and the record type.
- **Relative time** updates every second up to 60 s ("read 2 s ago"), then per minute, then shows the clock time. It is computed from the event's `at`, so a replay shows real times.
- **Arrival:** a new row fades in and rises 8px over 360ms; the rows below move down through a Motion `layout` animation. At most one row enters per 150ms ([§3.2](#32-pacing-batched-so-it-reads)).
- **Length:** six rows are visible while running; older rows fold into "─ 9 earlier ─". "Show all" opens the full list (it is the same list the Sources tab of a case shows).
- **Failed reads** are shown, muted, with the reason in words ("could not be read · 403", "timed out", "blocked by robots"). Hiding them would overstate what was read.
- **Clicking a row** opens the page in a new tab (`rel="noreferrer noopener"`), or for a Crustdata record opens the evidence popover.
- **Public information only.** A row can only be a public web page or a Crustdata record. Uploaded seller documents never appear here; reading one is shown in the step list as "Reading the uploaded document · 14 pages" and nowhere else ([§2.10](#210-confidentiality-rules)).
- **Favicons** come from a same-origin route, `/api/favicon?domain=…`, which fetches and caches the icon server-side. The browser never asks a third-party favicon service, because the list of domains a firm is reading about a target is itself sensitive. If no icon is found the row shows the source-class glyph in a 16px tile.

### 1.6 Findings stream: Discover

The shortlist is assembled in front of the user. A company is a row from the moment the search returns it, and the same row gains detail as each step reaches it.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ◍ Analyst working · Discover · "Indian warehousing and supply-chain software…"                       │
│   Reading job postings for Stellar Logistics            1 min 42 s   ▮▮▮▮▯▯▯▯▯▯ 41 of 100 cr · $0.02 │
├───────────────────────┬──────────────────────────────────────────────────┬───────────────────────────┤
│ Steps          2 of 5 │ Candidates          27 in play · 21 dropped      │ From Crustdata            │
│ ✓ Search companies    │ ──────────────────────────────────────────────── │ 48 matched · 15 enriched  │
│   48 matched    3 cr  │  Stellar Logistics      Pune · ~420 people       │ headcount series for 12   │
│ ✓ Remove duplicates   │  stellarlogistics.example                        │ 37 job postings           │
│   27 kept · 21 dropped│  ✓ funding  ✓ headcount  ◐ hiring                │ ───────────────────────── │
│ ◐ Enrich the top 15   │  Series B · Mar 2025 · headcount +18% in 12 mo   │ Company search   48  3 cr │
│   Job postings 9 of 15│ ──────────────────────────────────────────────── │ Company enrich   15 30 cr │
│ ○ Re-check and rank   │  Northwind WMS          Bengaluru · ~130 people  │ Job search       37  8 cr │
│ ○ Explain each        │  ✓ funding  ✓ headcount  ✓ hiring · 7 open roles │ ───────────────────────── │
│                       │ ──────────────────────────────────────────────── │ Sources          16 read  │
│                       │  Cargomatic India       Mumbai · ~60 people      │ [◔] Crustdata · jobs      │
│                       │  ○ waiting for enrich                            │     Stellar Logistics 2 s │
│                       │ ──────────────────────────────────────────────── │ [◔] Crustdata · company   │
│                       │  … 12 more being enriched                        │     Northwind WMS     9 s │
│                       │  ▸ 12 not in the top 15 (kept, not enriched)     │ ─ 14 earlier ─            │
│                       │  ▸ 21 dropped · 9 duplicates · 12 failed a       │                           │
│                       │    must-have                                     │                           │
└───────────────────────┴──────────────────────────────────────────────────┴───────────────────────────┘
```

A candidate row moves through stages, each driven by a `finding` event with `subject: "company"`:

| Stage | When | What the row shows |
| --- | --- | --- |
| `found` | search returns it | name, domain, city, headcount estimate (labelled as an estimate). Rows arrive in batches of up to 8 per event, and enter 60ms apart |
| `dropped` | gate step | the row's text goes muted and it moves into the collapsed "21 dropped" group with its reason ("duplicate of Stellar Logistics", "failed must-have: privately held"). It is not deleted: the user can open the group |
| `enriching` → `enriched` | enrich step | three small marks, funding / headcount / hiring, each a pending ring that settles to a check or to a dash ("no funding record"). One highlight line appears |
| `scored` | score step | fit and assessable appear on the criteria strip ("Fit 82 · 70% assessable"); the row takes its rank number. Rows reorder to rank order **once**, in a single 360ms layout animation, when the score step finishes — not on every individual score, which would make the list jump |
| `explained` | explain step | the "why it is on the list" line fades in under the row |

Rules that keep it honest:

- Before the score step there is **no rank and no fit number**. Rows are in arrival order and the column header reads "Candidates", not "Shortlist". The header changes to "Shortlist" when ranking is done.
- A dropped company is never shown as if it failed on quality. The reason is the criterion's own label.
- "12 not in the top 15" is stated while it is true, so nobody thinks all 27 were enriched.

### 1.7 Findings stream: Verify (a case run)

The claim ledger fills in. The run view sits on the case page; C is the ledger itself, not a copy of it.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ◍ Analyst working · Verify · Meridian Warehousing                                                    │
│   Reading economictimes.indiatimes.com                  2 min 14 s   ▮▮▮▯▯▯▯▯▯▯ 38 of 150 cr · $0.06 │
├───────────────────────┬──────────────────────────────────────────────────┬───────────────────────────┤
│ Steps         6 of 21 │ Identity  ✓ Confirmed on domain + registration   │ From Crustdata            │
│ ✓ Confirm identity    │ ──────────────────────────────────────────────── │ 3 candidates · 1 profile  │
│ ✓ Build the profile   │ Claims         5 settled · 2 checking · 5 queued │ 6 people · 14 pages read  │
│ ✓ Read the uploaded   │ ──────────────────────────────────────────────── │ 22 facts extracted        │
│   document  12 claims │ ✓ Supported        Incorporated 2014, Pune       │ ───────────────────────── │
│ ◐ Registry records    │   ▤ Registry mirror · as of 12 Mar 2014          │ Company identify  3  0 cr │
│ ◐ Dated events        │ ──────────────────────────────────────────────── │ Company enrich    1  2 cr │
│ ✓ Comparable companies│ ◑ Partially        Opened a new facility, Oct    │ Person search     6  9 cr │
│ ◐ Check 12 claims     │   corroborated     2026                          │ Web search        8  8 cr │
│   5 settled           │   ✎ Announcement · 3 Sep 2026 "…plans to open…"  │ Web fetch        14 14 cr │
│   ✓ incorporation     │ ──────────────────────────────────────────────── │ ───────────────────────── │
│   ✓ funding           │ ◐ checking…        Raised growth funding in 2025 │ Sources   14 read · 2 not │
│   ◐ dated event       │   reading 2 of 4 pages                           │ [f] economictimes…   2 s  │
│   ◐ leadership        │ ──────────────────────────────────────────────── │     Meridian raises …     │
│   ○ team size  …      │ ◐ checking…        Founder ran operations at …   │ [f] meridianware…    6 s  │
│ ○ Assess the case     │   searching professional records                 │     About us              │
│ ○ Draft the request   │ ──────────────────────────────────────────────── │ [◔] Crustdata·people 14 s │
│                       │ ○ queued           We employ 250 people          │     6 leadership records  │
│                       │ ○ queued           We have no debt          …    │ ─ 11 earlier ─            │
└───────────────────────┴──────────────────────────────────────────────────┴───────────────────────────┘
```

A claim row has four live states:

| State | Spine mark | Right side |
| --- | --- | --- |
| `queued` | open ring, muted | nothing |
| `checking` | arc spinner | one muted line of what is being done for this claim, from that step's latest `status` ("reading 2 of 4 pages", "searching professional records") |
| `settled` | the status glyph | status label, the evidence source line, and a snippet of at most 200 characters when the evidence is a public source |
| `not_checked` | dashed ring, hatched row | "Not checked · budget reached" or the reason |

The flip from `checking` to `settled` is the moment of the product, and it uses the motion the design direction already defines for a status mark settling: the spinner fades out, the glyph fades in and scales 0.9 → 1 over 200ms, the label crossfades. Then the evidence line fades in 140ms later, so the eye reads status first and proof second. A row that settles as Cannot verify moves exactly like one that settles as Supported.

- The claim's **text** is not in the event stream. It is already on the page from `GET /cases/{id}`, and the `finding` event carries only the claim id, category, status and a public evidence reference ([§2.7](#27-kind-finding)). When a claim settles, the client also refetches the case (debounced to once per 2 s) so the row has its full evidence list.
- Rows keep their ledger order. They do not jump to the top when they settle; the group header counts do the summarising ("5 settled · 2 checking · 5 queued").
- **Identity** sits above the ledger as a band. While the identity step runs it reads "Confirming which company this is · 3 candidates"; it settles to Confirmed, Ambiguous (with the picker) or Unresolved. If identity is not confirmed the run stops there, the ledger stays `queued`, and the band says why. That is a real outcome, and the page must not look as if it failed.
- **Dated events** and **comparables** found during the run are counted in the tab labels of the case ("Events 6", "Comparables 4"), each count tweening up as `finding` events arrive, and a one-line preview appears under the ledger ("Latest: 5 Jun 2025 · funding announcement · economictimes.indiatimes.com").
- After the claim checks, the **assessment** step writes the disposition. The disposition stamp at the top of the case is a hatched placeholder ("Assessment pending · 5 of 12 claims settled") during the run and settles with the same 200ms mark motion when the `assessment` finding arrives.

### 1.8 Findings stream: Investor search

Investors accumulate from dated rounds. The stream has two halves because the work has two halves: first comparable companies, then the investors behind them.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ◍ Analyst working · Investor search · Logistics software, India, Series A                            │
│   Reading funding rounds of 18 companies                0 min 38 s   ▮▮▮▯▯▯▯▯▯▯ 27 of 100 cr · $0.01 │
├───────────────────────┬──────────────────────────────────────────────────┬───────────────────────────┤
│ Steps          2 of 4 │ Comparable companies that raised           18    │ From Crustdata            │
│ ✓ Read the business   │ Northwind WMS · Cargomatic India · Stellar       │ 18 comparable companies   │
│   profile             │ Logistics · Loadlane · +14                       │ 41 funding rounds read    │
│ ✓ Find comparable     │ ──────────────────────────────────────────────── │ 23 investors named        │
│   companies       18  │ Investors so far      23 named · 41 dated rounds │ 36 rounds with a date     │
│ ◐ Read dated funding  │ ──────────────────────────────────────────────── │ ───────────────────────── │
│   rounds              │  Arkam Ventures                       4 rounds   │ Company search   18  2 cr │
│ ○ Group investors and │  2021 ──●────●──────●───────────●── 2026         │ Company enrich   18 25 cr │
│   rank                │  Northwind WMS · Series A · Mar 2025             │   rounds for 16 of 18     │
│                       │  Loadlane · Seed · Aug 2023   +2                 │ ───────────────────────── │
│                       │ ──────────────────────────────────────────────── │ Sources          18 read  │
│                       │  Blume Ventures                       3 rounds   │ [◔] Crustdata · funding   │
│                       │  2021 ────●──────────●────●──────── 2026         │     Northwind WMS    1 s  │
│                       │  Stellar Logistics · Series B · Mar 2025  +2     │ [◔] Crustdata · funding   │
│                       │ ──────────────────────────────────────────────── │     Loadlane         1 s  │
│                       │  Lightspeed India                     1 round    │ ─ 16 earlier ─            │
│                       │  …                                               │                           │
└───────────────────────┴──────────────────────────────────────────────────┴───────────────────────────┘
```

- Comparable companies arrive as a wrapping line of names (a `finding` with `subject: "company"`, `stage: "found"`), up to 8 per event.
- Each `finding` with `subject: "round"` names a company, a round, a date and its investors. The client groups rounds by investor. A new investor row fades in; an existing one gets its count tweened (+1), a new dot on its round axis (the existing `round-axis.tsx`) that fades and scales in, and its newest round line replaced.
- While rounds are still arriving, rows sort by **first seen**, not by count, so the list does not reshuffle under the reader. The header says "Investors so far". When the rank step finishes, rows reorder once to rank order and the header becomes "Investor shortlist".
- A round with no date is counted in the tally ("36 of 41 rounds with a date") and does not create a dot. An investor supported only by undated rounds is listed after ranking under "Not ranked · no dated round", in line with the PRD.
- Only investor organisation names and round facts are shown. No personal contact details exist in the events, by design.

### 1.9 Findings stream: Evaluate and recheck

These runs are short (a recheck after new seller documents touches a few claims, then re-assesses; an evaluate run only re-applies rules). The same view is used at a smaller size: it is docked at the top of the Assessment tab, B is horizontal, and D/E collapse to their one-line forms.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ◍ Analyst working · Recheck · Meridian Warehousing · after 2 new documents     0 min 21 s · 6 cr     │
│   Applying status rules to "team size"                                                               │
│   ✓ Read the uploaded document ── ◐ Check 3 claims · 1 settled ── ○ Assess the case                  │
├──────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ What is being rechecked                                    3 claims · 9 unchanged and not re-run     │
│ ──────────────────────────────────────────────────────────────────────────────────────────────────── │
│  Team size        Cannot verify  →  ✓ Supported       Seller document · payroll summary, Oct 2026    │
│  Debt             Cannot verify  →  ◐ checking…       reading the uploaded document                  │
│  New facility     Partially corroborated  →  ○ queued                                                │
│ ──────────────────────────────────────────────────────────────────────────────────────────────────── │
│  Assessment v2    Investigate further  →  pending                                                    │
│ From Crustdata: 0 calls (rechecks read seller documents) · Model: 3 reads · $0.02 · Sources: 0 public│
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Each row shows **before → after**. The before value is known from the previous assessment; the after value is `queued` / `checking` / the settled status. A status that did not change settles to "unchanged" in muted ink, which is a result worth stating.
- "9 unchanged and not re-run" is said outright so the short run does not look like a shallow one.
- When the assessment step finishes, this panel **becomes the assessment diff** (design direction §7.4): rows keep their place, the header becomes "Version 2 · what changed", and changed rows get the one-time `accent-tint` fade. The diff is the settled form of the live view.
- The tally says "0 calls" for Crustdata when that is the truth. The seller document's own content is never previewed in the stream; its evidence line names it as "Seller document · payroll summary" and opens through the existing signed-URL flow.
- A pure Evaluate run (rules only, no credits) lasts a second or two. It shows the header and the three-step line only, with no empty columns.

### 1.10 Starting a run

The first second matters as much as the rest. Pressing "Search" / "Verify" / "Find investors":

1. The button shows a 12px spinner in place for as long as the `POST` takes (real wait, usually under a second).
2. On the 202 response the button's container changes shape into the header band through a shared layout animation (360ms), and the run view's columns fade in beneath it with their empty-state lines.
3. The NOW line reads "Starting" until the first event; the step list is already there from the response's steps, all pending.

No fake "warming up" events. If the worker takes four seconds to pick the run up, the page says "Waiting for a worker · 4 s".

### 1.11 Finishing: how the live view becomes the result

There is no swap, because the findings stream was the result all along. When the terminal `run` event arrives:

1. **0 ms.** The pacing queue is flushed: anything not yet shown appears at once (a finished run must not keep "arriving").
2. **0–200 ms.** The orb is removed. The NOW line is replaced by the finished line: "Discover finished · 2 min 51 s · 61 of 100 credits · $0.04 · 2 checks not run".
3. **200–560 ms.** One layout animation: the header band shrinks to a single line; the step rail (B) and the tally/sources column (D/E) fade out and the findings column (C) widens to the full content width. The rows inside C do not re-enter; they keep their identity (`layoutId` per company, claim or investor) and only widen.
4. The single line keeps three links: **Run log** (everything that just folded away, [§4](#4-replay-and-the-run-log)), **Sources (16)** and **Cost**.
5. If the run was Discover or Investor search, the one-time reorder to rank order has already happened at the end of the rank step, so nothing moves now.
6. Sound, if the user turned it on: the `ready` cue, once.

If the user is scrolled down in the findings when the run ends, the page keeps their scroll position on the row they were reading (anchor the scroll to the first visible row before the layout change).

If the run **fails**: steps and sources stay open (they are the diagnosis), the header reads "Run stopped · {step} did not finish: {reason}", and "Resume run" sits in the header. Findings already settled stay settled. After a resume, replayed steps show "from cache · 0 cr" and their events arrive marked `from_cache`, drawn without entrance animation.

If the user **leaves and comes back** mid-run: the view is rebuilt from the stored events ([§2.11](#211-transport)). Backlog is drawn instantly in its settled form; only events that arrive from then on animate.

---

## 2. The event schema

### 2.1 Overview

The stream at `GET /runs/{id}/events` keeps its two events and gains one:

| SSE event | Payload | Change |
| --- | --- | --- |
| `run` | `RunOut` without steps | Also sent whenever `cost` changes (today only on state change), so the cost meter is driven by the server's totals |
| `step` | `StepOut` | Unchanged |
| `activity` | `ActivityOut` (below) | **New.** Append-only, ordered by `seq` |

Activities are **persisted** in a new table and are the single source for the live view, the reload-mid-run case, and the run log. They are facts about what the run did, never instructions and never estimates of progress.

### 2.2 The envelope

Every activity has this shape. Fields not used by a kind are `null`, never omitted.

```jsonc
{
  "seq": 42,                       // int, per run, strictly increasing from 1. Also the SSE `id:`
  "run_id": "5b0c…",
  "step_id": "9a1e…",              // the step that emitted it
  "step_key": "discover.enrich",
  "kind": "call",                  // status | call | source | model | finding | notice
  "at": "2026-11-22T11:12:41.318Z",// when it happened (UTC, ms). Not when it was sent
  "label": "Enriched 15 companies",// ≤ 120 chars, plain words, built from a template (§2.10)
  "detail": "funding, headcount and web traffic", // ≤ 200 chars or null
  "progress": { "done": 9, "total": 15 },         // or null. Only when both numbers are real
  "source":   null,                // SourceRef, for kind = source (and finding evidence)
  "call":     null,                // CallInfo, for kind = call | model
  "counts":   null,                // { [key: string]: int } — keys fixed per kind/endpoint
  "highlights": null,              // string[] ≤ 2, each ≤ 100 chars
  "items":    null,                // preview items, ≤ 8, typed by `subject`
  "subject":  null,                // company | claim | investor | round | identity | event | peer | assessment | request_list
  "code":     null,                // notice code, for kind = notice (§2.8)
  "ref":      null                 // { "type": "claim", "id": "…" } — the row this is about
}
```

Shared sub-objects:

```jsonc
// SourceRef — a public page or a Crustdata record. Never an uploaded document's content.
{
  "type": "web_page",              // web_page | crustdata_record | seller_document
  "domain": "economictimes.indiatimes.com", // registrable host, lower case; null for non-web
  "url": "https://economictimes.indiatimes.com/…", // null for crustdata_record and seller_document
  "title": "Meridian Warehousing raises Series A", // ≤ 140 chars; page <title> or record name
  "source_class": "news",          // the product's reliability classes
  "as_of": "2025-06-05",           // date of the fact, or null → UI says "no date"
  "state": "read",                 // read | failed | skipped
  "reason": null                   // when not read: http_403 | timeout | robots | empty | too_large | budget
}

// CallInfo — one external call, final state only (emitted when it returns)
{
  "provider": "crustdata",         // crustdata | anthropic
  "endpoint": "company_enrich",    // company_identify | company_search | company_enrich |
                                   // person_search | job_search | web_search | web_fetch | messages
  "ok": true,
  "error": null,                   // allowlisted code when ok = false (same list as CallAttempt.error)
  "from_cache": false,
  "attempts": 1,                   // HTTP dispatches; > 1 means it was retried
  "duration_ms": 1840,
  "credits": 30.0,                 // this call. 0 on a cache hit. null when the provider did not report
  "usd": null,                     // model calls only
  "credits_total": 41.0,           // run totals after this call, so a replay can redraw the meter
  "usd_total": 0.02
}
```

### 2.3 Kind `status`

What the agent is doing now, in plain words. Drives the NOW line and the running step's sub-line. Emitted at the **start** of a unit of work.

`ctx.set_detail(text)` keeps working and additionally emits a `status` with that text as the label, so existing call sites light up with no change. New call sites should use `ctx.activity.status(...)` to add `progress` and `ref`.

```json
{
  "seq": 17, "run_id": "5b0c…", "step_id": "9a1e…", "step_key": "discover.enrich",
  "kind": "status", "at": "2026-11-22T11:12:44.020Z",
  "label": "Reading job postings for Stellar Logistics",
  "detail": null, "progress": { "done": 9, "total": 15 },
  "source": null, "call": null, "counts": null, "highlights": null,
  "items": null, "subject": null, "ref": null
}
```

Rules: at most one `status` per second per step (the emitter drops intermediate ones, keeping the latest); the label is a present participle with no ellipsis and no trailing period.

### 2.4 Kind `call`

One Crustdata call has returned (or failed, or was served from cache). Drives the tally, the cost meter and the orb state. Emitted **after** the call, from the parsed result and its `CallRecord`.

```json
{
  "seq": 16, "run_id": "5b0c…", "step_id": "9a1e…", "step_key": "discover.enrich",
  "kind": "call", "at": "2026-11-22T11:12:41.318Z",
  "label": "Enriched 15 companies", "detail": "funding, headcount and web traffic",
  "progress": null, "source": null,
  "call": { "provider": "crustdata", "endpoint": "company_enrich", "ok": true, "error": null,
            "from_cache": false, "attempts": 1, "duration_ms": 1840,
            "credits": 30.0, "usd": null, "credits_total": 41.0, "usd_total": 0.02 },
  "counts": { "requested": 15, "returned": 15, "with_funding": 9,
              "with_headcount_series": 12, "with_web_traffic": 4 },
  "highlights": ["Stellar Logistics · Series B · Mar 2025", "Northwind WMS · headcount +18% in 12 months"],
  "items": null, "subject": null, "ref": null
}
```

`counts` keys are fixed per endpoint. The tally adds them up by key, so the keys are part of the contract:

| `endpoint` | `counts` keys | Headline it feeds |
| --- | --- | --- |
| `company_identify` | `candidates` | "3 candidates" |
| `company_search` | `returned`, `total_available` (null → omit), `new` (not seen in an earlier pass of this run) | "48 companies matched" = sum of `new` |
| `company_enrich` | `requested`, `returned`, `with_funding`, `funding_rounds`, `with_investors`, `with_headcount_series`, `with_web_traffic` | "15 enriched · headcount series for 12" |
| `person_search` | `returned`, `current_leadership` | "6 people" |
| `job_search` | `postings`, `companies` | "37 job postings" |
| `web_search` | `hits`, `news_hits` | "8 searches · 61 results" |
| `web_fetch` | `requested`, `read`, `failed` | "14 pages read" |

A failed call:

```json
{
  "seq": 31, "run_id": "5b0c…", "step_id": "c77d…", "step_key": "verify.events",
  "kind": "call", "at": "2026-11-22T11:14:02.900Z",
  "label": "News search did not return", "detail": "Crustdata timed out after 3 tries",
  "progress": null, "source": null,
  "call": { "provider": "crustdata", "endpoint": "web_search", "ok": false, "error": "timeout",
            "from_cache": false, "attempts": 3, "duration_ms": 30112,
            "credits": 0.0, "usd": null, "credits_total": 38.0, "usd_total": 0.06 },
  "counts": null, "highlights": null, "items": null, "subject": null, "ref": null
}
```

Rules: `highlights` are built only from public record fields (company name, round name and date, city, counts). The **search query and filter body are never sent** for case runs, because they can be derived from confidential claims; for Discover and Investor runs the `detail` may name the filters in words ("India · warehousing · 50–500 people"), which are the user's own criteria.

### 2.5 Kind `source`

One page or record was read (or could not be). Drives the source ticker. One event **per page**, even when ten pages came back from one `web_fetch` call: the handler emits them in the order the pages were processed, each with its own `at`.

```json
{
  "seq": 33, "run_id": "5b0c…", "step_id": "c77d…", "step_key": "verify.events",
  "kind": "source", "at": "2026-11-22T11:14:09.440Z",
  "label": "Read economictimes.indiatimes.com", "detail": null, "progress": { "done": 2, "total": 4 },
  "source": { "type": "web_page", "domain": "economictimes.indiatimes.com",
              "url": "https://economictimes.indiatimes.com/small-biz/meridian-series-a/articleshow/1.cms",
              "title": "Meridian Warehousing raises Series A led by Arkam", "source_class": "news",
              "as_of": "2025-06-05", "state": "read", "reason": null },
  "call": null, "counts": null, "highlights": null, "items": null, "subject": null,
  "ref": { "type": "claim", "id": "0c9f…" }
}
```

A Crustdata record and a failed page:

```json
{ "seq": 12, "kind": "source", "step_key": "verify.profile", "at": "2026-11-22T11:12:20.100Z",
  "label": "Read the company record", "detail": "4 field groups",
  "source": { "type": "crustdata_record", "domain": null, "url": null,
              "title": "Meridian Warehousing Pvt Ltd · company record",
              "source_class": "professional_profile_signal", "as_of": "2026-10-01",
              "state": "read", "reason": null } }
```

```json
{ "seq": 34, "kind": "source", "step_key": "verify.events", "at": "2026-11-22T11:14:09.600Z",
  "label": "Could not read linkedin.com", "detail": null,
  "source": { "type": "web_page", "domain": "linkedin.com", "url": "https://www.linkedin.com/company/…",
              "title": null, "source_class": "company_announcement", "as_of": null,
              "state": "failed", "reason": "http_403" } }
```

(The two short examples omit null envelope fields for space; the wire format includes them.)

Rules: `ref` is set when the page was read for one claim, so the claim row can show "reading 2 of 4 pages". `url` has its query string stripped of tracking parameters and is dropped entirely (set to null, domain kept) if it contains credentials or a token-like parameter. `type: "seller_document"` is allowed **only** with `title` set to the document kind in words ("Seller document · presentation"), never the filename, and it is shown in the step list, not the ticker.

### 2.6 Kind `model`

A model read or draft finished. Feeds the "Model:" line and the cost meter. It carries **counts only**: no prompt, no completion, no extracted text.

```json
{
  "seq": 35, "run_id": "5b0c…", "step_id": "c77d…", "step_key": "verify.events",
  "kind": "model", "at": "2026-11-22T11:14:12.008Z",
  "label": "Extracted 3 dated facts from the article", "detail": null, "progress": null,
  "source": null,
  "call": { "provider": "anthropic", "endpoint": "messages", "ok": true, "error": null,
            "from_cache": false, "attempts": 1, "duration_ms": 2410,
            "credits": null, "usd": 0.004, "credits_total": 38.0, "usd_total": 0.064 },
  "counts": { "facts": 3, "rejected_no_span": 1 },
  "highlights": null, "items": null, "subject": null, "ref": { "type": "claim", "id": "0c9f…" }
}
```

`counts` keys by purpose: fact extraction `facts`, `rejected_no_span`; claim intake `claims`, `pages`; thesis or profile parsing `criteria`; explanations `explained`; request drafting `request_items`. `rejected_no_span` is shown ("1 discarded: no matching passage") because it is evidence that the product checks the model, which is the point of the product.

### 2.7 Kind `finding`

A piece of the result exists or changed state. Drives the findings stream. `subject` says what it is; `items` carries up to 8 typed previews; `counts` carries the group totals after this event.

**Company (Discover; comparables in Investor search and Verify)**

```json
{
  "seq": 6, "run_id": "5b0c…", "step_id": "71aa…", "step_key": "discover.search",
  "kind": "finding", "at": "2026-11-22T11:11:58.700Z",
  "label": "Found 8 companies", "detail": "primary pass", "progress": null,
  "source": null, "call": null,
  "counts": { "found": 24, "in_play": 24, "dropped": 0, "enriched": 0, "scored": 0 },
  "highlights": null, "subject": "company",
  "items": [
    { "id": "cand_01", "stage": "found", "name": "Stellar Logistics",
      "domain": "stellarlogistics.example", "location": "Pune, India",
      "headcount": 420, "headcount_is_estimate": true,
      "reason": null, "marks": null, "highlight": null, "fit": null, "assessable": null, "rank": null }
  ],
  "ref": null
}
```

Later stages reuse the item shape and send only the rows that changed:

```json
{ "seq": 9, "kind": "finding", "step_key": "discover.gate", "subject": "company",
  "label": "Dropped 21 companies", "detail": "9 duplicates · 12 failed a must-have",
  "counts": { "found": 48, "in_play": 27, "dropped": 21, "enriched": 0, "scored": 0 },
  "items": [ { "id": "cand_17", "stage": "dropped", "name": "Stellar Logistics India",
               "reason": "Duplicate of Stellar Logistics" },
             { "id": "cand_22", "stage": "dropped", "name": "Portside Freight",
               "reason": "Failed must-have: privately held" } ] }
```

```json
{ "seq": 19, "kind": "finding", "step_key": "discover.enrich", "subject": "company",
  "label": "Enriched Stellar Logistics", "counts": { "found": 48, "in_play": 27, "dropped": 21, "enriched": 9, "scored": 0 },
  "items": [ { "id": "cand_01", "stage": "enriched", "name": "Stellar Logistics",
               "marks": { "funding": "found", "headcount": "found", "hiring": "pending" },
               "highlight": "Series B · Mar 2025 · headcount +18% in 12 months" } ] }
```

```json
{ "seq": 26, "kind": "finding", "step_key": "discover.score", "subject": "company",
  "label": "Ranked 15 companies", "counts": { "found": 48, "in_play": 27, "dropped": 21, "enriched": 15, "scored": 15 },
  "items": [ { "id": "cand_01", "stage": "scored", "name": "Stellar Logistics",
               "fit": 82, "assessable": 0.7, "rank": 1 } ] }
```

`marks` values: `pending | found | none | not_checked`. When more than 8 rows change in one step (the gate drops 21), the event carries the first 8 and the counts; the client reads the rest from the result endpoint when the step's `step` event says done. The `id` is the candidate row's id so the client can join with `GET /theses/{id}`.

**Claim (Verify, recheck)**

```json
{
  "seq": 40, "run_id": "5b0c…", "step_id": "e3b2…", "step_key": "checks.claim:0c9f…",
  "kind": "finding", "at": "2026-11-22T11:14:20.300Z",
  "label": "Claim settled: Partially corroborated", "detail": "dated event", "progress": null,
  "source": { "type": "web_page", "domain": "meridianwarehousing.example",
              "url": "https://meridianwarehousing.example/news/pune-facility",
              "title": "Meridian plans new Pune facility", "source_class": "company_announcement",
              "as_of": "2026-09-03", "state": "read", "reason": null },
  "call": null,
  "counts": { "queued": 5, "checking": 2, "settled": 5, "not_checked": 0 },
  "highlights": null, "subject": "claim",
  "items": [ { "id": "0c9f…", "stage": "settled", "category": "dated_event",
               "status": "partially_corroborated", "previous_status": null,
               "evidence_count": 2,
               "snippet": "…plans to open a 40,000 sq ft facility in Chakan by October…",
               "gap": "Nothing found shows the facility is operating" } ],
  "ref": { "type": "claim", "id": "0c9f…" }
}
```

- `stage`: `queued | checking | settled | not_checked`. A `queued` event is sent once per claim when its check step is created; `checking` when the step starts.
- **No claim text.** The client already has it. `category` is the only description.
- `snippet` (≤ 200 chars) is present **only** when the evidence `source.type` is `web_page` or `crustdata_record`. For seller-document evidence it is null and the UI shows the source line alone.
- `gap` is the rule's own canned sentence for what is missing (from the rules table), never model text about the document.
- `previous_status` is set on recheck runs and drives "before → after".

**Identity**

```json
{ "seq": 4, "kind": "finding", "step_key": "verify.identity", "subject": "identity",
  "label": "Identity confirmed", "detail": "matched on domain and registration number",
  "counts": { "candidates": 3 },
  "items": [ { "id": "681234", "stage": "confirmed", "name": "Meridian Warehousing Pvt Ltd",
               "domain": "meridianwarehousing.example", "matched_keys": ["domain", "registration_number"] } ] }
```

`stage`: `confirmed | ambiguous | unresolved`. On `ambiguous`, `items` holds up to 5 candidates with `matched_keys` so the picker can open at once.

**Round and investor (Investor search)**

```json
{
  "seq": 14, "run_id": "77d1…", "step_id": "aa20…", "step_key": "investors.enrich",
  "kind": "finding", "at": "2026-11-22T11:20:31.150Z",
  "label": "Read 3 funding rounds of Northwind WMS", "detail": null, "progress": { "done": 4, "total": 18 },
  "source": null, "call": null,
  "counts": { "companies": 18, "rounds": 11, "rounds_dated": 10, "investors": 9 },
  "highlights": null, "subject": "round",
  "items": [
    { "id": "rnd_0091", "stage": "found", "company": "Northwind WMS", "company_id": "cmp_31",
      "round": "Series A", "date": "2025-03-14", "amount_usd": 12000000,
      "investors": [ { "key": "arkam-ventures", "name": "Arkam Ventures" },
                     { "key": "blume-ventures", "name": "Blume Ventures" } ] }
  ],
  "ref": null
}
```

```json
{ "seq": 30, "kind": "finding", "step_key": "investors.rank", "subject": "investor",
  "label": "Ranked 23 investors", "counts": { "investors": 23, "ranked": 19, "not_ranked": 4 },
  "items": [ { "id": "arkam-ventures", "stage": "ranked", "name": "Arkam Ventures", "rank": 1,
               "comparable_rounds": 4, "last_round_date": "2025-03-14" } ] }
```

`date` null means undated: counted, no dot, cannot be ranked on. `investors[].key` is the pipeline's own grouping key so the client's grouping matches the server's.

**Event, peer, assessment, request list** (same envelope; only `items` shown)

```json
{ "subject": "event", "label": "Found a dated event", "counts": { "events": 6 },
  "items": [ { "id": "evt_12", "stage": "found", "date": "2025-06-05",
               "event_kind": "funding", "title": "Funding announcement", "domain": "economictimes.indiatimes.com" } ] }
```

```json
{ "subject": "peer", "label": "Found 4 comparable companies", "counts": { "peers": 4 },
  "items": [ { "id": "681777", "stage": "found", "name": "Loadlane", "location": "Chennai, India", "headcount": 210, "headcount_is_estimate": true } ] }
```

```json
{ "subject": "assessment", "label": "Assessment written: Investigate further", "counts": { "supported": 3, "open": 3 },
  "items": [ { "id": "asm_v2", "stage": "written", "version": 2, "disposition": "investigate_further",
               "previous_disposition": "investigate_further", "fit": 78, "assessable": 0.7 } ] }
```

```json
{ "subject": "request_list", "label": "Drafted a request for 3 documents", "counts": { "request_items": 3 },
  "items": [ { "id": "req_5", "stage": "drafted" } ] }
```

Event `title` is the event kind in words plus the publisher's domain, not the model's summary of the article. The request list's item text is not in the stream.

### 2.8 Kind `notice`

Something about the run itself that the user should know: a limit, a retry, a widening, a resume. Shown as a muted line in the step list under its step, and in the run log.

```json
{
  "seq": 8, "run_id": "5b0c…", "step_id": "71aa…", "step_key": "discover.search",
  "kind": "notice", "at": "2026-11-22T11:12:02.010Z",
  "label": "Widened the search", "detail": "The strict filters returned 6 companies; preferences were relaxed",
  "progress": null, "source": null, "call": null,
  "counts": null, "highlights": null, "items": null, "subject": null,
  "code": "search_widened", "ref": null
}
```

`label` and `detail` are fixed sentences per `code`, with counts as the only slots. Codes: `search_widened`, `budget_low` (20% left), `budget_reached`, `step_resumed`, `served_from_cache`, `call_retried`, `source_limit` (more hits than the read cap), `identity_blocked` (run stops at identity), `nothing_to_check`.

### 2.9 Which step emits what

| Run | Step (key) | `status` | `call` | `source` | `model` | `finding` | `notice` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Discover | `discover.search` | "Resolving filter values"; "Searching companies ({filters in words})" per pass | `company_search` per pass | — | — | `company` `found`, ≤ 8 per event | `search_widened` |
| | `discover.gate` | "Removing duplicates and must-have failures" | — | — | — | `company` `dropped` (first 8 + counts) | — |
| | `discover.enrich` | "Enriching 15 companies"; "Reading job postings for {name}" with progress | `company_enrich` ×1; `job_search` per company | `crustdata_record` per company enriched | — | `company` `enriching` then `enriched`, one per company | `budget_low`, `budget_reached` |
| | `discover.score` | "Applying your criteria to 15 companies" | — | — | — | `company` `scored`, all rows in one or two events | — |
| | `discover.explain` | "Writing why each company is on the list" with progress | — | — | one per company (`explained`) | `company` `explained` | — |
| Investor search | `investors.spec` | "Reading the business profile" | — | — | 1 (`criteria`) | — | — |
| | `investors.comparables` | "Searching for comparable companies that raised money" | `company_search` | — | — | `company` `found` | `search_widened` |
| | `investors.enrich` | "Reading funding rounds of 18 companies" with progress | `company_enrich` | `crustdata_record` per company | — | `round` `found`, one event per company | `budget_reached` |
| | `investors.rank` | "Grouping investors and ranking by dated comparable rounds" | — | — | — | `investor` `ranked` | — |
| Verify | `verify.identity` | "Matching the domain {domain}"; "Matching the name" | `company_identify` | — | — | `identity` | `identity_blocked` |
| | `verify.profile` | "Reading the company record" | `company_enrich` | `crustdata_record` | — | — | — |
| | `verify.registry` | "Searching public registry records"; "Reading {domain}" per page | `web_search`, `web_fetch` | `web_page` per page | per page chunk (`facts`) | — | `source_limit` |
| | `verify.events` | "Searching news about the company"; "Reading {domain}" per page | `web_search` ×1–2, `web_fetch` | `web_page` per page | per page (`facts`) | `event` per dated event | `source_limit` |
| | `verify.comparables` | "Searching for comparable companies" | `company_search` | — | — | `peer` | — |
| | claim intake (`claims.extract:{document_id}`) | "Reading the uploaded document" with page progress | — | — | 1+ (`claims`, `pages`) | `claim` `queued`, one event for all claims (ids and categories only) | `nothing_to_check` |
| | claim check (`checks.claim:{claim_id}`) | "Checking: {category}"; "Searching professional records"; "Reading {domain}" | `person_search`, `web_search`, `web_fetch`, `company_enrich` as the category needs | `web_page` / `crustdata_record`, with `ref` = the claim | per text unit (`facts`, `rejected_no_span`) | `claim` `checking` at start, `settled` or `not_checked` at end | `budget_reached`, `served_from_cache` |
| | `evaluate` | "Applying the screening rules" | — | — | — | `assessment` | — |
| | `request_list` | "Drafting the document request" | — | — | 1 (`request_items`) | `request_list` | — |
| Recheck | intake, affected claim checks, `evaluate` | as Verify | usually none | `seller_document` (step list only) | as Verify | `claim` with `previous_status`; `assessment` with `previous_disposition` | — |
| Evaluate | `evaluate` | "Applying the screening rules" | — | — | — | `assessment` | — |

Step keys are the constants in the code today (`verify.*`, `claims.extract:`, `checks.claim:`, `evaluate`, `request_list`, `discover.*`, `investors.*`).

### 2.10 Confidentiality rules

The stream is stored and replayed, so it holds **public lookup information and the user's own criteria only**.

1. **Never in any event:** claim text, any text from an uploaded document, document filenames, prompts, model output, search queries for case runs, request-list item text, email text, personal contact details.
2. **Labels come from templates.** `label` and `detail` are built by functions in one module from an allowlist of templates with typed slots: a domain, a public company name, a count, a claim **category**, a criterion label, a filter in words. No free string from a document or a model can reach them. `ctx.set_detail` is the one free-text entry point; the backend chunk audits its call sites and removes the two that leak today (`f"Reading {document.filename}"` in claim intake, and the step label `f"Read claims from {filename}"`, which should become "Read claims from the uploaded {kind}").
3. **Snippets** are allowed only from `web_page` and `crustdata_record` sources, ≤ 200 chars, and only inside `finding` items.
4. **Company names in case runs** are the confirmed public entity name. Before identity is confirmed, events use "the company".
5. **Scope.** The activity endpoints are workspace-scoped exactly like `GET /runs/{id}`. "Public only" is a second wall, not the only one.
6. **Deletion.** Activities are deleted with their run. They need no separate expiry because rule 1 keeps confidential text out; a test enforces rule 1 by running each pipeline against a fixture deck containing a canary string and asserting the string never appears in `run_activities`.

### 2.11 Transport

- **Table** `run_activities`: `id`, `workspace_id`, `run_id` (FK, cascade delete), `step_id`, `seq` (int, unique with `run_id`), `kind`, `at`, `payload` (JSONB, the envelope). `seq` is allocated with `SELECT coalesce(max(seq),0)+1 … FOR UPDATE` on the run row, or a per-run advisory lock, since parallel steps emit at once.
- **Emission** commits in its own short session (like `set_detail`), so an event is visible immediately and survives a handler rollback. That is correct: the call really happened and really cost credits even if the step later fails.
- **Resume and retries.** A retried or resumed step emits again. Its events carry `call.from_cache: true` where calls replay from cache, and a `step_resumed` notice precedes them. The client keys rows by item id, so a replayed `found` updates the same row and creates no duplicate.
- **SSE.** `run_event_stream` polls `run_activities WHERE run_id = :id AND seq > :last ORDER BY seq` each tick and yields `id: {seq}\nevent: activity\ndata: {json}\n\n`. Poll interval drops from 1 s to 0.5 s while the run is live. On connect it accepts `Last-Event-ID` (set by `EventSource` on reconnect) or `?after={seq}`; with neither it sends the whole backlog first, then a comment line `: live`, then new events. The client draws everything before `: live` without animation.
- **REST.** `GET /runs/{id}/activity?after=0&limit=500` → `{ "items": ActivityOut[], "next_after": 500 | null }`. Used by the run log and by the polling fallback (every 2 s with the last `seq`).
- **Volume.** A Discover run is about 60 events, a 12-claim Verify about 250. Cap: 2,000 per run; past it the emitter stores `status` events only for the latest per step and emits one `notice`.
- **Fixtures.** Fixture mode gets recorded activity lists per fixture run, replayed with their real spacing compressed to at most 600 ms between events, so the demo without a backend still feels live and is still a recording of a plausible run rather than random filler.

---

## 3. Motion and feel

### 3.1 Easing and durations

No new values. The product curve `cubic-bezier(0.22, 1, 0.36, 1)` and the three durations (140 / 200 / 360ms) from the design direction cover everything here:

| Thing | Motion | Duration |
| --- | --- | --- |
| NOW line change | old fades and rises 4px out, new fades in | 200ms |
| Row enters (source, candidate, investor, claim becoming visible) | fade + rise 8px; siblings shift by `layout` | 360ms |
| Check draws in | SVG path length 0 → 1 | 200ms |
| Status mark settles | spinner out, glyph in, scale 0.9 → 1; label crossfade; evidence line follows 140ms later | 200ms + 140ms |
| Counter tween (tally, cost, group counts) | tabular digits tween | 360ms |
| "+3" credit delta | rises 8px and fades | 600ms, once |
| Reorder to rank | one `layout` pass for the whole list | 360ms |
| Finish: columns fold, findings widen | one `layout` pass | 360ms |
| Step spinner | linear rotation | 900ms per turn, only while that step runs |

Only `opacity`, `transform` and colours animate. Row height changes go through Motion `layout`, not animated height.

### 3.2 Pacing: batched so it reads

Events arrive in bursts (the stream polls twice a second, and a search returns 48 companies at once). Dumping a burst is unreadable; trickling it slowly would be lying about time. The client uses a small **reveal queue** per region:

- Each region (ticker, findings, tally) reveals at most **one item per 150 ms**. Items within one event that hold several previews stagger 60 ms apart.
- The queue may delay an item by at most **1.5 s**. If the backlog would exceed that, everything older is revealed at once, without animation, with one summary line animating in ("+ 14 more"). So the display is never more than 1.5 s behind reality.
- The NOW line never queues: it always shows the latest label. It changes at most once per 400 ms; intermediate labels are skipped, not shown late.
- Counters tween straight to the newest total; they do not step through intermediate values.
- When the terminal `run` event arrives, every queue flushes immediately.
- Backlog (events before `: live`, or more than 3 s older than now when received) is drawn settled, no animation.

"Read 2 s ago" is computed from the event's `at`, not from when the row was revealed, so pacing never falsifies a timestamp.

### 3.3 Reduced motion

Under `prefers-reduced-motion: reduce` (already wired through `MotionConfig reducedMotion="user"`):

- The orb is replaced by the word "Working" in the bordered mono chip that exists today.
- Step spinners become a static half-filled ring (◐); the check appears without drawing.
- Rows appear in place, no rise, no stagger; the reveal queue still limits to one batch per 400 ms so screen readers and eyes are not flooded.
- Counters jump to their value; the "+3" delta is a static "+3" for 1 s, then gone.
- Reorder and finish happen instantly; the rank reorder announces "Shortlist ranked" in the live region.
- Relative times still update, but once every 10 s.

### 3.4 Accessibility of a live view

- One polite live region for the run. It announces step changes and finding settlements ("Claim 7, dated event: partially corroborated"), at most one announcement per 2 s; the rest are dropped, since the list itself is navigable. Sources and counters are **not** announced.
- The ticker is a `<ul>` with `aria-label="Sources read, newest first"`, not a `role="log"` with assertive behaviour.
- New rows must never move focus or shift the row under the pointer by more than its own slot: rows enter at the top of the ticker but **at the bottom** of the findings list, where nothing is being read yet.
- A "Pause updates" control in the header freezes the reveal queues (events keep being received; a chip reads "12 new"). Needed for anyone reading a row while the list grows, and satisfies WCAG 2.2.2.
- All states have a text equivalent next to the glyph; colour and motion are never the only signal.

### 3.5 Sound

Off by default, as the design direction says. One setting with three levels, per user:

| Level | Cues (`cuelume`) |
| --- | --- |
| Off (default) | none |
| Run finished | `ready` when a run finishes; `error` when a run stops with a failure; `success` when a send is approved and sent (existing rule) |
| Live cues (opt-in, for demos) | the above, plus `count` when a finding settles (a claim reaches a status, the shortlist is ranked). Rate-limited to one per 600 ms; never for sources, never for status lines, never while the tab is hidden |

A cue only ever accompanies a visible state change. Audio starts only after a user gesture on the page (the start button is one), which is also what browsers require.

### 3.6 Anti-gimmick rules

These are the rules that separate "feels alive" from "is pretending". They are requirements, and review should reject a PR that breaks one.

1. **Every visible item is one stored event.** No client-side generated rows, labels, domains or counts. If the stream is silent, the page is still, apart from the clock, the orb and the step spinner.
2. **No fake progress.** No percentage, no bar that advances on a timer, no "estimated time left". "9 of 15" appears only when the server sent both numbers.
3. **No fake typing.** Text appears whole. Nothing is revealed character by character, because nothing is being typed: the model's output is validated before any of it is shown.
4. **No invented waiting messages.** No rotating "Crunching the numbers…" lines. The only time-based text is the true idle clock ("· 8 s") and the true provider name of the open call.
5. **Pacing may delay, never invent or reorder across regions**, and never by more than 1.5 s.
6. **Failures are shown at the same weight as successes.** Pages that could not be read, calls that failed, facts the checker rejected.
7. **Cache is said out loud.** A replayed step does not perform its animation again and reads "from cache · 0 cr".
8. **Provisional is labelled provisional.** "Candidates" until ranked; "Investors so far" until ranked; "checking" until the rule fires. No fit number, rank or status appears before the step that computes it.
9. **The orb means work is happening now.** It is removed the moment the run ends and never used as decoration.
10. **A replay says it is a replay** ([§4](#4-replay-and-the-run-log)) and spends nothing.

### 3.7 Changes to the design direction

| Rule in `design-direction.md` | Change |
| --- | --- |
| §9 principle 4: "Nothing loops except the single run indicator" | Becomes: nothing loops except **run indicators while a run is live**: the one header orb, and a 12px spinner on each running step and each claim being checked. All stop when their work stops. This is the user's explicit request (step states with a spinner) |
| §7.6: the running step shows a chevron | Replaced by the spinner; the chevron is no longer used for state |
| §7.6: "the panel collapses to one line" | Kept, and specified as a layout animation that widens the findings ([§1.11](#111-finishing-how-the-live-view-becomes-the-result)) |
| §9 "Not used anywhere: … typewriter text, pulsing dots, shimmer" | Unchanged and reaffirmed |
| §9 Sound: three cues | A fourth, `count`, exists only at the opt-in "Live cues" level |

---

## 4. Replay and the run log

A finished run can be opened and inspected, with the same components.

**Where**

- Cases: a new tab, **Run log**, at `/app/cases/{id}/log`, listing the case's runs (verify, rechecks, evaluate) newest first; selecting one shows it.
- Discover and Investor search: a **Run log** link in the finished line, opening `/app/discover/{thesisId}/log` and `/app/investors/{id}/log`.
- The finished line's "Run log" link (which today points nowhere specific) goes to these.

**What it shows** — `RunView` with `mode="log"`:

```
 Verify · Meridian Warehousing · 22 Nov 2026, 16:42–16:45 IST · 2 min 51 s · 61 of 150 cr · $0.09 · 2 checks not run
 [ Timeline ]  [ Sources 16 ]  [ Crustdata 31 calls ]  [ Cost ]                              ▷ Replay · 8×
 ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
 16:42:07  ✓ Confirm identity                                                                0 cr      1.2 s
           16:42:07  Matching the domain meridianwarehousing.example
           16:42:08  Company identify · 3 candidates                                         0 cr
           16:42:08  Identity confirmed · matched on domain and registration number
 16:42:09  ✓ Build the company profile                                                       2 cr      2.0 s
           16:42:11  Company enrich · 1 of 1 returned                                        2 cr
 16:42:11  ✓ Gather dated events                                                            12 cr     41.3 s
           16:42:12  Web search · 9 hits, 6 news                                             1 cr
           16:42:19  Read economictimes.indiatimes.com · Meridian Warehousing raises…        1 cr
           16:42:21  Extracted 3 dated facts · 1 discarded: no matching passage             $0.004
           16:42:22  Could not read linkedin.com · 403
           …
 16:44:40  ⌀ Check claim: debt                              Skipped · budget reached
```

- **Timeline** (default): steps as collapsible groups, each with its events in order, absolute times, per-event cost, per-step duration. Static, fully settled, printable. It is built from `GET /runs/{id}` + `GET /runs/{id}/activity`.
- **Sources / Crustdata / Cost** tabs are the same E and D components fed the whole event list at once, plus the existing cost readout.
- **Replay** plays the stored events through the live layout, so the user (or a judge) can watch the run again. Controls: play/pause, speed 1× / 8× / 30× (default 8×), a scrubber with a tick per step. Gaps longer than 2 s of real time are compressed to 600 ms at any speed. A banner stays on screen throughout: "Replay of the run from 22 Nov 2026, 16:42 IST · nothing is being fetched and no credits are spent". The orb is not shown in a replay (no work is happening); the step spinners are, since they depict the recorded state. Relative times read as they were ("read 2 s ago" relative to the replay clock).
- Filter: by step (click a step), by kind (calls / sources / findings / notices), and "only problems" (failed calls, unread pages, skipped steps).
- A run older than the activity feature has no events. Its log shows the steps as today and one line: "Detailed activity was not recorded for this run".

The log is also the audit answer to the PRD's "a record of every source used, so the case can be reproduced": the Sources tab of a run lists exactly what that run read, with times.

---

## 5. Implementation plan

Three chunks. B1 and F1 can start in parallel because F1 works against fixtures and the schema in §2; F2 needs both.

### B1. Backend: emit, persist, stream

Owner: backend agent. Touches only `apps/api`.

| File | Change |
| --- | --- |
| `apps/api/alembic/versions/0005_run_activities.py` (new) | `run_activities` table, unique (`run_id`, `seq`), index on (`run_id`, `seq`) |
| `apps/api/app/db/models.py` | `RunActivity` model |
| `apps/api/app/api/schemas/runs.py` | `ActivityOut`, `SourceRefOut`, `CallInfoOut`, typed item models per `subject`, `ActivityEvent`, `ActivityPage` |
| `apps/api/app/jobs/activity.py` (new) | `ActivityEmitter` (`status`, `call`, `source`, `model`, `finding`, `notice`), seq allocation, own-session commit, 1/s status throttle, 2,000 cap; **label templates**; URL and title sanitisers; `counts_for(endpoint, result)` helpers |
| `apps/api/app/jobs/engine.py` | `StepContext.activity` (the emitter); `set_detail` also emits `status` |
| `apps/api/app/jobs/events.py` | stream `activity` events with `id:`; `Last-Event-ID` / `after`; `: live` marker; 0.5 s poll; `run` event on cost change; `load_activity_page` |
| `apps/api/app/api/runs.py` | `GET /runs/{id}/activity`; SSE docs; fixture stream replays fixture activities |
| `apps/api/app/api/fixtures.py` | recorded activities for each fixture run (discover, investor, verify, recheck) |
| `apps/api/app/pipelines/discover/steps.py`, `investors/steps.py`, `verify/identity.py`, `verify/profile.py`, `verify/registry.py`, `verify/events.py`, `verify/comparables.py`, `verify/claims/steps.py`, `verify/claims/intake.py`, `verify/checks/steps.py`, `verify/checks/gather.py`, `evaluate/step.py`, `act/step.py` | emission call sites per §2.9; remove filename from detail and step label |
| `apps/api/openapi.json` | regenerated |
| `apps/api/tests/jobs/test_activity.py`, `tests/api/test_run_activity.py`, per-pipeline assertions | seq ordering under parallel steps; resume emits `from_cache`; SSE resume from `Last-Event-ID`; **canary test** for §2.10; counts keys per endpoint |

Order inside the chunk: table + emitter + stream + REST (with `set_detail` → `status` giving every pipeline a NOW line at once) → `call` and `source` at the Crustdata call sites → `finding` per pipeline (Discover, then Verify, then Investors, then recheck) → fixtures.

Done when: a live Discover run produces `status`, `call`, `source` and `finding` events in order over SSE; reloading mid-run returns the backlog then `: live`; the canary test passes.

### F1. Frontend: components and the activity store

Owner: frontend agent 1. Works in fixture mode. Owns new files only, plus the API client.

| File | Change |
| --- | --- |
| `apps/web/lib/api/client.ts` | `ActivityOut` types; `RunStreamEvent` gains `{ event: "activity" }` and `{ event: "live" }`; `subscribeRun` listens for `activity`, passes `after`, polling fallback calls `listRunActivity`; `listRunActivity(runId, after)` |
| `apps/web/lib/api/fixtures.ts` + `fixtures.json` | activity lists; `replayRun` plays them with compressed gaps |
| `apps/web/lib/run/activity-store.ts` (new) | reducer: events → `{ now, steps, tally, sources, findings by subject, cost }`; idempotent by `seq`; item upsert by id |
| `apps/web/lib/run/reveal-queue.ts` (new) | the pacing queue of §3.2, with pause, flush and reduced-motion mode |
| `apps/web/lib/run/use-run-activity.ts` (new) | hook: subscribe, store, queue, clock |
| `apps/web/components/run/run-view.tsx` (new) | layout A–E, `mode: "live" | "log" | "replay"`, the finish transition, `findings` slot |
| `apps/web/components/run/run-header.tsx`, `now-line.tsx`, `cost-meter.tsx` (new) | header band; orb state mapping |
| `apps/web/components/run/step-checklist.tsx`, `step-mark.tsx` (new) | checklist with spinner, check draw, grouping, filter-on-click |
| `apps/web/components/run/crustdata-tally.tsx` (new) | tally |
| `apps/web/components/run/source-ticker.tsx`, `favicon.tsx` (new) | ticker |
| `apps/web/app/api/favicon/route.ts` (new) | same-origin cached favicon proxy; domain validation, size cap, glyph fallback |
| `apps/web/components/run/run-log.tsx`, `replay-controls.tsx` (new) | timeline and replay |
| `apps/web/lib/sound.ts` (new) + settings toggle | `cuelume` levels of §3.5 |
| `apps/web/components/dealproof/run-progress.tsx` | reduced to a thin wrapper over `step-checklist` + `run-header` so existing imports keep working; `WorkingIndicator` moves to `run-header.tsx` and is re-exported |

Done when: a `/dev`-only gallery page (or Storybook-style route already used for components, if one exists) shows `RunView` replaying each fixture run, in live, reduced-motion, failed, budget-reached and log modes.

### F2. Frontend: per-pipeline integration

Owner: frontend agent 2. Starts when F1's `RunView` and store are merged. Owns the feature directories.

| File | Change |
| --- | --- |
| `apps/web/components/discover/run-panel.tsx`, `thesis-view.tsx`, `shortlist.tsx`, `shortlist-card.tsx` | `LiveRun` renders `RunView` with the Discover findings; `ShortlistCard` gains the provisional stages (`found` … `explained`) and a stable `layoutId`; the settled shortlist is the same list |
| `apps/web/components/discover/candidate-stream.tsx` (new) | the Candidates list, dropped / not-enriched groups |
| `apps/web/components/investors/search-view.tsx`, `shortlist.tsx`, `investor-entry.tsx`, `round-axis.tsx` | "Investors so far" grouping from `round` findings; dots enter; one reorder on rank |
| `apps/web/components/case/case-context.tsx` | holds the activity store for the case's run; `isClaimPending` replaced by `claimLiveState(claimId)` → `queued | checking | settled | not_checked` with its status line; debounced `reload()` on claim settle |
| `apps/web/components/case/claims-tab.tsx`, `components/dealproof/claim-ledger.tsx` | ledger rows take the live state; settle motion; identity band and assessment placeholder |
| `apps/web/components/case/case-shell.tsx`, `overview-tab.tsx` | `RunView` docked on the case; tab counts tween; new "Run log" tab |
| `apps/web/components/case/recheck-stream.tsx` (new) + `components/dealproof/version-diff.tsx` | before → after rows that settle into the assessment diff |
| `apps/web/app/(app)/app/cases/[id]/log/page.tsx`, `discover/[thesisId]/log/page.tsx`, `investors/[id]/log/page.tsx` (new) | run log routes |

Done when: each of the four run kinds, in fixture mode and against the real API, shows steps, NOW line, tally, sources and its findings live; finishing causes no remount of result rows; the run log replays it.

### Sequencing and risk

- B1's first slice (emitter + `set_detail` → `status` + stream) is small and gives a moving NOW line everywhere. If time runs out at the hackathon, the order of value is: NOW line → source ticker → claim rows settling → tally → Discover candidates → investors → replay.
- The largest risk is `finding` emission in Discover's score step and Verify's checks touching hot code. Emission must be fire-and-forget: a failed emit logs and never fails a step.
- The SSE poll at 0.5 s doubles `load_run_out` queries per viewer. Split the loop so the cheap activity query runs every 0.5 s and the full run/steps load stays at 1 s.

---

## 6. Open decisions

1. **Step spinners.** This design amends "nothing loops except the single run indicator" ([§3.7](#37-changes-to-the-design-direction)). Recommended: accept. Alternative: keep the static chevron and let the orb be the only motion, which is quieter and noticeably less alive.
2. **Favicons.** Recommended: the same-origin proxy. Alternative: no favicons, source-class glyphs only (no outbound requests at all; plainer ticker).
3. **Search queries in the log for case runs.** Left out for confidentiality. An analyst auditing a case may want them. Option: store them in the confidential payload store with the documents' expiry and show them only in the run log.
4. **"Live cues" sound level.** Recommended: build it, leave it off, turn it on for the demo if the room suits it.
5. **Replay default speed.** 8× is a guess. Pick after watching a real 3-minute Verify run replayed.
6. **Dropped companies during Discover.** Shown in a collapsed group with reasons. If that reads as noise in the demo, show the count only and keep the reasons for the run log.
