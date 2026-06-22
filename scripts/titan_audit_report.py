"""
TITAN XAU AI - Project State Audit PDF Generator
Style: Goldman Sachs white paper (navy + crimson + serif)
Output: /home/z/my-project/download/TITAN_Project_State_Audit_v1.0.pdf
"""
from __future__ import annotations
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    KeepTogether, Image, ListFlowable, ListItem
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.platypus.flowables import HRFlowable
from reportlab.pdfgen import canvas

# === FONT REGISTRATION ===
FONT_DIR = "/usr/share/fonts/truetype/liberation"
pdfmetrics.registerFont(TTFont("BodySerif", f"{FONT_DIR}/LiberationSerif-Regular.ttf"))
pdfmetrics.registerFont(TTFont("BodySerif-Bold", f"{FONT_DIR}/LiberationSerif-Bold.ttf"))
pdfmetrics.registerFont(TTFont("BodySerif-Italic", f"{FONT_DIR}/LiberationSerif-Italic.ttf"))
pdfmetrics.registerFont(TTFont("HeadingSans", f"{FONT_DIR}/LiberationSans-Regular.ttf"))
pdfmetrics.registerFont(TTFont("HeadingSans-Bold", f"{FONT_DIR}/LiberationSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Mono", f"{FONT_DIR}/LiberationMono-Regular.ttf"))
pdfmetrics.registerFont(TTFont("Mono-Bold", f"{FONT_DIR}/LiberationMono-Bold.ttf"))

from reportlab.pdfbase.pdfmetrics import registerFontFamily
registerFontFamily("BodySerif", normal="BodySerif", bold="BodySerif-Bold", italic="BodySerif-Italic")
registerFontFamily("HeadingSans", normal="HeadingSans", bold="HeadingSans-Bold")
registerFontFamily("Mono", normal="Mono", bold="Mono-Bold")

# === PALETTE (Goldman Sachs White Paper) ===
NAVY = colors.HexColor("#14213D")
CRIMSON = colors.HexColor("#C8102E")
GOLD = colors.HexColor("#B8860B")
GREEN = colors.HexColor("#1E7D3A")
RED = colors.HexColor("#C8102E")
AMBER = colors.HexColor("#B8860B")
LIGHT_NAVY = colors.HexColor("#2D4063")
LIGHTER_NAVY = colors.HexColor("#5C6B85")
BG_LIGHT = colors.HexColor("#F5F6F8")
BG_TABLE = colors.HexColor("#EEF1F5")
BG_TABLE_HEAD = colors.HexColor("#14213D")
TEXT_PRIMARY = colors.HexColor("#1A1A1A")
TEXT_MUTED = colors.HexColor("#5C5C5C")
BORDER = colors.HexColor("#D0D5DD")

# === PAGE SETUP ===
PAGE_W, PAGE_H = A4
MARGIN_L = 1.8 * cm
MARGIN_R = 1.8 * cm
MARGIN_T = 2.0 * cm
MARGIN_B = 2.0 * cm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

# === STYLES ===
ss = getSampleStyleSheet()

style_cover_title = ParagraphStyle(
    "CoverTitle", parent=ss["Title"],
    fontName="HeadingSans-Bold", fontSize=32, leading=38,
    textColor=colors.white, alignment=TA_LEFT, spaceAfter=8
)
style_cover_sub = ParagraphStyle(
    "CoverSub", fontName="HeadingSans", fontSize=14, leading=18,
    textColor=colors.HexColor("#C5CDD8"), alignment=TA_LEFT, spaceAfter=6
)
style_cover_meta = ParagraphStyle(
    "CoverMeta", fontName="BodySerif", fontSize=10, leading=14,
    textColor=colors.HexColor("#A0A8B5"), alignment=TA_LEFT
)

style_h1 = ParagraphStyle(
    "H1", fontName="HeadingSans-Bold", fontSize=18, leading=24,
    textColor=NAVY, spaceBefore=18, spaceAfter=10, alignment=TA_LEFT,
    borderPadding=(0, 0, 4, 0)
)
style_h2 = ParagraphStyle(
    "H2", fontName="HeadingSans-Bold", fontSize=13, leading=17,
    textColor=NAVY, spaceBefore=12, spaceAfter=6, alignment=TA_LEFT
)
style_h3 = ParagraphStyle(
    "H3", fontName="HeadingSans-Bold", fontSize=11, leading=14,
    textColor=LIGHT_NAVY, spaceBefore=8, spaceAfter=4, alignment=TA_LEFT
)

style_body = ParagraphStyle(
    "Body", fontName="BodySerif", fontSize=10, leading=14.5,
    textColor=TEXT_PRIMARY, alignment=TA_JUSTIFY, spaceAfter=6,
    firstLineIndent=0
)
style_body_left = ParagraphStyle(
    "BodyLeft", fontName="BodySerif", fontSize=10, leading=14.5,
    textColor=TEXT_PRIMARY, alignment=TA_LEFT, spaceAfter=6
)
style_bullet = ParagraphStyle(
    "Bullet", fontName="BodySerif", fontSize=10, leading=14,
    textColor=TEXT_PRIMARY, alignment=TA_LEFT, leftIndent=14, bulletIndent=2,
    spaceAfter=3
)
style_callout = ParagraphStyle(
    "Callout", fontName="BodySerif-Italic", fontSize=10, leading=14,
    textColor=NAVY, alignment=TA_LEFT, leftIndent=10, rightIndent=10,
    spaceBefore=6, spaceAfter=6, borderColor=GOLD, borderWidth=0,
    backColor=colors.HexColor("#FBF6E8"), borderPadding=8
)
style_critical = ParagraphStyle(
    "Critical", fontName="BodySerif-Bold", fontSize=10, leading=14,
    textColor=colors.white, alignment=TA_LEFT, leftIndent=10, rightIndent=10,
    spaceBefore=6, spaceAfter=6, backColor=CRIMSON, borderPadding=8
)
style_caption = ParagraphStyle(
    "Caption", fontName="BodySerif-Italic", fontSize=8.5, leading=11,
    textColor=TEXT_MUTED, alignment=TA_CENTER, spaceAfter=10
)
style_table_cell = ParagraphStyle(
    "TCell", fontName="BodySerif", fontSize=8.5, leading=11,
    textColor=TEXT_PRIMARY, alignment=TA_LEFT
)
style_table_cell_center = ParagraphStyle(
    "TCellC", fontName="BodySerif", fontSize=8.5, leading=11,
    textColor=TEXT_PRIMARY, alignment=TA_CENTER
)
style_table_head = ParagraphStyle(
    "THead", fontName="HeadingSans-Bold", fontSize=9, leading=11,
    textColor=colors.white, alignment=TA_CENTER
)

# === PAGE FRAME (header + footer) ===
def draw_page_frame(canv: canvas.Canvas, doc):
    canv.saveState()
    # Top thin navy line
    canv.setStrokeColor(NAVY)
    canv.setLineWidth(0.6)
    canv.line(MARGIN_L, PAGE_H - 1.2*cm, PAGE_W - MARGIN_R, PAGE_H - 1.2*cm)
    # Header text (right)
    canv.setFont("HeadingSans", 8)
    canv.setFillColor(TEXT_MUTED)
    canv.drawRightString(PAGE_W - MARGIN_R, PAGE_H - 1.0*cm,
                         "TITAN XAU AI  /  Project State Audit v1.0")
    # Bottom thin line
    canv.setStrokeColor(BORDER)
    canv.setLineWidth(0.3)
    canv.line(MARGIN_L, MARGIN_B - 0.5*cm, PAGE_W - MARGIN_R, MARGIN_B - 0.5*cm)
    # Footer text
    canv.setFont("BodySerif", 8)
    canv.setFillColor(TEXT_MUTED)
    canv.drawString(MARGIN_L, MARGIN_B - 0.9*cm, "Z.ai Engineering  /  CONFIDENTIAL — Internal Use Only")
    canv.drawRightString(PAGE_W - MARGIN_R, MARGIN_B - 0.9*cm, f"Page {doc.page}")
    canv.restoreState()

def draw_cover_frame(canv: canvas.Canvas, doc):
    """Cover page: full navy background, no header/footer."""
    canv.saveState()
    canv.setFillColor(NAVY)
    canv.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    # Crimson accent bar (left edge)
    canv.setFillColor(CRIMSON)
    canv.rect(0, 0, 0.5*cm, PAGE_H, fill=1, stroke=0)
    # Gold horizontal divider
    canv.setFillColor(GOLD)
    canv.rect(MARGIN_L, PAGE_H - 7.0*cm, 4*cm, 0.15*cm, fill=1, stroke=0)
    canv.restoreState()


# === TABLE BUILDERS ===
def make_table(headers, rows, col_widths=None, header_color=BG_TABLE_HEAD, zebra=True):
    """Build a styled table with header + body rows."""
    if col_widths is None:
        col_widths = [CONTENT_W / len(headers)] * len(headers)
    # Wrap header text in paragraphs
    head_row = [Paragraph(h, style_table_head) for h in headers]
    # Wrap body cells in paragraphs
    body_rows = []
    for row in rows:
        body_rows.append([Paragraph(str(c), style_table_cell) for c in row])
    data = [head_row] + body_rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("BOX", (0, 0), (-1, -1), 0.8, NAVY),
    ]
    if zebra:
        for i in range(1, len(data)):
            if i % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), BG_TABLE))
    t.setStyle(TableStyle(style_cmds))
    return t


