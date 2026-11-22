# B. App consistency, anti-gimmick audit and information architecture

Iteration B · 22 Nov 2026 · signed-in app only (`apps/web/app/(app)`, `app/login`, `components/{app-shell,dashboard,discover,investors,case,case-b,ui,dealproof}`)

This is a spec for builders. It does not change `docs/design/design-direction.md`; where the two disagree on something this document adds (page header, section heading size, navigation), this document is the newer decision and the direction file should be updated to match after the user agrees.

**How this was produced.** The code was read and searched; nothing was rendered, built or run. The `/design` gallery (`app/design/gallery.tsx`) was not audited line by line. Line numbers are from `main` at `9dc7c99` and will drift.

**Credit.** The `unslop` skill's audit list was used (unslop by Damir Sokolovsky, [@heydamir](https://x.com/heydamir), CC BY 4.0).

## 0. The short version

The app is already disciplined at the token level. A search of the signed-in app found one arbitrary Tailwind value (`max-w-[85vw]`), no raw colours outside the print stylesheet, one `font-semibold` (the disposition stamp, which the direction allows), no uppercase labels, no gradients, no glows, no emoji. Colour, radius and shadow are not the problem.

What makes it feel thin and gimmicky is structural:

1. **It has four destinations and one of them is a button.** A product an analyst lives in has a directory, a pipeline, an inbox, a feed. DealProof has the data for all of them and shows a single table.
2. **Every screen was built by a different hand.** There are nine page headers, six empty states, eight error states and two implementations of the case tabs. Each is tidy; together they read as a prototype.
3. **Hierarchy is flat.** Section headings are 20px under a 24px page title, 12px is the most used text size (232 uses, against 164 at 13px and 116 at 14px), and summary figures are sentences. Nothing on a screen is clearly the main object.
4. **A few things perform instead of inform.** A third-party animated orb, "Analyst working", a fade-and-rise on almost every list row and tab change, a serif slogan on the login page.
5. **The deployed app falls through to the framework's black 404.** One screenshot in the reference set is exactly that.

Dealroom's product tour shows the alternative: a persistent left nav of eight views, a compact page header with three or four figures at its right edge, and a page body made of titled panels that each hold one table or one list at 12 to 13px. Sections 2 and 5 take that information design and leave its visual style (blue, pills, uppercase eyebrows, a blended match score).

## 1. Ranked issues

Severity: **A** breaks the sense of a real product, **B** visible inconsistency, **C** polish.

