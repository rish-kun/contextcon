# DealProof live demo script (ContextCon, 4 minutes)

Total runtime: **4:00**. Target pacing: calm, factual, unhurried. Speak in short sentences. Let the evidence on screen do the work.

Placeholders in `{braces}` refer to the named real company, thesis, and accounts from the deployed showcase run. Fill them in during rehearsal so every name and number spoken matches the screen exactly.

---

## Pre-demo setup (2 minutes before going on stage)

1. Confirm `EMAIL_SEND_ENABLED=false` (the `Test mode` badge is visible in the top bar).
2. Confirm two browser tabs are ready:
   - **Tab 1:** Public home page (`/`) scrolled to the top.
   - **Tab 2:** Pre-run showcase case (`/app/cases/{showcase_case_id}`) ready in case of a slow network call.
3. Have credentials ready for two workspace accounts:
   - Analyst account (`{analyst_email}`)
   - Manager account (`{manager_email}`)
4. Copy the live thesis string to the clipboard:
   `Privately held Indian warehousing and supply-chain software companies that serve enterprise customers and show recent expansion`
5. Decide whether to leave sound `Off` or set to `Run finished` depending on room audio. Never rely on audio cues.

---

## Beat 1 · The home page: one real run (0:00 – 0:45)

**Screen:** Tab 1 (`/`).

**Do:**
- Pause for 3 seconds on the cover: headline on the left, mono docket on the right.
- Click `Read the file` and scroll steadily past Exhibit 1 (thesis to criteria), Exhibit 2 (the sieve reordering and ranked shortlist), Exhibit 3 (identity keys), into Exhibit 4 (the claim ledger).
- Stop on one `Supported` row and one `Cannot verify` row. Click one source chip to open the evidence popover.
- Scroll down to Exhibit 5 so the disposition stamp settles into the pinned case bar, glance past Exhibit 6 (unsigned request) and the bill at the bottom.

**Say:**
> "DealProof is an AI analyst for M&A advisers and corporate development teams. It takes an investment thesis, finds real companies, checks their claims against independent records, and produces a screening case a decision-maker can defend.
>
> Our home page is not a product tour. It is one finished screening run on a real Indian company, `{showcase_company}`, pulled from public records and its public website.
>
> Notice the order. Plain-English thesis turned into must-haves and preferences. A shortlist showing how many companies were dropped and why. Identity confirmed on keys before attaching a single record.
>
> In the claim ledger, every fact ends in a source and a date. Click any source to inspect the excerpt and retrieval time. And where public records are silent, DealProof says `Cannot verify` and names the exact document that would settle it.
>
> The disposition stays blank in the top bar until you reach the evidence. At the bottom, the page prints its own bill in credits and model spend."

---

## Beat 2 · Log in as the analyst (0:45 – 1:00)

**Screen:** Click `Log in` in the top navigation.

**Do:**
- Sign in with `{analyst_email}` (the analyst account).
- Land on `/app` (`Overview`).
- Point briefly at the sidebar (`Workspace` and `Research` groups), the `Needs you` panel, and the `Test mode` badge in the top bar.

**Say:**
> "Now let us open the workspace. I am signing in as the analyst. Every action is tied to a signed-in user, and you can see `Test mode` in the top bar so nothing leaves DealProof during this demo.
>
> Overview shows the book of work: cases by disposition, what needs attention, and total credits and model spend kept strictly separate."

---

## Beat 3 · Start a thesis, watch the live run, inspect the shortlist (1:00 – 1:55)

**Screen:** Click `New` → `New screening` (`/app/discover`).

**Do:**
- Paste the thesis:
  `Privately held Indian warehousing and supply-chain software companies that serve enterprise customers and show recent expansion`
