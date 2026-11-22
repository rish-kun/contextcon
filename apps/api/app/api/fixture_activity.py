"""Recorded activity streams for the fixture runs (fixture mode and the web fixtures).

Each list is a plausible recording of a real run of that kind: the same templates,
counts keys and item shapes the emitter produces (`app.jobs.activity`), fictional
"(fixture)" companies, `.example` domains, and timestamps spaced like a real run.
Fixture mode replays them over SSE between each step's running and done events, and
serves them from `GET /runs/{id}/activity`.
"""

from __future__ import annotations

from datetime import timedelta
from functools import cache
from typing import Any

from app.api import fixtures as fx
from app.api.schemas.runs import ActivityOut, ActivityPage, ActivitySummaryOut
from app.jobs.activity import (
    NOTICES,
    Kind,
    Label,
    NoticeCode,
    Subject,
    claim_ref,
    envelope,
    free_status,
    render,
    source_ref,
)

CR = "crustdata"


def _call(
    endpoint: str,
    *,
    credits: float | None = 0.0,
    usd: float | None = None,
    ms: int = 900,
    from_cache: bool = False,
    ok: bool = True,
    error: str | None = None,
    attempts: int = 1,
) -> dict[str, Any]:
    return {
        "provider": "anthropic" if endpoint == "messages" else CR,
        "endpoint": endpoint,
        "ok": ok,
        "error": error,
        "from_cache": from_cache,
        "attempts": attempts,
        "duration_ms": ms,
        "credits": None if endpoint == "messages" else credits,
        "usd": usd,
        "credits_total": 0.0,
        "usd_total": 0.0,
    }


def _notice(code: NoticeCode, **slots: Any) -> dict[str, Any]:
    from app.jobs.activity import _fill

    label, detail = NOTICES[code]
    return envelope(
        Kind.NOTICE,
        Label(_fill(label, slots)),
        detail=None if detail is None else Label(_fill(detail, slots)),
        code=code,
    )


def _company(cid: str, stage: str, name: str, **kw: Any) -> dict[str, Any]:
    return {"id": cid, "stage": stage, "name": name, **kw}


class _Recorder:
    """Numbers events, stamps `at` from a running clock and fills the run totals."""

    def __init__(self, run_id: str) -> None:
        self.run = fx.runs()[run_id]
        self.steps = {s.key: s for s in self.run.steps}
        self.events: list[dict[str, Any]] = []
        self.clock = 0.0
        self.credits = 0.0
        self.usd = 0.0

    def add(self, step_key: str, event: dict[str, Any], after: float = 0.6) -> None:
        step = self.steps[step_key]
        self.clock += after
        base = step.started_at or self.run.created_at
        at = base + timedelta(seconds=min(self.clock, 59.0))
        call = event.get("call")
        if call:
            self.credits += call.get("credits") or 0
            self.usd += call.get("usd") or 0
            call["credits_total"] = round(self.credits, 4)
            call["usd_total"] = round(self.usd, 6)
        self.events.append(
            {
                **event,
                "seq": len(self.events) + 1,
                "run_id": self.run.id,
                "step_id": step.id,
                "step_key": step_key,
                "at": at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            }
        )

    def step(self, step_key: str) -> None:
        self.clock = 0.0


def _status(label: Label, progress: tuple[int, int] | None = None, ref=None) -> dict[str, Any]:
    return envelope(Kind.STATUS, label, progress=progress, ref=ref)


KESTREL = ("fx-sl-kestrel", "Kestrel Supply Systems (fixture)", "kestrel-supply.example")
HARBOUR = ("fx-sl-harbourline", fx.HARBOURLINE, fx.HARBOURLINE_DOMAIN)
MORROW = ("fx-sl-morrow", "Morrow Docks (fixture)", "morrowdocks.example")
TARAWADE = ("fx-sl-tarawade", "Tarawade Freight Software (fixture)", "tarawade.example")
SHORTLIST = (KESTREL, HARBOUR, MORROW, TARAWADE)
DROPPED = (
    ("fx-cand-21", "Portside Freight (fixture)", "Failed must-have: privately held"),
    ("fx-cand-22", "Kestrel Supply Systems India (fixture)", "Duplicate of Kestrel Supply Systems"),
)


