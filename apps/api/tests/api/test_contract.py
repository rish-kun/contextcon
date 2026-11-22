"""Contract tests: routes, committed artifacts, stub behaviour, fixture mode, SSE."""

import importlib
import json
import re

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import export_openapi, fixtures, runs
from app.api._base import FIXTURE_HEADER
from app.api.schemas import common
from app.api.schemas.common import ClaimStatus, FactStr, SourceClass, SourceRef
from app.api.schemas.runs import ActivityOut
from app.main import create_app

CASE = fixtures.CASE_ID
RUN = fixtures.VERIFY_RUN_ID

CRITERION = {
    "label": "Headquartered in India",
    "kind": "must",
    "dimension": "geography",
    "operator": "eq",
    "value": "India",
}

# (method, path template, concrete path, JSON body)
ROUTES: list[tuple[str, str, str, object]] = [
    ("POST", "/auth/login", "/auth/login", {"email": "a@b.example", "password": "x"}),
    ("POST", "/auth/logout", "/auth/logout", None),
    ("GET", "/auth/me", "/auth/me", None),
    ("POST", "/theses", "/theses", {"text": "Indian warehousing software companies"}),
    ("GET", "/theses", "/theses", None),
    ("GET", "/theses/{thesis_id}", f"/theses/{fixtures.THESIS_ID}", None),
    (
        "PUT",
        "/theses/{thesis_id}/criteria",
        f"/theses/{fixtures.THESIS_ID}/criteria",
        [CRITERION],
    ),
    ("POST", "/theses/{thesis_id}/search", f"/theses/{fixtures.THESIS_ID}/search", None),
    (
        "POST",
        "/investor-searches",
        "/investor-searches",
        {
            "sector": "Warehousing software",
            "location": "India",
            "stage": "series_a",
            "size": "51-200",
            "funding_sought": "equity venture",
        },
    ),
    ("GET", "/investor-searches", "/investor-searches", None),
    (
        "GET",
        "/investor-searches/{search_id}",
        f"/investor-searches/{fixtures.INVESTOR_SEARCH_ID}",
        None,
    ),
    ("POST", "/cases", "/cases", {"name": "Example (fixture)", "website": "example.example"}),
    ("GET", "/cases", "/cases", None),
    ("GET", "/companies/lookup", "/companies/lookup?q=Acme", None),
    ("GET", "/cases/{case_id}", f"/cases/{CASE}", None),
    (
        "POST",
        "/cases/{case_id}/identity",
        f"/cases/{fixtures.CASE_AMBIGUOUS_ID}/identity",
        {"crustdata_company_id": 900010},
    ),
    ("POST", "/cases/{case_id}/verify", f"/cases/{CASE}/verify", None),
    ("PUT", "/cases/{case_id}/criteria", f"/cases/{CASE}/criteria", {"criteria": [CRITERION]}),
    ("GET", "/cases/{case_id}/assessments", f"/cases/{CASE}/assessments", None),
    ("GET", "/cases/{case_id}/decision-flip", f"/cases/{CASE}/decision-flip", None),
    ("POST", "/cases/{case_id}/decision-flip", f"/cases/{CASE}/decision-flip", None),
    ("POST", "/cases/{case_id}/claims", f"/cases/{CASE}/claims", {"text": "We have 3 sites"}),
    (
        "POST",
        "/cases/{case_id}/claims/{claim_id}/check",
        f"/cases/{CASE}/claims/{fixtures.case_detail(CASE).claims[0].id}/check",
        None,
    ),
    ("POST", "/cases/{case_id}/documents", f"/cases/{CASE}/documents", None),
    (
        "GET",
        "/documents/{document_id}/url",
        f"/documents/{fixtures.DECK_DOC_ID}/url",
        None,
    ),
    ("POST", "/cases/{case_id}/requests", f"/cases/{CASE}/requests", None),
    ("GET", "/cases/{case_id}/requests", f"/cases/{CASE}/requests", None),
    ("GET", "/runs", "/runs?status=recent&limit=5", None),
    ("GET", "/runs/{run_id}", f"/runs/{RUN}", None),
    ("GET", "/runs/{run_id}/events", f"/runs/{RUN}/events", None),
    ("GET", "/runs/{run_id}/activity", f"/runs/{RUN}/activity", None),
    ("POST", "/runs/{run_id}/resume", f"/runs/{RUN}/resume", None),
    ("GET", "/policy", "/policy", None),
    ("GET", "/public/showcase", "/public/showcase", None),
    ("GET", "/public/showcase/case", "/public/showcase/case", None),
    ("GET", "/public/showcase/case/assessments", "/public/showcase/case/assessments", None),
    ("GET", "/public/showcase/discovery", "/public/showcase/discovery", None),
    ("GET", "/public/showcase/investors", "/public/showcase/investors", None),
    ("GET", "/public/showcase/runs/{run_id}", f"/public/showcase/runs/{RUN}", None),
    (
        "GET",
        "/public/showcase/runs/{run_id}/activity",
        f"/public/showcase/runs/{RUN}/activity",
        None,
    ),
]

