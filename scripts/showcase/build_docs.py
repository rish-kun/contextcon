"""Build the two public documents the showcase case is given, from fetched pages.

Input: the JSON files `fetch_site.py` wrote (Crustdata `/web/enrich/live`, text made by
DealProof's own `html_to_text`, which already redacts emails and phone numbers).
Output: two text PDFs (stdlib only, no new dependency), one source page per PDF page,
each page headed by its URL and retrieval date so every extracted claim keeps its source.

What is kept is decided here, in code, and recorded in `sections.json`:
- the company's own words, verbatim, in page order;
- dropped: site navigation, cookie banners, the chat widget, product feature lists and
  the FAQ (generic product copy, not statements about the company), descriptions of
  third-party clients (statements about other companies), and contact lines (email,
  phone, fax, a named contact person).

Usage: python build_docs.py WEB_DIR WEB2_DIR OUT_DIR
"""

from __future__ import annotations

import json
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path

CONTACT_PREFIXES = ("Email:", "Telephone:", "Call:", "Whatsapp:", "Fax:", "Contact Person:")


def load(d: Path, name: str) -> dict:
    return json.loads((d / f"{name}.json").read_text())


def chrome_cut(text: str) -> str:
    """Drop the trailing cookie banner and chat widget the fetcher captured."""
    return text.split("```html", 1)[0].strip()


def between(text: str, start: str, end: str | None) -> str:
    i = text.index(start)
    j = text.index(end, i) if end else len(text)
    return text[i:j].strip()


def one_carousel_cycle(text: str) -> str:
    """The testimonial carousel is captured more than once; keep the first cycle."""
    lines = text.splitlines()
    first_quote = next(i for i, line in enumerate(lines) if line.startswith('"'))
    for i in range(first_quote + 1, len(lines)):
        if lines[i] == lines[first_quote]:
            return "\n".join(lines[:i])
    return text


def retrieved(page: dict) -> str:
    ts = page.get("timestamp")
    return datetime.fromtimestamp(ts, UTC).date().isoformat() if ts else "2026-11-22"


# --- Minimal PDF writer (Helvetica, WinAnsi) ------------------------------------------


def _pdf_str(s: str) -> str:
    raw = s.replace("₹", "Rs.").encode("cp1252", errors="replace").decode("latin-1")
    return raw.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(path: Path, pages: list[list[tuple[str, int]]], title: str) -> None:
    """`pages`: per page, (line, font size) pairs top to bottom."""
    objs: list[bytes] = []

    def add(body: str | bytes) -> int:
        objs.append(body.encode("latin-1") if isinstance(body, str) else body)
        return len(objs)

    font = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    bold = add(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    )
    pages_id = len(objs) + 1 + 2 * len(pages)  # placeholder index computed below
    kids = []
    for lines in pages:
        y = 800
        ops = ["BT"]
        for text, size in lines:
            f = "F2" if size >= 11 else "F1"
            ops.append(f"/{f} {size} Tf 1 0 0 1 50 {y} Tm ({_pdf_str(text)}) Tj")
            y -= size + 4
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page = add(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font} 0 R /F2 {bold} 0 R >> >> "
            f"/Contents {content} 0 R >>"
        )
        kids.append(page)
    assert pages_id == len(objs) + 1
    add(f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>")
    info = add(f"<< /Title ({_pdf_str(title)}) /Producer (DealProof showcase build_docs.py) >>")
    catalog = add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objs) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n"
    ).encode()
    path.write_bytes(bytes(out))


def paginate(sections: list[dict], per_page: int = 52) -> list[list[tuple[str, int]]]:
    pages: list[list[tuple[str, int]]] = []
    for s in sections:
        header = [
            (f"Source: {s['url']}", 11),
            (f"Retrieved {s['retrieved']} through Crustdata live web fetch (/web/enrich/live)", 8),
            ("", 8),
        ]
        body: list[tuple[str, int]] = []
        for para in s["text"].splitlines():
            para = para.strip()
            if not para:
                continue
            for line in textwrap.wrap(para, 100) or [""]:
                body.append((line, 9))
        while body:
            chunk, body = body[:per_page], body[per_page:]
            pages.append(header + chunk)
            header = [(f"Source: {s['url']} (continued)", 11), ("", 8)]
    return pages


# --- The two documents ----------------------------------------------------------------


