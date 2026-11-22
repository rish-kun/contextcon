import io
import zipfile

import pytest

from app.documents.validation import (
    FileKind,
    UploadRejected,
    sanitize_filename,
    sniff_kind,
    validate_upload,
)


def test_accepts_each_supported_type(sample_pdf, sample_pptx, sample_docx) -> None:
    cases = [
        ("deck.pdf", sample_pdf, FileKind.PDF),
        ("deck.PPTX", sample_pptx, FileKind.PPTX),
        ("memo.docx", sample_docx, FileKind.DOCX),
        ("notes.txt", b"Plain notes", FileKind.TXT),
        ("notes.md", "# Heading\n\u20b9 50 crore".encode(), FileKind.MD),
    ]
    for name, data, kind in cases:
        result = validate_upload(name, data)
        assert result.kind is kind
        assert result.size_bytes == len(data)


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("deck.pdf", b"PK\x03\x04 not a pdf at all"),
        ("deck.pdf", b"Just some text pretending"),
        ("memo.docx", b"%PDF-1.4 renamed pdf"),
        ("notes.txt", b"%PDF-1.4 a pdf renamed to txt"),
        ("notes.txt", b"MZ\x90\x00 executable"),
        ("notes.txt", b"\xff\xfe\x00\x00 not utf8"),
    ],
)
def test_rejects_content_that_does_not_match_extension(name: str, data: bytes) -> None:
    with pytest.raises(UploadRejected) as exc:
        validate_upload(name, data)
    assert exc.value.status_code == 415


def test_pptx_renamed_to_docx_is_rejected(sample_pptx) -> None:
    with pytest.raises(UploadRejected) as exc:
        validate_upload("memo.docx", sample_pptx)
    assert exc.value.status_code == 415


def test_plain_zip_is_not_office() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.txt", "hi")
    assert sniff_kind(buf.getvalue()) is None
    with pytest.raises(UploadRejected):
        validate_upload("deck.pptx", buf.getvalue())


def test_rejects_unsupported_extension() -> None:
    with pytest.raises(UploadRejected) as exc:
        validate_upload("run.exe", b"hello")
    assert exc.value.status_code == 415
    with pytest.raises(UploadRejected):
        validate_upload("no_extension", b"hello")


def test_rejects_oversize_file() -> None:
    limit = 1024
    with pytest.raises(UploadRejected) as exc:
        validate_upload("notes.txt", b"a" * (limit + 1), max_bytes=limit)
    assert exc.value.status_code == 413
    assert validate_upload("notes.txt", b"a" * limit, max_bytes=limit).size_bytes == limit


def test_default_limit_is_25_mb() -> None:
    big = b"a" * (25 * 1024 * 1024 + 1)
    with pytest.raises(UploadRejected) as exc:
        validate_upload("notes.txt", big)
    assert exc.value.status_code == 413


def test_rejects_empty_file() -> None:
    with pytest.raises(UploadRejected) as exc:
        validate_upload("notes.txt", b"")
    assert exc.value.status_code == 400


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\a\\Deck Final (v2).PDF", "Deck_Final_v2.pdf"),
        ("..pdf", "document.pdf"),
        (".hidden.docx", "hidden.docx"),
        ("Pitch\x00\nDeck.pptx", "Pitch_Deck.pptx"),
        ("Résumé – Q3.docx", "Resume_Q3.docx"),
        ("", "document"),
        (None, "document"),
        ("a" * 300 + ".pdf", "a" * 116 + ".pdf"),
        ('evil"; filename=x.pdf', "evil_filename_x.pdf"),
    ],
)
def test_sanitize_filename(raw, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_sanitized_name_has_no_path_or_unsafe_chars() -> None:
    for raw in ["../a.pdf", "a/b/c.pdf", "\\\\server\\share\\x.pdf", "a b<>|?*.pdf"]:
        name = sanitize_filename(raw)
        assert "/" not in name and "\\" not in name
        assert not name.startswith(".")
        assert all(c.isalnum() or c in "._-" for c in name)


def test_zip_bomb_rejected(monkeypatch) -> None:
    import app.documents.validation as v

    monkeypatch.setattr(v, "MAX_UNCOMPRESSED_BYTES", 1000)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "x")
        zf.writestr("word/document.xml", "0" * 5000)
    with pytest.raises(UploadRejected) as exc:
        validate_upload("memo.docx", buf.getvalue())
    assert exc.value.status_code == 422
