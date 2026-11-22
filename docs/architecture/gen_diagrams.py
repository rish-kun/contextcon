"""Generate the DealProof architecture diagrams (technical + business) as SVG.

Usage: python docs/architecture/gen_diagrams.py docs/architecture
"""
import sys
from html import escape
from pathlib import Path

INK, MUTED, LINE = "#0f172a", "#64748b", "#94a3b8"
BADGE = {
    "D": ("#2563eb", "Live data call"),
    "A": ("#d97706", "Human approval"),
    "R": ("#7c3aed", "Retry / resume"),
    "$": ("#059669", "Cost ledger"),
}
KIND = {  # fill, stroke
    "person": ("#fdf2f8", "#db2777"),
    "ui": ("#eef2ff", "#6366f1"),
    "core": ("#faf5ff", "#7c3aed"),
    "step": ("#ffffff", "#7c3aed"),
    "gw": ("#eff6ff", "#2563eb"),
    "chip": ("#ffffff", "#2563eb"),
    "ext": ("#fff7ed", "#ea580c"),
    "db": ("#ecfdf5", "#059669"),
    "gate": ("#fffbeb", "#d97706"),
    "grey": ("#f8fafc", "#94a3b8"),
    "white": ("#ffffff", "#cbd5e1"),
}
STYLE = f"""<style>
text {{ font-family: 'Segoe UI', Inter, 'Helvetica Neue', Arial, sans-serif; fill: {INK}; }}
.title {{ font-size: 30px; font-weight: 700; }}
.sub {{ font-size: 17px; fill: {MUTED}; }}
.zone {{ font-size: 14px; font-weight: 700; fill: {MUTED}; letter-spacing: 1.6px; }}
.h {{ font-size: 19px; font-weight: 700; }}
.s {{ font-size: 16px; fill: #334155; }}
.lab {{ font-size: 14px; fill: {MUTED}; }}
.num {{ font-size: 14px; font-weight: 800; fill: #ffffff; }}
.big {{ font-size: 20px; font-weight: 700; }}
</style>"""


class SVG:
    def __init__(self, w, h):
        self.w, self.h, self.p = w, h, []

    def rect(self, x, y, w, h, kind, rx=12, dash=False, sw=2):
        f, s = KIND[kind]
        d = ' stroke-dasharray="8 6"' if dash else ""
        self.p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{f}" stroke="{s}" stroke-width="{sw}"{d}/>')

    def text(self, x, y, s, cls="s", anchor="start", fill=None):
        f = f' style="fill:{fill}"' if fill else ""
        self.p.append(f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}"{f}>{escape(s)}</text>')

    def card(self, x, y, w, h, title, lines=(), kind="white", badges=(), center=False):
        self.rect(x, y, w, h, kind)
        n = 1 + len(lines)
        top = y + h / 2 - (n - 1) * 12 + 6
        if center:
            self.text(x + w / 2, top, title, "h", "middle")
            for i, ln in enumerate(lines):
                self.text(x + w / 2, top + 25 + i * 22, ln, "s", "middle")
        else:
            self.text(x + 18, y + 32, title, "h")
            for i, ln in enumerate(lines):
                self.text(x + 18, y + 58 + i * 22, ln, "s")
        bx = x + w - 20
        for b in badges:
            self.badge(bx, y + 20, b)
            bx -= 30

    def badge(self, cx, cy, b, r=13):
        self.p.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{BADGE[b][0]}"/>')
        self.text(cx, cy + 5, b, "num", "middle")

    def arrow(self, pts, color=LINE, w=2.5, dash=False, head=True):
        d = "M " + " L ".join(f"{x} {y}" for x, y in pts)
        mk = f' marker-end="url(#a{color[1:]})"' if head else ""
        da = ' stroke-dasharray="7 6"' if dash else ""
        self.p.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}" stroke-linejoin="round"{da}{mk}/>')

    def render(self):
        cols = {LINE, "#475569", "#2563eb", "#d97706", "#7c3aed", "#059669", "#db2777"}
        mk = "".join(
            f'<marker id="a{c[1:]}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
            f'<path d="M0 0 L10 5 L0 10 z" fill="{c}"/></marker>' for c in sorted(cols))
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}">'
                f'{STYLE}<defs>{mk}</defs><rect width="{self.w}" height="{self.h}" fill="#ffffff"/>' + "".join(self.p) + "</svg>")


def legend(s, x, y):
    for b, (_, label) in BADGE.items():
        s.badge(x, y - 5, b, 12)
        s.text(x + 20, y, label, "s")
        x += 40 + len(label) * 8.5 + 30


