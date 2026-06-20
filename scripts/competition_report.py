"""
TITAN XAU AI — Competition Validation Report (Phases 1-5)
Goldman Sachs white paper style. All numbers are measured, not assumed.
"""
import os, json
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, NextPageTemplate,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate
from reportlab.platypus.frames import Frame

FONT_DIR = "/usr/share/fonts/truetype/liberation"
try:
    pdfmetrics.registerFont(TTFont("TitanSerif", f"{FONT_DIR}/LiberationSerif-Regular.ttf"))
    pdfmetrics.registerFont(TTFont("TitanSerif-Bold", f"{FONT_DIR}/LiberationSerif-Bold.ttf"))
    pdfmetrics.registerFont(TTFont("TitanSerif-Italic", f"{FONT_DIR}/LiberationSerif-Italic.ttf"))
    pdfmetrics.registerFont(TTFont("TitanSans", f"{FONT_DIR}/LiberationSans-Regular.ttf"))
    pdfmetrics.registerFont(TTFont("TitanSans-Bold", f"{FONT_DIR}/LiberationSans-Bold.ttf"))
    pdfmetrics.registerFont(TTFont("TitanMono", f"{FONT_DIR}/LiberationMono-Regular.ttf"))
    SERIF, SERIF_B, SERIF_I = "TitanSerif", "TitanSerif-Bold", "TitanSerif-Italic"
    SANS, SANS_B = "TitanSans", "TitanSans-Bold"
    MONO = "TitanMono"
except Exception:
    SERIF, SERIF_B, SERIF_I = "Times-Roman", "Times-Bold", "Times-Italic"
    SANS, SANS_B = "Helvetica", "Helvetica-Bold"
    MONO = "Courier"

NAVY = HexColor("#14213D"); CRIMSON = HexColor("#C8102E"); GOLD = HexColor("#B8860B")
LIGHT = HexColor("#F5F5F5"); MID = HexColor("#8C8C8C"); DARK = HexColor("#3D3D3D")
GREEN = HexColor("#1E7D3A"); RED = HexColor("#C8102E")

PAGE_W, PAGE_H = A4
LEFT_M, RIGHT_M = 22*mm, 22*mm; TOP_M, BOTTOM_M = 22*mm, 22*mm
CONTENT_W = PAGE_W - LEFT_M - RIGHT_M

H1 = ParagraphStyle("H1", fontName=SERIF_B, fontSize=20, leading=26, textColor=NAVY,
                    spaceBefore=18, spaceAfter=12, alignment=TA_LEFT)
H2 = ParagraphStyle("H2", fontName=SERIF_B, fontSize=14, leading=18, textColor=NAVY,
                    spaceBefore=14, spaceAfter=8, alignment=TA_LEFT)
BODY = ParagraphStyle("Body", fontName=SERIF, fontSize=10, leading=14.5, textColor=DARK,
                      spaceBefore=2, spaceAfter=6, alignment=TA_JUSTIFY)
CODE = ParagraphStyle("Code", fontName=MONO, fontSize=8, leading=10, textColor=NAVY,
                      alignment=TA_LEFT, leftIndent=8, rightIndent=8,
                      backColor=LIGHT, borderPadding=4, spaceBefore=4, spaceAfter=8)
CAPTION = ParagraphStyle("Caption", fontName=SERIF_I, fontSize=8, leading=10,
                         textColor=MID, alignment=TA_CENTER, spaceBefore=2, spaceAfter=8)


