import pytest

from app.documents.extract import NO_TEXT_LAYER_REASON, ExtractionError, extract_text
from app.documents.validation import FileKind
from tests.documents.conftest import make_docx, make_pdf, make_pptx, make_scanned_pdf


def test_pdf_pages(sample_pdf) -> None:
    result = extract_text(sample_pdf, FileKind.PDF)
    assert result.status == "ok"
    assert [p.page for p in result.pages] == [1, 2]
    assert "Incorporated in 2014, based in Pune." in result.pages[0].text
    assert "We employ 250 people." in result.pages[1].text
    assert result.page_count == 2
    assert result.pages[0].as_dict() == {
        "page": 1,
        "paragraph": None,
        "text": result.pages[0].text,
    }


def test_pdf_escaped_characters() -> None:
    result = extract_text(make_pdf(["Revenue (FY25) rose"]), "pdf")
    assert "Revenue (FY25) rose" in result.pages[0].text


def test_scanned_pdf_reports_no_text_layer() -> None:
    result = extract_text(make_scanned_pdf(3), FileKind.PDF)
    assert result.status == "no_text_layer"
    assert result.reason == NO_TEXT_LAYER_REASON
    assert result.pages_without_text == [1, 2, 3]
    assert all(not p.has_text_layer and p.text == "" for p in result.pages)


def test_partially_scanned_pdf_is_ok_but_lists_blank_pages() -> None:
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for page in PdfReader(BytesIO(make_pdf(["Text page"]))).pages:
        writer.add_page(page)
    writer.add_blank_page(width=612, height=792)
    buf = BytesIO()
    writer.write(buf)

    result = extract_text(buf.getvalue(), FileKind.PDF)
    assert result.status == "ok"
    assert result.pages_without_text == [2]
    assert result.pages[0].has_text_layer and not result.pages[1].has_text_layer


def test_encrypted_pdf_is_unreadable_not_crash() -> None:
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(BytesIO(make_pdf(["Secret"]))))
    writer.encrypt(user_password="pw", owner_password="owner", algorithm="RC4-128")
    buf = BytesIO()
    writer.write(buf)
    result = extract_text(buf.getvalue(), FileKind.PDF)
    assert result.status == "unreadable"
    assert "password" in (result.reason or "")


def test_pptx_slide_numbers(sample_pptx) -> None:
    result = extract_text(sample_pptx, FileKind.PPTX)
    assert result.status == "ok"
    assert [p.page for p in result.pages] == [1, 2, 3]
    assert result.pages[0].text == "Northwind Storage (fixture)"
    assert result.pages[1].text == "" and not result.pages[1].has_text_layer
    assert result.pages[2].text == "We raised growth funding in 2025"
    assert result.pages_without_text == [2]


def test_pptx_with_no_text_is_no_text_layer() -> None:
    result = extract_text(make_pptx(["", ""]), FileKind.PPTX)
    assert result.status == "no_text_layer"


def test_docx_paragraphs(sample_docx) -> None:
    result = extract_text(sample_docx, FileKind.DOCX)
    assert result.status == "ok"
    texts = [p.text for p in result.pages]
    assert texts[:2] == [
        "Founder ran operations at a national logistics firm.",
        "Contact: ops@fixture.test",
    ]
    assert "Year | Warehouses" in texts and "2025 | 4" in texts
    assert all(p.page is None for p in result.pages)
    # Paragraph indices keep the original position (the blank paragraph is index 1).
    assert [p.paragraph for p in result.pages[:2]] == [0, 2]


def test_empty_docx_is_no_text_layer() -> None:
    assert extract_text(make_docx([]), FileKind.DOCX).status == "no_text_layer"


def test_plain_text_and_markdown() -> None:
    result = extract_text("﻿# Title\r\nLine two\r\n".encode(), FileKind.MD)
    assert result.pages[0].text == "# Title\nLine two"
    assert result.pages[0].page is None
    assert extract_text(b"   \n", FileKind.TXT).status == "no_text_layer"


def test_corrupt_file_raises_extraction_error() -> None:
    with pytest.raises(ExtractionError):
        extract_text(b"%PDF-1.4\ngarbage with no objects", FileKind.PDF)
    with pytest.raises(ExtractionError):
        extract_text(b"PK\x03\x04broken", FileKind.DOCX)
