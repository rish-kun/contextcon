"""Generate the DealProof architecture SVGs (technical + business)."""
import sys
from html import escape
from pathlib import Path

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

INK = "#0f172a"
MUTED = "#475569"
LINE = "#94a3b8"
BADGE = {
    "D": ("#2563eb", "Data call to a live source"),
    "A": ("#d97706", "Human approval gate"),
    "R": ("#7c3aed", "Retry / resume point"),
    "$": ("#059669", "Cost ledger write"),
}
FILL = {
    "ui": ("#eef2ff", "#6366f1"),
    "api": ("#f8fafc", "#64748b"),
    "job": ("#f5f3ff", "#7c3aed"),
    "pipe": ("#ffffff", "#7c3aed"),
    "call": ("#eff6ff", "#2563eb"),
    "db": ("#ecfdf5", "#059669"),
    "ext": ("#fff7ed", "#ea580c"),
    "gate": ("#fffbeb", "#d97706"),
    "person": ("#fdf2f8", "#db2777"),
    "plain": ("#ffffff", "#cbd5e1"),
    "today": ("#f1f5f9", "#94a3b8"),
    "out": ("#ecfdf5", "#059669"),
}

STYLE = f"""
<style>
  text {{ font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', Arial, sans-serif; fill: {INK}; }}
  .title {{ font-size: 26px; font-weight: 700; }}
  .sub {{ font-size: 15px; fill: {MUTED}; }}
  .h {{ font-size: 16px; font-weight: 700; }}
  .s {{ font-size: 14px; fill: #1e293b; }}
  .m {{ font-family: Consolas, 'Cascadia Mono', 'Courier New', monospace; font-size: 13px; fill: #1e293b; }}
  .lab {{ font-size: 13px; fill: {MUTED}; font-style: italic; }}
  .lane {{ font-size: 13px; font-weight: 700; fill: {MUTED}; letter-spacing: 1.5px; }}
  .badge {{ font-size: 13px; font-weight: 800; fill: #ffffff; }}
  .gate {{ font-size: 14px; font-weight: 800; fill: #b45309; }}
</style>
"""


class SVG:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.parts = []

    def add(self, s):
        self.parts.append(s)

    def box(self, x, y, w, h, kind="plain", rx=10, dash=False, sw=1.6):
        fill, stroke = FILL[kind]
        d = ' stroke-dasharray="7 5"' if dash else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def text(self, x, y, s, cls="s", anchor="start", extra=""):
        self.add(f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}"{extra}>{escape(s)}</text>')

    def card(self, x, y, w, h, title, lines, kind="plain", badges=(), mono=False, lh=19, dash=False):
        self.box(x, y, w, h, kind, dash=dash)
        self.text(x + 14, y + 25, title, "h")
        cy = y + 25 + lh + 2
        for ln in lines:
            if ln.startswith("!GATE "):
                self.text(x + 14, cy, ln[6:], "gate")
            else:
                self.text(x + 14, cy, ln, "m" if mono else "s")
            cy += lh
        bx = x + w - 18
        for b in badges:
            self.badge(bx, y + 18, b)
            bx -= 30

    def badge(self, cx, cy, b):
        col = BADGE[b][0]
        self.add(f'<circle cx="{cx}" cy="{cy}" r="12" fill="{col}"/>')
        self.text(cx, cy + 4.5, b, "badge", "middle")

    def arrow(self, pts, color=LINE, width=2, dash=False, label=None, lx=None, ly=None, head=True):
        d = "M " + " L ".join(f"{x} {y}" for x, y in pts)
        mk = f' marker-end="url(#ah-{color[1:]})"' if head else ""
        da = ' stroke-dasharray="6 5"' if dash else ""
        self.add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{da}{mk}/>')
        if label:
            self.text(lx, ly, label, "lab")

    def render(self):
        colors = {LINE, "#2563eb", "#d97706", "#7c3aed", "#059669", "#475569", "#db2777", "#ea580c"}
        markers = "".join(
            f'<marker id="ah-{c[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0 0 L10 5 L0 10 z" fill="{c}"/></marker>'
            for c in colors
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}">'
            f"{STYLE}<defs>{markers}</defs>"
            f'<rect width="{self.w}" height="{self.h}" fill="#ffffff"/>'
            + "".join(self.parts)
            + "</svg>"
        )


