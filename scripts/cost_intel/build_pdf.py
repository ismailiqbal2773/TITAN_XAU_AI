"""
TITAN XAU AI — Execution Cost Intelligence (Module 9)
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
DIAGRAM_DIR = '/home/z/my-project/scripts/cost_intel/diagrams/png'

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
    c.setFont('FreeSerif-Italic',8.5); c.setFillColor(TEXT_MUTED); c.drawString(20*mm, A4[1]-14*mm, 'TITAN XAU AI — Execution Cost Intelligence')
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
    s.append(p('The Execution Cost Intelligence (ECI) module is Module 9 of the TITAN XAU AI trading architecture. It is the system\'s cost-awareness layer — a real-time cost measurement, modeling, and decision framework that ensures no trade is placed unless the expected edge remains positive after all execution costs. The ECI measures 5 cost components (spread, commission, swap, slippage, latency), aggregates them into a total cost estimate in basis points, and computes the expected net edge: signal_edge minus total_cost. If the net edge is negative, the trade is rejected. If the edge is positive but thin (below 3 bps safety margin), the position size is reduced. Only trades with a net edge above the safety margin are executed at full size.'))
    s.append(p('The module\'s core innovation is the EdgeCalculator — a pre-trade decision model that normalizes all costs to basis points of notional, making them comparable across brokers, account types, and instruments. This normalization is critical because different brokers charge costs in different units (spread in pips, commission in dollars per million, swap in points per lot, slippage in price units, latency in milliseconds). By converting everything to bps, the ECI can compare a raw-spread broker (low spread, high commission) against a standard broker (high spread, no commission) and route each signal to the lowest-cost venue.'))
    s.append(p('The ECI also includes a Cost Learning Engine that continuously updates slippage and latency models from realized fills. Every fill provides a data point: the predicted slippage vs the realized slippage, the expected latency vs the actual latency. The learning engine uses EMA updates (alpha=0.05) to calibrate per-broker, per-session, and per-regime cost models, ensuring that the cost estimates become more accurate over time. This adaptive calibration is what separates the ECI from static cost models — it learns from experience and improves.'))
    s.append(p('Two scoring systems provide ongoing quality assessment. The Execution Quality Score (EQS) is a 5-factor per-trade score (spread efficiency 0.30, slippage efficiency 0.25, commission efficiency 0.20, latency efficiency 0.15, swap efficiency 0.10) that rates how well each trade was executed relative to expectations. The Broker Quality Score (BQS) is a comparative ranking of all 6 supported brokers on their total cost, recomputed monthly and used for venue routing. Together, EQS and BQS provide a complete picture of execution quality — per-trade and per-broker.'))

    s.append(h1('Architecture Overview',2))
    s.append(p('The ECI is organized into 6 layers: cost measurement (5 real-time meters), cost model (aggregate total cost), decision model (edge calculator + size optimizer), performance scoring (EQS + variance tracker), broker quality scoring (BQS + learning engine), and audit/observability. All layers operate asynchronously except the decision model, which runs synchronously in the pre-trade path.'))
    s.append(diagram('d01_architecture.png',170))
    s.append(caption('Figure 2.1 — ECI architecture: 6 layers, 5 cost meters, decision model, scoring, and learning engine.'))

    s.append(PageBreak())

    s.append(h1('Decision Model',3))
    s.append(p('The decision model is the ECI\'s core. It computes the expected net edge for every signal and decides whether to trade, reduce size, or reject. The formula is simple but powerful: expected_edge = signal_edge - total_cost. If expected_edge <= 0, no trade. If 0 < expected_edge < min_edge (3.0 bps), reduce size. If expected_edge >= min_edge, full size.'))
    s.append(diagram('d02_decision.png',170))
    s.append(caption('Figure 3.1 — Decision model flowchart: signal edge → total cost → net edge → trade/reduce/reject.'))

    s.append(h2('Signal Edge Computation'))
    s.append(p('The signal edge is the expected profit from the trade, expressed in basis points. It is derived from the strategy\'s R-multiple target and the current ATR: signal_edge_bps = R_multiple × ATR / price × 10000. For example, a trend strategy targeting 1.5R with ATR=$2 and price=$1950 produces a signal edge of 1.5 × 2 / 1950 × 10000 = 15.4 bps. This is the gross edge before costs.'))

    s.append(h2('Total Cost Computation'))
    s.append(p('The total cost is the sum of 5 components, all normalized to bps: spread_bps + commission_bps + swap_bps + slippage_bps + latency_bps. Each component is measured or modeled in real-time, adjusted for the current regime and session, and made size-dependent where applicable (slippage increases with order size). The typical total cost for XAUUSD on a raw-spread broker with 0.5 lot and 4-hour holding is approximately 3.7 bps; on a standard broker it is approximately 8.0 bps.'))

    s.append(h2('Size Optimization'))
    s.append(p('When the net edge is positive but below the safety margin (0 < edge < 3.0 bps), the SizeOptimizer reduces the position size until the marginal cost equals the marginal edge. The formula: optimal_qty = max(0, (edge_bps - min_edge_bps) / slippage_slope). This ensures that the trade is still profitable after costs, but with a smaller position that has lower slippage impact.'))

    s.append(PageBreak())

    s.append(h1('5 Cost Components',4))
    s.append(p('All costs are normalized to basis points of notional, making them comparable across brokers, account types, and instruments. This normalization is the foundation of the ECI — without it, comparing a pip-based spread with a dollar-based commission would be impossible.'))
    s.append(diagram('d03_components.png',170))
    s.append(caption('Figure 4.1 — 5 cost components with formulas, ranges, and measurement methods.'))

    s.append(h2('C1: Spread'))
    s.append(p('spread_bps = (ask - bid) / mid × 10000. Measured from real-time tick data with 1000-tick rolling mean and standard deviation. Session-adjusted (spread is typically wider in Asia, tighter in London/NY overlap). Variable vs fixed detection: if sigma/mean < 0.05, spread is classified as FIXED; otherwise VARIABLE. Range: 0-1 bps (raw spread + commission) to 3-8 bps (standard mark-up) to 15-50 bps (during news events).'))

    s.append(h2('C2: Commission'))
    s.append(p('commission_bps depends on the commission type (from BrokerProfile, BCE Module 2): PER_MILLION (rate / 100), PER_LOT (rate / (price × contract_size) × 10000), PCT (rate × 100), or NONE (0). Typically stable unless the broker changes its fee schedule. The ECI detects silent fee changes by comparing realized commission against the BrokerProfile on every fill.'))

    s.append(h2('C3: Swap'))
    s.append(p('swap_bps = |swap_rate| × hold_hours / 24 × contract_size / price × 10000. Projected based on expected holding time (3-tier: 4h / 8h / overnight). Swap-free accounts (Exness) have 0 swap cost. For standard accounts, swap is typically 0.5-2.0 bps per 4 hours of holding. The ECI uses the strategy\'s expected hold time (from the R-multiple target and ATR) to project the swap cost.'))

    s.append(h2('C4: Slippage'))
    s.append(p('slippage_bps is size-dependent and modeled using one of three models: Linear (slip = lambda × qty / ADV, for small sizes), Square-Root Impact (slip = sigma × sqrt(qty / ADV), for medium sizes), or Learned (ML model trained on historical fills, for large sizes). Model selection is automatic based on order size and regime. The slippage model is continuously calibrated from realized fills via EMA updates.'))

    s.append(h2('C5: Latency'))
    s.append(p('latency_bps = price drift during the signal-to-fill latency = |delta_price| / price × 10000. Measured as the difference between the price at signal time and the price at fill time. The ECI tracks p50/p95/p99 latency per broker and converts it to a bps cost using the current volatility regime. Fast brokers (5ms) incur 0.1-0.5 bps; slow brokers (50ms) incur 2-5 bps.'))

    s.append(PageBreak())

    s.append(h1('Performance Scoring',5))
    s.append(p('The Execution Quality Score (EQS) is a 5-factor per-trade score that rates how well each trade was executed relative to expectations. Each factor compares the realized cost against the expected cost: 100 means the cost was exactly as expected, 0 means the cost was 2× expected.'))
    s.append(diagram('d04_scoring.png',170))
    s.append(caption('Figure 5.1 — EQS 5-factor model and BQS 6-broker comparative ranking.'))

    s.append(h2('EQS Formula'))
    s.append(code("""EQS = 0.30 × spread_eff + 0.25 × slip_eff + 0.20 × comm_eff
    + 0.15 × latency_eff + 0.10 × swap_eff