| # | Sev | Where | What is wrong | Fix |
| --- | --- | --- | --- | --- |
| 1 | A | `components/app-shell/nav.ts:35-45`, `:59-77` | Four primary items; "Verify a company" is a dialog trigger sitting in a list of places; "Dashboard" in the sidebar opens a page titled "Cases" (`dashboard/dashboard.tsx:42`); "New screening" opens a page titled "Discover" (`discover/step-header.tsx:25`); the breadcrumb uses a third set of names. `docs/content/app-microcopy.md` §1 names the nav Cases, Discover, Investors. | Replace with the grouped nav in §5.1. Actions leave the nav list and go into one "New" menu. One name per destination, used by the nav, the breadcrumb, the `h1` and the document title. |
| 2 | A | no `app/not-found.tsx`, `app/error.tsx`, `app/(app)/app/not-found.tsx` | Unknown routes render the framework's default page: black, centred "404". It is the only dark, centred screen in the product. | Add the three files using `PageState` (§3). Inside the shell, a missing page keeps the sidebar and says where to go. |
| 3 | A | `dealproof/run-progress.tsx:4`, `:23` | `ThinkingOrb` from `thinking-orbs`, an animated orb, with the label "Analyst working". It is the one element in the app whose job is to look intelligent. | Remove the orb. The running step already shows a live sub-line and elapsed time. Use a static 16px `LoaderCircle`-free marker: a filled 6px accent dot before the running step, and the header reads `Verify running · {subject}`. Drop the `thinking-orbs` dependency once unused (ask before uninstalling). |
| 4 | A | `dashboard/dashboard.tsx:53-70` | The home page is one table plus a rail holding a form and two short lists. There is no summary of the book of work: how many cases sit at each disposition, what is waiting on the user, what changed. | Replace with the Overview in §5.3: stat tiles, an attention list, the pipeline summary, recent changes. |
| 5 | B | `discover/notice.tsx:31-54`, `case/parts.tsx:63-86`, `dashboard/cases-section.tsx:93-111` and `:157-172`, `investors/searches-list.tsx:56-68`, `dashboard/recent-lists.tsx:57`, `case-b/tabs.tsx:98` | Seven empty states, two of them both named `EmptyState`. Title is 20px in three and 14px in three; padding is `p-4 sm:p-6`, `px-5 py-8`, `p-5` or none; one is a bare `role="status"` line. | One `EmptyState` in `components/ui` (§3). Delete both local ones. |
| 6 | B | `discover/notice.tsx:4-28`, `case-b/parts.tsx:38-53`, `dashboard/cases-section.tsx:45-51`, `investors/searches-list.tsx:44-50`, `dashboard/recent-lists.tsx:48-55`, `case/case-shell.tsx:131-155`, `app-shell/app-shell.tsx:175`, `case/case-header.tsx:150` | Eight error presentations. `ErrorNotice` is a red-tinted box in Contradicted ink; the others are neutral. A network failure borrowing the Contradicted colour breaks the rule that red means one thing. `searches-list.tsx:44` has no `role="alert"`. Wording varies: "could not be loaded", "did not load", "Could not load {what}", "could not open". | One `ErrorState` (§3): neutral surface, `line-strong` border, `role="alert"`, title `{Thing} did not load`, the reason, one `Try again`. Red stays with Contradicted and with destructive confirmation. |
| 7 | B | `dashboard/dashboard.tsx:40-51`, `app/(app)/app/investors/page.tsx:11-22`, `investors/new/page.tsx:23-24`, `cases/new/page.tsx:8-10`, `policy/page.tsx:298-299`, `settings/settings.tsx:42`, `discover/step-header.tsx:22-29`, `investors/search-view.tsx:198`, `case/case-header.tsx:183-211` | Nine hand-built page headers. Alignment is `items-end` or `items-start`; the line under the title is mono 12px in one, a 14px sentence in four; the width cap is `max-w-2xl`, `max-w-3xl` or none; Settings uses `mb-6` instead of the page gap. Page wrappers use `gap-6 lg:gap-8`, `gap-8` and `gap-6`. `step-header.tsx:62` caps at `max-w-360`, which repeats the shell's cap at `app-shell.tsx:47`. | One `PageHeader` and one `Page` wrapper (§2.1, §3). |
| 8 | B | `text-xl`: `discover/criteria-editor.tsx:372`, `discover/shortlist.tsx:168`, `investors/shortlist.tsx:52`, `investors/profile-form.tsx:155`, `investors/search-view.tsx:46`, `policy/page.tsx:53`, `case/parts.tsx:24`. `text-sm`: `dashboard/dashboard.tsx:60`, `dashboard/recent-lists.tsx:41`, `settings/settings.tsx:21`, `case-b/cost-panel.tsx:45`, `dealproof/judgment-panel.tsx:130` and `:178`, `investors/principles.tsx:17`. `text-xs` muted: `discover/new-thesis.tsx:40` | The same level of heading is 20px, 14px or 12px depending on the folder. At 20px a section head is nearly the page title and the page reads as a stack of equal blocks. | Section heading is 14px medium everywhere (§2.2). 20px is retired from the app except the memo. |
| 9 | B | `components/case/adapt.ts` and `components/case-b/adapt.ts`; also `discover/adapt.ts`, `investors/adapt.ts`, `investors/format.ts` | `toEvidence` and `factEvidence` exist three times (`case/adapt.ts:117,134`, `case-b/adapt.ts:80,97`, `discover/adapt.ts:75,101`); `toAssessment` and `toDiff` twice (`case/adapt.ts:257,329`, `case-b/adapt.ts:119,245`); `toSource` twice; `toRun` three times; `isTerminal` twice; `formatAmountUsd` twice plus `formatAmount` at `case/memo.tsx:222` and `formatUsd` in `lib/format.ts:88`; `roundLabel` twice; a stage re-spacer three times (`dashboard/recent-lists.tsx:16`, `discover/adapt.ts:244`, `investors/format.ts:73`). Two screens can show the same fact formatted differently. | One `lib/adapt/` and one `lib/format.ts` (§3.3). `case-b` is merged into `case`. |
| 10 | B | `ui/tabs.tsx:57-91` and `case/case-shell.tsx:60-84` | The case tab row re-implements the tab trigger: same underline, same count, different heights (`h-9` against `h-11 md:h-9`), separate `layoutId`. | Add `TabsNav` (link-based) to `ui/tabs.tsx` sharing one trigger class; `case-shell` uses it. |
| 11 | B | `case/case-shell.tsx:182-185`, `dealproof/claim-ledger.tsx:207`, `investors/investor-entry.tsx:134`, `case/comparables-tab.tsx:88`, `case/events-tab.tsx:64`, `dashboard/dashboard.tsx:39`, `settings/settings.tsx:41`, `discover/step-header.tsx:62` | Fade-and-rise on page load for three screens and not the others, on every row of four lists, and a fade on every tab change (`key={active}`). The direction allows one page entrance and the first six ledger rows. Motion on everything is the most recognisable generated-interface habit. | Remove `animate-row-in` from page wrappers and list rows. Keep it in one place: ledger rows while a run is filling them in. Remove the `key={active}` fade. |
| 12 | B | `ui/table.tsx` users (8 files) against `case/comparables-tab.tsx:88`, `investors/investor-entry.tsx:134`, `case/events-tab.tsx:64`, `dashboard/recent-lists.tsx:65`, `dashboard/cases-section.tsx:77` | Tabular data is a `Table` in some places and a hand-made grid in others. Horizontal cell padding is 12 (`ui/table.tsx:57,74`), 16 (`comparables-tab`, `investor-entry`) or 20 (`cases-section.tsx:78`). `cases-section.tsx:60-73` rebuilds the table frame for its skeleton. | One `DataTable` pattern with three densities and a matching `TableSkeleton` (§2.3). Comparables becomes a real table. |
| 13 | B | at least 15 hand-typed `rounded-lg border border-line bg-surface` containers; padding `p-4` ×6, `p-5` ×7, `p-6` ×2, `p-4 sm:p-6` ×2 | `Card` and `Panel` exist in `ui/card.tsx` but most surfaces are typed out, so padding drifts between 16, 20 and 24 for the same kind of box. | `Panel` becomes the only container (§2.2), padding 16, header 40px. |
| 14 | B | `dashboard/dashboard.tsx:46` and `:59-67`, `nav.ts:38`, `case/case-header.tsx:204` | "New case", "Verify a company", "Run verification", "New screening", "New thesis" and "Discover" name two actions. The dashboard offers the verify form three times on one screen (header button, sidebar item, rail card). | Vocabulary in §2.9. One "New" menu in the sidebar; the rail card is removed. |
| 15 | B | `app/login/page.tsx:21-22`, `:41-57` | The form is a `max-w-sm` column centred in the viewport, beside a `paper-warm` panel with a 44px serif slogan and three selling points. It is the marketing page's voice at the door of the tool. | Keep the two columns. Left-align the form to the same 32px page gutter and top offset as the app. Replace the slogan panel with a plain facts panel on `paper`: what a session records, that there is no sign-up, the test-mode state if sending is off. No serif inside the app door. |
| 16 | C | `Icon` at 14: `investors/investor-entry.tsx:91`, `investors/round-source.tsx:133`, `case/identity-tab.tsx:275`, `case/events-tab.tsx:44`, `case/intake.tsx:55`, `case-b/document-download.tsx:37`, `dealproof/approval-block.tsx:92`, `dealproof/source-line.tsx:120`; `SourceClassGlyph` at 16 in `source-line.tsx:66` and `round-source.tsx:90`; `glyphs.tsx:92` stroke 1.2 | Two icon sizes with no rule for which. The direction (§6.5) puts the class glyph at 14 inside a 22px chip; the code uses 16. One glyph has a 1.2 stroke. `CircleQuestionMark` (6 imports) and `CircleHelp` (1) are the same icon under two names. | Sizes in §2.7: 16 default, 14 only inside chips, tags and table cells. Fix the stroke. One import name. |
| 17 | C | `discover/thesis-list.tsx:66-68`, `investors/searches-list.tsx:34-37`, `investors/search-view.tsx:56-64`, `discover/thesis-view.tsx:39-43`, `case/case-shell.tsx:122-127`, `dashboard/cases-section.tsx:60-73`, `app-shell/app-shell.tsx:163-166` | Seven skeleton shapes (16, 10, 32, 28-unit blocks; `rounded-md`, `rounded-lg` or none). Only `thesis-view.tsx:43` shows "Still working" after two seconds, which the direction requires everywhere. | `LoadingState` with three variants that mirror the real layout (§3). The two-second line lives inside it. |
| 18 | C | `case/case-header.tsx:198,206`, `case/case-shell.tsx:65` | Touch height is applied by hand as `h-11 md:h-9`. | Move into `Button` and the tab trigger as the default responsive size. |
| 19 | C | `dashboard/cases-section.tsx:138,141` | Toolbar controls override the input to `h-8 bg-surface`; inputs elsewhere are `h-9 bg-surface-raised`. | `Toolbar` (§3) sets 32px controls on `surface`. Add `size="sm"` to `Input` and `SelectTrigger`. |
| 20 | C | `case/case-header.tsx:243`, `:70`, `investors/searches-list.tsx:94`, `dashboard/recent-lists.tsx:66`, `case-b/parts.tsx:56-76`, `ui/button.tsx:21` | Five spellings of an in-text link: underline offset 2 or 4, decoration `line-strong` or accent, underline always or on hover. | `TextLink` moves to `components/ui`; accent ink, underline, offset 2. Table row titles use `RowLink` (ink, medium, no underline, accent on hover). |
| 21 | C | `case/memo-print.css:17,22,27`, `case/memo.tsx:1127`, `app-shell/app-shell.tsx:223` | `#454a54` typed four times (it is `ink-secondary`); one arbitrary width. | `var(--color-ink-secondary)`; `max-w-[85vw]` becomes a token `--layout-sheet-max`. |
| 22 | C | `discover/thesis-form.tsx:59`, `investors/profile-form.tsx:152`, `settings/settings.tsx:82`, `case/memo.tsx:1134` | `shadow-xs` marks "the main object" on forms and one settings block; the case header panel, which is the main object of its page, has none. | Shadow level 1 is for buttons and the memo sheet only. Forms and panels are flat. |
| 23 | C | `dashboard/cases-section.tsx:135` | Placeholder "Search by company"; microcopy §2 says "Search by company or city". Search matches the name only (`:122`). | Keep the code's wording, since it is true, and correct the microcopy file. |

