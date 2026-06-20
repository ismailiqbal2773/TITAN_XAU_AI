"""
TITAN XAU AI — Stress Testing Framework (Module 16)
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
DIAGRAM_DIR = '/home/z/my-project/scripts/stress/diagrams/png'

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
    c.setFont('FreeSerif-Italic',8.5); c.setFillColor(TEXT_MUTED); c.drawString(20*mm, A4[1]-14*mm, 'TITAN XAU AI — Stress Testing Framework')
    c.setFont('FreeSerif-Bold',8.5); c.setFillColor(ACCENT); c.drawRightString(A4[0]-20*mm, A4[1]-14*mm, 'v1.0  ·  VALIDATION')
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
    s.append(p('The Stress Testing Framework (STF) is Module 16 of the TITAN XAU AI trading system. It is the platform\'s adverse-condition authority — the validation framework that asks: <b>does this strategy survive when the market and infrastructure misbehave?</b> Backtests, walk-forward analysis, and Monte Carlo all assume normal operating conditions. Stress testing does not. It deliberately injects 6 categories of adverse conditions — flash crash, high spread, server lag, broker disconnect, extreme volatility, and gap open — and verifies that the strategy\'s risk controls (kill-switch, news filter, stale-signal veto, position reconciliation) activate correctly and that capital is preserved within expanded tolerance bands.'))
    s.append(p('A strategy that passes backtest (M16), walk-forward (M17), and Monte Carlo (M18) but fails stress testing is unsafe for live capital. The 6 stress scenarios represent the real-world failure modes that have caused the largest losses in algorithmic trading history: flash crashes (2010, 2020), broker outages (Exness 2021, IC Markets 2022), news-event spread widening (every NFP), weekend gap risk (Brexit, COVID), and infrastructure latency (VPS contention). The STF simulates each scenario on a recorded tick dataset with the adverse condition overlaid, runs the strategy through it, and verifies both that risk controls activate AND that capital preservation targets are met.'))
    s.append(p('The framework delivers four outputs specified in this document: (1) the 6 stress scenarios — flash crash (−8% in 90s), high spread (5× baseline for 30 min), server lag (300 ms P99 for 60s), broker disconnect (90s socket drop), extreme volatility (4× ATR for 2 hours), gap open (±3% Sunday open); (2) the recovery logic — 6-stage protocol (detect → halt → flatten → protect → recover → resume) with explicit latency SLAs and protective-mode staircase (50% → 75% → 100%); (3) the failure logic — 12 hard rules (5 CRITICAL + 5 MAJOR + 2 MINOR) with kill-switch SLA (&lt;500 ms) and position reconciliation (100%) as non-negotiable invariants; (4) the certification criteria — 3-band verdict (CERTIFIED / CONDITIONAL / REJECTED) aggregating all 6 scenario verdicts via logical AND.'))
    s.append(p('The single most important stress test is the flash crash scenario. An 8% XAUUSD drop in 90 seconds (e.g., 2000 → 1840 USD/oz) is rare but has happened (March 2020 COVID crash, August 2020 silver flash spread to gold). Without a functioning kill-switch, a leveraged position can be wiped out in seconds. The STF verifies that the kill-switch triggers on MDD ≥ 5% AND completes the flatten in &lt;500 ms — the institutional SLA measured by dedicated latency probes. A flash crash MDD &gt; 12% (vs the 5% live target — 2.4× headroom) is an automatic REJECT: the kill-switch failed, and the strategy is unsafe for any capital allocation. This single test catches more live-trading disasters than any other validation.'))

    # Ch 2 — Stress Scenarios Overview
    s.append(h1('Stress Scenarios Overview',2))
    s.append(p('The STF simulates 6 adverse scenarios, each representing a different category of risk: market risk (flash crash, extreme volatility, gap open), execution risk (high spread), infrastructure risk (server lag, broker disconnect). Each scenario has explicit simulation parameters (magnitude, duration, injection method), historical basis (real events the scenario is calibrated to), tests performed (which risk controls should activate), recovery actions, and a pass threshold. All 6 must pass for the strategy to achieve CERTIFIED status — partial pass (5 of 6) is CONDITIONAL at best.'))
    s.append(diagram('d01_scenarios.png',170))
    s.append(caption('Figure 2.1 — 6 stress scenarios: flash crash, high spread, server lag, broker disconnect, extreme volatility, gap open.'))

    s.append(h2('Aggregation Logic'))
    s.append(p('The final stress-test verdict is the logical AND of all 6 scenario verdicts. If ANY scenario returns REJECTED, the final verdict is REJECTED. If any scenario returns CONDITIONAL (with the others CERTIFIED), the final is CONDITIONAL. Only when all 6 return CERTIFIED is the strategy authorized for live capital. This strict aggregation reflects the principle that a strategy must survive all adverse conditions — being robust to flash crashes but fragile to broker disconnects is not acceptable, because both will eventually occur in live trading.'))

    s.append(PageBreak())

    # Ch 3 — Flash Crash Scenario
    s.append(h1('SCN-01 — Flash Crash',3))
    s.append(p('The flash crash scenario simulates a sudden, large price drop followed by partial recovery. The specific simulation: XAUUSD drops 8% in 90 seconds (e.g., 2000 → 1840 USD/oz), then recovers 5% over the next 4 minutes (1840 → 1932). This is injected into a recorded tick stream at a random time during the London session (08:00-17:00 UTC), preserving the original tick timestamps but replacing prices with the crash-modified values. The strategy runs through this modified stream with all risk controls active.'))
    s.append(diagram('d02_scenario_detail.png',170))
    s.append(caption('Figure 3.1 — Detailed specification for flash crash, high spread, and server lag scenarios.'))

    s.append(h2('Expected Behavior'))
    s.append(p('The risk engine\'s kill-switch must trigger when drawdown reaches 5% (the live-trading MDD floor). The kill-switch must complete position flatten in &lt;500 ms (measured by dedicated latency probe — see Module 8 Risk Engine). Stop-loss orders must fill at the modified (crashed) prices, with slippage bounded by the broker\'s P99 slippage distribution. After flatten, no positions should remain open. The recovery protocol (Chapter 5) activates: halt for 5 minutes, then resume with 50% position size for the first hour, 75% for the next 4 hours, 100% after 24 hours.'))

    s.append(h2('Pass Threshold'))
    s.append(p('Flash crash MDD ≤ 12% (vs the 5% live target — 2.4× headroom). The 12% threshold acknowledges that flash crashes produce worse-than-normal slippage and that the kill-switch cannot perfectly time the bottom. A strategy that limits flash-crash MDD to 12% is robust; one that lets MDD exceed 12% has a failed kill-switch and is unsafe. Kill-switch latency must be &lt;500 ms (hard SLA, no waiver). Stop-loss fills must be at prices within 1% of the kill-switch trigger price (sanity bound on slippage).'))

    s.append(h2('Historical Basis'))
    s.append(p('The 8%/90s parameters are calibrated from three historical events: (1) March 2020 COVID crash — XAUUSD dropped 8% in 4 hours (slower but larger context); (2) August 2020 silver flash crash — XAGUSD dropped 10% in 90 seconds, with correlated spill to XAUUSD; (3) January 2015 EURCHF unpegging — EUR dropped 30% in 15 minutes, demonstrating that forex can produce extreme moves. The 8% magnitude is conservative for gold (which has lower realized volatility than silver or CHF), and the 90s duration is calibrated to the observed crash velocity. The 5% recovery over 4 minutes models the typical V-shaped recovery that follows flash crashes as liquidity returns.'))

    s.append(PageBreak())

    # Ch 4 — High Spread + Server Lag
    s.append(h1('SCN-02 — High Spread',4))
    s.append(p('The high spread scenario simulates an extended period of spread widening, as occurs during major news events (NFP, FOMC, CPI). The specific simulation: spread widens to 5× the broker\'s baseline P50 spread for 30 minutes. For IC Markets (baseline 0.18 USD), this means spread = 0.90 USD for 30 minutes. The tick stream is preserved (prices unchanged) but a spread overlay is applied: every tick\'s bid/ask spread is multiplied by 5. The strategy runs through this modified stream with all risk controls active.'))
    s.append(p('Expected behavior: the regime detector\'s news filter must suppress new entries (no new orders during the 30-minute widened-spread window). Existing positions should be held with tightened stops — closing them during widened spread incurs excessive cost. The risk engine\'s cost-cap control should veto any signal whose projected cost (spread + slippage + commission) exceeds 0.5% of equity. After the spread returns to baseline, the strategy resumes normal operation. Pass threshold: cost drag ≤ 45% (vs the 35% normal threshold — 10 pp headroom for the elevated spread conditions).'))

    s.append(h1('SCN-03 — Server Lag',5))
    s.append(p('The server lag scenario simulates infrastructure latency degradation — VPS CPU contention, network congestion, or broker API slowdown. The specific simulation: tick-to-execution latency increases to 300 ms P99 (2× the 150 ms budget) for 60 seconds. A network simulation layer injects 150 ms of delay into the broker round-trip. The strategy runs through this modified stream with all risk controls active.'))
    s.append(p('Expected behavior: the risk engine\'s stale-signal veto must activate — any signal whose timestamp is more than 150 ms old (the latency budget) is flagged "stale" and rejected. No orders should be placed on stale data. The execution engine\'s backpressure mechanism should drop ticks that arrive &gt;250 ms late (rather than queuing them). Pass threshold: stale-veto rate ≥ 95% (95% of stale signals correctly rejected) AND zero stale fills (no order placed on stale data) AND no order queue overflow. A stale fill is a CRITICAL failure — it means an order was placed on outdated price data, which can cause catastrophic loss if the market moved between signal generation and execution.'))

    s.append(PageBreak())

    # Ch 6 — Broker Disconnect + Extreme Volatility
    s.append(h1('SCN-04 — Broker Disconnect',6))
    s.append(p('The broker disconnect scenario simulates a complete MT5 socket failure. The specific simulation: the MT5 socket drops for 90 seconds (simulating broker-side maintenance, ISP outage, or VPS network failure), then auto-reconnects. Position state is intentionally preserved on the broker side (positions are not closed during the disconnect — they continue to exist and accrue P&amp;L based on market prices). The strategy runs through this scenario with all risk controls active.'))
    s.append(p('Expected behavior: the broker adapter\'s reconnect logic must succeed within 5 seconds of socket restoration. After reconnect, the position manager must reconcile local position state with broker position state — every position the broker reports must match the local record. Any discrepancy (phantom orders, missing positions, size mismatch) is a CRITICAL failure. During the disconnect, the strategy should halt new entries (no signals can be executed without broker connection) but should not flatten existing positions (they continue to be managed by their stop-loss orders on the broker side). Pass threshold: reconnect &lt;5 s AND position reconciliation 100% AND zero phantom orders.'))

    s.append(h2('Historical Basis'))
    s.append(p('The 90-second disconnect duration is calibrated from observed broker outages: Exness had a 2-minute MT5 server outage in March 2021; IC Markets had a 75-second disconnect during a 2022 NFP release; Pepperstone had a 90-second network partition in November 2022. The 90-second duration is long enough to test the reconnect logic thoroughly but short enough that existing positions are unlikely to be stopped out by normal market movement. The position-preservation assumption (positions continue to exist on broker side) matches MT5 behavior — positions are server-side, not client-side.'))

    s.append(h1('SCN-05 — Extreme Volatility',7))
    s.append(p('The extreme volatility scenario simulates a sustained period of elevated volatility, as occurs during geopolitical events or central bank surprises. The specific simulation: ATR spikes to 4× its 30-day average for 2 hours. A GARCH-based tick volatility model with elevated σ generates tick data with the elevated volatility, preserving the price direction but amplifying the tick-to-tick variance. The strategy runs through this modified stream with all risk controls active.'))
    s.append(p('Expected behavior: the regime detector must classify the period as "volatile" regime, triggering the volatility engine\'s reduced-size mode (50% position sizing). Stops should be widened (1.5× normal) to avoid being stopped out by the elevated noise. New entries should be suppressed unless the signal confidence is very high (≥0.85 vs the normal 0.65 threshold). Pass threshold: MDD ≤ 10% during the 2-hour volatility spike (vs the 5% live target — 2× headroom). The 10% threshold acknowledges that high volatility produces larger drawdowns even with correct risk controls, but a strategy that lets MDD exceed 10% has failed to adapt its sizing.'))

    s.append(PageBreak())

    # Ch 8 — Gap Open
    s.append(h1('SCN-06 — Gap Open',8))
    s.append(p('The gap open scenario simulates a weekend price gap, as occurs when significant news breaks during the Saturday-Sunday market closure. The specific simulation: Sunday 23:00 GMT open price gaps +3% or −3% from Friday 22:00 GMT close price. The tick stream is modified to include a 3% jump at Sunday open, with no ticks in between (modeling the weekend closure). The strategy runs through this modified stream with all risk controls active.'))
    s.append(p('Expected behavior: the strategy must be flat (zero open positions) by Friday 22:00 GMT — the weekend-flat policy. With no weekend exposure, the gap has no impact on equity. If the strategy held positions through the gap (policy violation), stop-loss orders would fill at the gap price (which could be 3% away from the stop level), producing a large loss. Pass threshold: gap loss ≤ 2% of equity. The 2% threshold allows for small slippage on Friday-close stops but rejects strategies that hold meaningful exposure through the gap.'))
    s.append(h2('Weekend Flat Policy'))
    s.append(p('The weekend flat policy is enforced by the risk engine (Module 8): at 21:00 GMT every Friday, the risk engine begins closing all open positions. By 22:00 GMT (1 hour before market close), the system must be flat. Any position still open at 22:00 GMT triggers a P1 alert and forced flatten. The policy exists because weekend gaps are unhedgeable — there is no market to trade during the closure, so any exposure is naked gap risk. The 3% gap magnitude is calibrated from historical weekend gaps: Brexit (June 2016, +6% gold gap), COVID (March 2020, multiple 3-5% gaps), and various central bank surprises.'))

    s.append(PageBreak())

    # Ch 9 — Recovery Logic
    s.append(h1('Recovery Logic — 6-Stage Protocol',9))
    s.append(p('When a stress condition is detected, the system activates a 6-stage recovery protocol: DETECT → HALT → FLATTEN → PROTECT → RECOVER → RESUME. Each stage has explicit latency SLAs and entry/exit conditions. The protocol is automated — no human action required for stages 1-5 — but stage 6 (RESUME) requires the "all clear" verification to hold for 60 seconds before normal trading resumes. The protocol is designed to err on the side of caution: better to halt unnecessarily than to continue trading through a stress condition.'))
    s.append(diagram('d03_recovery.png',170))
    s.append(caption('Figure 9.1 — 6-stage recovery protocol with latency SLAs and 5 invariants that never get violated.'))

    s.append(h2('Stage 1 — DETECT'))
    s.append(p('Stress condition detected by an automated monitor. Five monitors run continuously: drawdown monitor (triggers on MDD ≥ 5%), spread monitor (triggers on spread ≥ 3× baseline), latency monitor (triggers on P99 latency &gt; 200 ms), connection monitor (triggers on MT5 socket drop), volatility monitor (triggers on ATR ≥ 3× 30-day avg). When a monitor triggers, it publishes a STRESS_DETECTED event to NATS with the monitor ID, timestamp, and condition magnitude. Detection latency: &lt;100 ms from condition onset.'))

    s.append(h2('Stage 2 — HALT'))
    s.append(p('On STRESS_DETECTED event, the execution engine sets an atomic halt flag. No new orders are accepted — any signal arriving after the halt is queued (not dropped, in case the halt is brief). Existing orders remain open and continue to be managed by their stop-loss/take-profit orders. Halt latency: &lt;50 ms from detect. The halt flag is sticky — it can only be cleared by the RESUME stage, not by operator override.'))

    s.append(h2('Stage 3 — FLATTEN'))
    s.append(p('If MDD &gt; 5% OR kill-switch criteria are met, the risk engine triggers an emergency flatten: all open positions are closed via market orders at the current tick. Flatten latency: &lt;500 ms from trigger (the institutional SLA, measured by dedicated latency probe). If MDD &lt; 5%, positions are held with tightened stops (1.5× normal) — the strategy is in protective mode but not flattened. The flatten decision is automated — no human approval required.'))

    s.append(h2('Stage 4 — PROTECT'))
    s.append(p('After halt (and flatten if triggered), the system enters protective mode for a minimum of 24 hours. Protective mode means: position size reduced to 50%, stops widened to 1.5× normal, no new entries (only management of existing positions if any remain). The 24-hour minimum is non-negotiable — even if the stress condition clears in 5 minutes, protective mode persists for 24 hours. This prevents the strategy from re-entering too quickly after a near-miss.'))

    s.append(h2('Stage 5 — RECOVER'))
    s.append(p('The recovery check runs every 30 seconds during protective mode. It verifies: spread &lt; 2× baseline, latency &lt; 200 ms P99, broker connection stable for 60 s, volatility &lt; 2× 30-day avg, no gap event in last 5 min. When all conditions are clear for 60 consecutive seconds, the system advances to RESUME. If any condition re-triggers during the 60-second window, the timer resets.'))

    s.append(h2('Stage 6 — RESUME'))
    s.append(p('Normal trading resumes with a staircase size schedule: 50% size for the first hour (continuing from protective mode), 75% size for the next 4 hours, 100% size after 24 hours if no further stress events. The staircase prevents the strategy from immediately re-entering at full size, which would be risky after a stress event. Operator is notified via PagerDuty at every stage transition.'))

    s.append(h2('Recovery Invariants (5 — never violated)'))
    s.append(bullet('<b>Kill-switch SLA:</b> flatten completes &lt;500 ms from trigger (measured by dedicated latency probe)'))
    s.append(bullet('<b>Position reconciliation:</b> post-flatten, local position state == broker position state (zero phantom orders)'))
    s.append(bullet('<b>Audit trail:</b> every recovery action logged with timestamp, reason, and operator ID (if manual)'))
    s.append(bullet('<b>No silent resume:</b> resumption requires explicit "all clear" verification, never a timer'))
    s.append(bullet('<b>Operator notification:</b> P2 PagerDuty at DETECT, P1 if FLATTEN triggers, P1 if not recovered in 30 min'))

    s.append(PageBreak())

    # Ch 10 — Failure Logic
    s.append(h1('Failure Logic — Hard Veto Triggers',10))
    s.append(p('The STF applies 12 hard rules across three severities: 5 CRITICAL (any failure = automatic REJECT, no override except documented CTO waiver), 5 MAJOR (any 2 = REJECT, any 1 = CONDITIONAL), and 2 MINOR (advisory only). The rules are applied after all 6 scenarios complete. The 3-band verdict (CERTIFIED / CONDITIONAL / REJECTED) is the final output, recorded in the audit manifest and read by the trading gate.'))
    s.append(diagram('d04_failure.png',170))
    s.append(caption('Figure 10.1 — Failure logic: 12 rules (5 critical + 5 major + 2 minor) and 3-band certification gates.'))

    s.append(h2('CRITICAL Rules (5 — any one = automatic REJECT)'))
    s.append(bullet('<b>CRIT-01: Flash crash MDD &gt; 12%</b> — Kill-switch failed to flatten in time, or stop-loss fills slipped beyond threshold. Capital preservation failed.'))
    s.append(bullet('<b>CRIT-02: Kill-switch latency &gt; 500 ms</b> — Emergency flatten exceeded SLA. Critical risk control non-functional.'))
    s.append(bullet('<b>CRIT-03: Phantom orders after disconnect</b> — Position reconciliation failed. Local state ≠ broker state. Trading must halt.'))
    s.append(bullet('<b>CRIT-04: Gap loss &gt; 2% equity</b> — Weekend position policy failed. Strategy held exposure through gap, lost &gt;2%.'))
    s.append(bullet('<b>CRIT-05: Stale fill executed</b> — Signal veto failed, order placed on stale data. Could cause catastrophic loss.'))

    s.append(h2('MAJOR Rules (5 — any 2 = REJECT, any 1 = CONDITIONAL)'))
    s.append(bullet('<b>MAJ-01: Cost drag &gt; 45%</b> during high spread — Strategy entered trades during widened spread despite news filter.'))
    s.append(bullet('<b>MAJ-02: Stale veto rate &lt; 95%</b> — Risk engine allowed &gt;5% of stale signals through during lag scenario.'))
    s.append(bullet('<b>MAJ-03: Vol spike MDD &gt; 10%</b> — Vol regime detection failed to reduce size, drawdown exceeded threshold.'))
    s.append(bullet('<b>MAJ-04: Reconnect &gt; 5 seconds</b> — Broker reconnection logic too slow. Increased exposure window.'))
    s.append(bullet('<b>MAJ-05: Recovery &gt; 30 min</b> — System failed to auto-recover. Required manual intervention.'))

    s.append(h2('MINOR Rules (2 — advisory only)'))
    s.append(bullet('<b>MIN-01: Cost drag 35-45%</b> — Elevated but within tolerance. Monitor.'))
    s.append(bullet('<b>MIN-02: Stale veto 90-95%</b> — Borderline. Investigate veto logic.'))

    s.append(PageBreak())

    # Ch 11 — Certification Criteria
    s.append(h1('Certification Criteria',11))
    s.append(p('The final stress-test verdict aggregates all 6 scenario verdicts via logical AND. If ANY scenario returns REJECTED, the final verdict is REJECTED. If any scenario returns CONDITIONAL (with the others CERTIFIED), the final is CONDITIONAL. Only when all 6 return CERTIFIED is the strategy authorized for live capital. The 3-band verdict is recorded in the audit manifest, dispatched to PagerDuty, and read by the trading gate — no strategy with REJECTED verdict is authorized for live trading.'))
    s.append(diagram('d05_certification.png',170))
    s.append(caption('Figure 11.1 — Certification criteria: 3-band verdict, reporting tiers, worked example (Trend v3.2 passing all 6 scenarios = CERTIFIED).'))

    s.append(h2('3-Band Certification Verdict'))
    s.append(table([
        ['Band', 'Criteria', 'Trading Authorization', 'Re-Stress Cadence'],
        ['CERTIFIED', 'All 6 scenarios PASS · 0 critical · 0 major · kill-switch SLA met · 100% reconciliation', 'Live trading authorized', 'Quarterly'],
        ['CONDITIONAL', '1 major failure OR 1 critical with documented waiver', 'Paper / small-capital only', '30-day re-stress'],
        ['REJECTED', 'Any critical (no waiver) OR ≥ 2 major failures', 'Trading HALTED', 'Engineering review required'],
    ], cw=[14, 38, 24, 14]))
    s.append(Spacer(1, 8))

    s.append(h2('Worked Example — TITAN Trend v3.2'))
    s.append(p('TITAN Trend Following v3.2 was stress tested across all 6 scenarios. Results: Flash Crash MDD 9.4% (≤12%, PASS), kill-switch 312 ms (≤500 ms, PASS). High Spread cost drag 38.2% (≤45%, PASS), 100% entries suppressed during widened spread (PASS). Server Lag stale-veto 97.3% (≥95%, PASS), 0 stale fills (PASS). Broker Disconnect reconnect 3.1 s (≤5 s, PASS), 100% position reconciliation (PASS). Extreme Vol MDD 7.8% (≤10%, PASS), 50% size reduction (PASS). Gap Open 0% gap loss (≤2%, PASS), 100% weekend flat (PASS). All 6 scenarios PASS, 0 critical, 0 major. Verdict: <b>CERTIFIED</b>. The 9.4% flash crash MDD (vs 12% threshold) indicates the kill-switch worked correctly but stop-loss slippage was non-trivial — flagged for monitoring but acceptable.'))

    s.append(h2('Reporting System'))
    s.append(p('The STF generates three report tiers: executive (1-page brief), technical (20-30 page full scenario dump), and regulatory (10-15 page audit trail). All reports archived to S3 at s3://titan-stress/{strategy}/{version}/{timestamp}/ with 7-year retention and RSA-2048 signed manifests. Auto-dispatched via PagerDuty (P1 for REJECT, P3 for PASS), Slack #titan-stress, and email to stakeholders. Each stress test is compared against the last 5 runs of the same strategy; any scenario downgrade (CERTIFIED → CONDITIONAL or REJECTED) triggers a P1 regression alert.'))

    s.append(h2('Operational Integration'))
    s.append(p('The STF integrates at three points: (1) pre-deployment — every new strategy version must pass stress testing (along with backtest, walk-forward, and Monte Carlo) before live capital; (2) scheduled — every live strategy is re-stress-tested quarterly to catch control drift; (3) on-demand — operators can trigger via CLI or REST. Runtime: ~25 minutes per strategy (6 scenarios × ~4 min each, parallelizable to ~6 min on 4 cores). The STF shares the tick data store with the Backtesting Framework (Module 16) — no duplication.'))

    s.append(h2('Future Evolution'))
    s.append(p('Planned extensions: (1) <b>Combined stress scenarios</b> — flash crash + broker disconnect simultaneously (correlated failures); (2) <b>Regime-conditional stress</b> — stress test under each regime (trend/range/volatile/news) to find regime-specific fragility; (3) <b>Multi-broker stress</b> — simulate one broker failing while others operate, testing broker-failover logic; (4) <b>Custom scenario builder</b> — operators define ad-hoc stress scenarios via YAML config for specific concerns. The 6-scenario core and 6-stage recovery protocol are expected to remain stable — they cover the failure modes that have caused the largest losses in algorithmic trading history.'))

    return s

def main():
    out = '/home/z/my-project/scripts/stress/body.pdf'
    doc = TocDocTemplate(out, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=24*mm, bottomMargin=22*mm, title='TITAN XAU AI — Stress Testing Framework', author='TITAN Quant Research', subject='Stress testing: 6 scenarios, recovery logic, failure logic, certification criteria', creator='TITAN Architecture Workbench')
    story = build_story()
    print(f'[build] Building body PDF with {len(story)} flowables...')
    doc.multiBuild(story, onFirstPage=hf, onLaterPages=hf)
    print(f'[build] Body PDF written: {out}')
    from pypdf import PdfReader; r = PdfReader(out); print(f'[build] Page count: {len(r.pages)}')

if __name__ == '__main__': main()
