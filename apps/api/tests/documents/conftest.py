"""Tiny fixture documents built in-test with fictional text (no binary blobs)."""

from __future__ import annotations

import io

import pytest

from tests.db.fixtures import db_url, pg_server, session, sm  # noqa: F401


def _escape_pdf(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[str]) -> bytes:
    """A minimal valid PDF with one line of Helvetica text per page."""
    n = len(pages)
    font_id = 3 + 2 * n
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (
            "<< /Type /Pages /Kids ["
            + " ".join(f"{3 + 2 * i} 0 R" for i in range(n))
            + f"] /Count {n} >>"
        ).encode(),
    ]
    for i, text in enumerate(pages):
        content_id = 4 + 2 * i  # page i is object 3 + 2i, its content stream follows it
        stream = f"BT /F1 12 Tf 72 720 Td ({_escape_pdf(text)}) Tj ET".encode()
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for num, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % num + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    )
    return out.getvalue()


def make_scanned_pdf(n_pages: int = 2) -> bytes:
    """Pages with no text layer, like a scan."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(n_pages):
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def make_pptx(slides: list[str]) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches

    deck = Presentation()
    layout = deck.slide_layouts[6]  # blank
    for text in slides:
        slide = deck.slides.add_slide(layout)
        if text:
            box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1))
            box.text_frame.text = text
    buf = io.BytesIO()
    deck.save(buf)
    return buf.getvalue()


def make_docx(paragraphs: list[str], table: list[list[str]] | None = None) -> bytes:
    from docx import Document

    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    if table:
        t = doc.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, value in enumerate(row):
                t.cell(r, c).text = value
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def sample_pdf() -> bytes:
    return make_pdf(["Incorporated in 2014, based in Pune.", "We employ 250 people."])


@pytest.fixture
def sample_pptx() -> bytes:
    return make_pptx(["Northwind Storage (fixture)", "", "We raised growth funding in 2025"])


@pytest.fixture
def sample_docx() -> bytes:
    return make_docx(
        ["Founder ran operations at a national logistics firm.", "", "Contact: ops@fixture.test"],
        table=[["Year", "Warehouses"], ["2025", "4"]],
    )