def verdict_badge(text, color):
    """Return a small colored badge flowable."""
    p = Paragraph(f'<font color="white"><b>{text}</b></font>', style_table_head)
    t = Table([[p]], colWidths=[2.5*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


# === BUILD STORY ===
story = []

# ============ COVER PAGE ============
# Cover content drawn via canvas, but we also need flowables positioned via Spacer.
# Approach: use a single full-page navy background (drawn in draw_cover_frame),
# then push flowables with a top spacer to position the title block.

story.append(Spacer(1, 5.5*cm))  # space above title (gold line at 7cm, title below)
story.append(Paragraph("TITAN XAU AI", style_cover_title))
story.append(Paragraph("Project State Audit", ParagraphStyle(
    "CoverSubBig", fontName="HeadingSans-Bold", fontSize=22, leading=28,
    textColor=colors.white, alignment=TA_LEFT, spaceAfter=14
)))
story.append(Paragraph("Brutally Honest · Evidence-Only · Fresh Session Bootstrap", style_cover_sub))
story.append(Spacer(1, 1.5*cm))

# Cover meta block
meta_lines = [
    ("Document Version", "1.0"),
    ("Audit Date", "2026-06-23"),
    ("Auditor", "Z.ai Engineering (fresh session)"),
    ("Repository", "github.com/ismailiqbal2773/TITAN_XAU_AI"),
    ("Audited Commit", "da52456 (HEAD of main)"),
    ("Previous Phase", "F8 — Reality Gap Closure (commit 2f86364)"),
    ("Verdict", "DEMO READY WITH CRITICAL CAVEATS"),
    ("Classification", "CONFIDENTIAL — Internal Use Only"),
]
meta_data = [[Paragraph(f'<font color="#A0A8B5">{k}</font>', style_cover_meta),
              Paragraph(f'<font color="white">{v}</font>', style_cover_meta)] for k, v in meta_lines]
meta_tbl = Table(meta_data, colWidths=[5*cm, 9*cm])
meta_tbl.setStyle(TableStyle([
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 2),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ("LEFTPADDING", (0, 0), (-1, -1), 0),
]))
story.append(meta_tbl)

story.append(Spacer(1, 3*cm))
# Verdict band at bottom of cover
verdict_para = Paragraph(
    '<font color="white" size="9"><b>HEADLINE FINDING:</b>  The repo is clean, '
    'demo-ready in spec, but <b>NOT live-ready</b>. The user\'s target broker '
    '(FundedNext) has <b>insufficient historical data</b> (37.8% H1 coverage, 1.01% M1), '
    '6 audit reports still cite <b>mathematically impossible frozen-model metrics</b> '
    '(Sharpe 29-55+), and <b>Phase F (live execution engine) does not exist</b>.</font>',
    ParagraphStyle("Verdict", fontName="BodySerif", fontSize=9, leading=13,
                   textColor=colors.white, alignment=TA_LEFT)
)
verdict_tbl = Table([[verdict_para]], colWidths=[CONTENT_W])
verdict_tbl.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), CRIMSON),
    ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ("TOPPADDING", (0, 0), (-1, -1), 10),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
]))
story.append(verdict_tbl)

story.append(PageBreak())

# ============ TABLE OF CONTENTS (manual) ============
story.append(Paragraph("Table of Contents", style_h1))
story.append(HRFlowable(width="100%", thickness=1, color=NAVY, spaceAfter=12))

toc_rows = [
    ["Section", "Page Topic", "Verdict"],
    ["1", "Repository Health", "Clean Tree, 9 Deps Missing"],
    ["2", "Model Inventory", "9 Models Present, No Manifest"],
    ["3", "Architecture Inventory (L1-L7)", "Code Exists, No Live Pipeline"],
    ["4", "Data Inventory", "FundedNext FAILS Coverage"],
    ["5", "Validation Inventory", "6 Reports Cite Impossible Metrics"],
    ["6", "Open Risks", "3 Critical, 4 High"],
    ["7", "Missing Work", "Demo / Shadow / Capital Gates"],
    ["8", "Reality Scorecard", "Overall 45/100"],
    ["9", "Contradictions Audit", "9 Direct Contradictions Found"],
    ["10", "CEO Summary", "Build Phase F, Fix Environment First"],
]
toc_tbl = make_table(toc_rows[0], toc_rows[1:],
                     col_widths=[1.5*cm, 9.5*cm, 5.5*cm])
story.append(toc_tbl)

story.append(Spacer(1, 0.8*cm))
story.append(Paragraph(
    "<b>Audit Method:</b> This audit was performed by inspecting the actual repository state "
    "(git log, file listings, JSON report contents, code imports, Python environment) — "
    "<b>not</b> by summarizing prior phase READMEs. Where prior reports conflict with current "
    "evidence, evidence wins. Where prior reports conflict with each other, both are flagged.",
    style_callout
))

story.append(PageBreak())

# ============ SECTION 1: REPOSITORY HEALTH ============
story.append(Paragraph("Section 1 — Repository Health", style_h1))
story.append(Paragraph(
    "The git working tree is clean and the project is fully committed, but the "
    "Python environment is missing nine production dependencies and three test modules "
    "cannot be collected. The handoff document's claim of \"25+ commits\" and "
    "\"latest commit 2f86364\" are both stale — the repo actually has 48 commits and "
    "the HEAD has moved past Phase F8 to include the handoff document itself.",
    style_body
))

story.append(Paragraph("1.1 Git State", style_h2))
git_rows = [
    ["Current branch", "main", "PASS"],
    ["Latest commit hash", "da52456", "Stale handoff (claimed 2f86364)"],
    ["Latest commit subject", "docs: add NEW_SESSION_HANDOFF.md for cross-session project continuity", "—"],
    ["Latest commit date", "2026-06-22 19:06:26 UTC", "—"],
    ["Total commit count", "48", "Handoff said 25+"],
    ["Uncommitted changes", "0 (clean tree)", "PASS"],
    ["Remote configured", "origin → github.com/ismailiqbal2773/TITAN_XAU_AI.git", "PASS"],
    ["Total files in repo", "5,847", "Matches handoff"],
]
story.append(make_table(["Field", "Value", "Status"], git_rows,
                        col_widths=[5*cm, 8*cm, 3.5*cm]))

story.append(Paragraph("1.2 Python Environment", style_h2))
story.append(Paragraph(
    "Python 3.12.13 is installed and matches the project's stated minimum (3.12+). "
    "However, the installed package set diverges significantly from "
    "<code>titan/requirements.txt</code>. Nine production dependencies are missing, "
    "and two core scientific packages (numpy, pandas) are installed at newer major "
    "or minor versions than pinned — a potential source of silent API breakage.",
    style_body
))
env_rows = [
    ["Python", "3.12.13", "3.12+", "PASS"],
    ["numpy", "2.1.3 (installed)", "1.26.4 (pinned)", "MAJOR VERSION CONFLICT"],
    ["pandas", "2.2.3 (installed)", "2.2.1 (pinned)", "Minor mismatch"],
    ["xgboost", "2.1.3", "2.0.3", "Minor mismatch"],
    ["scipy", "1.14.1", "1.12.0", "Minor mismatch"],
    ["fastapi", "0.128.0", "0.110.0", "Minor mismatch"],
    ["pydantic", "2.12.5", "2.6.4", "Minor mismatch"],
    ["torch", "MISSING", "2.2.2", "BLOCKER — LSTM/Transformer untestable"],
    ["MetaTrader5", "MISSING", "5.0.45", "EXPECTED (Windows-only)"],
    ["onnxruntime", "MISSING", "1.17.1", "ONNX inference blocked"],
    ["sqlalchemy", "MISSING", "2.0.29", "Database layer blocked"],
    ["aiosqlite", "MISSING", "0.20.0", "Database layer blocked"],
    ["structlog", "MISSING", "24.1.0", "Observability blocked"],
    ["optuna", "MISSING", "(not pinned)", "HPO blocked"],
    ["pyarrow", "MISSING", "(not pinned)", "Parquet I/O blocked"],
]
story.append(make_table(["Package", "Installed", "Required", "Status"], env_rows,
                        col_widths=[3.5*cm, 3.8*cm, 3.7*cm, 5.5*cm]))

story.append(Paragraph("1.3 Test Suite Collection", style_h2))
story.append(Paragraph(
    "The test suite collects 381 tests (handoff claims 364). Three test modules fail "
    "to import due to missing dependencies: <code>test_database.py</code> (aiosqlite), "
    "<code>test_infrastructure.py</code> (structlog), and <code>test_recovery.py</code> "
    "(aiosqlite via database layer). Tests that do collect are presumed passing based on "
    "the prior commit history, but cannot be re-verified in this environment without "
    "installing the missing packages.",
    style_body
))
test_rows = [
    ["Tests collected", "381", "PASS (with caveats)"],
    ["Test modules with collection errors", "3 of 20", "FAIL"],
    ["Failed modules", "test_database, test_infrastructure, test_recovery", "—"],
    ["Root cause", "Missing: aiosqlite, structlog", "Fixable with pip install"],
    ["Production modules failing import on Linux", "3 (risk, execution, broker)", "Due to MetaTrader5 (Windows-only)"],
    ["Modules importable on Linux", "ai.xgboost_model, regime.engine, compliance.profiles, training.feature_engine, preprocessing.pipeline", "PASS"],
]
story.append(make_table(["Metric", "Value", "Status"], test_rows,
                        col_widths=[5.5*cm, 8*cm, 3*cm]))

story.append(Paragraph("1.4 Section 1 Verdict", style_h2))
story.append(Paragraph(
    "<b>REPOSITORY HEALTH: 7/10.</b> Git state is clean and verifiable. The Python "
    "environment is the weak link — nine missing dependencies make three test modules "
    "and three production modules (risk, execution, broker) un-importable on this Linux "
    "machine. Production deployment on Windows would resolve the MetaTrader5 import "
    "(it is Windows-only by design), but <code>structlog</code>, <code>aiosqlite</code>, "
    "<code>sqlalchemy</code>, <code>torch</code>, <code>onnxruntime</code>, <code>optuna</code>, "
    "and <code>pyarrow</code> must be installed on any machine that runs TITAN. The numpy "
    "2.x / pandas 2.2.3 mismatch with the pinned 1.26.4 / 2.2.1 versions is a latent "
    "compatibility risk that should be resolved before any production deployment.",
    style_callout
))

