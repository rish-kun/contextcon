"""Export the live showcase to `apps/web/content/showcase/` (the home page's fallback).

    python export.py OUT_DIR [--notes NOTES.json]

Reads the API's public read-only routes (`/public/showcase/*`), which serve the records
flagged `is_showcase` through the same response builders the app uses, already
scrubbed. Writes them unchanged:

    discovery.json    ThesisOut
    case.json         CaseDetail
    assessments.json  list[AssessmentVersionOut], oldest first, with diffs
    investors.json    InvestorSearchOut
    run-activity.json {run_id: {"run": RunOut, "activity": ActivityPage}}
    meta.json         run dates, names, totals and provenance notes (no contract type)

Totals in meta.json are sums of the exported objects, so the page's checks hold.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import dp


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--notes", help="JSON file with extra provenance notes and fetch credits")
    a = ap.parse_args()
    out = Path(a.out)
    c = dp.Client()  # no sign-in: public routes only

    index = c.get("/public/showcase")
    discovery = c.get("/public/showcase/discovery")
    case = c.get("/public/showcase/case")
    assessments = c.get("/public/showcase/case/assessments")
    investors = c.get("/public/showcase/investors")
    runs = {}
    for run_id in index["run_ids"]:
        runs[run_id] = {
            "run": c.get(f"/public/showcase/runs/{run_id}"),
            "activity": c.get(f"/public/showcase/runs/{run_id}/activity?after=0&limit=2000"),
        }

    disc_run = discovery.get("run") or {}
    inv_run = investors.get("run") or {}
    case_cost = case["cost"]
    shortlist = discovery.get("shortlist") or []
    excluded = [s for s in shortlist if s.get("excluded")]
    case_runs = [r for r in case.get("runs") or []]
    started = min(
        [x for x in [disc_run.get("created_at"), *(r["created_at"] for r in case_runs)] if x]
    )
    finished = max(
        [
            x
            for x in [
                disc_run.get("finished_at"),
                inv_run.get("finished_at"),
                *(r.get("finished_at") for r in case_runs),
            ]
            if x
        ]
    )
    credits = (
        case_cost["crustdata_credits"]
        + (disc_run.get("cost") or {}).get("crustdata_credits", 0)
        + (inv_run.get("cost") or {}).get("crustdata_credits", 0)
    )
    llm = (
        case_cost["llm_usd"]
        + (disc_run.get("cost") or {}).get("llm_usd", 0)
        + (inv_run.get("cost") or {}).get("llm_usd", 0)
    )
    assessment = case.get("assessment") or {}
    notes = json.loads(Path(a.notes).read_text()) if a.notes else {}
    meta = {
        "exported_at": datetime.now(UTC).isoformat(),
        "source": "GET /public/showcase/* on the live API (records flagged is_showcase)",
        "run_started_at": started,
        "run_finished_at": finished,
        "thesis_id": index["thesis_id"],
        "case_id": index["case_id"],
        "investor_search_id": index["investor_search_id"],
        "company_name": case["case"]["name"],
        "company_domain": case["case"].get("website"),
        "claims_origin": "public_website",
        "credits_total": round(credits, 4),
        "llm_usd_total": round(llm, 6),
        "credits_by_part": {
            "discovery": (disc_run.get("cost") or {}).get("crustdata_credits", 0),
            "case": case_cost["crustdata_credits"],
            "investors": (inv_run.get("cost") or {}).get("crustdata_credits", 0),
        },
        "credit_budget": case_cost["credit_budget"],
        "returned_count": len(shortlist),
        "excluded_count": len(excluded),
        "claims_count": len(case.get("claims") or []),
        "assessment_versions": [v["version"] for v in assessments],
        "policy_version": assessment.get("policy_version"),
        "provenance": index["provenance"],
        **notes,
    }

    out.mkdir(parents=True, exist_ok=True)
    for name, obj in {
        "discovery.json": discovery,
        "case.json": case,
        "assessments.json": assessments,
        "investors.json": investors,
        "run-activity.json": runs,
        "meta.json": meta,
    }.items():
        dp.save(obj, out / name)
        print("wrote", out / name)


if __name__ == "__main__":
    main()
