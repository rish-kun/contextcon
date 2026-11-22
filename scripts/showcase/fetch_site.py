"""Fetch public web pages through Crustdata's live web fetch (`/web/enrich/live`).

Run from `apps/api`:

    env -u ANTHROPIC_BASE_URL -u ANTHROPIC_AUTH_TOKEN uv run --env-file <repo>/.env \
        python ../../scripts/showcase/fetch_site.py OUT_DIR URL [URL ...]

Writes one JSON file per requested URL (the provider's url, title, timestamp, HTML and
the plain text DealProof's own `html_to_text` makes of it) plus `credits.json` with the
credits each call reported. Nothing is edited.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.clients.crustdata import CrustdataClient
from app.pipelines.verify.checks.html import html_to_text


def slug(url: str) -> str:
    s = re.sub(r"^https?://", "", url).strip("/")
    return re.sub(r"[^A-Za-z0-9]+", "_", s)[:80] or "root"


async def main(out: Path, urls: list[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    credits_file = out / "credits.json"
    ledger = json.loads(credits_file.read_text()) if credits_file.exists() else []
    async with CrustdataClient.from_settings() as client:
        for i in range(0, len(urls), 10):
            batch = urls[i : i + 10]
            human = os.environ.get("HUMAN_MODE") == "1"  # the provider's slower browser fetch
            pages, record = await client.fetch_pages(batch, human_mode=human)
            ledger.append(
                {
                    "endpoint": "/web/enrich/live",
                    "urls": batch,
                    "credits_used": record.credits_used,
                    "human_mode": human,
                    "called_at": datetime.now(UTC).isoformat(),
                }
            )
            for requested, page in zip(batch, pages, strict=False):
                doc = page.model_dump()
                doc["requested_url"] = requested
                doc["text"] = html_to_text(page.content or "")
                (out / f"{slug(requested)}.json").write_text(
                    json.dumps(doc, indent=1, ensure_ascii=False)
                )
                print(
                    f"{requested} -> ok={bool(page.url)} title={page.title!r} "
                    f"chars={len(doc['text'])}"
                )
            print(f"credits: {record.credits_used}")
    credits_file.write_text(json.dumps(ledger, indent=1))


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), sys.argv[2:]))