story.append(PageBreak())

# ============ SECTION 2: MODEL INVENTORY ============
story.append(Paragraph("Section 2 — Model Inventory", style_h1))
story.append(Paragraph(
    "Nine trained model artifacts are present in <code>titan/data/models/</code>, plus "
    "four HPO parameter JSONs and four Optuna trial databases. The models are real "
    "(verified by file size and format: .pkl for sklearn/xgboost, .pt for PyTorch). "
    "However, there is <b>no model registry file</b> that records training date, "
    "training dataset period, or which validation produced which metric. The Phase F8 "
    "verdict explicitly rejects the frozen v1 metrics as unattainable in live trading, "
    "yet the v1 models remain the only production-ready artifacts.",
    style_body
))

story.append(Paragraph("2.1 Model File Inventory", style_h2))
model_rows = [
    ["xgboost_v1.pkl", "1.9 MB", "XGBoost", "v1 (frozen)", "L1 Signal Engine", "Primary directional model"],
    ["xgboost_v2_micro.pkl", "1.2 MB", "XGBoost", "v2 (micro features)", "L1 alt", "9 microstructure features only"],
    ["lstm_v1.pt", "652 KB", "PyTorch LSTM", "v1 (frozen)", "L1 alt", "2 layers, 128 hidden (per manifest)"],
    ["lstm_v2_clean.pt", "608 KB", "PyTorch LSTM", "v2 (clean features)", "L1 alt", "22 features (micro+price)"],
    ["transformer_v1.pt", "816 KB", "PyTorch Transformer", "v1 (frozen)", "L1 alt", "8 heads, 6 layers (per manifest)"],
    ["meta_label_v1.pkl", "4.0 KB", "Logistic Regression", "v1", "L2 Meta-Label", "Trade quality filter"],
    ["meta_label_v2_context.pkl", "4.0 KB", "Logistic Regression", "v2 (context)", "L2 Meta-Label", "With H4/D1 context"],
    ["logreg_v1_price.pkl", "4.0 KB", "Logistic Regression", "v1", "L1 alt (price only)", "13 price features"],
    ["lightgbm_v1.pkl", "672 KB", "LightGBM", "v1", "L1 alt", "Trained via HPO (Optuna)"],
]
story.append(make_table(
    ["File", "Size", "Type", "Version", "Layer", "Notes"],
    model_rows,
    col_widths=[3.6*cm, 1.5*cm, 3.0*cm, 2.5*cm, 2.5*cm, 3.4*cm]
))

story.append(Paragraph("2.2 HPO Parameters (Best Trials)", style_h2))
hpo_rows = [
    ["XGBoost", "max_depth=7, n_estimators=397, lr=0.0175, subsample=0.70, colsample=0.95, gamma=1.98, reg_alpha=3.97, reg_lambda=3.65", "xgb_trials.db (184 KB)"],
    ["LightGBM", "max_depth=5, n_estimators=219, num_leaves=119, lr=0.0203, subsample=0.93, colsample=0.69, reg_alpha=7.84, reg_lambda=0.75", "lgbm_trials.db (184 KB)"],
    ["LSTM", "hidden_size=85, num_layers=3, dropout=0.139, lr=0.000585, batch_size=128", "lstm_trials.db (132 KB)"],
    ["Transformer", "d_model=64, nhead=4, num_layers=4, dropout=0.297, lr=0.000716, batch_size=64", "transformer_trials.db (132 KB)"],
]
story.append(make_table(["Model", "Best Parameters", "Trials DB"], hpo_rows,
                        col_widths=[2.5*cm, 10.5*cm, 3.5*cm]))

story.append(Paragraph("2.3 Validation Metrics — Reconciled", style_h2))
story.append(Paragraph(
    "The metrics below are <b>reconciled from JSON evidence</b>, not from README claims. "
    "Three different metric families exist in the repo and they are <b>not interchangeable</b>: "
    "(a) frozen-model annualized metrics (mathematically inflated, rejected by F8), "
    "(b) frozen-model daily metrics (the \"frozen\" column in handoff), and "
    "(c) walk-forward rebuild metrics (the \"truth\" per F8). Many prior JSON reports "
    "still cite family (a) as PASS — these reports are technically still in the repo "
    "without a \"SUPERSEDED\" marker.",
    style_body
))
metrics_rows = [
    ["AUC", "0.79 (frozen H1 annualized)", "0.76 (rebuild)", "0.712 (live haircut)", "REJECTED by F8"],
    ["Profit Factor", "5.29 (frozen annualized)", "3.34 (rebuild)", "2.65 (live haircut)", "REJECTED by F8"],
    ["Win Rate", "74.7% (frozen)", "69.3% (rebuild)", "66.7% (live haircut)", "REJECTED by F8"],
    ["Sharpe (annualized)", "36.95 (frozen H1)", "1.66 (daily, rebuild)", "1.46 (daily, live)", "REJECTED by F8"],
    ["Sharpe (daily)", "2.33 (frozen daily)", "1.66 (rebuild)", "1.46 (live haircut)", "Frozen rejected"],
    ["Max Drawdown", "3.16% (frozen)", "4.45% (rebuild)", "5.01% (live haircut)", "REJECTED by F8"],
    ["Trades/year", "4,087 (frozen)", "2,737 (rebuild)", "2,463 (live haircut)", "—"],
]
story.append(make_table(
    ["Metric", "Frozen (annualized)", "Rebuild (truth)", "Live (haircut)", "Status"],
    metrics_rows,
    col_widths=[3.2*cm, 3.5*cm, 3.2*cm, 3.5*cm, 3.1*cm]
))

story.append(Paragraph("2.4 Deployment Status", style_h2))
dep_rows = [
    ["xgboost_v1.pkl", "Frozen (training complete)", "Champion (per F-Prime spec)", "Last audit: F8 (2026-06-22) — Retrain Required"],
    ["meta_label_v2_context.pkl", "Frozen", "Champion", "F8 Section 2: KEEP (positive uplift all 4 years)"],
    ["transformer_v1.pt", "Frozen", "Challenger (per F-Prime)", "F8: +0.18 Sharpe contribution"],
    ["lstm_v1.pt / v2_clean.pt", "Frozen", "Challenger", "F8: not used in live inference chain (L1 = XGBoost only)"],
    ["lightgbm_v1.pkl", "Frozen", "Challenger", "Not in F8 inference chain"],
    ["logreg_v1_price.pkl", "Frozen", "Reference model (price-only)", "Not in F8 inference chain"],
]
story.append(make_table(
    ["Model", "Status", "Role", "Last Audit"],
    dep_rows,
    col_widths=[3.8*cm, 3.2*cm, 3.8*cm, 5.7*cm]
))

story.append(Paragraph("2.5 Section 2 Verdict", style_h2))
story.append(Paragraph(
    "<b>MODEL INVENTORY: 6/10.</b> All nine model artifacts are present and real, but "
    "the lack of a machine-readable model registry (training date, dataset period, "
    "validation metrics per model) makes provenance audit difficult. The coexistence "
    "of three incompatible metric families in the same repo — with the inflated "
    "frozen-model numbers still cited as PASS in six JSON audit reports — is a "
    "documentation hazard for any future developer or auditor. The Phase F8 "
    "recommendation to retrain L1 XGBoost with 2025-2026 walk-forward data is the "
    "single most important model-side action.",
    style_callout
))

story.append(PageBreak())

# ============ SECTION 3: ARCHITECTURE INVENTORY ============
story.append(Paragraph("Section 3 — Architecture Inventory (L1–L7)", style_h1))
story.append(Paragraph(
    "The 7-layer architecture is <b>specified</b> in Phase F-Prime and <b>partially "
    "implemented</b> across the existing codebase. However, the live inference chain "
    "(L1 → L2 → L3 → L4 → L5 → L6 → L7) <b>does not exist as runnable code</b>. "
    "The <code>titan/production/</code> directory mentioned in the handoff document "
    "<b>does not exist</b>. Each layer's components are present as standalone modules, "
    "but no orchestrator wires them into a live trading loop. This is the core gap "
    "Phase F is meant to close.",
    style_body
))

arch_rows = [
    ["L1", "Signal Engine", "XGBoost + Platt calibration", "P ≥ 0.55",
     "IMPLEMENTED (titan/ai/xgboost_model.py, 214 lines)", "TESTED (test_ai_layer, 25 tests)", "NO (no live inference path)"],
    ["L2", "Meta-Label", "Logistic Regression", "P(win) ≥ 0.65",
     "IMPLEMENTED (meta_label_v2_context.pkl, 4 KB)", "TESTED indirectly (Phase A audit)", "NO"],
    ["L3", "Context / Regime", "Transformer HMM (per spec) / 3-model vote (per code)",
     "mult ∈ {0, 0.5, 1.0}",
     "IMPLEMENTED (titan/regime/engine.py, 17.5 KB)", "TESTED (test_regime, 17 tests)", "NO"],
    ["L4", "Risk Engine", "Kelly 10/25% + Risk Parity", "heat ≤ 6%, trade ≤ 1.5%",
     "IMPLEMENTED (titan/risk/engine.py, 15.7 KB)", "TESTED (test_risk, 11 tests)", "NO (cannot import on Linux)"],
    ["L5", "Execution Engine", "Slippage model, spread-aware", "σ = 0.18 pip",
     "IMPLEMENTED (titan/execution/engine.py, 13.9 KB)", "TESTED (test_execution, 13 tests)", "NO (cannot import on Linux)"],
    ["L6", "Monitoring", "5 monitors: AUC/WR/ECE/PSI/KS", "Drift thresholds",
     "PARTIAL (titan/observability/metrics.py, 7.9 KB)", "TESTED (test_infrastructure, 18 tests)", "NO (structlog missing)"],
    ["L7", "Kill-Switch", "5-state FSM, hard kill on 5 conditions", "< 500 ms SLA",
     "SCATTERED (risk/engine.py + execution + recovery/manager.py + database/layer.py)", "PARTIAL (test_risk covers some paths)", "NO"],
]
story.append(make_table(
    ["#", "Layer", "Model / Method", "Threshold", "Implementation Status", "Test Status", "Production Ready?"],
    arch_rows,
    col_widths=[0.6*cm, 1.8*cm, 2.8*cm, 2.0*cm, 3.5*cm, 2.5*cm, 2.3*cm]
))

