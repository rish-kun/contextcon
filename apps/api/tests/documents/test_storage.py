from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from app.documents.storage import (
    GCSStorage,
    LocalStorage,
    compute_delete_after,
    object_path,
    storage_from_settings,
)
from app.settings import Settings

NOW = datetime(2026, 11, 22, 10, 30, tzinfo=UTC)


def test_retention_date_calculation() -> None:
    assert compute_delete_after(NOW, 30) == datetime(2026, 12, 22, 10, 30, tzinfo=UTC)
    assert compute_delete_after(NOW, 1) == NOW + timedelta(days=1)
    with pytest.raises(ValueError):
        compute_delete_after(NOW, 0)
    with pytest.raises(ValueError):
        compute_delete_after(datetime(2026, 11, 22), 30)  # naive datetime


def test_object_path_layout_and_guards() -> None:
    assert object_path("case1", "doc_9", "deck.pdf") == "cases/case1/doc_9/deck.pdf"
    for bad in [
        ("../x", "d", "f.pdf"),
        ("c", "d/e", "f.pdf"),
        ("c", "d", "../f.pdf"),
        ("", "d", "f"),
    ]:
        with pytest.raises(ValueError):
            object_path(*bad)


def test_local_storage_roundtrip_and_delete(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "uploads", clock=lambda: NOW)
    path = object_path("case1", "doc1", "deck.pdf")
    delete_after = compute_delete_after(NOW, 30)

    stored = storage.put(path, b"%PDF-1.4 hello", "application/pdf", delete_after)
    assert stored.path == path and stored.size_bytes == 14 and stored.backend == "local"
    assert stored.delete_after == delete_after
    assert len(stored.sha256) == 64
    assert storage.get(path) == b"%PDF-1.4 hello"
    # The local upload folder ignores itself so files can't be committed by accident.
    assert (tmp_path / "uploads" / ".gitignore").read_text() == "*\n"

    with pytest.raises(FileExistsError):
        storage.put(path, b"other", "application/pdf", delete_after)

    record = storage.delete(path)
    assert record.existed and record.path == path and record.deleted_at == NOW
    with pytest.raises(FileNotFoundError):
        storage.get(path)
    assert not (tmp_path / "uploads" / "cases").exists()  # empty folders cleaned up
    assert storage.delete(path).existed is False


def test_local_storage_rejects_escaping_paths(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "uploads")
    with pytest.raises(ValueError):
        storage.put("../outside.txt", b"x", "text/plain", NOW)
    with pytest.raises(ValueError):
        storage.get("cases/../../outside.txt")


def test_local_signed_url_expires_and_checks_signature(tmp_path: Path) -> None:
    clock = {"now": NOW}
    storage = LocalStorage(tmp_path, signing_key=b"k" * 32, clock=lambda: clock["now"])
    path = object_path("case1", "doc1", "deck.pdf")
    storage.put(path, b"data", "application/pdf", NOW)

    url = storage.signed_url(path, timedelta(minutes=5))
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert unquote(parsed.path) == f"/local-files/{path}"
    expires, sig = int(query["expires"][0]), query["sig"][0]
    assert storage.verify_signed_url(path, expires, sig)
    assert not storage.verify_signed_url("cases/case2/doc1/deck.pdf", expires, sig)
    assert not storage.verify_signed_url(path, expires + 60, sig)

    clock["now"] = NOW + timedelta(minutes=6)
    assert not storage.verify_signed_url(path, expires, sig)


def test_signed_url_ttl_is_capped(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    path = object_path("case1", "doc1", "a.txt")
    storage.put(path, b"x", "text/plain", NOW)
    with pytest.raises(ValueError):
        storage.signed_url(path, timedelta(hours=1))
    with pytest.raises(ValueError):
        storage.signed_url(path, timedelta(0))
    with pytest.raises(FileNotFoundError):
        storage.signed_url("cases/case1/doc1/missing.txt")


class _FakeBlob:
    def __init__(self, bucket: "_FakeBucket", name: str) -> None:
        self.bucket, self.name, self.metadata = bucket, name, None

    def upload_from_string(self, data, content_type, if_generation_match=None):
        assert if_generation_match == 0
        self.bucket.objects[self.name] = (data, content_type, self.metadata)

    def download_as_bytes(self):
        return self.bucket.objects[self.name][0]

    def delete(self):
        from google.api_core.exceptions import NotFound

        if self.name not in self.bucket.objects:
            raise NotFound("gone")
        del self.bucket.objects[self.name]

    def generate_signed_url(self, **kwargs):
        self.bucket.sign_calls.append(kwargs)
        return f"https://signed.example/{self.name}"


class _FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, tuple] = {}
        self.sign_calls: list[dict] = []

    def blob(self, name: str) -> _FakeBlob:
        return _FakeBlob(self, name)


class _FakeClient:
    def __init__(self) -> None:
        self.buckets: dict[str, _FakeBucket] = {}

    def bucket(self, name: str) -> _FakeBucket:
        return self.buckets.setdefault(name, _FakeBucket())


class _TokenCreds:
    """Looks like Cloud Run ADC: no private key, signs through IAM."""

    valid = True
    token = "access-token"
    service_account_email = "dealproof-api@example.iam.gserviceaccount.com"


def test_gcs_storage_with_fake_client() -> None:
    client = _FakeClient()
    storage = GCSStorage("uploads", client=client, credentials=_TokenCreds(), clock=lambda: NOW)
    path = object_path("case1", "doc1", "deck.pdf")
    delete_after = compute_delete_after(NOW, 30)

    stored = storage.put(path, b"bytes", "application/pdf", delete_after)
    assert stored.backend == "gcs"
    data, content_type, metadata = client.buckets["uploads"].objects[path]
    assert data == b"bytes" and content_type == "application/pdf"
    assert metadata == {"delete_after": delete_after.isoformat()}
    assert storage.get(path) == b"bytes"

    assert storage.signed_url(path) == f"https://signed.example/{path}"
    call = client.buckets["uploads"].sign_calls[0]
    assert call["version"] == "v4" and call["method"] == "GET"
    assert call["expiration"] == timedelta(minutes=5)
    assert call["service_account_email"] == _TokenCreds.service_account_email
    assert call["access_token"] == "access-token"
    with pytest.raises(ValueError):
        storage.signed_url(path, timedelta(days=1))

    record = storage.delete(path)
    assert record.existed and record.backend == "gcs" and record.deleted_at == NOW
    assert storage.delete(path).existed is False


def test_storage_from_settings_picks_backend(tmp_path: Path) -> None:
    local = storage_from_settings(Settings(_env_file=None, gcs_bucket=""), local_root=tmp_path)
    assert isinstance(local, LocalStorage)
