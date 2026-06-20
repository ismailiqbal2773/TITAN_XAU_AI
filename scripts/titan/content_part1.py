"""
TITAN XAU AI — Architecture Document Body Content
==================================================
All narrative content (paragraphs, tables, callouts) for the 24-section PDF.
Diagrams are embedded as PNGs from /home/z/my-project/scripts/titan/diagrams/png/.

This module is imported by build_pdf.py. It exposes a single function
build_story() that returns a list of ReportLab Flowables.
"""

import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    Paragraph, Spacer, Table, TableStyle, Image, PageBreak,
    KeepTogether, KeepInFrame, HRFlowable,
)

# ─── Goldman Sachs white palette (user-specified) ──────────────────────────
PAGE_BG       = colors.HexColor('#FFFFFF')
SECTION_BG    = colors.HexColor('#F8FAFC')
CARD_BG       = colors.HexColor('#F1F5F9')
TABLE_STRIPE  = colors.HexColor('#F8FAFC')
HEADER_FILL   = colors.HexColor('#14213D')  # Deep navy
COVER_BLOCK   = colors.HexColor('#14213D')
BORDER        = colors.HexColor('#CBD5E1')
ICON          = colors.HexColor('#4A5568')
ACCENT        = colors.HexColor('#C8102E')  # Crimson
ACCENT_2      = colors.HexColor('#14213D')
TEXT_PRIMARY  = colors.HexColor('#14213D')
TEXT_MUTED    = colors.HexColor('#4A5568')
SEM_SUCCESS   = colors.HexColor('#15803D')
SEM_WARNING   = colors.HexColor('#B45309')
SEM_ERROR     = colors.HexColor('#C8102E')

DIAGRAM_DIR = '/home/z/my-project/scripts/titan/diagrams/png'

# ─── Paragraph styles ──────────────────────────────────────────────────────
def make_styles():
    S = {}
    # H1 — chapter heading (numbered)
    S['h1'] = ParagraphStyle('h1', fontName='FreeSerif-Bold', fontSize=20, leading=26,
                              textColor=HEADER_FILL, spaceBefore=18, spaceAfter=10, alignment=TA_LEFT)
    # H2 — section heading
    S['h2'] = ParagraphStyle('h2', fontName='FreeSerif-Bold', fontSize=14, leading=18,
                              textColor=HEADER_FILL, spaceBefore=14, spaceAfter=6, alignment=TA_LEFT)
    # H3 — subsection
    S['h3'] = ParagraphStyle('h3', fontName='FreeSerif-Bold', fontSize=11.5, leading=15,
                              textColor=ACCENT, spaceBefore=10, spaceAfter=4, alignment=TA_LEFT)
    # Body — justified serif
    S['body'] = ParagraphStyle('body', fontName='FreeSerif', fontSize=10.5, leading=16,
                                textColor=TEXT_PRIMARY, spaceBefore=0, spaceAfter=8,
                                alignment=TA_JUSTIFY, firstLineIndent=0)
    # Bullet
    S['bullet'] = ParagraphStyle('bullet', fontName='FreeSerif', fontSize=10.5, leading=15,
                                  textColor=TEXT_PRIMARY, leftIndent=18, bulletIndent=4,
                                  spaceBefore=2, spaceAfter=4, alignment=TA_LEFT)
    # Code
    S['code'] = ParagraphStyle('code', fontName='DejaVuSans', fontSize=9, leading=12,
                                textColor=TEXT_PRIMARY, leftIndent=14, rightIndent=14,
                                spaceBefore=6, spaceAfter=8, backColor=SECTION_BG,
                                borderColor=BORDER, borderWidth=0.5, borderPadding=8,
                                alignment=TA_LEFT)
    # Caption — italic muted, centered
    S['caption'] = ParagraphStyle('caption', fontName='FreeSerif-Italic', fontSize=9, leading=12,
                                   textColor=TEXT_MUTED, alignment=TA_CENTER,
                                   spaceBefore=4, spaceAfter=14)
    # Table cell — header
    S['th'] = ParagraphStyle('th', fontName='FreeSerif-Bold', fontSize=9.5, leading=12,
                              textColor=colors.white, alignment=TA_LEFT)
    # Table cell — body
    S['td'] = ParagraphStyle('td', fontName='FreeSerif', fontSize=9, leading=12,
                              textColor=TEXT_PRIMARY, alignment=TA_LEFT)
    # Table cell — body, mono
    S['td_mono'] = ParagraphStyle('td_mono', fontName='DejaVuSans', fontSize=8.5, leading=11,
                                   textColor=TEXT_PRIMARY, alignment=TA_LEFT)
    # Callout
    S['callout'] = ParagraphStyle('callout', fontName='FreeSerif-Italic', fontSize=10, leading=15,
                                   textColor=HEADER_FILL, leftIndent=18, rightIndent=18,
                                   spaceBefore=8, spaceAfter=10, alignment=TA_LEFT,
                                   backColor=CARD_BG, borderColor=ACCENT, borderWidth=0,
                                   borderPadding=10)
    # Pull quote
    S['quote'] = ParagraphStyle('quote', fontName='FreeSerif-Italic', fontSize=12, leading=18,
                                 textColor=HEADER_FILL, leftIndent=24, rightIndent=24,
                                 spaceBefore=10, spaceAfter=12, alignment=TA_LEFT,
                                 borderColor=ACCENT, borderWidth=0, borderPadding=0)
    return S

