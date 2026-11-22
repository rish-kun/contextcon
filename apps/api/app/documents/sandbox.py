"""Run text extraction in a child process with a time limit and a memory guard.

Parsers (pypdf, python-pptx, python-docx) run on untrusted uploads. A crafted file can
make them loop or allocate without bound, so ingestion runs them here:

- a fresh ``python -m app.documents.sandbox`` process reads the file on stdin;
- before parsing, it caps its own address space (``RLIMIT_AS``, where the OS enforces
  it, as on Linux/Cloud Run) and CPU time (``RLIMIT_CPU``);
- the parent kills it after ``timeout_seconds`` of wall time;
- page and output caps (``ExtractionLimits``) apply inside, as in-process.

Any failure (timeout, memory exhausted, crash) becomes an ``ExtractionError``, which the
ingestion service turns into a 422 for the uploader.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.documents.extract import (
    DEFAULT_LIMITS,
    ExtractionError,
    ExtractionLimits,
    ExtractionResult,
    PageText,
    extract_text,
)
from app.documents.validation import FileKind

_API_DIR = Path(__file__).resolve().parents[2]


def extract_text_isolated(
    data: bytes, kind: FileKind | str, *, limits: ExtractionLimits = DEFAULT_LIMITS
) -> ExtractionResult:
    kind = FileKind(kind)
    args = [
        sys.executable,
        "-m",
        "app.documents.sandbox",
        kind.value,
        str(limits.max_pages),
        str(limits.max_chars),
        str(limits.memory_mb),
        str(max(1, math.ceil(limits.timeout_seconds))),
    ]
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "LC_ALL", "TMPDIR"}}
    env["PYTHONPATH"] = str(_API_DIR)
    try:
        proc = subprocess.run(
            args,
            input=data,
            capture_output=True,
            timeout=limits.timeout_seconds,
            cwd=_API_DIR,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExtractionError(
            "Reading the file took too long; upload a smaller or simpler document."
        ) from exc
    if proc.returncode != 0:
        raise ExtractionError(
            "The file could not be read within the memory and time limits; upload a smaller "
            "or simpler document."
        )
    try:
        out = json.loads(proc.stdout)
    except ValueError as exc:
        raise ExtractionError(f"Could not read the {kind.value.upper()} file.") from exc
    if "error" in out:
        raise ExtractionError(str(out["error"]))
    return ExtractionResult(
        pages=[
            PageText(
                page=p["page"],
                text=p["text"],
                paragraph=p["paragraph"],
                has_text_layer=p["has_text_layer"],
            )
            for p in out["pages"]
        ],
        status=out["status"],
        reason=out["reason"],
        pages_without_text=list(out["pages_without_text"]),
    )


def _limit_resources(memory_mb: int, cpu_seconds: int) -> None:
    try:
        import resource
    except ImportError:  # pragma: no cover - not on POSIX
        return
    for name, value in (
        ("RLIMIT_AS", memory_mb * 1024 * 1024),
        ("RLIMIT_CPU", cpu_seconds),
    ):
        which = getattr(resource, name, None)
        if which is None:
            continue
        try:
            _, hard = resource.getrlimit(which)
            if hard != resource.RLIM_INFINITY:
                value = min(value, hard)
            resource.setrlimit(which, (value, hard))
        except (ValueError, OSError):  # some platforms (macOS) do not enforce RLIMIT_AS
            pass


def _serialise(result: ExtractionResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "reason": result.reason,
        "pages_without_text": result.pages_without_text,
        "pages": [
            {
                "page": p.page,
                "paragraph": p.paragraph,
                "text": p.text,
                "has_text_layer": p.has_text_layer,
            }
            for p in result.pages
        ],
    }


def main(argv: list[str]) -> int:
    kind, max_pages, max_chars, memory_mb, cpu_seconds = argv
    data = sys.stdin.buffer.read()
    # Import the parsers before the address-space cap, so the cap measures parsing.
    import docx  # noqa: F401
    import pptx  # noqa: F401
    import pypdf  # noqa: F401

    _limit_resources(int(memory_mb), int(cpu_seconds))
    limits = ExtractionLimits(max_pages=int(max_pages), max_chars=int(max_chars))
    try:
        out = _serialise(extract_text(data, kind, limits=limits))
    except ExtractionError as exc:
        out = {"error": str(exc)}
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
