"""
TITAN XAU AI — Meta AI CEO Supervisor (Module 18)
Body content + PDF builder.
"""
import os, sys, hashlib
sys.path.insert(0, '/home/z/my-project/skills/pdf/scripts')
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, HRFlowable, Image
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

FONT_DIR = '/usr/share/fonts'
pdfmetrics.registerFont(TTFont('FreeSerif', f'{FONT_DIR}/truetype/freefont/FreeSerif.ttf'))
pdfmetrics.registerFont(TTFont('FreeSerif-Bold', f'{FONT_DIR}/truetype/freefont/FreeSerifBold.ttf'))
pdfmetrics.registerFont(TTFont('FreeSerif-Italic', f'{FONT_DIR}/truetype/freefont/FreeSerifItalic.ttf'))
pdfmetrics.registerFont(TTFont('FreeSerif-BoldItalic', f'{FONT_DIR}/truetype/freefont/FreeSerifBoldItalic.ttf'))
pdfmetrics.registerFont(TTFont('DejaVuSans', f'{FONT_DIR}/truetype/dejavu/DejaVuSansMono.ttf'))
pdfmetrics.registerFont(TTFont('NotoSerifSC', f'{FONT_DIR}/truetype/noto-serif-sc/NotoSerifSC-Regular.ttf'))
pdfmetrics.registerFont(TTFont('NotoSerifSC-Bold', f'{FONT_DIR}/truetype/noto-serif-sc/NotoSerifSC-Bold.ttf'))
registerFontFamily('FreeSerif', normal='FreeSerif', bold='FreeSerif-Bold', italic='FreeSerif-Italic', boldItalic='FreeSerif-BoldItalic')
registerFontFamily('DejaVuSans', normal='DejaVuSans', bold='DejaVuSans')
registerFontFamily('NotoSerifSC', normal='NotoSerifSC', bold='NotoSerifSC-Bold')
try:
    from pdf import install_font_fallback; install_font_fallback()
except Exception: pass

HEADER_FILL = colors.HexColor('#14213D'); ACCENT = colors.HexColor('#C8102E')
TEXT_PRIMARY = colors.HexColor('#14213D'); TEXT_MUTED = colors.HexColor('#4A5568')
BORDER = colors.HexColor('#CBD5E1'); SECTION_BG = colors.HexColor('#F8FAFC')
TABLE_STRIPE = colors.HexColor('#F8FAFC')
DIAGRAM_DIR = '/home/z/my-project/scripts/ceo/diagrams/png'

S = {}
S['h1'] = ParagraphStyle('h1', fontName='FreeSerif-Bold', fontSize=20, leading=26, textColor=HEADER_FILL, spaceBefore=18, spaceAfter=10, alignment=TA_LEFT)
S['h2'] = ParagraphStyle('h2', fontName='FreeSerif-Bold', fontSize=14, leading=18, textColor=HEADER_FILL, spaceBefore=14, spaceAfter=6, alignment=TA_LEFT)
S['h3'] = ParagraphStyle('h3', fontName='FreeSerif-Bold', fontSize=11.5, leading=15, textColor=ACCENT, spaceBefore=10, spaceAfter=4, alignment=TA_LEFT)
S['body'] = ParagraphStyle('body', fontName='FreeSerif', fontSize=10.5, leading=16, textColor=TEXT_PRIMARY, spaceBefore=0, spaceAfter=8, alignment=TA_JUSTIFY)
S['bullet'] = ParagraphStyle('bullet', fontName='FreeSerif', fontSize=10.5, leading=15, textColor=TEXT_PRIMARY, leftIndent=18, bulletIndent=4, spaceBefore=2, spaceAfter=4, alignment=TA_LEFT)
S['code'] = ParagraphStyle('code', fontName='DejaVuSans', fontSize=8.5, leading=11, textColor=TEXT_PRIMARY, leftIndent=14, rightIndent=14, spaceBefore=6, spaceAfter=8, backColor=SECTION_BG, borderColor=BORDER, borderWidth=0.5, borderPadding=8, alignment=TA_LEFT)
S['caption'] = ParagraphStyle('caption', fontName='FreeSerif-Italic', fontSize=9, leading=12, textColor=TEXT_MUTED, alignment=TA_CENTER, spaceBefore=4, spaceAfter=14)
S['th'] = ParagraphStyle('th', fontName='FreeSerif-Bold', fontSize=9.5, leading=12, textColor=colors.white, alignment=TA_LEFT)
S['td'] = ParagraphStyle('td', fontName='FreeSerif', fontSize=9, leading=12, textColor=TEXT_PRIMARY, alignment=TA_LEFT)

def h1(text, n=None):
    d = f'Chapter {n} — {text}' if n else text
    k = f'h1_{hashlib.md5(d.encode()).hexdigest()[:8]}'
    p = Paragraph(f'<a name="{k}"/><b>{d}</b>', S['h1']); p.bookmark_name=k; p.bookmark_level=0; p.bookmark_text=d; p.bookmark_key=k; return p
def h2(t):
    k = f'h2_{hashlib.md5(t.encode()).hexdigest()[:8]}'
    p = Paragraph(f'<a name="{k}"/><b>{t}</b>', S['h2']); p.bookmark_name=k; p.bookmark_level=1; p.bookmark_text=t; p.bookmark_key=k; return p
def h3(t): return Paragraph(f'<b>{t}</b>', S['h3'])
def p(t): return Paragraph(t, S['body'])
def bullet(t): return Paragraph(f'• {t}', S['bullet'])
def code(t):
    t = t.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('\n','<br/>')
    return Paragraph(f'<font name="DejaVuSans">{t}</font>', S['code'])
def caption(t): return Paragraph(t, S['caption'])
def diagram(f, w=170):
    path = os.path.join(DIAGRAM_DIR, f)
    if not os.path.exists(path): return Paragraph(f'<i>[Missing: {f}]</i>', S['caption'])
    tw = w*mm; from PIL import Image as I; pil=I.open(path); a=pil.height/pil.width; th=tw*a
    mh=230*mm
    if th>mh: th=mh; tw=th/a
    img=Image(path, width=tw, height=th); img.hAlign='CENTER'; return img