# Implemented with auth (CP-16): outside fixture mode they answer 401 without a session.
SESSION_ROUTES = {
    "/auth/me",
    "/runs",  # the jobs queue
    "/runs/{run_id}",
    "/runs/{run_id}/events",
    "/runs/{run_id}/activity",
    "/runs/{run_id}/resume",
    "/cases",  # CP-19: create and list
    "/companies/lookup",  # pick a company before a case opens
    "/cases/{case_id}",  # CP-19
    "/cases/{case_id}/identity",  # CP-19
    "/cases/{case_id}/verify",  # CP-19
    "/cases/{case_id}/criteria",
    "/cases/{case_id}/assessments",
    "/cases/{case_id}/decision-flip",
    "/cases/{case_id}/claims",  # CP-20
    "/cases/{case_id}/claims/{claim_id}/check",  # one row's "Run check"
    "/cases/{case_id}/documents",  # CP-20
    "/documents/{document_id}/url",  # CP-20
    "/theses",
    "/theses/{thesis_id}",
    "/theses/{thesis_id}/criteria",
    "/theses/{thesis_id}/search",
    "/investor-searches",  # CP-18
    "/investor-searches/{search_id}",  # CP-18
    "/cases/{case_id}/requests",  # CP-23
}
# Implemented and public: served without a session. The showcase routes are read-only
# and serve only rows flagged `is_showcase` (app.api.showcase).
PUBLIC_ROUTES = {
    "/policy",
    "/public/showcase",
    "/public/showcase/case",
    "/public/showcase/case/assessments",
    "/public/showcase/discovery",
    "/public/showcase/investors",
    "/public/showcase/runs/{run_id}",
    "/public/showcase/runs/{run_id}/activity",
}
AUTH_ROUTES = SESSION_ROUTES | {"/auth/login", "/auth/logout"}
STUB_ROUTES = [r for r in ROUTES if r[1] not in AUTH_ROUTES | PUBLIC_ROUTES]

MSG = f"/cases/{CASE}/messages"
REVISION = {"subject": "s", "body": "b", "recipient": "a@b.example"}
# Implemented by app.act (mounted as-is); they need a session (CP-16).
ACT_ROUTES: list[tuple[str, str, str, object]] = [
    ("POST", "/cases/{case_id}/messages", MSG, REVISION),
    ("GET", "/cases/{case_id}/messages/send-summary", f"{MSG}/send-summary", None),
    ("GET", "/cases/{case_id}/messages/{message_id}", f"{MSG}/m", None),
    ("POST", "/cases/{case_id}/messages/{message_id}/revisions", f"{MSG}/m/revisions", REVISION),
    (
        "POST",
        "/cases/{case_id}/messages/{message_id}/approve",
        f"{MSG}/m/approve",
        {"revision_id": "r"},
    ),
    (
        "POST",
        "/cases/{case_id}/messages/{message_id}/send",
        f"{MSG}/m/send",
        {"revision_id": "r", "expect_live": False},
    ),
    ("POST", "/cases/{case_id}/messages/{message_id}/reconcile", f"{MSG}/m/reconcile", None),
]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("DEALPROOF_FIXTURES", raising=False)
    return TestClient(create_app())


