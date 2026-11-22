"""Text extraction, one entry per PDF page / PPTX slide / DOCX paragraph.

No OCR. A PDF with no text layer (a scan) comes back with
``status == "no_text_layer"`` and a reason, so the claim pipeline can mark its
claims *Not checked* with that reason instead of silently finding nothing.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

from app.documents.validation import FileKind

ExtractionStatus = Literal["ok", "no_text_layer", "unreadable"]

NO_TEXT_LAYER_REASON = (
    "The document has no text layer (it looks like a scan or images only), "
    "so its claims could not be read. Upload a text-based PDF to check them."
)


@dataclass(frozen=True)
class PageText:
    """``page`` is the 1-based PDF page or slide number; None for DOCX and plain text.

    ``paragraph`` is the 0-based paragraph index for DOCX, else None.
    """

    page: int | None
    text: str
    paragraph: int | None = None
    has_text_layer: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {"page": self.page, "paragraph": self.paragraph, "text": self.text}


@dataclass(frozen=True)
class ExtractionResult:
    pages: list[PageText]
    status: ExtractionStatus = "ok"
    reason: str | None = None
    pages_without_text: list[int] = field(default_factory=list)

    @property
    def page_count(self) -> int | None:
        nums = [p.page for p in self.pages if p.page is not None]
        return max(nums) if nums else None


class ExtractionError(ValueError):
    """The file passed validation but could not be parsed."""


@dataclass(frozen=True)
class ExtractionLimits:
    """Bounds on what one upload may cost to parse.

    ``max_pages`` caps PDF pages / PPTX slides / DOCX paragraphs plus table rows, and
    ``max_chars`` caps the extracted text, both checked while parsing. ``timeout_seconds``
    and ``memory_mb`` apply when extraction runs in the sandbox subprocess
    (``app.documents.sandbox.extract_text_isolated``).
    """

    max_pages: int = 500
    max_chars: int = 2_000_000
    timeout_seconds: float = 60.0
    memory_mb: int = 1024


DEFAULT_LIMITS = ExtractionLimits()


class _Budget:
    def __init__(self, limits: ExtractionLimits) -> None:
        self.limits = limits
        self.chars = 0

    def check_pages(self, n: int, unit: str) -> None:
        if n > self.limits.max_pages:
            raise ExtractionError(
                f"The file has more than {self.limits.max_pages} {unit}; split it and upload "
                "the parts separately."
            )

    def take(self, text: str) -> str:
        self.chars += len(text)
        if self.chars > self.limits.max_chars:
            raise ExtractionError(
                f"The file holds more than {self.limits.max_chars:,} characters of text; "
                "upload a shorter document."
            )
        return text


def extract_text(
    data: bytes, kind: FileKind | str, *, limits: ExtractionLimits = DEFAULT_LIMITS
) -> ExtractionResult:
    kind = FileKind(kind)
    budget = _Budget(limits)
    try:
        if kind is FileKind.PDF:
            return _extract_pdf(data, budget)
        if kind is FileKind.PPTX:
            return _extract_pptx(data, budget)
        if kind is FileKind.DOCX:
            return _extract_docx(data, budget)
        return _extract_plain(data, budget)
    except ExtractionError:
        raise
    except Exception as exc:  # parser libraries raise many types on malformed files
        raise ExtractionError(f"Could not read the {kind.value.upper()} file.") from exc


def _extract_pdf(data: bytes, budget: _Budget) -> ExtractionResult:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        return ExtractionResult(
            pages=[],
            status="unreadable",
            reason="The PDF is password-protected, so its text could not be read.",
        )

    budget.check_pages(len(reader.pages), "pages")
    pages: list[PageText] = []
    empty: list[int] = []
    for number, page in enumerate(reader.pages, start=1):
        text = budget.take(_clean(page.extract_text() or ""))
        has_text = bool(text.strip())
        if not has_text:
            empty.append(number)
        pages.append(PageText(page=number, text=text, has_text_layer=has_text))

    if pages and len(empty) == len(pages):
        return ExtractionResult(
            pages=pages,
            status="no_text_layer",
            reason=NO_TEXT_LAYER_REASON,
            pages_without_text=empty,
        )
    return ExtractionResult(pages=pages, pages_without_text=empty)


def _shape_texts(shapes: Any) -> Iterator[str]:
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _shape_texts(shape.shapes)
            continue
        if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
            text = shape.text_frame.text
            if text.strip():
                yield text
        if getattr(shape, "has_table", False) and shape.has_table:
            for row in shape.table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    yield " | ".join(cells)


def _extract_pptx(data: bytes, budget: _Budget) -> ExtractionResult:
    from pptx import Presentation

    deck = Presentation(io.BytesIO(data))
    budget.check_pages(len(deck.slides), "slides")
    pages: list[PageText] = []
    empty: list[int] = []
    for number, slide in enumerate(deck.slides, start=1):
        text = budget.take(_clean("\n".join(_shape_texts(slide.shapes))))
        has_text = bool(text.strip())
        if not has_text:
            empty.append(number)
        pages.append(PageText(page=number, text=text, has_text_layer=has_text))
    if pages and len(empty) == len(pages):
        return ExtractionResult(
            pages=pages,
            status="no_text_layer",
            reason="The slides contain no text (images only), so no claims could be read.",
            pages_without_text=empty,
        )
    return ExtractionResult(pages=pages, pages_without_text=empty)


def _extract_docx(data: bytes, budget: _Budget) -> ExtractionResult:
    from docx import Document

    doc = Document(io.BytesIO(data))
    texts = [p.text for p in doc.paragraphs]
    # Paragraphs and table rows are the DOCX "pages": cap them like pages, at 50x.
    unit_cap = budget.limits.max_pages * 50
    for table in doc.tables:
        for row in table.rows:
            if len(texts) > unit_cap:
                break
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            texts.append(" | ".join(dict.fromkeys(cells)))  # merged cells repeat
    if len(texts) > unit_cap:
        raise ExtractionError(
            f"The document has more than {unit_cap:,} paragraphs; upload a shorter document."
        )
    pages = [
        PageText(page=None, paragraph=i, text=budget.take(_clean(t)))
        for i, t in enumerate(texts)
        if t.strip()
    ]
    if not pages:
        return ExtractionResult(
            pages=[],
            status="no_text_layer",
            reason="The document contains no text, so no claims could be read.",
        )
    return ExtractionResult(pages=pages)


def _extract_plain(data: bytes, budget: _Budget) -> ExtractionResult:
    text = budget.take(_clean(data.decode("utf-8-sig")))
    if not text.strip():
        return ExtractionResult(
            pages=[], status="no_text_layer", reason="The file contains no text."
        )
    return ExtractionResult(pages=[PageText(page=None, text=text)])


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()
