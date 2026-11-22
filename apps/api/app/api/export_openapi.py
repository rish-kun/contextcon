"""Write the committed contract artifacts.

    uv run python -m app.api.export_openapi          # rewrite both files
    uv run python -m app.api.export_openapi --check  # exit 1 if either is stale

Outputs:
- `apps/api/openapi.json`: the OpenAPI document (`pnpm --filter web gen:api` turns it
  into `apps/web/lib/api/schema.ts`).
- `apps/web/lib/api/fixtures.json`: contract-valid fixture data for the web app's
  `NEXT_PUBLIC_API_MODE=fixtures` mode.
"""

import json
import sys
from pathlib import Path
from typing import Any

API_DIR = Path(__file__).resolve().parents[2]
OPENAPI_PATH = API_DIR / "openapi.json"
WEB_FIXTURES_PATH = API_DIR.parent / "web" / "lib" / "api" / "fixtures.json"


def render(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def artifacts() -> dict[Path, str]:
    from app.api import fixtures
    from app.main import create_app

    return {
        OPENAPI_PATH: render(create_app().openapi()),
        WEB_FIXTURES_PATH: render(fixtures.export()),
    }


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for path, text in artifacts().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        if check:
            stale.append(path)
        else:
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path}")
    for path in stale:
        print(f"stale: {path} (run: uv run python -m app.api.export_openapi)", file=sys.stderr)
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