def _discover() -> list[dict[str, Any]]:
    r = _Recorder(fx.DISCOVER_RUN_ID)
    k = "discover.search"
    r.add(k, _status(render("status.resolving_filters")))
    r.add(
        k,
        _status(
            render("status.searching_companies", filters="India · warehousing · 50–500 people")
        ),
    )
    r.add(
        k,
        envelope(
            Kind.CALL,
            render("call.company_search", n=48),
            detail=render("detail.filters", filters="India · warehousing · 50–500 people"),
            call=_call("company_search", credits=6.2, ms=2310),
            counts={"returned": 48, "new": 48, "total_available": 212},
            highlights=[
                "Kestrel Supply Systems (fixture) · Pune, India",
                "Morrow Docks (fixture) · Chennai, India",
            ],
        ),
        after=2.3,
    )
    found = [
        _company(cid, "found", name, domain=dom, location=loc, headcount=hc,
                 headcount_is_estimate=True)
        for (cid, name, dom), loc, hc in zip(
            SHORTLIST,
            ("Pune, India", "Bhiwandi, India", "Chennai, India", "Ahmedabad, India"),
            (420, 310, 180, 95),
            strict=True,
        )
    ]  # fmt: skip
    found += [
        _company(cid, "found", name, location="India", headcount_is_estimate=True)
        for cid, name, _ in DROPPED
    ]
    r.add(
        k,
        envelope(
            Kind.FINDING,
            render("finding.found_companies", n=48),
            detail=render("finding.pass", pass_="primary"),
            subject=Subject.COMPANY,
            items=found,
            counts={"found": 48, "in_play": 48, "dropped": 0, "enriched": 0, "scored": 0},
        ),
    )
    k = "discover.dedupe_gate"
    r.step(k)
    r.add(k, _status(render("status.removing_duplicates")))
    r.add(
        k,
        envelope(
            Kind.FINDING,
            render("finding.dropped_companies", n=7),
            detail=render("finding.dropped_detail", n=3, m=4),
            subject=Subject.COMPANY,
            items=[_company(cid, "dropped", name, reason=why) for cid, name, why in DROPPED],
            counts={"found": 48, "in_play": 41, "dropped": 7, "enriched": 0, "scored": 0},
        ),
    )
    k = "discover.enrich"
    r.step(k)
    r.add(k, _status(render("status.enriching", n=15)))
    r.add(
        k,
        envelope(
            Kind.CALL,
            render("call.company_enrich", n=15, total=15),
            detail=render("detail.groups", groups="funding and headcount"),
            call=_call("company_enrich", credits=30, ms=1840),
            counts={
                "requested": 15,
                "returned": 15,
                "with_funding": 9,
                "funding_rounds": 14,
                "with_investors": 8,
                "with_headcount_series": 12,
                "with_web_traffic": 0,
            },
            highlights=[
                "Kestrel Supply Systems (fixture) · Seed · 2025-04",
                "Harbourline Warehousing (fixture) · Series A · 2023-11",
            ],
        ),
        after=1.8,
    )
    marks = {"funding": "found", "headcount": "found", "hiring": "pending"}
    for i, (cid, name, _dom) in enumerate(SHORTLIST, start=1):
        r.add(
            k,
            envelope(
                Kind.SOURCE,
                render("source.read_record", name=name),
                source=source_ref(
                    "crustdata_record",
                    title=f"{name} · company record",
                    source_class="data_provider",
                    as_of="2026-11-01",
                ),
            ),
            after=0.2,
        )
        r.add(
            k,
            _status(render("status.reading_jobs", name=name), progress=(i, len(SHORTLIST))),
            after=0.4,
        )
        r.add(
            k,
            envelope(
                Kind.CALL,
                render("call.job_search", n=10 - 2 * i),
                call=_call("job_search", credits=0.03 * (10 - 2 * i), ms=640),
                counts={"postings": 10 - 2 * i, "companies": 1},
            ),
            after=0.6,
        )
        r.add(
            k,
            envelope(
                Kind.FINDING,
                render("finding.enriched_company", name=name),
                subject=Subject.COMPANY,
                items=[_company(cid, "enriched", name, marks={**marks, "hiring": "found"},
                                highlight="Headcount +18% in 12 months" if i == 1 else None)],
                counts={"found": 48, "in_play": 41, "dropped": 7, "enriched": i, "scored": 0},
            ),
            after=0.2,
        )  # fmt: skip
    k = "discover.score"
    r.step(k)
    r.add(k, _status(render("status.scoring", n=15)))
    r.add(
        k,
        envelope(
            Kind.FINDING,
            render("finding.ranked_companies", n=4),
            subject=Subject.COMPANY,
            items=[
                _company(cid, "scored", name, fit=fit, assessable=a, rank=i)
                for i, ((cid, name, _), fit, a) in enumerate(
                    zip(SHORTLIST, (82, 78, 64, 51), (0.8, 0.9, 0.6, 0.5), strict=True), start=1
                )
            ],
            counts={"found": 48, "in_play": 4, "dropped": 7, "enriched": 15, "scored": 15},
        ),
    )
    k = "discover.cards"
    r.step(k)
    r.add(k, _status(render("status.explaining"), progress=(0, 4)))
    for i, (cid, name, _) in enumerate(SHORTLIST, start=1):
        r.add(
            k,
            envelope(
                Kind.MODEL,
                render("model.explanation"),
                call=_call("messages", usd=0.0005, ms=1200),
                counts={"explained": 1},
            ),
            after=1.1,
        )
        r.add(
            k,
            envelope(
                Kind.FINDING,
                render("finding.explained_company", name=name),
                subject=Subject.COMPANY,
                items=[_company(cid, "explained", name)],
                progress=(i, 4),
            ),
            after=0.1,
        )
    return r.events