story.append(Paragraph("3.1 Critical Architecture Gaps", style_h2))
story.append(Paragraph(
    "The following components are <b>specified</b> in Phase F-Prime or Phase F.6 but are "
    "<b>not present</b> in the repository as runnable code. Each is a hard prerequisite "
    "for live trading.",
    style_body
))
gap_rows = [
    ["Live MT5 Python connector", "titan/production/mt5_connector.py", "NO", "Phase F-Prime Ch. 8", "5 days"],
    ["Real-time incremental feature pipeline", "titan/production/feature_stream.py", "NO", "Phase F-Prime Ch. 3", "7 days"],
    ["7-layer inference orchestrator", "titan/production/inference.py", "NO", "Phase F-Prime Ch. 2", "10 days"],
    ["Broker-side hard SL/TP submission", "Extend titan/execution/engine.py", "PARTIAL (order_send supports SL/TP fields)", "Phase F-Prime Ch. 6", "2 days"],
    ["Position sync on startup", "titan/production/position_sync.py", "NO", "Phase F-Prime Ch. 3.5", "3 days"],
    ["Watchdog process + auto-restart", "titan/recovery/watchdog.py (exists, 5.6 KB) — needs deployment wrapper", "PARTIAL", "Phase F.6 Tier 1", "3 days"],
    ["Kill-switch FSM (5-state)", "titan/production/kill_switch.py", "NO (logic scattered across 4 files)", "Phase F-Prime Ch. 6", "5 days"],
    ["Grafana dashboard setup", "titan/production/grafana/", "NO", "Phase F-Prime Ch. 5", "5 days"],
    ["TITAN.bat one-click launcher", "TITAN.bat (Windows)", "NO (only RUN_ON_WINDOWS.bat for data acquisition)", "Phase F.6 Tier 1", "2 days"],
    ["Total Phase F effort", "—", "—", "—", "~40 days"],
]
story.append(make_table(
    ["Component", "Expected Path", "Exists?", "Spec", "Effort"],
    gap_rows,
    col_widths=[4.5*cm, 4.5*cm, 2.2*cm, 3.0*cm, 2.3*cm]
))

story.append(Paragraph("3.2 Section 3 Verdict", style_h2))
story.append(Paragraph(
    "<b>ARCHITECTURE: 4/10.</b> Every L1–L7 component exists as a tested module, but "
    "no live inference chain wires them together. The <code>titan/production/</code> "
    "directory does not exist. The kill-switch logic is scattered across at least "
    "four files (risk, execution, recovery, database) instead of being a dedicated "
    "FSM as Phase F-Prime specifies. The watchdog module exists in "
    "<code>titan/recovery/watchdog.py</code> but has no deployment wrapper. Phase F "
    "is the largest single piece of missing work — ~40 engineering days — and is "
    "the gate that separates \"research project\" from \"trading system\".",
    style_callout
))

story.append(PageBreak())

# ============ SECTION 4: DATA INVENTORY ============
story.append(Paragraph("Section 4 — Data Inventory", style_h1))
story.append(Paragraph(
    "TITAN has two real data sources: Dukascopy M1 ticks (interbank baseline) and "
    "MT5 broker-specific bars from four brokers (Exness, FBS, FundedNext, IC Markets). "
    "The aggregate v4 audit claims <code>REAL_MT5_DATA_VERIFIED_4_BROKERS</code>, but "
    "the per-broker audit JSONs tell a different story — <b>FundedNext (the user's "
    "target broker) has insufficient historical data</b>, and the aggregate verdict "
    "achieves \"verified\" status only by excluding FundedNext from its pass conditions.",
    style_body
))

story.append(Paragraph("4.1 Dukascopy (Interbank Baseline)", style_h2))
duk_rows = [
    ["Storage location", "titan/data/sources/dukascopy/daily/"],
    ["Daily parquet files", "1,302 (project_memory.md says 587 — STALE)"],
    ["Monthly merged files", "7 (XAUUSD_M1_YYYY-M.parquet)"],
    ["Date range", "2020-01-01 → 2024-12-31"],
    ["Approximate M1 bars", "~783,085 (per project_memory, not re-counted here)"],
    ["Synthetic data", "0% (verified — Dukascopy direct download)"],
    ["Quality", "HIGH (real interbank tick data, no calibration)"],
]
story.append(make_table(["Field", "Value"], duk_rows, col_widths=[5*cm, 11.5*cm]))

story.append(Paragraph("4.2 MT5 Broker Data (4 Brokers)", style_h2))
broker_rows = [
    ["Exness", "real", "Exness-MT5Real3", "Login 44974666", "38,215 (H1, 119.08%)", "PASS", "M1: 21,924 bars (only ~3 weeks recent)"],
    ["FBS", "demo", "FBS-Demo", "Login 106259467", "36,782 (H1, 95.2%)", "PASS", "Adequate"],
    ["FundedNext", "demo", "FundedNext-Server 3", "Login 34265693", "14,460 (H1, 37.8%)", "FAIL", "M1: 22,141 bars (1.01% coverage) — REJECTED"],
    ["IC Markets", "demo", "(server in audit JSON)", "Login (per JSON)", "38,244 (H1, 98.93%)", "PASS", "Best coverage, tightest spreads (3.68 pts)"],
]
story.append(make_table(
    ["Broker", "Type", "Server", "Login", "H1 Bars (Coverage)", "Pass 95%?", "Notes"],
    broker_rows,
    col_widths=[1.8*cm, 1.2*cm, 2.7*cm, 2.2*cm, 2.8*cm, 1.5*cm, 4.3*cm]
))

story.append(Paragraph(
    "<b>CRITICAL:</b> The FundedNext per-broker audit JSON (<code>titan/data/sources/"
    "mt5_brokers/fundednext/MT5_Audit_Report.json</code>) explicitly returns "
    "<code>verdict: DATA_REJECTED</code> with <code>coverage_95: False</code>. "
    "FundedNext's H1 coverage is 37.8% (target 95%) and M1 coverage is 1.01% "
    "(target 95%). The aggregate v4 audit JSON marks the overall verdict as "
    "<code>REAL_MT5_DATA_VERIFIED_4_BROKERS</code> but its pass conditions list "
    "only three brokers (Exness, FBS, IC Markets) — FundedNext is silently excluded. "
    "Since FundedNext is the user's target broker for live trading, this is the "
    "single most important data-side risk in the project.",
    style_critical
))

story.append(Paragraph("4.3 Timeframe Coverage (Canonical Merged)", style_h2))
story.append(Paragraph(
    "After preprocessing (4-broker median merge), the canonical datasets are:",
    style_body
))
canonical_rows = [
    ["M5", "101,092 bars", "2025-01-17 → 2026-06-19", "~5 months"],
    ["M15", "100,645 bars", "2022-03-22 → 2026-06-19", "~4.3 years"],
    ["M30", "76,069 bars", "2020-01-02 → 2026-06-19", "~6.5 years"],
    ["H1", "38,234 bars", "2020-01-02 → 2026-06-19", "~6.5 years (BEST COVERAGE)"],
]
story.append(make_table(
    ["Timeframe", "Bars (canonical)", "Date Range", "Span"],
    canonical_rows,
    col_widths=[2.5*cm, 3.5*cm, 6.5*cm, 4.0*cm]
))

story.append(Paragraph("4.4 Data Quality Score", style_h2))
quality_rows = [
    ["Coverage (training readiness gate)", "98.87%", "1,669 / 1,688 trading days present", "PASS"],
    ["Missing days", "19", "All confirmed market holidays", "PASS"],
    ["Duplicate timestamps (canonical)", "0", "—", "PASS"],
    ["Bars with ≥2 brokers (cross-validation)", "100%", "—", "PASS"],
    ["Bars with ≥3 brokers", "92.47%", "—", "PASS"],
    ["Bars with all 4 brokers", "35.48%", "Expected — Exness is on different LP", "Acceptable"],
    ["Regime distribution max %", "49.9% (TREND_UP)", "Below 60% threshold — regime-stable", "PASS"],
    ["Spread normalization", "Correct (Exness 0.001, others 0.01 → USD)", "—", "PASS"],
    ["Mean spread (USD)", "0.132", "—", "Reasonable"],
    ["Data leakage from preprocessing", "None detected", "—", "PASS"],
    ["FundedNext broker-specific coverage (H1)", "37.8%", "Below 95% requirement", "FAIL"],
]
story.append(make_table(
    ["Check", "Value", "Detail", "Status"],
    quality_rows,
    col_widths=[5*cm, 3*cm, 5.5*cm, 3*cm]
))

story.append(Paragraph("4.5 Section 4 Verdict", style_h2))
story.append(Paragraph(
    "<b>DATA INVENTORY: 6/10.</b> The aggregate data quality is high (98.87% coverage, "
    "0% synthetic, 4-broker cross-validation, regime-balanced). However, the "
    "<b>FundedNext-specific data is inadequate for broker-specific backtesting</b> — "
    "the user's target broker only provides 37.8% H1 coverage and 1.01% M1 coverage. "
    "Live trading on FundedNext will require either (a) accepting that backtested "
    "metrics were derived from Dukascopy/ICMarkets data and may not perfectly "
    "translate to FundedNext's spreads/execution, or (b) acquiring more FundedNext "
    "historical data before going live. The contradiction between the aggregate "
    "verdict (VERIFIED) and the per-broker verdict (REJECTED) is a documentation "
    "defect that must be fixed.",
    style_callout
))

