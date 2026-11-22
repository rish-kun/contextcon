"""Object storage for uploaded case documents.

Objects live under ``cases/<case_id>/<doc_id>/<filename>``. Two backends share one
interface:

- ``GCSStorage``: a private Google Cloud Storage bucket, authenticated with
  Application Default Credentials. A bucket lifecycle rule does the scheduled
  deletion; each object also carries its ``delete_after`` in metadata.
- ``LocalStorage``: a directory on disk, for development and tests.

Download links are short-lived signed URLs. The storage layer only signs; deciding
who may receive a link is the service layer's job (see ``service.download_url``).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import quote, urlencode

DEFAULT_URL_TTL = timedelta(minutes=5)
MAX_URL_TTL = timedelta(minutes=15)

_ID_ALLOWED = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


def compute_delete_after(now: datetime, retention_days: int) -> datetime:
    """Return the moment an upload made at ``now`` must be deleted."""
    if retention_days <= 0:
        raise ValueError("retention_days must be positive")
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now + timedelta(days=retention_days)


def object_path(case_id: str, document_id: str, filename: str) -> str:
    """Build ``cases/<case_id>/<doc_id>/<filename>``.

    ``filename`` must already be sanitized; ids must be plain tokens so a crafted
    id cannot climb out of its case prefix.
    """
    for label, value in (("case_id", case_id), ("document_id", document_id)):
        if not value or not set(value) <= _ID_ALLOWED:
            raise ValueError(f"{label} must be a non-empty token of letters, digits, - or _")
    if not filename or "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise ValueError("filename must be a sanitized basename")
    return f"cases/{case_id}/{document_id}/{filename}"


def case_prefix(case_id: str) -> str:
    return f"cases/{case_id}/"


@dataclass(frozen=True)
class StoredObject:
    path: str
    size_bytes: int
    sha256: str
    content_type: str
    delete_after: datetime
    backend: Literal["gcs", "local"]


@dataclass(frozen=True)
class DeletionRecord:
    path: str
    existed: bool
    deleted_at: datetime
    backend: Literal["gcs", "local"]


class DocumentStorage(Protocol):
    backend: Literal["gcs", "local"]

    def put(
        self, path: str, data: bytes, content_type: str, delete_after: datetime
    ) -> StoredObject: ...

    def get(self, path: str) -> bytes: ...

    def signed_url(self, path: str, ttl: timedelta = DEFAULT_URL_TTL) -> str: ...

    def delete(self, path: str) -> DeletionRecord: ...


def _check_ttl(ttl: timedelta) -> None:
    if ttl <= timedelta(0) or ttl > MAX_URL_TTL:
        raise ValueError(f"signed URL ttl must be between 0 and {MAX_URL_TTL}")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalStorage:
    """Filesystem backend. Signed URLs are HMAC tokens checked by ``verify_signed_url``."""

    backend: Literal["local"] = "local"

    def __init__(
        self,
        root: Path,
        *,
        signing_key: bytes | None = None,
        url_base: str = "/local-files",
        clock: Any = None,
    ) -> None:
        self.root = Path(root).resolve()
        self._key = signing_key or secrets.token_bytes(32)
        self._url_base = url_base.rstrip("/")
        self._clock = clock or (lambda: datetime.now(UTC))

    def _resolve(self, path: str) -> Path:
        target = (self.root / path).resolve()
        if not target.is_relative_to(self.root) or target == self.root:
            raise ValueError("path escapes the storage root")
        return target

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        ignore = self.root / ".gitignore"
        if not ignore.exists():
            # Uploaded documents must never be committed by accident.
            ignore.write_text("*\n")

    def put(
        self, path: str, data: bytes, content_type: str, delete_after: datetime
    ) -> StoredObject:
        self._ensure_root()
        target = self._resolve(path)
        if target.exists():
            raise FileExistsError(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return StoredObject(
            path=path,
            size_bytes=len(data),
            sha256=_sha256(data),
            content_type=content_type,
            delete_after=delete_after,
            backend=self.backend,
        )

    def get(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    def _signature(self, path: str, expires: int) -> str:
        msg = f"{path}\n{expires}".encode()
        return hmac.new(self._key, msg, hashlib.sha256).hexdigest()

    def signed_url(self, path: str, ttl: timedelta = DEFAULT_URL_TTL) -> str:
        _check_ttl(ttl)
        if not self._resolve(path).is_file():
            raise FileNotFoundError(path)
        expires = int((self._clock() + ttl).timestamp())
        query = urlencode({"expires": expires, "sig": self._signature(path, expires)})
        return f"{self._url_base}/{quote(path)}?{query}"

    def verify_signed_url(self, path: str, expires: int, sig: str) -> bool:
        if self._clock().timestamp() > expires:
            return False
        return hmac.compare_digest(self._signature(path, expires), sig)

    def delete(self, path: str) -> DeletionRecord:
        target = self._resolve(path)
        existed = target.is_file()
        if existed:
            target.unlink()
            # Remove now-empty <doc_id>/ and <case_id>/ folders, never the root.
            parent = target.parent
            while parent != self.root and parent.is_relative_to(self.root):
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        return DeletionRecord(
            path=path, existed=existed, deleted_at=self._clock(), backend=self.backend
        )


class GCSStorage:
    """Private GCS bucket backend using Application Default Credentials.

    ``client`` and ``credentials`` are injectable so tests never touch the network.
    """

    backend: Literal["gcs"] = "gcs"

    def __init__(
        self,
        bucket: str,
        *,
        client: Any = None,
        credentials: Any = None,
        clock: Any = None,
    ) -> None:
        if not bucket:
            raise ValueError("bucket is required")
        if client is None:
            from google.cloud import storage as gcs  # imported lazily: heavy, GCS-only

            client = gcs.Client()
        self._client = client
        self._bucket = client.bucket(bucket)
        self._credentials = credentials
        self._clock = clock or (lambda: datetime.now(UTC))

    def put(
        self, path: str, data: bytes, content_type: str, delete_after: datetime
    ) -> StoredObject:
        blob = self._bucket.blob(path)
        blob.metadata = {"delete_after": delete_after.isoformat()}
        # if_generation_match=0: fail rather than overwrite an existing object.
        blob.upload_from_string(data, content_type=content_type, if_generation_match=0)
        return StoredObject(
            path=path,
            size_bytes=len(data),
            sha256=_sha256(data),
            content_type=content_type,
            delete_after=delete_after,
            backend=self.backend,
        )

    def get(self, path: str) -> bytes:
        return self._bucket.blob(path).download_as_bytes()

    def _signing_kwargs(self) -> dict[str, Any]:
        """Credentials without a private key (Cloud Run, ADC user login) sign via IAM.

        For those, pass the service account email plus a fresh access token so the
        library calls ``signBlob`` instead of signing locally.
        """
        from google.auth.credentials import Signing

        creds = self._credentials
        if creds is None:
            import google.auth

            creds, _ = google.auth.default()
            self._credentials = creds
        if isinstance(creds, Signing):
            return {"credentials": creds}
        from google.auth.transport.requests import Request

        if not creds.valid:
            creds.refresh(Request())
        email = getattr(creds, "service_account_email", None)
        if not email:
            raise RuntimeError("signed URLs need service-account credentials")
        return {"service_account_email": email, "access_token": creds.token}

    def signed_url(self, path: str, ttl: timedelta = DEFAULT_URL_TTL) -> str:
        _check_ttl(ttl)
        blob = self._bucket.blob(path)
        filename = path.rsplit("/", 1)[-1]
        return blob.generate_signed_url(
            version="v4",
            expiration=ttl,
            method="GET",
            response_disposition=f'attachment; filename="{filename}"',
            **self._signing_kwargs(),
        )

    def delete(self, path: str) -> DeletionRecord:
        from google.api_core.exceptions import NotFound

        existed = True
        try:
            self._bucket.blob(path).delete()
        except NotFound:
            existed = False
        return DeletionRecord(
            path=path, existed=existed, deleted_at=self._clock(), backend=self.backend
        )


DEFAULT_LOCAL_ROOT = Path(__file__).resolve().parents[2] / ".data" / "uploads"


def storage_from_settings(settings: Any, *, local_root: Path | None = None) -> DocumentStorage:
    """GCS when ``GCS_BUCKET`` is set, otherwise local disk under ``apps/api/.data/uploads``."""
    bucket = getattr(settings, "gcs_bucket", "") or ""
    if bucket:
        return GCSStorage(bucket)
    return LocalStorage(local_root or DEFAULT_LOCAL_ROOT)