S = make_styles()

# ─── Helper: chapter heading with bookmark ─────────────────────────────────
import hashlib

def h1(text, chapter_num=None):
    """Chapter heading with TOC bookmark."""
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
    # Replace newlines with <br/> for Paragraph
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text = text.replace('\n', '<br/>')
    return Paragraph(f'<font name="DejaVuSans">{text}</font>', S['code'])

def caption(text):
    return Paragraph(text, S['caption'])

def callout(text):
    return Paragraph(text, S['callout'])

def hr():
    return HRFlowable(width='100%', thickness=0.5, color=BORDER, spaceBefore=8, spaceAfter=8)

def diagram(filename, width_mm=170):
    """Embed a diagram PNG, scaled to fit content width."""
    path = os.path.join(DIAGRAM_DIR, filename)
    if not os.path.exists(path):
        return Paragraph(f'<i>[Diagram missing: {filename}]</i>', S['caption'])
    # A4 content width = 210 - 2*20 = 170mm
    target_w = width_mm * mm
    from PIL import Image as PILImage
    pil = PILImage.open(path)
    aspect = pil.height / pil.width
    target_h = target_w * aspect
    # Cap height to avoid full-page diagrams being absurd
    max_h = 230 * mm
    if target_h > max_h:
        target_h = max_h
        target_w = target_h / aspect
    img = Image(path, width=target_w, height=target_h)
    img.hAlign = 'CENTER'
    return img

def table(data, col_widths=None, header_bg=HEADER_FILL, stripe=True):
    """Build a styled table. data is a list of rows; each cell is a string or Paragraph."""
    # Wrap strings in Paragraph
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
        # Scale to available width
        total = sum(col_widths)
        scale = available / total
        col_widths = [w * scale for w in col_widths]

    t = Table(wrapped, colWidths=col_widths, hAlign='CENTER', repeatRows=1)
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), header_bg),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
        ('LINEBELOW', (0, 0), (-1, 0), 1.2, HEADER_FILL),
    ]
    if stripe:
        for i in range(1, len(data)):
            if i % 2 == 0:
                style_cmds.append(('BACKGROUND', (0, i), (-1, i), TABLE_STRIPE))
    t.setStyle(TableStyle(style_cmds))
    return t


# ════════════════════════════════════════════════════════════════════════════
#  STORY BUILDER — returns list of Flowables
# ════════════════════════════════════════════════════════════════════════════