@pytest.fixture
def fixture_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DEALPROOF_FIXTURES", "1")
    monkeypatch.setattr(runs, "FIXTURE_EVENT_DELAY_SECONDS", 0)
    return TestClient(create_app())


def _call(client: TestClient, method: str, path: str, body: object):
    return (
        client.request(method, path, json=body)
        if body is not None
        else client.request(method, path)
    )


def test_openapi_has_all_routes() -> None:
    spec = create_app().openapi()
    present = {(m.upper(), p) for p, ops in spec["paths"].items() for m in ops}
    expected = {(m, p) for m, p, _, _ in ROUTES + ACT_ROUTES}
    assert expected <= present
    # Nothing undocumented sneaks in either: only /health sits outside the contract list.
    assert present - expected == {("GET", "/health")}


def test_openapi_matches_committed_file() -> None:
    committed = json.loads(export_openapi.OPENAPI_PATH.read_text(encoding="utf-8"))
    assert committed == create_app().openapi(), (
        "apps/api/openapi.json is stale: run `uv run python -m app.api.export_openapi` "
        "and `pnpm --filter web gen:api`"
    )


def test_web_fixtures_match_committed_file() -> None:
    committed = json.loads(export_openapi.WEB_FIXTURES_PATH.read_text(encoding="utf-8"))
    assert committed == fixtures.export(), (
        "apps/web/lib/api/fixtures.json is stale: run `uv run python -m app.api.export_openapi`"
    )


def test_operation_ids_are_function_names() -> None:
    spec = create_app().openapi()
    ids = [op["operationId"] for ops in spec["paths"].values() for op in ops.values()]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z_]+", i) for i in ids)


@pytest.mark.parametrize(("method", "template", "path", "body"), STUB_ROUTES)
def test_stub_returns_501(client: TestClient, method, template, path, body) -> None:
    response = _call(client, method, path, body)
    assert response.status_code == 501, (template, response.text)
    assert "Not implemented" in response.json()["detail"]
    assert FIXTURE_HEADER not in response.headers


@pytest.mark.parametrize(
    ("method", "template", "path", "body"),
    [r for r in ROUTES if r[1] in SESSION_ROUTES] + ACT_ROUTES,
)
def test_routes_need_a_session(client: TestClient, method, template, path, body) -> None:
    """No `dp_session` cookie → 401 before any handler (or database) runs."""
    response = _call(client, method, path, body)
    assert response.status_code == 401, (template, response.text)
    assert response.headers["content-type"].startswith("application/json")
    assert FIXTURE_HEADER not in response.headers


def test_logout_without_session_clears_cookie(client: TestClient) -> None:
    response = client.post("/auth/logout")
    assert response.status_code == 204
    assert "dp_session=" in response.headers["set-cookie"]


def test_sse_contract_documents_events_and_json_errors() -> None:
    spec = create_app().openapi()
    responses = spec["paths"]["/runs/{run_id}/events"]["get"]["responses"]
    assert set(responses["200"]["content"]) == {"text/event-stream"}
    events = responses["200"]["content"]["text/event-stream"]["x-sse-events"]
    assert events == {
        "run": {"$ref": "#/components/schemas/RunOut"},
        "step": {"$ref": "#/components/schemas/StepOut"},
        "activity": {"$ref": "#/components/schemas/ActivityOut"},
    }
    for code in ("401", "404"):
        assert set(responses[code]["content"]) == {"application/json"}, code


