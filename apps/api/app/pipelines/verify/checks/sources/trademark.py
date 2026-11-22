"""Trademark and IP claims ("PALMS(TM) is a registered trademark of X"): the register.

Two lookups at most (policy.MAX_LOOKUPS_PER_CLAIM), the second only when the first
found no register entry:

1. `"<company>" "<mark>" trademark`, with trademark register pages recognised by host.
2. The same terms on one registry mirror (`site:`).

A register page found through web search is a copy of the register's record, so it
is `registry_mirror` (adequate for the mark and its owner, like an exchange filing
copy). It counts only when one entry on the fetched page (split at "Trademark:" /
"Mark:" labels; a page without one is not read as an entry) has the mark as its
labelled mark, exactly one owner-type field whose value is the confirmed company's
name, a class and a labelled registered status (`register_entry_problem`), AND the
page carries a second identifier (the proprietor's address city or the domain) like
any page. Other pages are kept as searched sources; the company's own "registered
trademark" line is a company announcement, which the rules cap at partially
corroborated.

Only public terms go out: the confirmed company name, the mark from the claim's
structured `trademark` component (checked by `query.clean_entity`), fixed words.
"""

from __future__ import annotations

import re

from app.domain.enums import SourceReliability
from app.domain.types import Claim
from app.pipelines.verify.checks.gather import CheckEnv, Gathered, Lookup, run_lookups
from app.pipelines.verify.checks.query import PublicTerms
from app.rules.compare import normalize_text

R = SourceReliability

# Trademark registers and sites that republish their entries (proprietor, mark,
# class, status). Matched on the exact host (`gather.on_party_site`).
REGISTER_HOSTS = (
    "ipindia.gov.in",
    "tmrsearch.ipindia.gov.in",
    "ipindiaonline.gov.in",
    "tsdr.uspto.gov",
    "tmsearch.uspto.gov",
    "euipo.europa.eu",
    "branddb.wipo.int",
    "quickcompany.in",
    "trademarkia.com",
    "trademarking.in",
    "trademarks.justia.com",
    "tmdn.org",
)
# The mirror the second lookup is restricted to.
SITE_LOOKUP = "quickcompany.in"

_MARK_SIGNS = re.compile("[™℠®©]")
_CLASS = re.compile(r"\bclass(?:es)?\s*(?:no\.?|number)?\s*[:#-]?\s*\d{1,2}\b", re.IGNORECASE)


def clean_mark(value: object) -> str | None:
    """The mark as a lookup term: the component's value without TM/(R) signs."""
    if value is None:
        return None
    return " ".join(_MARK_SIGNS.sub(" ", str(value)).split()) or None


# The current proprietor's field, at the start of a line or cell ("Proprietor:",
# "Registrant name:", "Owner:"); "Previous owner:" or "Assignor:" never match.
_PROPRIETOR = re.compile(
    r"(?:^|[\n|])[ \t]*(?:proprietor|registrant|owner)(?:'s)?(?:[ \t]+name)?[ \t]*[:\-][ \t]*"
    r"([^\n|;]{2,200})",
    re.IGNORECASE,
)
# Where a field's value ends: the next "Label:" on the same line.
_NEXT_LABEL = re.compile(r"[.,]?\s+(?=[A-Z][A-Za-z ]{0,30}:)")
# Any owner-type label, anywhere: a second one in an entry (even inline, as a
# co-proprietor) makes the entry not the company's alone.
_ANY_OWNER_LABEL = re.compile(
    r"(?<!previous )(?<!former )\b(?:proprietor|registrant|owner|applicant|assignee)(?:'s)?"
    r"(?:\s+name)?\s*[:\-]",
    re.IGNORECASE,
)
# The label that starts one register entry, with its value ("Trademark: PALMS",
# "Word Mark: PALMS"). The page is split at these; a page without one is not read as
# an entry at all.
_ENTRY_START = re.compile(
    r"(?:^|\n)[ \t]*(?:trade\s*mark|word\s*mark|mark)(?:\s+name)?[ \t]*[:\-][ \t]*([^\n|]{1,120})",
    re.IGNORECASE,
)
# One entry is short: the mark, its proprietor, class and status sit together.
_ENTRY_MAX = 1500
_STATUS = re.compile(r"(?:^|[\n|])[ \t]*status[ \t]*[:\-][ \t]*([^\n|]{1,80})", re.IGNORECASE)
# A "registered trademark" claim needs a registered entry; these statuses are not one.
_NOT_REGISTERED = re.compile(
    r"\b(?:objected|opposed|abandoned|refused|withdrawn|pending|expired|removed|cancelled|"
    r"canceled|formalities|advertised|examination|application)\b",
    re.IGNORECASE,
)
_REGISTERED = re.compile(r"\bregistered\b", re.IGNORECASE)


