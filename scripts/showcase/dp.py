"""A tiny stdlib client for the live DealProof site, used to build the public showcase.

It signs in as the demo analyst through the web origin's same-origin `/api/*` proxy,
exactly as the browser does, and drives the real routes. Nothing here computes a
result: every record comes back from the deployed pipelines.

Credentials are read from the file named by `DEALPROOF_DEMO_ENV` (KEY=VALUE lines:
`DEMO_ANALYST_EMAIL`, `DEMO_ANALYST_PASSWORD`). They are never printed.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

WEB = os.environ.get("DEALPROOF_WEB", "https://dealproof-web-527967664479.asia-south1.run.app")


def _read_env(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


class ApiError(RuntimeError):
    def __init__(self, status: int, body: str, path: str) -> None:
        super().__init__(f"{status} on {path}: {body[:800]}")
        self.status = status
        self.body = body


class Client:
    def __init__(self, web: str = WEB) -> None:
        self.web = web.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def _req(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        raw: bytes | None = None,
        ctype: str | None = None,
        timeout: float = 180,
    ) -> Any:
        data = raw
        headers = {"origin": self.web, "accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode()
            headers["content-type"] = "application/json"
        elif ctype:
            headers["content-type"] = ctype
        req = urllib.request.Request(
            f"{self.web}/api{path}", data=data, method=method, headers=headers
        )
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                text = resp.read().decode()
        except urllib.error.HTTPError as exc:
            raise ApiError(exc.code, exc.read().decode(errors="replace"), path) from None
        return json.loads(text) if text else None

    def get(self, path: str) -> Any:
        return self._req("GET", path)

    def post(self, path: str, body: Any = None, timeout: float = 180) -> Any:
        return self._req("POST", path, body if body is not None else {}, timeout=timeout)

    def put(self, path: str, body: Any) -> Any:
        return self._req("PUT", path, body)

    def patch(self, path: str, body: Any) -> Any:
        return self._req("PATCH", path, body)

    def login(self, env_file: str | None = None, role: str = "ANALYST") -> dict[str, Any]:
        env = _read_env(env_file or os.environ["DEALPROOF_DEMO_ENV"])
        me = self.post(
            "/auth/login",
            {
                "email": env[f"DEMO_{role}_EMAIL"],
                "password": env[f"DEMO_{role}_PASSWORD"],
            },
        )
        return {"id": me["id"], "display_name": me["display_name"]}

    def upload(self, case_id: str, path: str, kind: str, mime: str) -> Any:
        boundary = uuid.uuid4().hex
        name = Path(path).name
        parts = [
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="kind"\r\n\r\n{kind}\r\n'
            ).encode(),
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                f'filename="{name}"\r\nContent-Type: {mime}\r\n\r\n'
            ).encode()
            + Path(path).read_bytes()
            + b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        return self._req(
            "POST",
            f"/cases/{case_id}/documents",
            raw=b"".join(parts),
            ctype=f"multipart/form-data; boundary={boundary}",
        )

    def wait_run(self, run_id: str, *, every: float = 5, limit: float = 1800) -> dict[str, Any]:
        """Poll a run until it is no longer pending or running. Prints step progress."""
        start = time.time()
        seen: dict[str, str] = {}
        while True:
            run = self.get(f"/runs/{run_id}")
            for s in run.get("steps", []):
                state = s.get("state")
                if seen.get(s["key"]) != state:
                    seen[s["key"]] = state
                    print(
                        f"  [{run['state']}] {s['key']}: {state} {s.get('result') or ''}",
                        file=sys.stderr,
                    )
            if run["state"] not in ("pending", "running"):
                return run
            if time.time() - start > limit:
                raise TimeoutError(f"run {run_id} still {run['state']}")
            time.sleep(every)


def save(obj: Any, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
