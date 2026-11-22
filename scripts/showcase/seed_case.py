"""Open a case on the live site from a shortlist item and let the real pipelines run.

    DEALPROOF_DEMO_ENV=<path> python seed_case.py THESIS_ID "<shortlist name>" OUT.json \
        [--doc PATH ...]

Uploads each `--doc` (kind `other`: a public document, not a seller document) right
after the case is opened, so the case's closing assessment includes its claims. Waits
until the case's latest run has finished, then saves the CaseDetail and run summaries.
"""

from __future__ import annotations

import argparse
import sys
import time

import dp


def wait_case(c: dp.Client, case_id: str, limit: float = 3600) -> dict:
    start = time.time()
    last = None
    while True:
        case = c.get(f"/cases/{case_id}")["case"]
        run = case.get("run") or {}
        state = (case["status"], run.get("id"), run.get("state"))
        if state != last:
            print(f"  case {case['status']} run {run.get('kind')} {run.get('state')}", file=sys.stderr)
            last = state
        if run and run.get("state") not in ("pending", "running") and case["status"] != "verifying":
            return case
        if time.time() - start > limit:
            raise TimeoutError(f"case {case_id} still {state}")
        time.sleep(10)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("thesis_id")
    ap.add_argument("name")
    ap.add_argument("out")
    ap.add_argument("--doc", action="append", default=[])
    a = ap.parse_args()
    c = dp.Client()
    c.login()
    thesis = c.get(f"/theses/{a.thesis_id}")
    item = next(s for s in thesis["shortlist"] if s["name"] == a.name)
    if item.get("case_id"):
        case_id = item["case_id"]
        print("existing case", case_id)
    else:
        case = c.post("/cases", {"shortlist_item_id": item["id"], "thesis_id": a.thesis_id})
        case_id = case["id"]
        print("case", case_id, case["status"])
        for path in a.doc:
            doc = c.upload(case_id, path, "other", "application/pdf")
            print("uploaded", doc["id"], doc["filename"], doc.get("pages"))
    wait_case(c, case_id)
    detail = c.get(f"/cases/{case_id}")
    dp.save(detail, a.out)
    claims = detail.get("claims") or []
    print("claims", len(claims))
    for cl in claims:
        print(f"  {cl['number']:>2} {cl['status']:<24} {cl['category']:<22} {cl['original_text'][:90]}")
    a_ = detail.get("assessment") or {}
    print("assessment v", a_.get("version"), a_.get("disposition"))
    print("cost", detail["cost"]["crustdata_credits"], detail["cost"]["llm_usd"])


if __name__ == "__main__":
    main()