## 2. App-wide spec

Everything below uses existing tokens from `apps/web/app/globals.css`. No new colour, radius or shadow is introduced.

### 2.1 Page frame and page header

```
┌ sidebar 248 ┬ top bar 56: breadcrumb                         Test mode  ⌘K  user ┐
│             ├──────────────────────────────────────────────────────────────────────┤
│             │ 32                                                                    │
│             │ Title (24/32, 500)                 figure  figure  figure   [Action]  │  page header
│             │ meta line (13/20, ink-secondary)   label   label   label              │
│             │ 24                                                                    │
│             │ [Toolbar: search · filters · view switch                  count]      │  optional
│             │ 16                                                                    │
│             │ panels on a 12-column grid, 16 gap                                    │
└─────────────┴──────────────────────────────────────────────────────────────────────┘
```

- `Page` is the only wrapper: `flex flex-col gap-6`, no max width (the shell already caps at 1440), no entrance animation.
- `PageHeader` has four slots and nothing else: `title`, `meta`, `figures`, `actions`.
  - `title`: `h1`, `text-2xl font-medium`. It names the place ("Companies") or the object ("Meridian Warehousing Pvt Ltd"). Never a greeting, never a verb phrase.
  - `meta`: one line, `text-dense text-ink-secondary`. Counts and dates inside it are mono. It is a fact line, not a description of the feature. A page that needs an explanation puts it in an `EmptyState` or a panel `lead`, not here.
  - `figures`: up to four `StatFigure`s (§2.5), right-aligned, bottom-aligned to the meta line. This is where Dealroom puts "34.5K companies · 520 unicorns".
  - `actions`: at most one primary and one secondary button, 36px, right of the figures. Further actions go in a `⋯` menu.
  - Layout: `flex flex-wrap items-end justify-between gap-x-8 gap-y-4`. Below `lg`, figures wrap under the title and actions stay on the title row.
- A hairline does not sit under the header. Space separates it from the body.
- The breadcrumb, the `h1`, the nav label and `<title>` use the same word.

### 2.2 Section and panel anatomy

One container, `Panel`, replaces every hand-typed card.

```
┌──────────────────────────────────────────────────────────────┐
│ Title 14/20 500   meta mono 12 muted          [action 28px] │  header: 40px, px 16, border-b line
├──────────────────────────────────────────────────────────────┤
│ body: px 16 py 16, or flush when it holds a table or a list  │
├──────────────────────────────────────────────────────────────┤
│ footer: 36px, px 16, text-xs ink-muted · "View all 42"       │  optional
└──────────────────────────────────────────────────────────────┘
```

- Radius 12 (`rounded-lg`), `border-line`, `bg-surface`, no shadow.
- The header title is the section heading: `h2`, `text-sm font-medium text-ink`. `meta` sits on its baseline in `font-mono text-xs text-ink-muted` (a count, a version, an as-of date). The right side holds one quiet 28px action or a segmented switch.
- `flush` removes body padding so a table or list runs edge to edge; its rows carry the 16px inset.
- A `lead` line may follow the header inside the body: `text-dense text-ink-secondary`, max 680px.
- An unboxed `Section` (title and content directly on `paper`) is allowed only inside the memo and on the Policy page, where the content is prose.
- Panels never nest. A group inside a panel is a sub-heading (`h3`, `text-xs font-medium text-ink-secondary`) over a hairline.
- Heading levels in the app: `h1` 24, `h2` 14 medium, `h3` 12 medium secondary. `text-xl` appears only in dialogs and the memo.

### 2.3 Table pattern

One component set (`ui/table.tsx`), three densities, chosen by content and not by taste.

| Density | Row | Use |
| --- | --- | --- |
| `compact` | 32px, one line | Cost steps, sources, policy tables, compare matrix |
| `default` | 40px, one line | Directories and lists: companies, investor searches, approvals |
| `two-line` | 52px, name over meta | Rows whose identity needs a second line: cases with their status cue |

Rules

- Header band: 32px, `bg-surface-sunken`, `text-xs font-medium text-ink-secondary`, sentence case, sticky under the top bar when the table is the page's main object.
- Cells: `text-dense` (13px), horizontal padding 12, first and last cell 16 so text aligns with the panel header.
- First column is the entity: name in `text-ink font-medium`, the whole row is the click target (`RowLink` stretches over the row), second line in `text-xs text-ink-muted`.
- Numbers, dates and credits: right-aligned, mono, tabular. A dash `–` for no value; never "N/A", never blank.
- A figure with a change stacks the change under it in `text-2xs`, and the change always says what it compares to.
- Status cells use `StatusMark` or `DispositionStamp size="sm"`; never a `Badge`.
- Row states: hover `surface-raised`; keyboard focus `focus-inset`; selected `accent-tint` with `selected-bar`. Sorted column header is `text-ink` with a 14px arrow.
- Sorting is offered only where the API order is not already meaningful. No column picker in v1.
- Below `md`, a table with more than four columns becomes a stacked list of the same rows (entity, then two key cells); it does not scroll sideways except the compare matrix.
- A table always has a count somewhere above it: in the panel `meta` or the toolbar's right edge.

### 2.4 Card density

Cards are for objects that are compared one at a time and carry more than a row can (a shortlist company, an investor entry). Everything else is a table row.

- Padding 16. Internal gaps 12 between blocks, 4 between a label and its value.
- First line: name `text-sm font-medium` and the one key readout on the right (fit readout, or comparable-round count).
- Second line: one meta line `text-xs text-ink-muted`.
- Body: a two-column definition grid, label `text-xs text-ink-muted` 96px wide, value `text-dense`. Every value ends in its source line.
- Cards in a list are separated by 8px, not by nested borders, and all share one width. No card grid of equal tiles on any screen.

### 2.5 Stat figures and stat tiles

Two forms, both numbers only: no icon, no sparkline, no coloured delta chip.

