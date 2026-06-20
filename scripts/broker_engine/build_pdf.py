"""
TITAN XAU AI — Broker Compatibility Engine
==========================================
Body content + PDF builder for the Broker Compatibility Engine architecture document.
Single-file approach for simplicity (smaller scope than the main architecture doc).
"""
import os
import sys
import hashlib
import platform

sys.path.insert(0, '/home/z/my-project/skills/pdf/scripts')

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    KeepTogether, HRFlowable, Image,
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

# ─── Font registration ────────────────────────────────────────────────────
FONT_DIR = '/usr/share/fonts'
pdfmetrics.registerFont(TTFont('FreeSerif', f'{FONT_DIR}/truetype/freefont/FreeSerif.ttf'))
pdfmetrics.registerFont(TTFont('FreeSerif-Bold', f'{FONT_DIR}/truetype/freefont/FreeSerifBold.ttf'))
pdfmetrics.registerFont(TTFont('FreeSerif-Italic', f'{FONT_DIR}/truetype/freefont/FreeSerifItalic.ttf'))
pdfmetrics.registerFont(TTFont('FreeSerif-BoldItalic', f'{FONT_DIR}/truetype/freefont/FreeSerifBoldItalic.ttf'))
pdfmetrics.registerFont(TTFont('DejaVuSans', f'{FONT_DIR}/truetype/dejavu/DejaVuSansMono.ttf'))
pdfmetrics.registerFont(TTFont('NotoSerifSC', f'{FONT_DIR}/truetype/noto-serif-sc/NotoSerifSC-Regular.ttf'))
pdfmetrics.registerFont(TTFont('NotoSerifSC-Bold', f'{FONT_DIR}/truetype/noto-serif-sc/NotoSerifSC-Bold.ttf'))

registerFontFamily('FreeSerif', normal='FreeSerif', bold='FreeSerif-Bold',
                   italic='FreeSerif-Italic', boldItalic='FreeSerif-BoldItalic')
registerFontFamily('DejaVuSans', normal='DejaVuSans', bold='DejaVuSans')
registerFontFamily('NotoSerifSC', normal='NotoSerifSC', bold='NotoSerifSC-Bold')

try:
    from pdf import install_font_fallback
    install_font_fallback()
except Exception:
    pass

# ─── Goldman Sachs white palette ──────────────────────────────────────────
HEADER_FILL = colors.HexColor('#14213D')
ACCENT = colors.HexColor('#C8102E')
TEXT_PRIMARY = colors.HexColor('#14213D')
TEXT_MUTED = colors.HexColor('#4A5568')
BORDER = colors.HexColor('#CBD5E1')
SECTION_BG = colors.HexColor('#F8FAFC')
CARD_BG = colors.HexColor('#F1F5F9')
TABLE_STRIPE = colors.HexColor('#F8FAFC')

DIAGRAM_DIR = '/home/z/my-project/scripts/broker_engine/diagrams/png'

# ─── Styles ───────────────────────────────────────────────────────────────
S = {}
S['h1'] = ParagraphStyle('h1', fontName='FreeSerif-Bold', fontSize=20, leading=26,
                          textColor=HEADER_FILL, spaceBefore=18, spaceAfter=10, alignment=TA_LEFT)
S['h2'] = ParagraphStyle('h2', fontName='FreeSerif-Bold', fontSize=14, leading=18,
                          textColor=HEADER_FILL, spaceBefore=14, spaceAfter=6, alignment=TA_LEFT)
S['h3'] = ParagraphStyle('h3', fontName='FreeSerif-Bold', fontSize=11.5, leading=15,
                          textColor=ACCENT, spaceBefore=10, spaceAfter=4, alignment=TA_LEFT)
S['body'] = ParagraphStyle('body', fontName='FreeSerif', fontSize=10.5, leading=16,
                            textColor=TEXT_PRIMARY, spaceBefore=0, spaceAfter=8,
                            alignment=TA_JUSTIFY, firstLineIndent=0)
S['bullet'] = ParagraphStyle('bullet', fontName='FreeSerif', fontSize=10.5, leading=15,
                              textColor=TEXT_PRIMARY, leftIndent=18, bulletIndent=4,
                              spaceBefore=2, spaceAfter=4, alignment=TA_LEFT)
S['code'] = ParagraphStyle('code', fontName='DejaVuSans', fontSize=9, leading=12,
                            textColor=TEXT_PRIMARY, leftIndent=14, rightIndent=14,
                            spaceBefore=6, spaceAfter=8, backColor=SECTION_BG,
                            borderColor=BORDER, borderWidth=0.5, borderPadding=8, alignment=TA_LEFT)
S['caption'] = ParagraphStyle('caption', fontName='FreeSerif-Italic', fontSize=9, leading=12,
                               textColor=TEXT_MUTED, alignment=TA_CENTER, spaceBefore=4, spaceAfter=14)
S['th'] = ParagraphStyle('th', fontName='FreeSerif-Bold', fontSize=9.5, leading=12,
                          textColor=colors.white, alignment=TA_LEFT)
S['td'] = ParagraphStyle('td', fontName='FreeSerif', fontSize=9, leading=12,
                          textColor=TEXT_PRIMARY, alignment=TA_LEFT)
S['callout'] = ParagraphStyle('callout', fontName='FreeSerif-Italic', fontSize=10, leading=15,
                               textColor=HEADER_FILL, leftIndent=18, rightIndent=18,
                               spaceBefore=8, spaceAfter=10, alignment=TA_LEFT,
                               backColor=CARD_BG, borderColor=ACCENT, borderWidth=0, borderPadding=10)

def h1(text, chapter_num=None):
    display = f'Chapter {chapter_num} — {text}' if chapter_num else text
    key = f'h1_{hashlib.md5(display.encode()).hexdigest()[:8]}'
    p = Paragraph(f'<a name="{key}"/><b>{display}</b>', S['h1'])
    p.bookmark_name = key
    p.bookmark_level = 0
    p.bookmark_text = display
    p.bookmark_key = key
    return p

def h2(text):
    key = f'h2_{hashlib.md5(text.encode()).hexdigest()[:8]}'
    p = Paragraph(f'<a name="{key}"/><b>{text}</b>', S['h2'])
    p.bookmark_name = key
    p.bookmark_level = 1
    p.bookmark_text = text
    p.bookmark_key = key
    return p

def h3(text):
    return Paragraph(f'<b>{text}</b>', S['h3'])

def p(text):
    return Paragraph(text, S['body'])

def bullet(text):
    return Paragraph(f'• {text}', S['bullet'])

def code(text):
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text = text.replace('\n', '<br/>')
    return Paragraph(f'<font name="DejaVuSans">{text}</font>', S['code'])

def caption(text):
    return Paragraph(text, S['caption'])

def callout(text):
    return Paragraph(text, S['callout'])

def diagram(filename, width_mm=170):
    path = os.path.join(DIAGRAM_DIR, filename)
    if not os.path.exists(path):
        return Paragraph(f'<i>[Diagram missing: {filename}]</i>', S['caption'])
    target_w = width_mm * mm
    from PIL import Image as PILImage
    pil = PILImage.open(path)
    aspect = pil.height / pil.width
    target_h = target_w * aspect
    max_h = 230 * mm
    if target_h > max_h:
        target_h = max_h
        target_w = target_h / aspect
    img = Image(path, width=target_w, height=target_h)
    img.hAlign = 'CENTER'
    return img

def table(data, col_widths=None):
    wrapped = []
    for i, row in enumerate(data):
        wrapped_row = []
        for cell in row:
            if isinstance(cell, str):
                style = S['th'] if i == 0 else S['td']
                wrapped_row.append(Paragraph(cell, style))
            else:
                wrapped_row.append(cell)
        wrapped.append(wrapped_row)
    available = 170 * mm
    if col_widths is None:
        n = len(data[0])
        col_widths = [available / n] * n
    else:
        total = sum(col_widths)
        scale = available / total
        col_widths = [w * scale for w in col_widths]
    t = Table(wrapped, colWidths=col_widths, hAlign='CENTER', repeatRows=1)
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_FILL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('LINEBELOW', (0, 0), (-1, 0), 1.2, HEADER_FILL),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_cmds.append(('BACKGROUND', (0, i), (-1, i), TABLE_STRIPE))
    t.setStyle(TableStyle(style_cmds))
    return t


# ════════════════════════════════════════════════════════════════════════════
#  TOC + Header/Footer
# ════════════════════════════════════════════════════════════════════════════

class TocDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if hasattr(flowable, 'bookmark_name'):
            level = getattr(flowable, 'bookmark_level', 0)
            text = getattr(flowable, 'bookmark_text', '')
            key = getattr(flowable, 'bookmark_key', '')
            self.notify('TOCEntry', (level, text, self.page, key))

def header_footer(canvas, doc):
    canvas.saveState()
    page_num = doc.page
    if page_num <= 2:  # skip TOC pages
        canvas.restoreState()
        return
    canvas.setStrokeColor(HEADER_FILL)
    canvas.setLineWidth(0.6)
    canvas.line(20*mm, A4[1] - 18*mm, A4[0] - 20*mm, A4[1] - 18*mm)
    canvas.setFont('FreeSerif-Italic', 8.5)
    canvas.setFillColor(TEXT_MUTED)
    canvas.drawString(20*mm, A4[1] - 14*mm, 'TITAN XAU AI — Broker Compatibility Engine')
    canvas.setFont('FreeSerif-Bold', 8.5)
    canvas.setFillColor(ACCENT)
    canvas.drawRightString(A4[0] - 20*mm, A4[1] - 14*mm, 'v1.0  ·  INTERNAL')
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.3)
    canvas.line(20*mm, 18*mm, A4[0] - 20*mm, 18*mm)
    canvas.setFont('FreeSerif-Italic', 8)
    canvas.setFillColor(TEXT_MUTED)
    canvas.drawString(20*mm, 12*mm, '© 2026 TITAN Quant Research  ·  Proprietary & Confidential')
    canvas.setFont('FreeSerif-Bold', 9)
    canvas.setFillColor(HEADER_FILL)
    canvas.drawRightString(A4[0] - 20*mm, 12*mm, f'{page_num}')
    canvas.setFillColor(ACCENT)
    canvas.circle(A4[0] - 25*mm, 14.5*mm, 1.0, fill=1, stroke=0)
    canvas.restoreState()

toc_h1_style = ParagraphStyle('TOC_H1', fontName='FreeSerif-Bold', fontSize=11, leading=16,
                               textColor=HEADER_FILL, leftIndent=0, spaceBefore=4)
toc_h2_style = ParagraphStyle('TOC_H2', fontName='FreeSerif', fontSize=10, leading=14,
                               textColor=colors.black, leftIndent=18, spaceBefore=1)


# ════════════════════════════════════════════════════════════════════════════
#  STORY BUILDER
# ════════════════════════════════════════════════════════════════════════════