def test_fact_schema_requires_source() -> None:
    with pytest.raises(ValidationError):
        FactStr.model_validate({"value": "Pune"})
    spec = create_app().openapi()["components"]["schemas"]
    for name in ("FactStr", "FactInt", "FactFloat", "FactStrList"):
        assert {"value", "source"} <= set(spec[name]["required"]), name
    assert {"source_id", "provider", "retrieved_at", "source_class"} <= set(
        spec["SourceRef"]["required"]
    )


def test_request_bodies_reject_unknown_keys(fixture_client: TestClient) -> None:
    response = fixture_client.post("/theses", json={"text": "Indian warehousing", "extra": 1})
    assert response.status_code == 422


def test_case_create_needs_an_entry_point(fixture_client: TestClient) -> None:
    assert fixture_client.post("/cases", json={"name": "Only a name"}).status_code == 422
    assert fixture_client.post("/cases", json={"shortlist_item_id": "x"}).status_code == 201


@pytest.mark.parametrize(("method", "template", "path", "body"), ROUTES)
def test_fixture_mode_serves_every_route(
    fixture_client: TestClient, method, template, path, body
) -> None:
    response = _call(fixture_client, method, path, body)
    assert 200 <= response.status_code < 300, (template, response.text)
    assert response.headers[FIXTURE_HEADER] == "1"


def test_fixture_mode_unknown_id_is_404(fixture_client: TestClient) -> None:
    assert fixture_client.get("/cases/nope").status_code == 404
    assert fixture_client.get("/runs/nope").status_code == 404


def test_fixture_ledger_covers_all_six_statuses() -> None:
    statuses = {c.status for c in fixtures.claims(1)}
    assert statuses == set(ClaimStatus)
    for claim in fixtures.claims(2):
        if claim.status == ClaimStatus.not_checked:
            assert claim.reason


