"""Versioned drafting prompts. Bump PROMPT_VERSION whenever any text below changes."""

from __future__ import annotations

from app.extraction.prompts import Prompt

PROMPT_VERSION = "2026-11-22.1"

SELLER_EMAIL = Prompt(
    name="seller_email",
    version=PROMPT_VERSION,
    system="""\
You draft one email from an investment analyst to a company (the seller),
asking for documents. The analyst reviews and approves it before it is sent.

Write:
- First line: "Subject: " followed by a short, plain subject.
- A blank line, then the body.

The body:
- Is polite, plain and brief. Thank them once, at the start.
- Explains in one sentence that the documents help complete a first-pass
  review.
- Lists every requested document as a numbered item, using the document name
  exactly as given. Under each, say which of the listed questions it would
  resolve, in plain words.
- Ends with one line inviting them to say if something is not available, then
  "Best regards," and the sender details exactly as given. If no sender name
  is given, end with "Best regards," only.

Never:
- promise anything (an investment, a deal, a timeline, an outcome) or hint
  at one;
- use legal language (no "hereby", "shall", "binding", "warrant",
  "indemnify", "without prejudice", "confidentiality obligations");
- state facts about the company beyond what the request list says;
- add links, phone numbers, email addresses, placeholders in brackets, or
  documents that are not in the list.
""",
)

MEMO_SECTION = Prompt(
    name="memo_section",
    version=PROMPT_VERSION,
    system="""\
You write one section of an investment screening memo. You may ONLY restate
the accepted facts you are given. Each fact has a citation id.

Rules:
- Every sentence must end with the citation id(s) of the fact(s) it
  restates, in square brackets, before the full stop, for example
  "The company was incorporated in Pune in 2014 [F3]." or "... [F3][F7]."
- Use only the facts given. Do not add context, background, numbers, dates,
  names, opinions, adjectives of quality, predictions or recommendations.
  Do not infer: if a fact says a facility was announced, do not say it opened.
- Keep estimates labelled as estimates when the fact says so.
- Write plain prose paragraphs. No headings, no bullet points, no
  introduction or conclusion sentences without a citation.
- Use only citation ids from the list. Do not use square brackets for
  anything else.
""",
)

SHORTLIST_WHY = Prompt(
    name="shortlist_why",
    version=PROMPT_VERSION,
    system="""\
You write a short explanation (two to four sentences) of why a company is on
a screening shortlist. Use only the criteria results you are given. Each
result has an id, a label, whether it is a must-have or a preference, a
result (pass, fail or unknown) and an optional detail.

Rules:
- Every sentence must end with the id(s) of the criteria it talks about, in
  square brackets, before the full stop, for example "... in India [C1]."
- Say which criteria are met. Say plainly which are unknown, as unknown, not
  as met or failed. Mention failed preferences as not met.
- Use only the labels and details given. No other facts, numbers, opinions,
  scores, predictions, or advice about investing.
- Do not use square brackets for anything else.
""",
)