- `StatFigure` (in a page header): value `text-xl font-medium` mono tabular, label under it `text-xs text-ink-muted`. Right-aligned, 32px between figures.
- `StatTile` (a row of tiles in the body, Overview only): 16 padding, label on top `text-xs text-ink-secondary`, value `text-3xl font-medium` mono tabular, a `note` line under it `text-xs text-ink-muted` that states the denominator or the comparison ("of 14 cases", "2 since Monday"). Tiles sit in one `Panel` divided by vertical hairlines, not as separate cards, so the row reads as one instrument.
- A tile whose value is a count of items links to the filtered list. The whole tile is the link.
- Estimates keep the tilde and the `Estimate` tag inside a tile.
- A figure that mixes settled and unsettled work says so in the note: "9 settled · 3 not checked". Not checked is never folded into a total.
- At most one figure per screen is in accent ink.

### 2.6 Empty, loading and error

One trio, one anatomy, three sizes (`page`, `panel`, `inline`).

| | Empty | Loading | Error |
| --- | --- | --- | --- |
| Role | none | `role="status"`, one label | `role="alert"` |
| Title | `text-sm font-medium`: what is absent ("No cases yet") | none | `{Thing} did not load` |
| Body | one or two sentences, `text-dense text-ink-secondary`, max 680px: what the thing is and how it comes to exist | skeleton that mirrors the real layout | the reason from the API, and that nothing was changed |
| Actions | at most two, 32px, primary first | none | `Try again`, 32px secondary |
| After 2s | – | adds `Still working` in `text-dense text-ink-secondary` | – |