story.append(PageBreak())

# ============ SECTION 5: VALIDATION INVENTORY ============
story.append(Paragraph("Section 5 — Validation Inventory", style_h1))
story.append(Paragraph(
    "The repo contains <b>33 JSON audit artifacts</b> in <code>download/</code>, plus "
    "5 phase-specific result JSONs. The list below summarizes every distinct "
    "validation performed, with the <b>actual verdict extracted from the JSON</b> "
    "(not the README summary). Where the JSON's own metrics contradict its verdict, "
    "the contradiction is flagged.",
    style_body
))

val_rows = [
    ["Alpha Validity Audit", "TITAN_Alpha_Validity_Audit_v1.0.json", "2026-06-21", "GENUINE", "PASS",
     "Permutation test p=0.0 (15 trials). Confusion matrix AUC=0.777. Class balance LOW risk."],
    ["Economic Sanity Audit", "TITAN_Economic_Sanity_Audit_v1.0.json", "2026-06-21", "Corrected", "PASS (with corrections)",
     "Found 100x cost underestimate in previous audit (per-oz vs per-lot). Corrected total cost = $30.20/lot."],
    ["Execution Safety Layer", "TITAN_Execution_Safety_Layer_v1.0.json", "2026-06-21", "PASS", "PASS",
     "Survives 5x cost explosion, 1000ms latency. Uses FROZEN Sharpe 29.8 (rejected by F8)."],
    ["Training Readiness Gate", "TITAN_Training_Readiness_Gate_v1.0.json", "2026-06-21", "PASS", "PASS",
     "98.87% coverage, 63 features, 0 future leakage. Solid gate."],
    ["Final Institutional Validation Gate", "TITAN_Final_Institutional_Validation_Gate.json", "2026-06-21", "PASS", "PASS",
     "Feature ablation, shuffle test, WFA all pass. AUC ~0.78 (rebuild-consistent)."],
    ["Reality Audit v1.0", "TITAN_Reality_Audit_v1.0.json", "2026-06-22", "REALITY_VERIFIED", "PASS (with caveat)",
     "★ Self-flagged: 'Sharpe=36.95 (>10) — SUSPICIOUS. Daily Sharpe = 2.33' — annualization artifact."],
    ["Walk-Forward Validation", "TITAN_Walk_Forward_Validation.json", "2026-06-22", "PASSED", "FAILS INTERNAL CONSISTENCY",
     "★ Claims Sharpe 55.04 / PF 14.63 / WR 86.3% — mathematically impossible for real trading. FROZEN-annualized."],
    ["Monte Carlo v2", "TITAN_Monte_Carlo_v2.json", "2026-06-22", "PASS", "FAILS INTERNAL CONSISTENCY",
     "★ Claims Sharpe 37.04 / PF 5.30 — frozen-model annualized. Survival rate 100% (suspicious)."],
    ["Red Team Audit", "TITAN_Red_Team_Audit.json", "2026-06-22", "SAFE FOR DEMO (81.9/100)", "FAILS INTERNAL CONSISTENCY",
     "★ Uses Sharpe 29.8 (frozen). 'PASS' on metrics F8 later rejected."],
    ["Alpha Decay Report", "TITAN_Alpha_Decay_Report.json", "2026-06-22", "Robust up to 50% trade filter", "INFORMATIVE",
     "Shows PF improves as low-quality trades removed (frozen-model math)."],
    ["Failure Point Report", "TITAN_Failure_Point_Report.json", "2026-06-22", "ROBUST", "PASS (frozen-model context)",
     "Survives 60% trend-up removal, 5x costs, meta-label removal. Context removal = no impact (contradicts F8)."],
    ["Clean Model Performance Report", "TITAN_Clean_Model_Performance_Report.json", "2026-06-22", "FURTHER REFINEMENT REQUIRED", "MIXED",
     "Clean XGB AUC 0.775 vs old 0.788 — small regression. LSTM+TF ensemble correlation 0.96 (low diversity)."],
    ["Pre-HPO Reality Check", "TITAN_Pre_HPO_Reality_Check_v1.0.json", "2026-06-21", "(informative)", "—",
     "Reality check before HPO."],
    ["Baseline Model Test", "TITAN_Baseline_Model_Test_v1.0.json", "2026-06-21", "(informative)", "—",
     "Baseline before HPO optimization."],
    ["Phase F.5 Reality Simulator", "phase_f5/titan_phase_f5_results.json", "2026-06-22", "Demo Ready (Prod 54, Capital 24)", "PASS for demo",
     "27 stress scenarios. 0% market-event survival (CRITICAL — news pre-halt missing)."],
    ["Phase F.6 Hybrid Deployment", "phase_f6/titan_phase_f6_results.json", "2026-06-22", "All 3 tiers ready, World-Class NO", "PASS for demo",
     "Tier 1 (retail/local), Tier 2 (VPS), Tier 3 (dual-VPS failover). No tier claims World-Class."],
    ["Phase F.7 Live Performance Prediction", "phase_f7/titan_phase_f7_results.json", "2026-06-22", "DEMO READY (score 72.3)", "PASS for demo",
     "Yearly baseline shows alpha decay: AUC 0.78→0.73 (2023→2026), Sharpe 2.18→1.34."],
    ["Phase F8 Reality Gap Closure", "phase_f8/titan_phase_f8_results.json", "2026-06-22", "Retrain Required (gap 0.22)", "FAIL for shadow-live",
     "Optimization ceiling: Sharpe 1.58 < 1.80 target. Must retrain L1 XGBoost."],
    ["Real MT5 Data Final Audit v4.0", "TITAN_Real_MT5_Data_Final_Audit_v4.0_4brokers.json", "2026-06-21", "REAL_MT5_DATA_VERIFIED_4_BROKERS", "CONTRADICTS per-broker audits",
     "Aggregate verdict ignores FundedNext failure (per-broker audit says DATA_REJECTED)."],
]
story.append(make_table(
    ["Audit Name", "JSON File", "Date", "Verdict", "Status", "Key Finding"],
    val_rows,
    col_widths=[3.5*cm, 3.8*cm, 1.5*cm, 2.3*cm, 2.0*cm, 3.4*cm]
))

story.append(Paragraph("5.1 Section 5 Verdict", style_h2))
story.append(Paragraph(
    "<b>VALIDATION INVENTORY: 5/10.</b> The breadth of validation work is impressive "
    "(19 distinct audits, 33+ JSON artifacts). However, <b>six audit reports still "
    "cite mathematically impossible frozen-model metrics</b> (Sharpe 29–55+) as PASS, "
    "despite Phase F8 explicitly rejecting those metrics as unattainable in live "
    "trading. The Reality Audit v1.0 is the only frozen-era report that honestly "
    "self-flags its own Sharpe as \"SUSPICIOUS\". The aggregate MT5 data audit "
    "(v4.0) directly contradicts the per-broker FundedNext audit. These "
    "inconsistencies create a documentation hazard: any new developer reading the "
    "repo could cite the inflated Sharpe 37 as \"validated\" without realizing "
    "Phase F8 has superseded it.",
    style_callout
))

story.append(PageBreak())

# ============ SECTION 6: OPEN RISKS ============
story.append(Paragraph("Section 6 — Open Risks", style_h1))
story.append(Paragraph(
    "Risks below are ranked by severity. <b>Critical</b> = blocks live trading. "
    "<b>High</b> = blocks shadow-live or causes significant rework. <b>Medium</b> = "
    "operational drag or documentation hazard. <b>Low</b> = cosmetic or future-work.",
    style_body
))

story.append(Paragraph("6.1 Critical Risks (3)", style_h2))
crit_rows = [
    ["C1", "FundedNext data inadequate",
     "FundedNext H1 coverage = 37.8%, M1 = 1.01%. User's target broker cannot support broker-specific backtesting.",
     "Acquire more FundedNext history via Windows MT5 script, OR explicitly accept cross-broker backtest translation risk."],
    ["C2", "Phase F (live execution engine) does not exist",
     "titan/production/ directory is absent. No live MT5 connector, no real-time feature pipeline, no 7-layer inference orchestrator, no kill-switch FSM, no TITAN.bat.",
     "Build Phase F per Phase F-Prime spec (~40 engineering days)."],
    ["C3", "Live Sharpe 1.46 below 1.80 shadow-live gate",
     "F8 optimization ceiling is 1.58 (gap 0.22). Cannot close without retraining L1 XGBoost with 2025-2026 walk-forward data.",
     "Deploy demo now. Retrain L1 in parallel. Re-evaluate after 30-day demo + retrain."],
]
story.append(make_table(
    ["ID", "Risk", "Description", "Mitigation"],
    crit_rows,
    col_widths=[0.8*cm, 3.5*cm, 6.5*cm, 5.7*cm]
))