# --------------------------------------------------------------------- technical
def technical():
    s = SVG(1600, 1010)
    s.text(40, 52, "DealProof · technical architecture", "title")
    s.text(40, 82, "One request flows top to bottom. Badges mark where live data calls, approvals, retries and the cost ledger sit.", "sub")

    # 1. people + web
    s.text(40, 128, "1  PEOPLE AND WEB APP", "zone")
    s.card(40, 142, 220, 70, "Analyst", ["asks, reads results"], "person")
    s.card(40, 224, 220, 70, "Approver", ["signs off the email"], "person", badges=("A",))
    s.card(320, 142, 1000, 152, "Web app", ["Next.js on Cloud Run", "Discover · case pages (claims, sources, assessment, cost) · approvals queue",
                                           "Live progress of every run"], "ui")
    s.arrow([(260, 177), (318, 177)], "#db2777")
    s.arrow([(260, 259), (318, 259)], "#d97706")
    s.card(1380, 142, 180, 152, "Seller", ["gets one", "approved email"], "person", center=True)

    # 2. API + job engine
    s.arrow([(820, 294), (820, 344)], "#475569")
    s.text(832, 324, "HTTPS + live updates", "lab")
    s.text(40, 336, "2  API AND JOB ENGINE  (FastAPI on Cloud Run)", "zone")
    s.rect(40, 350, 1280, 250, "core", rx=16)
    s.text(64, 386, "Job engine", "h")
    s.text(176, 386, "Every request is a Run of small Steps saved in Postgres. A worker holds a 60 s lease per step;", "s")
    s.text(176, 410, "if the process is killed, another worker resumes the step. A failed step is retried up to 3 times.", "s")
    s.badge(1290, 378, "R")
    steps = [
        ("Discover", ["thesis →", "ranked shortlist"], ()),
        ("Verify", ["identity first, then", "each claim vs. evidence"], ()),
        ("Evaluate", ["fixed rules →", "disposition"], ()),
        ("Act", ["◆ approval, then", "send email once"], ("A",)),
    ]
    x, w, gap = 64, 290, 21
    for i, (t, ls, b) in enumerate(steps):
        s.card(x, 440, w, 136, t, ls, "gate" if t == "Act" else "step", badges=b, center=True)
        if i < 3:
            s.arrow([(x + w + 2, 508), (x + w + gap - 2, 508)], "#7c3aed")
        x += w + gap
    act_cx = 64 + 3 * (w + gap) + w / 2

    # 3. call gateway
    s.arrow([(500, 600), (500, 650)], "#2563eb")
    s.text(512, 630, "every paid call goes through one gateway", "lab")
    s.text(40, 642, "3  CALL GATEWAY", "zone")
    s.rect(40, 656, 1280, 128, "gw", rx=16)
    chips = [
        ("1 · Cache", "already paid? replay free", ()),
        ("2 · Budget + log", "reserve credits, log the attempt", ()),
        ("3 · Call + retry", "back off on 429 / 5xx", ("R", "D")),
        ("4 · Record cost", "credits + tokens → ledger", ("$",)),
    ]
    x, cw, cg = 60, 296, 16
    chip_x = []
    for i, (t, ln, b) in enumerate(chips):
        s.card(x, 674, cw, 92, t, [ln], "chip", badges=b)
        chip_x.append(x)
        if i < 3:
            s.arrow([(x + cw + 1, 720), (x + cw + cg - 1, 720)], "#2563eb")
        x += cw + cg

    # email path: Act -> Resend -> Seller (right column)
    s.arrow([(act_cx + 145, 508), (1470, 508), (1470, 672)], "#d97706")
    s.card(1380, 674, 180, 92, "Resend", ["email, idempotent"], "ext", badges=("A",), center=True)
    s.arrow([(1545, 674), (1545, 296)], "#d97706")
    s.text(1480, 600, "sent once", "lab")

    # 4. data + providers
    s.text(40, 826, "4  LIVE SOURCES AND STORAGE", "zone")
    c3 = chip_x[2] + cw / 2
    s.card(chip_x[1] - 10, 840, 300, 100, "Crustdata", ["companies, people, jobs, web"], "ext", badges=("D",))
    s.card(chip_x[2] + 20, 840, 260, 100, "Claude (Haiku)", ["extract + draft only"], "ext", badges=("D",))
    s.arrow([(c3 - 40, 766), (c3 - 40, 800), (chip_x[1] + 140, 800), (chip_x[1] + 140, 838)], "#2563eb")
    s.arrow([(c3 + 20, 766), (c3 + 20, 838)], "#2563eb")
    c4 = chip_x[3] + cw / 2
    s.card(chip_x[3] + 10, 840, 290, 100, "Postgres", ["runs, evidence, cost ledger"], "db", badges=("$",))
    s.arrow([(c4 + 10, 766), (c4 + 10, 838)], "#059669")
    s.card(40, 840, 270, 100, "Cloud Storage", ["seller decks, deleted", "after 30 days"], "db")
    s.card(1380, 840, 180, 100, "Rules", ["decide every", "status, not AI"], "grey", center=True)

    legend(s, 52, 982)
    return s.render()


