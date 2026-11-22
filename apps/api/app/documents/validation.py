"""Upload checks: size, file type by extension *and* magic bytes, filename sanitizing."""

from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from enum import StrEnum

DEFAULT_MAX_UPLOAD_MB = 25
# Office files are zip archives; refuse ones that would inflate past this (zip bombs).
MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_ZIP_ENTRIES = 5000
MAX_FILENAME_CHARS = 120


class FileKind(StrEnum):
    PDF = "pdf"
    PPTX = "pptx"
    DOCX = "docx"
    TXT = "txt"
    MD = "md"


MIME_TYPES: dict[FileKind, str] = {
    FileKind.PDF: "application/pdf",
    FileKind.PPTX: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    FileKind.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    FileKind.TXT: "text/plain; charset=utf-8",
    FileKind.MD: "text/markdown; charset=utf-8",
}

_EXTENSIONS: dict[str, FileKind] = {
    ".pdf": FileKind.PDF,
    ".pptx": FileKind.PPTX,
    ".docx": FileKind.DOCX,
    ".txt": FileKind.TXT,
    ".md": FileKind.MD,
    ".markdown": FileKind.MD,
}

# Binary signatures that must never be accepted as text.
_BINARY_MAGIC = (b"%PDF", b"PK\x03\x04", b"\xd0\xcf\x11\xe0", b"\x7fELF", b"MZ", b"\x89PNG")


class UploadRejected(ValueError):
    """The upload is refused. ``status_code`` is the HTTP status the API should return."""

    def __init__(self, reason: str, status_code: int = 415) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str  # sanitized
    kind: FileKind
    mime: str
    size_bytes: int


def sanitize_filename(raw: str | None, *, fallback_stem: str = "document") -> str:
    """Return a safe basename: ASCII letters, digits, ``.``, ``-`` and ``_`` only.

    Drops any directory part (either slash style), control characters and leading
    dots, so the result can't be hidden, traverse paths or break a header. The
    extension is lower-cased and kept when the name is truncated.
    """
    name = unicodedata.normalize("NFKC", raw or "")
    name = re.split(r"[\\/]", name)[-1]
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    name = re.sub(r"_{2,}", "_", name)
    name = re.sub(r"\.{2,}", ".", name)

    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    ext = re.sub(r"[^a-z0-9]", "", ext.lower())
    stem = stem.strip("._- ") or fallback_stem
    suffix = f".{ext}" if ext else ""
    stem = stem[: max(1, MAX_FILENAME_CHARS - len(suffix))].rstrip("._-") or fallback_stem
    return f"{stem}{suffix}"


def kind_from_extension(filename: str) -> FileKind | None:
    dot = filename.rfind(".")
    if dot < 0:
        return None
    return _EXTENSIONS.get(filename[dot:].lower())


def _office_kind(data: bytes) -> FileKind | None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise UploadRejected("Archive has too many entries.", 422)
            if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
                raise UploadRejected("Archive expands to an unsafe size.", 422)
            names = {i.filename for i in infos}
    except zipfile.BadZipFile:
        return None
    if "[Content_Types].xml" not in names:
        return None
    if "ppt/presentation.xml" in names:
        return FileKind.PPTX
    if "word/document.xml" in names:
        return FileKind.DOCX
    return None


def sniff_kind(data: bytes) -> FileKind | None:
    """Detect the file type from its content, ignoring the name."""
    if data.startswith(b"%PDF-"):
        return FileKind.PDF
    if data.startswith(b"PK\x03\x04"):
        return _office_kind(data)
    if data.startswith(_BINARY_MAGIC) or b"\x00" in data[:8192]:
        return None
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return FileKind.TXT


def validate_upload(
    filename: str | None, data: bytes, *, max_bytes: int = DEFAULT_MAX_UPLOAD_MB * 1024 * 1024
) -> ValidatedUpload:
    """Check size, extension and content; return the sanitized name and detected kind."""
    if len(data) > max_bytes:
        raise UploadRejected(f"File is larger than {max_bytes // (1024 * 1024)} MB.", 413)
    if not data:
        raise UploadRejected("File is empty.", 400)

    clean = sanitize_filename(filename)
    claimed = kind_from_extension(clean)
    if claimed is None:
        raise UploadRejected("Only PDF, PPTX, DOCX, TXT and MD files are accepted.", 415)

    sniffed = sniff_kind(data)
    text_kinds = {FileKind.TXT, FileKind.MD}
    matches = sniffed == claimed or (claimed in text_kinds and sniffed == FileKind.TXT)
    if not matches:
        raise UploadRejected(f"File content does not match its .{claimed.value} extension.", 415)
    return ValidatedUpload(
        filename=clean, kind=claimed, mime=MIME_TYPES[claimed], size_bytes=len(data)
    )