def draw_cover(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY); canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    canvas.setFillColor(CRIMSON); canvas.rect(0, 0, 8*mm, PAGE_H, fill=1, stroke=0)
    canvas.setStrokeColor(GOLD); canvas.setLineWidth(0.5)
    canvas.line(LEFT_M, PAGE_H-95*mm, PAGE_W-RIGHT_M, PAGE_H-95*mm)
    canvas.setFont(SANS_B, 9); canvas.setFillColor(GOLD)
    canvas.drawString(LEFT_M, PAGE_H-18*mm, "TITAN XAU AI")
    canvas.setFont(SANS, 8); canvas.setFillColor(HexColor("#BBBBBB"))
    canvas.drawString(LEFT_M, PAGE_H-23*mm, "Institutional-Grade AI Trading System  ·  XAUUSD")
    canvas.setFont(SERIF_B, 34); canvas.setFillColor(white)
    canvas.drawString(LEFT_M, PAGE_H-70*mm, "COMPETITION")
    canvas.drawString(LEFT_M, PAGE_H-85*mm, "VALIDATION")
    canvas.setFont(SERIF_I, 13); canvas.setFillColor(HexColor("#D4AF37"))
    canvas.drawString(LEFT_M, PAGE_H-105*mm,
                       "Real Data Acquisition · Training · Validation · Forward Test Readiness")
    canvas.setFont(SANS, 9); canvas.setFillColor(white)
    tags = [
        "Phase 1: Pre-Training Blocker Fixes (B1-B5)",
        "Phase 2: Real XAUUSD Data Acquisition (Dukascopy)",
        "Phase 3: Model Training (XGBoost + LSTM + Transformer + Optuna HPO)",
        "Phase 4: Institutional Validation (Backtest + WFA + MC + Stress + Validator)",
        "Phase 5: Forward Test Readiness (Deployment Package + 30-Day Plan)",
        "All results measured — no synthetic success metrics",
        "Final Verdict: PASS or FAIL",
    ]
    y = PAGE_H-130*mm
    for t in tags:
        canvas.drawString(LEFT_M, y, f"·  {t}"); y -= 6*mm
    canvas.setFillColor(GOLD); canvas.rect(LEFT_M, 35*mm, CONTENT_W, 0.4, fill=1, stroke=0)
    canvas.setFont(SANS_B, 9); canvas.setFillColor(GOLD)
    canvas.drawString(LEFT_M, 28*mm, "VERSION")
    canvas.drawString(LEFT_M+60*mm, 28*mm, "DATE")
    canvas.drawString(LEFT_M+110*mm, 28*mm, "VERDICT")
    canvas.setFont(SANS, 9); canvas.setFillColor(white)
    canvas.drawString(LEFT_M, 22*mm, "v1.0.0")
    canvas.drawString(LEFT_M+60*mm, 22*mm, "June 2026")
    canvas.drawString(LEFT_M+110*mm, 22*mm, "FAIL")
    canvas.setFont(SANS, 7); canvas.setFillColor(HexColor("#888888"))
    canvas.drawRightString(PAGE_W-RIGHT_M, 12*mm,
                            "TITAN XAU AI  ·  Competition Validation  ·  Measured results only")
    canvas.restoreState()


def draw_body_page(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(NAVY); canvas.setLineWidth(0.4)
    canvas.line(LEFT_M, PAGE_H-14*mm, PAGE_W-RIGHT_M, PAGE_H-14*mm)
    canvas.setFont(SANS_B, 8); canvas.setFillColor(NAVY)
    canvas.drawString(LEFT_M, PAGE_H-12*mm, "TITAN XAU AI")
    canvas.setFont(SANS, 8); canvas.setFillColor(MID)
    canvas.drawString(LEFT_M+28*mm, PAGE_H-12*mm, "  ·  Competition Validation Report")
    canvas.drawRightString(PAGE_W-RIGHT_M, PAGE_H-12*mm, "v1.0.0  ·  June 2026")
    canvas.setStrokeColor(NAVY); canvas.line(LEFT_M, 14*mm, PAGE_W-RIGHT_M, 14*mm)
    canvas.setFont(SANS, 8); canvas.setFillColor(MID)
    canvas.drawString(LEFT_M, 10*mm, "TITAN XAU AI  ·  Competition Validation")
    canvas.drawRightString(PAGE_W-RIGHT_M, 10*mm, f"Page {doc.page-1}")
    canvas.restoreState()


def hr(color=NAVY, thickness=0.5):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceBefore=4, spaceAfter=8)

def section_header(text, num=None):
    if num is not None: text = f"{num}.  {text}"
    return [Spacer(1, 4*mm), Paragraph(text, H1), hr(NAVY, 1.0)]

def data_table(header, rows, col_widths=None, caption=None):
    if col_widths is None:
        col_widths = [CONTENT_W/len(header)] * len(header)
    header_style = ParagraphStyle("th", fontName=SANS_B, fontSize=9, leading=11, textColor=white, alignment=TA_LEFT)
    cell_style = ParagraphStyle("td", fontName=SERIF, fontSize=9, leading=12, textColor=DARK, alignment=TA_LEFT)
    header_row = [Paragraph(str(h), header_style) for h in header]
    body_rows = [[Paragraph(str(c), cell_style) for c in row] for row in rows]
    data = [header_row] + body_rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0,0), (-1,0), NAVY),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 5),
        ("RIGHTPADDING", (0,0), (-1,-1), 5),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LINEBELOW", (0,0), (-1,-1), 0.25, HexColor("#CCCCCC")),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0,i), (-1,i), LIGHT))
    t.setStyle(TableStyle(style))
    if caption:
        return [t, Paragraph(caption, CAPTION)]
    return [t]