story.append(Paragraph("6.2 High Risks (4)", style_h2))
high_rows = [
    ["H1", "0% market-event survival (Phase F.5)",
     "Phase F.5 stress simulator: TITAN has 0% survival rate on news-event scenarios. No news pre-halt implemented.",
     "Add economic calendar feed + pre-event position flatten (Phase F-Prime Ch. 6). Mandatory before any capital."],
    ["H2", "Operational readiness 45/100",
     "No on-call rotation, no runbook, no MRO (Maintenance, Repair, Operations) process. Capital deployment forbidden.",
     "Build runbook, define on-call, document MRO before shadow-live."],
    ["H3", "Kill-switch logic scattered across 4+ files",
     "risk/engine.py, execution/engine.py, recovery/manager.py, database/layer.py all contain kill-switch fragments. No single FSM.",
     "Consolidate into titan/production/kill_switch.py as 5-state FSM per Phase F-Prime Ch. 6."],
    ["H4", "numpy 2.x vs requirements 1.26.x",
     "Major version mismatch. Pandas 2.2.3 vs 2.2.1 also mismatched. Potential silent API breakage in production.",
     "Pin to exact requirements.txt versions, OR update requirements.txt to match installed and re-test."],
]
story.append(make_table(
    ["ID", "Risk", "Description", "Mitigation"],
    high_rows,
    col_widths=[0.8*cm, 3.5*cm, 6.5*cm, 5.7*cm]
))

story.append(Paragraph("6.3 Medium Risks (5)", style_h2))
med_rows = [
    ["M1", "6 audit reports cite impossible frozen metrics as PASS",
     "Walk-Forward, Monte Carlo v2, Red Team, Execution Safety, Alpha Decay, Failure Point all cite Sharpe 29-55+.",
     "Add 'SUPERSEDED' marker to those JSONs OR re-issue them with rebuild metrics."],
    ["M2", "Aggregate vs per-broker MT5 audit contradiction",
     "v4.0 says VERIFIED_4_BROKERS; FundedNext/Exness per-broker audits say DATA_REJECTED.",
     "Fix aggregate verdict logic to require ALL brokers pass, OR explicitly mark tier-B brokers."],
    ["M3", "9 Python dependencies missing in environment",
     "structlog, aiosqlite, sqlalchemy, torch, onnxruntime, optuna, pyarrow, MetaTrader5, asyncio not installed.",
     "pip install -r titan/requirements.txt on production machine (Windows for MetaTrader5)."],
    ["M4", "No model registry / manifest",
     "9 model files exist but no JSON records training date, dataset period, or validation metrics per model.",
     "Generate titan/data/models/manifest.json with SHA256 + training metadata for each artifact."],
    ["M5", "project_memory.md is stale",
     "Says 587 Dukascopy daily files; actual is 1,302. Says 'in progress' for data acquisition; reality is complete.",
     "Update project_memory.md to reflect current state."],
]
story.append(make_table(
    ["ID", "Risk", "Description", "Mitigation"],
    med_rows,
    col_widths=[0.8*cm, 3.5*cm, 6.5*cm, 5.7*cm]
))

story.append(Paragraph("6.4 Low Risks (3)", style_h2))
low_rows = [
    ["L1", "Handoff doc commit hash stale",
     "Handoff says 'Latest Commit 2f86364'; actual is da52456 (handoff doc commit itself).",
     "Update handoff doc OR accept that handoff doc ages by one commit (itself)."],
    ["L2", "Handoff doc test count stale",
     "Says 364 tests; actual is 381.",
     "Update handoff doc."],
    ["L3", "FundedNext server name mismatch",
     "Handoff says 'FundedNext-Demo'; audit JSON says 'FundedNext-Server 3'.",
     "Update handoff doc to match verified broker server name."],
]
story.append(make_table(
    ["ID", "Risk", "Description", "Mitigation"],
    low_rows,
    col_widths=[0.8*cm, 3.5*cm, 6.5*cm, 5.7*cm]
))

story.append(PageBreak())

# ============ SECTION 7: MISSING WORK ============
story.append(Paragraph("Section 7 — Missing Work (Gates)", style_h1))
story.append(Paragraph(
    "Three deployment gates must be cleared in sequence: Demo → Shadow Live → Real Capital. "
    "Each gate has hard prerequisites that cannot be skipped. The list below is "
    "<b>evidence-based</b> — it reflects what is actually missing in the repo, not "
    "what the handoff doc says is missing.",
    style_body
))

story.append(Paragraph("7.1 Gate A — Demo Trading (FundedNext demo account)", style_h2))
story.append(Paragraph(
    "Target: 30-day unattended demo run on FundedNext demo account (login 34265693). "
    "This is the cheapest insurance Phase F8 strongly recommends. Estimated effort: "
    "~40 engineering days.",
    style_body
))
demo_rows = [
    ["1", "Live MT5 Python connector", "Phase F-Prime Ch. 8", "5 days", "NO"],
    ["2", "Real-time incremental feature pipeline", "Phase F-Prime Ch. 3", "7 days", "NO"],
    ["3", "7-layer inference orchestrator (L1→L7)", "Phase F-Prime Ch. 2", "10 days", "NO"],
    ["4", "Broker-side hard SL/TP on every order", "Phase F-Prime Ch. 6", "2 days", "PARTIAL (field exists in OrderRequest)"],
    ["5", "Position sync on startup (broker = source of truth)", "Phase F-Prime Ch. 3.5", "3 days", "NO"],
    ["6", "Watchdog process + auto-restart wrapper", "Phase F.6 Tier 1", "3 days", "PARTIAL (watchdog.py exists, no wrapper)"],
    ["7", "Kill-switch FSM (5-state)", "Phase F-Prime Ch. 6", "5 days", "SCATTERED (4 files, no FSM)"],
    ["8", "TITAN.bat one-click launcher (Windows)", "Phase F.6 Tier 1", "2 days", "NO"],
    ["9", "Local Grafana dashboard (optional for demo)", "Phase F-Prime Ch. 5", "3 days", "NO"],
    ["10", "Accept FundedNext cross-broker translation risk", "This audit §4", "0 days (decision)", "PENDING"],
    ["", "TOTAL", "", "~40 days", ""],
]
story.append(make_table(
    ["#", "Component", "Spec", "Effort", "Status"],
    demo_rows,
    col_widths=[0.7*cm, 5.5*cm, 3.5*cm, 1.8*cm, 5.0*cm]
))

story.append(Paragraph("7.2 Gate B — Shadow Live (micro-lots 0.01)", style_h2))
story.append(Paragraph(
    "Target: Live execution with real money at 0.01 lot size. Requires Gate A complete "
    "AND Sharpe ≥ 1.80 (rebuild, post-haircut). Per F8: optimization ceiling is 1.58, "
    "gap 0.22 requires L1 XGBoost retrain with 2025-2026 walk-forward data.",
    style_body
))
shadow_rows = [
    ["1", "All Gate A items complete", "§7.1", "~40 days", "NO"],
    ["2", "30-day demo run with no kill-switch triggers", "Phase F8 Action Plan", "30 days", "NO"],
    ["3", "L1 XGBoost retrain (2025-2026 walk-forward data)", "Phase F8 §7", "10-15 days", "NO"],
    ["4", "Retrained model passes 7-day shadow test", "Phase F8 §7", "7 days", "NO"],
    ["5", "Sharpe ≥ 1.80 (rebuild metric, post-haircut)", "Shadow-live gate", "—", "FAIL (current 1.46)"],
    ["6", "News-event pre-halt (economic calendar + flatten)", "Phase F.5 (0% survival finding)", "5 days", "NO"],
    ["7", "Drift monitoring active (PSI/ECE/AUC) with Slack alerts", "Phase F-Prime Ch. 5", "3 days", "NO"],
    ["", "TOTAL (after Gate A)", "", "~50 days", ""],
]
story.append(make_table(
    ["#", "Component", "Spec", "Effort", "Status"],
    shadow_rows,
    col_widths=[0.7*cm, 5.5*cm, 3.5*cm, 1.8*cm, 5.0*cm]
))

story.append(Paragraph("7.3 Gate C — Real Capital (production deployment)", style_h2))
story.append(Paragraph(
    "Target: Live trading at full intended position size. Requires Gate B complete "
    "AND operational readiness ≥ 80/100 (current: 45/100). Capital deployment without "
    "operational readiness is forbidden per project iron rules.",
    style_body
))
capital_rows = [
    ["1", "All Gate B items complete", "§7.2", "~50 days", "NO"],
    ["2", "Operational readiness ≥ 80/100 (current: 45/100)", "Phase F.7", "—", "FAIL"],
    ["3", "On-call rotation defined (24/7 coverage)", "Operational readiness", "5 days", "NO"],
    ["4", "Runbook (incident response, kill-switch recovery, restart)", "Operational readiness", "5 days", "NO"],
    ["5", "MRO process (maintenance, repair, operations)", "Operational readiness", "5 days", "NO"],
    ["6", "Grafana + PagerDuty alerts wired", "Phase F.6 Tier 2/3", "3 days", "NO"],
    ["7", "Failover VPS (Tier 3 institutional only)", "Phase F.6 Tier 3", "10 days", "NO (Tier 1 sufficient for retail)"],
    ["8", "Compliance engine verified for prop firm rules", "titan/compliance/profiles.py", "—", "TESTED (69 tests)"],
    ["9", "Licensing engine verified (3 tiers)", "titan/licensing/", "—", "TESTED (47 tests)"],
    ["", "TOTAL (after Gate B)", "", "~30 days", ""],
]
story.append(make_table(
    ["#", "Component", "Spec", "Effort", "Status"],
    capital_rows,
    col_widths=[0.7*cm, 5.5*cm, 3.5*cm, 1.8*cm, 5.0*cm]
))

story.append(Paragraph("7.4 Section 7 Verdict", style_h2))
story.append(Paragraph(
    "<b>MISSING WORK: ~120 engineering days to Real Capital.</b> Gate A (Demo) is "
    "~40 days and is the immediate next milestone. Gate B (Shadow Live) is ~50 days "
    "after Gate A and depends on the L1 retrain closing the Sharpe gap. Gate C "
    "(Capital) is ~30 days after Gate B and depends on operational readiness. "
    "FundedNext data inadequacy (§4) is a parallel-track risk that should be "
    "addressed during Gate A — either by acquiring more history or by explicitly "
    "accepting cross-broker backtest translation risk.",
    style_callout
))