def test_fixture_companies_are_labelled() -> None:
    data = fixtures.export()
    names: list[str] = []

    def walk(node: object, key: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for v in node:
                walk(v, key)
        elif key in {"name", "company_name", "investor_name", "entity_name"} and isinstance(
            node, str
        ):
            names.append(node)

    walk(data)
    company_like = [n for n in names if n not in {"Name"}]
    assert company_like
    for name in company_like:
        if name == fixtures.USER.display_name:
            continue
        assert "(fixture)" in name, name


def _sse_blocks(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.split("\n") if not line.startswith(":"))
        if "event" in fields:
            out.append((fields["event"], json.loads(fields["data"])))
    return out


def test_sse_stream_emits_steps_activities_then_run(fixture_client: TestClient) -> None:
    from app.api import fixture_activity

    run = fixtures.runs()[fixtures.DISCOVER_RUN_ID]
    with fixture_client.stream("GET", f"/runs/{run.id}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        text = "".join(response.iter_text())
    assert ": live\n\n" in text
    events = _sse_blocks(text)
    assert events[0][0] == "run" and events[0][1]["state"] == "running"
    assert events[-1] == ("end", {}) and events[-2][0] == "run" and events[-2][1]["state"] == "done"
    steps = [data for name, data in events if name == "step"]
    assert len(steps) == 2 * len(run.steps)
    assert steps[-1]["state"] == "done"
    activities = [data for name, data in events if name == "activity"]
    recorded = fixture_activity.activities(run.id)
    assert (
        [a["seq"] for a in activities]
        == [a.seq for a in recorded]
        == list(range(1, len(recorded) + 1))
    )
    assert f"id: {recorded[-1].seq}\nevent: activity" in text
    # Resuming after a seq sends only what came after it.
    with fixture_client.stream(
        "GET", f"/runs/{run.id}/events", headers={"Last-Event-ID": "30"}
    ) as response:
        resumed = _sse_blocks("".join(response.iter_text()))
    assert [d["seq"] for n, d in resumed if n == "activity"] == list(range(31, len(recorded) + 1))


def test_fixture_activity_page_and_kinds(fixture_client: TestClient) -> None:
    from app.api import fixture_activity

    for run_id in (
        fixtures.DISCOVER_RUN_ID,
        fixtures.INVESTOR_RUN_ID,
        fixtures.VERIFY_RUN_ID,
        fixtures.RECHECK_RUN_ID,
    ):
        page = fixture_client.get(f"/runs/{run_id}/activity").json()
        assert page["items"], run_id
        assert [a["seq"] for a in page["items"]] == list(range(1, len(page["items"]) + 1))
        assert page["next_after"] is None
        assert page["summary"]["last_seq"] == len(page["items"])
        for item in page["items"]:
            assert set(item) == set(ActivityOut.model_fields), item  # nulls, never omitted
            assert len(item["label"]) <= 120
    first = fixture_client.get(f"/runs/{fixtures.VERIFY_RUN_ID}/activity?after=0&limit=10").json()
    assert [a["seq"] for a in first["items"]] == list(range(1, 11)) and first["next_after"] == 10
    verify = fixture_activity.activities(fixtures.VERIFY_RUN_ID)
    kinds = {a.kind.value for a in verify}
    assert kinds == {"status", "call", "source", "model", "finding", "notice"}
    subjects = {a.subject.value for a in verify if a.subject}
    assert {"identity", "claim", "event", "peer", "assessment"} <= subjects
    assert fixture_client.get("/runs/nope/activity").status_code == 404


def test_shared_enums_match_spec() -> None:
    assert {s.value for s in common.ClaimStatus} == {
        "supported",
        "contradicted",
        "partially_corroborated",
        "conflicting_evidence",
        "cannot_verify",
        "not_checked",
    }
    assert {d.value for d in common.Disposition} == {
        "prioritise",
        "investigate_further",
        "deprioritise",
        "cannot_assess",
    }
    assert {k.value for k in common.CriterionKind} == {"must", "preference"}
    assert {r.value for r in common.CriterionResultState} == {"pass", "fail", "unknown"}
    assert {i.value for i in common.IdentityState} == {"confirmed", "unresolved", "ambiguous"}


SHARED_ENUMS = [  # spec §5.0: exact equality
    ("ClaimStatus", "ClaimStatus"),
    ("Disposition", "Disposition"),
    ("CriterionKind", "CriterionKind"),
    ("CriterionResultState", "TriState"),
    ("IdentityState", "IdentityState"),
    ("SourceClass", "SourceReliability"),
]
OTHER_ENUMS = [  # the contract may be a superset (e.g. `litigation`, spec §6.3)
    ("ClaimCategory", "ClaimCategory"),
    ("RunKind", "RunKind"),
    ("StepState", "StepState"),
    ("CompanyType", "CompanyType"),
    ("CriterionDimension", "CriterionDimension"),
]


def _domain_enum(name: str):
    try:
        domain = importlib.import_module("app.domain.enums")
    except ModuleNotFoundError:
        pytest.skip("app.domain.enums not on this branch yet")
    found = getattr(domain, name, None)
    if found is None:
        pytest.skip(f"app.domain.enums has no {name}")
    return found


@pytest.mark.parametrize(("contract_name", "domain_name"), SHARED_ENUMS)
def test_shared_enums_equal_domain(contract_name: str, domain_name: str) -> None:
    domain_values = {e.value for e in _domain_enum(domain_name)}
    assert {e.value for e in getattr(common, contract_name)} == domain_values


@pytest.mark.parametrize(("contract_name", "domain_name"), OTHER_ENUMS)
def test_domain_values_fit_contract(contract_name: str, domain_name: str) -> None:
    """Every value the domain can produce must serialise through the contract."""
    domain_values = {e.value for e in _domain_enum(domain_name)}
    assert domain_values <= {e.value for e in getattr(common, contract_name)}


def test_source_ref_has_class() -> None:
    ref = SourceRef(
        source_id="s",
        provider="web",
        label="Registry mirror",
        url_or_endpoint="https://registry-mirror.example",
        retrieved_at="2026-11-22T00:00:00Z",
        source_class=SourceClass.registry_mirror,
    )
    assert ref.source_class == "registry_mirror"