INVESTOR_COMPANIES = (
    ("900002", "Kestrel Supply Systems (fixture)", "Seed", "2025-04-02", None,
     [("name:northgate ventures (fixture)", "Northgate Ventures (fixture)")]),
    ("900005", "Ridgeway Cold Chain (fixture)", "Seed", "2024-09-01", 1_500_000,
     [("name:banyan seed partners (fixture)", "Banyan Seed Partners (fixture)")]),
    ("900006", "Lattice Yards (fixture)", "Pre Seed", "2022-01-15", None,
     [("name:banyan seed partners llp (fixture)", "Banyan Seed Partners LLP (fixture)")]),
)  # fmt: skip


def _investors() -> list[dict[str, Any]]:
    r = _Recorder(fx.INVESTOR_RUN_ID)
    k = "investors.comparables"
    r.add(k, _status(free_status_label("Searching for comparable companies that raised money")))
    r.add(
        k,
        envelope(
            Kind.CALL,
            render("call.company_search", n=40),
            detail=render("detail.filters", filters="India · warehousing software · Series A"),
            call=_call("company_search", credits=6.5, ms=2100),
            counts={"returned": 40, "new": 40, "total_available": 133},
        ),
        after=2.1,
    )
    r.add(
        k,
        envelope(
            Kind.FINDING,
            render("finding.found_companies", n=40),
            subject=Subject.COMPANY,
            items=[_company(cid, "found", name) for cid, name, *_ in INVESTOR_COMPANIES],
            counts={"found": 40, "in_play": 40, "dropped": 0, "enriched": 0, "scored": 0},
        ),
    )
    k = "investors.enrich"
    r.step(k)
    r.add(k, _status(render("status.reading_rounds", n=25), progress=(0, 25)))
    r.add(
        k,
        envelope(
            Kind.CALL,
            render("call.company_enrich", n=25, total=25),
            detail=render("detail.groups", groups="funding"),
            call=_call("company_enrich", credits=50, ms=3900),
            counts={
                "requested": 25,
                "returned": 25,
                "with_funding": 18,
                "funding_rounds": 31,
                "with_investors": 14,
                "with_headcount_series": 0,
                "with_web_traffic": 0,
            },
        ),
        after=3.9,
    )
    for i, (cid, name, rnd, day, amount, investors) in enumerate(INVESTOR_COMPANIES, start=1):
        r.add(
            k,
            envelope(
                Kind.FINDING,
                render("finding.rounds_of", n=1, name=name),
                subject=Subject.ROUND,
                items=[
                    {
                        "id": f"rnd-{cid}",
                        "stage": "found",
                        "company": name,
                        "company_id": cid,
                        "round": rnd,
                        "date": day,
                        "amount_usd": amount,
                        "investors": [{"key": key, "name": nm} for key, nm in investors],
                    }
                ],
                counts={"companies": 25, "rounds": i, "rounds_dated": i, "investors": i},
                progress=(i, 25),
            ),
            after=0.3,
        )
    k = "investors.rank"
    r.step(k)
    r.add(k, _status(render("status.ranking_investors")))
    r.add(
        k,
        envelope(
            Kind.FINDING,
            render("finding.ranked_investors", n=3),
            subject=Subject.INVESTOR,
            items=[
                {"id": key, "stage": "ranked", "name": nm, "rank": i, "comparable_rounds": 1,
                 "last_round_date": day}
                for i, (_cid, _n, _r, day, _a, [(key, nm)]) in enumerate(INVESTOR_COMPANIES, 1)
            ],
            counts={"investors": 3, "ranked": 3, "not_ranked": 0},
        ),
    )  # fmt: skip
    return r.events