def legend(s, x, y):
    s.text(x, y, "LEGEND", "lane")
    cx = x + 90
    for b, (col, label) in BADGE.items():
        s.badge(cx, y - 5, b)
        s.text(cx + 20, y, label, "s")
        cx += 20 + len(label) * 7.6 + 40


# ------------------------------------------------------------------ technical
def technical():
    s = SVG(1500, 1170)
    s.text(20, 38, "DealProof — technical architecture", "title")
    s.text(20, 60, "Components, data flow, and where data calls (D), approvals (A), retries (R) and the cost ledger ($) sit", "sub")

    # Band A: people + web + seller
    s.card(20, 76, 240, 46, "Analyst / associate", [], "person")
    s.card(20, 130, 240, 46, "Named approver", [], "person", badges=("A",))
    s.card(300, 76, 860, 100, "Web app — Next.js 16 (apps/web) on Cloud Run, asia-south1", [
        "Discover · Investors · Case pages: identity, claims, sources, assessment, request, cost",
        "Approvals queue · same-origin /api proxy · live run activity over SSE (polling fallback)",
    ], "ui", badges=("$",))
    s.card(1200, 76, 280, 100, "Seller / target company", [
        "receives one approved email",
        "returns documents → upload",
    ], "person")
    s.arrow([(260, 99), (298, 99)], "#db2777")
    s.arrow([(260, 153), (298, 153)], "#d97706", label=None)
    s.arrow([(730, 176), (730, 210)], "#475569")
    s.text(740, 198, "HTTPS JSON + SSE", "lab")

    # API container
    s.box(10, 212, 1470, 600, "api", rx=14, dash=True)
    s.text(26, 236, "API service — FastAPI (apps/api), Python 3.12 · the same image runs the step worker · Cloud Run", "h")

    s.card(30, 250, 450, 82, "HTTP routers", [
        "theses · investors · cases · documents · requests (act)",
        "runs + activity stream · policy · public showcase",
    ])
    s.card(496, 250, 450, 82, "Auth & access control", [
        "named users, sessions, origin check, rate limits",
        "case-scoped authorisation on every read path",
    ])
    s.card(962, 250, 500, 82, "Document intake (seller decks, claims)", [
        "validate → sandboxed text extraction → PII redaction",
        "→ private GCS bucket, case-scoped, 30-day retention",
    ])

    # Job engine
    s.box(30, 346, 1432, 262, "job", rx=12)
    s.text(46, 370, "Job engine — every pipeline is a Run of idempotent Steps, persisted in Postgres", "h")
    s.card(46, 384, 430, 206, "Step worker (jobs/worker.py)", [
        "claim: SELECT … FOR UPDATE SKIP LOCKED",
        "60 s lease, renewed while the step runs",
        "fresh lease_token per claim (fencing)",
        "expired leases reclaimed by sweep + claim",
        "step retried ≤ 3 attempts (2 s → 120 s)",
        "budget spent → skipped_budget (Not checked)",
        "pending → running → done|failed|skipped",
    ], "pipe", badges=("R",), lh=20)

    px, pw, gap = 494, 224, 16
    pipes = [
        ("1 · Discover", ["thesis → criteria (LLM)", "company search (live)", "must-have gate", "enrich top N + jobs", "re-gate → fit rank", "+ investor discovery"], ("D",)),
        ("2 · Verify", ["identity guard (blocking)", "profile · registry · events", "comparables · claim intake", "evidence per claim", "facts (LLM), span-checked", "status by rule table"], ("D",)),
        ("3 · Evaluate (rules only)", ["fit + % assessable", "evidence sufficiency", "business · financial", "disposition (4 values)", "AssessmentVersion + diff", "DecisionFlip what-if"], ()),
        ("4 · Act", ["request list (rules)", "draft email (LLM)", "!GATE ◆ APPROVAL GATE", "approval bound to revision", "send once (send key)", "docs back → re-check"], ("A",)),
    ]
    for i, (t, ls, b) in enumerate(pipes):
        x = px + i * (pw + gap)
        s.card(x, 384, pw, 196, t, ls, "pipe", badges=b, lh=24)
        if i < 3:
            s.arrow([(x + pw, 420), (x + pw + gap - 1, 420)], "#7c3aed")
    # recheck loop Act -> Verify
    vx = px + (pw + gap) + pw / 2
    ax = px + 3 * (pw + gap) + pw / 2
    s.arrow([(ax, 580), (ax, 588), (vx, 588), (vx, 582)], "#7c3aed", dash=True)
    s.text(vx + 14, 603, "seller documents arrive → affected claims re-checked → new assessment version", "lab")

    # Worker <-> Postgres along the left gutter
    s.arrow([(46, 470), (20, 470), (20, 852)], "#059669", width=2)
    s.text(26, 838, "claim · lease · state", "lab", extra=' transform="rotate(0)"')

    # Call layer
    s.box(30, 652, 1432, 146, "call", rx=12)
    s.text(46, 676, "External call layer — CallOperation (clients/base.py): the single path for every paid call", "h")
    s.badge(1438, 670, "D")
    s.arrow([(730, 608), (730, 650)], "#2563eb")
    s.text(740, 636, "every data / model call", "lab")
    steps = [
        ("① Cache lookup", ["request-hash cache", "case-scoped if private text", "hit → replay, zero cost"], ()),
        ("② Pre-dispatch", ["check lease (fencing)", "reserve case credit budget", "call_attempt = started"], ()),
        ("③ Dispatch + retry", ["429 · 5xx · network · timeout", "exp. backoff + jitter", "Crustdata ≤3, Claude ≤2"], ("R",)),
        ("④ Finish (one txn)", ["usage → cost_entries", "cache write + attempt status", "lost usage = unknown, not 0"], ("$",)),
    ]
    sx, sw2, sg = 46, 262, 14
    for i, (t, ls, b) in enumerate(steps):
        x = sx + i * (sw2 + sg)
        s.card(x, 688, sw2, 98, t, ls, "plain", badges=b, lh=20)
        if i < 3:
            s.arrow([(x + sw2, 736), (x + sw2 + sg - 1, 736)], "#2563eb")
    ex = sx + 4 * (sw2 + sg)
    s.card(ex, 688, 1446 - ex, 98, "Email sender (Resend)", [
        "send key stored before the call",
        "= provider idempotency key",
        "unknown → reconcile, never resend",
    ], "gate", badges=("A",), lh=20)
    s.arrow([(1404, 580), (1404, 686)], "#d97706")

    # Band E: stores + externals
    s.card(30, 852, 780, 214, "Neon Postgres — system of record", [], "db")
    col1 = ["runs, steps (state, lease_token, attempts)", "call_attempts: started → succeeded|failed|unknown",
            "cost_entries — THE COST LEDGER (credits, tokens, USD)", "api cache (request hash, case scope)", "run_activities (live log shown in the UI)"]
    col2 = ["sources, evidence (span, date, origin)", "claims (original + normalised)", "assessment_versions (immutable)",
            "messages, revisions, approvals", "sends (unique send key), deletion log"]
    for i, ln in enumerate(col1):
        s.text(44, 902 + i * 30, ln, "m")
    for i, ln in enumerate(col2):
        s.text(476, 902 + i * 30, ln, "m")
    s.badge(32, 958, "$")

    s.card(826, 852, 190, 214, "GCS bucket", ["cases/<id>/ uploads", "private, signed URLs", "lifecycle delete", "after 30 days"], "db", lh=24)

    s.card(1032, 852, 392, 124, "Crustdata API — live data", [
        "/company/identify  /company/search",
        "/company/enrich    /person/search",
        "/job/search        /web/search/live",
        "/web/enrich/live   (page fetch)",
    ], "ext", badges=("D",), mono=True, lh=21)
    s.card(1032, 988, 210, 78, "Anthropic Claude", ["Haiku 5.5 · extract", "and draft only"], "ext", badges=("D",), lh=20)
    s.card(1254, 988, 208, 78, "Resend email", ["idempotent send", "test mode by flag"], "ext", badges=("A",), lh=20)

    # call layer -> externals (data)
    s.arrow([(730, 786), (730, 826), (1200, 826), (1200, 850)], "#2563eb", width=2.2)
    s.arrow([(1024, 826), (1024, 1027), (1030, 1027)], "#2563eb", width=2.2)
    s.text(1210, 846, "D  live HTTP calls", "lab")
    # finish -> ledger
    s.arrow([(1005, 786), (1005, 838), (330, 838), (330, 850)], "#059669", width=2.2)
    s.text(340, 832, "$ usage + cost per call", "lab")
    # email -> resend -> seller
    s.arrow([(1440, 786), (1440, 986)], "#d97706", width=2)
    s.arrow([(1462, 1027), (1490, 1027), (1490, 160), (1482, 160)], "#d97706", width=2)
    s.text(1300, 205, "approved email, sent once", "lab")

    legend(s, 30, 1110)
    s.text(30, 1148, "Deterministic rules (app/rules, POLICY.md) decide every status, score and disposition; the LLM only extracts and drafts, and each extracted value is checked against its source span.", "s")
    return s.render()


