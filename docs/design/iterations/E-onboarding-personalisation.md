# E. Onboarding and personalisation

Design iteration · 2026-11-22 · docs only, nothing here is built yet

The user's request, in their words: "Design the onboarding experience. Add a signup button where startups can onboard and we take the information required for them, which personalises the results according to them and makes the application more catered towards them. Ideally we won't be showing different pages, but we will ensure different info can be used wherever we can, for example in giving them data or finding startups or whatever. We can analyse that as well."

Today there is no sign-up: an admin creates each workspace and user with `python -m app.auth.cli`, and the login page says so. Every workspace then sees the same app with the same blank forms, whether it is a CFO office looking for targets or a startup looking for investors. This document specifies self-serve signup, a four-step onboarding that captures an organisation profile, how that profile tailors the existing screens without adding new ones, the analytics that tell us whether it worked, and the backend behind all of it.

It extends `docs/design/design-direction.md` (§10 copy rules, §11 page inventory), `docs/design/iterations/B-app-consistency.md` (§4 information architecture) and `docs/content/app-microcopy.md`. Where it changes a rule in those, it says so in [§2.4](#24-changes-to-earlier-documents).

Every company, person and figure in the layouts below is a placeholder. Nothing here is a real record.

Contents: [0 The short version](#0-the-short-version) · [1 Signup and onboarding](#1-signup-and-onboarding-flow) · [2 Personalisation map](#2-personalisation-map) · [3 Analytics](#3-analytics) · [4 Data model and API](#4-data-model-and-api) · [5 Implementation plan](#5-implementation-plan) · [6 Open decisions](#6-open-decisions)

---

## 0. The short version

1. **Sign up** is one form: your name, work email, password, organisation name. It creates a workspace and its first user and signs them in. No email verification in the demo, and the page does not pretend otherwise.
2. **Onboarding** is four steps, each skippable, all editable later in Settings: who you are, what the record shows about your organisation, what you are looking for, and who approves.
3. **The moment** is step 2. The user types a website; DealProof identifies the company in Crustdata and shows its sector, headquarters, team size and funding, each with a source chip and an as-of date, each editable. The app shows what it found and where it found it, and asks whether it is right.
4. **The profile is an input, never evidence.** It pre-fills forms, sets default filters, orders first actions and supplies the user's own company as a reference row. It does not change a claim status, a fit formula, a disposition rule or an investor's ranking rule. Every tailored element says "From your profile" and links to the edit.
5. **Two kinds of values, never mixed.** A value from the record carries its source chip. A value the user typed carries "Stated by you". Editing a sourced value replaces the chip; the original is kept in the edit history.
6. **Analytics** are first-party, workspace-level and content-free: event names, enums, counts and durations. No thesis text, no claim text, no document names, no IP addresses.

---

## 1. Signup and onboarding flow

### 1.1 Where Sign up lives

| Place | Today | Change |
| --- | --- | --- |
| Home page nav (`components/marketing/sections.tsx`) | `Log in` link, `Open app` primary button | `Log in` link, `Sign up` primary button. With a `dp_session` cookie present the button reads `Open app` and goes to `/app`, as now |
| Home page hero and closing band | `Open app` primary, `See a worked case` secondary | `Sign up` primary, `See a worked case` secondary. Same cookie rule |
| Home page mobile menu | links plus `Log in` | adds `Sign up` as the last, full-width button |
| Login page (`app/login/page.tsx`) | "There is no sign-up page. An admin creates each account…" | "New to DealProof? `Create an account`" under the form. The subtitle becomes "Use your work email and password" |
| Signup page (`/signup`, new) | – | "Already have an account? `Log in`" under the form |
| When sign-up is closed (`AUTH_SIGNUP_MODE=closed`) | – | The home buttons read `Open app`, `/signup` shows one line: "Sign-up is closed on this deployment. Ask the person who runs DealProof for your team for an account", and the login page keeps today's admin note |

The button label is "Sign up" everywhere. The page title is "Create your account". No "Get started free", no "Join", no exclamation mark.

### 1.2 Signup page

Same split layout as the login page, so the two read as one pair: form on the left, a plain statement on `paper-warm` on the right.

```
┌──────────────────────────────────────────────┬───────────────────────────────────────────┐
│ DealProof                                    │                                           │
│                                              │  Tell us who you are once.                │
│   Create your account                        │  Every screen starts from there           │
│   One workspace for your organisation.       │                                           │
│   You can change all of this later           │  ─────────────────────────────────────    │
│                                              │  We look up your organisation in public   │
│   Your name                                  │  company data and show you what we found, │
│   [ Asha Rao                         ]       │  with the source on every line            │
│   Recorded on every request you approve      │  ─────────────────────────────────────    │
│                                              │  You confirm or correct it. Nothing is    │
│   Work email                                 │  assumed                                  │
│   [ asha@acmefreight.example         ]       │  ─────────────────────────────────────    │
│                                              │  Your profile sets defaults. It never     │
│   Password                                   │  changes what the evidence says           │
│   [ ••••••••••••            ] [ Show ]       │                                           │
│   At least 10 characters                     │                                           │
│                                              │                                           │
│   Organisation                               │                                           │
│   [ Acme Freight                     ]       │                                           │
│   This names your workspace                  │                                           │
│                                              │                                           │
│   [ Create account ]                         │                                           │
│                                              │                                           │
│   ───────────────────────────────────        │                                           │
│   Already have an account? Log in            │                                           │
│   We store your name, email and a hash of    │                                           │
│   your password. What we store and why       │                                           │
└──────────────────────────────────────────────┴───────────────────────────────────────────┘
```

Fields and validation

| Field | Rule | Error copy (inline, under the field, on blur and on submit) |
| --- | --- | --- |
| Your name | required, 1–200 characters after trim | `Enter your name. Approvals are recorded against a named person` |
| Work email | required, valid shape, at most 320 characters, lower-cased | `Enter a valid email address` |
| Password | at least `AUTH_MIN_PASSWORD_LENGTH` (10), at most 1024. No composition rules, no strength meter | `Use at least 10 characters` |
| Organisation | required, 2–200 characters after trim | `Enter your organisation's name` |
| (hidden) `company_url` | honeypot: must be empty | none; a filled value gets the generic failure below |

Responses

| Case | Behaviour |
| --- | --- |
| Created | Signed in (the `dp_session` cookie is set exactly as login sets it) and sent to `/welcome` |
| Email already has an account | `An account with this email already exists. Log in instead` with the link. This tells a visitor that the email is registered; see [§4.3](#43-signup-rate-limits-and-abuse-protection) for why that is accepted in the demo and how it is bounded |
| Rate limited (429) | `Too many accounts created from this network. Try again in {minutes} minutes` |
| Busy (503) | `DealProof is busy. Try again in a moment` |
| Anything else | `The account was not created. Nothing was saved. Try again` |

- The button reads `Create account`, then `Creating account` with the single linear loader while the request is in flight. It is disabled only during the request.
- A personal email (gmail.com and similar) is accepted. It only means the website field in step 1 is not suggested from the email.
- **Email verification is not required in the demo.** The page does not show a "check your inbox" step, because no email is sent (`EMAIL_SEND_ENABLED` is off). The account records `email_verified_at = null`. The production plan is in [§4.3](#43-signup-rate-limits-and-abuse-protection).
- **We do not verify that the person works at the organisation they name.** The profile only changes what that workspace sees, and the lookup returns public company data that anyone could search, so naming someone else's company gains nothing. The privacy note says this.

### 1.3 Onboarding frame

Route `/welcome`, signed-in only, outside the app shell: no sidebar, so nothing competes with the four questions.

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ DealProof                                                    Asha Rao · Skip setup       │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   1 About you    2 What the record shows    3 What you are looking for    4 Approvals    │
│   ━━━━━━━━━━━    ───────────────────────    ──────────────────────────    ───────────    │
│                                                                                          │
│   ┌ content column, max 640 ──────────────────────────────────────────────┐              │
│   │ h1, one helper sentence, the fields                                   │              │
│   └───────────────────────────────────────────────────────────────────────┘              │
│                                                                                          │
│   [ Back ]                                              Skip this step   [ Continue ]    │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

- The step header is the existing `step-header` pattern from Discover (numbers, because the steps are a real sequence). Completed steps are links; later steps are not.
- `Continue` saves the step to the server and moves on. `Skip this step` saves nothing from that step and moves on. `Skip setup` (top right) ends onboarding now, keeps whatever was already saved and goes to `/app`.
- Progress is stored on the server per step. Closing the tab, or the session expiring part-way, resumes at the same step after the next sign-in.
- Nothing is gated. A workspace with no profile gets the app exactly as it is today.
- After skipping, Overview shows one dismissible inline panel, not a banner or a modal: `Finish your profile · 2 of 4 steps done. It pre-fills searches and sets your defaults` `[ Continue setup ]` `Dismiss`. Dismissing is remembered on the server; Settings always has the profile.
- No confetti, no progress percentage, no "You're all set". The last step's button is `Finish`, and it lands on Overview ([§1.9](#19-landing-after-onboarding)).
- Motion: steps cross-fade with the existing route transition; fields in step 2 fill top to bottom with the list stagger used elsewhere. Reduced motion: no stagger, values appear at once.

### 1.4 Step 1 · About you

```
About you
This decides which defaults you start with. Every screen stays available either way

  You are
  ┌────────────────────────────┐ ┌────────────────────────────┐ ┌────────────────────────────┐
  │ ◉ An investor or acquirer  │ │ ○ A business raising money │ │ ○ An adviser               │
  │ You look for companies     │ │ You look for investors     │ │ You act for a buyer, an    │
  │ to buy or back             │ │ for your own company       │ │ investor or a business     │
  └────────────────────────────┘ └────────────────────────────┘ └────────────────────────────┘

  Which kind                                                      (changes with the choice above)
  ( Corporate development ) ( Private equity ) ( Venture capital ) ( Family office )
  ( Search fund ) ( Roll-up operator ) ( Other )

  Organisation
  [ Acme Freight                                   ]

  Website
  [ acmefreight.example                            ]   Suggested from your email
  We look this up in public company data to pre-fill the next step. Leave it empty to fill
  everything in yourself

                                                        Skip this step   [ Continue ]
```

| Choice | Second question | Options |
| --- | --- | --- |
| An investor or acquirer | Which kind | Corporate development · Private equity · Venture capital · Family office · Search fund · Roll-up operator · Other |
| A business raising money | Which kind | Startup · Established business |
| An adviser | Who you act for | Buyers and investors · Businesses raising money · Both |
| An adviser | Which kind | M&A advisory · Business broker · Fundraising adviser · Other |

- The three choices are radio cards (one hairline border, `accent-tint` fill when chosen, a real radio input underneath). No icons, no illustrations.
- "Startup" and "Established business" map to the existing `CompanyType` (`startup`, `established`), the same split the evaluation already uses. The user's own choice wins over the pipeline's inference for their own company.
- The website is suggested from the email's domain only when that domain is not a public mail provider. It is a suggestion in an editable field; no lookup has happened yet, and the helper line says where it came from.
- Validation: the type is required to continue (`Choose the one that fits best. You can change it in Settings`). Organisation is pre-filled from signup. Website is optional; when given it must parse to a registrable domain (`Enter a website such as acmefreight.example`). A scheme and path are stripped.
- `Continue` starts the lookup when a website was given and moves to step 2 immediately; the lookup's progress is shown there, not behind a spinner here.
- An adviser's profile describes the adviser's **default mandate**, not one client. Step 3 says so. Per-client profiles are out of scope ([§6](#6-open-decisions)).

### 1.5 Step 2 · What the record shows

This is the step the rest is built around. It has five states.

**Looking up** (usually two to four seconds)

```
What the record shows
Looking up acmefreight.example in public company data

  ✓ Company identified         Acme Freight Pvt Ltd · acmefreight.example
  › Reading the company record
  · Sector, headquarters, team size, funding

  This lookup is on us. It does not use your workspace's credits
```

The three lines are the real calls (`company_identify`, then `company_enrich`), shown with the step-checklist marks from the live run view. Fields below fill as the record arrives.

**Found** (a business raising money)

```
What the record shows
We found Acme Freight Pvt Ltd from acmefreight.example. Check each line. Change anything that
is wrong or out of date

  Is this your organisation?   Acme Freight Pvt Ltd · Pune, India · acmefreight.example
                               [▤ Crustdata company record · retrieved 22 Nov 2026]   Not us

  Sector            [ Transportation, logistics and storage  ▾ ]  [▤ Crustdata record · as of Nov 2026]
  Sub-sector        [ Warehousing ✕ ] [ Third-party logistics ✕ ] [ + ]
                                                                  [▤ Crustdata record · as of Nov 2026]
  Headquarters      [ Pune            ]  [ India           ▾ ]    [▤ Crustdata record · as of Nov 2026]
  Founded           [ 2014 ]                                      [▤ Crustdata record · as of Nov 2026]
  Team size         [ 51–200          ▾ ]   ~180  Estimate        [◔ Crustdata profiles · as of Oct 2026]
                    From professional profiles, not a payroll count
  Funding to date   $6.2M across 2 rounds                         [▤ Funding record · as of 3 Jun 2025]
  Stage             [ Series A        ▾ ]   Latest round on record: Series A, 3 Jun 2025
                                                                  [▤ Funding record · as of 3 Jun 2025]
  What you do       [ Runs warehousing and transport for enterprise customers in western India ]
  one line, 160 max                                               [✎ Company description · as of Nov 2026]

  Revenue           [ Prefer not to say ▾ ]   Optional            Not in the record. DealProof holds
                                                                  no revenue figures

  6 values from the record · 0 changed by you

  [ Back ]                              Skip this step   [ Confirm and continue ]
```

- Each row is: label, an editable control holding the value, and the source chip from the design direction §6.5 (class glyph, short source name, mono as-of date). The chip opens the evidence popover with the field path and value, the retrieval time and the identity key used (`domain = acmefreight.example`).
- **Editing a value replaces its chip.** The moment the user changes a sourced value, the chip becomes `Stated by you · 22 Nov 2026` in muted ink, and a `Restore` link appears that puts back the record's value and chip. The original is never shown as the user's and the user's value is never shown as the record's.
- Team size shows the estimate with its `Estimate` tag and basis line, exactly as elsewhere in the product, and maps it to a band in the control. The user may pick a different band; that band is then "Stated by you" and the estimate stays visible beside it.
- "Funding to date" is read-only here (it is a list of dated rounds; correcting a round is not this form's job). `Stage` is the editable field derived from the latest dated round and says which round it came from.
- "What you do" is the first sentence of the company description on record, cut at 160 characters at a word boundary. It is not rewritten by a model. Its chip uses the company-announcement class, because a company's description of itself shows what it says, not what is so.
- Revenue is never pre-filled. The right-hand note says why. Bands: Prefer not to say · Pre-revenue · Under $1M · $1–5M · $5–25M · $25–100M · Over $100M ([§6](#6-open-decisions) on currency).
- A field the record lacks is an empty control with `Not in the record` in muted ink where the chip would be. It is not hidden and not guessed.
- The summary line counts honestly: `6 values from the record · 2 changed by you · 1 added by you`.
- `Confirm and continue` saves every row with its provenance. Its label is "Confirm" because that is what the user is doing.
- `Not us` clears the match, discards the pre-filled values and shows the "Several matches" or "No match" state.

**Found** (an investor or acquirer, or an adviser). The same panel with four rows: the identity line, Sector, Headquarters, Team size. Founded, funding, stage and revenue are omitted, because a thesis does not use them. The helper sentence adds: `This describes your own organisation. What you are looking for is the next step`. For an acquirer the sector row matters: it seeds the thesis in step 3 and supplies the "your company" reference in Comparables.

**Several matches**

```
What the record shows
More than one company matches acmefreight.example. Pick yours. We do not guess

  ○ Acme Freight Pvt Ltd        Pune, India · ~180 people Estimate · acmefreight.example
  ○ Acme Freight Holdings Ltd   Mumbai, India · ~40 people Estimate · acmefreight.example
  ○ None of these               Fill in the details yourself

  [ Back ]                                              Skip this step   [ Continue ]
```

This is the product's identity rule applied to the user's own company: a name or a shared domain is not enough, and when the record cannot tell two apart the person decides.

**No match**

```
What the record shows
We did not find acmefreight.example in public company data. That is common for young and
privately held companies, and it changes nothing about what you can do here

  [ Try another website ]

  Fill in the details yourself. Every line will be marked "Stated by you"

  Sector            [ Choose                              ▾ ]
  …
```

**Lookup failed or not run** (source unavailable, the onboarding budget is spent, or no website was given)

```
  We could not look up acmefreight.example just now (the company data source did not answer).
  Nothing was pre-filled.   [ Try again ]   or fill in the details yourself
```

This follows the product's "Not checked" rule: a lookup that did not run is said to have not run, with the reason. It is never shown as "no data found".

### 1.6 Step 3 · What you are looking for

The step has two forms. An investor, acquirer or buy-side adviser sees the thesis form. A business or a fundraising adviser sees the raise form. An adviser who acts for both sees the thesis form with a link `Also set up a default raise` that opens the raise form below it.

**Thesis form** (investor, acquirer, buy-side adviser)

```
What you are looking for
Your default thesis. It pre-fills new screenings and the criteria on cases you open directly.
You edit it every time before anything runs

  Sectors           [ Warehousing ✕ ] [ Supply-chain software ✕ ] [ + ]     From your sector
  Geographies       [ India ✕ ] [ + ]                                       From your headquarters
  Stage or size     ( Any ) ( Startup ) ( Established )
                    Team size  [ 51–200 ▾ ] to [ 1,001–5,000 ▾ ]
  Ownership         ( Any ) ( Privately held ) ( Founder-owned ) ( Backed by investors )
  Deal types        [x] Acquisition (majority)  [x] Minority investment  [ ] Venture round
                    [ ] Growth equity  [ ] Debt
  Deal size         [ $2–10M ▾ ]        Optional

  Which of these are must-haves?
  A company that verifiably fails a must-have is removed from a shortlist. Everything else is a
  preference and only changes the fit score

  Must have         [ Geographies: India ✕ ] [ Ownership: privately held ✕ ]
  Preference        [ Sectors ✕ ] [ Team size ✕ ] [ Deal types ✕ ]
                    drag a chip between the rows, or use its menu: Make must-have · Make preference

  In your words     [ Regional operators with enterprise customers and recent expansion      ]
  optional, 400 max  Added to the thesis text as written

  [ Back ]                                              Skip this step   [ Continue ]
```

- "From your sector" and "From your headquarters" mark the two values carried from step 2. They are suggestions in editable fields, removed with one click.
- The must-have and preference split is the Discover criteria editor's own vocabulary, with its own explanation. The defaults are conservative: geography and ownership start as must-haves when set; everything else starts as a preference. A missing public record never fails a must-have (the PRD rule), and the helper text says "verifiably fails".
- Deal size has no must-have option: DealProof holds no valuations, so it could never be assessed. It is used only to describe the thesis and, for investors, to word the investor-side defaults.
- Chips can be moved by keyboard through the chip's menu; drag is a convenience.

**Raise form** (business raising money, fundraising adviser)

```
What you are looking for
What you want to raise. It pre-fills investor searches. Nothing is sent to any investor

  Kind of funding   ( Venture equity ) ( Growth equity ) ( Debt ) ( Grant ) ( Not sure yet )
  Amount            [ $2–10M ▾ ]        Optional
  Timing            ( Raising now ) ( In the next 6 months ) ( In 6 to 12 months ) ( Exploring )

  Investors you want
  Preferences       [x] Has backed companies in my sector
                    [x] Has invested in my country
                    [ ] Has led rounds at my stage
  These set the default filters on an investor shortlist. The ranking rule does not change:
  investors are ordered by the comparable rounds on record

  [ Back ]                                              Skip this step   [ Continue ]
```

- Kinds of funding are the four values the investor pipeline already maps (`venture_equity`, `growth_equity`, `debt`, `grant`) plus "Not sure yet", which leaves the field empty.
- The closing sentence is there because a business will otherwise read "preferences" as "investors likely to say yes".

Validation for both forms: nothing is required. `Continue` with an empty form saves nothing and behaves as `Skip this step`.

### 1.7 Step 4 · Approvals and notices

```
Approvals and notices
DealProof never sends a message to a seller or an investor until a named person approves it

  Approver          Asha Rao (you)
                    Your name is recorded on every request you approve. To add a teammate as
                    approver, ask the person who runs DealProof for your team to add them, then
                    choose them in Settings

  Signs as          [ Asha Rao                      ]
                    [ Finance, Acme Freight         ]
                    The sign-off on a drafted request. You can edit each draft before approving

  Tell me when      [x] A run finishes
                    [x] A request is waiting for approval
                    [x] A seller's documents arrive
                    [ ] A source could not be reached
                    Shown in the app. Email notices are off on this deployment

  Usage data        [x] Share anonymous usage counts to improve DealProof
                    Which steps people finish and how often defaults are kept. Never your thesis,
                    claims or documents.   What we record

  [ Back ]                                              Skip this step   [ Finish ]
```

- With one user in the workspace, the approver is that user and the row is read-only. With more, it is a select of named workspace members with `Anyone in this workspace` as an option. Approval itself is unchanged: one explicit decision per request by the signed-in person, recorded with their name. The preference only decides whose queue a draft appears in and who is notified.
- "Email notices are off on this deployment" is shown while `EMAIL_SEND_ENABLED` is false, matching the honest test-mode wording on the Request tab. When email is on, the line becomes `Sent to asha@acmefreight.example`.
- The usage checkbox is on by default and stated in plain words ([§3.1](#31-principles)).

### 1.8 Mobile layout

Below `md` everything is one column with 16px gutters.

```
┌──────────────────────────────┐   ┌──────────────────────────────┐
│ DealProof          Skip setup│   │ DealProof          Skip setup│
│ Step 2 of 4                  │   │ Step 1 of 4                  │
│ ━━━━━━━━━━━━━━──────────────│   │ ━━━━━━━─────────────────────│
│                              │   │                              │
│ What the record shows        │   │ About you                    │
│ We found Acme Freight Pvt    │   │ You are                      │
│ Ltd. Check each line         │   │ ┌──────────────────────────┐ │
│                              │   │ │ ◉ An investor or acquirer│ │
│ Sector                       │   │ │ You look for companies   │ │
│ ┌──────────────────────────┐ │   │ └──────────────────────────┘ │
│ │ Transportation, logist… ▾│ │   │ ┌──────────────────────────┐ │
│ └──────────────────────────┘ │   │ │ ○ A business raising     │ │
│ [▤ Crustdata record ·        │   │ │   money                  │ │
│    as of Nov 2026]           │   │ └──────────────────────────┘ │
│                              │   │ ┌──────────────────────────┐ │
│ Team size                    │   │ │ ○ An adviser             │ │
│ ┌──────────────────────────┐ │   │ └──────────────────────────┘ │
│ │ 51–200                  ▾│ │   │                              │
│ └──────────────────────────┘ │   │ Which kind                   │
│ ~180 Estimate                │   │ ┌──────────────────────────┐ │
│ [◔ Crustdata profiles ·      │   │ │ Corporate development   ▾│ │
│    as of Oct 2026]           │   │ └──────────────────────────┘ │
│ …                            │   │ …                            │
├──────────────────────────────┤   ├──────────────────────────────┤
│ Skip          [   Confirm   ]│   │ Skip          [  Continue   ]│
└──────────────────────────────┘   └──────────────────────────────┘
```

- The step header collapses to "Step 2 of 4" with a 2px track. Step names are announced to screen readers.
- The source chip moves under its control and never truncates the as-of date; the source name truncates first. Tapping it opens the evidence drawer (the popover's small-screen form).
- Chip groups for "Which kind" become a native select below `sm`. Radio cards stack. The must-have and preference rows stack, and moving a chip uses its menu (no drag on touch).
- The action row is sticky at the bottom with a hairline above it: `Skip` as a text button on the left, the primary button on the right, both 44px tall. `Back` is the browser's back and the step link in the header.
- Signup stacks the same way; the right-hand statement panel is hidden below `lg`, as on login.
- Inputs use `inputmode="email"` and `inputmode="url"`, `autocomplete="name"`, `email`, `new-password` and `organization`, and 16px text so iOS does not zoom.

### 1.9 Landing after onboarding

`Finish` goes to `/app`. There is no separate success page. Overview's own empty state does the work ([§2.2](#22-screen-by-screen), Overview and empty states), with the first action chosen by type:

| Type | First action (primary) | Second |
| --- | --- | --- |
| Investor or acquirer | `Start a screening from your thesis` → `/app/discover/new` with the thesis draft filled | `Verify a company` |
| Business raising money | `Find investors for {org}` → `/app/investors/new` with the form filled | `See your company's record` |
| Adviser, buyers | as investor | – |
| Adviser, businesses | as business, worded `Find investors for a client` | – |
| Adviser, both | `Start a screening` and `Find investors` side by side | – |
| No profile | today's empty state | – |

Neither action runs anything. Each opens the existing form, pre-filled, where the user still presses the existing button. Credits are spent only by a button the user presses.

### 1.10 Editing later: Settings

Settings gains a fourth `Panel`, **Organisation profile**, between Account and Preferences. It is the same four groups as a `DefinitionList`, each value with its chip, and one `Edit` per group that opens the step's form in a dialog.

```
Organisation profile                                   Version 3 · last changed 22 Nov 2026 by Asha Rao

  About you          A business raising money · Startup                                    [ Edit ]
                     Acme Freight · acmefreight.example

  What the record    Sector        Transportation, logistics and storage  [▤ Crustdata record · as of Nov 2026]
  shows              Headquarters  Pune, India                            [▤ Crustdata record · as of Nov 2026]
                     Team size     201–500                                Stated by you · 22 Nov 2026
                                   ~180 Estimate                          [◔ Crustdata profiles · as of Oct 2026]
                     Stage         Series A                               [▤ Funding record · as of 3 Jun 2025]
                     [ Edit ]   [ Look up again ]   Last looked up 22 Nov 2026

  Looking for        Growth equity · $2–10M · raising now                                  [ Edit ]

  Approvals          Approver: Asha Rao · Signs as "Asha Rao, Finance, Acme Freight"       [ Edit ]

  History            3 changes   Show
  Delete profile     Removes the profile and its history. Your cases are not changed       [ Delete ]
```

- `Look up again` re-runs the lookup and shows a diff, in the assessment-diff pattern: `Team size  ~180 → ~210 Estimate (as of Feb 2027)` with `Accept` per row. A value the user stated is never overwritten by a refresh; the new record value is shown beside it.
- History lists each change: date, person, field, from, to, and whether each side was from the record or stated.
- Changing the type from "business" to "investor" keeps the other side's answers stored but unused, so switching back loses nothing.
- Existing CLI-created workspaces have no profile. They see `Set up your profile` in this panel and the Overview panel from [§1.3](#13-onboarding-frame); nothing else changes for them.

### 1.11 Privacy: what we store and why

The "What we store and why" link on signup and step 4 opens this table (also the fourth block on the Confidentiality page).

| What | Why | Who sees it | How long |
| --- | --- | --- | --- |
| Your name | Recorded on requests you approve | Your workspace; a seller on a request you approve | While the account exists |
| Your email | Sign-in and notices | Your workspace | While the account exists |
| Password | Sign-in. Stored only as an Argon2 hash | No one | While the account exists |
| Organisation name and website | Names the workspace; the website is the lookup key | Your workspace | Until you delete the profile |
| Public company record for your website (sector, headquarters, team-size estimate, funding rounds) | Pre-fills your profile and is the "your company" reference | Your workspace. It is public data, retrieved once and cached | Until you delete the profile or look up again |
| What you typed (kind, thesis, raise, revenue band, sign-off) | Sets defaults in forms and filters | Your workspace | Until you change or delete it. Earlier values stay in the profile history until the profile is deleted |
| Usage counts | To see where onboarding fails and whether defaults help | DealProof's team, by workspace type, never with content | 180 days in detail, then monthly totals only |

Also stated on that page, in sentences:

- Your profile is used only inside your workspace. It is not shown to sellers, investors or other customers, and it is not used to train AI models.
- The profile is not sent to the language model as free text. The model sees the same structured form values that any search form sends today ([§4.7](#47-how-pipelines-read-the-profile)).
- Revenue is optional, is a band and not a figure, and is used only to word your own investor search. It never appears in a case, a memo or a request.
- We do not collect anyone's personal contact details during onboarding other than your own name and email.
- We do not verify that you work at the organisation you named.
- Deleting the profile removes it and its history. Runs already finished keep the form values they were started with, because a case must stay reproducible.

---

## 2. Personalisation map

### 2.1 Rules

These hold on every screen. They are the PRD's principles applied to a profile.

1. **The profile is an input, never evidence.** It can fill a form, set a default filter, choose a first action, order a menu, word a template and add the user's own company as a reference. It cannot change a claim status, the evidence attached to anything, the fit formula, the policy thresholds, the disposition rules or the investor ranking rule.
2. **Pre-filled is not submitted.** Every profile-derived form value arrives in an editable field, before anything runs. No run starts because a profile exists.
3. **Said out loud.** Any tailored element carries a `ProfileNote`: one muted line, `From your profile · Edit`, linking to the Settings panel. A default filter is a visible, removable chip. There is no silent tailoring.
4. **Same records, same answer.** A run snapshots the form values it was started with (as it does today) and the profile version they came from. Changing the profile later changes no finished run, shortlist or assessment. Two workspaces that run the same thesis text and criteria get the same shortlist.
5. **Sourced or stated, never blended.** The user's own company appears with the record's values and their chips. Values the user stated appear with "Stated by you". Where both exist they sit side by side.
6. **The fit score is still not a prediction, and the investor ranking still describes history.** Personalisation makes the question more specific. It does not make the answer more certain, and no copy implies it does. The fixed caveats stay where they are.
7. **Missing profile, same app.** Every row below has a no-profile behaviour, and it is today's behaviour.
8. **No new pages.** Signup and the onboarding frame are the only new routes. Everything else is the screens in B §4.

### 2.2 Screen by screen

"Driven by" names fields from [§4.1](#41-org_profiles). I = investor or acquirer (and buy-side adviser), B = business raising money (and fundraising adviser).

| Screen | What changes | Driven by | What does not change |
| --- | --- | --- | --- |
| **Sidebar** | The `New` menu's first item: I → `New screening`, B → `Find investors`. Nav items, order and labels are identical for everyone | `org_type`, `acts_for` | The nav. A business still has Companies, Screenings and Compare; an investor still has Investors |
| **Top bar and command menu** | Workspace name is the organisation name. The command menu lists the type's first action first | `org_name`, `org_type` | Commands available |
| **Overview** | A context line under the page title (see [§2.3](#23-overview-in-detail)). A "Matching signals" panel replaces the right-hand Screenings list's lower half when there are matches. For B the stat row's first tile is `Investor searches`, and "Recently updated cases" sits below "Investor searches" | `thesis.*` or `raise.*`, `sectors`, `geographies` | The stat tiles' definitions; "Needs you" rules; no greeting headline |
| **Pipeline** | Nothing | – | Columns are derived states of cases; a profile has no bearing on them |
| **Companies** | One extra filter chip `Your sectors`, off by default. For I with an identified own company, that company is never listed as a target; if a shortlist returned it, it is dropped with the count line `1 removed: this is your own organisation` | `sectors`, `own_company_id` | Columns, order, default sort |
| **Screenings · step 1 Thesis** | The textarea starts with a thesis draft composed from the profile by a fixed sentence template, with a `ProfileNote` and `Clear`. Example chips are replaced by up to three variations of the user's own thesis (`Same, any size`, `Same, in South-East Asia`) | `thesis.sectors`, `thesis.geographies`, `thesis.size_*`, `thesis.ownership`, `thesis.deal_types`, `thesis.note` | The text is the user's to edit; criteria are still extracted from the text that is submitted |
| **Screenings · step 2 Criteria** | Criteria extracted from the text arrive with the profile's must-have and preference split applied where a criterion's dimension matches (geography, ownership, industry, size). Each such row shows `From your profile` in the "Assessed from" column's sub-line | `thesis.must_haves`, `thesis.preferences` | Weights (must 2, preference 1), "Edit before searching. Nothing runs yet", and every edit control |
| **Screenings · step 3 Shortlist** | For I with an identified own company: the own company is dropped (above). A `Relative to you` line on each card where both sides have the figure: `~90 people Estimate · you ~2,400 Estimate`, each with its chip | `own_company_id`, profile record values | Fit, assessable share, rank, exclusion reasons |
| **Investors · new search form** | Sector, location, stage, size and funding sought arrive filled from the profile. Section label reads `Your business · from your profile`. For an adviser the label is `Your client's business` and the form starts empty unless a default raise was set | `sector`, `hq_country`, `stage`, `team_size_band`, `raise.kind` | The form's fields and the button |
| **Investors · shortlist** | When the own company is identified: comparables are found from the company's recorded activity categories and headcount (the rule `verify.comparables` already uses), not only from the typed sector, and the scope note says so. An investor already on the user's own funding record is tagged `Invested in you · Series A, 3 Jun 2025` with the round's chip. Default filters from the raise preferences appear as removable chips | `own_company_id`, own funding rounds, `raise.preferences` | The ranking rule (recency-weighted count of comparable rounds), the caveat line, "no dated record, no investor", duplicates never merged |
| **Case · Overview and memo** | Memo header reads `Prepared for {org_name}`. The opportunity section's first sentence names the thesis the case was scored against | `org_name` | Everything the memo asserts |
| **Case · fit criteria (direct verify)** | A case opened from a name and website has no thesis, and today asks for criteria before any fit score. The criteria editor now starts from the default thesis, with `From your default thesis · Edit before scoring` | `thesis.*` | No fit score until the user confirms criteria |
| **Case · Comparables** | A `Your company` reference row above the peers, with the same columns, from the profile's own record and chips. Labelled `Reference, not a peer`. It is not counted toward the "at least two fair peers" rule and does not appear when the user's company fails the fairness basis in a way that would mislead (different country: the row still shows, with `Different country from this company` beside it) | `own_company_id`, profile record values | The peer set, the fairness rule, "No fair comparison found" |
| **Compare** | An optional first column `Your company · reference`, toggled by `Show your company`, on by default for I when the own company is identified. It fills only the rows that exist for it (identity, people estimate, latest dated event from its record). Disposition, fit, criteria and claims are dashes with `Not assessed: this is your own organisation` | `own_company_id`, profile record | No winner column, no colouring, no totals |
| **Signals** | A default filter chip `Your sectors · {geographies}` when the profile has them and at least one item matches; `Show all` removes it and the choice is remembered. Items from cases opened under the default thesis are not ranked higher; the feed stays date-ordered | `sectors`, `geographies` | Date order, nature tags, absolute dates, no "live" |
| **Approvals and Request tab** | A drafted request's sign-off uses `signs_as_name` and `signs_as_org`; the subject line is unchanged. The Approvals default view is `Awaiting approval` filtered to drafts for the named approver, with `All approvers` one click away | `signs_as_*`, `default_approver_user_id` | One explicit approval per request, the confirmation dialog, send-once, test-mode wording |
| **Scoring policy** | Nothing | – | The policy is the same for every workspace. That is the point of it |
| **Settings** | The Organisation profile panel ([§1.10](#110-editing-later-settings)) | all | – |
| **Live run view** (D) | One `status` activity at the start of a run that used profile defaults: `Started from your profile (version 3)`, linked to the form values used | `profile_version` | Every other activity |
| **Empty states** | Body and first action by type ([§2.5](#25-empty-states)) | `org_type`, `acts_for`, `org_name` | Illustration case link |
| **Home page (signed out)** | Nothing | – | It has no profile to read |

### 2.3 Overview in detail

The design direction rules out greeting headlines, and Overview in B has "no greeting". The request asks that Overview "greets them with their thesis". Both hold: the page keeps its title and gains a **context line**, a statement of what the workspace is set up to do, in the same place and size as the existing meta line.

```
Overview                                                                       [ + New ▾ ]
Acme Freight · Corporate development
Looking for  warehousing, supply-chain software · India · privately held · 51 to 5,000 people
             From your profile · Edit                             [ Start a screening from this ]
14 cases · 3 screenings · last updated 22 Nov 2026, 16:42 IST

┌ Cases 14 ─────┬ Needs you 4 ──┬ Prioritise 3 ─┬ Not checked 7 ──┬ Spent ──────────┐
…
┌ Needs you 4 ──────────────────────────────── span 8 ┐ ┌ By disposition ── span 4 ┐
…
┌ Recently updated cases 8 ─────────────────── span 8 ┐ ┌ Matching signals 5 ─ sp 4┐
│ …                                                   │ │ In your sectors · India  │
│                                                     │ │ 9 Sep 2026  Meridian W…  │
│                                                     │ │ Announcement describes a │
│                                                     │ │ planned facility         │
│                                                     │ │ [✎ Announcement · as of  │
│                                                     │ │    9 Sep 2026]           │
│                                                     │ │ View all in Signals      │
│                                                     │ ├ Screenings 3 ────────────┤
│                                                     │ │ …                        │
└─────────────────────────────────────────────────────┘ └──────────────────────────┘
```

For a business the context line reads:

```
Acme Freight · Startup · Series A · Pune, India
Raising  growth equity · $2–10M · now
         From your profile · Edit                                  [ Find investors for this ]
```

- "Matching signals" is the Signals feed with the default filter applied, five rows. It lists only dated records DealProof already holds from this workspace's cases. With no matches the panel is absent; it is never filled with something looser.
- The word is "Matching" in the plain sense of "in your sectors and geographies". The panel's sub-line states the filter. It does not say "recommended" or "for you".
- For a business with an identified own company, a second panel `Your company's record` shows its last three dated events and funding rounds with chips, linking to a case for the company if one exists and offering `Open a case for {org}` if not. This is the "See your company's record" action from [§1.9](#19-landing-after-onboarding).

### 2.4 Changes to earlier documents

| Document | Rule today | Change |
| --- | --- | --- |
| `design-direction.md` §10 | "no greeting headlines" | Unchanged. The Overview context line is a statement of scope, not a greeting; it has no salutation and no name of the person |
| `B-app-consistency.md` §4.2 | "No greeting, no illustration, no activity graph" | Unchanged, with the context line added above the meta line and "Matching signals" as an optional span-4 panel |
| `B-app-consistency.md` §4.1 | `New` menu order: New screening · Verify a company · Find investors | First item depends on the type; the other two keep their order |
| `B-app-consistency.md` §4.10 | Settings has three panels | Four, with Organisation profile second |
| `app-microcopy.md` login | "There is no sign-up page…" | Replaced as in [§1.1](#11-where-sign-up-lives) |
| `app-microcopy.md` §2 Investor discovery | Section label `Your business` | `Your business · from your profile` when pre-filled |
| `apps/web/app/login/page.tsx` doc comment and `app/auth/cli.py` docstring | "There is no sign-up page" | Updated; the CLI stays for admins and for adding teammates |

New copy (to be added to `app-microcopy.md` as §19 when this is built): the strings in §1, plus:

- `ProfileNote`: `From your profile · Edit`
- Stated chip: `Stated by you · {date}`
- Restored: `Restored to the record's value`
- Own company in a shortlist: `{n} removed: this is your own organisation`
- Reference row label: `Your company` / `Reference, not a peer`
- Compare empty cell: `Not assessed: this is your own organisation`
- Investor tag: `Invested in you · {round}, {date}`
- Run activity: `Started from your profile (version {n})`

### 2.5 Empty states

| Screen | Type | Heading | Body | Actions |
| --- | --- | --- | --- | --- |
| Overview | I | `No cases yet` | `Your thesis is set: {thesis_summary}. Start a screening from it, or open a case for a company you already have in mind.` | `Start a screening from your thesis` · `Verify a company` |
| Overview | B | `Nothing here yet` | `Start with the investors who have backed companies like {org_name}. Each one is listed with the dated rounds that put it there.` | `Find investors for {org_name}` · `See your company's record` |
| Overview | none | today's | today's | today's |
| Screenings | I | `No screenings yet` | `A screening turns a thesis into a shortlist of real companies. Yours starts from your default thesis.` | `Start a screening` |
| Screenings | B | `No screenings yet` | `A screening finds companies that match a thesis. If you are raising money, Find investors is usually the place to start.` | `Find investors` · `Start a screening` |
| Investors | B | `No investor searches yet` | `We will look for companies comparable to {org_name} that have raised money, and list who invested in them and when.` | `Find investors for {org_name}` |
| Investors | I | `No investor searches yet` | `Investor search is for a business raising money. It lists investors by the comparable rounds on record.` | `Find investors` |
| Signals | any, filter empty | `Nothing in your sectors yet` | `Signals come from the cases in this workspace. None of them is in {sectors} so far.` | `Show all signals` |
| Compare | I with own company | `Choose two to four cases to compare` | `Your company is added as a reference column.` | case picker |

### 2.6 Pipelines

| Pipeline | What reads the profile | How | Guard |
| --- | --- | --- | --- |
| **Discover** | Thesis text draft; criteria kind defaults | The web asks `GET /profile/defaults` for the draft text and passes nothing extra: the thesis is created from text the user submitted, as today. After criteria extraction, the API applies the profile's must-have and preference split to criteria whose dimension matches, sets `edited = false` and a new `origin = "profile"` on those rows | The split is applied once, at extraction, and the user edits before searching. `thesis.profile_version` records which version was used |
| **Discover · search** | Own company id | The shortlist step drops a candidate whose `crustdata_company_id` equals `own_company_id`, counted in the step output | Dropped only on an id match, never on a name |
| **Investor discovery** | The whole `InvestorSearchIn`, pre-filled; own company id; own funding rounds | Form values come from `GET /profile/defaults`. When the search is started with `use_own_company = true` and the profile has `own_company_id`, the comparable search adds the company's recorded activity categories and uses its headcount estimate for the size band; own investors are tagged from the profile's stored funding rounds | Ranking unchanged. `use_own_company` is false for advisers by default. The scope note states the basis: "comparables chosen from Acme Freight's recorded activity (warehousing, third-party logistics)" |
| **Verify · comparables** | Own company record | No change to the peer search. The case API adds a `reference` object beside `comparables`, built from the profile snapshot | Reference is never stored as a `Comparable` row |
| **Verify · events / Signals** | Sectors, geographies | Filtering happens in the browser over what is already loaded (`lib/workspace.ts`), by the case company's recorded industry and country | No extra calls |
| **Evaluate** | Default thesis, for direct-verify cases | The case criteria editor is seeded from `GET /profile/defaults`; the user confirms; evaluation runs on the confirmed criteria as today | No fit score before confirmation. Company type for the target is still inferred from the target's record |
| **Act** | `signs_as_name`, `signs_as_org` | `drafting/seller_email.py` already takes `sender_name` and `sender_organisation`; they are filled from the profile, falling back to the approver's display name and the workspace name | The draft is editable; nothing is sent without approval |
| **Memo** | `org_name` | Header line only | – |

The language model's exposure does not grow: it sees a thesis text the user submitted and form fields the user submitted, as now. The profile itself is never added to a prompt as background.

---

## 3. Analytics

### 3.1 Principles

1. **First party only.** Events go to our own API and table. No third-party script, pixel or SDK, on the home page or in the app.
2. **Workspace-level, typed, content-free.** An event is a name, the workspace, the workspace's type at that moment, and a small set of allowlisted properties whose values are enums, booleans, counts and durations. There is no free-text property. The API rejects unknown names and unknown property keys.
3. **Never recorded:** thesis text, criteria labels, claim text, document names or contents, company or investor names, websites, search queries, email addresses, IP addresses, user agents, anything from an uploaded deck.
4. **People are not profiled.** Events carry no user id. Where "distinct people" would matter, the workspace is the unit. The one exception is `approval.recorded`, which already exists as an approval row with a named person for audit; analytics counts it without the name.
5. **Derive, do not track, where the record already exists.** Runs, cases, shortlists, approvals and credits are in the database with timestamps. Those metrics are computed by query from the source tables. Only what the server cannot see (which onboarding step was viewed, whether a pre-filled field was edited before submit) is sent by the browser.
6. **Off means off.** The step 4 checkbox, mirrored in Settings, stops browser events for that workspace and excludes it from derived per-workspace rows. Global `Sec-GPC` and `DNT` headers are honoured for browser events. Signed-out pages record nothing.
7. **Short retention.** Event rows are deleted after 180 days by the existing retention job. Monthly aggregates by type are kept.

### 3.2 Events

Browser events (sent to `POST /analytics/events`):

| Event | When | Properties |
| --- | --- | --- |
| `onboarding.step_viewed` | A step renders | `step` (1–4) |
| `onboarding.step_completed` | `Continue` or `Finish` saved | `step`, `duration_s` (capped at 3,600), `fields_filled` (count) |
| `onboarding.step_skipped` | `Skip this step` | `step` |
| `onboarding.exited` | `Skip setup` | `at_step` |
| `onboarding.finished` | Step 4 saved | `steps_completed` (0–4), `total_duration_s` |
| `autofill.reviewed` | Step 2 confirmed | per field key, one of `accepted`, `edited`, `cleared`, `added`, `absent` (for example `sector: "accepted"`); `match` (`single`, `chosen`, `none`, `rejected`, `failed`, `not_run`) |
| `defaults.used` | A pre-filled form is submitted | `surface` (`thesis`, `criteria`, `investor_search`, `case_criteria`), `outcome` (`unchanged`, `edited`, `cleared`), `fields_changed` (count) |
| `defaults.filter_removed` | A default filter chip is removed | `surface` (`signals`, `investors`, `approvals`) |
| `profile.edited` | Settings profile saved | `group` (`about`, `record`, `looking_for`, `approvals`), `fields_changed` (count) |
| `first_action.clicked` | A first-action button in an empty state or the context line | `action` (`start_screening`, `find_investors`, `verify_company`, `own_record`) |

`defaults.used` with `surface = thesis` reports `edited` when the submitted text differs from the draft and `fields_changed` as a coarse band of how much (0, 1–20%, 21–50%, over 50% of characters), computed in the browser. The text itself never leaves the form except as the thesis the user is submitting.

Server events (written by the API in the same transaction as the thing they describe; no browser involvement):

| Event | When | Properties |
| --- | --- | --- |
| `signup.completed` | Account created | `mode` (`open`, `invite_code`) |
| `signup.rejected` | Signup refused | `reason` (`rate_limited`, `duplicate`, `honeypot`, `closed`, `invalid`); no workspace |
| `autofill.lookup` | Lookup returned | `match` as above, `credits` (number), `from_cache` |
| `run.started` | Any run created | `kind` (`discover`, `investors`, `verify`, `evaluate`, `recheck`), `from_profile` (bool), `nth` (1 for the workspace's first run of that kind) |
| `run.finished` | Run reaches a final state | `kind`, `state`, `duration_s`, `credits`, `stopped_on_budget` (bool) |
| `shortlist.ready` | First shortlist of a thesis or investor search | `kind`, `items` (count) |
| `case.assessed` | A case first reaches `assessed` | `disposition`, `claims` (count), `claims_settled` (count) |
| `approval.recorded` | A request is approved | `test_mode` (bool) |

### 3.3 Measures

| Question | Measure | From |
| --- | --- | --- |
| Do people finish onboarding? | Completion: workspaces with `onboarding.finished` ÷ `signup.completed`, by type | events |
| Where do they leave? | Step funnel: viewed → completed or skipped, per step, by type | events |
| How long to value? | Time to first run and time to first shortlist: `signup.completed` → first `run.started` → first `shortlist.ready`, median and 75th percentile, by type | events |
| Does the work get done? | Cases assessed per workspace per week; approvals per workspace | `cases`, `approvals` tables |
| What does each type cost? | Credits spent per workspace per week by type and by run kind; credits per assessed case | `cost_entries` joined to `org_profiles.org_type` |
| Does a profile help? | Time to first run and runs in the first week, for workspaces that finished onboarding against those that skipped | events |

**Personalisation quality.** The honest test of a pre-fill is whether the person left it alone.

| Signal | Reading |
| --- | --- |
| Lookup match rate (`single` + `chosen`) by type and by country | How often "the app already knows you" happens at all. A low rate for young Indian companies is expected and should be visible, not averaged away |
| `Not us` rate (`rejected`) | Wrong-entity matches. This is the one that damages trust; target near zero, and any rise means the domain match rule is too loose |
| Field acceptance rate: `accepted` ÷ (`accepted` + `edited` + `cleared`), per field | Which sourced fields are right. Expected weakest: team-size band (profile estimates undercount operating staff) and sub-sector |
| Thesis draft kept: `defaults.used` `surface = thesis` by outcome and edit band | Whether the default thesis is close to what people search for |
| Criteria split kept: `surface = criteria`, `fields_changed` | Whether the must-have and preference defaults are right |
| Investor form kept: `surface = investor_search` | Whether the business profile is enough to start a search |
| Default filter removal rate | A filter most people remove should stop being a default |
| Downstream, with care | Shortlist-to-case rate and cases assessed for runs with `from_profile = true` against `false`. This is correlation between groups that chose differently; the view labels it as such and draws no conclusion from it |

No measure uses the content of a thesis, a claim or a document, and none scores an individual person.

### 3.4 Internal analytics view

One page, `/app/internal/analytics`, visible only to signed-in users whose email is in `ANALYTICS_ADMIN_EMAILS`. It is not in the sidebar (reachable from the command menu for those users) and answers 404 for everyone else. It reuses `PageHeader`, `StatRow`, `Panel` and the `compact` table. No new chart types: the funnel is a ranked list with one neutral bar per row, like "By disposition".

```
Product analytics                                Last 30 days ▾     All types ▾
41 workspaces · 29 with a profile · updated 22 Nov 2026, 16:42 IST · counts only, no content

┌ Signed up ────┬ Finished setup ┬ First run ─────┬ First shortlist ┬ Credits ────────┐
│ 41            │ 26 · 63%       │ 31 · 76%       │ 27 · 66%        │ 3,912           │
│ 3 rejected    │ median 3m 10s  │ median 6m      │ median 11m      │ 95 per workspace│
└───────────────┴────────────────┴────────────────┴─────────────────┴─────────────────┘

┌ Onboarding funnel ───────────────── span 7 ┐ ┌ By type ─────────────────────── span 5 ┐
│ Step                 Viewed  Done  Skipped │ │ Type           Wksp  Setup  Runs  Cr   │
│ 1 About you            41     39     2     │ │ Investor        17    12     48  2,210 │
│ ▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮           │ │ Business        15    11     22    940 │
│ 2 Record               39     33     4     │ │ Adviser          6     3     14    690 │
│ ▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮                 │ │ No profile       3     –      4     72 │
│ 3 Looking for          37     30     5     │ └────────────────────────────────────────┘
│ 4 Approvals            35     26     7     │ ┌ Work done ───────────────────── span 5 ┐
└────────────────────────────────────────────┘ │ Cases assessed            38           │
┌ Pre-fill quality ────────────────── span 7 ┐ │ Requests approved          9 (9 test)  │
│ Lookup   single 22 · chosen 3 · none 9 ·   │ │ Credits per assessed case 71           │
│          not us 1 · failed 2 · not run 4   │ │ Median time to first shortlist  11m    │
│ Field          Kept  Edited  Cleared  n    │ └────────────────────────────────────────┘
│ Sector         84%    12%      4%     25   │
│ Headquarters   96%     4%      0%     25   │
│ Team size      56%    44%      0%     25   │
│ Stage          80%    13%      7%     15   │
│ Thesis draft   kept 5 · edited 9 · cleared 1                                            
│ Criteria split kept 8 · edited 6                                                        
└────────────────────────────────────────────┘
```

- Every figure is a count or a median with its denominator (`n`) shown. A rate over fewer than five workspaces is shown as counts only, so one workspace cannot be read off the page.
- No workspace names, no per-workspace drill-down. This page answers "is onboarding working" and nothing about any one customer.
- Filters: period, type. That is all.

---

## 4. Data model and API

### 4.1 `org_profiles`

One row per workspace. Queryable facts are columns; every profile value with provenance lives in `fields`.

```
org_profiles
  id                         uuid pk
  workspace_id               uuid fk workspaces.id, unique
  version                    int not null default 1         -- bumps on every saved change
  org_type                   text null                      -- investor_acquirer | business | adviser
  org_kind                   text null                      -- corp_dev | private_equity | venture_capital |
                                                            -- family_office | search_fund | roll_up | startup |
                                                            -- established | ma_advisory | broker |
                                                            -- fundraising_adviser | other
  acts_for                   text null                      -- advisers only: buyers | businesses | both
  website_domain             text null                      -- registrable domain, lower case
  own_company_id             bigint null                    -- Crustdata company id, set only on a confirmed match
  own_company_match          text not null default 'not_run'-- single | chosen | none | rejected | failed | not_run
  record_source_id           uuid null fk sources.id        -- the lookup's source row (for chips and the popover)
  record_snapshot            jsonb null                     -- the enrich fields we display, as retrieved
  record_retrieved_at        timestamptz null
  fields                     jsonb not null default '{}'    -- see below
  default_approver_user_id   uuid null fk users.id on delete set null
  analytics_opt_out          bool not null default false
  onboarding_state           text not null default 'not_started' -- not_started | in_progress | finished | exited
  onboarding_step            smallint not null default 1    -- step to resume at
  onboarding_steps           jsonb not null default '{}'    -- {"1":"completed","2":"skipped",…}
  setup_prompt_dismissed_at  timestamptz null
  created_at, updated_at     timestamptz
  updated_by                 uuid null fk users.id on delete set null
  check (org_type in (…)), check (org_kind in (…)), check (onboarding_state in (…))
```

`fields` is a map from field key to one entry:

```jsonc
{
  "sector": {
    "value": "Transportation, logistics and storage",
    "origin": "record",              // record | stated
    "evidence_path": "basic_info.industries[0]", // record only: where in the snapshot it came from
    "as_of": "2026-11-01",           // record only: date of the underlying fact, or null
    "record_value": "Transportation, logistics and storage", // what the record said when shown; kept after an edit
    "confirmed_by": "…user id…",
    "confirmed_at": "2026-11-22T11:12:41Z"
  },
  "team_size_band": {
    "value": "201-500", "origin": "stated",
    "record_value": "51-200", "evidence_path": "headcount.total", "as_of": "2026-10-01",
    "is_estimate": true, "estimate_basis": "from professional profiles, not a payroll count",
    "confirmed_by": "…", "confirmed_at": "…"
  }
}
```

Field keys (allowlisted; the API rejects others):

| Group | Keys | Value shape |
| --- | --- | --- |
| Organisation | `org_name`, `one_line` | text (200, 160) |
| Record | `sector`, `sub_sectors`, `hq_city`, `hq_country`, `founded_year`, `team_size_band`, `stage`, `total_funding_usd` | text, text[], text, ISO country name, int, band enum, stage enum, number (read-only, record only) |
| Business | `revenue_band`, `raise_kind`, `raise_amount_band`, `raise_timing`, `raise_preferences` | enums, enum[]; always `stated` |
| Thesis | `thesis_sectors`, `thesis_geographies`, `thesis_company_type`, `thesis_size_min`, `thesis_size_max`, `thesis_ownership`, `thesis_deal_types`, `thesis_deal_size_band`, `thesis_must_haves`, `thesis_note` | text[], text[], enum, band, band, enum, enum[], enum, dimension key[] (the rest are preferences), text (400) |
| Approvals | `signs_as_name`, `signs_as_org` | text (200) |

Band enums reuse what exists: team-size bands are `EMPLOYEE_BANDS` from `pipelines/investors/profile.py` (`1-10` … `10001+`), stages are `STAGE_ORDER` (`pre_seed` … `series_f`) plus `bootstrapped` and `not_applicable`, funding kinds are the `FundingKind` values. Amount bands: `under_0_5m`, `0_5m_2m`, `2m_10m`, `10m_50m`, `over_50m` (USD; [§6](#6-open-decisions)).

Rules

- A `record` entry must have `record_source_id` set on the row and an `evidence_path`. A `stated` entry has neither requirement. This is "no source, no render" for the profile: the API never returns a `record` field it cannot back with the source row.
- `record_snapshot` holds only the enrich fields the profile displays (industries, categories, HQ, founded year, headcount and its date, funding rounds with dates and investors, description). It is public company data and is not confidential. It is what the `Your company` reference row and the "Invested in you" tag read from.
- `own_company_id` is set only when the user confirmed the match (`single` accepted by continuing, or `chosen`). `rejected` clears it and the snapshot.
- Per-user notification preferences are on the user, not the organisation: `users.notification_prefs jsonb not null default '{}'` with boolean keys `run_finished`, `approval_waiting`, `documents_received`, `source_unreachable`.
- `users` also gains `email_verified_at timestamptz null` and `role text not null default 'member'` (`owner` for the user who signed up; existing users become `owner` of their workspace when it has one user, else `member`). The role is used for one thing in this iteration: only an owner may delete the profile.

### 4.2 `org_profile_revisions` (edit history)

Append-only, added to `IMMUTABLE_MODELS`.

```
org_profile_revisions
  id            uuid pk
  profile_id    uuid fk org_profiles.id on delete cascade
  workspace_id  uuid fk workspaces.id
  version       int not null                    -- the profile version this revision produced
  changed_by    uuid null fk users.id on delete set null
  changed_at    timestamptz not null default now()
  reason        text not null                   -- onboarding | settings | autofill | autofill_refresh | delete_field
  changes       jsonb not null                  -- [{ "key": "team_size_band", "from": {value, origin}, "to": {value, origin} }]
  unique (profile_id, version)
```

Deleting the profile deletes its revisions (cascade), which is the one sanctioned removal from this immutable table; the deletion itself is written to the existing `deletion_records`.

### 4.3 Signup: rate limits and abuse protection

`POST /auth/signup`

```jsonc
// request
{ "display_name": "Asha Rao", "email": "asha@acmefreight.example", "password": "…",
  "organisation": "Acme Freight", "company_url": "", "invite_code": null }
// 201 → UserOut (extended, §4.4) and Set-Cookie: dp_session
// 409 { "detail": "An account with this email already exists." }
// 403 sign-up closed or bad invite code · 422 validation · 429 + Retry-After · 503 + Retry-After
```

In one transaction: create the workspace (name = organisation), the user (`role = owner`), an `org_profiles` row (`org_name` stated, `onboarding_state = in_progress`), a session, and the `signup.completed` event.

Settings (`AUTH_*`, in `auth/config.py`):

| Setting | Default | Meaning |
| --- | --- | --- |
| `signup_mode` | `closed` | `open`, `invite_code` or `closed`. The demo deployment sets `open`. Closed by default so a fresh deployment does not accept strangers by accident |
| `signup_invite_code` | empty | Shared code for `invite_code` mode, compared in constant time |
| `signup_max_per_ip` | 3 per hour | Accounts per client IP (or /64) per window |
| `signup_max_per_ip_day` | 10 | Same, per day |
| `signup_max_global_day` | 200 | All signups per day; trips to 429 for everyone |
| `signup_attempts_per_ip` | 20 per hour | All signup requests, successful or not, per IP |
| `workspace_starting_credits` | 300 | Total Crustdata credits a self-serve workspace may spend across all runs until an admin raises it |
| `onboarding_credit_budget` | 3 | Credits one workspace may spend on profile lookups per day, charged to the platform, not the workspace |

Protection, layer by layer

1. **Origin check.** The existing `OriginCheckMiddleware` already rejects cross-site POSTs; signup is covered with no change.
2. **Rate limits.** A second limiter instance built from the same `LoginRateLimiter` class (it is a keyed sliding-window counter; only the keys differ): keys `("signup_ip", ip)` hourly and daily, `("signup_attempt_ip", ip)` and `("signup_global",)`. Client IP comes from `client_ip_info`, and the per-IP keys count only when `ip_trusted` is true, exactly as login does. The same caveat applies: counts are per process, so limits multiply by instance count. Accepted for the demo; the global daily cap is additionally enforced by a `COUNT(*)` over `users.created_at` so it holds across instances.
3. **Argon2 cost.** Hashing the new password takes a slot from the existing `VerificationSlots`, so signups and sign-ins share one cap on concurrent Argon2 work and a flood of signups cannot starve sign-in beyond the 5-second wait and a 503.
4. **Honeypot.** A filled `company_url` returns the generic failure with no detail and is counted as an attempt.
5. **Spend is the real exposure.** A new account can start runs that cost Crustdata credits and model calls. `workspace_starting_credits` is a hard ceiling per self-serve workspace, checked in the recorder before each metered dispatch alongside the existing per-run budget (one more row to lock: the workspace's). When it is reached, runs stop with the existing budget-limit wording, and Settings shows `{used} of {allowance} credits used · ask us to raise it`. CLI-created workspaces have no ceiling unless one is set. Without this, open signup is an open tap on the Crustdata account.
6. **Duplicate emails.** 409 tells the caller the email is registered. A silent success would need a verification email to be honest, and the demo sends none. The disclosure is bounded by the attempt limit (20 per IP per hour) and reveals only that someone has an account. With email verification on, the response becomes a uniform "check your inbox" for both cases.
7. **No password oracle.** Signup with an existing email never checks or changes that account's password and never signs anyone in.
8. **Input limits.** The same lengths as the schema; the organisation name is stored as text and escaped on render; the website is parsed to a registrable domain and never fetched by our server (only passed to Crustdata as an identifier).

**Email verification** is off in the demo and stated as such here and on the privacy page. Production: signup sends a one-time link (a random token, stored hashed, 24-hour expiry, single use), the account works immediately but cannot approve a send or exceed 60 credits until `email_verified_at` is set, and unverified accounts with no runs are purged after 7 days. The schema already has the column so this is additive.

### 4.4 Interactions with auth

- **Session.** Signup creates a session through the same `create_session` and `set_session_cookie` as login, with the same absolute lifetime `AUTH_SESSION_TTL_HOURS` (24 hours by default in code; a deployment that wants a 7-day session sets 168). A session never extends itself. Onboarding state lives on the server, so an expired session costs the user a sign-in and nothing else.
- **Login limiter.** After a successful signup the API calls the login limiter's `succeeded` path for the (email, IP) pair, so the new user's first real sign-in from the same network is treated as a known pair and is not caught by a per-IP or global login trip. A signup never refunds or clears anyone's failed sign-in counts.
- **`GET /auth/me`** gains fields the shell needs on every load, so the web makes no second request:

```jsonc
{ "id": "…", "email": "…", "display_name": "Asha Rao",
  "role": "owner",
  "workspace": { "id": "…", "name": "Acme Freight" },
  "profile": { "org_type": "business", "org_kind": "startup", "acts_for": null,
               "version": 3, "onboarding_state": "in_progress", "onboarding_step": 3,
               "setup_prompt_dismissed": false },
  "internal_analytics": false }
```

- **Redirects.** `/welcome` joins `PROTECTED_PREFIXES` in `lib/api/proxy-rules.ts` and the `proxy.ts` matcher. After sign-in, a user whose `onboarding_state` is `in_progress` and who has no `next` parameter is sent to `/welcome`; with `exited` or `finished` to `/app`. A user is sent to `/welcome` automatically only until they finish or exit once; after that it is reachable only from Settings and the Overview panel. `/signup` with a valid session redirects to `/app`.
- **Fixture mode.** `fixtures.py` gains a fixture profile (business, with a record snapshot marked as illustration) and `signup` returns `fixtures.USER`, so the whole flow runs with `NEXT_PUBLIC_API_MODE=fixtures`.
- **CLI.** `create-user` gains `--role` and stays the way to add teammates. `create-workspace` creates an empty `org_profiles` row. No invite flow in this iteration.

### 4.5 Profile endpoints

All under `/profile`, all scoped to the signed-in user's workspace through `current_workspace_id`. There is no workspace id in any path.

| Method and path | Purpose |
| --- | --- |
| `GET /profile` | The profile: columns, `fields` with provenance, and for each `record` field a `SourceRef` so the web renders the standard chip. Creates the row lazily for old workspaces |
| `PATCH /profile` | Save changes. Body: `{ "base_version": 3, "reason": "onboarding", "set": { "sector": {"value": "…"} , … }, "clear": ["revenue_band"], "org_type": …, "org_kind": …, "acts_for": … }`. The server decides `origin`: a value equal to the current `record_value` is `record`, anything else is `stated`. 409 when `base_version` is stale, returning the current profile. Writes one revision |
| `POST /profile/onboarding` | `{ "step": 2, "outcome": "completed" \| "skipped" }`, `{ "exit": true }`, or `{ "dismiss_prompt": true }`. Advances `onboarding_step` and state |
| `POST /profile/autofill` | The lookup ([§4.6](#46-auto-fill-from-the-website)) |
| `POST /profile/autofill/choose` | `{ "crustdata_company_id": 123 }` from the candidates of the last lookup, or `{ "none": true }` |
| `GET /profile/history` | Revisions, newest first, with the changer's display name |
| `GET /profile/defaults` | Everything the screens pre-fill, computed in one place ([§4.7](#47-how-pipelines-read-the-profile)) |
| `DELETE /profile` | Owner only. Clears the row to its empty state, deletes revisions, writes a `deletion_records` row |
| `PATCH /auth/me/notifications` | The four notification booleans for the signed-in user |

Validation is by field key: enums are checked against their lists, text lengths against the table in [§4.1](#41-org_profiles), countries against the list `pipelines/discover/countries.py` already holds. `PATCH` accepts at most 40 keys. Write endpoints are limited to 60 requests per workspace per minute.

### 4.6 Auto-fill from the website

`POST /profile/autofill` `{ "website": "acmefreight.example" }`

1. Parse to a registrable domain. Reject IP addresses, localhost and anything without a public suffix (422). The server makes no request to the domain itself.
2. `identify_company(domains=[domain])` (0.2 credits per match; unmatched is free).
3. Decide the match:
   - exactly one result whose own domain equals the requested domain → `single`;
   - more than one → `multiple`, return up to five candidates (id, name, HQ, headcount estimate, domain) and stop;
   - none → `none`.
4. For `single` (or after `/autofill/choose`): `enrich_company(id)` with a reduced field list (basic info, taxonomy, headcount, funding, locations; 2 credits).
5. Write a `sources` row (`provider = "crustdata"`, `endpoint_or_url = "company_enrich"`, `source_class` = the class the case profile uses for the same record, `case_id = null`, `request` = the identifier used), store the trimmed `record_snapshot`, and return **suggestions**:

```jsonc
{ "match": "single",
  "company": { "crustdata_company_id": 123, "name": "Acme Freight Pvt Ltd", "domain": "acmefreight.example",
               "source": { …SourceRef… } },
  "suggestions": {
    "sector":         { "value": "Transportation, logistics and storage", "source": {…}, "as_of": "2026-11-01",
                        "evidence_path": "basic_info.industries[0]" },
    "team_size_band": { "value": "51-200", "source": {…}, "as_of": "2026-10-01", "is_estimate": true,
                        "estimate_kind": "estimate", "estimate_basis": "from professional profiles, not a payroll count",
                        "observed": 180 },
    "stage":          { "value": "series_a", "source": {…}, "as_of": "2025-06-03",
                        "basis": "latest dated round on record" },
    …
  },
  "absent": ["founded_year"],
  "candidates": [],
  "credits": 2.2, "from_cache": false }
```

Suggestions are **not** written to `fields`. They become profile values only when the user confirms step 2 through `PATCH /profile`. Until then the profile holds a snapshot and nothing asserted. This is what keeps the pre-fill honest in the data as well as on the screen: a value is in the profile because a named person confirmed it, with the time they did.

Derivations, all deterministic (no model call anywhere in onboarding):

| Field | From | Rule |
| --- | --- | --- |
| `sector` | first industry on the record | as given |
| `sub_sectors` | activity categories | first five |
| `hq_city`, `hq_country` | headquarters location | country normalised with the existing alias table |
| `team_size_band` | headcount total | mapped through `EMPLOYEE_BANDS`; always `is_estimate` |
| `stage` | funding rounds | the latest round **with a date**; undated rounds are ignored, as everywhere else |
| `total_funding_usd` | funding total | shown read-only |
| `one_line` | description | first sentence, cut at 160 characters on a word boundary |

Costs and limits

- About 2.2 credits per successful lookup, 0 when nothing matches. Calls go through the existing recorder and `api_cache`, so a second lookup of the same domain inside the cache window is free.
- The lookup is charged to a platform budget owner (`onboarding`), not to the workspace's starting credits. Capped by `onboarding_credit_budget` per workspace per day (one lookup and a retry), with a global daily cap of 300 credits. Over either cap the endpoint answers `{ "match": "not_run", "reason": "budget" }` and the screen shows the "not run" state.
- Rate limit: 5 lookups per workspace per hour.
- Failures map to `match: "failed"` with the allowlisted error code already used by `CallAttempt.error`.
- The lookup reads company data only. It does not search for people, the user's own profile or any contact detail.

### 4.7 How pipelines read the profile

One loader, one snapshot type, one place for rules:

```
app/profile/context.py
  @dataclass(frozen=True) ProfileContext:
      version, org_type, org_kind, acts_for, org_name, own_company_id,
      sector, sub_sectors, hq_country, team_size_band, stage,
      thesis: ThesisDefaults | None, raise_: RaiseDefaults | None,
      signs_as_name, signs_as_org, record: RecordSnapshot | None
  async def load_profile_context(db, workspace_id) -> ProfileContext | None

app/profile/defaults.py        # pure functions, unit-tested, no I/O
  thesis_draft(ctx) -> str | None            # the fixed sentence template
  criteria_split(ctx) -> dict[CriterionDimension, CriterionKind]
  investor_search_prefill(ctx) -> InvestorSearchIn | None
  signals_filter(ctx) -> {sectors, countries} | None
  first_actions(ctx) -> list[str]
  own_reference(ctx) -> ReferenceOut | None  # the "Your company" row, every value a Fact with its SourceRef
```

`GET /profile/defaults` returns the output of those functions, so the web holds no personalisation rules of its own:

```jsonc
{ "profile_version": 3,
  "thesis_draft": "Privately held warehousing and supply-chain software companies in India with 51 to 5,000 people. Regional operators with enterprise customers and recent expansion",
  "criteria_split": { "geography": "must", "ownership": "must", "industry_activity": "preference", "size": "preference" },
  "investor_search": { "sector": "Warehousing, third-party logistics", "location": "India", "stage": "series_a",
                       "size": "51-200", "funding_sought": "growth equity" },
  "use_own_company_available": true,
  "signals_filter": { "sectors": ["Warehousing", "Supply-chain software"], "countries": ["India"] },
  "first_actions": ["find_investors", "own_record"],
  "reference": { "name": {…Fact…}, "headcount": {…Fact, is_estimate…}, "headquarters": {…}, "latest_round": {…} },
  "signs_as": { "name": "Asha Rao", "organisation": "Finance, Acme Freight" } }
```

The thesis template, in full, so nobody is tempted to hand it to a model:

`{ownership} {sectors} companies in {geographies}{ with {size_min} to {size_max} people}.{ {note}}`

with "Companies" when ownership is "any", sectors joined with "and", and each optional clause dropped when its field is empty. An empty thesis yields `null` and the textarea stays empty.

Where each pipeline plugs in:

| Code | Change |
| --- | --- |
| `api/theses.py` (create) | Accepts optional `profile_version` and `from_profile: bool`, stored on the thesis. After criteria extraction, applies `criteria_split` and marks `origin = "profile"` on affected criteria |
| `pipelines/discover/steps.py` (shortlist) | Drops the candidate with `own_company_id`; records the count in the step output |
| `api/investors.py` (create) | Accepts `use_own_company: bool` and `profile_version`; stores both in `investor_runs.profile` beside the form values (the JSONB already exists) |
| `pipelines/investors/profile.py` | When `use_own_company`, adds the record's activity categories to the comparable search and uses the record's headcount for the band; the scope note states the basis |
| `pipelines/investors/service.py` (read) | Tags entries whose `investor_key` matches an investor on the profile's own dated rounds: `invested_in_you: { round_type, date, source }` |
| `api/cases_service.py` (read) | Adds `reference` (from `own_reference`) to the case's comparables section and to Compare's payload |
| `api/cases.py` (direct-verify criteria) | No change; the web seeds the editor from `/profile/defaults` |
| `pipelines/act/step.py` | Fills `sender_name` and `sender_organisation` from the context |
| `drafting/memo.py` | Header line `Prepared for {org_name}` |
| `db/models.py` `Run` | `profile_version int null`, set at creation when any profile default was used |

Every one of these reads the profile **at run creation** and stores what it used. No step handler loads the live profile, so a resumed or re-run step sees the same inputs and the same records under the same policy give the same assessment.

### 4.8 Analytics table and endpoints

```
analytics_events
  id            bigserial pk
  at            timestamptz not null default now()
  name          text not null                   -- allowlisted, §3.2
  workspace_id  uuid null fk workspaces.id on delete cascade   -- null only for signup.rejected
  org_type      text null                       -- the workspace's type when the event happened
  props         jsonb not null default '{}'     -- allowlisted keys per name; enums, bools, numbers only
  origin        text not null                   -- browser | server
  index (name, at), index (workspace_id, at)
```

No user id, no session id, no IP, no user agent, no URL, no referrer.

`POST /analytics/events` (signed-in only)

```jsonc
{ "events": [ { "name": "onboarding.step_completed", "props": { "step": 2, "duration_s": 48, "fields_filled": 7 } } ] }
// 202 always for a well-formed body; invalid events are dropped and counted, not echoed
```

- At most 20 events per request and 120 per workspace per minute; over that, 202 and drop.
- Each event is validated against a schema per name (`app/analytics/schema.py`): unknown name, unknown key, wrong type, a string value outside its enum, or a number outside its range → dropped. There is no string property that accepts arbitrary text, so content cannot be sent even by mistake.
- Dropped silently when the workspace has opted out or the request carries `Sec-GPC: 1` or `DNT: 1`.
- The server sets `at`, `workspace_id` and `org_type`. The browser cannot set them.
- The web sends with `navigator.sendBeacon` through the existing `/api` proxy, batched, fire-and-forget. A failed send is never retried and never surfaces to the user.

Server events are written by `app/analytics/record.py: record(db, name, workspace_id, **props)` inside the caller's transaction. It is fire-and-forget in the same sense as activity emission in D: a failure logs and never fails the request or the step.

`GET /internal/analytics/summary?days=30&org_type=` (users in `ANALYTICS_ADMIN_EMAILS` only; 404 otherwise) returns the aggregates the internal view draws: funnel counts, medians, pre-fill outcomes per field, per-type totals, and the derived figures from `runs`, `cases`, `approvals` and `cost_entries`. Any cell with fewer than five workspaces behind it returns counts without rates. Opted-out workspaces are excluded.

Retention: `db/retention.py` deletes `analytics_events` older than 180 days after rolling them into `analytics_monthly (month, name, org_type, key, value, count)`.

### 4.9 Migrations

One Alembic revision per table group, numbered after whatever is latest when the work starts (D adds an activities table; do not assume 0006):

1. `org_profiles`, `org_profile_revisions`, the three `users` columns, `runs.profile_version`, `theses.profile_version` / `from_profile`, `criteria.origin`, `workspaces.credit_allowance`. Backfill: an empty profile row per existing workspace with `onboarding_state = 'exited'` (they are not pushed into `/welcome`), `role = 'owner'` for single-user workspaces.
2. `analytics_events`, `analytics_monthly`.

---

## 5. Implementation plan

Three chunks with disjoint file ownership. Chunk 1's first slice is a contract: schemas, fixtures and the regenerated `openapi.json`. Once that is merged, chunks 2 and 3 run in fixture mode in parallel with the rest of chunk 1. Nobody edits a file they do not own; a needed change in someone else's file goes in the hand-off note.

Order of value, if time runs out: **signup → lookup and the step 2 confirm screen → investor form pre-fill → thesis draft pre-fill → Overview context line and empty states → request sign-off → reference row and "Invested in you" → signals filter → analytics view.** Each item is useful without the ones after it.

### Chunk 1 · Backend: signup, profile, auto-fill, analytics

Owner: backend agent. Owns everything under `apps/api/`.

| Slice | Files | Done when |
| --- | --- | --- |
| **1a Contract** (first, small) | `app/api/schemas/auth.py` (`SignupIn`, extended `UserOut`), `app/api/schemas/profile.py` (new), `app/api/schemas/analytics.py` (new), `app/api/fixtures.py`, `openapi.json` | The OpenAPI export has every endpoint in §4 and fixture mode answers all of them |
| **1b Signup** | `app/api/auth.py`, `app/auth/config.py`, `app/auth/ratelimit.py` (signup limiter factory), `app/auth/sessions.py` (`create_account`), `app/auth/cli.py` (`--role`, docstring), `app/db/models.py`, `alembic/versions/*_org_profiles.py`, `tests/auth/test_signup.py` | A new email gets a workspace, an owner, an empty profile and a session; duplicate, honeypot, closed mode and each limit are tested; a signup flood cannot take more Argon2 slots than login allows |
| **1c Profile and auto-fill** | `app/profile/__init__.py`, `context.py`, `defaults.py`, `autofill.py`, `service.py` (new package), `app/api/profile.py` (new), `app/api/router.py`, `tests/profile/*` | Lookup returns sourced suggestions for a known domain, candidates for an ambiguous one and honest states for none, failed and over-budget; `PATCH` sets `origin` correctly, bumps the version and writes a revision; `defaults.py` is covered by table-driven tests including the empty profile |
| **1d Workspace credit ceiling** | `app/db/ledger.py`, the recorder's reservation path, `app/settings.py`, tests | A self-serve workspace cannot reserve past its allowance; the run stops with the existing budget wording |
| **1e Pipeline reads** | `app/api/theses.py`, `app/api/investors.py`, `app/api/cases_service.py`, `app/pipelines/discover/steps.py`, `app/pipelines/investors/profile.py`, `service.py`, `app/pipelines/act/step.py`, `app/drafting/memo.py` | Each row of the table in §4.7 has a test showing the profile value used and a test showing the no-profile behaviour unchanged; a finished run's output does not change when the profile is edited afterwards |
| **1f Analytics** | `app/analytics/__init__.py`, `schema.py`, `record.py`, `summary.py`, `app/api/analytics.py`, `alembic/versions/*_analytics_events.py`, `app/db/retention.py`, `tests/analytics/*` | Unknown names and keys are dropped; no event row can hold free text; the summary suppresses small cells; opted-out workspaces are absent |

1b and 1c are the value. 1d must land before the deployment sets `AUTH_SIGNUP_MODE=open`. 1e and 1f can follow in either order.

### Chunk 2 · Frontend: signup and onboarding

Owner: frontend agent 1. Starts when 1a is merged.

| File | Change |
| --- | --- |
| `apps/web/app/signup/page.tsx`, `signup-form.tsx` (new) | The signup page, mirroring `app/login` |
| `apps/web/app/login/page.tsx`, `login-form.tsx` | Subtitle and the "Create an account" line; post-login redirect by onboarding state |
| `apps/web/app/(onboarding)/layout.tsx`, `welcome/page.tsx` (new) | The frame: header, step header, sticky action row |
| `apps/web/components/onboarding/` (new): `onboarding-flow.tsx`, `step-about.tsx`, `step-record.tsx`, `step-looking-for.tsx`, `step-approvals.tsx`, `sourced-field.tsx`, `match-picker.tsx`, `must-have-rows.tsx`, `privacy-table.tsx` | The four steps and their parts. `sourced-field.tsx` is the row with control, chip, "Stated by you" and `Restore`, and is the one component chunk 3 and Settings reuse |
| `apps/web/lib/api/profile.ts`, `lib/profile.tsx` (new) | Client functions and `ProfileProvider` / `useOrgProfile()` / `useProfileDefaults()`, read once per session from `/auth/me` and `/profile/defaults` |
| `apps/web/lib/analytics.ts` (new) | `track(name, props)`: typed by event name, batched, `sendBeacon`, no-op when opted out or in fixture mode |
| `apps/web/lib/api/proxy-rules.ts`, `apps/web/proxy.ts` | `/welcome` protected; `/signup` redirects to `/app` when signed in |
| `apps/web/components/marketing/content.ts`, `sections.tsx` | `Sign up` in nav, hero, closing band and mobile menu, with the cookie rule |
| `apps/web/app/(app)/app/settings/settings.tsx`, `components/settings/org-profile-panel.tsx` (new) | The Organisation profile panel, history, look up again, delete |
| `apps/web/app/design/gallery.tsx` | Each step-2 state (looking up, found, several, none, failed) and both step-3 forms, from fixtures |
| `docs/content/app-microcopy.md` | New §19 with every string in §1 and §2.4 |

Done when: in fixture mode and against the real API, a new visitor can sign up, see their organisation's record with chips, change one value and see it become "Stated by you", skip any step, leave and resume, and edit everything in Settings. Keyboard-only and at 360px wide.

### Chunk 3 · Frontend: personalisation wiring

Owner: frontend agent 2. Starts when 1a and chunk 2's `lib/profile.tsx` and `sourced-field.tsx` are merged. Owns the feature directories; in this order.

| # | File | Change |
| --- | --- | --- |
| 1 | `components/ui/profile-note.tsx` (new) | `From your profile · Edit` |
| 2 | `components/investors/profile-form.tsx`, `search-view.tsx` | Form pre-fill, section label, `use_own_company` toggle, scope note |
| 3 | `components/discover/thesis-form.tsx`, `new-thesis.tsx`, `criteria-editor.tsx` | Thesis draft, variation chips, `From your profile` on criteria rows |
| 4 | `components/dashboard/dashboard.tsx` (Overview), `components/app-shell/sidebar-nav.tsx`, `nav.ts`, `command-menu.tsx`, `top-bar.tsx` | Context line, first actions, setup prompt panel, `New` menu order, workspace name |
| 5 | Empty states in `components/dashboard`, `components/discover/thesis-list.tsx`, `components/investors/searches-list.tsx` | The table in §2.5 |
| 6 | `components/case/new-case-form.tsx`, the case criteria editor, Request tab sign-off preview | Default thesis seeding; sign-off shown from the draft |
| 7 | `components/case/comparables-tab.tsx`, `app/(app)/app/compare/*` | `Your company` reference row and column |
| 8 | `components/investors/shortlist.tsx`, `investor-detail.tsx`, `components/discover/shortlist.tsx`, `shortlist-card.tsx` | `Invested in you` tag, default filter chips, own-company removed count, `Relative to you` line |
| 9 | `app/(app)/app/signals/*`, `app/(app)/app/approvals/*`, `lib/workspace.ts` | Default filter chips |
| 10 | `app/(app)/app/internal/analytics/page.tsx` (new), `components/internal/analytics-view.tsx` (new) | The internal view |
| – | `track()` calls for `defaults.used`, `defaults.filter_removed`, `first_action.clicked` at each site above | – |

Done when: with the business fixture profile and the investor fixture profile, every row of §2.2 shows its tailored state with a `ProfileNote`; with no profile every screen is pixel-identical to today; no screen shows a profile-derived value without either a source chip or "Stated by you".

### Shared rules

- No new dependency in either app. Everything here is built from primitives that exist.
- Fixture mode covers every state, including the dishonest-looking ones we must not ship: a test asserts that a `record` field without a `SourceRef` fails to render.
- The acceptance check that matters most: edit the profile after a run finishes, reload the run, and nothing in it has changed.

---

## 6. Open decisions

1. **Open signup on the demo deployment.** Recommended: `invite_code` for the public URL (the code is on the ContextCon slide and in the pitch), `open` only if 1d (the workspace credit ceiling) has landed. `open` without the ceiling lets anyone spend the Crustdata balance.
2. **Starting credits per self-serve workspace.** Proposed 300 (two full cases, or one screening, one investor search and a case). Lower is safer; too low and nobody reaches a finished case.
3. **Currency for amount bands.** Proposed USD bands, because every funding amount on record is in USD and mixing currencies would need a conversion rate DealProof has no source for. The first customer is Indian; the alternative is INR crore bands for display with a stated, dated rate, which adds an unsourced number to the product.
4. **Duplicate-email wording.** Proposed: say the account exists (honest and useful, bounded by rate limits). Alternative: a uniform response, which only becomes honest once verification email is on.
5. **Teammates.** Out of scope here: the CLI still adds users to a workspace. An invite link is the natural next step and would make the approver select in step 4 meaningful for more than one person.
6. **Advisers with several clients.** This design gives an adviser one default mandate. Per-client profiles (a profile attached to a thesis or an investor search rather than to the workspace) are a larger change to the data model; say if the first adviser customer needs it.
7. **`use_own_company` default.** Proposed on for a business with a confirmed match, off for advisers. It changes which comparables are found, and so which investors appear, which is the point; the scope note states the basis either way.
8. **Usage data default.** Proposed on, with the checkbox visible in step 4. The stricter alternative is off by default, which will leave the funnel nearly empty.
9. **Who sees the internal analytics view.** Proposed an env allowlist of emails. Alternative: no view in the app at all, only a CLI report, which removes an internal route from a customer-facing deployment.