- Click `Turn into criteria`.
- Pause 3 seconds on Step 2 (`Criteria`): point at the split between `Must have` and `Preference`, and the `Assessed from` column (`Company record`, `Evidence`, `Signal`). Note that nothing has run yet and the user can edit any row.
- Click `Search`.
- **While the live run is working (point at four things in order):**
  1. **Header band:** the plain-language NOW line (`Searching companies matching {n} criteria`, `Reading job postings for {company}`), elapsed clock, and segmented credit meter.
  2. **Left column (Steps):** checklist items ticking off with real counts and credit costs.
  3. **Right column (From Crustdata + Sources):** live tally of matched and enriched companies, plus source rows arriving with domains and timestamps.
  4. **Centre column (Candidates):** companies arriving, must-have failures folding into the dropped group with stated reasons, enrichment marks settling, and a single rank reorder when scoring finishes.
- Once settled (or as candidates populate), point at one shortlisted row: `Fit {score} · {pct}% of criteria assessable`, headcount marked `Estimate`, hiring marked `Signal`.

**Say:**
> "Let us run a live screening for our logistics client. We paste the thesis in plain words and turn it into editable criteria. Must-haves are separate from preferences, and nothing spends a credit until we approve the criteria and press Search.
>
> While it runs, you see real work as it happens. At the top, the now line names the exact call in flight next to the clock and credit meter. On the left, each step checks off with its cost. On the right, the Crustdata tally counts every company matched and enriched, and the source ticker logs each record read.
>
> In the middle, candidates arrive, must-have failures drop with their stated reason, and once scoring finishes the list orders once into a shortlist. Notice every fit score sits next to how much of the thesis was assessable, and hiring is labelled `Signal`, never revenue."

---

## Beat 4 · Open the showcase case: ledger, evidence, five judgments, version diff (1:55 – 2:55)

**Screen:** Open `Companies` → click `{showcase_company}` (the pre-run showcase case with two assessment versions).

**Do:**
- Start on the `Claims` tab.
  - Point at the two-sided ledger (`Seller said` / `The company's website says` vs `The record shows`).
  - Point at one `Supported` claim, one `Partially corroborated` claim (showing `Supported` and `Not supported` parts), and one `Cannot verify` claim ending in `What would settle it`.
  - Click a source chip to open the evidence popover; point at the quote, reliability class in words, as-of date, retrieved timestamp, and identity key match.
- Switch to the `Assessment` tab.
  - Point across all **five separate judgments**:
    1. `Opportunity fit` (score + assessable share)
    2. `Evidence sufficiency` (settled vs open vs not checked)
    3. `Business assessment` (operating signals and estimates)
    4. `Financial assessment` (`Not assessed · No reliable financial inputs`, hatched)
    5. `Screening disposition` (rule-driven stamp under `Policy 1.0`, resting on named claim numbers)
- Scroll to `Assessment history` and click `Compare v1 and v2` (or open `What changed in v2`).
  - Point at the public document attached after v1, the status transition (`{old_status} → {new_status}`), and the `Because:` line with its source chip.

**Say:**
> "Now let us open a completed case on `{showcase_company}`.
>
> First, the claim ledger. Every claim sits opposite what independent records show. When a source supports only part of a claim, DealProof splits what is supported from what is not. Click any chip to read the exact excerpt, source class, and retrieval date.
>
> Next, the Assessment tab. DealProof never blends everything into one opaque score. Five judgments stay apart: opportunity fit with assessable share, evidence sufficiency, operating signals, financial assessment — clearly hatched as `Not assessed` because private accounts are not public — and the screening disposition decided by deterministic rules under Policy 1.0.
>
> Finally, new evidence updates the case in the open. After we attached `{public_document_name}`, version 2 recorded exactly which claim changed, from what status to what status, and why, while keeping version 1 intact."

---

## Beat 5 · Approval inbox: sign in as manager and approve in test mode (2:55 – 3:25)

**Screen:** Open the case's `Request` tab (or `Approvals` in the sidebar).

**Do:**
- Point out the draft request list mapped back to the open claims (`← claim {n}`) and the empty `To` field ("DealProof does not suggest or collect personal contact details").
- Open the user menu → `Sign out`.
- Sign in with `{manager_email}` (the manager account).
- Click `Approvals` in the sidebar (point at the mono count beside it) → click `Review` on `{showcase_company}`.
- Enter a test recipient address (e.g. `demo-review@example.com`).
- Click `Approve (test mode, nothing is sent)` → confirm `Record approval`.
- Point at the permanent hatched receipt: `Suppressed (test mode) · not sent`, `Approved by {manager_name}`, timestamp, and the disabled send button.