- `page` size: left-aligned at the top of the content area under the page header, 32px above, no box. Never centred in the viewport.
- `panel` size: inside the panel body, 16 padding, left-aligned.
- `inline` size: one line in `text-dense text-ink-secondary` with an optional text link, for a list inside a rail.
- Error is neutral: `surface`, `line-strong` border. The HTTP status may follow in mono `text-xs`. A 401 says "Your session has ended" and offers `Log in`.
- Loading has three skeleton shapes and no others: `rows` (n table rows at the table's density, including the header band), `lines` (text), `tiles` (the stat row). Blocks that stand in for whole panels are not used; render the panel chrome and skeleton its body.
- "Waiting on identity" is not an empty state. It keeps its own component, `BlockedByIdentity`, in Cannot verify slate.
- Not checked and suppressed sends keep `HatchedBlock`. A hatch never appears on an empty or loading state.

### 2.7 Icons

- One set: `lucide-react` through `Icon`, stroke 1.5, plus the local status and source-class glyphs.
- Two sizes. **16** everywhere by default: nav, buttons, headings, row actions. **14** only inside a chip, a tag, a keycap or a 32px table cell. Nothing at 12, 18, 20 or 24.
- Icons take the ink of the text beside them. Only status glyphs and the disposition stamp carry their own colour.
- Icons appear on: nav items, buttons whose action is an object verb (print, download, upload, re-run), external links, status and source-class marks. They do not appear in panel titles, stat tiles, table headers, empty states or page titles.
- Nav icons, one per destination and not reused elsewhere: Overview `LayoutDashboard`, Pipeline `Columns3`, Approvals `Inbox`, Companies `Building2`, Compare `GitCompareArrows`, Signals `Activity`, Investors `Landmark`, Screenings `ListFilter`, Scoring policy `Scale`, Settings `Settings`. Check each name against the installed lucide version before use; some were renamed between releases.
- `CircleQuestionMark` is the one name for the Cannot verify mark; remove the `CircleHelp` import.

### 2.8 Spacing rhythm

| Step | Use |
| --- | --- |
| 4 | Label to value; icon to adjacent mono figure |
| 8 | Icon to label; between buttons; between cards in a list |
| 12 | Table cell x-padding; blocks inside a card |
| 16 | Panel padding; grid gutter between panels; toolbar to table |
| 24 | Page header to body (`Page` gap); between panel groups |
| 32 | Page padding at `lg`; top of content |
| 48 | Only between the memo's major sections |

- Panel grid: 12 columns, 16 gutter. Common splits: 8 + 4 (main and rail), 6 + 6, 4 + 4 + 4, 12.
- A rail is 320px (`--layout-rail`) and holds lists, never forms.
- Inside a group the gap is always smaller than the gap around the group.
- Heights: 28 panel-header action, 32 toolbar control and compact row, 36 page action and form control, 40 default row and panel header, 44 touch (below `md`, applied by the component).

### 2.9 Vocabulary

| Thing | The one name | Not |
| --- | --- | --- |
| A company under review | Case | Screening, deal |
| A thesis and its shortlist | Screening | Discovery run, thesis (as a noun for the page) |
| Starting from a thesis | New screening | New thesis, Discover |
| Starting from a known company | Verify a company | New case |
| Running checks on a case | Run verification / Re-run verification | Verify (alone) |
| The home page | Overview | Dashboard, Cases |
| A failed read | `{Thing} did not load` + `Try again` | could not be loaded, Retry, Reload |
| A live run | `{Workflow} running` | Analyst working |

Middle dots join items only inside a mono meta line and inside the fixed readouts the direction defines (`Fit 82 · 70% of criteria assessable`). Sentences use commas.

### 2.10 Information hierarchy of a dense screen

How Dealroom packs data in calmly, restated as rules for DealProof.

1. **One reading order: who, state, evidence, detail.** The page header answers what this is and its current state in figures. The first row of panels holds the judgment. Tables of supporting records come below. Nothing important is below a decoration.
2. **Three levels of text and no more on one screen.** Level 1 is the page title and at most one figure. Level 2 is entity names and panel titles, 14px medium ink. Level 3 is everything else at 13px, with labels and meta at 12px in muted ink. Size and ink role make the levels; weight stays at 400 and 500.
3. **13px is the content size. 12px is for labels.** A value a reader came for is never set at 12px. Today 12px is the most used size in the app; after this pass it should be third.
4. **Labels are quiet and values are loud.** A label is 12px muted, above or left of its value. Labels never carry colour, icons or weight.
5. **Many small panels, each with one job.** A panel holds one table, one list or one readout. Its title says which. Density comes from placing six such panels on a 12-column grid, not from shrinking type or packing one panel.
6. **Unequal widths.** The main panel takes 8 columns and its neighbours 4. Three equal cards in a row are used only for the stat row, where equality is the meaning.
7. **Numbers line up.** Every numeric column is right-aligned, mono and tabular, so a column can be scanned vertically.
8. **Colour is spent on state only.** Chrome is paper, ink and hairlines. The only hues on a screen are status marks, disposition stamps and one accent for selection and links.
9. **Every panel shows its count and its date.** "Claims 12", "as of 22 Nov 2026". A reader should never wonder how much there is or how old it is.
10. **Nothing moves unless work is happening.** The only live element on any screen is a running step.

## 3. Shared components to extract or unify

New or changed files live in `components/ui` unless stated. Names and props are fixed so the three builders can code against them before they exist.

### 3.1 Layout

```ts
// ui/page.tsx
Page({ children, className? })
PageHeader({
  title: string,
  meta?: React.ReactNode,          // one fact line
  figures?: StatFigureProps[],     // max 4
  actions?: React.ReactNode,       // max 1 primary + 1 secondary
  back?: { label: string; href: string },   // detail pages only
})
StatFigure({ value: React.ReactNode, label: string, href?: string, estimate?: boolean })

// ui/card.tsx (Panel replaces Card for app surfaces; Card stays for the marketing page)
Panel({ children, className?, id?, "aria-labelledby"? })
PanelHeader({ title: string, meta?: React.ReactNode, action?: React.ReactNode, id?: string })
PanelBody({ flush?: boolean, lead?: React.ReactNode, children })
PanelFooter({ children })
PanelGrid({ children })                         // 12 columns, 16 gap
PanelGridItem({ span: 4 | 6 | 8 | 12, children })   // collapses to 12 below lg

// ui/stat.tsx
StatRow({ children })                            // one Panel, hairline-divided
StatTile({ label: string, value: React.ReactNode, note?: React.ReactNode, href?: string, estimate?: boolean })

// ui/toolbar.tsx
Toolbar({ children, count?: React.ReactNode })   // 32px controls on surface, count right-aligned mono
```

### 3.2 States

```ts
// ui/states.tsx
type StateSize = "page" | "panel" | "inline";
EmptyState({ title: string, children: React.ReactNode, actions?: React.ReactNode, size?: StateSize })
ErrorState({ what: string, reason?: string, status?: number | null, onRetry?: () => void, size?: StateSize })
LoadingState({ label: string, shape: "rows" | "lines" | "tiles", count?: number,
               density?: "compact" | "default" | "two-line", size?: StateSize })
// Convenience for the common case of a Load<T>
Loadable<T>({ state: Load<T>, what: string, loading: LoadingStateProps, onRetry,
              empty: React.ReactNode, isEmpty?: (data: T) => boolean, children: (data: T) => React.ReactNode })
```

`Load<T>` moves from `components/dashboard/use-load.ts` and `components/investors/use-load.ts` into `lib/use-load.ts`; both existing hooks are replaced by it.

Deleted after migration: `discover/notice.tsx` (`EmptyState`, `ErrorNotice`), `EmptyState` in `case/parts.tsx`, `LoadError` in `case-b/parts.tsx`, `CasesSkeleton`, `LoadingThesis`, `LoadingSearch`, `CaseLoading`.

### 3.3 Tables, tabs, links

```ts
// ui/table.tsx (extend, do not replace)
Table({ density?: "compact" | "default" | "two-line", flush?: boolean })  // flush: no own border, for use in a Panel
TableHead({ numeric?, sort?: "asc" | "desc" | null, onSort?: () => void })
TableCell({ numeric?, muted? })
EntityCell({ name: string, href?: string, meta?: React.ReactNode })       // first column, stretches the row link
TableSkeleton({ columns: number, rows?: number, density? })

// ui/tabs.tsx
TabsNav({ items: { label: string; href: string; count?: number; waiting?: boolean }[], current: string, label: string })

// ui/link.tsx
TextLink({ href, children, external? })   // accent, underlined, offset 2; external adds a 14px ExternalLink
RowLink({ href, children })               // ink medium, no underline, accent on hover

// ui/input.tsx, ui/select.tsx
Input({ size?: "sm" | "md" }), SelectTrigger({ size?: "sm" | "md" })

// ui/definition.tsx
DefinitionList({ items: { label: string; value: React.ReactNode }[], columns?: 1 | 2, labelWidth?: number })
```

### 3.4 Adapters and formatters

```
lib/format.ts            add: formatAmountUsd, formatModelUsd, roundLabel, stageLabel, formatBytes
lib/adapt/evidence.ts    toSource, toEvidence, factEvidence, factEstimate, sourceEvidence   (one copy)
lib/adapt/run.ts         isTerminal, isRunActive, toRun, mergeRunEvent, runDuration
lib/adapt/assessment.ts  toFit, toAssessment, toDiff, toVersionMeta, statusCounts
lib/adapt/case.ts        toClaim, toIdentity, toCaseCost, eventNature, identityResolved, usesBySource
lib/adapt/labels.ts      SOURCE_CLASS_LABEL, CATEGORY_LABEL, COMPANY_TYPE_LABEL, DISPOSITION_LABEL, STATUS_LABEL
```

Before merging two functions of the same name, diff them: `case/adapt.ts` and `case-b/adapt.ts` versions of `toAssessment` and `toDiff` may differ in what they accept. The merged version takes the wider input; if behaviour differs, keep the `case/` behaviour and note the difference in the commit message. `components/case-b/*` then moves into `components/case/` and the `case-b` folder is removed.

### 3.5 Domain components that change

- `RunProgress`: remove `ThinkingOrb`; header reads `{workflow} running · {subject}`.
- `DispositionStamp`: add `size="sm"` (24px, for table cells) if absent.
- `StatusCounts` (in `dashboard/case-cells.tsx`) moves to `dealproof/` as `StatusDistribution` with `variant: "counts" | "bar"`, since four screens need it.
- `BlockedByIdentity` and `TabHeading` stay in `case/parts.tsx`; `TabHeading` becomes a thin wrapper over `PanelHeader` sizing (14px), not a 20px heading.

## 4. Information architecture

The data rule for every screen below: **show only records DealProof already holds.** Each screen lists its source. Where a screen needs data from more than one case and no aggregate endpoint exists, it is built from `listCases()` plus `getCase()` for the cases shown, capped, and the panel says so in its meta ("from the 20 most recently updated cases"). No screen invents a figure, a trend or a company. Charts appear only where a dated series exists (`headcount_series`).

### 4.1 Sidebar

```
DealProof
[ + New                 ▾ ]     New screening · Verify a company · Find investors

Workspace
  Overview
  Pipeline
  Approvals              2      mono count: requests awaiting approval

Research
  Companies
  Screenings
  Compare
  Signals
  Investors

Recent                          last 5 cases, as now
  Meridian Warehousing
  …

──────────
  Scoring policy
  Settings
```

- Width 248. Rows 32px, 2px apart. Group label `text-xs text-ink-muted`, 24 above and 8 below. Icons in one 16px column.
- "New" is a 32px secondary button with a menu, the only action in the sidebar. `NavAction` is removed from `nav.ts`; the nav list contains places only.
- A count sits right-aligned in mono `text-2xs text-ink-muted`; it turns `text-accent` only for Approvals when it is above zero. No dot, no pill.
- Active item: `accent-tint` fill and accent text, as now.
- Screenings is added to the requested nine because theses and shortlists need a home that is not a button; it is the existing `/app/discover` list.
- Collapsed rail (`md` to `lg`): icons only, group labels become 8px gaps with a hairline.

Routes

| Nav | Route | Status |
| --- | --- | --- |
| Overview | `/app` | replaces the dashboard |
| Pipeline | `/app/pipeline` | new |
| Approvals | `/app/approvals` | new |
| Companies | `/app/companies` | new; `/app/cases/[id]` stays the detail page |
| Screenings | `/app/discover` | exists |
| Compare | `/app/compare?cases=a,b,c` | new |
| Signals | `/app/signals` | new |
| Investors | `/app/investors` | exists |
| Scoring policy | `/app/policy` | exists |
| Settings | `/app/settings` | exists |

### 4.2 Overview (`/app`)

Purpose: the state of the book of work in one screen, and what needs the user.

Data: `listCases()` (status, identity_state, disposition, fit, assessable_pct, claim_count, cost, latest_run_state, updated_at), `listTheses()`, `listInvestorSearches()`, and per-case detail for the cases shown in "Needs you" and "Recent changes".

```
Overview                                                      [ + New ▾ ]
14 cases · 3 screenings · last updated 22 Nov 2026, 16:42 IST

┌ Cases 14 ─────┬ Needs you 4 ──┬ Prioritise 3 ─┬ Not checked 7 ──┬ Spent ──────────┐
│ 14            │ 4             │ 3             │ 7               │ 412 cr          │   StatRow
│ 2 running     │ 2 approvals   │ of 11 assessed│ across 3 cases  │ $2.18 model     │
└───────────────┴───────────────┴───────────────┴─────────────────┴─────────────────┘

┌ Needs you 4 ──────────────────────────────── span 8 ┐ ┌ By disposition ── span 4 ┐
│ Company          What is waiting            Since   │ │ Prioritise           3   │
│ Meridian Wareh…  Request awaiting approval  21 Nov  │ │ Investigate further  5   │
│ Cold Chain Logix Identity unresolved · 2    20 Nov  │ │ Deprioritise         2   │
│ Northline Frei…  Verification failed        20 Nov  │ │ Cannot assess        1   │
│ Fleetwise        3 checks not run           19 Nov  │ │ No disposition yet   3   │
└─────────────────────────────────────────────────────┘ └──────────────────────────┘

┌ Recently updated cases 8 ─────────────────── span 8 ┐ ┌ Screenings 3 ──── span 4 ┐
│ Company  Disposition  Fit · assessable  Claims  Upd │ │ thesis text, 2 lines     │
│ two-line rows, same cells as Companies              │ │ Ready · 14 shortlisted   │
│ footer: View all 14 companies                       │ ├ Investor searches 2 ─────┤
└─────────────────────────────────────────────────────┘ │ sector · stage · n       │
                                                        └──────────────────────────┘
```

- The stat row has five tiles, each a link to its filtered list. "Needs you" counts cases where `status` is `awaiting_identity` or `failed`, where a request message is `draft`, or where any claim is Not checked.
- "By disposition" is a ranked list with a thin neutral bar per row (one accent-free series), not a chart. The "No disposition yet" row is set apart by a hairline.
- "Spent" shows credits and model usage as two lines and never adds them.
- No greeting, no illustration, no activity graph. There is no time series of cases to plot, so none is drawn.
- Empty (no cases): the stat row is omitted and one `EmptyState size="page"` offers New screening and Verify a company.

### 4.3 Pipeline (`/app/pipeline`)

Purpose: every case by where it stands, so an analyst can see what is stuck.

Data: `listCases()`; the request state needs `message.status` from `getCase()` for assessed cases.

Columns are derived states, not stages a user drags between. DealProof decides the state from the record; the board does not allow drag and drop, because a person cannot move a case to "Assessed".

| Column | Rule |
| --- | --- |
| Identity | `identity_state` is `unresolved` or `ambiguous` |
| Verifying | `status` is `verifying` |
| Failed | `status` is `failed` |
| Assessed | `status` is `assessed`, no request drafted |
| Request drafted | message `draft` or `approved` |
| Request sent | message `sent` or `suppressed_test_mode` (the card says which) |

```
Pipeline                                     14 cases   [Board | Table]
┌ Identity 2 ──┬ Verifying 1 ─┬ Failed 1 ────┬ Assessed 6 ──┬ Request drafted 2 ┬ Request sent 2 ┐
│ ┌──────────┐ │              │              │              │                   │                │
│ │ Name     │ │  cards, 8 apart, column 240 wide, board scrolls sideways below xl               │
│ │ stamp sm │ │
│ │ 82 · 70% │ │
│ │ ●3 ◐1 ◌2 │ │
│ │ 21 Nov   │ │
│ └──────────┘ │
```

- Column header: 32px, title `text-sm font-medium`, mono count, hairline under. Columns sit on `paper`; cards are `surface` with a hairline, radius 8, padding 12.
- Card: name (14 medium, one line), disposition stamp `sm` or the identity cue, compact fit readout `82 · 70%`, status counts, updated date in mono `text-2xs`. Five lines at most. The whole card links to the case.
- A card with Not checked claims shows the hatched count; a suppressed send shows "Suppressed (test mode)" and never "Sent".
- The Table view is the same data as one sortable table grouped by column, for readers who prefer rows. The choice is remembered per user in `localStorage`.
- Empty column: the column stays, with "None" in muted 12px. Columns are not hidden, so the board's shape is stable.

### 4.4 Companies (`/app/companies`)

Purpose: the directory of every company DealProof holds a record for.

Data: `listCases()` for companies with a case. Shortlisted companies without a case come from each thesis's shortlist (`getThesis(id)` → `ShortlistItemOut`: name, domain, fit, assessable_pct, `card.business`, `card.location`, `card.headcount`, `card.total_funding_usd`, `case_id`).

```
Companies                                    26 companies · 14 with a case      [ Verify a company ]
[Search by company]  [Disposition ▾] [Identity ▾] [Source: All | Cases | Shortlists ▾]        26

Company                 Disposition            Fit · assessable   Claims        Size        Updated     Cost
Meridian Warehousing    [⌕ Investigate further] 82 · 70% ▮▮▮▯▮╱╱  ●3 ◐1 ?2 ◌0   ~180 Est.   22 Nov 2026  86 cr
meridian.example · Identity confirmed
Cold Chain Logix        [? Cannot assess]       –                  –             –           21 Nov 2026  12 cr
Identity unresolved · 2 candidates
Fleetwise               No case                 76 · 60% ▮▮▮▯╱╱    –             ~90 Est.    20 Nov 2026  –
Shortlisted in "Regional 3PL operators"                                                       [ Open case ]
```

- `two-line` density. Column order is fixed: Company, Disposition, Fit · assessable, Claims, Size, Updated, Cost.
- Size is `card.headcount` or the case profile's headcount with the tilde and `Estimate` tag; a dash when absent. No revenue column exists because DealProof holds no revenue.
- A shortlisted company with no case shows "No case" in muted ink in the Disposition cell and an `Open case` row action.
- Row selection (checkbox in the first cell, shown on hover and focus) enables one toolbar action: `Compare (n)`, for two to four rows with a case.
- Filters live in the URL so a filtered view can be shared and linked from Overview tiles.
- This table replaces `dashboard/cases-section.tsx`'s table; its cells (`dashboard/case-cells.tsx`) are reused.

### 4.5 Screenings (`/app/discover`)

Existing screens, restyled only: `PageHeader` with `title="Screenings"`, a `default` table of theses (Thesis, Status, Criteria, Shortlisted, Started), and the three-step flow unchanged inside `/app/discover/[thesisId]`. The step header keeps its numbers because the steps are a real sequence.

### 4.6 Compare (`/app/compare`)

Purpose: two to four cases side by side on the things that decide a screening.

Data: `getCase()` for each selected case. Every row is a field already on `CaseDetail`.

```
Compare                                  3 cases                    [ Add a case ▾ ]  [ Print ]

                         Meridian Warehousing   Cold Chain Logix     Northline Freight
Disposition              [⌕ Investigate further][? Cannot assess]    [↗ Prioritise]
Identity                 Confirmed · 2 keys     Unresolved · 2       Confirmed · 3 keys
Fit · assessable         82 · 70% ▮▮▮▯▮╱╱       –                    74 · 100% ▮▮▮▮▮▮
─ Criteria ──────────────────────────────────────────────────────────────────────────
Headquartered in India   Met                    Unknown              Met
Privately held           Met                    Unknown              Met
Serves enterprise        Unknown                Unknown              Not met
─ Claims ────────────────────────────────────────────────────────────────────────────
Settled                  9 of 12                0 of 4               11 of 11
By status                ●3 ◐1 ◇0 ⬣0 ?5 ◌3      ◌4                   ●9 ◐2
─ Operating signals ─────────────────────────────────────────────────────────────────
People                   ~180 Estimate          –                    ~60 Estimate
Latest dated event       Facility announced     –                    Funding round
                         9 Sep 2026                                  3 Jun 2026
─ Record ────────────────────────────────────────────────────────────────────────────
Sources                  31                     4                    22
Assessment               v2 · 22 Nov 2026       –                    v1 · 20 Nov 2026
Cost                     86 cr · $0.42          12 cr · $0.04        61 cr · $0.31
```

- A `compact` table with a sticky first column of row labels (200px) and one equal column per case. Group rows are `h3`-style labels on `surface-sunken`.
- Criteria rows appear only when the cases share a thesis (`opportunity.criterion_results` with the same criterion ids); otherwise that group is replaced by one line: "These cases were scored against different criteria, so fit is not comparable row by row".
- No column is highlighted as the winner, no cell is coloured for better or worse, and there is no total row. The five judgments stay separate here as everywhere.
- Cells differ only by content; an empty value is a dash with the reason on hover.
- Entry points: `Compare (n)` in Companies, and `Add a case` here. The selection is in the URL.
- Empty: `EmptyState size="page"`, "Choose two to four cases to compare", with a case picker.

### 4.7 Signals (`/app/signals`)

Purpose: one dated feed of what the record shows across all cases. This is the Dealroom newsfeed's information design without its "new founder" badges.

Data: `events` on each `CaseDetail` (`event_date`, `title`, `kind`, `evidence`), plus changes DealProof itself recorded: a new assessment version (`assessment.created_at`, version), a claim whose status changed (`changed_in_version`), a document received (`documents`). All are already dated records with a source.

```
Signals                                        48 items · from 14 cases        
[All | Company events | Assessment changes | Documents]  [Company ▾] [Nature ▾]            48

22 Nov 2026
  16:42  Meridian Warehousing   Assessment v2 · Investigate further → Prioritise        Assessment
                                Because: lease start 1 Oct 2026            [▣ Lease agreement p. 3 · as of 1 Oct 2026]
  11:05  Meridian Warehousing   Document received · Lease agreement.pdf                 Document
9 Sep 2026
         Meridian Warehousing   Announcement describes a planned facility               Announced
                                                                [✎ Company announcement · as of 9 Sep 2026]
3 Jun 2026
         Northline Freight      Series A recorded                                       Recorded
                                                                [▤ Funding record · as of 3 Jun 2026]
```

- One list in a flush panel, grouped under mono date headings, newest first. Row grid: time 56px, company 200px (a `RowLink` to the case), sentence, nature tag right-aligned. The source line sits on the second line, right of the company column.
- Sorted by the date the thing happened (`event_date`), not by when DealProof retrieved it. Items with no date are in a separate "Undated" group at the end.
- Nature tag uses the three existing words, Announced, Reported, Recorded, plus Assessment and Document. Tags are neutral `Badge`s; no colour per type, no dot legend.
- An announcement of a plan is worded as a plan, as in the Events tab.
- Hiring and headcount items, where present, are tagged `Signal` and never sit under a heading that implies traction.
- No "live" indicator, no relative times ("5h ago"): dates are absolute so the feed can be quoted.
- Not a centred timeline with cards alternating left and right. One left-aligned column.

### 4.8 Investors (`/app/investors`)

Existing screens. Changes: `PageHeader` with figures (searches, investors listed), the searches table at `default` density, and on the search page a two-pane layout from `xl`: the ranked list on the left (span 5), the selected investor's detail on the right (span 7) with a `Panel` each for Comparable rounds (compact table: company, round, date, source), Why they fit, Unknown, and Possible duplicates. This is Dealroom's investor list and detail, without the match score rendered as a headline number: `rank` orders the list and the leading facts are the comparable-round count and the last dated round in the sector. The fixed caveat line stays under the list.

### 4.9 Approvals (`/app/approvals`)

Purpose: every request across cases, by state, with the one action that needs a named person.

Data: `request_list` and `message` on each `CaseDetail` (status, recipient, approver, timestamps), and `getSendSummary(caseId)`.

```
Approvals                           2 awaiting approval · 5 total           Test mode: nothing is sent
[Awaiting approval 2 | Approved 0 | Sent 1 | Suppressed 2 | Failed 0]

Company               Documents requested          Drafted        State                    Approver
Meridian Warehousing  3 · payroll, lender, lease   22 Nov, 16:40  Draft                    –              [ Review ]
Northline Freight     2 · audited statements, …    21 Nov, 10:12  Draft                    –              [ Review ]
```

- `default` table in a flush panel; segmented filter with mono counts. Default view is Awaiting approval.
- `Review` opens the case's Request tab. Approval happens there, with the existing confirmation dialog; there is no bulk approve and no approve button in this table, because each send is one explicit, named decision.
- State cell: Draft and Approved are plain text; Sent is the receipt's wording; Suppressed uses the hatched family and reads "Suppressed (test mode) · not sent"; Failed reads "Failed · not sent". No green.
- While sending is off, the test-mode line sits in the header meta and the Sent filter is labelled Suppressed first.
- The sidebar count is the number of drafts.
- Empty: "Nothing is waiting for approval. Requests appear here when a case has open claims a seller document would settle."

### 4.10 Scoring policy and Settings

- Policy: `PageHeader` (`title="Scoring policy"`, `meta="Policy 1.0 · the same records under the same policy produce the same assessment"`), then unboxed `Section`s with `compact` tables. A sticky in-page contents list in a 240px rail from `xl`. It is the one long reading page besides the memo.
- Settings: `PageHeader`, then three `Panel`s (Account, Preferences, Data and confidentiality), each a `DefinitionList` with controls on the right. No shadow on any block.

### 4.11 Case view

Unchanged in structure. It adopts: `PageHeader` with `back={{ label: "Companies", href: "/app/companies" }}`, figures (Fit, assessable share, claims settled, cost), the identity / fit / disposition band as one `Panel` with three hairline-divided cells, `TabsNav`, and `Panel` for each tab's blocks. The assessment rail stays at 320px.

## 5. Implementation plan

Three chunks with disjoint file ownership. Chunk 1 lands first and is small; chunks 2 and 3 then run in parallel. Nobody edits a file they do not own; a needed change in someone else's file is requested in the hand-off note.

### Chunk 1. Primitives and shell (lands first)

Owns

- `components/ui/**` (new: `page.tsx`, `stat.tsx`, `states.tsx`, `toolbar.tsx`, `link.tsx`, `definition.tsx`; changed: `card.tsx`, `table.tsx`, `tabs.tsx`, `input.tsx`, `select.tsx`, `button.tsx`, `index.ts`)
- `components/app-shell/**`
- `lib/format.ts`, `lib/adapt/**`, `lib/use-load.ts`
- `app/not-found.tsx`, `app/error.tsx`, `app/(app)/app/not-found.tsx`, `app/(app)/layout.tsx`
- `app/login/**`
- `app/design/**` (add the new primitives to the gallery)
- `app/globals.css` and `docs/design/tokens.css` (only `--layout-sheet-max`)

Does

1. Build every component in §3.1 to §3.3 exactly as named.
2. Create `lib/adapt/*` and extend `lib/format.ts` (§3.4) by copying, without deleting the old files; chunks 2 and 3 switch their imports and delete the old ones.
3. New `nav.ts` and `sidebar-nav.tsx` (§4.1), the "New" menu, the breadcrumb using the §2.9 names.
4. Not-found and error pages; login layout (issue 15).
5. Issues 1, 2, 10, 15, 18, 19, 20, 21.

Exit: the gallery shows `PageHeader`, `Panel`, `StatRow`, the three table densities, and the empty, loading and error trio at three sizes.

### Chunk 2. Workspace and research lists

Owns

- `components/dashboard/**` (becomes Overview)
- new `components/pipeline/**`, `components/companies/**`, `components/compare/**`, `components/signals/**`, `components/approvals/**`
- `components/discover/**`, `components/investors/**`
- `app/(app)/app/page.tsx`, `app/(app)/app/{pipeline,companies,compare,signals,approvals}/**`, `app/(app)/app/discover/**`, `app/(app)/app/investors/**`

Does

1. Overview, Pipeline, Companies, Compare, Signals, Approvals (§4.2 to §4.9) on the chunk 1 primitives.
2. Migrate Discover and Investors to `PageHeader`, `Panel`, `Loadable`; delete `discover/notice.tsx` and both `use-load.ts` files; switch to `lib/adapt` and delete the duplicated functions in `discover/adapt.ts`, `investors/adapt.ts`, `investors/format.ts`.
3. Issues 4, 5, 6, 7, 8, 11, 12, 13, 14, 17, 22, 23 within these folders.

Note for the builder already working on the new sections: keep the routes and component folder names above, and take `PageHeader`, `Panel`, `StatRow`, `Table density`, `EmptyState`, `ErrorState` and `LoadingState` from `components/ui` as soon as chunk 1 lands instead of local versions. If chunk 1 has not landed, code against the prop signatures in §3 and import from `@/components/ui`.

### Chunk 3. Case view, domain components, policy and settings

Owns

- `components/case/**`, `components/case-b/**` (merged into `case/`, folder removed)
- `components/dealproof/**`
- `app/(app)/app/cases/**`, `app/(app)/app/policy/**`, `app/(app)/app/settings/**`

Does

1. Merge `case-b` into `case`; switch to `lib/adapt`; delete both `adapt.ts` files (issue 9).
2. Case header on `PageHeader` and `Panel`; `TabsNav`; every tab on `Panel` and the state trio (§4.11).
3. Remove `ThinkingOrb` and rename the run header (issue 3). Move `StatusCounts` into `dealproof/` as `StatusDistribution` and tell chunk 2 the import path.
4. Icon sizes and glyph stroke (issue 16); motion removal in the ledger, events and comparables (issue 11); Comparables as a real table (issue 12).
5. Policy and Settings (§4.10).

### Shared rules for all three

- No new dependency. Removing `thinking-orbs` from `package.json` needs the user's permission first.
- No raw colour, radius, shadow or arbitrary spacing value; add a token in chunk 1 if one is missing.
- Fixture data may be extended only with records shaped like the API's; nothing a real response could not contain.
- After each chunk, the checks in §6.

## 6. Acceptance checks

Search checks, run from `apps/web` over the signed-in app folders.

| Check | Expect |
| --- | --- |
| `rounded-lg border border-line bg-surface` typed in a component outside `components/ui` | 0 |
| `function EmptyState`, `function ErrorNotice`, `function LoadError` outside `components/ui` | 0 |
| `<h1` outside `ui/page.tsx` and the memo | 0 |
| `text-xl` outside dialogs and the memo | 0 |
| `animate-row-in` outside `dealproof/claim-ledger.tsx` | 0 |
| `ThinkingOrb` | 0 |
| `size={14}` on `Icon` outside chips, tags, keycaps and table cells | 0 |
| `export function toEvidence` | 1 |
| `components/case-b` | does not exist |
| `kind: "action"` in `nav.ts` | 0 |

Reading checks, one per screen.

- The nav label, breadcrumb, `h1` and document title are the same word.
- The page has one `PageHeader`, and its meta line is a fact, not a description.
- Every table has a count above it and right-aligned mono numerals.
- Every list has an empty, a loading and an error state from `components/ui`, left-aligned.
- No figure appears that the API did not return; estimates carry the tilde and the tag; Not checked is counted apart.
- Nothing moves on load.
- With the product name covered, the screen could still only be DealProof: the source line, the hatch for what did not run, and fit shown with its assessable share are all present where they apply.

## 7. Open questions for the user

1. **Screenings in the sidebar.** The requested list has nine sections and no home for theses. This spec adds Screenings as a tenth. The alternative is to reach it only from the "New" menu and Overview.
2. **Removing the orb.** The direction's open decision 2 recommended `thinking-orbs`. This audit recommends removing it. It is the cheapest single change against "gimmicky".
3. **Aggregate endpoints.** Signals, Approvals and the Overview "Needs you" list read several cases. Building them from `getCase()` per case works for tens of cases. Past that, the API needs `/signals` and `/approvals` list endpoints. That is an API decision outside this document.
4. **Section headings at 14px.** This reverses the direction's "20px card title, section head in the app". It is the largest visual change in the spec and the one most responsible for the denser, calmer look.
