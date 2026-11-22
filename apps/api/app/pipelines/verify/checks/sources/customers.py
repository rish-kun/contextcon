"""Customer counts ("trusted by 100+ clients in 20+ countries", "99% positive feedback").

One lookup: `"<company>" customer case study`, the company's own case studies and
press releases plus customers' pages that name it. Public pages name customers but
never count them, so a count stays Cannot verify, which is the honest result; what
the lookup finds is kept: the searched sources (`Gathered.searched`, shown as
"Searched: ...") and any named customer as related evidence. What settles the count
is the seller's dated customer list or reference letters (`policy.DOC_CUSTOMER_LIST`).

Claims that name a customer ("Acme is our customer") go to `sources/partnership.py`,
which looks for the customer's own confirmation first.

Only public terms go out: the confirmed company name and fixed words. The claim's
figures and wording never reach the provider.
"""

from __future__ import annotations

from app.domain.types import Claim
from app.pipelines.verify.checks.gather import CheckEnv, Gathered, Lookup, run_lookups

LABEL = "the company's customer case studies and press releases"


def plan(claim: Claim) -> list[Lookup]:
    return [
        Lookup(
            label=LABEL,
            words="customer case study",
            focus=("customer", "customers", "client", "clients", "case study"),
        )
    ]


async def gather(env: CheckEnv, claim: Claim) -> Gathered:
    out = Gathered(entity_ids=[env.company_entity])
    if env.crustdata is None or env.llm is None:
        out.searched.append(
            {"label": LABEL, "query": None, "results": [], "skipped": "source_unavailable"}
        )
        return out
    await run_lookups(env, claim, plan(claim), out)
    return out