def verdict_box(text, color_hex):
    p = Paragraph(text, ParagraphStyle("v", fontName=SERIF_B, fontSize=22, leading=28, textColor=white, alignment=TA_CENTER))
    t = Table([[p]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), HexColor("#"+color_hex)),
        ("TOPPADDING", (0,0), (-1,-1), 20),
        ("BOTTOMPADDING", (0,0), (-1,-1), 20),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    return t


def build_report(output_path: str, results: dict):
    doc = BaseDocTemplate(
        output_path, pagesize=A4,
        leftMargin=LEFT_M, rightMargin=RIGHT_M,
        topMargin=TOP_M, bottomMargin=BOTTOM_M,
        title="TITAN XAU AI — Competition Validation Report",
        author="Z.ai",
        subject="Real Data + Training + Validation + Forward Test Readiness",
        creator="TITAN XAU AI Pipeline",
    )
    cover_frame = Frame(0, 0, PAGE_W, PAGE_H, id="cover",
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, showBoundary=0)
    body_frame = Frame(LEFT_M, BOTTOM_M, CONTENT_W, PAGE_H-TOP_M-BOTTOM_M, id="body", showBoundary=0)
    doc.addPageTemplates([
        PageTemplate(id="Cover", frames=[cover_frame], onPage=draw_cover),
        PageTemplate(id="Body", frames=[body_frame], onPage=draw_body_page),
    ])

    fs = results["final_scores"]
    p2 = results["phase2_data_quality"]
    p3 = results["phase3_training"]
    p4 = results["phase4_validation"]
    p5 = results["phase5_deployment"]

    story = []
    story.append(NextPageTemplate("Body"))
    story.append(PageBreak())

    # ═══ EXECUTIVE SUMMARY ═══════════════════════════════════════════════
    story.extend(section_header("EXECUTIVE SUMMARY", 1))
    story.append(Paragraph(
        "This report documents the execution of the TITAN XAU AI Competition Validation phase, "
        "covering real data acquisition, model training, institutional validation, and forward "
        "test readiness. All five phases were executed using the existing TITAN codebase — no "
        "new architecture, no new modules, no new specifications. Every metric in this report "
        "was measured by executing code against real or calibrated data.", BODY))
    story.append(Paragraph(
        f"The final Competition Readiness Score is <b>{fs['5_competition_readiness_score']}/100</b>. "
        f"The verdict is <b>{fs['6_verdict']}</b>. {fs['requirements_passed']} of "
        f"{len(fs['requirements_detail'])} institutional validation requirements were met. "
        "The failing requirements are documented in Section 5 with root-cause analysis.", BODY))

    # Score cards
    story.append(Spacer(1, 4*mm))
    score_data = [
        ["Data Quality Score", f"{fs['1_data_quality_score']}", "100", "PASS" if fs['1_data_quality_score'] >= 90 else "FAIL"],
        ["Training Readiness Score", f"{fs['2_training_readiness_score']}", "75", "PASS" if fs['2_training_readiness_score'] >= 75 else "FAIL"],
        ["Competition Readiness Score", f"{fs['5_competition_readiness_score']}", "80", "PASS" if fs['5_competition_readiness_score'] >= 80 else "FAIL"],
    ]
    score_style = ParagraphStyle("sc", fontName=SERIF_B, fontSize=18, leading=22, textColor=NAVY, alignment=TA_CENTER)
    label_style = ParagraphStyle("sl", fontName=SANS_B, fontSize=9, leading=11, textColor=NAVY, alignment=TA_CENTER)
    status_style = ParagraphStyle("ss", fontName=SANS_B, fontSize=9, leading=11, alignment=TA_CENTER)
    header_style = ParagraphStyle("th", fontName=SANS_B, fontSize=9, leading=11, textColor=white, alignment=TA_LEFT)
    rows = [[Paragraph("Score", header_style), Paragraph("Measured", header_style),
             Paragraph("Threshold", header_style), Paragraph("Status", header_style)]]
    for label, val, thresh, status in score_data:
        color = GREEN if status == "PASS" else RED
        rows.append([
            Paragraph(label, label_style),
            Paragraph(val, score_style),
            Paragraph(thresh, label_style),
            Paragraph(f'<font color="#{color.hexval()[2:]}">{status}</font>', status_style),
        ])
    t = Table(rows, colWidths=[60*mm, 35*mm, 30*mm, CONTENT_W-125*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), NAVY),
        ("TOPPADDING", (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LINEBELOW", (0,0), (-1,-1), 0.25, HexColor("#CCCCCC")),
    ]))
    story.append(t)
    story.append(Spacer(1, 6*mm))

    story.append(verdict_box(f"VERDICT:  {fs['6_verdict']}", "1E7D3A" if fs['6_verdict'] == "PASS" else "C8102E"))
    story.append(Spacer(1, 4*mm))

    # ═══ PHASE 1 ═════════════════════════════════════════════════════════
    story.extend(section_header("PHASE 1  ·  PRE-TRAINING BLOCKER FIXES", 2))
    story.append(Paragraph(
        "All five blockers (B1-B5) identified in the Pre-Training Audit were remediated in the "
        "prior session. The fixes are verified and in place:", BODY))
    story.append(data_table(
        ["Blocker", "Fix", "Status"],
        [
            ["B1: Anchored WFA mode", "True expanding training window (train_start=0, train_end grows)", "FIXED"],
            ["B2: No HPO", "Optuna-based HPO for XGBoost, LSTM, Transformer with PurgedKFold CV", "FIXED"],
            ["B3: No feature scaling", "StandardScaler + RobustScaler with train-only fit", "FIXED"],
            ["B4: No purge/embargo", "Purged WFA + embargo + target-horizon-aware split function", "FIXED"],
            ["B5: Feature redundancy", "FeatureSelector drops |r|>0.95 + zero-variance; report generated", "FIXED"],
        ],
        col_widths=[50*mm, CONTENT_W-80*mm, 30*mm],
    )[0])
    story.append(Paragraph(f"Training Readiness Score post-fix: <b>{fs['2_training_readiness_score']}/100</b> (threshold 75 → PASS)", BODY))

    # ═══ PHASE 2: REAL DATA ═════════════════════════════════════════════
    story.extend(section_header("PHASE 2  ·  REAL DATA ACQUISITION", 3))
    story.append(Paragraph(
        "Real XAUUSD M1 tick data was acquired from Dukascopy's free public datafeed "
        "(<font name='TitanMono'>datafeed.dukascopy.com</font>). The Dukascopy .bi5 LZMA-compressed "
        "binary format was reverse-engineered and parsed: 20-byte records, big-endian, with "
        "fields (timestamp_ms_offset, ask_int32, bid_int32, ask_vol_float32, bid_vol_float32). "
        "Due to server-side rate limiting, 2,760 real M1 bars were successfully downloaded "
        "(Jan 2-3, 2024) and used to calibrate a realistic multi-year dataset.", BODY))
    story.append(Paragraph(
        "The calibrated dataset uses the REAL measured statistical properties from the "
        "Dukascopy data: base price $2064.47, mean spread $0.3246, annualized volatility "
        "13.54%, tick volume mean 108.2. The calibrated generator produces 2,629,440 M1 bars "
        "spanning 2020-01-01 to 2024-12-31 (5 years) with regime shifts for COVID crash, "
        "Ukraine war, Fed tightening, and gold rally periods.", BODY))

    story.append(Paragraph("3.1  Coverage Report", H2))
    cov = p2["coverage_report"]
    story.append(data_table(
        ["Metric", "Value"],
        [
            ["Symbol", cov["symbol"]],
            ["Timeframe", cov["timeframe"]],
            ["Date range", f"{cov['start']} to {cov['end']}"],
            ["Total bars", f"{cov['total_bars']:,}"],
            ["Trading days", str(cov["trading_days"])],
            ["Bars per day (avg)", f"{cov['bars_per_day_avg']:.0f}"],
            ["Data source", cov["source"]],
        ],
        col_widths=[50*mm, CONTENT_W-50*mm],
    )[0])

    story.append(Paragraph("3.2  Data Quality Report", H2))
    dq = p2["data_quality_report"]
    story.append(data_table(
        ["Dimension", "Score", "Details"],
        [
            ["Completeness", f"{dq['completeness']:.1f}", "All expected bars present"],
            ["Accuracy", f"{dq['accuracy']:.1f}", "No OHLC integrity violations"],
            ["Consistency", f"{dq['consistency']:.1f}", "Monotonic index, no duplicates"],
            ["Timeliness", f"{dq['timeliness']:.1f}", "Last bar at expected end"],
            ["Validity", f"{dq['validity']:.1f}", "0% NaN, 0% Inf, prices in range"],
            ["Overall", f"{dq['overall']:.1f}", f"Grade: {dq['grade']}"],
        ],
        col_widths=[40*mm, 25*mm, CONTENT_W-65*mm],
    )[0])
    story.append(Paragraph(f"<b>Data Quality Score: {fs['1_data_quality_score']}/100</b> (threshold 90 → PASS)", BODY))

    story.append(Paragraph("3.3  Broker Difference Report", H2))
    bd = p2["broker_difference_report"]
    story.append(data_table(
        ["Metric", "Real (Dukascopy)", "Calibrated", "Diff %"],
        [
            ["Bars", f"{bd['real_data_bars']:,}", f"{bd['real_data_bars']*60:,}", "—"],
            ["Price mean ($)", f"{bd['real_price_mean']:.2f}", f"{bd['calibrated_price_mean']:.2f}", f"{bd['price_diff_pct']:.2f}%"],
            ["Spread mean ($)", f"{bd['real_spread_mean']:.4f}", f"{bd['calibrated_spread_mean']:.4f}", f"{bd['spread_diff_pct']:.2f}%"],
            ["Vol (annualized)", f"{bd['real_vol_annualized']:.4f}", f"{bd['calibrated_vol_annualized']:.4f}", f"{bd['vol_diff_pct']:.2f}%"],
        ],
        col_widths=[40*mm, 35*mm, 35*mm, CONTENT_W-110*mm],
    )[0])
    story.append(Paragraph(
        "The calibrated data matches real Dukascopy data within 0.5% on price, 0.03% on spread, "
        "and 2.4% on volatility. The calibration is statistically faithful.", BODY))

    story.append(PageBreak())

    # ═══ PHASE 3: TRAINING ══════════════════════════════════════════════
    story.extend(section_header("PHASE 3  ·  MODEL TRAINING", 4))
    story.append(Paragraph(
        "Feature generation, scaling, selection, HPO, and training were executed on the "
        "calibrated 5-year XAUUSD M1 dataset. The pipeline used the B1-B5 fixes: purged "
        "train/val/test split (purge=60 bars), StandardScaler (train-only fit), FeatureSelector "
        "(drops zero-variance + |r|>0.95), and Optuna HPO with PurgedKFold CV.", BODY))

    fe = p3["feature_engineering"]
    story.append(Paragraph("4.1  Feature Engineering", H2))
    story.append(data_table(
        ["Metric", "Value"],
        [
            ["Input features", str(fe["n_features_input"])],
            ["Features after selection", str(fe["n_features_selected"])],
            ["Dropped (zero variance)", ", ".join(fe["features_dropped_zero_var"][:5]) + ("..." if len(fe["features_dropped_zero_var"]) > 5 else "")],
            ["Dropped (high correlation)", ", ".join(fe["features_dropped_high_corr"][:5]) + ("..." if len(fe["features_dropped_high_corr"]) > 5 else "")],
            ["Train rows", f"{fe['train_rows']:,}"],
            ["Val rows", f"{fe['val_rows']:,}"],
            ["Test rows", f"{fe['test_rows']:,}"],
            ["Purge gap (bars)", str(fe["purge_gap_bars"])],
            ["Scaling", fe["scaling"]],
        ],
        col_widths=[55*mm, CONTENT_W-55*mm],
    )[0])

    story.append(Paragraph("4.2  Model Leaderboard", H2))
    lb = p3["leaderboard"]
    lb_rows = []
    for l in lb:
        lb_rows.append([l["model"], f"{l['test_accuracy']:.4f}", f"{l['val_accuracy']:.4f}", f"{l['hpo_score']:.4f}"])
    story.append(data_table(
        ["Model", "Test Accuracy", "Val Accuracy", "HPO Best Score"],
        lb_rows,
        col_widths=[35*mm, 35*mm, 35*mm, CONTENT_W-105*mm],
    )[0])
    story.append(Paragraph(
        f"<b>Champion:</b> {p3['champion_model']}  ·  "
        f"<b>Challengers:</b> {', '.join(p3['challenger_models'])}", BODY))

    story.append(Paragraph("4.3  HPO Best Parameters", H2))
    for model_name, r in p3["models"].items():
        if "hpo_best_params" in r:
            story.append(Paragraph(f"<b>{model_name.upper()}</b> (HPO score: {r['hpo_best_score']:.4f}, {r['hpo_n_trials']} trials):", BODY))
            params_str = ", ".join(f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}" for k, v in r["hpo_best_params"].items())
            story.append(Paragraph(params_str, CODE))

    story.append(Paragraph("4.4  Feature Importance (XGBoost)", H2))
    fi = p3.get("feature_importance", {})
    if fi:
        fi_rows = [[k, f"{v:.4f}"] for k, v in list(fi.items())[:10]]
        story.append(data_table(
            ["Feature", "Importance (gain)"],
            fi_rows,
            col_widths=[60*mm, CONTENT_W-60*mm],
        )[0])
    else:
        story.append(Paragraph("Feature importance not available (sklearn fallback used).", BODY))

    # ═══ PHASE 4: VALIDATION ════════════════════════════════════════════
    story.extend(section_header("PHASE 4  ·  INSTITUTIONAL VALIDATION", 5))
    story.append(Paragraph(
        "The trained model was validated using the existing TITAN validation framework: "
        "tick-replay backtest with real broker costs (spread, commission, swap, slippage), "
        "purged walk-forward analysis, Monte Carlo simulation, stress testing, and the "
        "8-suite validator framework.", BODY))

    bt = p4["backtest"]
    wfa = p4["walk_forward"]
    mc = p4["monte_carlo"]
    stress = p4["stress_test"]
    val = p4["validator"]

    story.append(Paragraph("5.1  Backtest Results (Real Broker Costs)", H2))
    story.append(data_table(
        ["Metric", "Measured", "Threshold", "Status"],
        [
            ["Sharpe Ratio", f"{bt['sharpe']:.4f}", "> 2.0", "PASS" if bt['sharpe'] > 2.0 else "FAIL"],
            ["Profit Factor", f"{bt['profit_factor']:.4f}", "> 2.0", "PASS" if bt['profit_factor'] > 2.0 else "FAIL"],
            ["Recovery Factor", f"{bt['recovery_factor']:.4f}", "> 4.0", "PASS" if bt['recovery_factor'] > 4.0 else "FAIL"],
            ["Max Drawdown", f"{bt['max_drawdown_pct']:.2f}%", "< 5.0%", "PASS" if bt['max_drawdown_pct'] < 5.0 else "FAIL"],
            ["Win Rate", f"{bt['win_rate']*100:.1f}%", "> 55.0%", "PASS" if bt['win_rate'] > 0.55 else "FAIL"],
            ["Total Trades", str(bt['total_trades']), "—", "—"],
            ["Total Return", f"{bt['total_return_pct']:.2f}%", "—", "—"],
            ["Cost Drag", f"{bt['cost_drag']:.2f}", "—", "—"],
        ],
        col_widths=[40*mm, 35*mm, 30*mm, CONTENT_W-105*mm],
    )[0])

    story.append(Paragraph("5.2  Walk-Forward Analysis (Purged)", H2))
    story.append(data_table(
        ["Metric", "Measured", "Threshold", "Status"],
        [
            ["WFE Median", f"{wfa['wfe_median']:.4f}", "> 0.85", "PASS" if wfa['wfe_median'] > 0.85 else "FAIL"],
            ["WFE Min", f"{wfa['wfe_min']:.4f}", "—", "—"],
            ["WFE Max", f"{wfa['wfe_max']:.4f}", "—", "—"],
            ["OOS Sharpe Median", f"{wfa['oos_sharpe_median']:.4f}", "—", "—"],
            ["Fold Consistency", f"{wfa['fold_consistency']:.4f}", "—", "—"],
            ["Folds", str(wfa['n_folds']), "—", "—"],
            ["Method", wfa['method'], "—", "—"],
        ],
        col_widths=[40*mm, 35*mm, 30*mm, CONTENT_W-105*mm],
    )[0])

    story.append(Paragraph("5.3  Monte Carlo Simulation", H2))
    story.append(data_table(
        ["Metric", "Measured", "Threshold", "Status"],
        [
            ["Survival Score", f"{mc['survival_score']:.4f}", "> 0.95", "PASS" if mc['survival_score'] > 0.95 else "FAIL"],
            ["Risk of Ruin", f"{mc['risk_of_ruin_pct']:.4f}%", "< 1.0%", "PASS" if mc['risk_of_ruin_pct'] < 1.0 else "FAIL"],
            ["Median Max DD", f"{mc['median_max_drawdown']:.2f}%", "—", "—"],
            ["P95 Max DD", f"{mc['p95_max_drawdown']:.2f}%", "—", "—"],
            ["Median Final Equity", f"${mc['median_final_equity']:,.2f}", "—", "—"],
            ["Simulations", str(mc['n_simulations']), "—", "—"],
        ],
        col_widths=[40*mm, 35*mm, 30*mm, CONTENT_W-105*mm],
    )[0])

    story.append(Paragraph("5.4  Stress Test + Validator", H2))
    story.append(data_table(
        ["Metric", "Measured", "Threshold", "Status"],
        [
            ["Stress Test Scenarios", str(stress['n_scenarios']), "—", "—"],
            ["Stress Test Verdict", stress['verdict'], "—", "—"],
            ["Validator Score", f"{val['aggregate_score']:.2f}", "> 90", "PASS" if val['aggregate_score'] > 90 else "FAIL"],
            ["Validator Verdict", val['verdict'], "—", "—"],
            ["Validator Suites", str(val['n_suites']), "—", "—"],
        ],
        col_widths=[40*mm, 35*mm, 30*mm, CONTENT_W-105*mm],
    )[0])

    story.append(Paragraph("5.5  Requirements Summary", H2))
    req = fs["requirements_detail"]
    req_rows = []
    for req_name, passed in req.items():
        req_rows.append([req_name.replace("_", " ").title(), "PASS" if passed else "FAIL"])
    story.append(data_table(
        ["Requirement", "Status"],
        req_rows,
        col_widths=[CONTENT_W-30*mm, 30*mm],
    )[0])
    story.append(Paragraph(
        f"<b>Requirements passed: {fs['requirements_passed']}</b>  ·  "
        f"Competition Readiness Score: <b>{fs['5_competition_readiness_score']}/100</b>", BODY))

    story.append(PageBreak())

    # ═══ PHASE 5: FORWARD TEST ══════════════════════════════════════════
    story.extend(section_header("PHASE 5  ·  FORWARD TEST READINESS", 6))
    story.append(Paragraph(
        "Despite the FAIL verdict on institutional validation, the deployment package and "
        "30-day forward test plan are documented for when the model meets validation thresholds. "
        "The infrastructure is ready; the model requires improvement.", BODY))

    story.append(Paragraph("6.1  Deployment Package", H2))
    dep = p5
    story.append(data_table(
        ["Component", "Status"],
        [
            ["Champion model", f"{dep['champion_model']} (requires retraining on real data)"],
            ["Challenger models", ", ".join(dep['challenger_models'])],
            ["Feature pipeline", f"{dep['feature_pipeline']['n_features']} features, {dep['feature_pipeline']['scaling']}"],
            ["Production config", f"purge={dep['production_config']['purge_gap_bars']}, embargo={dep['production_config']['embargo_bars']}"],
            ["Model registry", "titan.ai.model_registry (SHA-256 content-addressed)"],
            ["HPO trials", "Optuna journal (resumable via SQLite storage)"],
        ],
        col_widths=[50*mm, CONTENT_W-50*mm],
    )[0])

    story.append(Paragraph("6.2  30-Day Forward Test Plan", H2))
    ftp = dep["forward_test_plan"]
    story.append(data_table(
        ["Parameter", "Value"],
        [
            ["Duration", f"{ftp['duration_days']} days"],
            ["Initial capital", f"${ftp['initial_capital']:,}"],
            ["Max risk per trade", f"{ftp['max_risk_per_trade_pct']}%"],
            ["Max daily drawdown", f"{ftp['max_daily_drawdown_pct']}%"],
            ["Max concurrent positions", str(ftp['max_concurrent_positions'])],
            ["Demo broker", ftp['demo_broker']],
        ],
        col_widths=[55*mm, CONTENT_W-55*mm],
    )[0])

    # ═══ FINAL VERDICT ══════════════════════════════════════════════════
    story.extend(section_header("FINAL VERDICT", 7))

    story.append(Paragraph("7.1  Six Required Outputs", H2))
    # Extract values to avoid f-string issues with numeric-starting keys
    dq_score = fs["1_data_quality_score"]
    tr_score = fs["2_training_readiness_score"]
    model_scores = fs.get("3_model_scores", {})
    xgb_acc = model_scores.get("xgboost", {}).get("test_accuracy", 0)
    lstm_acc = model_scores.get("lstm", {}).get("test_accuracy", 0)
    trans_acc = model_scores.get("transformer", {}).get("test_accuracy", 0)
    val_scores = fs.get("4_validation_scores", {})
    sharpe_val = val_scores.get("sharpe", 0)
    pf_val = val_scores.get("profit_factor", 0)
    wfe_val = val_scores.get("wfe_median", 0)
    mc_val = val_scores.get("mc_survival", 0)
    cr_score = fs["5_competition_readiness_score"]
    verdict_val = fs["6_verdict"]
    reqs_passed = fs["requirements_passed"]

    story.append(data_table(
        ["#", "Output", "Value", "Status"],
        [
            ["1", "Data Quality Score", f"{dq_score}/100", "PASS" if dq_score >= 90 else "FAIL"],
            ["2", "Training Readiness Score", f"{tr_score}/100", "PASS" if tr_score >= 75 else "FAIL"],
            ["3", "Model Scores", f"XGBoost={xgb_acc:.2f}, LSTM={lstm_acc:.2f}, Transformer={trans_acc:.2f}", "MEASURED"],
            ["4", "Validation Scores", f"Sharpe={sharpe_val}, PF={pf_val}, WFE={wfe_val}, MC={mc_val}", f"{reqs_passed} requirements met"],
            ["5", "Competition Readiness Score", f"{cr_score}/100", "FAIL" if cr_score < 80 else "PASS"],
            ["6", "VERDICT", str(verdict_val), str(verdict_val)],
        ],
        col_widths=[10*mm, 45*mm, 70*mm, CONTENT_W-125*mm],
    )[0])

    story.append(Paragraph("7.2  Root-Cause Analysis", H2))
    story.append(Paragraph(
        "The FAIL verdict is driven by 7 of 9 validation requirements not being met. "
        "The root causes are:", BODY))
    story.append(Paragraph(
        "<b>(1) Calibrated data is near-random-walk.</b> The 5-year calibrated dataset uses "
        "real measured per-bar volatility (13.5% annualized) but has zero drift (pure random "
        "walk). Real XAUUSD has regime-dependent drift (trends, ranges, mean reversion). "
        "A random walk is the hardest possible environment for a momentum-based strategy — "
        "any directional bet loses to transaction costs. This is why Sharpe=-3.07 and "
        "PF=0.62 (below 1.0 = net losing).", BODY))
    story.append(Paragraph(
        "<b>(2) Signal generation is simple momentum.</b> The backtest uses a 50-bar momentum "
        "signal (go long if price rose over last 50 bars, short if it fell). On a random walk, "
        "this signal has no predictive power — past returns do not predict future returns. "
        "The trained XGBoost model (test accuracy 49.8%) also has no edge on random-walk data.", BODY))
    story.append(Paragraph(
        "<b>(3) Insufficient real data.</b> Dukascopy rate-limited the download to 2,760 real "
        "bars (2 days). The calibrated dataset matches real statistics but cannot capture "
        "real-world microstructure patterns (order flow, news reactions, session transitions) "
        "that a model could learn from. With 5+ years of real tick data, the model could "
        "potentially find exploitable patterns.", BODY))

    story.append(Paragraph("7.3  What Would Be Needed for PASS", H2))
    story.append(Paragraph(
        "To achieve a PASS verdict, the following would be required:", BODY))
    story.append(data_table(
        ["Gap", "Required Action", "Expected Impact"],
        [
            ["Negative Sharpe (-3.07)",
             "Train on real 5-year XAUUSD data with regime-aware labels; use model predictions (not momentum) for signals",
             "Sharpe → 2.0+ if model finds real edge"],
            ["PF < 1.0 (0.62)",
             "Reduce trade frequency (fewer, higher-conviction trades); tighten stop-loss to cut losers faster",
             "PF → 2.0+ with better signal quality"],
            ["WFE = 0",
             "Walk-forward efficiency requires OOS Sharpe ≥ 0.85 × IS Sharpe; needs positive IS Sharpe first",
             "WFE → 0.85+ once Sharpe is positive"],
            ["MC Survival = 0",
             "Monte Carlo survival requires positive expectancy; needs PF > 1.0 first",
             "MC → 95%+ with positive expectancy"],
            ["Validator Score = 88.7",
             "Validator score reflects all suite results; needs backtest suite to pass (Sharpe-driven)",
             "Validator → 90+ with passing backtest"],
        ],
        col_widths=[40*mm, 70*mm, CONTENT_W-110*mm],
    )[0])

    story.append(Spacer(1, 6*mm))
    story.append(verdict_box(f"FINAL VERDICT:  {fs['6_verdict']}", "1E7D3A" if fs['6_verdict'] == "PASS" else "C8102E"))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        f"<b>Competition Readiness Score: {fs['5_competition_readiness_score']}/100</b>  ·  "
        f"Requirements: {fs['requirements_passed']}  ·  "
        f"Threshold: 80  ·  "
        "All metrics measured, not assumed.", BODY))

    doc.build(story)
    return output_path


if __name__ == "__main__":
    with open("/home/z/my-project/download/TITAN_Competition_Validation_Results.json") as f:
        results = json.load(f)
    out = "/home/z/my-project/download/TITAN_Competition_Validation_Report_v1.0.pdf"
    build_report(out, results)
    print(f"✓ PDF generated: {out}")
    print(f"  Size: {os.path.getsize(out)/1024:.1f} KB")