where each factor_i = 100 × max(0, 1 - realized_cost_i / expected_cost_i)

EQS bands:
  90-100: EXCELLENT (cost as expected)
  75-89:  GOOD (slightly above expected)
  60-74:  ACCEPTABLE (moderately above)
  40-59:  POOR (significantly above)
  0-39:   CRITICAL (auto-pause strategy)"""))

    s.append(h2('Cost Variance Tracker'))
    s.append(p('The CostVarianceTracker maintains rolling 100-trade statistics on the difference between expected and realized costs, decomposed by component. If the realized cost exceeds the expected cost by more than 2 standard deviations for any component, an alert is fired. This catches model degradation early — before it impacts the edge calculation enough to cause unprofitable trades.'))

    s.append(h1('Broker Quality Scoring',6))
    s.append(p('The Broker Quality Score (BQS) is a comparative ranking of all 6 supported brokers on their total execution cost, recomputed monthly. The broker with the lowest total cost receives the highest BQS. Signals are routed to the highest-BQS broker first, with failover to the next broker if the signal is rejected.'))
    s.append(p('Current BQS ranking (June 2026): IC Markets Raw (92), Pepperstone Razor (90), Tickmill VIP (89), FP Markets Raw (85), Fusion Zero (83), Exness Standard (72). The ranking reflects that raw-spread brokers with low commission (IC Markets, Pepperstone) offer the lowest total cost for active trading, while Exness Standard\'s zero-commission model is offset by its wider spread.'))

    s.append(PageBreak())

    s.append(h1('Validation Logic',7))
    s.append(p('The ECI performs 8 pre-trade validation checks and 6 post-trade verifications. Pre-trade checks reject trades with invalid cost estimates; post-trade checks alert when realized costs diverge from expectations. All checks are audited.'))
    s.append(diagram('d05_validation.png',170))
    s.append(caption('Figure 7.1 — 8 pre-trade checks + 6 post-trade verifications with thresholds and actions.'))

    s.append(h2('Key Pre-Trade Checks'))
    s.append(bullet('V1 Spread within expected range: spread_bps <= mu + 3sigma. Reject if spread is anomalously high (e.g., during news).'))
    s.append(bullet('V6 Expected edge > 0: signal_edge - total_cost > 0. Reject if costs exceed the signal edge (trade would lose money).'))
    s.append(bullet('V7 Expected edge > min_edge: net_edge > 3.0 bps. Reduce size if edge is positive but thin (below safety margin).'))
    s.append(bullet('V8 Broker BQS acceptable: broker BQS >= 60. Route to a higher-quality broker if current broker\'s score is too low.'))

    s.append(h2('Key Post-Trade Verifications'))
    s.append(bullet('V10 Realized slippage <= 1.5 × predicted. Alert if slippage model is underestimating (retrain needed).'))
    s.append(bullet('V12 Realized commission matches profile. Alert P1 if broker changed fees silently (fee integrity check).'))
    s.append(bullet('V14 EQS >= 40 (not CRITICAL). Alert P1 and auto-pause strategy if execution quality is unacceptable.'))

    s.append(PageBreak())

    s.append(h1('Cost Learning Engine',8))
    s.append(p('The Cost Learning Engine continuously updates cost models from realized fills. Every fill provides a data point: predicted vs realized slippage, expected vs actual latency, projected vs actual swap. The engine uses EMA updates (alpha=0.05) to calibrate per-broker, per-session, and per-regime models, ensuring that cost estimates become more accurate over time.'))
    s.append(diagram('d07_learning.png',170))
    s.append(caption('Figure 8.1 — Learning loop: fill arrives → compare expected vs realized → update models → better estimates next trade.'))

    s.append(h2('Model Calibration'))
    s.append(bullet('Slippage model: EMA update on (qty, realized_slip) pair. Per-broker × per-regime × per-session. 3 models: linear (small), sqrt-impact (medium), learned (large). MAPE target: <= 30%.'))
    s.append(bullet('Latency model: Rolling p50/p95/p99 per broker. Decomposed into internal latency (signal-to-dispatch) and broker latency (dispatch-to-fill). p99 within 1.5× of predicted.'))
    s.append(bullet('Spread model: Rolling mu, sigma (1000-tick window) per broker × per-session × per-regime. Detects spread widening patterns (pre-news, session open/close).'))

    s.append(h1('Validation Tests',9))
    s.append(p('The ECI is validated through 180 tests across 5 categories. Critical: no trade with negative edge, EQS >= 60 rolling average, realized cost <= 1.5× expected (95% of trades), BQS recomputed monthly.'))
    s.append(diagram('d06_tests.png',170))
    s.append(caption('Figure 9.1 — Test pyramid and sample test cases.'))

    s.append(h1('Integration with TITAN Core',10))
    s.append(p('The ECI integrates with 4 TITAN components: Broker Compatibility Engine (Module 2) for commission/swap/contract_size data, Execution Engine (Module 3) for fill callbacks and latency measurement, Risk Engine (Module 8) for risk_per_trade ceiling on size optimization, and Operator Console for real-time cost display. The ECI sits between the Strategy Coordinator and the Execution Engine in the signal path, adding a cost-awareness gate that rejects or size-adjusts signals before they reach the broker.'))
    s.append(code("""Signal from Strategy / AI Ensemble
  → ECI pre-trade check:
    → compute total_cost_bps (5 components)
    → compute expected_edge = signal_edge - total_cost
    → if edge <= 0: NO TRADE (audit: NEGATIVE_EDGE)
    → if 0 < edge < 3 bps: REDUCE SIZE (audit: THIN_EDGE)
    → if edge >= 3 bps: TRADE (full or optimized size)
    → select best broker (highest BQS)
    → risk gate check (Module 8)
    → if approved: emit cost-adjusted signal to Execution Engine
  → Post-trade: compare realized vs expected
    → update slippage/latency/spread models
    → compute EQS score
    → daily TCA report to operator"""))

    return s

def main():
    out = '/home/z/my-project/scripts/cost_intel/body.pdf'
    doc = TocDocTemplate(out, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=24*mm, bottomMargin=22*mm, title='TITAN XAU AI — Execution Cost Intelligence', author='TITAN Quant Research', subject='Execution Cost Intelligence: cost measurement, edge calculation, broker scoring', creator='TITAN Architecture Workbench')
    story = build_story()
    print(f'[build] Building body PDF with {len(story)} flowables...')
    doc.multiBuild(story, onFirstPage=hf, onLaterPages=hf)
    print(f'[build] Body PDF written: {out}')
    from pypdf import PdfReader; r = PdfReader(out); print(f'[build] Page count: {len(r.pages)}')

if __name__ == '__main__': main()
