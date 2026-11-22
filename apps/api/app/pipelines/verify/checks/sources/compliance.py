"""Certifications and compliance (ISO 9001, ISO 27001, SOC 2, CMMI, PCI DSS, HIPAA, GDPR):
the certification body's or registry's record first, then the company's own page.

Two lookups at most (policy.MAX_LOOKUPS_PER_CLAIM):

1. Certification record: `"<company>" <standards> certificate`. Accreditation
   registers (IAF CertSearch and similar), certification bodies and auditors are
   recognised by host; their page about the company is `counterparty_confirmation`.
2. The company's trust or security page: `"<company>" certified site:<domain>` (or
   `"<company>" <standards> certified` without a domain). Skipped when the first
   lookup already reached a certifier's or registry's page about the company.

Only public terms go out: the confirmed company name and domain, each standard's
public name as `app.rules.standards` reads it from the structured `certification`
component ("ISO 27001", "SOC 2"; never the claim's wording), and fixed words.

A register or certifier page counts only when it names the company with a second
identifier (domain, or HQ city outside the name), like any page. The rules then check
each standard and the certificate's validity (`certificate_valid_until`, on or after
today): a register showing the standard and a current expiry gives Supported, an
expired one Contradicted; the company's own page alone gives Partially corroborated
(an expired date there is shown, but cannot settle it). Copies of one announcement
share an origin and count once. Would settle it: the certificate itself, or the
auditor's report under NDA (`policy.DOC_CERTIFICATION`).
"""

from __future__ import annotations

from app.domain.enums import IdentityStatus, SourceReliability
from app.domain.types import Claim, ClaimComponent
from app.jobs import BudgetExceeded
from app.pipelines.verify.checks.gather import CheckEnv, Gathered, Lookup, run_lookups
from app.rules.claim_status import effective_components
from app.rules.standards import Standard, standards_in

R = SourceReliability

MAX_STANDARDS = 3  # standards named in one query

# Accreditation registers and certification bodies or auditors: their page about the
# company is the certifier's own record of the certificate.
CERTIFIER_HOSTS: tuple[str, ...] = (
    # Accreditation registers
    "iafcertsearch.org",
    "cmmiinstitute.com",  # CMMI Published Appraisal Results
    "ukas.com",
    "anab.ansi.org",
    "nabcb.qci.org.in",
    "jas-anz.org",
    # Certification bodies
    "bsigroup.com",
    "tuv.com",
    "tuvsud.com",
    "tuv-nord.com",
    "tuvaustria.com",
    "dnv.com",
    "sgs.com",
    "bureauveritas.com",
    "intertek.com",
    "lrqa.com",
    "ul.com",
    "kiwa.com",
    "dekra.com",
    "nqa.com",
    # SOC 2 / PCI DSS auditors
    "a-lign.com",
    "schellman.com",
    "coalfire.com",
)

_STRONG = frozenset({R.COUNTERPARTY_CONFIRMATION.value, R.REGISTRY.value})
_FOCUS = ("certif", "valid", "expir", "scope", "audit", "complian", "standard")
# What the extractor is told the validity component is (the rules compare it with
# today; the extractor reports the date the evidence gives, verbatim).
_VALIDITY_HINT = "the date the certificate is valid until, as the evidence states it"


def claimed_standards(claim: Claim) -> list[Standard]:
    """Standards named by the structured `certification` component(s), never read
    from the claim's free text."""
    found: list[Standard] = []
    for c in claim.components:
        if c.name != "certification":
            continue
        for std in standards_in(c.value):
            if all(std.key != s.key for s in found):
                found.append(std)
    return found[:MAX_STANDARDS]


def _core(std: Standard) -> str:
    """What a page writes for sure: "27001" for ISO/IEC 27001:2022, else the label."""
    return std.key.split(":", 1)[1] if std.key.startswith("iso:") else std.label


def plan(claim: Claim, domain: str | None) -> list[Lookup]:
    standards = claimed_standards(claim)
    if not standards:
        return []
    labels = " ".join(s.label for s in standards)
    focus = (*(_core(s) for s in standards), *_FOCUS)
    first = Lookup(
        label=f"{labels} certification record (certification body or registry)",
        words="certificate",
        entity=labels,
        quote_entity=False,
        party_hosts=CERTIFIER_HOSTS,
        party_class=R.COUNTERPARTY_CONFIRMATION,
        focus=focus,
    )
    if domain:
        second = Lookup(
            label=f"the company's trust or security page ({domain})",
            words="certified",
            site=domain,
            focus=focus,
        )
    else:
        second = Lookup(
            label=f"the company's {labels} statements",
            words="certified",
            entity=labels,
            quote_entity=False,
            focus=focus,
        )
    return [first, second]


def _extraction_claim(claim: Claim) -> Claim:
    """The claim as the extractor sees it: each standard, plus the validity date."""
    comps = [
        ClaimComponent(name=c.name, value=_VALIDITY_HINT)
        if c.name == "certificate_valid_until" and c.op == "gte"
        else c
        for c in effective_components(claim)
    ]
    return claim.model_copy(update={"components": comps})


def _reached_certifier(out: Gathered) -> bool:
    return any(
        r.get("attached") and r.get("source_class") in _STRONG
        for entry in out.searched
        for r in entry.get("results", [])
    )


async def gather(env: CheckEnv, claim: Claim) -> Gathered:
    out = Gathered(entity_ids=[env.company_entity])
    if env.case.identity_status == IdentityStatus.CONFIRMED and env.company_id is not None:
        await env.profile()  # the public name and domain come from the enriched record
    lookups = plan(claim, env.terms().domain)
    if not lookups:
        out.notes.append("no named standard in the claim to look up")
        return out
    reading = _extraction_claim(claim)
    first, second = lookups
    await run_lookups(env, reading, [first], out)  # budget refused: Not checked
    if _reached_certifier(out):
        return out  # the certifier's record is the best source; no second lookup
    try:
        await run_lookups(env, reading, [second], out)
    except BudgetExceeded:
        out.notes.append("second lookup skipped: the case's credit budget is spent")
    return out