CLAIMS = (
    ("fx-claim-1", "identity_incorporation", "supported", "registry", None),
    ("fx-claim-2", "team_size", "cannot_verify", None, "No dated payroll record was found"),
    ("fx-claim-3", "leadership_history", "supported", None, None),
    ("fx-claim-4", "funding", "conflicting_evidence", "news", "Sources disagree on the date"),
    ("fx-claim-5", "dated_event", "partially_corroborated", "company_announcement",
     "Nothing found shows the facility is operating"),
    ("fx-claim-7", "location", "contradicted", "registry", None),
    ("fx-claim-8", "debt_security", "cannot_verify", None, "Lender statements are needed"),
)  # fmt: skip


def _verify() -> list[dict[str, Any]]:
    r = _Recorder(fx.VERIFY_RUN_ID)
    k = "verify.identity"
    r.add(k, _status(free_status_label(f"Matching the domain {fx.HARBOURLINE_DOMAIN}")))
    r.add(
        k,
        envelope(
            Kind.CALL,
            render("call.company_identify", n=2),
            call=_call("company_identify", credits=0.4, ms=700),
            counts={"candidates": 2},
        ),
    )
    r.add(
        k,
        envelope(
            Kind.FINDING,
            render("finding.identity_confirmed"),
            subject=Subject.IDENTITY,
            items=[
                {
                    "id": str(fx.HARBOURLINE_ID),
                    "stage": "confirmed",
                    "name": fx.HARBOURLINE,
                    "domain": fx.HARBOURLINE_DOMAIN,
                    "matched_keys": ["domain", "crustdata_company_id"],
                }
            ],
            counts={"candidates": 2},
        ),
    )
    k = "verify.registry"
    r.step(k)
    r.add(k, _status(free_status_label("Searching public registry records")))
    r.add(
        k,
        envelope(
            Kind.CALL,
            render("call.web_search", n=6),
            call=_call("web_search", credits=1, ms=1500),
            counts={"hits": 6, "news_hits": 0},
        ),
        after=1.5,
    )
    for i, (dom, title) in enumerate(
        (
            ("registry.example", "Harbourline Warehousing Private Limited (fixture)"),
            ("filings.example", "Charges registered against Harbourline (fixture)"),
        ),
        start=1,
    ):  # fmt: skip
        r.add(k, _status(render("status.reading_domain", domain=dom), progress=(i, 2)))
        r.add(
            k,
            envelope(
                Kind.SOURCE,
                render("source.read_domain", domain=dom),
                source=source_ref(
                    "web_page",
                    url=f"https://{dom}/company/harbourline",
                    title=title,
                    source_class="registry",
                    as_of="2026-10-01",
                ),
                progress=(i, 2),
            ),
            after=1.2,
        )
        r.add(
            k,
            envelope(
                Kind.MODEL,
                render("model.read_article", domain=dom),
                call=_call("messages", usd=0.0006, ms=1900),
                counts={"facts": 2, "rejected_no_span": 0},
            ),
            after=1.9,
        )
    k = "verify.profile"
    r.step(k)
    r.add(k, _status(free_status_label("Reading the company record")))
    r.add(
        k,
        envelope(
            Kind.CALL,
            render("call.company_enrich", n=1, total=1),
            call=_call("company_enrich", credits=2, ms=1300),
            counts={
                "requested": 1, "returned": 1, "with_funding": 1, "funding_rounds": 1,
                "with_investors": 1, "with_headcount_series": 1, "with_web_traffic": 0,
            },
        ),
    )  # fmt: skip
    r.add(
        k,
        envelope(
            Kind.SOURCE,
            render("source.read_company_record"),
            source=source_ref(
                "crustdata_record",
                title=f"{fx.HARBOURLINE} · company record",
                source_class="data_provider",
                as_of="2026-11-01",
            ),
        ),
    )
    k = "verify.people"
    r.step(k)
    r.add(
        k,
        envelope(
            Kind.CALL,
            render("call.person_search", n=6),
            call=_call("person_search", credits=5.5, ms=1700),
            counts={"returned": 6, "current_leadership": 4},
        ),
    )
    k = "verify.jobs"
    r.step(k)
    r.add(
        k,
        envelope(
            Kind.CALL,
            render("call.job_search", n=10),
            call=_call("job_search", credits=0.3, ms=800),
            counts={"postings": 10, "companies": 1},
        ),
    )
    k = "claims.extract:fx-doc-deck"
    r.step(k)
    r.add(k, _status(render("status.reading_document", doc_kind="presentation")))
    r.add(
        k,
        envelope(
            Kind.MODEL,
            render("model.read_document"),
            call=_call("messages", usd=0.0046, ms=6200),
            counts={"claims": 8, "pages": 14},
        ),
        after=6.2,
    )
    r.add(
        k,
        envelope(
            Kind.FINDING,
            render("finding.claims_queued", n=8),
            subject=Subject.CLAIM,
            items=[
                {"id": cid, "stage": "queued", "category": cat}
                for cid, cat, *_ in (*CLAIMS, ("fx-claim-6", "customer_partnership"))
            ],
            counts={"queued": 8, "checking": 0, "settled": 0, "not_checked": 0},
        ),
    )
    settled = 0
    for cid, category, status, source_class, gap in CLAIMS:
        k = f"evidence.claim:{cid}"
        ref = claim_ref(cid)
        r.step(k)
        r.add(k, _status(render("status.checking", category=category), ref=ref))
        r.add(
            k,
            envelope(
                Kind.FINDING,
                render("finding.claim_checking", category=category),
                subject=Subject.CLAIM,
                items=[{"id": cid, "stage": "checking", "category": category}],
                counts={"queued": 8 - settled - 1, "checking": 1, "settled": settled,
                        "not_checked": 0},
                ref=ref,
            ),
        )  # fmt: skip
        source = None
        snippet = None
        if source_class is not None:
            dom = "registry.example" if source_class == "registry" else "news.example"
            source = source_ref(
                "web_page",
                url=f"https://{dom}/harbourline/{cid}",
                title="Harbourline Warehousing (fixture) · public record",
                source_class=source_class,
                as_of="2026-09-03",
            )
            r.add(
                k,
                envelope(
                    Kind.SOURCE,
                    render("source.read_domain", domain=dom),
                    source=source,
                    ref=ref,
                ),
                after=1.4,
            )
            r.add(
                k,
                envelope(
                    Kind.MODEL,
                    render("model.read_domain_for", domain=dom, category=category),
                    call=_call("messages", usd=0.0007, ms=1600),
                    counts={"facts": 1, "rejected_no_span": 0},
                    ref=ref,
                ),
                after=1.6,
            )
            snippet = "…Harbourline Warehousing (fixture) was incorporated in 2016 in Pune…"
        settled += 1
        r.add(
            k,
            envelope(
                Kind.FINDING,
                render("finding.claim_settled", status=status),
                detail=render("finding.category", category=category),
                subject=Subject.CLAIM,
                source=source,
                items=[
                    {
                        "id": cid,
                        "stage": "settled",
                        "category": category,
                        "status": status,
                        "previous_status": None,
                        "evidence_count": 2 if source else 0,
                        "snippet": snippet,
                        "gap": gap,
                    }
                ],
                counts={"queued": 8 - settled - 1, "checking": 0, "settled": settled,
                        "not_checked": 0},
                ref=ref,
            ),
        )  # fmt: skip
    k = "evidence.events"
    r.step(k)
    r.add(k, _status(free_status_label("Searching news about the company")))
    r.add(
        k,
        envelope(
            Kind.CALL,
            render("call.web_search", n=9),
            call=_call("web_search", credits=1, ms=1400),
            counts={"hits": 9, "news_hits": 6},
        ),
    )
    r.add(
        k,
        envelope(
            Kind.SOURCE,
            render("source.failed_domain", domain="social.example"),
            source=source_ref(
                "web_page",
                url="https://social.example/company/harbourline",
                source_class="company_announcement",
                state="failed",
                reason="http_403",
            ),
        ),
    )
    r.add(
        k,
        envelope(
            Kind.FINDING,
            render("finding.dated_events", n=3),
            subject=Subject.EVENT,
            items=[
                {"id": "fx-evt-1", "stage": "found", "date": "2023-11-20", "event_kind": "funding",
                 "title": "Funding announcement · news.example", "domain": "news.example"},
            ],
            counts={"events": 3},
        ),
    )  # fmt: skip
    k = "evidence.comparables"
    r.step(k)
    r.add(
        k,
        envelope(
            Kind.FINDING,
            render("finding.peers", n=2),
            subject=Subject.PEER,
            items=[
                _company("900005", "found", "Ridgeway Cold Chain (fixture)",
                         location="Chennai, India", headcount=210, headcount_is_estimate=True),
                _company("900003", "found", "Morrow Docks (fixture)", location="Chennai, India",
                         headcount=180, headcount_is_estimate=True),
            ],
            counts={"peers": 2},
        ),
    )  # fmt: skip
    r.add(k, _notice(NoticeCode.BUDGET_REACHED))
    k = "evaluate.assess"
    r.step(k)
    r.add(k, _status(render("status.assessing")))
    r.add(
        k,
        envelope(
            Kind.FINDING,
            render("finding.assessment", disposition="investigate_further"),
            subject=Subject.ASSESSMENT,
            items=[
                {"id": "fx-assessment-1", "stage": "written", "version": 1,
                 "disposition": "investigate_further", "previous_disposition": None,
                 "fit": 78, "assessable": 0.7}
            ],
            counts={"supported": 2, "open": 5},
        ),
    )  # fmt: skip
    return r.events