def proprietor_is(value: str, owner: str) -> bool:
    """The labelled field's value, up to the next label, is exactly `owner`."""
    raw = _NEXT_LABEL.split(value, maxsplit=1)[0]
    return bool(normalize_text(owner)) and normalize_text(raw) == normalize_text(owner)


def entries(text: str) -> list[tuple[str, str]]:
    """(labelled mark, entry text) for each entry on the page, each at most
    `_ENTRY_MAX` characters long."""
    starts = list(_ENTRY_START.finditer(text))
    out = []
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        label = _NEXT_LABEL.split(m.group(1), maxsplit=1)[0]
        out.append((label, text[m.start() : min(end, m.start() + _ENTRY_MAX)]))
    return out


def register_entry_problem(text: str, mark: str, owner: str) -> str | None:
    """None when the fetched page `text` holds ONE registered entry whose labelled
    mark is `mark`, whose only owner-type field is exactly the confirmed company's
    name, and which states a class and a labelled registered status."""
    if not text.strip():
        return "register page not read"
    if not owner:
        return "no confirmed company name"
    found = entries(text)
    if not found:
        return "not a register entry (no labelled mark)"
    problem = "no entry for the mark"
    for label, entry in found:
        if normalize_text(label) != normalize_text(mark):
            continue
        fields = [m.group(1) for m in _PROPRIETOR.finditer(entry)]
        if not any(proprietor_is(f, owner) for f in fields):
            problem = "no proprietor field naming the confirmed company"
            continue
        if len(_ANY_OWNER_LABEL.findall(entry)) != 1:
            problem = "the entry names more than one owner"
            continue
        if not _CLASS.search(entry):
            problem = "states no trademark class"
            continue
        status = _STATUS.search(entry)
        value = status.group(1) if status else ""
        if not _REGISTERED.search(value) or _NOT_REGISTERED.search(value):
            problem = f"not a registered entry (status: {value.strip() or 'none'})"
            continue
        return None
    return problem


def plan(mark: str) -> list[Lookup]:
    def entry(text: str, terms: PublicTerms) -> str | None:
        return register_entry_problem(text, mark, terms.company_name)

    def lookup(label: str, site: str | None = None) -> Lookup:
        return Lookup(
            label=label,
            words="trademark",
            entity=mark,
            site=site,
            party_hosts=REGISTER_HOSTS,
            party_class=R.REGISTRY_MIRROR,
            focus=(mark, "class", "proprietor"),
            party_check=entry,
        )

    return [
        lookup(f"trademark register pages for {mark}"),
        lookup(f"{mark} on {SITE_LOOKUP}", site=SITE_LOOKUP),
    ]


def _found_entry(out: Gathered) -> bool:
    return any(f.evidence.source.reliability is R.REGISTRY_MIRROR for f in out.facts)


async def gather(env: CheckEnv, claim: Claim) -> Gathered:
    from app.jobs import BudgetExceeded

    out = Gathered(entity_ids=[env.company_entity])
    comps = {c.name: c.value for c in claim.components}
    mark = clean_mark(comps.get("trademark"))
    if mark is None or env.crustdata is None or env.llm is None:
        out.searched.append(
            {
                "label": "trademark register pages",
                "query": None,
                "results": [],
                "skipped": "no_mark" if mark is None else "source_unavailable",
            }
        )
        return out
    first, second = plan(mark)
    await run_lookups(env, claim, [first], out)
    if _found_entry(out) or out.searched[-1]["skipped"] == "identity":
        return out
    try:
        await run_lookups(env, claim, [second], out)
    except BudgetExceeded:
        out.searched[-1]["skipped"] = "budget"
    return out