def table(d, cw=None):
    w=[]
    for i,r in enumerate(d):
        wr=[]
        for c in r:
            if isinstance(c,str): wr.append(Paragraph(c, S['th'] if i==0 else S['td']))
            else: wr.append(c)
        w.append(wr)
    av=170*mm
    if cw is None: n=len(d[0]); cw=[av/n]*n
    else: t=sum(cw); s=av/t; cw=[x*s for x in cw]
    t=Table(w, colWidths=cw, hAlign='CENTER', repeatRows=1)
    sc=[('BACKGROUND',(0,0),(-1,0),HEADER_FILL),('TEXTCOLOR',(0,0),(-1,0),colors.white),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('GRID',(0,0),(-1,-1),0.4,BORDER),('LINEBELOW',(0,0),(-1,0),1.2,HEADER_FILL)]
    for i in range(1,len(d)):
        if i%2==0: sc.append(('BACKGROUND',(0,i),(-1,i),TABLE_STRIPE))
    t.setStyle(TableStyle(sc)); return t

class TocDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, f):
        if hasattr(f,'bookmark_name'):
            self.notify('TOCEntry', (getattr(f,'bookmark_level',0), getattr(f,'bookmark_text',''), self.page, getattr(f,'bookmark_key','')))

def hf(c, d):
    c.saveState(); pn=d.page
    if pn<=2: c.restoreState(); return
    c.setStrokeColor(HEADER_FILL); c.setLineWidth(0.6); c.line(20*mm, A4[1]-18*mm, A4[0]-20*mm, A4[1]-18*mm)
    c.setFont('FreeSerif-Italic',8.5); c.setFillColor(TEXT_MUTED); c.drawString(20*mm, A4[1]-14*mm, 'TITAN XAU AI — Meta AI CEO Supervisor')
    c.setFont('FreeSerif-Bold',8.5); c.setFillColor(ACCENT); c.drawRightString(A4[0]-20*mm, A4[1]-14*mm, 'v1.0  ·  GOVERNANCE')
    c.setStrokeColor(BORDER); c.setLineWidth(0.3); c.line(20*mm, 18*mm, A4[0]-20*mm, 18*mm)
    c.setFont('FreeSerif-Italic',8); c.setFillColor(TEXT_MUTED); c.drawString(20*mm, 12*mm, '© 2026 TITAN Quant Research  ·  Proprietary & Confidential')
    c.setFont('FreeSerif-Bold',9); c.setFillColor(HEADER_FILL); c.drawRightString(A4[0]-20*mm, 12*mm, f'{pn}')
    c.setFillColor(ACCENT); c.circle(A4[0]-25*mm, 14.5*mm, 1.0, fill=1, stroke=0); c.restoreState()

t1=ParagraphStyle('t1',fontName='FreeSerif-Bold',fontSize=11,leading=16,textColor=HEADER_FILL,leftIndent=0,spaceBefore=4)
t2=ParagraphStyle('t2',fontName='FreeSerif',fontSize=10,leading=14,textColor=colors.black,leftIndent=18,spaceBefore=1)