def _recheck() -> list[dict[str, Any]]:
    r = _Recorder(fx.RECHECK_RUN_ID)
    k = "claims.extract_text:fx-doc-payroll"
    r.add(k, _status(render("status.reading_document", doc_kind="PDF")))
    r.add(
        k,
        envelope(
            Kind.SOURCE,
            render("source.read_document", doc_kind="PDF"),
            source=source_ref("seller_document", title="Seller document · PDF"),
        ),
    )
    k = "recheck.facts:fx-claim-2"
    ref = claim_ref("fx-claim-2")
    r.step(k)
    r.add(k, _status(render("status.checking", category="team_size"), ref=ref))
    r.add(
        k,
        envelope(
            Kind.MODEL,
            render("model.read_document_for", category="team_size"),
            call=_call("messages", usd=0.0005, ms=1500),
            counts={"facts": 1, "rejected_no_span": 0},
            ref=ref,
        ),
    )
    r.add(
        k,
        envelope(
            Kind.FINDING,
            render("finding.claim_settled", status="supported"),
            detail=render("finding.category", category="team_size"),
            subject=Subject.CLAIM,
            items=[
                {"id": "fx-claim-2", "stage": "settled", "category": "team_size",
                 "status": "supported", "previous_status": "cannot_verify",
                 "evidence_count": 1, "snippet": None, "gap": None}
            ],
            counts={"queued": 0, "checking": 0, "settled": 1, "not_checked": 0},
            ref=ref,
        ),
    )  # fmt: skip
    k = "evaluate.assess"
    r.step(k)
    r.add(k, _status(render("status.assessing")))
    r.add(
        k,
        envelope(
            Kind.FINDING,
            render("finding.assessment", disposition="investigate_further"),
            subject=Subject.ASSESSMENT,
            items=[
                {"id": "fx-assessment-2", "stage": "written", "version": 2,
                 "disposition": "investigate_further",
                 "previous_disposition": "investigate_further", "fit": 80, "assessable": 0.75}
            ],
            counts={"supported": 3, "open": 4},
        ),
    )  # fmt: skip
    return r.events