# ------------------------------------------------------------------ business
def business():
    s = SVG(1500, 1060)
    s.text(20, 38, "DealProof — business architecture", "title")
    s.text(20, 60, "The paid job, who pays for it today, and how a request becomes a finished, sourced screening case", "sub")

    # Lane 1: today
    s.box(10, 78, 1480, 170, "today", rx=14)
    s.text(26, 102, "TODAY — THE JOB A FIRM IS PAID FOR", "lane")
    s.card(26, 114, 290, 120, "Buyer: CFO office / corp-dev", ["mid-size Indian 3PL looking at", "logistics, warehousing and", "supply-chain tech targets"], "person", lh=20)
    s.card(380, 114, 290, 120, "Paid firm", ["M&A advisory, diligence team", "or venture scout; paid a", "retainer or per-target fee"], "plain", lh=20)
    s.card(734, 114, 340, 120, "Manual first-pass screening", ["databases + registry lookups,", "reading the seller deck,", "an analyst's spreadsheet"], "plain", lh=20)
    s.card(1138, 114, 336, 120, "What goes wrong", ["days per target · deck claims", "unchecked · lookalike names", "mixed up · gaps filled by guesses"], "plain", lh=20)
    s.arrow([(316, 174), (378, 174)], "#475569")
    s.text(322, 166, "pays fee", "lab")
    s.arrow([(670, 174), (732, 174)], "#475569")
    s.arrow([(1074, 174), (1136, 174)], "#475569")

    # Lane 2: with DealProof
    s.box(10, 266, 1480, 446, "api", rx=14)
    s.text(26, 290, "WITH DEALPROOF — THE SAME JOB, DONE BY THE SERVICE", "lane")
    s.card(26, 304, 230, 290, "Request (input)", [
        "• an investment thesis",
        "  in plain words, or",
        "• a company name +",
        "  website, and",
        "• optional seller deck",
        "  or typed claims",
        "• or a business profile",
        "  (to find investors)",
    ], "ui", lh=22)
    stages = [
        ("Discover", ["criteria you can edit", "live company search", "must-haves gate, then", "rank by fit", "", "→ sourced shortlist"]),
        ("Verify", ["confirm legal identity", "first (no name-only", "matches), check each", "claim vs evidence", "", "→ claim ledger"]),
        ("Evaluate", ["5 separate judgments,", "rules not AI opinion;", "unknowns stated,", "never penalised", "", "→ disposition"]),
        ("Act", ["list the documents that", "settle open questions,", "draft one request,", "!GATE ◆ person approves", "", "→ sent exactly once"]),
    ]
    x0, w, g = 290, 210, 22
    for i, (t, ls) in enumerate(stages):
        x = x0 + i * (w + g)
        s.card(x, 304, w, 200, f"{i + 1} · {t}", ls, "pipe", badges=("A",) if t == "Act" else (), lh=24)
        s.arrow([(x - g + 1 if i else 256, 400), (x - 1, 400)], "#7c3aed")
    last = x0 + 3 * (w + g) + w
    s.card(1236, 304, 238, 290, "Finished result", [
        "a screening case that",
        "reads in minutes and",
        "audits in full:",
        "• identity + profile",
        "• each claim: status,",
        "  quote/field, date",
        "• Prioritise / Investigate",
        "  / Deprioritise / Cannot",
        "  assess, with reasons",
        "• request list + email",
    ], "out", lh=22)
    s.arrow([(last, 400), (1234, 400)], "#059669")

    # humans row
    s.card(290, 524, 450, 70, "Analyst (user)", ["edits criteria, picks identity when ambiguous, reads the case"], "person")
    s.card(756, 524, 462, 70, "Named approver", ["approves the exact email revision; any edit needs a new approval"], "gate", badges=("A",))
    s.card(26, 610, 520, 86, "Seller / target company", ["gets one consolidated document request;", "documents it returns re-check the affected claims"], "person")
    s.card(562, 610, 912, 86, "Decision-maker (buyer's CFO office)", [
        "goes into the second meeting with claims checked and unknowns named; earlier assessment kept,",
        "and every change between versions explained (e.g. 'Partially corroborated → Supported because …')",
    ], "out")
    s.arrow([(1110, 504), (1110, 522)], "#d97706")
    s.arrow([(1355, 594), (1355, 608)], "#059669")
    s.arrow([(800, 594), (800, 602), (520, 602), (520, 608)], "#d97706")

    # Lane 3: economics + trust
    s.box(10, 730, 735, 312, "db", rx=14)
    s.text(26, 754, "ECONOMICS — MEASURED ON THE LIVE SHOWCASE RUN (22 NOV 2026)", "lane")
    rows = [
        ("Verify + evaluate one case (Palms WMS, 9 claims)", "8.7 Crustdata credits"),
        ("Discover: thesis → 25 enriched companies", "50.1 credits, shared"),
        ("Investor search for the same profile", "59.2 credits"),
        ("All LLM calls for the whole showcase", "$0.018 (≈ ₹1.5)"),
        ("Budget caps (configurable)", "case 150 · discover 100"),
        ("Who pays (proposed)", "per finished case, or"),
        ("", "monthly plan for a deal team"),
    ]
    for i, (a, b) in enumerate(rows):
        y = 790 + i * 34
        s.text(30, y, a, "s")
        s.text(720, y, b, "h", "end")
        if i < len(rows) - 1 and a:
            s.add(f'<line x1="30" y1="{y + 12}" x2="720" y2="{y + 12}" stroke="#bbf7d0"/>')
    s.badge(712, 748, "$")

    s.box(760, 730, 730, 312, "gate", rx=14)
    s.text(776, 754, "TRUST — WHY A FIRM CAN SIGN OFF ON IT", "lane")
    trust = [
        "Every fact links to its record: URL or API field, exact passage, and date",
        "'Cannot verify' is a real answer and names the document that would settle it",
        "Identity first: lookalike names stay separate; nothing attaches on a name alone",
        "Rules decide; same records + same policy version → same assessment",
        "Nothing leaves without a named approver, and it leaves once",
        "Uploads: case-only, personal details stripped, deleted after 30 days",
        "Web searches use public lookup terms only, never confidential claim text",
    ]
    for i, t in enumerate(trust):
        s.text(780, 790 + i * 34, "✓  " + t, "s")
    return s.render()


(OUT / "technical-architecture.svg").write_text(technical(), encoding="utf-8")
(OUT / "business-architecture.svg").write_text(business(), encoding="utf-8")
print("ok")