def build_story():
    story = []

    # ─── TOC ──────────────────────────────────────────────────────────────
    story.append(Paragraph('<b>Table of Contents</b>',
                           ParagraphStyle('TOC_Title', fontName='FreeSerif-Bold', fontSize=22,
                                          leading=28, textColor=HEADER_FILL, alignment=TA_LEFT,
                                          spaceAfter=18)))
    story.append(HRFlowable(width='100%', thickness=2, color=ACCENT, spaceBefore=0, spaceAfter=18))
    toc = TableOfContents()
    toc.levelStyles = [toc_h1_style, toc_h2_style]
    story.append(toc)
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # Chapter 1 — Executive Summary
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Executive Summary', 1))
    story.append(p(
        'The Broker Compatibility Engine (BCE) is a TITAN XAU AI subsystem responsible for '
        'automatically detecting and validating the trading-environment properties of any '
        'connected MetaTrader 5 broker at runtime. It produces a single, immutable BrokerProfile '
        'value object containing nine critical properties: digits, point, contract size, tick size, '
        'tick value, leverage, spread type, commission type, and swap type. This profile is then '
        'consumed by the risk gate, the order manager, and the strategy coordinator to ensure all '
        'position sizing, PnL computation, and risk calculations are correct for the specific '
        'broker and account configuration in use.'
    ))
    story.append(p(
        'The BCE exists because the XAUUSD trading landscape is heterogeneous. Different brokers '
        'quote gold with different digit counts (2, 3, 4, or 5 digits after the decimal point), '
        'different contract sizes (100 in cent accounts, 100,000 in standard accounts), different '
        'leverage caps (1:30 to 1:Unlimited), different commission structures (per lot, per million, '
        'percentage, or none), and different swap calculation methods (points, percentage, or disabled). '
        'A trading system that hardcodes assumptions about any of these properties will produce '
        'incorrect position sizes, incorrect PnL, and incorrect risk exposure on at least some '
        'brokers — a defect class that has caused real-world trading losses in less disciplined systems.'
    ))
    story.append(p(
        'The BCE design is governed by two non-negotiable principles. First, no hardcoded pip values: '
        'every monetary calculation must derive from runtime-detected properties, never from a baked-in '
        'constant. Second, runtime calculations only: the engine performs all detection against the live '
        'MT5 terminal at startup and on cache expiry, with no static configuration files containing '
        'broker-specific values. These principles ensure that the system works correctly on any '
        'supported broker (Exness, IC Markets, Pepperstone, Tickmill, FP Markets, Fusion Markets, plus '
        'any generic MT5 broker) without code changes, and that it adapts automatically when a broker '
        'changes its contract specifications — which they do, occasionally and without notice.'
    ))
    story.append(p(
        'The engine is organized into five layers: probe (raw MT5 API calls), detection (nine '
        'property-specific detectors), validation (cross-property consistency checks), profile and state '
        '(profile library, cache, builder), and publication (event bus, error handler, audit logger). '
        'A strict layering rule ensures that detectors cannot reach into the publication layer and that '
        'the error handler has no dependency on the detection logic, making the failure paths independent '
        'of the success paths. The engine publishes a <font name="DejaVuSans">bce.profile.ready</font> '
        'event on the async event bus whenever a new profile is built, allowing downstream services to '
        'react to broker configuration changes in real time.'
    ))
    story.append(p(
        'This document specifies the complete architecture, flowchart, validation logic, error handling '
        'logic, and test cases for the BCE. It does not specify trading logic — the BCE is intentionally '
        'agnostic to strategy, signal generation, and order placement. Its sole responsibility is to '
        'answer the question "what is the trading environment?" with high confidence and explicit error '
        'classification when the answer is uncertain.'
    ))

    # ════════════════════════════════════════════════════════════════════
    # Chapter 2 — Problem Domain
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Problem Domain — Why Broker Compatibility Matters', 2))
    story.append(h2('The Heterogeneity of XAUUSD Brokerage'))
    story.append(p(
        'XAUUSD is quoted by every major retail and institutional forex broker, but the contract '
        'specifications vary dramatically. A standard lot of gold is conventionally 100 troy ounces, '
        'but brokers express this in MT5 with different digit counts and contract sizes. Exness quotes '
        'XAUUSD with 2 digits on cent accounts (price like 1950.45) and 5 digits on standard accounts '
        '(price like 1950.45123). IC Markets quotes 2 digits on standard accounts and 5 digits on Raw '
        'Spread accounts. Pepperstone follows the same pattern with their Standard and Razor account '
        'types. Tickmill uses 2 digits on Classic and 5 digits on Pro and VIP. The point value (the '
        'minimum price increment) is the inverse of 10^digits — 0.01 for 2 digits, 0.00001 for 5 digits — '
        'and every downstream calculation that uses points must use this runtime-detected value, never a '
        'hardcoded constant.'
    ))
    story.append(p(
        'Contract size, which determines how many ounces a "lot" represents, varies by account type. '
        'On a cent account, one lot might be 1 ounce (so a 100-cent balance can trade 0.01 lots without '
        'leverage). On a standard account, one lot is 100 ounces. On a micro account, one lot might be '
        '10 ounces. The contract size directly affects position value: a 1.00 lot at 100 contract size '
        'and $1,950 gold is $195,000 notional, while a 1.00 lot at 100,000 contract size at the same '
        'price would be $195,000,000 — a thousand-fold difference. Getting this wrong is catastrophic.'
    ))
    story.append(p(
        'Leverage caps vary by broker and jurisdiction. Exness offers "unlimited" leverage on cent '
        'accounts; IC Markets, Pepperstone, Tickmill, FP Markets, and Fusion Markets typically cap at '
        '1:500 for international clients and 1:30 for EU/UK regulated clients. The leverage directly '
        'determines the margin required per lot, and thus the maximum position size for a given account '
        'balance. A trading system that assumes 1:500 leverage on a 1:30 account will attempt to open '
        'positions that exceed available margin, triggering immediate broker rejection.'
    ))
    story.append(p(
        'Spread type (fixed vs variable), commission type (per lot, per million notional, percentage, '
        'or none), and swap type (points, percentage, or disabled) each have multiple variants across '
        'brokers. IC Markets Raw Spread charges $3.50 per $1M notional as commission; Pepperstone Razor '
        'charges $3.50 per $1M; Tickmill VIP charges $2 per $1M; Fusion Markets Zero charges $2.25 per '
        '$1M. Exness Standard charges no commission but marks up the spread. A trading system that '
        'computes transaction cost must detect the commission type at runtime, not assume it.'
    ))

    story.append(h2('The Cost of Hardcoded Assumptions'))
    story.append(p(
        'Trading systems that hardcode broker assumptions exhibit a specific and predictable failure '
        'mode: they work correctly on the broker they were developed against and produce subtly (or '
        'catastrophically) incorrect behavior on every other broker. A system developed against an IC '
        'Markets Raw Spread account (5 digits, $3.50/$1M commission) will, when deployed on an Exness '
        'cent account (2 digits, no commission, 100x smaller contract size), compute position sizes '
        '100x too large, PnL 100x too small, and transaction costs as zero — producing a trading book '
        'that appears profitable in the system but is hemorrhaging money in reality. This is not a '
        'theoretical risk; it has happened in production at multiple firms.'
    ))
    story.append(p(
        'The root cause is always the same: a developer hardcoded a value that should have been '
        'detected. "Pip = 0.0001" (wrong on 5-digit accounts where pip = 0.01 and point = 0.00001). '
        '"Contract size = 100000" (wrong on cent accounts). "Commission = $7 per lot" (wrong on '
        'per-million brokers). These constants creep into code through legitimate-looking shortcuts '
        'and are then extremely difficult to find because the system appears to work — the bug only '
        'manifests when the system is deployed on a different broker, by which point the developer '
        'who wrote the code has often moved on.'
    ))
    story.append(p(
        'The BCE eliminates this entire class of bugs by making runtime detection the only path. There '
        'is no configuration file where a developer can hardcode "pip = 0.0001"; the only way to obtain '
        'the pip value is to call <font name="DejaVuSans">bce.get_profile(symbol).pip_value()</font>, '
        'which returns a value derived at runtime from the detected digits property. The architecture '
        'enforces the principle structurally, not by convention.'
    ))

    story.append(h2('Account Type Taxonomy'))
    story.append(p(
        'Beyond broker-specific differences, the BCE must classify the account type, which determines '
        'the magnitude of monetary values exposed to the system. Four account types are supported:'
    ))
    story.append(bullet('<b>Cent accounts</b>: balance is denominated in cents (e.g., 10000 cents = $100). Contract size is typically 100 (one cent-lot = 1 ounce). Used by Exness and others for low-capital trading.'))
    story.append(bullet('<b>Micro accounts</b>: balance is denominated in dollars but with smaller minimum trade sizes (0.01 lots) and often reduced contract sizes (e.g., 10000 = 1 ounce per 0.01 lot). Common for new traders.'))
    story.append(bullet('<b>Dollar (standard) accounts</b>: balance in dollars, contract size 100000 (1 lot = 100 ounces), the conventional MT5 setup. The default assumption for most testing.'))
    story.append(bullet('<b>Raw / ECN accounts</b>: balance in dollars, contract size 100000, but with raw interbank spreads plus per-million commission. Used by IC Markets Raw, Pepperstone Razor, Tickmill VIP, FP Markets Raw, Fusion Zero.'))
    story.append(p(
        'Account type classification is performed by examining the balance magnitude, server name '
        '(cent accounts often include "cent" in the server name), and contract size. The classification '
        'is informational — it does not change the detected properties — but it is recorded in the '
        'BrokerProfile so downstream services can apply account-type-specific logic (e.g., the strategy '
        'coordinator may want to use different position sizing on cent accounts versus dollar accounts).'
    ))

    # ════════════════════════════════════════════════════════════════════
    # Chapter 3 — Design Principles
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Design Principles', 3))
    story.append(p(
        'The BCE is governed by five design principles. Each principle exists to prevent a specific '
        'class of bug that has been observed in less-disciplined broker-compatibility implementations. '
        'These principles are non-negotiable; any code change that violates them must be rejected in '
        'code review.'
    ))

    story.append(h2('Principle 1 — No Hardcoded Pip Values'))
    story.append(p(
        'The pip value (the monetary value of a one-pip price movement for one lot) is the most '
        'commonly hardcoded value in trading systems, and the most common source of cross-broker bugs. '
        'The BCE forbids hardcoded pip values anywhere in the codebase. The pip value must always be '
        'computed at runtime from the detected digits and contract size. Specifically, for a 2-digit '
        'or 4-digit broker, pip = point × 1 (the smallest price increment is the pip). For a 3-digit '
        'or 5-digit broker, pip = point × 10 (the smallest increment is a fractional pip, and the '
        '"pip" is the conventional unit used by traders). The BCE exposes this via the '
        '<font name="DejaVuSans">BrokerProfile.pip_value()</font> method, which performs the '
        'computation; there is no constant.'
    ))

    story.append(h2('Principle 2 — Runtime Calculations Only'))
    story.append(p(
        'All broker-specific values must be detected at runtime by querying the MT5 terminal. The BCE '
        'does not load broker profiles from configuration files at startup. The BrokerProfileLibrary '
        '(which contains known profiles for the six supported brokers) is used only for validation — '
        'comparing detected values against known-good ranges to flag deviations — never as a source '
        'of truth. If a broker changes its contract specifications (which happens occasionally), the '
        'BCE will detect the new values on the next detection cycle and update the profile accordingly. '
        'There is no need to ship a code or config change in response.'
    ))

    story.append(h2('Principle 3 — Fail-Safe Defaults'))
    story.append(p(
        'When detection fails or produces a suspicious value, the BCE applies a safe-default fallback '
        'rather than refusing to operate. The fallbacks are deliberately conservative: contract size '
        'defaults to 100,000 (standard lot), leverage defaults to 30 (conservative), tick size '
        'defaults to the point value, and so on. The only property for which no fallback exists is '
        'digits — if digits cannot be determined, the engine treats this as a HARD error and blocks '
        'trading on that symbol, because every downstream calculation depends on digits and an '
        'incorrect assumption is more dangerous than no trading.'
    ))

    story.append(h2('Principle 4 — Explicit Error Classification'))
    story.append(p(
        'Every detection failure is classified into one of three severity levels: HARD (block trading, '
        'engage kill switch, page operator), SOFT (apply safe-default, allow trading with WARN flag, '
        'email operator), or WARN (use broker-reported value as-is, attach WARN flag, log only). The '
        'classification is encoded in an error code (e.g., <font name="DejaVuSans">BCE_TICK_VALUE_MISSING</font>) '
        'that is recorded in the audit log along with the full detection context. This explicit '
        'classification ensures that operators can quickly assess the severity of any BCE alert and '
        'that downstream services can react appropriately (e.g., the risk gate may reduce position '
        'size when a SOFT error is active).'
    ))

    story.append(h2('Principle 5 — Structural Separation of Detection and Validation'))
    story.append(p(
        'The detection layer (which queries MT5 and produces raw property values) is structurally '
        'separate from the validation layer (which cross-checks those values for consistency). This '
        'separation ensures that a bug in detection cannot be masked by a coincidental bug in '
        'validation, and vice versa. The two layers communicate only through a PropertyMap value '
        'object, and the validation layer has no knowledge of how the values were obtained. This '
        'makes it possible to test detection and validation independently, and to add new validators '
        'without touching detector code.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # Chapter 4 — Architecture
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Architecture Overview', 4))
    story.append(p(
        'The BCE is organized into five logical layers, each containing a cohesive set of components '
        'with a single responsibility. The layers are stacked such that data flows downward (probe at '
        'the top, publication at the bottom) and errors flow upward (publication layer reports errors '
        'to the operator and audit log). A strict dependency rule — layer N may only depend on layer '
        'N-1 or below — is enforced by an architecture linter in CI; cyclic dependencies fail the build.'
    ))
    story.append(diagram('d01_architecture.png', width_mm=170))
    story.append(caption('Figure 4.1 — Broker Compatibility Engine internal architecture, showing the five layers and their components.'))

    story.append(h2('Layer Responsibilities'))
    story.append(h3('L1 — Probe Layer'))
    story.append(p(
        'The probe layer is the only component that talks directly to the MT5 terminal. It contains '
        'four probes: <b>SymbolProbe</b> (queries symbol_info_tick for digits, point, contract size, '
        'tick size, tick value, swap mode, swap long, swap short), <b>AccountProbe</b> (queries '
        'account_info for leverage, balance, equity, currency, server name), <b>TradeProbe</b> '
        '(performs a 0.01-lot probe order and immediately cancels it, used to verify commission '
        'deduction), and <b>ServerProbe</b> (queries the broker server name for fingerprinting). All '
        'probes implement the <font name="DejaVuSans">IBrokerProbe</font> interface, allowing the BCE '
        'to support non-MT5 brokers in the future (FIX, IB) without changing the detection layer.'
    ))

    story.append(h3('L2 — Detection Layer'))
    story.append(p(
        'The detection layer contains ten detectors, each responsible for one property: '
        '<b>DigitsDetector</b>, <b>ContractSizeDetector</b>, <b>TickSizeDetector</b>, '
        '<b>TickValueDetector</b>, <b>LeverageDetector</b>, <b>SpreadTypeDetector</b>, '
        '<b>CommissionDetector</b>, <b>SwapTypeDetector</b>, <b>AccountClassifier</b>, and '
        '<b>BrokerFingerprinter</b>. Each detector implements the '
        '<font name="DejaVuSans">IDetector</font> interface with a single '
        '<font name="DejaVuSans">detect(probe)</font> method that returns a PropertyResult value '
        'object (value, confidence, source, warnings). Detectors are independent and can run in '
        'parallel; the engine assembles their results into a PropertyMap for the validation layer.'
    ))

    story.append(h3('L3 — Validation Layer'))
    story.append(p(
        'The validation layer contains three validators that cross-check the detected properties for '
        'consistency. <b>CrossPropertyValidator</b> checks mathematical relationships between '
        'properties (e.g., tick_value ≈ tick_size × contract_size × current_price). '
        '<b>ProfileConsistencyValidator</b> compares the detected values against the known-good '
        'profile for the fingerprinted broker (if matched), flagging deviations larger than 10%. '
        '<b>SanityBoundsValidator</b> checks that each property falls within sane ranges (digits in '
        '{2,3,4,5}, leverage in [1, 3000], etc.). Validators produce a ValidationResult containing '
        'zero or more ErrorEvent objects, each classified by severity.'
    ))

    story.append(h3('L4 — Profile & State Layer'))
    story.append(p(
        'The profile layer assembles the validated properties into a BrokerProfile value object and '
        'manages its lifecycle. <b>BrokerProfileLibrary</b> holds the known-good templates for the '
        'six supported brokers (Exness, IC Markets, Pepperstone, Tickmill, FP Markets, Fusion Markets) '
        'plus a generic fallback. <b>ProfileCache</b> stores detected profiles in Redis with a 24-hour '
        'TTL, keyed by <font name="DejaVuSans">bce:{broker}:{symbol}</font>. <b>ProfileBuilder</b> '
        'assembles the nine detector outputs plus the fingerprint and detection timestamp into the '
        'final immutable BrokerProfile.'
    ))

    story.append(h3('L5 — Publication Layer'))
    story.append(p(
        'The publication layer handles the engine\'s external communication. <b>ProfilePublisher</b> '
        'emits a <font name="DejaVuSans">bce.profile.ready</font> event on the async event bus '
        'whenever a new profile is built, with a FlatBuffer-serialized BrokerProfile payload. '
        '<b>ErrorHandler</b> classifies detection and validation errors by severity and routes them '
        'to the appropriate operator alert channel (PagerDuty for HARD, email for SOFT, log only for '
        'WARN). <b>AuditLogger</b> writes every detection, validation, and error event to the '
        'immutable hash-chained audit store.'
    ))

    story.append(h2('Service Inventory'))
    story.append(table([
        ['Layer', 'Component', 'Language', 'Responsibility', 'p99 Latency'],
        ['L1', 'SymbolProbe', 'C++', 'symbol_info_tick() call', '5 ms'],
        ['L1', 'AccountProbe', 'C++', 'account_info() call', '5 ms'],
        ['L1', 'TradeProbe', 'C++', '0.01-lot probe order + cancel', '200 ms'],
        ['L1', 'ServerProbe', 'C++', 'account_info_server', '1 ms'],
        ['L2', 'DigitsDetector', 'C++', 'digits + point validation', '0.01 ms'],
        ['L2', 'TickSize/ValueDetectors', 'C++', 'tick size + value', '0.05 ms'],
        ['L2', 'SpreadTypeDetector', 'C++', '1000-tick stddev analysis', '50 ms'],
        ['L2', 'CommissionDetector', 'C++', 'commission classification', '0.05 ms'],
        ['L2', 'SwapTypeDetector', 'C++', 'swap mode classification', '0.05 ms'],
        ['L2', 'AccountClassifier', 'C++', 'cent/micro/dollar/raw', '0.05 ms'],
        ['L2', 'BrokerFingerprinter', 'C++', 'regex match on server_name', '0.1 ms'],
        ['L3', 'CrossPropertyValidator', 'C++', 'math consistency checks', '0.05 ms'],
        ['L3', 'ProfileConsistencyValidator', 'C++', 'profile template match', '0.1 ms'],
        ['L3', 'SanityBoundsValidator', 'C++', 'range checks', '0.01 ms'],
        ['L4', 'ProfileBuilder', 'C++', 'assemble BrokerProfile', '0.05 ms'],
        ['L4', 'ProfileCache', 'Python', 'Redis SETEX / GET', '2 ms'],
        ['L4', 'BrokerProfileLibrary', 'C++', 'static broker templates', '0.01 ms'],
        ['L5', 'ProfilePublisher', 'C++', 'ZMQ PUB event', '0.5 ms'],
        ['L5', 'ErrorHandler', 'Python', 'classify + route', '1 ms'],
        ['L5', 'AuditLogger', 'Python', 'WORM append', 'async'],
    ], col_widths=[8, 30, 14, 60, 18]))
    story.append(Spacer(1, 8))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # Chapter 5 — Per-Property Detection Logic
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Per-Property Detection Logic', 5))
    story.append(p(
        'This chapter documents the detection algorithm for each of the nine properties. Each detector '
        'is a self-contained state machine that queries the probe layer, applies property-specific '
        'logic, and returns a PropertyResult. The state machines for the most consequential detectors '
        'are shown in Figure 5.1.'
    ))
    story.append(diagram('d03_state_machines.png', width_mm=170))
    story.append(caption('Figure 5.1 — Per-property detection state machines for digits, tick size/value, spread type, commission type, account type, and broker fingerprint.'))

    story.append(h2('5.1 Digits & Point Detection'))
    story.append(p(
        'Digits and point are the most fundamental properties — every other calculation depends on '
        'them. The DigitsDetector queries <font name="DejaVuSans">symbol_info_tick(symbol)</font> and '
        'reads the <font name="DejaVuSans">digits</font> field. It validates that the value is in '
        '{2, 3, 4, 5}; values outside this set produce a HARD error '
        '(<font name="DejaVuSans">BCE_DIGITS_OUT_OF_RANGE</font>) and block the symbol. The point '
        'value is read from the same call (<font name="DejaVuSans">point</font> field) and verified '
        'against <font name="DejaVuSans">10^(-digits)</font> — for 5 digits, point must be 0.00001; '
        'for 2 digits, point must be 0.01. A mismatch produces a HARD error '
        '(<font name="DejaVuSans">BCE_POINT_DIGITS_MISMATCH</font>).'
    ))
    story.append(p(
        'The pip value is derived from digits: for 2 or 4 digits, pip = point (smallest increment is '
        'the pip); for 3 or 5 digits, pip = point × 10 (smallest increment is a fractional pip). The '
        'BCE exposes this via <font name="DejaVuSans">BrokerProfile.pip_value()</font> rather than '
        'storing it as a separate property, to avoid the implication that pip is independently '
        'detected. Pip is a derived value, not a detected one.'
    ))

    story.append(h2('5.2 Contract Size Detection'))
    story.append(p(
        'The ContractSizeDetector reads <font name="DejaVuSans">trade_contract_size</font> from the '
        'symbol info. It validates that the value is in [1, 1,000,000] — values outside this range '
        'produce a SOFT error (<font name="DejaVuSans">BCE_CONTRACT_SIZE_INVALID</font>) and the '
        'engine falls back to 100,000 (standard lot). The contract size is the primary signal for '
        'account type classification: a value of 100 strongly suggests a cent account; 10,000 '
        'suggests a micro account; 100,000 suggests a standard dollar or raw account.'
    ))

    story.append(h2('5.3 Tick Size & Tick Value Detection'))
    story.append(p(
        'The TickSizeDetector reads <font name="DejaVuSans">trade_tick_size</font>. If the value is '
        'zero or missing (some brokers do not populate this field), the detector falls back to the '
        'point value and emits a SOFT warning. The TickValueDetector reads '
        '<font name="DejaVuSans">trade_tick_value</font> — the monetary value of one tick for one '
        'standard lot. If this is zero or missing, the engine computes it as '
        '<font name="DejaVuSans">tick_size × contract_size × current_price / contract_size</font>, '
        'simplified to <font name="DejaVuSans">tick_size × current_price × (contract_size / '
        'contract_size)</font> — which equals <font name="DejaVuSans">tick_size × price</font> for '
        'XAUUSD where contract size is denominated in the same units as the price.'
    ))
    story.append(p(
        'The tick_value cross-check is the most important validation in the engine. The validator '
        'computes the expected tick_value as <font name="DejaVuSans">tick_size × contract_size × '
        'current_price</font> and compares it to the broker-reported value. A deviation of more than '
        '5% triggers a WARN (<font name="DejaVuSans">BCE_TICK_VALUE_DEVIATION</font>) — the '
        'broker-reported value is used as-is, but a warning flag is attached to the profile. A '
        'deviation of more than 25% triggers a SOFT error, falling back to the computed value. This '
        'cross-check catches both broker data feed errors and BCE detection bugs.'
    ))

    story.append(h2('5.4 Leverage Detection'))
    story.append(p(
        'The LeverageDetector reads <font name="DejaVuSans">account_info().leverage</font>. The '
        'value is an integer representing the leverage ratio (e.g., 500 means 1:500). Values outside '
        '[1, 3000] produce a SOFT error '
        '(<font name="DejaVuSans">BCE_LEVERAGE_OUT_OF_RANGE</font>) and the engine falls back to 30 '
        '(conservative). The upper bound of 3000 covers Exness\'s highest leverage offering; values '
        'above this are almost certainly data feed errors. Note that Exness reports leverage as the '
        'integer 0 to indicate "unlimited" — the detector special-cases this and stores it as the '
        'string "UNLIMITED" in the profile, with downstream risk code applying a configurable cap '
        '(default 1:1000) for safety.'
    ))

    story.append(h2('5.5 Spread Type Detection'))
    story.append(p(
        'The SpreadTypeDetector samples 1000 ticks (approximately 20 seconds of normal market '
        'activity) and computes the spread for each tick as <font name="DejaVuSans">ask - bid</font>. '
        'It then computes the mean (μ) and standard deviation (σ) of the spread. If σ/μ is less than '
        '0.05 (i.e., the spread varies by less than 5% of its mean), the spread is classified as '
        'FIXED; otherwise it is VARIABLE. The classifier also reports μ and σ in the profile so '
        'downstream services (especially the slippage model) can use them.'
    ))
    story.append(p(
        'If fewer than 100 ticks can be sampled (e.g., the market is closed or the symbol is '
        'illiquid), the detector falls back to VARIABLE classification and emits a SOFT warning '
        '(<font name="DejaVuSans">BCE_SPREAD_SAMPLE_INSUFFICIENT</font>). A negative spread in any '
        'sample is a HARD error (<font name="DejaVuSans">BCE_SPREAD_NEGATIVE</font>) — it indicates '
        'either a broker data feed error or a crossed market, both of which make safe trading '
        'impossible.'
    ))

    story.append(h2('5.6 Commission Type Detection'))
    story.append(p(
        'The CommissionDetector reads <font name="DejaVuSans">account_info().commission_trade</font> '
        '(or equivalent). If the rate is zero, the commission type is NONE (the broker makes money '
        'purely from spread mark-up, common for Exness Standard). For non-zero rates, the detector '
        'classifies by magnitude relative to contract size:'
    ))
    story.append(bullet('Rate < 1.0 and contract_size > 10000: PER_MILLION (rate is dollars per $1M notional). Common for raw/ECN accounts ($2.00 to $7.00 per $1M).'))
    story.append(bullet('Rate in [1.0, 50.0] and contract_size >= 100000: PER_LOT (rate is dollars per standard lot). Less common but used by some brokers.'))
    story.append(bullet('Rate < 0.001 (i.e., rate × 10000 < 1): PCT (rate is a percentage of notional). Rare but used by some ECN venues.'))
    story.append(p(
        'The classification is heuristic because MT5 does not explicitly state the commission unit. '
        'The detector logs the raw rate, the classification, and the reasoning in the audit log so '
        'operators can verify the classification against the broker\'s published fee schedule. '
        'Misclassification is a WARN (not HARD or SOFT) because the worst case is overestimating '
        'transaction cost, which makes the system more conservative — a safe failure direction.'
    ))

    story.append(h2('5.7 Swap Type Detection'))
    story.append(p(
        'The SwapTypeDetector reads <font name="DejaVuSans">swap_mode</font> from the symbol info. '
        'MT5 supports several swap modes: <font name="DejaVuSans">SWAP_DISABLED</font> (no swap '
        'charged), <font name="DejaVuSans">SWAP_BY_POINTS</font> (swap charged in points), '
        '<font name="DejaVuSans">SWAP_BY_CURRENCY</font> (swap charged in account currency per lot), '
        'and <font name="DejaVuSans">SWAP_BY_INTEREST</font> (swap charged as annual percentage '
        'rate). The detector maps these to three classifications: NONE, POINTS, or PCT. The actual '
        'swap long and swap short values are recorded in the profile for downstream use by the '
        'overnight-risk calculator.'
    ))

    story.append(h2('5.8 Account Type Classification'))
    story.append(p(
        'The AccountClassifier combines balance magnitude, server name, and contract size to classify '
        'the account as CENT, MICRO, DOLLAR, or RAW. The decision tree is:'
    ))
    story.append(bullet('If balance < 100 (account currency units) and contract_size <= 1000: classify as CENT. Cent accounts typically have small balances denominated in cents.'))
    story.append(bullet('Else if balance in [100, 10000) and contract_size in [1000, 50000]: classify as MICRO. Micro accounts have small balances but standard-ish contract sizes.'))
    story.append(bullet('Else if balance >= 10000 and server_name contains "raw" or "ecn" (case-insensitive): classify as RAW. Raw accounts have standard balances but raw spreads + commission.'))
    story.append(bullet('Else if balance >= 10000: classify as DOLLAR (standard account).'))
    story.append(bullet('Else: classify as DOLLAR with WARN flag (unusual configuration, log for review).'))
    story.append(p(
        'The classification is informational only — it does not change the detected properties — but '
        'it is recorded in the BrokerProfile for downstream consumption. The strategy coordinator '
        'may apply different position sizing on cent accounts (where the entire balance is at risk '
        'on a single trade) versus dollar accounts (where risk is typically a small percentage).'
    ))

    story.append(h2('5.9 Broker Fingerprinting'))
    story.append(p(
        'The BrokerFingerprinter reads the server name from '
        '<font name="DejaVuSans">account_info().server</font> and matches it against a set of '
        'case-insensitive regular expressions, one per supported broker:'
    ))
    story.append(table([
        ['Broker', 'Regex', 'Notes'],
        ['Exness', '(?i)exness', 'Multiple server variants (Exness-Real, Exness-Techno, etc.)'],
        ['IC Markets', '(?i)icmarkets|ic markets|ic-markets', 'Includes hyphenated variant'],
        ['Pepperstone', '(?i)pepperstone|pepper', 'Commonly shortened in server names'],
        ['Tickmill', '(?i)tickmill|tick mill', 'Includes space variant'],
        ['FP Markets', '(?i)fpmarkets|fp markets|fp-markets', 'Includes hyphenated variant'],
        ['Fusion Markets', '(?i)fusion|fusion markets', 'Short match for "Fusion" prefix'],
        ['GENERIC', '(no match)', 'Fallback for unknown brokers'],
    ], col_widths=[24, 50, 96]))
    story.append(Spacer(1, 8))
    story.append(p(
        'When a broker is identified, the engine loads the corresponding template from the '
        'BrokerProfileLibrary and uses it for the ProfileConsistencyValidator. The template contains '
        'expected ranges for each property (e.g., for IC Markets Raw: digits=5, contract_size=100000, '
        'commission_type=PER_MILLION, commission_rate in [2.0, 7.0]). Deviations from the template '
        'larger than 10% produce a WARN — the detected values are used as-is, but the warning is '
        'logged so operators can investigate whether the broker has changed its specifications or '
        'whether the BCE has a bug.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # Chapter 6 — End-to-End Flowchart
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('End-to-End Detection Flowchart', 6))
    story.append(p(
        'The flowchart in Figure 6.1 shows the complete end-to-end detection sequence, from MT5 '
        'connection event through to publication of the BrokerProfile on the event bus. The sequence '
        'is initiated when the MT5 bridge reports a successful connection, and it completes when the '
        'profile is cached in Redis and published to subscribers. The cache hit path returns a '
        'previously-detected profile in under one millisecond, avoiding the full detection sequence '
        'for already-known broker/symbol combinations.'
    ))
    story.append(diagram('d02_flowchart.png', width_mm=170))
    story.append(caption('Figure 6.1 — End-to-end detection flowchart. Cache hit returns in <1ms; cache miss triggers full 9-detector sequence + 3-validator sequence.'))

    story.append(h2('Sequence Description'))
    story.append(p(
        'The sequence begins when the MT5 bridge establishes a connection to the broker terminal. '
        'The BCE first checks the Redis cache for an entry matching '
        '<font name="DejaVuSans">bce:{broker_fingerprint}:{symbol}</font>. If a valid (non-expired) '
        'entry exists, it is returned immediately — the full detection sequence is skipped. The '
        'cache TTL is 24 hours, covering a typical trading session.'
    ))
    story.append(p(
        'On a cache miss, the engine executes the full detection sequence. The probe layer queries '
        'the MT5 terminal for symbol info, account info, and a 1000-tick sample (for spread '
        'analysis). The ten detectors then run in parallel, each producing a PropertyResult. The '
        'PropertyMap is assembled and passed to the three validators, which run sequentially (each '
        'validator depends on the previous one\'s output for some checks).'
    ))
    story.append(p(
        'If validation produces any HARD errors, the engine engages the kill switch, blocks trading '
        'on the symbol, and pages the operator. If validation produces only SOFT or WARN errors, '
        'the engine applies safe-defaults for SOFT errors and proceeds to build the profile. The '
        'profile is cached in Redis (overwriting any previous entry) and published on the event bus '
        'via a <font name="DejaVuSans">bce.profile.ready</font> event, which downstream services '
        '(risk gate, order manager, strategy coordinator) subscribe to.'
    ))

    story.append(h2('Re-detection Triggers'))
    story.append(p(
        'The BCE re-runs the detection sequence when any of the following events occur:'
    ))
    story.append(bullet('Cache TTL expiry (24 hours after last detection)'))
    story.append(bullet('Manual operator invalidation via the operator console (e.g., after broker maintenance)'))
    story.append(bullet('MT5 bridge reconnection (broker disconnected and reconnected)'))
    story.append(bullet('Symbol change (e.g., rolling from XAUUSD to XAUUSDm — the suffix can change between brokers)'))
    story.append(bullet('Property change detection (a background job samples properties every 5 minutes and triggers re-detection if any change is observed)'))
    story.append(p(
        'The re-detection sequence is identical to the initial detection, except that the cache is '
        'invalidated first. If the new detection produces a profile that differs from the cached one, '
        'a <font name="DejaVuSans">bce.profile.changed</font> event is published in addition to '
        '<font name="DejaVuSans">bce.profile.ready</font>, allowing downstream services to react to '
        'configuration changes (e.g., the risk gate may need to recompute exposure).'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # Chapter 7 — Validation Logic
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Validation Logic', 7))
    story.append(p(
        'Validation is the BCE\'s defense against incorrect detection. The validation layer contains '
        'three validators that run sequentially after all detectors have completed. Each validator '
        'produces zero or more ErrorEvent objects, classified by severity. The complete validation '
        'tree is shown in Figure 7.1.'
    ))
    story.append(diagram('d04_validation_errors.png', width_mm=170))
    story.append(caption('Figure 7.1 — Cross-property validation tree (top) and 3-tier error handling decision tree (bottom) with safe-default fallback table.'))

    story.append(h2('Validator 1 — CrossPropertyValidator'))
    story.append(p(
        'The CrossPropertyValidator checks mathematical relationships between properties that must '
        'hold for any valid broker configuration. These checks are independent of any specific broker '
        'profile — they apply to all MT5 brokers universally.'
    ))
    story.append(bullet('<b>Point-digits consistency</b>: point must equal 10^(-digits). For 5 digits, point = 0.00001. For 2 digits, point = 0.01. Mismatch = HARD error.'))
    story.append(bullet('<b>Tick value cross-check</b>: |tick_value − (tick_size × contract_size × current_price)| / tick_value must be less than 5%. Larger deviation = WARN; missing tick_value = SOFT with computed fallback.'))
    story.append(bullet('<b>Leverage range</b>: leverage must be in [1, 3000] (or "UNLIMITED" for Exness). Out of range = SOFT with fallback to 30.'))
    story.append(bullet('<b>Contract size range</b>: contract_size must be in [1, 1,000,000]. Out of range = SOFT with fallback to 100,000.'))
    story.append(bullet('<b>Spread positivity</b>: every sampled spread must be non-negative. Any negative spread = HARD error (crossed market or data feed error).'))

    story.append(h2('Validator 2 — ProfileConsistencyValidator'))
    story.append(p(
        'The ProfileConsistencyValidator compares the detected properties against the known-good '
        'template for the fingerprinted broker. If the broker is GENERIC (no fingerprint match), '
        'this validator is skipped. For a matched broker, the validator checks each property against '
        'the template\'s expected range and flags deviations larger than 10%. Deviations are WARN, '
        'not HARD or SOFT — the detected values are always used as-is, but the warning is logged so '
        'operators can investigate.'
    ))
    story.append(p(
        'The validator is intentionally lenient because broker specifications do change occasionally. '
        'A WARN gives operators visibility without disrupting trading. If the deviation is large '
        'enough to suggest a detection bug (e.g., 5 digits detected on an Exness cent account that '
        'should be 2 digits), the operator can manually trigger re-detection or engage the kill '
        'switch based on the warning.'
    ))

    story.append(h2('Validator 3 — SanityBoundsValidator'))
    story.append(p(
        'The SanityBoundsValidator checks that each property falls within sane absolute ranges, '
        'independent of any broker profile. These checks catch gross detection errors (e.g., a '
        'contract_size of 0 due to a missing field, or a leverage of -1 due to a signed integer '
        'interpretation). The bounds are deliberately wide — they exist to catch absurd values, not '
        'to enforce policy.'
    ))
    story.append(table([
        ['Property', 'Lower Bound', 'Upper Bound', 'Violation Severity', 'Fallback'],
        ['digits', '2', '5', 'HARD', '(none — block symbol)'],
        ['point', '1e-6', '1.0', 'HARD', '(none)'],
        ['contract_size', '1', '1,000,000', 'SOFT', '100,000'],
        ['tick_size', '1e-8', '1.0', 'SOFT', 'point value'],
        ['tick_value', '0', '1,000,000', 'SOFT', 'tick_size × price'],
        ['leverage', '1', '3000', 'SOFT', '30'],
        ['spread', '0', '∞', 'HARD (if negative)', '(none)'],
        ['commission_rate', '0', '1,000', 'WARN', '0 (assume NONE)'],
        ['swap_long', '-1000', '1000', 'WARN', '0 (assume no swap)'],
        ['swap_short', '-1000', '1000', 'WARN', '0 (assume no swap)'],
    ], col_widths=[28, 18, 22, 26, 30]))
    story.append(Spacer(1, 8))

    story.append(h2('Validation Result Aggregation'))
    story.append(p(
        'The three validators produce a combined ValidationResult. If any validator produces a HARD '
        'error, the result is HARD and the engine blocks trading. If no HARD errors but one or more '
        'SOFT errors, the result is SOFT and the engine applies safe-defaults. If only WARN errors, '
        'the result is WARN and the engine uses detected values as-is. The complete result is '
        'attached to the BrokerProfile as a <font name="DejaVuSans">validation_summary</font> field, '
        'allowing downstream services to inspect the confidence level of the profile.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # Chapter 8 — Error Handling Logic
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Error Handling Logic', 8))
    story.append(p(
        'Error handling is the BCE\'s safety net. Every detection failure, validation failure, and '
        'probe error is classified into one of three severity tiers and routed to the appropriate '
        'operator alert channel. The complete classification and routing logic is shown in Figure 7.1 '
        '(bottom half), and the full error code table is reproduced below.'
    ))

    story.append(h2('Three-Tier Severity Classification'))
    story.append(h3('HARD — Block Trading'))
    story.append(p(
        'HARD errors indicate that the broker configuration cannot be safely determined. The engine '
        'blocks trading on the affected symbol, engages the kill switch if the error affects the '
        'primary trading symbol, and pages the operator via PagerDuty (P1 severity). HARD errors '
        'are rare and usually indicate either a broker data feed problem or a BCE bug. Examples: '
        'digits outside {2,3,4,5}, point ≠ 10^(-digits), negative spread in sample.'
    ))

    story.append(h3('SOFT — Safe-Default Fallback'))
    story.append(p(
        'SOFT errors indicate that a specific property could not be detected reliably, but the '
        'engine can continue operating with a safe-default value. The fallback is always '
        'conservative (e.g., leverage defaults to 30, not 500). The engine allows trading but '
        'attaches a WARN flag to the profile, and downstream services may apply additional '
        'constraints (e.g., the risk gate may reduce position size when a SOFT error is active). '
        'The operator is notified via email (P2 severity). Examples: tick_value missing (computed '
        'fallback), contract_size out of range (100,000 fallback), leverage out of range (30 '
        'fallback).'
    ))

    story.append(h3('WARN — Informational'))
    story.append(p(
        'WARN errors indicate a deviation from expectation that does not affect trading safety. The '
        'engine uses the broker-reported value as-is, attaches a WARN flag to the profile, and logs '
        'the warning for operator review. No operator alert is sent. WARN errors are common and '
        'usually benign — they exist to give operators visibility into broker behavior changes and '
        'potential detection anomalies. Examples: tick_value deviation > 5%, profile deviation > '
        '10%, broker not in fingerprint library (GENERIC).'
    ))

    story.append(h2('Safe-Default Fallback Table'))
    story.append(p(
        'The safe-default table (Figure 7.1, bottom right) specifies the fallback value for each '
        'property when detection fails. Fallbacks are deliberately conservative — they err on the '
        'side of reducing position size and increasing margin requirements, never the reverse. The '
        'one exception is digits: there is no safe fallback for digits because every downstream '
        'calculation depends on it. A digits detection failure is always HARD, blocking the symbol.'
    ))

    story.append(h2('Error Code Reference'))
    story.append(table([
        ['Error Code', 'Severity', 'Trigger', 'Action', 'Operator Alert'],
        ['BCE_DIGITS_OUT_OF_RANGE', 'HARD', 'digits ∉ {2,3,4,5}', 'Block symbol · kill switch', 'P1 PagerDuty'],
        ['BCE_POINT_DIGITS_MISMATCH', 'HARD', 'point ≠ 10^(-digits)', 'Block symbol', 'P1 PagerDuty'],
        ['BCE_TICK_VALUE_DEVIATION', 'WARN', '|tick_value − computed| / tick_value > 5%', 'Use broker-reported · WARN flag', 'Log only'],
        ['BCE_TICK_VALUE_MISSING', 'SOFT', 'tick_value = 0 or NaN', 'Fallback: tick_size × price', 'P2 email'],
        ['BCE_TICK_SIZE_MISSING', 'SOFT', 'tick_size = 0', 'Fallback: point value', 'P2 email'],
        ['BCE_CONTRACT_SIZE_INVALID', 'SOFT', 'cs ∉ [1, 1M]', 'Fallback: 100,000', 'P2 email'],
        ['BCE_LEVERAGE_OUT_OF_RANGE', 'SOFT', 'lever ∉ [1, 3000]', 'Fallback: 30', 'P2 email'],
        ['BCE_PROFILE_DEVIATION', 'WARN', 'deviation from known broker > 10%', 'Use detected · log', 'Log only'],
        ['BCE_SPREAD_NEGATIVE', 'HARD', 'spread < 0 in any sample', 'Block symbol', 'P1 PagerDuty'],
        ['BCE_SPREAD_SAMPLE_INSUFFICIENT', 'SOFT', 'samples < 100', 'Fallback: VARIABLE', 'Log only'],
        ['BCE_BROKER_UNIDENTIFIED', 'WARN', 'no regex match', 'Use GENERIC profile', 'Log only'],
        ['BCE_PROBE_TIMEOUT', 'SOFT', 'symbol_info_tick() > 5s', 'Retry 3× · fall back to cache', 'P2 email'],
        ['BCE_PROBE_DISCONNECTED', 'HARD', 'MT5 not connected', 'Block all detection', 'P1 PagerDuty'],
        ['BCE_CACHE_EXPIRED', 'INFO', 'TTL exceeded', 'Trigger re-detection', 'None'],
        ['BCE_COMMISSION_MISCLASSIFIED', 'WARN', 'classification uncertain', 'Use detected · log reasoning', 'Log only'],
        ['BCE_SWAP_MODE_UNKNOWN', 'WARN', 'swap_mode not in known set', 'Use NONE · log', 'Log only'],
    ], col_widths=[40, 12, 30, 36, 22]))
    story.append(Spacer(1, 8))

    story.append(h2('Error Propagation'))
    story.append(p(
        'Errors propagate through the system in three channels. First, the BrokerProfile carries a '
        '<font name="DejaVuSans">validation_summary</font> field with the highest severity and the '
        'list of error codes — this allows downstream services to inspect the confidence level of '
        'the profile and apply additional constraints if needed. Second, the ErrorHandler emits '
        'alerts via PagerDuty (HARD), email (SOFT), or structured log entries (WARN, INFO) — this '
        'is the operator-facing channel. Third, every error event is written to the immutable audit '
        'log with the full detection context, allowing post-incident forensic analysis.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # Chapter 9 — Test Cases
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Test Cases', 9))
    story.append(p(
        'The BCE is covered by a five-layer test pyramid: unit tests (per-detector and per-validator '
        'with mocked probes), integration tests (Pact contracts between layers), broker profile tests '
        '(golden-value tests against known profiles for each of the six supported brokers), regression '
        'tests (replay of 100+ captured broker sessions), and live broker tests (weekly paper-trade '
        'probes against each broker). The complete pyramid and per-property coverage matrix are shown '
        'in Figure 9.1.'
    ))
    story.append(diagram('d06_test_pyramid.png', width_mm=170))
    story.append(caption('Figure 9.1 — Test pyramid (5 layers) with per-property coverage matrix, plus broker profile reference table.'))

    story.append(h2('Unit Test Cases'))
    story.append(p(
        'Unit tests cover pure functions and isolated components with all dependencies mocked. The '
        'IBrokerProbe interface is mocked to return controlled symbol_info and account_info payloads, '
        'allowing each detector and validator to be tested in isolation against a wide range of inputs. '
        'Property-based tests (via hypothesis) are used for invariants — e.g., for any digits d in '
        '{2,3,4,5}, DigitsDetector.detect(probe_with_digits(d)) returns d, and the derived pip_value '
        'equals point × (10 if d in {3,5} else 1).'
    ))
    story.append(h3('Sample Unit Test Cases — DigitsDetector'))
    story.append(table([
        ['Test ID', 'Input', 'Expected Output', 'Severity'],
        ['UT-DIG-001', 'digits=2, point=0.01', 'PropertyResult(2, OK)', 'PASS'],
        ['UT-DIG-002', 'digits=3, point=0.001', 'PropertyResult(3, OK)', 'PASS'],
        ['UT-DIG-003', 'digits=4, point=0.0001', 'PropertyResult(4, OK)', 'PASS'],
        ['UT-DIG-004', 'digits=5, point=0.00001', 'PropertyResult(5, OK)', 'PASS'],
        ['UT-DIG-005', 'digits=1', 'HARD: BCE_DIGITS_OUT_OF_RANGE', 'FAIL-HARD'],
        ['UT-DIG-006', 'digits=6', 'HARD: BCE_DIGITS_OUT_OF_RANGE', 'FAIL-HARD'],
        ['UT-DIG-007', 'digits=5, point=0.001', 'HARD: BCE_POINT_DIGITS_MISMATCH', 'FAIL-HARD'],
        ['UT-DIG-008', 'digits=2, point=0.0001', 'HARD: BCE_POINT_DIGITS_MISMATCH', 'FAIL-HARD'],
        ['UT-DIG-009', 'digits=0 (missing)', 'HARD: BCE_DIGITS_OUT_OF_RANGE', 'FAIL-HARD'],
        ['UT-DIG-010', 'digits=null (NaN)', 'HARD: BCE_PROBE_TIMEOUT after 3 retries', 'FAIL-HARD'],
    ], col_widths=[16, 36, 70, 18]))
    story.append(Spacer(1, 8))

    story.append(h3('Sample Unit Test Cases — SpreadTypeDetector'))
    story.append(table([
        ['Test ID', 'Input (1000 ticks)', 'Expected Output', 'Severity'],
        ['UT-SPR-001', 'spread stddev/mean = 0.02', 'FIXED · μ, σ reported', 'PASS'],
        ['UT-SPR-002', 'spread stddev/mean = 0.10', 'VARIABLE · μ, σ reported', 'PASS'],
        ['UT-SPR-003', 'all spreads = 0.30 (constant)', 'FIXED · μ=0.30, σ=0', 'PASS'],
        ['UT-SPR-004', 'one spread = -0.01 (negative)', 'HARD: BCE_SPREAD_NEGATIVE', 'FAIL-HARD'],
        ['UT-SPR-005', 'only 50 ticks sampled (market closed)', 'SOFT: BCE_SPREAD_SAMPLE_INSUFFICIENT · fallback VARIABLE', 'FAIL-SOFT'],
        ['UT-SPR-006', 'all spreads = 0', 'FIXED · μ=0, σ=0 (zero-spread account)', 'PASS'],
        ['UT-SPR-007', 'spread stddev/mean = 0.049', 'FIXED (boundary)', 'PASS'],
        ['UT-SPR-008', 'spread stddev/mean = 0.051', 'VARIABLE (boundary)', 'PASS'],
    ], col_widths=[16, 36, 70, 18]))
    story.append(Spacer(1, 8))

    story.append(h3('Sample Unit Test Cases — CrossPropertyValidator'))
    story.append(table([
        ['Test ID', 'Input', 'Expected Output', 'Severity'],
        ['UT-XVAL-001', 'tick_value ≈ tick_size × cs × price (dev 1%)', 'PASS (no errors)', 'PASS'],
        ['UT-XVAL-002', 'tick_value deviates 7%', 'WARN: BCE_TICK_VALUE_DEVIATION', 'WARN'],
        ['UT-XVAL-003', 'tick_value deviates 30%', 'SOFT: BCE_TICK_VALUE_DEVIATION + fallback', 'FAIL-SOFT'],
        ['UT-XVAL-004', 'tick_value = 0', 'SOFT: BCE_TICK_VALUE_MISSING + computed fallback', 'FAIL-SOFT'],
        ['UT-XVAL-005', 'leverage = 5000', 'SOFT: BCE_LEVERAGE_OUT_OF_RANGE + fallback 30', 'FAIL-SOFT'],
        ['UT-XVAL-006', 'leverage = 0', 'SOFT: BCE_LEVERAGE_OUT_OF_RANGE + fallback 30', 'FAIL-SOFT'],
        ['UT-XVAL-007', 'contract_size = 0', 'SOFT: BCE_CONTRACT_SIZE_INVALID + fallback 100000', 'FAIL-SOFT'],
        ['UT-XVAL-008', 'all properties valid', 'PASS (no errors)', 'PASS'],
    ], col_widths=[18, 42, 64, 16]))
    story.append(Spacer(1, 8))

    story.append(h2('Broker Profile Tests (Golden Values)'))
    story.append(p(
        'Each of the six supported brokers has a golden-value test that exercises the full detection '
        'pipeline against a recorded MT5 session for that broker. The test verifies that the detected '
        'BrokerProfile matches the expected golden values for that broker\'s standard account type. '
        'These tests run nightly and on every PR that touches BCE code. A failure indicates either '
        'a broker specification change (which requires a profile library update) or a BCE regression '
        '(which requires code investigation).'
    ))
    story.append(h3('Golden Value Test — IC Markets Raw Spread (XAUUSD)'))
    story.append(table([
        ['Property', 'Expected Golden Value', 'Tolerance'],
        ['broker_id', 'IC_MARKETS', 'exact match'],
        ['digits', '5', 'exact match'],
        ['point', '0.00001', 'exact match'],
        ['contract_size', '100000', 'exact match'],
        ['tick_size', '0.00001', 'exact match'],
        ['tick_value', '≈ tick_size × price (dev < 1%)', '5% deviation'],
        ['leverage', '500 (international) / 30 (EU)', 'exact match (per jurisdiction)'],
        ['spread_type', 'VARIABLE', 'exact match'],
        ['commission_type', 'PER_MILLION', 'exact match'],
        ['commission_rate', '$3.50 per $1M', '10% deviation'],
        ['swap_type', 'POINTS', 'exact match'],
        ['account_type', 'RAW', 'exact match'],
    ], col_widths=[30, 50, 50]))
    story.append(Spacer(1, 8))

    story.append(h2('Regression Test Cases (Replay)'))
    story.append(p(
        'The regression test suite replays 100+ captured broker sessions (recorded via the MT5 '
        'bridge\'s pcap feature) through the BCE and verifies that the detected profile matches the '
        'profile detected at capture time. This catches regressions introduced by code changes — if '
        'a refactor causes the BCE to produce a different profile for the same input, the regression '
        'test fails. The replay library includes sessions from all six supported brokers, all four '
        'account types, and edge cases (low liquidity, news events, broker maintenance windows).'
    ))

    story.append(h2('Live Broker Test Cases'))
    story.append(p(
        'Weekly live broker tests connect to each of the six supported brokers with a paper-trading '
        'or small-balance account, run the full detection sequence, and verify that the detected '
        'profile is reasonable. These tests catch broker-side changes that the golden-value tests '
        '(which use recorded sessions) cannot. The tests run automatically every Sunday at 22:00 UTC '
        '(market open) and report results to the engineering Slack channel. A failure triggers an '
        'investigation — either the broker has changed something (requires profile library update) '
        'or the BCE has a bug.'
    ))

    story.append(h2('Test Coverage Summary'))
    story.append(table([
        ['Test Layer', 'Test Count', 'Coverage Target', 'CI Gate'],
        ['Unit (per-detector, per-validator)', '157', '85% line · 100% critical paths', 'Every PR'],
        ['Integration (Pact contracts)', '57', '100% critical paths', 'Every PR'],
        ['Broker profile (golden values)', '66', '6 brokers × 11 properties', 'Nightly + PR'],
        ['Regression (replay)', '100+', 'All captured sessions', 'Nightly'],
        ['Live broker', '72', '6 brokers × 12 properties', 'Weekly (Sun 22:00 UTC)'],
        ['Total', '450+', '—', '—'],
    ], col_widths=[40, 20, 50, 30]))
    story.append(Spacer(1, 8))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # Chapter 10 — Class Diagram & Integration
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Class Diagram & TITAN Core Integration', 10))
    story.append(p(
        'The BCE exposes three primary interfaces to the rest of the system: '
        '<font name="DejaVuSans">IBrokerProbe</font> (the broker abstraction, implemented by '
        'MT5Probe and future FIX/IB probes), <font name="DejaVuSans">IDetector</font> (the detector '
        'contract, implemented by ten concrete detectors), and <font name="DejaVuSans">IValidator</font> '
        '(the validator contract, implemented by three concrete validators). The orchestrator is '
        'the <font name="DejaVuSans">BrokerCompatEngine</font> class, which holds references to the '
        'probe, the detector array, the validator array, the profile library, and the cache.'
    ))
    story.append(diagram('d05_class_integration.png', width_mm=170))
    story.append(caption('Figure 10.1 — UML class diagram of the BCE (top) and integration with TITAN Core components (bottom).'))

    story.append(h2('Primary Classes'))
    story.append(h3('IBrokerProbe (interface)'))
    story.append(p(
        'The broker abstraction. Exposes five methods: <font name="DejaVuSans">symbol_info()</font>, '
        '<font name="DejaVuSans">account_info()</font>, <font name="DejaVuSans">sample_ticks(n)</font>, '
        '<font name="DejaVuSans">server_name()</font>, and <font name="DejaVuSans">is_connected()</font>. '
        'The current implementation is MT5Probe (which wraps the MetaTrader5 Python package and is '
        'invoked from C++ via PyO3). Future implementations will include FIXProbe (for FIX-protocol '
        'brokers) and IBProbe (for Interactive Brokers).'
    ))

    story.append(h3('BrokerProfile (value object)'))
    story.append(p(
        'The immutable output of the BCE. Contains the nine detected properties plus broker_id '
        '(fingerprint), account_type, detected_at (timestamp), and validation_summary (highest '
        'severity + error code list). The class is hashable and FlatBuffer-serializable for cache '
        'storage and event bus publication. The class exposes derived properties: '
        '<font name="DejaVuSans">pip_value()</font> (point × 10 for 3/5 digits, else point), '
        '<font name="DejaVuSans">contract_value(price)</font> (contract_size × price), and '
        '<font name="DejaVuSans">tick_value_per_lot()</font> (tick_value × contract_size).'
    ))

    story.append(h3('BrokerCompatEngine (orchestrator)'))
    story.append(p(
        'The main entry point. Exposes three public methods: '
        '<font name="DejaVuSans">detect_profile(symbol)</font> (full detection sequence, returns '
        'BrokerProfile), <font name="DejaVuSans">get_profile(symbol)</font> (cache lookup, returns '
        'BrokerProfile or triggers detection on miss), and <font name="DejaVuSans">invalidate(symbol)</font> '
        '(forces re-detection on next call). The engine is a singleton per TITAN process and is '
        'thread-safe via internal locking.'
    ))

    story.append(h2('Integration with TITAN Core'))
    story.append(p(
        'The BCE integrates with four TITAN Core components. The <b>risk gate</b> subscribes to '
        '<font name="DejaVuSans">bce.profile.ready</font> events and uses the BrokerProfile for '
        'position sizing (it needs contract_size and tick_value to compute notional exposure). '
        'The <b>order manager</b> queries <font name="DejaVuSans">get_profile(symbol)</font> '
        'synchronously before placing each order, using contract_size and tick_size for order '
        'parameter validation. The <b>strategy coordinator</b> uses account_type for strategy '
        'selection (some strategies are disabled on cent accounts due to position sizing '
        'constraints). The <b>operator console</b> can call <font name="DejaVuSans">invalidate(symbol)</font> '
        'to force re-detection after broker maintenance or suspected configuration drift.'
    ))
    story.append(p(
        'The integration is loosely coupled via the event bus. The BCE has no direct dependency on '
        'the risk gate, order manager, or strategy coordinator — they subscribe to BCE events, not '
        'the reverse. This allows the BCE to be deployed, upgraded, and tested independently of the '
        'consumers of its output.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # Chapter 11 — API Specification
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('API Specification', 11))
    story.append(p(
        'This chapter specifies the public API of the BCE. All APIs are stable across v1.x releases; '
        'breaking changes require v2.0 and a migration plan for licensees. The API is exposed in '
        'both C++ (for hot-path callers like the order manager) and Python (for cold-path callers '
        'like the operator console).'
    ))

    story.append(h2('C++ API — BrokerCompatEngine'))
    story.append(code("""// C++ public API (include/titan/bce/BrokerCompatEngine.h)

namespace titan::bce {

class BrokerCompatEngine {
public:
    // Singleton accessor
    static BrokerCompatEngine& instance();

    // Synchronous: returns cached profile or triggers detection on miss.
    // Throws BCEException on HARD error (caller must catch and handle).
    BrokerProfile get_profile(const std::string& symbol) const;

    // Force re-detection (invalidates cache). Returns new profile.
    // Used by operator console after broker maintenance.
    BrokerProfile detect_profile(const std::string& symbol);

    // Invalidate cache entry without re-detecting.
    // Next get_profile() call will trigger detection.
    void invalidate(const std::string& symbol);

    // Subscribe to profile events (called by Risk Gate, Order Manager, etc.)
    // Callback is invoked on ZMQ thread; must be non-blocking.
    using ProfileCallback = std::function<void(const BrokerProfile&)>;
    void on_profile_ready(ProfileCallback cb);
    void on_profile_changed(ProfileCallback cb);
};

} // namespace titan::bce"""))

    story.append(h2('C++ API — BrokerProfile'))
    story.append(code("""// C++ value object (include/titan/bce/BrokerProfile.h)

namespace titan::bce {

class BrokerProfile {
public:
    // Identity
    std::string symbol;
    BrokerID broker_id;          // EXNESS, IC_MARKETS, ..., GENERIC
    AccountType account_type;    // CENT, MICRO, DOLLAR, RAW
    uint64_t detected_at;        // unix nanos

    // 9 detected properties
    int digits;                  // {2, 3, 4, 5}
    Decimal point;               // 10^(-digits)
    Decimal contract_size;       // typically 100, 10000, or 100000
    Decimal tick_size;           // min price increment
    Decimal tick_value;          // monetary value per tick per lot
    int leverage;                // 1 to 3000, or 0 for UNLIMITED
    SpreadType spread_type;      // FIXED, VARIABLE
    CommissionType commission_type; // NONE, PER_LOT, PER_MILLION, PCT
    Decimal commission_rate;     // raw rate (units depend on type)
    SwapType swap_type;          // NONE, POINTS, PCT
    Decimal swap_long;
    Decimal swap_short;

    // Validation summary
    Severity highest_severity;   // OK, WARN, SOFT, HARD
    std::vector<ErrorCode> errors;

    // Derived (computed at call time, never stored)
    Decimal pip_value() const;            // point × 10 if 3/5 digits
    Decimal contract_value(Decimal price) const;
    Decimal tick_value_per_lot() const;
    Decimal commission_per_lot(Decimal price) const;
    bool is_safe() const { return highest_severity < Severity::HARD; }

    // Serialization
    flatbuffers::Offset<bce::fb::BrokerProfile> serialize(flatbuffers::FlatBufferBuilder&) const;
    static BrokerProfile deserialize(const bce::fb::BrokerProfile*);
};

} // namespace titan::bce"""))

    story.append(h2('Python API — Operator Console'))
    story.append(code("""# Python API (python/titan/bce/__init__.py)

from titan.bce import BrokerCompatEngine, BrokerProfile, Severity

engine = BrokerCompatEngine.instance()

# Get current profile (cached)
profile = engine.get_profile('XAUUSD')
print(f"Broker: {profile.broker_id}")
print(f"Digits: {profile.digits}")
print(f"Contract size: {profile.contract_size}")
print(f"Pip value: {profile.pip_value()}")
print(f"Safe to trade: {profile.is_safe()}")

# Force re-detection (operator action)
new_profile = engine.detect_profile('XAUUSD')
if new_profile.highest_severity == Severity.HARD:
    print(f"HARD error: {new_profile.errors}")

# Subscribe to events
def on_ready(p: BrokerProfile):
    print(f"Profile ready for {p.symbol}")
engine.on_profile_ready(on_ready)"""))

    story.append(h2('Event Bus Contract'))
    story.append(p(
        'The BCE publishes two events on the async event bus. Both use FlatBuffer serialization '
        'and are published on the <font name="DejaVuSans">bce.*</font> topic prefix.'
    ))
    story.append(table([
        ['Event', 'Topic', 'Payload', 'Subscribers'],
        ['Profile Ready', 'bce.profile.ready', 'BrokerProfile (FlatBuffer)', 'Risk Gate, Order Manager, Strategy Coordinator'],
        ['Profile Changed', 'bce.profile.changed', 'BrokerProfile (new) + BrokerProfile (old)', 'Risk Gate (recomputes exposure)'],
        ['Error', 'bce.error.{severity}', 'ErrorEvent (code, context, timestamp)', 'Operator Alert Gateway, Audit Logger'],
    ], col_widths=[20, 24, 38, 38]))
    story.append(Spacer(1, 8))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # Chapter 12 — Implementation Notes
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Implementation Notes', 12))
    story.append(p(
        'This chapter captures design decisions and implementation considerations that did not fit '
        'naturally into the preceding chapters. These notes are informative, not normative — they '
        'explain why certain choices were made, but they do not add new requirements.'
    ))

    story.append(h2('Why C++ for Detection, Python for Cache and Audit'))
    story.append(p(
        'The detection layer is implemented in C++ because it runs on every MT5 connection event '
        '(potentially hundreds of times per session, including reconnections and symbol rolls) and '
        'must complete within tens of milliseconds to avoid blocking the order manager. The cache '
        '(Redis client) and audit logger are implemented in Python because they perform I/O-bound '
        'work where the GIL is released during system calls, and because they integrate more '
        'naturally with the existing Python observability stack (structlog, prometheus_client). '
        'The C++ detection layer communicates with the Python cache/audit layer via PyO3, with '
        'FlatBuffers as the wire format.'
    ))

    story.append(h2('Why Redis for Cache, Not In-Process Memory'))
    story.append(p(
        'The cache is in Redis rather than in-process memory for two reasons. First, the BCE runs '
        'in both the titan-core (C++) and titan-strategy (Python) processes, and both need to '
        'access the same cached profiles — Redis provides cross-process sharing. Second, on '
        'failover from Z1 to Z2, the new primary can immediately use the cached profiles from '
        'Redis (which is replicated from Z1 to Z2), avoiding the full detection sequence during '
        'failover. The cache TTL is 24 hours, balancing freshness against detection overhead.'
    ))

    story.append(h2('Why 1000 Ticks for Spread Sampling'))
    story.append(p(
        'The SpreadTypeDetector samples 1000 ticks for its stddev calculation. This number is '
        'calibrated to provide a stable stddev estimate within 20 seconds of normal market activity '
        '(XAUUSD typically sees 50-100 ticks per second during liquid hours). Fewer than 100 ticks '
        'produces an unstable estimate (the detector falls back to VARIABLE with a SOFT warning); '
        'more than 5000 ticks adds latency without meaningfully improving the estimate. The 1000-tick '
        'sample is also large enough to span at least one minor liquidity cycle, making the '
        'FIXED/VARIABLE classification robust to short-term spread fluctuations.'
    ))

    story.append(h2('Why 5% Tolerance for Tick Value Cross-Check'))
    story.append(p(
        'The tick value cross-check tolerates 5% deviation between broker-reported and computed '
        'values. This tolerance accounts for two sources of legitimate deviation: (1) the current '
        'price used in the computation may differ slightly from the price the broker used to '
        'compute tick_value (the broker updates tick_value periodically, not on every tick); '
        'and (2) some brokers compute tick_value using a slightly different formula (e.g., '
        'rounding the contract size before multiplication). Deviations above 5% but below 25% '
        'are WARN — the broker-reported value is used; deviations above 25% are SOFT — the '
        'computed value is used as a fallback. The 5% threshold was calibrated against the six '
        'supported brokers and is reviewed quarterly.'
    ))

    story.append(h2('Future Extensions'))
    story.append(p(
        'The BCE is designed to be extensible. Planned extensions for v1.1 and beyond include:'
    ))
    story.append(bullet('<b>FIX broker support</b>: A new FIXProbe implementing IBrokerProbe, allowing the BCE to work with FIX-protocol brokers (e.g., LMAX, Currenex) in addition to MT5.'))
    story.append(bullet('<b>Multi-symbol detection</b>: Currently the BCE detects profiles one symbol at a time. For multi-symbol strategies, batch detection would reduce total latency.'))
    story.append(bullet('<b>Profile drift monitoring</b>: A background job that periodically re-detects profiles and compares to cached values, alerting on any drift. Currently this is on-demand only.'))
    story.append(bullet('<b>Broker-specific quirks database</b>: A more granular database of broker-specific quirks (e.g., "Exness reports leverage as 0 for unlimited, not -1") to improve detection accuracy.'))
    story.append(bullet('<b>ML-based broker identification</b>: Replace the regex-based fingerprinter with a classifier that uses all detected properties (not just server name) to identify the broker with higher confidence.'))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # Appendix A — Broker Profile Reference
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Appendix A — Broker Profile Reference', 13))
    story.append(p(
        'This appendix documents the known-good profiles for each of the six supported brokers. '
        'These profiles are encoded in the BrokerProfileLibrary and used by the '
        'ProfileConsistencyValidator for deviation checking. The values reflect the broker '
        'configurations as of June 2026; brokers occasionally change their specifications, and '
        'the library should be reviewed quarterly.'
    ))

    story.append(h2('A.1 Exness'))
    story.append(table([
        ['Property', 'Cent Account', 'Standard Account', 'Raw Spread Account'],
        ['digits', '2', '2', '5'],
        ['point', '0.01', '0.01', '0.00001'],
        ['contract_size', '100', '100000', '100000'],
        ['tick_size', '0.01', '0.01', '0.00001'],
        ['leverage', '0 (UNLIMITED)', '0 (UNLIMITED)', '0 (UNLIMITED)'],
        ['spread_type', 'VARIABLE', 'VARIABLE', 'VARIABLE'],
        ['commission_type', 'NONE', 'NONE', 'PER_MILLION'],
        ['commission_rate', '0', '0', '~$3.50/$1M (varies)'],
        ['swap_type', 'NONE (swap-free)', 'NONE (swap-free)', 'NONE (swap-free)'],
        ['account_type', 'CENT', 'DOLLAR', 'RAW'],
    ], col_widths=[30, 30, 30, 30]))
    story.append(Spacer(1, 8))

    story.append(h2('A.2 IC Markets'))
    story.append(table([
        ['Property', 'Standard Account', 'Raw Spread Account'],
        ['digits', '2', '5'],
        ['point', '0.01', '0.00001'],
        ['contract_size', '100000', '100000'],
        ['tick_size', '0.01', '0.00001'],
        ['leverage', '500 (intl) / 30 (EU/UK)', '500 (intl) / 30 (EU/UK)'],
        ['spread_type', 'VARIABLE', 'VARIABLE'],
        ['commission_type', 'NONE', 'PER_MILLION'],
        ['commission_rate', '0', '$3.50/$1M'],
        ['swap_type', 'POINTS', 'POINTS'],
        ['account_type', 'DOLLAR', 'RAW'],
    ], col_widths=[30, 40, 40]))
    story.append(Spacer(1, 8))

    story.append(h2('A.3 Pepperstone'))
    story.append(table([
        ['Property', 'Standard Account', 'Razor Account'],
        ['digits', '2', '5'],
        ['point', '0.01', '0.00001'],
        ['contract_size', '100000', '100000'],
        ['tick_size', '0.01', '0.00001'],
        ['leverage', '500 (intl) / 30 (AU/UK)', '500 (intl) / 30 (AU/UK)'],
        ['spread_type', 'VARIABLE', 'VARIABLE'],
        ['commission_type', 'NONE', 'PER_MILLION'],
        ['commission_rate', '0', '$3.50/$1M'],
        ['swap_type', 'POINTS', 'POINTS'],
        ['account_type', 'DOLLAR', 'RAW'],
    ], col_widths=[30, 40, 40]))
    story.append(Spacer(1, 8))

    story.append(h2('A.4 Tickmill'))
    story.append(table([
        ['Property', 'Classic Account', 'Pro Account', 'VIP Account'],
        ['digits', '2', '5', '5'],
        ['point', '0.01', '0.00001', '0.00001'],
        ['contract_size', '100000', '100000', '100000'],
        ['tick_size', '0.01', '0.00001', '0.00001'],
        ['leverage', '500', '500', '500'],
        ['spread_type', 'VARIABLE', 'VARIABLE', 'VARIABLE'],
        ['commission_type', 'NONE', 'NONE', 'PER_MILLION'],
        ['commission_rate', '0', '0', '$2.00/$1M'],
        ['swap_type', 'POINTS', 'POINTS', 'POINTS'],
        ['account_type', 'DOLLAR', 'DOLLAR', 'RAW'],
    ], col_widths=[30, 26, 26, 28]))
    story.append(Spacer(1, 8))

    story.append(h2('A.5 FP Markets'))
    story.append(table([
        ['Property', 'Standard Account', 'Raw Account'],
        ['digits', '2', '5'],
        ['point', '0.01', '0.00001'],
        ['contract_size', '100000', '100000'],
        ['tick_size', '0.01', '0.00001'],
        ['leverage', '500 (intl) / 30 (EU)', '500 (intl) / 30 (EU)'],
        ['spread_type', 'VARIABLE', 'VARIABLE'],
        ['commission_type', 'NONE', 'PER_MILLION'],
        ['commission_rate', '0', '$3.00/$1M'],
        ['swap_type', 'POINTS', 'POINTS'],
        ['account_type', 'DOLLAR', 'RAW'],
    ], col_widths=[30, 40, 40]))
    story.append(Spacer(1, 8))

    story.append(h2('A.6 Fusion Markets'))
    story.append(table([
        ['Property', 'Standard Account', 'Zero Account'],
        ['digits', '2', '5'],
        ['point', '0.01', '0.00001'],
        ['contract_size', '100000', '100000'],
        ['tick_size', '0.01', '0.00001'],
        ['leverage', '500 (intl) / 30 (AU)', '500 (intl) / 30 (AU)'],
        ['spread_type', 'VARIABLE', 'VARIABLE'],
        ['commission_type', 'NONE', 'PER_MILLION'],
        ['commission_rate', '0', '$2.25/$1M'],
        ['swap_type', 'POINTS', 'POINTS'],
        ['account_type', 'DOLLAR', 'RAW'],
    ], col_widths=[30, 40, 40]))
    story.append(Spacer(1, 8))

    story.append(h2('A.7 GENERIC (Fallback)'))
    story.append(p(
        'When the BrokerFingerprinter cannot match the server name against any of the six supported '
        'brokers, the engine classifies the broker as GENERIC. In this case, the BrokerProfileLibrary '
        'has no template to compare against, and the ProfileConsistencyValidator is skipped. The '
        'detected properties are used as-is, with the BCE\'s validation relying entirely on the '
        'CrossPropertyValidator and SanityBoundsValidator. The GENERIC classification is recorded '
        'in the audit log so operators can identify unsupported brokers and consider adding them to '
        'the fingerprint library.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # Appendix B — Sample Detection Output
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Appendix B — Sample Detection Output', 14))
    story.append(p(
        'This appendix shows the BrokerProfile output for three representative detection scenarios: '
        'a successful detection on IC Markets Raw Spread, a SOFT-error detection on a broker with '
        'missing tick_value, and a HARD-error detection on a broker with malformed digits. The '
        'outputs are shown in JSON form for readability; in production, profiles are serialized '
        'as FlatBuffers for performance.'
    ))

    story.append(h2('B.1 Successful Detection — IC Markets Raw Spread'))
    story.append(code("""{
  "symbol": "XAUUSD",
  "broker_id": "IC_MARKETS",
  "account_type": "RAW",
  "detected_at": 1718798400000000000,

  "digits": 5,
  "point": 0.00001,
  "contract_size": 100000,
  "tick_size": 0.00001,
  "tick_value": 1.0,
  "leverage": 500,
  "spread_type": "VARIABLE",
  "spread_mean": 0.00018,
  "spread_stddev": 0.00004,
  "commission_type": "PER_MILLION",
  "commission_rate": 3.50,
  "swap_type": "POINTS",
  "swap_long": -2.18,
  "swap_short": -0.42,

  "validation_summary": {
    "highest_severity": "OK",
    "errors": [],
    "warnings": []
  },

  "derived": {
    "pip_value": 0.0001,
    "contract_value_at_1950": 195000.0,
    "tick_value_per_lot": 1.0,
    "commission_per_lot_at_1950": 6.825
  }
}"""))

    story.append(h2('B.2 SOFT Error Detection — Missing tick_value'))
    story.append(code("""{
  "symbol": "XAUUSD",
  "broker_id": "GENERIC",
  "account_type": "DOLLAR",
  "detected_at": 1718798400000000000,

  "digits": 2,
  "point": 0.01,
  "contract_size": 100000,
  "tick_size": 0.01,
  "tick_value": 19.50,
  "leverage": 100,
  "spread_type": "VARIABLE",
  "spread_mean": 0.32,
  "spread_stddev": 0.08,
  "commission_type": "NONE",
  "commission_rate": 0.0,
  "swap_type": "POINTS",
  "swap_long": -4.5,
  "swap_short": -1.2,

  "validation_summary": {
    "highest_severity": "SOFT",
    "errors": [
      {
        "code": "BCE_TICK_VALUE_MISSING",
        "severity": "SOFT",
        "context": {
          "broker_reported": 0.0,
          "fallback_used": "tick_size * price",
          "computed_value": 19.50,
          "price_at_detection": 1950.0
        }
      }
    ],
    "warnings": [
      {
        "code": "BCE_BROKER_UNIDENTIFIED",
        "severity": "WARN",
        "context": {
          "server_name": "UnknownBroker-Real",
          "regex_matched": null
        }
      }
    ]
  },

  "derived": {
    "pip_value": 0.01,
    "contract_value_at_1950": 195000000.0,
    "tick_value_per_lot": 19.50,
    "commission_per_lot_at_1950": 0.0
  }
}"""))

    story.append(h2('B.3 HARD Error Detection — Malformed Digits'))
    story.append(code("""{
  "symbol": "XAUUSD",
  "broker_id": "GENERIC",
  "account_type": null,
  "detected_at": 1718798400000000000,

  "digits": 6,
  "point": 0.000001,
  "contract_size": null,
  "tick_size": null,
  "tick_value": null,
  "leverage": null,
  "spread_type": null,
  "commission_type": null,
  "commission_rate": null,
  "swap_type": null,
  "swap_long": null,
  "swap_short": null,

  "validation_summary": {
    "highest_severity": "HARD",
    "errors": [
      {
        "code": "BCE_DIGITS_OUT_OF_RANGE",
        "severity": "HARD",
        "context": {
          "digits": 6,
          "valid_range": [2, 5]
        }
      }
    ],
    "warnings": []
  },

  "action_taken": {
    "symbol_blocked": true,
    "kill_switch_engaged": true,
    "operator_alert": "P1 PagerDuty",
    "audit_log_entry_id": "audit_2026_06_19_084500_001"
  },

  "derived": {}
}"""))

    story.append(p(
        'These three examples illustrate the full range of BCE behavior: successful detection with '
        'no errors, SOFT-error detection with safe-default fallback, and HARD-error detection with '
        'trading blocked. In all three cases, the BrokerProfile is published on the event bus and '
        'recorded in the audit log; downstream services are responsible for inspecting the '
        '<font name="DejaVuSans">validation_summary.highest_severity</font> field and acting '
        'appropriately (the risk gate and order manager refuse to operate on profiles with HARD '
        'severity).'
    ))

    return story


# ════════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    output_path = '/home/z/my-project/scripts/broker_engine/body.pdf'

    doc = TocDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=24*mm, bottomMargin=22*mm,
        title='TITAN XAU AI — Broker Compatibility Engine',
        author='TITAN Quant Research',
        subject='Broker Compatibility Engine architecture for runtime broker property detection',
        creator='TITAN Architecture Workbench',
    )

    story = build_story()
    print(f'[build] Building body PDF with {len(story)} flowables...')
    doc.multiBuild(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(f'[build] Body PDF written: {output_path}')

    from pypdf import PdfReader
    r = PdfReader(output_path)
    print(f'[build] Page count: {len(r.pages)}')

if __name__ == '__main__':
    main()