def build_story():
    s=[]
    s.append(Paragraph('<b>Table of Contents</b>', ParagraphStyle('tt',fontName='FreeSerif-Bold',fontSize=22,leading=28,textColor=HEADER_FILL,alignment=TA_LEFT,spaceAfter=18)))
    s.append(HRFlowable(width='100%', thickness=2, color=ACCENT, spaceBefore=0, spaceAfter=18))
    toc=TableOfContents(); toc.levelStyles=[t1,t2]; s.append(toc); s.append(PageBreak())

    # Ch 1 — Executive Summary
    s.append(h1('Executive Summary',1))
    s.append(p('The Meta AI CEO Supervisor (Module 18) is a governance layer that sits ABOVE the existing TITAN XAU AI trading system. It does NOT generate trading signals — its sole purpose is to <b>monitor, score, and govern</b> the models, execution, risk, brokers, and regime detection that constitute the trading pipeline. The CEO observes all model predictions (XGBoost, LSTM, Transformer, RL), trade outcomes, and system metrics in real-time, computes 6 composite health scores every 60 seconds, runs 8 statistical detectors to identify degradation/drift/overfitting/instability/execution-issues/broker-problems/regime-failures/latency-breaches, and takes 5 automated control actions: reduce model influence, increase model influence, disable failing model, trigger emergency risk reduction, trigger capital preservation mode.'))
    s.append(p('The CEO layer addresses a gap in the existing TITAN architecture: while the system has 5 validation frameworks (Backtest, Walk-Forward, Monte Carlo, Stress, Validator) that gate pre-deployment, there is no <b>runtime governance</b> layer that continuously monitors live performance and takes corrective action when models degrade, brokers fail, or regimes shift. The CEO fills this gap. It uses 4 rolling windows (50/100/250/500 trades) to provide multi-scale views — short-term sensitivity (50 trades) for acute detection, long-term stability (500 trades) for structural drift. The 8 detectors use only NumPy vectorized statistical operations (PSI, ratio comparisons, consecutive-loss counting, IS-OOS gap) — no GPU, no external LLM, no paid API. <b>Fully offline-capable: the CEO operates normally with zero outbound network.</b>'))
    s.append(p('The CEO\'s 6 health scores are: Model Health Score (per model, from Sharpe/Sortino/PF/WR/MDD/Recovery across 4 windows), Execution Quality Score (system-wide, from latency/slippage/fill-rate), Risk Score (inverted, from MDD/exposure/margin/risk-utilization), Broker Quality Score (per broker, from spread-dev/slippage-dev/fill-rate/reconnect), Regime Confidence Score (from vote-agreement/transition-conf/regime-strategy-perf), and Overall System Health (weighted aggregate, min-model-health weighted highest at 30%). Each score is 0-100 with GREEN (≥85) / YELLOW (70-84) / RED (<70) thresholds. The Overall System Health drives the system status: GREEN = live trading, YELLOW = reduced size + defensive, RED = halt + emergency flatten + 24h capital preservation.'))
    s.append(p('This document delivers everything required for implementation: architecture (8 layers), classes (16 Python classes), interfaces (5 ABCs), database schema (10 PostgreSQL tables with TimescaleDB hypertables), unit tests (80 tests), integration tests (45 tests), validator tests (20 tests), and deployment documentation (10-step guide). The CEO is designed to be a drop-in addition to the existing TITAN stack — it subscribes to existing NATS topics, writes to a new PostgreSQL database, and controls existing modules (ensemble voter, risk engine, execution engine) via well-defined interfaces. No existing module needs modification — the CEO observes via subscriptions and controls via interface calls.'))

    # Ch 2 — Architecture
    s.append(h1('Architecture Overview',2))
    s.append(p('The CEO is organized into 8 layers: Ingestion (subscribes to NATS), Rolling Windows (4 ring buffers per model per metric), Health Scoring (6 composite scores), Detection (8 statistical detectors), Decision (GREEN/YELLOW/RED status), Action (5 control actions), Persistence (PostgreSQL + Parquet), Reporting (Prometheus + Grafana + PagerDuty + Slack). Each layer is independent, testable, and horizontally scalable. The CEO runs as a single asyncio process with a 60-second cycle: ingest → update windows → compute scores → run detectors → decide status → execute actions → persist → report. Total cycle time: <100ms on a 4-vCPU VPS.'))
    s.append(diagram('d01_architecture.png',170))
    s.append(caption('Figure 2.1 — CEO architecture: 8 layers sitting above existing TITAN stack. CEO reads from below, writes control actions down.'))

    s.append(h2('4 Hard Constraints'))
    s.append(p('The CEO operates under 4 non-negotiable constraints: (1) <b>No paid APIs</b> — all inputs come from internal NATS topics, no external paid data sources. (2) <b>No external LLM dependency</b> — no OpenAI/Anthropic/any-LLM calls. All detection is statistical (NumPy). The CEO must operate even if all external AI services are down. (3) <b>CPU optimized</b> — NumPy vectorized operations, single-core <100ms per cycle, no GPU required. The CEO runs on the same 4-vCPU VPS as the trading core. (4) <b>Fully offline capable</b> — no outbound network required for core operation. Optional egress only for PagerDuty/Slack alerts, which degrade gracefully (queued locally, retried) if network is unavailable.'))

    s.append(PageBreak())

    # Ch 3 — Rolling Windows
    s.append(h1('Rolling Windows — 4 Sizes × 8 Metrics',3))
    s.append(p('The CEO maintains 4 rolling windows per model per metric: W50 (50 trades, ~1 week, acute/tactical), W100 (100 trades, ~2 weeks, confirmation), W250 (250 trades, ~1 month, strategic baseline), W500 (500 trades, ~2 months, structural). Each window is a bounded ring buffer (collections.deque with maxlen) — O(1) push, O(N) iteration, no unbounded growth. Total memory: 4 models × 8 metrics × 4 windows × max_size = 28,800 floats = ~230 KB. Negligible.'))
    s.append(diagram('d02_rolling_windows.png',170))
    s.append(caption('Figure 3.1 — 4 rolling windows (50/100/250/500) × 8 metrics (WR/PF/Sharpe/Sortino/MDD/Recovery/Latency/Slippage) × per model.'))

    s.append(h2('8 Tracked Metrics'))
    s.append(p('Each window tracks 8 metrics: Win Rate (wins/total), Profit Factor (gross_profit/gross_loss), Sharpe (mean(ret)/std(ret)×√252), Sortino (mean(ret)/std(neg_ret)×√252), Max Drawdown (max(peak-trough)/peak), Recovery Factor (net_profit/|MaxDD|), Latency (P99 signal-to-broker ms), Slippage (mean |fill-signal|). These 8 metrics cover the full performance surface: return (WR, PF), risk-adjusted return (Sharpe, Sortino), capital preservation (MDD, Recovery), and execution quality (Latency, Slippage). All are computed from the trade ledger and execution telemetry that the CEO ingests from NATS.'))

    s.append(h2('Window Roles'))
    s.append(table([
        ['Window', 'Role', 'Detector Use', 'Alert Sensitivity'],
        ['W50', 'Acute / Tactical', 'degradation, instability, broker issues', 'YELLOW trigger (sensitive)'],
        ['W100', 'Confirmation', 'drift confirmation, exec deterioration', 'YELLOW→RED trigger'],
        ['W250', 'Strategic Baseline', 'overfitting (vs IS), persistent drift', 'RED trigger (decisive)'],
        ['W500', 'Structural', 'structural change, regime transition', 'RED trigger + manual review'],
    ], cw=[10, 18, 40, 32]))
    s.append(Spacer(1, 8))

    s.append(PageBreak())

    # Ch 4 — Health Scores
    s.append(h1('6 Health Scores',4))
    s.append(p('The CEO computes 6 health scores every cycle. 5 are sub-scores (Model Health per model, Execution Quality system-wide, Risk system-wide, Broker Quality per broker, Regime Confidence system-wide), and 1 is the aggregate (Overall System Health). Each score is 0-100 with GREEN (≥85) / YELLOW (70-84) / RED (<70) thresholds. The Overall System Health is a weighted aggregate where <b>min(ModelHealth) is weighted highest at 30%</b> — a single failing model can drag down the overall score, because one degraded model in a 4-model ensemble is a systemic risk.'))
    s.append(diagram('d03_health_scores.png',170))
    s.append(caption('Figure 4.1 — 6 health scores with formulas, thresholds, and weighted aggregation.'))

    s.append(h2('Score Composition'))
    s.append(p('<b>Model Health Score (per model):</b> 0.25×Sharpe_norm + 0.20×Sortino_norm + 0.20×PF_norm + 0.15×WR_norm + 0.10×Recovery_norm + 0.10×(1-MDD_norm). Computed from W250 rolling window, normalized against the model\'s backtest baseline. Detects degradation, drift, overfitting, instability. <b>Execution Quality Score (EQS):</b> 0.30×(1-Latency_norm) + 0.30×(1-SlipP50_norm) + 0.20×(1-SlipP99_norm) + 0.20×FillRate. System-wide. Detects execution deterioration.'))
    s.append(p('<b>Risk Score (inverted, 100=safe):</b> 100 - (0.40×MDD_pct + 0.20×Exposure_pct + 0.20×(100-MarginLevel) + 0.20×RiskUtil). Lower MDD/exposure = higher score. Detects risk buildup before breach. <b>Broker Quality Score (BQS, per broker):</b> 0.25×(1-SpreadDev) + 0.25×(1-SlipDev) + 0.25×FillRate + 0.25×(1-ReconnectRate). Detects broker-specific issues. <b>Regime Confidence Score:</b> 0.40×VoteAgreement + 0.30×TransitionConf + 0.30×RegimeStrategyPerf. Detects regime ambiguity + regime-specific failures.'))
    s.append(p('<b>Overall System Health:</b> 0.30×min(ModelHealth) + 0.25×RiskScore + 0.20×EQS + 0.15×RegimeConf + 0.10×min(BQS). The min() operators ensure that the worst-performing model and worst-performing broker cap the overall score — a single failure cannot be masked by strong performance elsewhere.'))

    s.append(PageBreak())

    # Ch 5 — Detection Layer
    s.append(h1('Detection Layer — 8 Detectors',5))
    s.append(p('The CEO runs 8 statistical detectors every 60 seconds. All use only NumPy vectorized operations — no GPU, no external API, no LLM. Total CPU time per cycle: <100ms on a single core. The detectors are implemented as interchangeable IDetectionRule instances (Strategy pattern), registered with the DetectionEngine at startup. Each detector returns a DetectionEvent (with severity CRITICAL/MAJOR/MINOR) or None.'))
    s.append(diagram('d04_detectors.png',170))
    s.append(caption('Figure 5.1 — 8 detectors: degradation, drift, instability, overfitting, exec deterioration, broker issues, regime failures, latency.'))

    s.append(h2('8 Detectors'))
    s.append(bullet('<b>D1 Degradation:</b> W50 Sharpe < 0.7 × W250 Sharpe for 3 consecutive cycles. Action: reduce model influence 25%.'))
    s.append(bullet('<b>D2 Drift (PSI):</b> Population Stability Index > 0.25 on model input features (W250 vs baseline). Action: flag for retraining + reduce influence 15%.'))
    s.append(bullet('<b>D3 Instability:</b> 5+ consecutive losses OR prediction std > 2× baseline. Action: reduce influence 50%.'))
    s.append(bullet('<b>D4 Overfitting:</b> Live Sharpe < 0.5 × backtest Sharpe sustained over W250. Action: disable model (requires manual review).'))
    s.append(bullet('<b>D5 Execution Deterioration:</b> Latency P99 > 1.5× budget OR slippage P90 > 1.5× baseline for 2 consecutive cycles. Action: flag broker + reduce trade frequency.'))
    s.append(bullet('<b>D6 Broker Issues:</b> BQS < 70 for 5 consecutive cycles. Action: failover to backup broker.'))
    s.append(bullet('<b>D7 Regime Failures:</b> Per-regime win rate < 40% over W100 in current regime. Action: suppress entries in that regime.'))
    s.append(bullet('<b>D8 Latency:</b> P99 signal-to-broker > 150ms budget. Action: enable stale-signal veto + alert.'))

    s.append(PageBreak())

    # Ch 6 — Decision & Actions
    s.append(h1('Decision Layer &amp; Control Actions',6))
    s.append(p('The DecisionEngine aggregates the 6 health scores and 8 detector outputs into a single SystemStatus: GREEN (OverallHealth ≥ 85, all sub-scores ≥ 80, 0 critical detectors), YELLOW (OverallHealth 70-84, or any sub-score 70-79, or 1+ non-critical detector), RED (OverallHealth < 70, or RiskScore < 70, or any critical detector, or kill-switch triggered). The ActionEngine executes 5 control actions based on the status: reduce influence (YELLOW), increase influence (GREEN recovery), disable model (RED), emergency risk reduction (RED), capital preservation (sustained RED >30min).'))
    s.append(diagram('d05_decision_actions.png',170))
    s.append(caption('Figure 6.1 — 3-band status (GREEN/YELLOW/RED) → 5 control actions. Automated, audited, reversible (except emergency).'))

    s.append(h2('5 Control Actions'))
    s.append(p('<b>ACTION-1 Reduce Model Influence:</b> Downweight flagged model in ensemble voter by 25-50%. Reversible when score recovers. Triggered on YELLOW. <b>ACTION-2 Increase Model Influence:</b> Restore weight to design value after recovery. Staircase: 50%→75%→100% over 3 cycles. Triggered on GREEN after YELLOW. <b>ACTION-3 Disable Failing Model:</b> Hard-disable model in ensemble. Requires manual re-enable after review. Quorum check — if disabling would drop below 2/4 quorum, CEO escalates to RED instead. Triggered on RED. <b>ACTION-4 Emergency Risk Reduction:</b> Trigger risk engine emergency mode: flatten positions <500ms, halt new entries, 24h protective. Triggered on RED. <b>ACTION-5 Capital Preservation Mode:</b> Sustained RED >30min: flatten all + 24h no-trade. Resume only after manual sign-off. Triggered on sustained RED.'))

    s.append(PageBreak())

    # Ch 7 — Classes & Interfaces
    s.append(h1('Classes &amp; Interfaces',7))
    s.append(p('The CEO is implemented in Python 3.12 with full mypy --strict typing. 16 classes + 5 interfaces. Design patterns: Strategy (IDetectionRule — 8 interchangeable detectors), Observer (CEOSupervisor subscribes to NATS), Command (ControlAction — serializable), Facade (CEOSupervisor wraps 5 monitors + 3 engines), Repository (Database abstracts persistence), Factory (DetectionEngine creates detectors from config). Zero external LLM dependency — all detection is statistical (NumPy).'))
    s.append(diagram('d06_uml.png',170))
    s.append(caption('Figure 7.1 — UML class diagram: 16 classes + 5 interfaces. Fully typed (mypy --strict).'))

    s.append(h2('Core Class: CEOSupervisor (Python)'))
    s.append(code("""from __future__ import annotations
import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

class SystemStatus(Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    RED_PRESERVE = "RED_PRESERVE"

class ControlAction(Enum):
    REDUCE_INFLUENCE = "REDUCE_INFLUENCE"
    INCREASE_INFLUENCE = "INCREASE_INFLUENCE"
    DISABLE_MODEL = "DISABLE_MODEL"
    EMERGENCY_RISK_REDUCTION = "EMERGENCY_RISK_REDUCTION"
    CAPITAL_PRESERVATION = "CAPITAL_PRESERVATION"

@dataclass(frozen=True)
class HealthScores:
    model_health: dict[str, float]      # per-model 0-100
    execution_quality: float             # system-wide 0-100
    risk: float                          # system-wide 0-100 (inverted)
    broker_quality: dict[str, float]    # per-broker 0-100
    regime_confidence: float             # system-wide 0-100
    overall: float                       # aggregate 0-100

class CEOSupervisor:
    \"\"\"Main orchestrator. Does NOT generate trading signals.\"\"\"

    def __init__(
        self,
        monitors: dict[str, IMonitor],
        detector_engine: DetectionEngine,
        decision_engine: DecisionEngine,
        action_engine: ActionEngine,
        database: Database,
        cycle_interval_s: int = 60,
    ) -> None:
        self._monitors = monitors
        self._detectors = detector_engine
        self._decision = decision_engine
        self._actions = action_engine
        self._db = database
        self._interval = cycle_interval_s
        self._cycle_task: asyncio.Task | None = None
        self._current_status: SystemStatus = SystemStatus.GREEN
        self._current_scores: HealthScores | None = None

    async def start(self) -> None:
        self._cycle_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._cycle_task:
            self._cycle_task.cancel()
            await asyncio.gather(self._cycle_task, return_exceptions=True)

    async def _run_loop(self) -> None:
        while True:
            try:
                await self.run_cycle()
            except Exception as e:
                # Log but never crash — CEO must be always-on
                await self._db.save_error(str(e))
            await asyncio.sleep(self._interval)

    async def run_cycle(self) -> SystemStatus:
        # 1. Ingest events (via NATS subscriptions, populated async)
        # 2. Compute 6 health scores
        scores = self._compute_scores()
        # 3. Run 8 detectors
        events = self._detectors.run_all(self._build_context(scores))
        # 4. Decide system status
        new_status = self._decision.decide(scores, events)
        # 5. Execute actions if status changed
        if new_status != self._current_status:
            await self._handle_status_change(new_status, scores, events)
        # 6. Persist + report
        await self._db.save_scores(scores, new_status)
        self._current_status = new_status
        self._current_scores = scores
        return new_status

    def _compute_scores(self) -> HealthScores:
        model_h = {mid: m.compute_score() for mid, m in
                   self._monitors.items() if mid.startswith("model:")}
        eqs = self._monitors["execution"].compute_score()
        risk = self._monitors["risk"].compute_score()
        bqs = {bid: m.compute_score() for bid, m in
               self._monitors.items() if bid.startswith("broker:")}
        regime = self._monitors["regime"].compute_score()
        overall = self._aggregate(model_h, eqs, risk, bqs, regime)
        return HealthScores(model_h, eqs, risk, bqs, regime, overall)

    @staticmethod
    def _aggregate(model_h, eqs, risk, bqs, regime) -> float:
        min_model = min(model_h.values()) if model_h else 0.0
        min_broker = min(bqs.values()) if bqs else 0.0
        return (0.30 * min_model + 0.25 * risk + 0.20 * eqs
                + 0.15 * regime + 0.10 * min_broker)

    async def _handle_status_change(self, new_status, scores, events) -> None:
        critical = [e for e in events if e.severity == "CRITICAL"]
        if new_status == SystemStatus.YELLOW:
            for model_id, score in scores.model_health.items():
                if score < 75:
                    await self._actions.reduce_influence(model_id, factor=0.5)
        elif new_status == SystemStatus.RED:
            for model_id, score in scores.model_health.items():
                if score < 60:
                    await self._actions.disable_model(model_id)
            await self._actions.trigger_emergency()
        elif new_status == SystemStatus.RED_PRESERVE:
            await self._actions.trigger_capital_preservation()"""))

    s.append(h2('RollingWindow Class (Python)')
    )
    s.append(code("""import collections
import numpy as np

class RollingWindow:
    \"\"\"Bounded ring buffer. O(1) push, O(N) iterate. No unbounded growth.\"\"\"

    __slots__ = ("_buffer", "_max_size")

    def __init__(self, max_size: int) -> None:
        self._buffer: collections.deque[float] = collections.deque(maxlen=max_size)
        self._max_size = max_size

    def push(self, value: float) -> None:
        self._buffer.append(value)

    def to_array(self) -> np.ndarray:
        return np.array(self._buffer, dtype=np.float64)

    def percentile(self, p: float) -> float:
        if len(self._buffer) == 0:
            return 0.0
        return float(np.percentile(self.to_array(), p))

    def mean(self) -> float:
        if len(self._buffer) == 0:
            return 0.0
        return float(np.mean(self.to_array()))

    def std(self) -> float:
        if len(self._buffer) < 2:
            return 0.0
        return float(np.std(self.to_array(), ddof=1))

    def max(self) -> float:
        if len(self._buffer) == 0:
            return 0.0
        return float(np.max(self.to_array()))

    def __len__(self) -> int:
        return len(self._buffer)"""))

    s.append(h2('5 Interfaces (Python Protocol)')
    )
    s.append(code("""from typing import Protocol

class IMonitor(Protocol):
    \"\"\"Interface for all health monitors.\"\"\"
    def compute_score(self) -> float: ...
    def get_window(self, metric: str, size: int) -> np.ndarray: ...

class IDetectionRule(Protocol):
    \"\"\"Interface for 8 detectors (Strategy pattern).\"\"\"
    def evaluate(self, context: DetectionContext) -> DetectionEvent | None: ...
    def severity(self) -> str: ...  # CRITICAL / MAJOR / MINOR

class IModelController(Protocol):
    \"\"\"Interface for controlling ensemble models.\"\"\"
    async def set_influence(self, model_id: str, weight: float) -> None: ...
    async def disable(self, model_id: str) -> None: ...
    async def enable(self, model_id: str) -> None: ...

class IRiskController(Protocol):
    \"\"\"Interface for triggering risk mode changes.\"\"\"
    async def set_mode(self, mode: str) -> None: ...  # NORMAL/DEFENSIVE/EMERGENCY
    async def emergency_flatten(self) -> None: ...

class IAlertSink(Protocol):
    \"\"\"Interface for alerts (PagerDuty, Slack, etc.).\"\"\"
    async def send(self, alert: Alert) -> None: ...
    async def send_batch(self, alerts: list[Alert]) -> None: ..."""))

    s.append(PageBreak())

    # Ch 8 — Database Schema
    s.append(h1('Database Schema — 10 PostgreSQL Tables',8))
    s.append(p('The CEO persists to PostgreSQL 15 with TimescaleDB extension for time-series hypertables. 10 tables: 6 time-series score tables (model_health_scores, execution_quality_scores, risk_scores, broker_quality_scores, regime_confidence_scores, system_health_scores) with 90-day hot retention + 7-year cold (S3 Parquet), and 4 immutable audit tables (system_status_changes, control_actions, detection_events, model_influence_changes) with 7-year WORM retention. All audit tables have INSERT-only triggers (no UPDATE/DELETE) and signed_hash columns for tamper-evidence.'))
    s.append(diagram('d07_db_schema.png',170))
    s.append(caption('Figure 8.1 — 10 PostgreSQL tables: 6 time-series + 4 audit (immutable). TimescaleDB hypertables, monthly partitioning.'))

    s.append(h2('Key DDL — Audit Table (PostgreSQL)'))
    s.append(code("""-- control_actions: every CEO action, immutable, tamper-evident
CREATE TABLE control_actions (
    id           BIGSERIAL PRIMARY KEY,
    timestamp    TIMESTAMPTZ NOT NULL DEFAULT now(),
    action_type  VARCHAR(32) NOT NULL,  -- REDUCE/DISABLE/EMERGENCY/PRESERVE
    target_model VARCHAR(32),
    target_broker VARCHAR(32),
    parameters   JSONB,
    trigger_score DECIMAL(5,2),
    trigger_reason TEXT,
    result       VARCHAR(16),
    executed_by  VARCHAR(16) DEFAULT 'CEO',
    signed_hash  CHAR(64) NOT NULL  -- SHA-256 of row for tamper-evidence
);

-- WORM lock: INSERT only, no UPDATE/DELETE
CREATE OR REPLACE FUNCTION prevent_audit_modify()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit table is INSERT-only (WORM)';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER no_update BEFORE UPDATE ON control_actions
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_modify();
CREATE TRIGGER no_delete BEFORE DELETE ON control_actions
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_modify();

-- TimescaleDB hypertable for time-series scores
CREATE TABLE system_health_scores (
    id              BIGSERIAL,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    score           DECIMAL(5,2) NOT NULL,
    status          VARCHAR(8) NOT NULL,
    min_model_health DECIMAL(5,2),
    risk_score      DECIMAL(5,2),
    eqs             DECIMAL(5,2),
    regime_conf     DECIMAL(5,2),
    min_bqs         DECIMAL(5,2),
    cycle_duration_ms INT,
    PRIMARY KEY (id, timestamp)
);
SELECT create_hypertable('system_health_scores', 'timestamp');
-- 90-day hot retention, then archive to S3 Parquet
SELECT add_retention_policy('system_health_scores', INTERVAL '90 days');"""))

    s.append(PageBreak())

    # Ch 9 — Tests
    s.append(h1('Test Suite — 145 Tests',9))
    s.append(p('The CEO has 145 tests across 3 layers: 80 unit tests (pure-function, <1ms each, pytest + GoogleTest), 45 integration tests (end-to-end flows, real NATS + PostgreSQL, ~5s each), 20 validator tests (compliance + invariants). All 145 must pass on every PR merge — zero flaky tolerance over 30-day window. The validator tests enforce the hard constraints: CEO must NOT generate signals, no external LLM, no paid APIs, fully offline, CPU-only, cycle <100ms.'))
    s.append(diagram('d08_tests_deployment.png',170))
    s.append(caption('Figure 9.1 — 145 tests: 80 unit + 45 integration + 20 validator. 100% CI-gated, zero flaky.'))

    s.append(h2('Key Validator Tests (compliance)'))
    s.append(p('<b>VT-001 CEO must NOT generate signals:</b> Static code scan asserts CEO code never calls strategy.execute() or places orders. The CEO is a governance layer, not a signal generator. <b>VT-002 No external LLM:</b> Static scan for openai/anthropic imports — zero found. Assert 0 outbound LLM calls in 24h network monitor. <b>VT-003 No paid APIs:</b> Network monitor asserts 0 outbound HTTP except optional PagerDuty/Slack. <b>VT-004 Fully offline:</b> Disable all network → CEO operates normally for 24h, alerts queued locally. <b>VT-005 CPU-only:</b> Run with CUDA_VISIBLE_DEVICES="" → CEO operates normally. <b>VT-006 Cycle <100ms:</b> P99 cycle time over 1000 cycles <100ms on 4-vCPU VPS.'))

    s.append(h2('Sample Unit Test (Python)'))
    s.append(code("""def test_d4_overfitting_detector_fires():
    \"\"\"D4: Live Sharpe < 0.5 × backtest Sharpe → fires CRITICAL.\"\"\"
    baseline_sharpe = 2.5  # from backtest
    live_sharpe = 1.0      # current live (ratio = 0.4 < 0.5)
    detector = OverfittingDetector(baseline_sharpe=baseline_sharpe)

    context = DetectionContext(
        live_sharpe=live_sharpe,
        window_size=250,
        model_id="xgboost",
    )
    event = detector.evaluate(context)

    assert event is not None
    assert event.severity == "CRITICAL"
    assert event.detector_id == "D4_OVERFITTING"
    assert event.target == "xgboost"
    assert event.metric_value == 1.0
    assert event.threshold == 1.25  # 0.5 × 2.5

def test_d4_overfitting_detector_does_not_fire():
    \"\"\"D4: Live Sharpe ≥ 0.5 × backtest → does NOT fire.\"\"\"
    baseline_sharpe = 2.5
    live_sharpe = 1.5  # ratio = 0.6 ≥ 0.5
    detector = OverfittingDetector(baseline_sharpe=baseline_sharpe)

    context = DetectionContext(live_sharpe=live_sharpe, window_size=250, model_id="xgboost")
    event = detector.evaluate(context)

    assert event is None

def test_overall_health_min_model_dominates():
    \"\"\"Overall health: min(model_health) weighted highest (30%).\"\"\"
    scores = HealthScores(
        model_health={"xgb": 95, "lstm": 60, "transformer": 90, "rl": 88},
        execution_quality=92,
        risk=90,
        broker_quality={"icmarkets": 95, "exness": 93},
        regime_confidence=88,
        overall=0,  # computed below
    )
    overall = CEOSupervisor._aggregate(
        scores.model_health, scores.execution_quality,
        scores.risk, scores.broker_quality, scores.regime_confidence
    )
    # min_model = 60 (LSTM), min_broker = 93
    # 0.30*60 + 0.25*90 + 0.20*92 + 0.15*88 + 0.10*93
    # = 18.0 + 22.5 + 18.4 + 13.2 + 9.3 = 81.4
    assert overall == pytest.approx(81.4, abs=0.1)
    # LSTM's low score (60) drags overall below 85 (GREEN threshold)
    assert overall < 85  # would trigger YELLOW"""))

    s.append(PageBreak())

    # Ch 10 — Deployment
    s.append(h1('Deployment Documentation',10))
    s.append(p('The CEO deploys as a single Python asyncio process on the same 4-vCPU VPS as the TITAN trading core. It requires PostgreSQL 15 (with TimescaleDB), Python 3.12, and 4 Python packages (asyncpg, numpy, nats-py, prometheus-client). Total deployment: 10 steps, ~30 minutes. The CEO runs as a systemd service, auto-restarts on failure, and integrates with the existing Prometheus + Grafana + PagerDuty stack.'))
    s.append(h2('10-Step Deployment Guide'))
    s.append(code("""# Step 1: Provision VPS (if not already running TITAN core)
# 4 vCPU, 8GB RAM, 100GB SSD, Ubuntu 22.04 LTS
# (CEO shares VPS with trading core — no separate hardware)

# Step 2: Install PostgreSQL 15 + TimescaleDB
sudo apt install postgresql-15 postgresql-15-timescaledb
sudo -u postgres psql -c "CREATE DATABASE titan_ceo;"
sudo -u postgres psql -d titan_ceo -c "CREATE EXTENSION timescaledb;"

# Step 3: Create schema (10 tables + hypertables + audit triggers)
psql -d titan_ceo -f /opt/titan/ceo/sql/schema.sql

# Step 4: Install Python 3.12 + dependencies
sudo apt install python3.12 python3.12-venv
python3.12 -m venv /opt/titan/ceo/venv
/opt/titan/ceo/venv/bin/pip install asyncpg numpy nats-py prometheus-client

# Step 5: Configure CEO
sudo mkdir -p /etc/titan
sudo cat > /etc/titan/ceo.yaml << 'EOF'
nats_url: "nats://localhost:4222"
db_dsn: "postgresql://titan@localhost/titan_ceo"
cycle_interval_s: 60
pagerduty_webhook: ""  # optional — offline if empty
slack_webhook: ""      # optional
models:
  - xgboost
  - lstm
  - transformer
  - rl
brokers:
  - exness
  - icmarkets
  - pepperstone
  - tickmill
  - fp_markets
  - fusion_markets
EOF

# Step 6: Install systemd service
sudo cat > /etc/systemd/system/titan-ceo.service << 'EOF'
[Unit]
Description=TITAN Meta AI CEO Supervisor
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=titan
ExecStart=/opt/titan/ceo/venv/bin/python -m titan_ceo.supervisor
Restart=always
RestartSec=10
Environment=TITAN_CEO_CONFIG=/etc/titan/ceo.yaml

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable titan-ceo
sudo systemctl start titan-ceo

# Step 7: Import Grafana dashboard
# (8 panels: 6 health scores + system status + action log)
grafana-cli dashboards import /opt/titan/ceo/grafana/ceo-dashboard.json

# Step 8: Configure Prometheus scrape
# Add to prometheus.yml:
#   - job_name: 'titan-ceo'
#     scrape_interval: 15s
#     static_configs:
#       - targets: ['localhost:9101']

# Step 9: Configure PagerDuty (optional)
# Set webhook in /etc/titan/ceo.yaml
# P1 = RED status, P2 = YELLOW status

# Step 10: Smoke test
# Feed 100 synthetic trades via NATS, verify:
# - 6 score rows in system_health_scores
# - GREEN status
# - No control_actions fired
# - Cycle time < 100ms
python -m titan_ceo.smoke_test --trades 100"""))

    s.append(PageBreak())

    # Ch 11 — Operational Notes
    s.append(h1('Operational Notes',11))
    s.append(p('The CEO is designed for 24/7 unattended operation. It auto-recovers from transient failures (NATS disconnect, PostgreSQL connection drop) via asyncio retry logic. If the CEO process crashes, systemd auto-restarts within 10 seconds. The CEO never blocks the trading core — all control actions are async (await model_ctrl.set_influence()), and the ensemble voter applies weight changes within 100ms of receiving them. The CEO is a governance layer, not a latency-critical path component.'))
    s.append(h2('Failure Modes'))
    s.append(p('<b>NATS disconnect:</b> CEO buffers last-known scores, continues operating with stale data for up to 5 minutes. After 5 minutes, status degrades to YELLOW (stale data). <b>PostgreSQL disconnect:</b> CEO buffers scores in memory (up to 1000 cycles = ~16 hours), retries every 15 seconds. No data loss. <b>CEO process crash:</b> systemd restarts within 10s. On restart, CEO loads last-known status from DB, re-syncs rolling windows from trade ledger. <b>False positive (CEO disables healthy model):</b> Manual re-enable via CLI: python -m titan_ceo.cli enable-model xgboost. CEO logs every action with trigger reason for post-hoc analysis.'))
    s.append(h2('Monitoring the CEO Itself'))
    s.append(p('The CEO exports 15 Prometheus metrics: ceo_cycle_duration_seconds (histogram), ceo_current_status (gauge: 0=GREEN/1=YELLOW/2=RED/3=PRESERVE), ceo_overall_health (gauge 0-100), ceo_model_health (gauge per model), ceo_eqs, ceo_risk_score, ceo_broker_quality (per broker), ceo_regime_confidence, ceo_detectors_fired_total (counter per detector), ceo_actions_executed_total (counter per action), ceo_nats_events_ingested_total, ceo_db_write_latency_ms, ceo_rolling_window_size (gauge per window). Alerting: ceo_current_status == 2 (RED) for >60s → P1 PagerDuty. ceo_cycle_duration_seconds P99 > 200ms → P2 (CEO is slow). ceo_db_write_latency_ms P99 > 1000ms → P2 (DB slow).'))
    s.append(h2('Integration with Existing TITAN Stack'))
    s.append(p('The CEO integrates with 4 existing TITAN modules via well-defined interfaces: (1) M11 Hybrid AI Stack — CEO controls ensemble voter via IModelController (set_influence, disable, enable). The ensemble voter checks influence weights before each vote, applying them within 100ms. (2) M08 Risk Engine — CEO triggers risk mode changes via IRiskController (set_mode, emergency_flatten). The risk engine applies mode changes within 500ms. (3) M03 Execution Engine — CEO observes fills and latency via NATS subscription (read-only). No control. (4) M20 Observability — CEO exports Prometheus metrics that M20 scrapes. <b>No existing module requires modification</b> — the CEO observes via subscriptions and controls via interfaces. This is a drop-in addition.'))

    s.append(PageBreak())

    # Ch 12 — Summary
    s.append(h1('Summary',12))
    s.append(p('The Meta AI CEO Supervisor (Module 18) is the runtime governance layer that the TITAN XAU AI system was missing. While the existing 5 validation frameworks (Backtest, Walk-Forward, Monte Carlo, Stress, Validator) gate pre-deployment, the CEO provides <b>continuous runtime governance</b> — monitoring all models, execution, risk, brokers, and regimes in real-time, detecting degradation before it becomes catastrophic, and taking automated corrective action. The CEO does NOT generate signals (enforced by validator test VT-001). It is a pure governance layer that observes, scores, and controls.'))
    s.append(p('The CEO delivers on all requirements: 6 health scores (Model Health, EQS, Risk, BQS, Regime Confidence, Overall), 8 detectors (degradation, drift, instability, overfitting, exec deterioration, broker issues, regime failures, latency), 4 rolling windows (50/100/250/500 trades), 8 tracked metrics (WR/PF/Sharpe/Sortino/MDD/Recovery/Latency/Slippage), GREEN/YELLOW/RED status, 5 control actions (reduce/increase influence, disable model, emergency risk reduction, capital preservation). It operates under 4 hard constraints: no paid APIs, no external LLM, CPU optimized (<100ms/cycle), fully offline capable. The implementation is fully specified: 16 Python classes, 5 interfaces, 10 PostgreSQL tables, 145 tests (80 unit + 45 integration + 20 validator), and a 10-step deployment guide.'))
    s.append(p('The CEO is the final piece of the TITAN governance architecture. With the CEO in place, the system has: (1) pre-deployment validation (5 frameworks), (2) runtime governance (CEO), (3) post-deployment monitoring (M20 Observability), and (4) quarterly re-validation (all 5 frameworks on live strategies). This is a complete, institutionally-rigorous governance lifecycle — the kind that separates world-class trading systems from retail bots. <b>The CEO watches the watchers.</b>'))

    return s

def main():
    out = '/home/z/my-project/scripts/ceo/body.pdf'
    doc = TocDocTemplate(out, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=24*mm, bottomMargin=22*mm, title='TITAN XAU AI — Meta AI CEO Supervisor', author='TITAN Quant Research', subject='Module 18: Meta AI CEO Supervisor — governance layer, 6 health scores, 8 detectors, 5 control actions, 145 tests, deployment docs', creator='TITAN Architecture Workbench')
    story = build_story()
    print(f'[build] Building body PDF with {len(story)} flowables...')
    doc.multiBuild(story, onFirstPage=hf, onLaterPages=hf)
    print(f'[build] Body PDF written: {out}')
    from pypdf import PdfReader; r = PdfReader(out); print(f'[build] Page count: {len(r.pages)}')

if __name__ == '__main__': main()