# --------------------------------------------------------------------- business
def business():
    s = SVG(1600, 960)
    s.text(40, 52, "DealProof · business architecture", "title")
    s.text(40, 82, "The paid job, who pays for it, and what the buyer gets back.", "sub")

    # Today
    s.text(40, 128, "TODAY", "zone")
    s.rect(40, 142, 1520, 120, "grey", rx=16)
    today = [("Buyer", "CFO office of a 3PL"), ("pays an advisory firm", "retainer or per target"),
             ("analysts screen by hand", "databases, deck, spreadsheet"), ("memo after days", "claims often unchecked")]
    x = 64
    for i, (t, ln) in enumerate(today):
        s.card(x, 160, 330, 84, t, [ln], "person" if i == 0 else "white", center=True)
        if i < 3:
            s.arrow([(x + 332, 202), (x + 368, 202)], "#475569")
        x += 370

    # With DealProof
    s.text(40, 306, "WITH DEALPROOF", "zone")
    s.rect(40, 320, 1520, 300, "core", rx=16)
    s.card(64, 344, 230, 150, "Request", ["a thesis, or a", "company + its deck"], "ui", center=True)
    steps = [("Discover", ["shortlist of", "real companies"]), ("Verify", ["each claim checked", "against records"]),
             ("Evaluate", ["rules give a", "clear next step"]), ("Act", ["request documents", "after approval"])]
    x = 334
    s.arrow([(296, 419), (x - 2, 419)], "#7c3aed")
    for i, (t, ls) in enumerate(steps):
        s.card(x, 344, 220, 150, f"{i + 1}  {t}", ls, "gate" if t == "Act" else "step", badges=("A",) if t == "Act" else (), center=True)
        if i < 3:
            s.arrow([(x + 222, 419), (x + 246, 419)], "#7c3aed")
        x += 248
    s.card(1326, 344, 210, 150, "Finished case", ["sourced, dated,", "ready to decide"], "db", center=True)
    s.arrow([(x - 26, 419), (1324, 419)], "#059669")
    s.card(334 + 3 * 248, 514, 220, 84, "Named approver", ["signs off first"], "gate", center=True)
    s.arrow([(334 + 3 * 248 + 110, 512), (334 + 3 * 248 + 110, 496)], "#d97706")
    s.card(334, 514, 714, 84, "Analyst stays in charge", ["edits criteria, picks identity when names are ambiguous"], "person", center=True)
    s.card(1326, 514, 210, 84, "Decision-maker", ["second meeting: go?"], "person", center=True)
    s.arrow([(1431, 496), (1431, 512)], "#059669")

    # Economics + trust
    s.text(40, 664, "COST PER JOB  (measured, live run, 22 Nov 2026)", "zone")
    s.rect(40, 678, 740, 250, "db", rx=16)
    rows = [("Verify one company (9 claims)", "8.7 credits"), ("Shortlist of 25 companies", "50.1 credits"),
            ("Find investors", "59.2 credits"), ("All AI model calls", "$0.018"), ("Budget cap per case", "150 credits")]
    for i, (a, b) in enumerate(rows):
        y = 724 + i * 44
        s.text(68, y, a, "s")
        s.text(752, y, b, "big", "end")
        if i < len(rows) - 1:
            s.p.append(f'<line x1="68" y1="{y + 16}" x2="752" y2="{y + 16}" stroke="#bbf7d0" stroke-width="1.5"/>')

    s.text(820, 664, "WHY A FIRM CAN TRUST IT", "zone")
    s.rect(820, 678, 740, 250, "gate", rx=16)
    trust = ["Every fact shows its source and date", "“Cannot verify” instead of a guess",
             "Lookalike names are never merged", "Nothing is sent without a named approver",
             "Uploaded files deleted after 30 days"]
    for i, t in enumerate(trust):
        s.text(848, 724 + i * 44, "✓  " + t, "s")
    return s.render()


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    (out / "technical-architecture.svg").write_text(technical(), encoding="utf-8")
    (out / "business-architecture.svg").write_text(business(), encoding="utf-8")
    print("ok")