**Say:**
> "Every unsettled claim generates a specific document request, but nothing leaves DealProof on its own.
>
> I will sign out as the analyst and sign in as the manager. In the Approvals inbox, the request is waiting. Notice there is no bulk approve — each send is one explicit decision.
>
> I enter the recipient myself, because DealProof does not scrape personal contact details, and approve in test mode. DealProof records the named approver and timestamp, locks the request so it can never be sent twice, and marks the receipt `Suppressed (test mode) · not sent`."

---

## Beat 6 · Investors: the other direction (3:25 – 3:45)

**Screen:** Click `Investors` in the sidebar → open the pre-run investor search for the warehousing software sector.

**Do:**
- Click the top ranked investor in the left pane to populate the right detail pane.
- Point at the dated `Comparable rounds` table, the round axis, `Why they fit`, `Unknown`, and any `Possible duplicate · not merged` flag.
- Point at the footer caveat line.

**Say:**
> "DealProof also works in the other direction for a business raising capital. Given sector, location, and stage, it finds comparable companies that raised money and ranks investors strictly by dated funding records.
>
> Every investor entry shows the exact rounds behind it, what is unknown, and possible duplicates kept unmerged. And as the footer states, past investments are a record, never a prediction."

---

## Beat 7 · Closing line (3:45 – 4:00)

**Screen:** Stay on the app or switch cleanly back to the showcase case header.

**Say:**
> "Every investment or acquisition opportunity that reaches a decision-maker should arrive with its claims already checked and its unknowns already named.
>
> DealProof does that first-pass screening in minutes, keeps every source and date attached, and never hides a gap. Thank you."

---

## Fallback plan if a live call is slow

Never stall on stage or apologise for a waiting screen. Use these exact triggers and switches.

### Trigger A · Live `Search` in Beat 3 takes more than 15 seconds to return first results

1. **At 8–15 seconds:** Point to the NOW line (`· {seconds} s` or `· still waiting on Crustdata`) and say:
   > "Crustdata is taking a moment on this live query. Notice DealProof shows the real wait clock and provider name rather than faking progress."
2. **At 20 seconds (if still waiting):** Leave the live run running in its tab. Click `Screenings` in the sidebar, open the pre-run showcase screening, and click `Run log` → `Replay · 8×`.
3. **Read the replay banner aloud so everything stays honest:**
   > "While that live query finishes in the background, here is the 8× replay of our recorded run on the same thesis. As the banner says, this is a replay and no credits are being spent."
4. Let the replay show the Crustdata tally, sources ticker, and shortlist rank reorder for 15 seconds, then continue directly to Beat 4 on the showcase case.
5. Check back on the live tab only if time remains at the end.

### Trigger B · Credit budget is reached mid-demo

- Treat it as a proof point. Point at the hatched `Budget reached` meter and any `Not checked · budget reached` rows and say:
  > "This run hit its credit cap. Instead of silently dropping checks or marking them clean, DealProof hatches them as `Not checked · budget reached` so the analyst knows exactly what did not run."

### Trigger C · Network drop or API error during login or page navigation

1. Point at the neutral error state (`{Thing} did not load` + `Try again`) and click `Try again` once.
2. If the connection does not recover within 5 seconds, switch to **Tab 1** (the statically built home page, which needs no live API) and walk through Exhibits 1 through 7 and the bill directly. Every artifact in Beats 1, 3, 4, 5, and 6 is present on that page with real data and working source popovers.

### Trigger D · Running short on time (past 3:15 before Beat 5)

- Skip signing out and back in for Beat 5: approve from the currently signed-in account, state clearly that a separate manager account can hold approval rights, and spend 10 seconds on Beat 6 (`Investors`) so Beat 7 lands cleanly before 4:00.