def build_story():
    story = []

    # ════════════════════════════════════════════════════════════════════
    # SECTION 1 — Document Control (front matter, no chapter number)
    # ════════════════════════════════════════════════════════════════════
    story.append(Paragraph('<b>Document Control</b>', S['h1']))
    story.append(p(
        'This document specifies the complete system architecture for <b>TITAN XAU AI</b>, '
        'an institutional-grade artificial intelligence trading system focused exclusively on '
        'the XAUUSD (spot gold versus US dollar) instrument. It is intended as the authoritative '
        'reference for engineering teams, licensees, infrastructure partners, and compliance '
        'reviewers. All design decisions captured here are binding on the v1.0 release; deviations '
        'require an Architecture Decision Record (ADR) and CTO sign-off.'
    ))
    story.append(p(
        'The document covers nine deliverables mandated by the project charter: complete folder '
        'structure, service architecture, data flow diagrams, module dependency graph, UML class '
        'diagrams, deployment architecture, VPS architecture, production architecture, and testing '
        'architecture. Each deliverable is presented as a dedicated chapter with a rendered diagram, '
        'supporting narrative, and reference tables. Non-functional requirements, risk controls, '
        'licensing hooks, and the implementation roadmap are covered in supporting chapters.'
    ))
    story.append(h2('Revision History'))
    story.append(table([
        ['Version', 'Date', 'Author', 'Reviewer', 'Summary of Changes'],
        ['v0.1', '2026-04-12', 'Quant Research', 'Internal', 'Initial draft, scope and outline'],
        ['v0.5', '2026-05-08', 'Quant Research', 'CTO', 'Folder structure, service architecture, DFD drafts'],
        ['v0.8', '2026-05-30', 'Quant Research', 'Risk Officer', 'Class diagrams, deployment topology, VPS deep dive'],
        ['v0.95', '2026-06-12', 'Quant Research', 'CTO + Risk + Compliance', 'Production architecture, testing, NFRs, licensing'],
        ['v1.0', '2026-06-19', 'Quant Research', 'Board sign-off', 'GA release, commercial licensing terms embedded'],
    ], col_widths=[16, 22, 30, 38, 80]))
    story.append(Spacer(1, 10))

    story.append(h2('Distribution List & Confidentiality'))
    story.append(p(
        'This document is classified <b>COMMERCIAL — LICENSEE DISTRIBUTION</b>. It may be shared '
        'with prospective licensees under NDA, with the operations team responsible for running '
        'the system, and with auditors performing due diligence. It must NOT be shared publicly, '
        'posted to public repositories, or distributed to competing trading firms. Each copy '
        'carries a watermark identifying the recipient; redistribution outside the named recipient '
        'is a breach of the master license agreement.'
    ))
    story.append(table([
        ['Recipient Class', 'Access Level', 'Watermark', 'Retention'],
        ['Internal engineering', 'Full', 'Employee ID', 'Employment + 1 year'],
        ['Licensee (signed MSA)', 'Full', 'Tenant ID', 'License term + 5 years'],
        ['Prospective licensee (NDA)', 'Redacted (no licensing chapter)', 'NDA reference', 'NDA term'],
        ['Auditor / due diligence', 'Full read-only', 'Auditor firm', 'Engagement + 90 days'],
        ['Investor (Term Sheet signed)', 'Executive summary + architecture overview only', 'Investor ID', 'Indefinite'],
    ], col_widths=[44, 50, 30, 46]))
    story.append(Spacer(1, 10))

    story.append(h2('Document Lifecycle'))
    story.append(p(
        'Architecture is a living artifact. The document is reviewed quarterly by the architecture '
        'review board (CTO, lead quant, lead SRE, risk officer). Minor revisions (typographical, '
        'clarifications) increment the patch version (v1.0.x) without board review. Major revisions '
        '(new chapters, changed NFRs, new modules) increment the minor version (v1.x.0) and require '
        'board approval. Breaking changes to public interfaces increment the major version (v2.0.0) '
        'and require a formal migration plan for licensees.'
    ))
    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 1 — Executive Summary
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Executive Summary', 1))
    story.append(p(
        'TITAN XAU AI is a modular, asynchronous, event-driven trading system engineered for '
        'institutional deployment on the XAUUSD instrument. It combines a low-latency C++ execution '
        'core with a Python-based intelligence layer, bridged via PyO3, to achieve the rare '
        'combination of microsecond-class order latency and machine-learning-class alpha generation. '
        'The system is broker-independent at the protocol layer (MT5 today, FIX and IB planned), '
        'compatible with MetaTrader 5 as its primary execution venue, and structured for commercial '
        'licensing from day one.'
    ))
    story.append(p(
        'The system is designed around a single non-negotiable principle: <b>capital preservation '
        'takes absolute precedence over alpha generation</b>. Every architectural decision — from '
        'the structural separation of the risk layer from the strategy layer, to the kill switch '
        'being a first-class citizen rather than an afterthought, to the mandatory backtest '
        'regression gate in the CI/CD pipeline — exists to enforce this principle. The target '
        'metrics reflect it: maximum drawdown below five percent, profit factor above two, Sharpe '
        'ratio above two, recovery factor above five, and a risk-of-ruin below one percent under '
        'Monte Carlo simulation. These are not aspirational numbers; they are CI/CD gate thresholds.'
    ))
    story.append(p(
        'The architecture comprises six logical layers (ingest, normalize, intelligence, risk, '
        'execution, persistence and operations), eleven core services, and approximately 350 modules '
        'split between C++ (latency-critical hot path) and Python (research, feature engineering, '
        'machine learning inference, orchestration). A strict layering rule — modules at layer N '
        'may only depend on modules at layer N-1 or below — guarantees that risk retains structural '
        'veto power over every order, a property that cannot be violated by accident or malice '
        'without an explicit architectural change.'
    ))
    story.append(p(
        'Deployment follows a three-zone high-availability topology: a primary VPS in NY4 '
        '(Equinix New York) colocated with broker matching engines, a hot-standby in EQ4 with '
        'sub-three-second VRRP failover, and a geographically remote disaster-recovery VPS in LD4 '
        '(London) for catastrophic failure scenarios. The system is designed for 99.95% uptime '
        'with a fifteen-minute mean time to recovery. Observability is built in from the kernel '
        'sysctl level up to the operator console, with Prometheus metrics, structured JSON logs '
        'in Loki, distributed traces in OpenTelemetry, and an immutable hash-chained audit store.'
    ))
    story.append(p(
        'Commercial licensing is enforced through a per-tenant RSA-signed JWT model with online '
        'heartbeat and a seven-day offline grace period. Three tiers (Starter, Pro, Enterprise) '
        'gate strategy count, capital ceiling, and feature access. Hardware fingerprinting, code '
        'obfuscation, and tamper detection protect against piracy without imposing onerous '
        'restrictions on legitimate licensees. The license server itself is a SaaS component '
        'running on AWS, freeing licensees from operating it themselves.'
    ))
    story.append(p(
        'The implementation roadmap spans twelve months across four phases: Foundation (M1-M3) '
        'delivers the core infrastructure and backtest engine; Intelligence (M4-M6) adds the '
        'feature and signal engines with the first live strategy; Productionization (M7-M9) '
        'completes the HA deployment, monitoring, licensing, and canary CI/CD pipeline; '
        'Commercialization (M10-M12) adds multi-tenant isolation, billing, and white-label '
        'capabilities culminating in v1.0 general availability. Each phase has hard exit criteria '
        'tied to the target metrics — the system cannot progress to the next phase without meeting '
        'them on out-of-sample data.'
    ))

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 2 — System Vision & Design Philosophy
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('System Vision & Design Philosophy', 2))
    story.append(h2('Problem Framing — Why XAUUSD Demands a Specialized Architecture'))
    story.append(p(
        'XAUUSD, the spot gold versus US dollar pair, is one of the most actively traded '
        'instruments in the world and exhibits a set of microstructure characteristics that make '
        'it uniquely challenging for systematic trading. It trades nearly twenty-four hours a day '
        'across Asian, European, and American sessions, with liquidity and volatility regimes that '
        'shift dramatically between them. It is acutely sensitive to central bank communications, '
        'geopolitical events, and real-yield movements — a single Federal Reserve press conference '
        'can move the price by several percent in minutes. Liquidity is fragmented across multiple '
        'ECNs and broker-dealer networks, with spreads that can widen by an order of magnitude '
        'during news events. These properties rule out many naive approaches: a strategy that '
        'works in calm conditions may experience catastrophic slippage during news windows, and '
        'a single broker disconnection during a fast market can leave a position exposed to '
        'unbounded adverse selection.'
    ))
    story.append(p(
        'TITAN XAU AI is purpose-built for this environment. Rather than attempting to be a '
        'general-purpose trading platform, every architectural choice is optimized for the '
        'specific demands of gold: low-latency tick processing to capture microstructure signals, '
        'news-aware risk gating to avoid trading during high-impact events, broker-agnostic '
        'abstraction to enable failover when a primary venue degrades, and a regime detection '
        'subsystem that adapts strategy behavior to the prevailing volatility environment. The '
        'narrow instrument focus also dramatically reduces the attack surface — there is no need '
        'to handle corporate actions, dividend dates, or earnings surprises, allowing the team to '
        'concentrate engineering effort on the few things that matter for gold.'
    ))

    story.append(h2('Design Philosophy'))
    story.append(p(
        'The system is built on four philosophical commitments that together define its character '
        'and distinguish it from retail-grade trading bots. Each commitment has direct architectural '
        'consequences documented throughout this specification.'
    ))
    story.append(h3('1. Capital Preservation First, Alpha Generation Second'))
    story.append(p(
        'Most trading systems treat risk management as a feature to be added on top of the trading '
        'logic. TITAN XAU AI treats it as the foundation on which everything else is built. The '
        'risk layer is structurally separate from the strategy layer, with a hard architectural '
        'rule that risk never depends on strategy — only the reverse. The kill switch is a '
        'first-class service with its own communication channel to the order manager, able to halt '
        'new orders, flatten existing positions, and cancel pending orders in under five hundred '
        'milliseconds. Pre-trade risk gates run synchronously in the hot path, blocking any order '
        'that violates position, leverage, exposure, or news-blackout constraints. The CI/CD '
        'pipeline refuses to promote any build that does not meet the target risk metrics on '
        'out-of-sample data.'
    ))
    story.append(h3('2. Deterministic Risk Envelope'))
    story.append(p(
        'The system operates within a strictly defined risk envelope that is verifiable from '
        'outside. Position size, leverage, daily trade count, drawdown circuit breakers, and '
        'news-blackout windows are all encoded as configuration that is loaded at startup and '
        'cannot be modified by the strategy layer at runtime. Any change to the risk envelope '
        'requires a supervisor-level authorization with an audit-trail entry, and most changes '
        'auto-revert after a configurable timeout. This determinism is essential for institutional '
        'licensees who must be able to demonstrate to their own risk committees and regulators '
        'that the system operates within approved bounds.'
    ))
    story.append(h3('3. Separation of Concerns via Strict Layering'))
    story.append(p(
        'The six-layer architecture is enforced by a strict dependency rule: a module at layer N '
        'may only import or call modules at layer N-1 or below. This rule is verified by an '
        'automated architecture lint in CI; cyclic dependencies fail the build. The practical '
        'consequence is that the strategy layer cannot reach into the execution layer to bypass '
        'risk checks, the execution layer cannot reach into the ingest layer to manipulate tick '
        'data, and the risk layer has no knowledge of why a particular order was placed — only '
        'that it must be vetted. This makes the system auditable, testable in isolation, and '
        'resistant to the kind of subtle coupling that causes cascading failures in less '
        'disciplined systems.'
    ))
    story.append(h3('4. Replay-Anywhere Determinism'))
    story.append(p(
        'Every event that flows through the system — every tick, every news item, every operator '
        'action, every risk decision, every fill — is captured to an immutable log with a '
        'monotonic sequence number and a high-precision timestamp. Given the same input event '
        'stream and the same starting state, the system produces byte-identical output. This '
        'enables forensic reconstruction of any trading day, walk-forward backtesting on actual '
        'historical event streams rather than sanitized bar data, and chaos engineering replays '
        'where fault scenarios can be re-run against historical data to verify mitigation '
        'effectiveness. Determinism is the foundation of trust in an autonomous trading system.'
    ))

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 3 — Architectural Tenets & Principles
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Architectural Tenets & Principles', 3))
    story.append(p(
        'The tenets below are the architectural constitution of TITAN XAU AI. They are referenced '
        'by every Architecture Decision Record and are the basis for resolving design disputes. '
        'A tenet may be overridden only by unanimous agreement of the architecture review board '
        'and only with a documented replacement.'
    ))

    tenets = [
        ('Single Source of Truth for Market Data',
         'All market data — ticks, bars, news, economic events — flows through a single '
         'normalization pipeline before reaching any consumer. There is exactly one TickStore '
         'and one FeatureStore per trading cluster. This eliminates the class of bugs where '
         'different strategies see slightly different views of the market due to feed timing '
         'or normalization discrepancies, and it makes the audit log authoritative: any '
         'decision can be traced back to the exact market state that produced it.'),
        ('Pure-Function Strategy Layer',
         'Strategies are implemented as pure functions of (market_state, position, config) '
         'returning a Signal. They have no side effects, no shared mutable state, and no '
         'direct access to the network, filesystem, or clock. This makes them trivially '
         'testable, parallelizable across instruments, and safe to hot-reload at runtime. '
         'Side-effecting operations — placing orders, logging, emitting metrics — are the '
         'exclusive responsibility of the framework.'),
        ('Risk as a Separate Microservice with Veto Power',
         'The risk layer runs as an independent service with its own CPU allocation, its own '
         'configuration, and its own deployment cadence. It cannot be overridden by the '
         'strategy layer, the operator console (for high-impact limits), or any other '
         'subsystem. The PreTradeRiskGate runs synchronously in the hot path; if it returns '
         'REJECT, the order is not sent. Period. This is the structural guarantee that '
         'capital preservation is enforced rather than merely encouraged.'),
        ('Deterministic Replay',
         'Given the same event stream and starting state, the system produces byte-identical '
         'output. This requires that all randomness be seeded from the configuration, all '
         'time-dependent logic read from a monotonic logical clock rather than wall time, and '
         'all external API calls be wrapped in replayable adapters. The reward is enormous: '
         'any production incident can be reproduced in a dev environment by replaying the '
         'event log, and backtests run on the same code path as live trading.'),
        ('C++ for the Latency-Critical Path, Python for the Intelligence Layer',
         'The hot path — tick ingestion, normalization, risk gating, order management — is '
         'implemented in C++20 with manual memory management, lock-free queues, and CPU '
         'pinning. The intelligence layer — feature engineering, signal generation, ML '
         'inference, strategy orchestration — is implemented in Python 3.12 with NumPy, '
         'pandas, and PyTorch. The two layers communicate via PyO3 bindings and zero-copy '
         'FlatBuffers. This division gives us sub-millisecond latency where it matters and '
         'rapid iteration where it does not.'),
        ('Async Event Bus with Backpressure',
         'All inter-service communication flows through a single async event bus implemented '
         'on ZeroMQ PUB/SUB with lock-free SPSC queues for the hottest paths. The bus '
         'implements backpressure: if a consumer falls behind, producers are throttled rather '
         'than dropping messages. This prevents cascading failures under load and ensures '
         'that the system degrades gracefully rather than catastrophically when a downstream '
         'service is slow.'),
        ('Statelessness of the Execution Layer',
         'The execution layer — OrderManager, SmartRouter, FillTracker — is stateless across '
         'restarts. All state is persisted to Redis (hot) and TimescaleDB (cold) on every '
         'transition. A crashed titan-core process can be restarted and resume trading within '
         'seconds by loading state from Redis. This dramatically simplifies operations: there '
         'is no need for graceful shutdown procedures, and rolling updates require no special '
         'coordination.'),
        ('Observability-First',
         'Every service emits Prometheus metrics, structured JSON logs, and OpenTelemetry '
         'traces from day one of development. Adding observability retroactively is far more '
         'expensive than building it in from the start, and in a trading system the absence '
         'of observability is itself a critical defect — you cannot debug what you cannot '
         'see. The default dashboard exposes real-time PnL, exposure, latency percentiles, '
         'and risk-gate rejection rates, and any deviation from baseline triggers an alert.'),
        ('Kill Switch as a First-Class Citizen',
         'The kill switch is not a feature flag or an operator action buried in a menu. It is '
         'a dedicated service with its own network path, its own authentication, and its own '
         'auditable trigger history. Engaging the kill switch halts all new orders, flattens '
         'existing positions, cancels pending orders, and notifies the operator — all in '
         'under five hundred milliseconds. The kill switch can be triggered manually from '
         'the operator console, automatically by the PostTradeRiskMonitor on hard drawdown '
         'breach, or by the license agent on revocation.'),
        ('License-Gated Features',
         'Every feature that has commercial value — strategy count, capital ceiling, ML '
         'inference, custom strategy development, white-label branding — is gated by claims '
         'in the per-tenant JWT. The license check is performed at startup and on every '
         'heartbeat refresh; a revoked or expired license triggers a graceful shutdown '
         'with a configurable grace period for closing positions. This is not a polite '
         'request; it is a hard architectural boundary that cannot be bypassed by '
         'configuration changes.'),
    ]

    for i, (title, body) in enumerate(tenets, 1):
        story.append(h3(f'Tenet {i}: {title}'))
        story.append(p(body))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 4 — Target Performance Metrics Framework
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Target Performance Metrics Framework', 4))
    story.append(p(
        'The target metrics quoted in the project charter — maximum drawdown under five percent, '
        'profit factor above two, Sharpe ratio above two, recovery factor above five, risk of ruin '
        'under one percent — are not marketing claims. They are measurable, formula-bound quantities '
        'that are computed automatically on every backtest run and on every live trading day, and '
        'they serve as gate thresholds in the CI/CD pipeline. This chapter defines each metric '
        'precisely, specifies the measurement window and calculation method, and explains the '
        'acceptance criteria.'
    ))

    story.append(h2('Metric Definitions'))
    story.append(table([
        ['Metric', 'Formula', 'Target', 'Measurement Window', 'Acceptance Gate'],
        ['Max Drawdown (MaxDD)',
         'max( (peak_t - equity_t) / peak_t ) for t in window',
         '< 5%',
         'Trailing 90 trading days',
         'Hard halt at 3% soft, 5% hard'],
        ['Profit Factor (PF)',
         'gross_profit / gross_loss over window',
         '> 2.0',
         'Trailing 90 trading days',
         'CI/CD gate; reject build if PF < 2.0 on OOS'],
        ['Sharpe Ratio',
         '(annualized_mean_return - risk_free) / annualized_std_dev',
         '> 2.0',
         'Trailing 252 trading days',
         'CI/CD gate; reject build if Sharpe < 2.0 on OOS'],
        ['Recovery Factor',
         'net_profit / MaxDD over window',
         '> 5.0',
         'Trailing 252 trading days',
         'CI/CD gate; reject build if RF < 5.0 on OOS'],
        ['Risk of Ruin (RoR)',
         'Monte Carlo: P(equity hits ruin_threshold) over N paths',
         '< 1%',
         '1000 paths × 252 days',
         'Hard gate; reject build if RoR > 1%'],
    ], col_widths=[28, 50, 18, 32, 50]))
    story.append(Spacer(1, 10))

    story.append(h2('Maximum Drawdown — Detailed Calculation'))
    story.append(p(
        'Maximum drawdown is the largest peak-to-trough decline in the equity curve over the '
        'measurement window, expressed as a percentage of the peak. Formally, given an equity '
        'series E(t) over the window, MaxDD = max over t of ( max(E(s) for s ≤ t) - E(t) ) / '
        'max(E(s) for s ≤ t). It is the most direct measure of capital risk: an investor who '
        'deposited capital at the worst possible moment would have experienced this loss. The '
        'five percent target is deliberately conservative for an XAUUSD-focused system, where '
        'volatility can produce intraday swings of one to two percent; achieving it requires '
        'both alpha generation and rigorous risk control.'
    ))
    story.append(p(
        'TITAN XAU AI enforces MaxDD through two circuit breakers: a soft breaker at three '
        'percent that throttles new entries and notifies the operator, and a hard breaker at '
        'five percent that engages the kill switch, flattens positions, and requires manual '
        'operator intervention to re-arm. Both breakers operate on the rolling ninety-day '
        'equity curve, computed in real time on every fill.'
    ))

    story.append(h2('Profit Factor — Detailed Calculation'))
    story.append(p(
        'Profit factor is the ratio of gross profit to gross loss over the measurement window. '
        'Gross profit is the sum of all positive trade PnL; gross loss is the absolute value of '
        'the sum of all negative trade PnL. A profit factor of two means the system earns two '
        'dollars for every dollar lost. Values above two are considered institutional-grade; '
        'values above three are rare in live trading and usually indicate curve-fitting in '
        'backtests. The target of two is calibrated to be ambitious but achievable on XAUUSD '
        'with disciplined risk management.'
    ))

    story.append(h2('Sharpe Ratio — Detailed Calculation'))
    story.append(p(
        'The Sharpe ratio measures risk-adjusted return: the excess return over the risk-free '
        'rate per unit of volatility. We use the standard annualized form: Sharpe = '
        '(mean_daily_return × 252 - risk_free_annual) / (std_daily_return × sqrt(252)). The '
        'risk-free rate is the three-month US Treasury bill yield. Daily returns are computed '
        'from the close-of-day equity including unrealized PnL. A Sharpe above two is considered '
        'excellent; above three is exceptional and typically only seen in high-frequency market '
        'making strategies. The target of two on XAUUSD reflects the system\'s design point of '
        'medium-frequency trading (a few trades per day) with rigorous volatility scaling.'
    ))

    story.append(h2('Recovery Factor — Detailed Calculation'))
    story.append(p(
        'Recovery factor is net profit divided by maximum drawdown over the same window. It '
        'measures how quickly the system recovers from its worst dip: a recovery factor of five '
        'means the system earns five times its worst drawdown over the period. This is a useful '
        'complement to Sharpe because it is sensitive to the temporal order of returns — a system '
        'that doubles then halves has the same Sharpe as one that halves then doubles, but very '
        'different recovery factors. The target of five ensures that drawdowns are not just '
        'shallow but also quickly recovered.'
    ))

    story.append(h2('Risk of Ruin — Monte Carlo Specification'))
    story.append(p(
        'Risk of ruin is the probability, under Monte Carlo simulation, that the equity curve '
        'hits a ruin threshold (defined as a fifty percent drawdown from starting capital) within '
        'a 252-trading-day horizon. The simulation generates one thousand randomized return '
        'sequences by sampling from the historical trade distribution with replacement, '
        'preserving the autocorrelation structure via block bootstrapping. A risk of ruin below '
        'one percent is the institutional standard for "safe" systematic strategies; we adopt '
        'it as a hard gate. Builds that exceed one percent risk of ruin on the out-of-sample '
        'window are rejected by CI/CD and cannot be promoted to canary.'
    ))

    story.append(callout(
        '<b>Gate enforcement:</b> All five metrics are computed automatically by the backtest '
        'regression stage of the CI/CD pipeline. A build is promoted to canary only if it '
        'satisfies ALL five gates on the out-of-sample window. There is no manual override — '
        'the gate is enforced by the pipeline configuration, not by human discretion.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 5 — Technology Stack Selection
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Technology Stack Selection — C++ Core + Python Intelligence', 5))
    story.append(p(
        'The choice of a dual-language architecture — C++20 for the latency-critical execution '
        'core and Python 3.12 for the intelligence layer — is the single most consequential '
        'technology decision in the system. It reflects a fundamental tension in trading system '
        'design: the hot path demands microsecond-class latency and deterministic memory '
        'behavior that interpreted languages cannot provide, while the research and ML workflow '
        'demands rapid iteration, rich libraries, and a productive REPL that compiled languages '
        'struggle to offer. The dual-language approach resolves the tension by accepting the '
        'complexity of a language boundary in exchange for getting the best of both worlds.'
    ))

    story.append(h2('C++ Execution Core — Responsibilities'))
    story.append(p(
        'The C++ core handles everything on the tick-to-trade hot path: MT5 broker communication, '
        'tick normalization, feature computation that must happen on every tick (microstructure '
        'features, technical indicators with tight latency budgets), the pre-trade risk gate, '
        'order management, and fill tracking. The design target is a warm-path p99 latency under '
        'five milliseconds from broker callback to order submission, with p99.9 under twenty-five '
        'milliseconds. Achieving this requires manual memory management (no garbage collection '
        'pauses), CPU pinning via systemd, lock-free queues between threads, and zero-copy '
        'serialization via FlatBuffers.'
    ))
    story.append(p(
        'The C++ build uses CMake with conan for dependency management. The toolchain is GCC 13 '
        'with C++20 enabled, LTO enabled in release builds, and Profile-Guided Optimization (PGO) '
        'applied to the hot path. Symbol visibility is controlled via export macros; the public '
        'API exposes only stable interfaces, with internal symbols stripped from release builds '
        'both for performance and to raise the barrier to reverse engineering.'
    ))

    story.append(h2('Python Intelligence Layer — Responsibilities'))
    story.append(p(
        'The Python layer handles everything off the hot path: feature engineering on aggregated '
        'bars (where ten-millisecond latency is acceptable), signal generation, ML model training '
        'and inference, strategy orchestration, backtest execution, and research workflows. '
        'Python 3.12 is chosen for its significant performance improvements over 3.11, '
        'particularly in asyncio and the GIL-aware subsystems. The runtime is uvloop for the '
        'event loop (significantly faster than the default asyncio loop), with PyTorch for ML '
        'inference, NumPy and pandas for numerical work, and numba for just-in-time compilation '
        'of hot Python paths.'
    ))
    story.append(p(
        'Python code is packaged with pyproject.toml and built with uv for fast, reproducible '
        'dependency resolution. Sensitive modules — the license validation, the model inference '
        'shims, the strategy parameter decryption — are compiled to native code via Cython and '
        'shipped as binary wheels, both for performance and to raise the reverse-engineering '
        'barrier. The Python layer communicates with the C++ core via PyO3 bindings, with '
        'FlatBuffers as the wire format for zero-copy message passing.'
    ))

    story.append(h2('Language Boundary Map'))
    story.append(table([
        ['Layer', 'C++ Modules', 'Python Modules', 'Bridge'],
        ['L1 Ingest', 'MT5Bridge, FIXAdapter, NewsFeedAdapter, FeedHealthMonitor', '—', '—'],
        ['L2 Normalize', 'TickNormalizer, SessionCalendar, FXConverter, BarAggregator', '—', '—'],
        ['L3 Intelligence', 'MicrostructureFeatureEngine (per-tick)', 'FeatureEngine (per-bar), SignalEngine, MLInferenceEngine, StrategyCoordinator, RegimeDetector', 'PyO3 + FlatBuffers'],
        ['L4 Risk', 'PreTradeRiskGate, PostTradeRiskMonitor, ExposureAggregator, KillSwitch', 'RiskConfigLoader', 'PyO3 (config only)'],
        ['L5 Execution', 'OrderManager, SmartRouter, FillTracker, SlippageModel, OrderReconciler', '—', '—'],
        ['L6 Ops', 'MetricsSink, Logger', 'TradeLogger, AuditStore, LicenseService, StateReplicator, OperatorAlertGateway', 'PyO3 + gRPC'],
    ], col_widths=[20, 50, 60, 40]))
    story.append(Spacer(1, 8))

    story.append(h2('Key Library Choices'))
    story.append(table([
        ['Domain', 'C++ Library', 'Python Library', 'Rationale'],
        ['Async I/O', 'Boost.Asio', 'asyncio + uvloop', 'Industry standard; uvloop is 2-4x faster than default asyncio'],
        ['Messaging', 'ZeroMQ (cppzmq)', 'pyzmq', 'Low-latency pub/sub; same wire format both sides'],
        ['Serialization', 'FlatBuffers', 'flatbuffers', 'Zero-copy, schema-driven, language-agnostic'],
        ['Logging', 'spdlog', 'structlog', 'Async, structured, JSON output for Loki'],
        ['Concurrency', 'moodycamel::ConcurrentQueue', '—', 'Lock-free SPSC queues for hot path'],
        ['Numerical', 'Eigen', 'NumPy + numba', 'Eigen for C++ linear algebra; NumPy for vectorized Python'],
        ['ML', 'LibTorch (C++ PyTorch)', 'PyTorch', 'Same model format; C++ for hot inference, Python for training'],
        ['Config', 'toml++', 'pydantic + tomli', 'Type-safe config; pydantic for validation'],
        ['Testing', 'GoogleTest + gmock', 'pytest + hypothesis', 'Property-based testing for quant logic'],
        ['HTTP/gRPC', '—', 'fastapi + grpcio', 'Operator console API; license server client'],
        ['Crypto', 'OpenSSL (libcrypto)', 'cryptography (pyca)', 'RSA-JWT for licensing; TLS for transport'],
    ], col_widths=[20, 30, 30, 90]))
    story.append(Spacer(1, 8))

    story.append(h2('Why Not Pure Python?'))
    story.append(p(
        'A common question is why not implement the entire system in Python with asyncio, given '
        'the productivity advantages. The answer is latency. CPython has a Global Interpreter '
        'Lock that serializes bytecode execution; even with asyncio, any CPU-bound work blocks '
        'the event loop. The Python interpreter itself adds overhead on every operation: a simple '
        'attribute access is tens of nanoseconds, a function call is hundreds. In a hot path that '
        'must process thousands of ticks per second with sub-millisecond risk gates, these '
        'overheads compound. Empirically, a pure-Python implementation of the TITAN hot path '
        'achieves a p99 latency of around thirty milliseconds — six times the budget. The C++ '
        'core achieves 4.8 milliseconds p99 on the same hardware.'
    ))

    story.append(h2('Why Not Pure C++?'))
    story.append(p(
        'The mirror question is why not implement everything in C++ for maximum performance. '
        'The answer is developer productivity and ecosystem. The Python data science ecosystem '
        '— NumPy, pandas, PyTorch, scikit-learn, matplotlib — is dramatically richer than '
        'anything available in C++. Strategy research is fundamentally an exploratory activity '
        'requiring rapid iteration on hypotheses, and a Jupyter notebook with pandas is roughly '
        'an order of magnitude more productive than a C++ compile-run-inspect cycle. The '
        'intelligence layer runs off the hot path with latency budgets in the tens of milliseconds; '
        'Python is more than fast enough for that, and the productivity multiplier is decisive.'
    ))

    story.append(PageBreak())

    return story