def website_sections(web: Path) -> list[dict]:
    home = load(web, "www_onpalms_com")
    t = chrome_cut(home["text"])
    home_text = "\n".join(
        [
            between(t, "Best Warehouse Management System for", "PALMS™ Products"),
            between(t, "About PALMS™", "Industries We Serve"),
            "Industries We Serve",
            "\n".join(between(t, "Industries We Serve", "Inventory tracking").splitlines()[1:]),
            one_carousel_cycle(between(t, "99% positive feedback", "FAQ")),
        ]
    )
    about = load(web, "www_onpalms_com_about_us")
    clients = load(web, "www_onpalms_com_clients")
    ct = chrome_cut(clients["text"])
    lines = ct.splitlines()
    names = []
    for i, line in enumerate(lines):
        if line.startswith("www.") and i >= 2:
            # The client's name is the last short line before its description paragraphs.
            j = i - 1
            while j > 0 and len(lines[j]) > 80:
                j -= 1
            names.append(lines[j])
    client_text = "Our prestigious clients include:-\n" + "\n".join(names)
    contact = load(web, "www_onpalms_com_contact")
    offices = between(chrome_cut(contact["text"]), "India", "Contact Form")
    offices = "\n".join(
        line for line in offices.splitlines() if not line.strip().startswith(CONTACT_PREFIXES)
    )
    partners = load(web, "www_onpalms_com_technology_partners")
    corp = load(web, "www_technoforte_co_in")
    c = chrome_cut(corp["text"])
    corp_text = "\n".join(
        [
            between(c, "Countries", "About Us"),
            between(c, "About Us", "Gain Success With Us!"),
            between(c, "Manufacturing\nTechnoforte has been", "Warehousing\n"),
        ]
    )
    return [
        {
            "url": "https://www.onpalms.com/",
            "retrieved": retrieved(home),
            "text": home_text,
            "kept": "hero, About, Industries We Serve (names), Testimonials",
        },
        {
            "url": "https://www.onpalms.com/about-us/",
            "retrieved": retrieved(about),
            "text": chrome_cut(about["text"]).removeprefix("WMS - Onpalms").strip(),
            "kept": "whole page",
        },
        {
            "url": "https://www.onpalms.com/clients/",
            "retrieved": retrieved(clients),
            "text": client_text,
            "kept": "client names only (descriptions are about the clients)",
        },
        {
            "url": "https://www.onpalms.com/contact/",
            "retrieved": retrieved(contact),
            "text": offices,
            "kept": "office names and addresses (no email, phone or contact person)",
        },
        {
            "url": "https://www.onpalms.com/technology-partners/",
            "retrieved": retrieved(partners),
            "text": chrome_cut(partners["text"]),
            "kept": "whole page",
        },
        {
            "url": "https://www.technoforte.co.in/",
            "retrieved": retrieved(corp),
            "text": corp_text,
            "kept": "headline figures, About Us, Manufacturing and Automobile paragraphs",
        },
    ]


def registry_sections(web2: Path) -> list[dict]:
    z = load(web2, "www_zaubacorp_com_TECHNOFORTE_SOFTWARE_PRIVATE_LIMITED_U72200KA2001PTC029189")
    t = between(chrome_cut(z["text"]), "TECHNOFORTE SOFTWARE PRIVATE LIMITED\nCIN:", "About the Report")
    drop = ("Purchase Report", "This information is part of the paid company report.")
    t = "\n".join(
        line
        for line in t.splitlines()
        if line.strip() not in drop and not line.startswith("Want to see") and "Prime Research" not in line
    )
    return [
        {
            "url": z["url"],
            "retrieved": retrieved(z),
            "text": t,
            "kept": "Company Information and Basic Information (compiled from MCA filings)",
        }
    ]


def main(web: Path, web2: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    docs = {
        "palms-technoforte-public-website-2026-11-22.pdf": (
            website_sections(web),
            "PALMS WMS and Technoforte public website statements, retrieved 2026-11-22",
        ),
        "technoforte-software-mca-registry-zaubacorp-2026-11-22.pdf": (
            registry_sections(web2),
            "Technoforte Software Pvt Ltd: MCA-derived company record (ZaubaCorp)",
        ),
    }
    record = {}
    for name, (sections, title) in docs.items():
        pages = paginate(sections)
        write_pdf(out / name, pages, title)
        record[name] = [
            {"page_url": s["url"], "retrieved": s["retrieved"], "kept": s["kept"]}
            for s in sections
        ]
        (out / f"{name}.txt").write_text(
            "\n\n".join(f"Source: {s['url']}\n{s['text']}" for s in sections)
        )
        print(name, len(pages), "pages")
    (out / "sections.json").write_text(json.dumps(record, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
