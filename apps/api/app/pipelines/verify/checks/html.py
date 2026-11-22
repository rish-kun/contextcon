"""HTML to readable text with the standard library (no parser dependency).

Drops script, style, nav, footer, header, aside, form and noscript content, keeps
block boundaries as line breaks and collapses whitespace.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_SKIP = {"script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg"}
_BLOCK = {
    "p",
    "div",
    "br",
    "li",
    "ul",
    "ol",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "tr",
    "table",
    "section",
    "article",
    "blockquote",
    "time",
}


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP:
            self.skip_depth += 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP and self.skip_depth:
            self.skip_depth -= 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    if "<" not in html:
        return " ".join(html.split())
    parser = _TextParser()
    parser.feed(html)
    parser.close()
    text = "".join(parser.parts)
    lines = (re.sub(r"[ \t\f\v\xa0]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def relevant_passages(text: str, needles: list[str], *, max_chars: int = 6000) -> str:
    """Paragraphs that mention any needle (case-insensitive), in order, up to max_chars.

    Keeps the extraction prompt on the part of a long article that is about the
    company. Paragraphs are kept whole, so quotes stay verbatim.
    """
    keys = [n.casefold() for n in needles if n and len(n) >= 3]
    paras = [p for p in text.split("\n") if p.strip()]
    hits = [p for p in paras if any(k in p.casefold() for k in keys)] if keys else paras
    out: list[str] = []
    size = 0
    for p in hits or paras:
        if size + len(p) > max_chars and out:
            break
        out.append(p)
        size += len(p) + 1
    return "\n".join(out)