story.append(PageBreak())

# ============ SECTION 8: REALITY SCORECARD ============
story.append(Paragraph("Section 8 — Reality Scorecard", style_h1))
story.append(Paragraph(
    "Scores below are evidence-based and brutally honest. They reflect the current "
    "state of the repo as inspected on 2026-06-23, not the aspirational state "
    "described in any prior phase README. The handoff doc's overall score of 68/100 "
    "is slightly generous — this audit's overall is 45/100, with the gap concentrated "
    "in Production Quality and Operational Quality.",
    style_body
))

score_rows = [
    ["Research Quality", "75 / 100", "AMBER",
     "Strong validation breadth (19 audits). Deductions: 6 audits cite impossible frozen metrics; "
     "project_memory.md stale; alpha decay visible (AUC 0.78 → 0.73 over 2023-2026)."],
    ["Trading Quality", "55 / 100", "AMBER",
     "Rebuild Sharpe 1.66 (close to gate). Live Sharpe 1.46 (below 1.80 shadow-live gate). "
     "F8 optimization ceiling 1.58 — gap 0.22 requires retrain."],
    ["Production Quality", "25 / 100", "RED",
     "Phase F not built (titan/production/ absent). No live MT5 connector. No real-time feature "
     "pipeline. No 7-layer inference orchestrator. Kill-switch scattered. No TITAN.bat."],
    ["Operational Quality", "15 / 100", "RED",
     "No on-call. No runbook. No MRO. No Grafana. No PagerDuty. Operational readiness 45/100 "
     "(per Phase F.7). Forbids capital deployment."],
    ["Data Quality", "70 / 100", "AMBER",
     "Aggregate 98.87% coverage, 0% synthetic, 4-broker cross-validation. Deductions: FundedNext "
     "37.8% H1 / 1.01% M1 (user's broker); aggregate vs per-broker verdict contradiction."],
    ["Risk Controls (spec)", "85 / 100", "GREEN",
     "Risk engine 12 controls, 4 modes, kill-switch <500ms SLA. 11 tests pass. Spec is excellent. "
     "Implementation tested but not deployed."],
    ["Compliance", "90 / 100", "GREEN",
     "5 prop firms (FTMO, FundedNext, E8, The5ers, FundingPips). 14 rules. 69 tests pass. "
     "Production-ready."],
    ["Licensing", "88 / 100", "GREEN",
     "Hardware-locked JWT, 3 tiers, online+offline activation. 47 tests pass. Production-ready."],
    ["Test Coverage", "70 / 100", "AMBER",
     "381 tests collected (handoff says 364). 3 modules fail collection (missing deps). "
     "Coverage of risk/execution/broker blocked by MetaTrader5 (Windows-only)."],
    ["Documentation Quality", "55 / 100", "AMBER",
     "NEW_SESSION_HANDOFF.md is excellent. MASTER_PROJECT_MANIFEST.md is thorough. But "
     "project_memory.md is stale and 6 audit JSONs contain contradictory verdicts."],
    ["OVERALL", "45 / 100", "RED",
     "Demo Ready with critical caveats. NOT Live Ready. NOT Capital Ready. Path forward: "
     "build Phase F, fix environment, retrain L1, then 30-day demo."],
]
story.append(make_table(
    ["Dimension", "Score", "Status", "Justification"],
    score_rows,
    col_widths=[3.5*cm, 2.0*cm, 1.5*cm, 9.5*cm]
))

story.append(Paragraph("8.1 Scorecard vs Handoff Doc", style_h2))
story.append(Paragraph(
    "The handoff doc's scorecard (overall 68/100) is more generous than this audit "
    "(45/100). The 23-point gap is concentrated in two dimensions: Production Quality "
    "(handoff 55, this audit 25 — because the handoff credits the spec while this "
    "audit credits only runnable code) and Operational Quality (handoff 45, this "
    "audit 15 — because the handoff counts spec'd-but-unbuilt items like the "
    "runbook as partial credit). The handoff's score is a \"spec readiness\" score; "
    "this audit's score is an \"evidence-based deployment readiness\" score. Both "
    "are valid lenses; this audit's lens is more conservative.",
    style_body
))

story.append(PageBreak())

# ============ SECTION 9: CONTRADICTIONS AUDIT ============
story.append(Paragraph("Section 9 — Contradictions Audit", style_h1))
story.append(Paragraph(
    "Each contradiction below is a pair of statements from different parts of the "
    "repo that cannot both be true. The format is: <b>Claim A (source)</b> vs "
    "<b>Claim B (source)</b>, with the resolution based on direct evidence.",
    style_body
))

contra_rows = [
    ["#1", "Sharpe Ratio",
     "Walk-Forward Validation JSON: Sharpe 55.04 (Window 1), 55.05 (Window 2), 48.89 (Window 3). Verdict: PASSED.",
     "Phase F8 Results JSON: Rebuild Sharpe 1.66, Live Sharpe 1.46. Verdict: Retrain Required.",
     "F8 is correct. WFA used H1-bar annualization (252×√24 ≈ 1233× inflation). Real daily Sharpe ≈ 1.66."],
    ["#2", "Monte Carlo Survival",
     "Monte Carlo v2 JSON: Sharpe mean 37.04, PF mean 5.30, survival 100%. Verdict: PASS.",
     "Phase F8: Live Sharpe 1.46, PF 2.65. Sharpe gap 0.22 to shadow-live gate.",
     "MC v2 used frozen-model annualized returns. F8 haircut is the live-truth. MC v2 should be marked SUPERSEDED."],
    ["#3", "Red Team Score",
     "Red Team Audit JSON: Score 81.9/100, SAFE FOR DEMO. Uses baseline Sharpe 29.86.",
     "Phase F8: Live Sharpe 1.46 (below shadow-live gate 1.80).",
     "Red Team 'SAFE FOR DEMO' is correct (demo gate is lower) but its Sharpe input was frozen-annualized. Confusing."],
    ["#4", "MT5 Data Verdict",
     "Aggregate v4.0 JSON: REAL_MT5_DATA_VERIFIED_4_BROKERS. Pass conditions list Exness, FBS, IC Markets only.",
     "FundedNext per-broker audit JSON: verdict DATA_REJECTED. H1 coverage 37.8%, M1 1.01%.",
     "FundedNext is silently excluded from aggregate pass conditions. User's target broker failed. Aggregate verdict is misleading."],
    ["#5", "Phase F Code Location",
     "NEW_SESSION_HANDOFF.md: 'Phase F = Separate Module. Phase F code lives in titan/production/.'",
     "Filesystem: titan/production/ does not exist. No phase F code present.",
     "Handoff describes the planned location, not the current state. Phase F is unbuilt."],
    ["#6", "Latest Commit",
     "NEW_SESSION_HANDOFF.md: 'Latest Commit: 2f86364 (Phase F8)'",
     "git log: HEAD is da52456 (handoff doc commit, 2026-06-22 19:06).",
     "Handoff is stale by one commit (itself). Minor but should be corrected."],
    ["#7", "Test Count",
     "NEW_SESSION_HANDOFF.md (via project_memory): 364 tests, 17 test files.",
     "pytest --collect-only: 381 tests collected, 20 test files (3 with collection errors).",
     "Handoff undercounts by 17 tests. Probably written before preprocessing tests were added."],
    ["#8", "Dukascopy File Count",
     "project_memory.md: '587 daily parquet files, 584 trading days.'",
     "Filesystem: 1,302 daily parquet files in titan/data/sources/dukascopy/daily/.",
     "project_memory.md is stale. Data acquisition continued past its last update (June 20)."],
    ["#9", "FundedNext Server Name",
     "NEW_SESSION_HANDOFF.md: 'Broker: FundedNext MT5 demo (login 34265693, server FundedNext-Demo)'",
     "MT5_Verification.json: 'server': 'FundedNext-Server 3'",
     "Handoff has wrong server name. Actual is 'FundedNext-Server 3'. Critical for live connection config."],
    ["#10", "Context Engine Contribution",
     "Failure Point Report JSON: context_removal improvement_pct = -2.84% (context HURTS PF).",
     "Phase F8 Section 2: 'Context adds +0.25 Sharpe in aggregate (2024-2026). Positive uplift in ALL 4 years.'",
     "F8 is the more granular analysis (yearly A/B). Failure Point Report used frozen-model aggregate. F8 wins."],
    ["#11", "Sharpe 'Daily' Definition",
     "Reality Audit v1.0 JSON: 'Sharpe = 36.95 (>10) — SUSPICIOUS. Inflated by H1 bar-level annualization. Daily Sharpe = 2.33.'",
     "Phase F7 yearly baseline: aggregate Sharpe 1.66 (daily, rebuild).",
     "Reality Audit's 'daily Sharpe = 2.33' is the FROZEN daily. F7's 1.66 is the REBUILD daily. Both are 'daily' but different models. Confusing terminology."],
    ["#12", "Commit Count",
     "NEW_SESSION_HANDOFF.md: 'Total Commits: 25+'",
     "git rev-list --count HEAD: 48",
     "Handoff undercounts. 48 commits as of audit date."],
]
story.append(make_table(
    ["#", "Topic", "Claim A (Source)", "Claim B (Source)", "Resolution"],
    contra_rows,
    col_widths=[0.7*cm, 2.3*cm, 4.5*cm, 4.5*cm, 4.5*cm]
))

story.append(Paragraph("9.1 Section 9 Verdict", style_h2))
story.append(Paragraph(
    "<b>CONTRADICTIONS: 12 found.</b> Three are critical (#1, #2, #4 — they affect "
    "deployment decisions). Six are documentation defects (#5, #6, #7, #8, #9, #12). "
    "Three are metric-family confusion (#3, #10, #11). None are show-stoppers, but "
    "all 12 should be reconciled before any new developer onboards. The simplest "
    "fix is a single <code>SUPERSEDED.md</code> file in <code>download/</code> "
    "that lists every JSON report with a 'use this metric, not that metric' note.",
    style_callout
))

