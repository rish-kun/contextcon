"""The citation validator.

Drafted prose may only restate facts that were passed in with citation ids.
`check_citations` splits text into sentences and rejects:
- a sentence with no citation;
- a citation id that was not passed in;
- any other square-bracket text;
- a number in a sentence that does not appear in any fact the sentence cites
  (a cheap guard against invented figures and dates).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.:\-]*"
_ID = re.compile(rf"^{ID_PATTERN}$")
_BRACKET = re.compile(r"\[([^\[\]]*)\]")
_BOUNDARY = re.compile(r"[.!?][\"'”’)]*((?:\s*\[[^\[\]]*\])*)(?=\s|$)")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_ABBREVIATIONS = frozenset(
    "pvt ltd inc co corp llp llc no nos mr mrs ms dr st rs approx est vs etc e.g i.e jan feb "
    "mar apr jun jul aug sep sept oct nov dec fy".split()
)


class UncitedSentenceError(ValueError):
    """Raised by `require_citations` when drafted text fails the validator."""

    def __init__(self, issues: list[str]):
        super().__init__("; ".join(issues))
        self.issues = issues


class CheckedSentence(BaseModel):
    text: str
    citation_ids: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class CitationReport(BaseModel):
    sentences: list[CheckedSentence]
    issues: list[str]

    @property
    def ok(self) -> bool:
        return not self.issues and bool(self.sentences)

    @property
    def citations_used(self) -> list[str]:
        seen: dict[str, None] = {}
        for s in self.sentences:
            for cid in s.citation_ids:
                seen.setdefault(cid, None)
        return list(seen)


def valid_citation_id(cid: str) -> bool:
    return bool(_ID.match(cid))


def _is_abbreviation(text_before_dot: str) -> bool:
    token = re.split(r"\s", text_before_dot.rstrip())[-1] if text_before_dot.strip() else ""
    token = token.lstrip("(\"'").lower()
    return token in _ABBREVIATIONS or (len(token) == 1 and token.isalpha())


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences. Trailing citation markers stay with their sentence."""
    sentences: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", line).strip()
        if not line:
            continue
        start = 0
        for m in _BOUNDARY.finditer(line):
            if m.group(0)[0] == "." and _is_abbreviation(line[start : m.start()]):
                continue
            piece = line[start : m.end()].strip()
            if piece:
                sentences.append(piece)
            start = m.end()
        tail = line[start:].strip()
        if tail:
            sentences.append(tail)
    return sentences


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in _NUMBER.findall(text)}


def check_citations(text: str, sources: dict[str, str]) -> CitationReport:
    """Validate `text` against `sources` (citation id → the fact text it may restate)."""
    checked: list[CheckedSentence] = []
    all_issues: list[str] = []
    for sentence in split_sentences(text):
        issues: list[str] = []
        ids: list[str] = []
        for raw in _BRACKET.findall(sentence):
            parts = [p.strip() for p in raw.split(",")]
            if not parts or not all(valid_citation_id(p) for p in parts):
                issues.append(f"non-citation brackets [{raw}]")
                continue
            for cid in parts:
                if cid in sources:
                    ids.append(cid)
                else:
                    issues.append(f"unknown citation id {cid}")
        if not ids and not issues:
            issues.append("sentence has no citation")
        if ids:
            cited_text = " ".join(sources[c] for c in ids)
            bare = _BRACKET.sub(" ", sentence)
            invented = sorted(_numbers(bare) - _numbers(cited_text))
            if invented:
                issues.append(f"numbers not in cited facts: {', '.join(invented)}")
        checked.append(CheckedSentence(text=sentence, citation_ids=ids, issues=issues))
        all_issues.extend(f'"{_short(sentence)}": {i}' for i in issues)
    if not checked:
        all_issues.append("text is empty")
    return CitationReport(sentences=checked, issues=all_issues)


def require_citations(text: str, sources: dict[str, str]) -> CitationReport:
    report = check_citations(text, sources)
    if not report.ok:
        raise UncitedSentenceError(report.issues)
    return report


def cite_each_sentence(statement: str, cid: str) -> str:
    """Deterministic fallback: restate `statement` with `[cid]` on every sentence."""
    out: list[str] = []
    for sentence in split_sentences(_BRACKET.sub("", statement)):
        sentence = sentence.rstrip()
        end = ""
        if sentence and sentence[-1] in ".!?":
            sentence, end = sentence[:-1].rstrip(), sentence[-1]
        out.append(f"{sentence} [{cid}]{end or '.'}")
    return " ".join(out)


def _short(text: str, n: int = 60) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"
