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
        if anchor == "start" and s.startswith("   "):  # continuation of a bullet
            x, s = x + 13, s.lstrip()
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
def panel(s, x, y, w, h, kind, heading):
    s.text(x, y - 14, heading, "zone")
    s.rect(x, y, w, h, kind, rx=16)


def business():
    s = SVG(1600, 1330)
    s.text(40, 52, "DealProof · business architecture", "title")
    s.text(40, 82, "The paid job, who pays for it today, what the service delivers, and what it costs.", "sub")

    # ---- Today
    panel(s, 40, 128, 1520, 140, "grey", "TODAY · THE JOB A FIRM IS PAID FOR")
    today = [("Buyer", ["CFO office of a mid-size", "Indian 3PL"], "person"),
             ("pays an advisory firm", ["M&A advisor or diligence team,", "retainer or fee per target"], "white"),
             ("analysts screen by hand", ["databases, registry lookups,", "seller deck, spreadsheet"], "white"),
             ("memo after days", ["claims unchecked, lookalike", "names mixed up, gaps guessed"], "white")]
    x = 64
    for i, (t, ls, k) in enumerate(today):
        s.card(x, 146, 330, 104, t, ls, k, center=True)
        if i < 3:
            s.arrow([(x + 332, 198), (x + 368, 198)], "#475569")
        x += 370

    # ---- With DealProof
    panel(s, 40, 326, 1520, 360, "core", "WITH DEALPROOF · THE SAME JOB, DONE BY THE SERVICE")
    s.card(64, 346, 200, 190, "Request", ["a thesis, or a", "company + website", "+ seller deck, or a", "business profile"], "ui", center=True)
    steps = [("1  Discover", ["thesis → editable criteria", "live company search", "must-haves gate, rank fit", "→ ranked shortlist"]),
             ("2  Verify", ["confirm legal entity first", "check each claim against", "dated records", "→ claim ledger"]),
             ("3  Evaluate", ["5 separate judgments", "decided by fixed rules", "unknowns never penalised", "→ next step + reason"]),
             ("4  Act", ["list docs that settle gaps", "draft one request email", "◆ named person approves", "→ sent exactly once"])]
    x, w, g = 294, 240, 24
    s.arrow([(266, 441), (x - 2, 441)], "#7c3aed")
    for i, (t, ls) in enumerate(steps):
        act = t.endswith("Act")
        s.card(x, 346, w, 190, t, ls, "gate" if act else "step", badges=("A",) if act else (), center=True)
        if i < 3:
            s.arrow([(x + w + 2, 441), (x + w + g - 2, 441)], "#7c3aed")
        x += w + g
    s.arrow([(x - g + 2, 441), (1334, 441)], "#059669")
    s.card(1336, 346, 200, 190, "Finished case", ["identity confirmed", "each claim: status,", "source and date", "disposition + request"], "db", center=True)

    s.card(294, 560, 240, 100, "Analyst", ["edits criteria, picks", "identity if ambiguous"], "person", center=True)
    s.card(558, 560, 504, 100, "Seller / target company", ["sends documents back → affected claims", "re-checked, new assessment version"], "person", center=True)
    s.card(1086, 560, 240, 100, "Named approver", ["approves the exact", "email; edits need re-approval"], "gate", center=True)
    s.card(1336, 560, 200, 100, "Decision-maker", ["second meeting:", "go or no-go"], "person", center=True)
    s.arrow([(1206, 558), (1206, 538)], "#d97706")
    s.arrow([(1084, 610), (1064, 610)], "#d97706")
    s.arrow([(690, 558), (690, 538)], "#7c3aed", dash=True)
    s.arrow([(1436, 538), (1436, 558)], "#059669")

    # ---- Who buys / example / model
    cw, y3, h3 = 493, 744, 250
    xs = [40, 40 + cw + 20, 40 + 2 * (cw + 20)]
    panel(s, xs[0], y3, cw, h3, "white", "WHO BUYS IT")
    for i, ln in enumerate(["• M&A advisory firms and corporate", "   development teams (first customers)",
                            "• PE and VC funds, family offices,", "   search funds, business brokers",
                            "• Businesses raising money: investors", "   matched by their dated deals"]):
        s.text(xs[0] + 24, y3 + 40 + i * 34, ln, "s")

    panel(s, xs[1], y3, cw, h3, "white", "A FINISHED CASE (ILLUSTRATION)")
    rows = [("“Incorporated 2014, Pune”", "Supported", "#059669"),
            ("“We employ 250 people”", "Cannot verify", "#64748b"),
            ("“New facility, Oct 2026”", "Partly corroborated", "#d97706"),
            ("“We have no debt”", "Cannot verify", "#64748b")]
    for i, (c, st, col) in enumerate(rows):
        y = y3 + 40 + i * 38
        s.text(xs[1] + 24, y, c, "s")
        s.text(xs[1] + cw - 24, y, st, "h", "end", fill=col)
    s.text(xs[1] + 24, y3 + 212, "→ Investigate further; ask for 3 documents", "h")

    panel(s, xs[2], y3, cw, h3, "white", "BUSINESS MODEL")
    for i, ln in enumerate(["• Buyer pays per finished case, or a", "   monthly plan for a deal team",
                            "• Our cost per job: data credits,", "   AI tokens, cloud hosting",
                            "• Each run has a credit budget, so", "   cost per case is capped in advance"]):
        s.text(xs[2] + 24, y3 + 40 + i * 34, ln, "s")

    # ---- Cost + trust
    y4, h4 = 1054, 256
    panel(s, 40, y4, 740, h4, "db", "COST PER JOB · MEASURED ON THE LIVE RUN, 22 NOV 2026")
    crow = [("Verify one company (9 claims)", "8.7 credits"), ("Shortlist of 25 companies (shared by its cases)", "50.1 credits"),
            ("Find investors for a business", "59.2 credits"), ("All AI model calls in the run", "$0.018"),
            ("Default budget cap per case", "150 credits")]
    for i, (a, b) in enumerate(crow):
        y = y4 + 42 + i * 46
        s.text(68, y, a, "s")
        s.text(752, y, b, "big", "end")
        if i < len(crow) - 1:
            s.p.append(f'<line x1="68" y1="{y + 18}" x2="752" y2="{y + 18}" stroke="#bbf7d0" stroke-width="1.5"/>')

    panel(s, 820, y4, 740, h4, "gate", "WHY A FIRM CAN TRUST IT")
    trust = ["Every fact shows its source link and date", "“Cannot verify” instead of a guess, naming what is missing",
             "Lookalike names are never merged", "Same evidence + same rules → same result",
             "Nothing is sent without a named approver, and only once", "Uploads stay in their case and are deleted after 30 days"]
    for i, t in enumerate(trust):
        s.text(848, y4 + 40 + i * 37, "\u2713  " + t, "s")
    return s.render()


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    (out / "technical-architecture.svg").write_text(technical(), encoding="utf-8")
    (out / "business-architecture.svg").write_text(business(), encoding="utf-8")
    print("ok")
