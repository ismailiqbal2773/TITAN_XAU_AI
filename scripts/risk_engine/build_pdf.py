"""
TITAN XAU AI — Institutional Risk Engine (Module 8)
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
CARD_BG = colors.HexColor('#F1F5F9'); TABLE_STRIPE = colors.HexColor('#F8FAFC')
DIAGRAM_DIR = '/home/z/my-project/scripts/risk_engine/diagrams/png'

S = {}
S['h1'] = ParagraphStyle('h1', fontName='FreeSerif-Bold', fontSize=20, leading=26, textColor=HEADER_FILL, spaceBefore=18, spaceAfter=10, alignment=TA_LEFT)
S['h2'] = ParagraphStyle('h2', fontName='FreeSerif-Bold', fontSize=14, leading=18, textColor=HEADER_FILL, spaceBefore=14, spaceAfter=6, alignment=TA_LEFT)
S['h3'] = ParagraphStyle('h3', fontName='FreeSerif-Bold', fontSize=11.5, leading=15, textColor=ACCENT, spaceBefore=10, spaceAfter=4, alignment=TA_LEFT)
S['body'] = ParagraphStyle('body', fontName='FreeSerif', fontSize=10.5, leading=16, textColor=TEXT_PRIMARY, spaceBefore=0, spaceAfter=8, alignment=TA_JUSTIFY)
S['bullet'] = ParagraphStyle('bullet', fontName='FreeSerif', fontSize=10.5, leading=15, textColor=TEXT_PRIMARY, leftIndent=18, bulletIndent=4, spaceBefore=2, spaceAfter=4, alignment=TA_LEFT)
S['code'] = ParagraphStyle('code', fontName='DejaVuSans', fontSize=9, leading=12, textColor=TEXT_PRIMARY, leftIndent=14, rightIndent=14, spaceBefore=6, spaceAfter=8, backColor=SECTION_BG, borderColor=BORDER, borderWidth=0.5, borderPadding=8, alignment=TA_LEFT)
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
    c.setFont('FreeSerif-Italic',8.5); c.setFillColor(TEXT_MUTED); c.drawString(20*mm, A4[1]-14*mm, 'TITAN XAU AI — Institutional Risk Engine')
    c.setFont('FreeSerif-Bold',8.5); c.setFillColor(ACCENT); c.drawRightString(A4[0]-20*mm, A4[1]-14*mm, 'v1.0  ·  INTERNAL')
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

    s.append(h1('Executive Summary',1))
    s.append(p('The Institutional Risk Engine (IRE) is Module 8 of the TITAN XAU AI trading architecture. It is the system\'s ultimate safety system — a multi-layered risk management framework that enforces capital preservation across 4 risk modes (Conservative, Balanced, Aggressive, Competition), 6 core controls (Daily DD, Weekly DD, Monthly DD, Risk Per Trade, Max Open Trades, Max Exposure), and 3 defense layers (loss streak management, equity guardrail, volatility throttle). The IRE has structural veto power over every order: no trade reaches the broker without passing through the pre-trade risk gate.'))
    s.append(p('The engine operates on a simple principle: capital preservation takes absolute precedence over alpha generation. Every architectural decision — from the 3-tier circuit breaker system (soft throttle, hard halt, critical flatten) to the kill switch (<500ms end-to-end shutdown) to the equity guardrail (auto-degrade to Conservative at 95% of starting equity) — exists to enforce this principle. The IRE is the structural guarantee that the system cannot blow up, regardless of what the strategies or AI models do.'))
    s.append(p('The 4 risk modes are swappable at runtime, allowing the system to adapt its risk posture to market conditions, account size, and operator preference. Conservative mode (0.5% risk per trade, 1.5% daily DD hard limit, 2 max trades) is the default and the auto-degrade target when any circuit breaker fires. Balanced mode (0.8% risk, 2.0% daily DD, 3 max trades) is the standard production mode for most licensees. Aggressive mode (1.2% risk, 3.0% daily DD, 4 max trades) requires supervisor authorization. Competition mode (2.0% risk, 5.0% daily DD, 5 max trades) requires triple authorization (CTO + risk officer + supervisor) and is intended only for trading competitions and prop firm challenges.'))
    s.append(p('The emergency shutdown system (kill switch) is the IRE\'s last line of defense. It can be triggered by 4 sources (hard DD, manual operator, license revocation, system critical) and executes a 4-action sequence in under 500 milliseconds: halt new orders, cancel pending orders, flatten all positions, and notify the operator. A 5-minute cooldown prevents panic re-triggering, and re-arm requires supervisor authorization plus mandatory degradation to Conservative mode.'))

    s.append(h1('Architecture Overview',2))
    s.append(p('The IRE is organized into 5 layers: risk mode selector (parameter provider), pre-trade risk gate (synchronous veto), post-trade risk monitor (async DD tracking), emergency shutdown (kill switch), and capital preservation (proactive defense). A 6th layer (audit and observability) records every decision for compliance and post-incident analysis.'))
    s.append(diagram('d01_architecture.png',170))
    s.append(caption('Figure 2.1 — IRE architecture: 5 layers + audit, showing all components and their interactions.'))

    s.append(h2('Layer Responsibilities'))
    s.append(h3('L1 — Risk Mode Selector'))
    s.append(p('RiskModeManager loads the active risk mode at startup and provides mode-specific parameters to all other layers. Modes are swappable by operators with appropriate authorization (Conservative/Balanced: supervisor; Aggressive: supervisor + risk officer; Competition: CTO + risk officer + supervisor). The mode auto-degrades to Conservative on any hard circuit breaker trigger, ensuring that the system always falls back to the safest configuration when under stress.'))

    s.append(h3('L2 — Pre-Trade Risk Gate (synchronous, <0.3ms)'))
    s.append(p('The pre-trade gate is a synchronous veto on every order. Three validators run in sequence: PositionSizeValidator (risk per trade, leverage, exposure), ConcurrencyValidator (max open trades, duplicate symbol, correlation, session, news blackout), and MarginValidator (free margin floor, post-trade margin projection). If any validator returns REJECT, the order is blocked — there is no bypass. The gate completes in under 0.3ms p99, ensuring zero impact on the execution engine\'s latency budget.'))

    s.append(h3('L3 — Post-Trade Risk Monitor (async, continuous)'))
    s.append(p('Three drawdown monitors run continuously: DailyDDMonitor (UTC day, resets at 00:00), WeeklyDDMonitor (7-day rolling), and MonthlyDDMonitor (30-day rolling). Each has soft and hard thresholds (mode-parameterized). Soft triggers size reduction (×0.5); hard triggers halt (no new entries). The monitors update on every fill, ensuring real-time drawdown tracking.'))

    s.append(h3('L4 — Emergency Shutdown (kill switch, <500ms)'))
    s.append(p('The KillSwitchController is the ultimate safety mechanism. It executes a 4-action sequence: halt new orders (atomic flag, <1ms), cancel pending orders (~50ms broker RTT), flatten all positions (~200ms market order), and notify operator (~100ms async). Total end-to-end: <500ms. The kill switch can be triggered by hard DD, manual operator action (2-person rule), license revocation, or system critical (broker disconnect, equity guardrail L3, AI ensemble halt). A 5-minute cooldown prevents panic re-triggering.'))

    s.append(h3('L5 — Capital Preservation (proactive)'))
    s.append(p('Three proactive defense layers: LossStreakManager (progressive de-risking: 3 losses → size×0.5, 5 losses → halt, 7 losses → flatten), EquityGuardRail (absolute equity protection: 95% → degrade, 90% → halt, 85% → flatten+lock), and VolatilityThrottle (ATR percentile-based: >60% → size×0.7, >80% → size×0.3, >95% → no new entries). These layers operate proactively — they reduce risk before losses occur, not after.'))

    s.append(PageBreak())

    s.append(h1('4 Risk Modes',3))
    s.append(p('The IRE supports 4 risk modes, each with 12+ parameters covering all 6 core controls plus additional safeguards. Modes are swappable at runtime with appropriate authorization. The default mode is Conservative; any circuit breaker trigger auto-degrades to Conservative regardless of the current mode.'))
    s.append(diagram('d02_risk_modes.png',170))
    s.append(caption('Figure 3.1 — 4 risk modes with all parameters side-by-side.'))

    s.append(h2('Mode Selection Guidelines'))
    s.append(bullet('Conservative (0.5% risk): Default mode. Use for large accounts, initial deployment, post-drawdown recovery, and regulatory compliance. Auto-degrade target.'))
    s.append(bullet('Balanced (0.8% risk): Standard production mode for most licensees (Pro tier). Requires verified track record. Best risk-reward trade-off for accounts $50k-$500k.'))
    s.append(bullet('Aggressive (1.2% risk): For experienced traders during high-conviction periods. Requires supervisor + risk officer authorization. Larger accounts ($500k+) only.'))
    s.append(bullet('Competition (2.0% risk): Trading competitions and prop firm challenges only. Small accounts ($1k-$10k). Requires CTO + risk officer + supervisor triple authorization. Not for production use.'))

    s.append(PageBreak())

    s.append(h1('Risk Formulas',4))
    s.append(p('All risk calculations are mode-parameterized and computed continuously. The formulas are the authoritative specification — any code producing different values is a bug.'))
    s.append(diagram('d03_formulas.png',170))
    s.append(caption('Figure 4.1 — All risk formulas: DD calculations, position size, exposure, and circuit breaker triggers.'))

    s.append(h2('Drawdown Calculations'))
    s.append(code("""DailyDD = (peak_equity_today - current_equity) / peak_equity_today
  peak_today = max(equity) since 00:00 UTC
  resets daily at 00:00 UTC