story.append(PageBreak())

# ============ SECTION 10: CEO SUMMARY ============
story.append(Paragraph("Section 10 — CEO Summary", style_h1))
story.append(Paragraph(
    "Five questions, answered brutally. No hedging.",
    style_body
))

story.append(Paragraph("Q1. What currently works?", style_h2))
story.append(Paragraph(
    "The research stack works. AI model training is complete: 9 trained artifacts "
    "(XGBoost v1+v2, LSTM v1+v2, Transformer v1, Meta-Label v1+v2, LightGBM, LogReg) "
    "are present with HPO parameters and trial databases. The backtest engine "
    "(<code>titan/backtest/engine.py</code>, 358 lines, 5 cost components) works. "
    "The walk-forward engine works (with the caveat that its JSON output uses "
    "H1-annualized Sharpe — mathematically valid but misleading). The regime engine "
    "(<code>titan/regime/engine.py</code>, 17.5 KB, 3-model vote) works. The compliance "
    "engine works (5 prop firms, 14 rules, 69 tests pass). The licensing engine works "
    "(JWT, 3 tiers, 47 tests pass). The preprocessing pipeline works (4-broker median "
    "merge, regime tagging, class balancing, 17 tests pass). 381 tests collect. The "
    "research verdict — <b>DEMO READY</b> — is supported by evidence.",
    style_body
))

story.append(Paragraph("Q2. What is unproven?", style_h2))
story.append(Paragraph(
    "<b>Live Sharpe 1.46 is unproven.</b> It is a haircut-adjusted simulation, not a "
    "measured live result. The 0.34 gap to the 1.80 shadow-live gate is bridged by "
    "an estimated +0.15 from execution co-location (unverified — no VPS deployed) "
    "and an estimated +0.15-0.25 from L1 XGBoost retrain (unverified — no retrain "
    "performed). The 7-layer inference chain is unproven — it is specified in "
    "Phase F-Prime but has never executed end-to-end. The kill-switch FSM is "
    "unproven — its logic is scattered across 4 files and has never been stress-tested "
    "in a live scenario. The watchdog auto-restart is unproven — the module exists "
    "but has no deployment wrapper. Position sync on startup is unproven — the spec "
    "exists but the implementation does not. FundedNext live connectivity is "
    "unproven — the broker was verified at the API level (login, server, symbol) "
    "but no live order has ever been sent.",
    style_body
))

story.append(Paragraph("Q3. What is broken?", style_h2))
story.append(Paragraph(
    "<b>Three test modules are broken</b> (test_database, test_infrastructure, "
    "test_recovery) due to missing Python packages (aiosqlite, structlog). "
    "<b>Three production modules cannot import on Linux</b> (risk.engine, "
    "execution.engine, broker.engine) due to MetaTrader5 being Windows-only — "
    "this is by design but blocks Linux-based development. <b>FundedNext MT5 data "
    "is broken</b> for backtesting purposes — H1 coverage 37.8%, M1 coverage 1.01%, "
    "per-broker audit verdict DATA_REJECTED. <b>Six audit JSONs are broken as "
    "documentation</b> — they cite Sharpe 29-55+ as PASS despite Phase F8 "
    "explicitly rejecting those metrics. <b>project_memory.md is broken</b> — "
    "claims 587 Dukascopy files, actual is 1,302. <b>The handoff doc is broken "
    "in three places</b> — wrong commit hash, wrong test count, wrong FundedNext "
    "server name.",
    style_body
))

story.append(Paragraph("Q4. What is missing?", style_h2))
story.append(Paragraph(
    "<b>Phase F is missing.</b> The entire live execution engine — MT5 connector, "
    "real-time feature pipeline, 7-layer inference orchestrator, kill-switch FSM, "
    "watchdog wrapper, position sync, TITAN.bat — does not exist as runnable code. "
    "The <code>titan/production/</code> directory mentioned in the handoff is absent. "
    "<b>Operational readiness is missing</b> — no on-call, no runbook, no MRO, no "
    "Grafana dashboard, no PagerDuty. <b>News-event pre-halt is missing</b> — Phase "
    "F.5 showed 0% survival on market-event scenarios. <b>A model registry is "
    "missing</b> — 9 model files exist but no manifest records training metadata. "
    "<b>A SUPERSEDED marker is missing</b> on the six frozen-metric audit JSONs. "
    "<b>FundedNext historical data is missing</b> — only 37.8% H1 coverage. "
    "<b>L1 XGBoost retrain with 2025-2026 data is missing</b> — F8 says this is "
    "required to close the Sharpe gap. <b>A reconciliation of the aggregate vs "
    "per-broker MT5 verdict is missing</b>.",
    style_body
))

story.append(Paragraph("Q5. If you inherited TITAN today, what would be your next step?", style_h2))
story.append(Paragraph(
    "<b>Stop adding new audits.</b> The project has 19 distinct validation reports "
    "and 5 phase summaries. Another audit will not move TITAN closer to live trading. "
    "The next 40 days should be spent building Phase F, not documenting why Phase F "
    "is needed.",
    style_body
))
story.append(Paragraph(
    "<b>Step 1 (Day 1): Fix the environment.</b> Install all 9 missing Python "
    "packages on a Windows machine with MT5 installed. Verify all 381 tests collect "
    "and pass. Verify the 3 currently-broken test modules import cleanly. This is "
    "the cheapest insurance and the prerequisite for everything else.",
    style_body
))
story.append(Paragraph(
    "<b>Step 2 (Day 2-3): Reconcile the contradictions.</b> Add a "
    "<code>SUPERSEDED.md</code> to <code>download/</code> listing the 6 frozen-metric "
    "JSONs with explicit 'use rebuild metrics, not these' notes. Fix the aggregate "
    "v4.0 MT5 audit to either (a) require all 4 brokers pass, or (b) explicitly "
    "mark FundedNext as 'cross-broker translation risk accepted'. Update "
    "project_memory.md and the handoff doc with current file counts and commit hash.",
    style_body
))
story.append(Paragraph(
    "<b>Step 3 (Day 4-5): Decide FundedNext data strategy.</b> Either (a) run the "
    "Windows MT5 acquisition script monthly to build up FundedNext history over "
    "time, accepting that the first 30-day demo will use cross-broker backtest "
    "translation, or (b) delay demo launch until FundedNext has 95% H1 coverage "
    "(estimated 6-9 months of accumulation). Option (a) is recommended — the demo "
    "is the cheapest way to discover real execution issues that no backtest can "
    "predict.",
    style_body
))
story.append(Paragraph(
    "<b>Step 4 (Day 6-40): Build Phase F.</b> Create <code>titan/production/</code> "
    "with the 9 components listed in §7.1. Use the existing frozen v1 models — do "
    "NOT retrain during Phase F (retrain is a parallel track per F8). Wire the "
    "kill-switch FSM as a dedicated module, not scattered logic. Build TITAN.bat "
    "last, after the inference chain is verified end-to-end on the dev machine.",
    style_body
))
story.append(Paragraph(
    "<b>Step 5 (Day 41+): 30-day demo on FundedNext.</b> Run unattended on the demo "
    "account. Monitor for kill-switch triggers, position sync failures, drift "
    "thresholds. In parallel, retrain L1 XGBoost with 2025-2026 walk-forward data. "
    "After 30 days + retrain, re-evaluate the shadow-live gate.",
    style_body
))

story.append(Spacer(1, 0.6*cm))
story.append(HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceAfter=10))

# Final verdict band
final_para = Paragraph(
    '<font color="white"><b>FINAL AUDIT VERDICT</b><br/><br/>'
    'TITAN XAU AI is a research-complete, production-incomplete trading system. '
    'The research stack (models, validation, compliance, licensing) is solid. '
    'The production stack (live execution, kill-switch FSM, watchdog, operational '
    'readiness) does not exist. The user\'s target broker (FundedNext) has '
    'insufficient historical data. Six prior audit reports cite mathematically '
    'impossible frozen-model metrics without a SUPERSEDED marker.<br/><br/>'
    '<b>Path forward: Build Phase F. Do not add new audits. Do not retrain during '
    'Phase F. Run 30-day demo on FundedNext. Retrain L1 in parallel. Re-evaluate '
    'shadow-live gate after demo + retrain.</b></font>',
    ParagraphStyle("Final", fontName="BodySerif", fontSize=10, leading=14,
                   textColor=colors.white, alignment=TA_LEFT)
)
final_tbl = Table([[final_para]], colWidths=[CONTENT_W])
final_tbl.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), NAVY),
    ("LEFTPADDING", (0, 0), (-1, -1), 14),
    ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ("TOPPADDING", (0, 0), (-1, -1), 14),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ("BOX", (0, 0), (-1, -1), 1.5, GOLD),
]))
story.append(final_tbl)


# === BUILD ===
def build():
    out_path = "/home/z/my-project/download/TITAN_Project_State_Audit_v1.0.pdf"
    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=MARGIN_L, rightMargin=MARGIN_R,
        topMargin=MARGIN_T, bottomMargin=MARGIN_B,
        title="TITAN XAU AI — Project State Audit v1.0",
        author="Z.ai Engineering",
        subject="Fresh-session evidence-based audit of TITAN XAU AI repository",
        creator="Z.ai (Super Z) — ReportLab",
    )
    # Use cover frame for page 1, regular frame for subsequent pages
    doc.build(story, onFirstPage=draw_cover_frame, onLaterPages=draw_page_frame)
    sz = os.path.getsize(out_path)
    print(f"✓ Audit PDF generated: {out_path}")
    print(f"  Size: {sz/1024:.1f} KB")


if __name__ == "__main__":
    build()