def free_status_label(text: str) -> Label:
    """A status as `ctx.set_detail(text)` would emit it."""
    return free_status(text)


@cache
def recordings() -> dict[str, list[ActivityOut]]:
    raw = {
        fx.DISCOVER_RUN_ID: _discover(),
        fx.INVESTOR_RUN_ID: _investors(),
        fx.VERIFY_RUN_ID: _verify(),
        fx.RECHECK_RUN_ID: _recheck(),
    }
    return {
        run_id: [ActivityOut.model_validate(e) for e in events] for run_id, events in raw.items()
    }


def activities(run_id: str) -> list[ActivityOut]:
    return list(recordings().get(run_id, []))


def page(run_id: str, *, after: int = 0, limit: int = 500) -> ActivityPage:
    everything = activities(run_id)
    items = [a for a in everything if a.seq > after][:limit]
    return ActivityPage(
        items=items,
        next_after=items[-1].seq
        if len(items) == limit and items[-1].seq < len(everything)
        else None,
        summary=summary(run_id, everything),
    )


def summary(run_id: str, items: list[ActivityOut]) -> ActivitySummaryOut:
    run = fx.runs()[run_id]
    by_kind: dict[str, int] = {}
    for a in items:
        by_kind[a.kind.value] = by_kind.get(a.kind.value, 0) + 1
    sources = [a.source for a in items if a.kind == Kind.SOURCE and a.source]
    calls = [a for a in items if a.call and a.call.provider == CR]
    companies = {
        i.id
        for a in items
        if a.subject and a.subject.value == "company"
        for i in a.items or []
        if getattr(i, "stage", None) == "found"
    }
    investors = {
        inv.key for a in items for i in a.items or [] for inv in getattr(i, "investors", None) or []
    }
    claims = {
        i.id
        for a in items
        if a.subject and a.subject.value == "claim"
        for i in a.items or []
        if getattr(i, "stage", None) in ("settled", "not_checked")
    }
    end = run.finished_at or run.created_at
    return ActivitySummaryOut(
        by_kind=by_kind,
        crustdata_calls=len(calls),
        records_returned=sum(
            sum((a.counts or {}).get(k, 0) for k in ("returned", "candidates", "postings"))
            for a in calls
        ),
        sources_read=sum(s.state == "read" for s in sources),
        sources_failed=sum(s.state == "failed" for s in sources),
        domains=len({s.domain for s in sources if s.domain}),
        companies_found=len(companies),
        investors_found=len(investors),
        claims_settled=len(claims),
        credits=run.cost.crustdata_credits,
        llm_usd=run.cost.llm_usd,
        elapsed_seconds=(end - run.created_at).total_seconds(),
        last_seq=items[-1].seq if items else 0,
    )


def export() -> dict[str, list[dict[str, Any]]]:
    return {
        run_id: [a.model_dump(mode="json") for a in items] for run_id, items in recordings().items()
    }