WeeklyDD = (peak_equity_7d - current_equity) / peak_equity_7d
  peak_7d = max(equity) over rolling 7-day window
  no reset (continuous rolling)

MonthlyDD = (peak_equity_30d - current_equity) / peak_equity_30d
  peak_30d = max(equity) over rolling 30-day window
  no reset (continuous rolling)

Each DD has soft and hard thresholds (mode-parameterized):
  Soft → size × 0.5 (throttle)
  Hard → no new entries (halt)"""))

    s.append(h2('Position Size Formula'))
    s.append(code("""qty = (equity × risk_per_trade%) / (stop_distance × tick_value)

where:
  risk_per_trade% = mode.risk_per_trade × confidence_factor × streak_factor × vol_factor
  bounded to [mode.risk_floor, mode.risk_ceiling]

  confidence_factor ∈ [0.5, 1.0]  (from ARDS or AI ensemble)
  streak_factor ∈ [0.5, 1.2]      (anti-martingale)
  vol_factor ∈ [0.3, 1.1]         (ATR percentile inverse)"""))

    s.append(h2('Exposure Formula'))
    s.append(code("""gross_exposure = Σ(|qty_i × price_i|) for all open positions

  must satisfy: gross_exposure ≤ mode.max_exposure × equity

  If new entry would exceed: REJECT"""))

    s.append(h2('Circuit Breaker Triggers'))
    s.append(p('Three tiers of circuit breakers, each with specific triggers and actions:'))
    s.append(bullet('SOFT (Throttle): DailyDD/WeeklyDD/MonthlyDD ≥ soft threshold, or loss streak ≥ (halt-1), or ATR pct > 80. Action: size × 0.5, continue trading.'))
    s.append(bullet('HARD (Halt): DailyDD/WeeklyDD/MonthlyDD ≥ hard threshold, or loss streak ≥ halt count, or equity < guard_L1. Action: no new entries, manage open positions, auto-degrade to Conservative.'))
    s.append(bullet('CRITICAL (Flatten): Equity < guard_L2, or kill switch engaged, or broker disconnect, or license revoked. Action: flatten ALL positions immediately, halt, page operator P1.'))

    s.append(PageBreak())

    s.append(h1('Emergency Shutdown Logic',5))
    s.append(p('The emergency shutdown (kill switch) is the IRE\'s last line of defense — the mechanism that guarantees the system cannot blow up. It can be triggered by 4 sources and executes a 4-action sequence in under 500 milliseconds. After shutdown, a 5-minute cooldown prevents panic re-triggering, and re-arm requires supervisor authorization plus mandatory degradation to Conservative mode.'))
    s.append(diagram('d04_shutdown.png',170))
    s.append(caption('Figure 5.1 — Kill switch flowchart: 4 triggers, 4 actions, cooldown, re-arm with degradation.'))

    s.append(h2('Trigger Sources'))
    s.append(h3('T1: Hard Drawdown (automatic)'))
    s.append(p('When any drawdown monitor (daily, weekly, or monthly) hits its hard threshold, the kill switch fires automatically. No human input is required — the system protects itself. This is the most common trigger in production.'))

    s.append(h3('T2: Manual Operator (2-person rule)'))
    s.append(p('An operator can manually trigger the kill switch from the operator console. This requires the 2-person rule: a TRADER initiates and a SUPERVISOR approves within a 5-minute window. This prevents a single rogue operator from halting the system.'))

    s.append(h3('T3: License Revoked (automatic)'))
    s.append(p('If the license server heartbeat fails and the 7-day offline grace period expires, the kill switch fires automatically. The system flattens all positions and halts, preventing unauthorized use.'))

    s.append(h3('T4: System Critical (automatic)'))
    s.append(p('Broker disconnect mid-trade, equity below guard_L3 (e.g., 85% of start), or 2+ AI models degraded (ensemble halt). These are system-level failures that require immediate position flattening.'))

    s.append(h2('Shutdown Sequence'))
    s.append(p('The 4-action sequence executes in under 500ms total: (1) Halt new orders via atomic flag (<1ms), (2) Cancel all pending orders via broker API (~50ms), (3) Flatten all open positions via market orders (~200ms, accepting slippage — speed > price), (4) Notify operator via PagerDuty + Telegram + email + console (~100ms, async non-blocking). After the sequence, a 5-minute cooldown begins during which re-arm is impossible.'))

    s.append(h2('Re-arm Protocol'))
    s.append(p('After the 5-minute cooldown, a re-arm request can be made. It requires SUPERVISOR authorization plus an audit reason code explaining why the kill switch was triggered and why it is safe to resume. On re-arm, the system automatically degrades to Conservative mode (regardless of the previous mode) and applies a size × 0.5 multiplier for the first 30 minutes. This ensures that the system resumes cautiously after any emergency shutdown.'))

    s.append(PageBreak())

    s.append(h1('Capital Preservation Logic',6))
    s.append(p('Capital preservation is the IRE\'s proactive defense system — it reduces risk before losses occur, not after. Three layers operate continuously: loss streak management (anti-martingale progressive de-risking), equity guardrail (absolute equity protection), and volatility throttle (market condition adaptation).'))
    s.append(diagram('d05_capital.png',170))
    s.append(caption('Figure 6.1 — 3 capital preservation layers with triggers, actions, and reset conditions.'))

    s.append(h2('Layer 1: Loss Streak Manager'))
    s.append(p('Progressive de-risking on consecutive losses. 0-2 losses: normal (1.0x size). 3 losses: throttled (0.5x size, stricter entry). 5 losses: halted (no new entries). 7 losses: critical (flatten all, lock session). Any win resets the counter to 0. This is anti-martingale: the system reduces risk when losing (not increases it), which is the opposite of the gambler\'s fallacy that destroys most trading accounts.'))

    s.append(h2('Layer 2: Equity Guardrail'))
    s.append(p('Absolute equity protection based on % of starting capital. Equity ≥ 95%: normal. 90-95%: degrade to Conservative mode + size × 0.5 for 1 hour. 85-90%: halt + flatten + operator review. Below 85%: flatten + lock account (manual CTO unlock only). The guardrail is an absolute floor — it cannot be overridden by any mode or operator action. It ensures that the system never loses more than 15% of starting capital under any circumstances.'))

    s.append(h2('Layer 3: Volatility Throttle'))
    s.append(p('ATR percentile-based size scaling. Normal vol (ATR < 60th pct): 1.0x size. Elevated vol (60-80th pct): 0.7x size, tighter stops. High vol (> 80th pct): 0.3x size, no new entries above 95th pct. The throttle adapts to market conditions automatically, reducing risk in storms and exploiting calm periods. It is mode-parameterized: Conservative throttles at lower ATR percentiles than Aggressive.'))

    s.append(PageBreak())

    s.append(h1('Risk Controls Summary',7))
    s.append(p('The IRE enforces 6 core controls (Daily DD, Weekly DD, Monthly DD, Risk Per Trade, Max Open Trades, Max Exposure) plus 6 additional controls (Margin Floor, Loss Streak Halt, Equity Guardrail, Volatility Throttle, News Blackout, Session Filter). Each control is mode-parameterized, meaning the thresholds differ across the 4 risk modes. All 12 controls are audited and CI-tested.'))
    s.append(diagram('d07_controls.png',170))
    s.append(caption('Figure 7.1 — Complete risk controls summary: 6 core + 6 additional, all 4 modes, all thresholds.'))

    s.append(PageBreak())

    s.append(h1('Validation Tests',8))
    s.append(p('The IRE is validated through 200 tests across 5 categories: unit tests (per-mode parameters, formulas, breaker logic), integration tests (kill switch, circuit breakers, mode switching), chaos tests (broker disconnect, loss streak, stress load), and recovery tests (re-arm protocol, degradation, cooldown). All tests are CI-gated — a build that fails any gate cannot be promoted to production.'))
    s.append(diagram('d06_tests.png',170))
    s.append(caption('Figure 8.1 — Test pyramid and sample test cases covering DD, mode switch, size, exposure, loss streak, equity guardrail, and kill switch.'))

    s.append(h2('Critical Test Cases'))
    s.append(bullet('Kill switch end-to-end < 500ms (verified via high-resolution timer).'))
    s.append(bullet('Circuit breakers fire at exact thresholds (no off-by-one errors).'))
    s.append(bullet('Mode switch to Conservative in < 1s on degrade trigger.'))
    s.append(bullet('No position ever exceeds risk_per_trade × equity (stress test with 100 concurrent signals).'))
    s.append(bullet('Equity guardrail flattens positions in < 2s on L3 breach.'))
    s.append(bullet('Cooldown prevents re-arm for exactly 5 minutes (no early/late).'))
    s.append(bullet('Re-arm always degrades to Conservative mode (regardless of previous mode).'))

    s.append(h1('Integration with TITAN Core',9))
    s.append(p('The IRE integrates with every TITAN component that touches orders or equity. The pre-trade risk gate sits between the Strategy Coordinator and the Execution Engine, giving it structural veto power over every order. The post-trade monitors subscribe to fill events from the Execution Engine. The kill switch communicates with the Execution Engine via a dedicated reverse signal bus (not the main event bus), ensuring it can reach the OrderManager even if the main bus is saturated. The RiskMetricsExporter publishes risk state to Prometheus and the operator console via ZMQ.'))

    s.append(h2('Structural Veto Guarantee'))
    s.append(p('The IRE\'s veto power is structural, not conventional. It is enforced by the module dependency graph: the Execution Engine depends on the Risk Engine (not the reverse), and the OrderManager calls RiskGateClient.check() before every order submission. There is no code path from Strategy to Execution that bypasses the Risk Engine. This is verified by the architecture linter in CI — any commit that introduces a bypass is rejected.'))

    return s

def main():
    out = '/home/z/my-project/scripts/risk_engine/body.pdf'
    doc = TocDocTemplate(out, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=24*mm, bottomMargin=22*mm, title='TITAN XAU AI — Institutional Risk Engine', author='TITAN Quant Research', subject='Institutional Risk Engine: multi-layered risk management with 4 modes and 12 controls', creator='TITAN Architecture Workbench')
    story = build_story()
    print(f'[build] Building body PDF with {len(story)} flowables...')
    doc.multiBuild(story, onFirstPage=hf, onLaterPages=hf)
    print(f'[build] Body PDF written: {out}')
    from pypdf import PdfReader; r = PdfReader(out); print(f'[build] Page count: {len(r.pages)}')

if __name__ == '__main__': main()
