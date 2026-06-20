"""
TITAN XAU AI — Production Readiness Review (Module 17)
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
DIAGRAM_DIR = '/home/z/my-project/scripts/readiness/diagrams/png'

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
    c.setFont('FreeSerif-Italic',8.5); c.setFillColor(TEXT_MUTED); c.drawString(20*mm, A4[1]-14*mm, 'TITAN XAU AI — Production Readiness Review')
    c.setFont('FreeSerif-Bold',8.5); c.setFillColor(ACCENT); c.drawRightString(A4[0]-20*mm, A4[1]-14*mm, 'v1.0  ·  AUDIT')
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
    s.append(p('This Production Readiness Review (PRR) is Module 17 of the TITAN XAU AI trading system. It is the institutional gate that determines whether the system is authorized for live capital deployment. The review covers all 16 previously delivered architecture modules across 13 validation categories: code review, security review, performance review, memory leak analysis, latency analysis, unit tests, integration tests, regression tests, backtests, walk-forward tests, Monte Carlo tests, stress tests, and broker compatibility tests. Each category is scored on a 0-100 scale with a strict 90/100 minimum threshold — any category below 90 blocks release.'))
    s.append(p('The verdict is <b>CONDITIONAL APPROVAL — NOT YET PRODUCTION READY</b>. The architecture is institutionally rigorous: 10 of 13 categories score ≥ 90/100, with the Risk Engine (94.6 module avg), Validator (94.5), Backtesting (94.0), and Licensing (93.3) modules demonstrating best-in-class design. The aggregate weighted score is 91.0/100 — above the 90/100 institutional threshold. However, 4 categories fall below threshold (C1 Code Review 88, C4 Memory Leak 87, C6 Unit Tests 86, C7 Integration Tests 85), and 7 critical issues must be resolved before PRODUCTION READY status can be granted. Per the institutional rule "do not approve release until all critical issues are fixed," release is BLOCKED.'))
    s.append(p('The root cause is uniform across all below-threshold categories: the TITAN system exists as 16 architecture specification documents, not as implemented production code. The specifications are rigorous — they define 20 core modules, 5 AI components, 4 regime targets, 6 supported brokers, 6 account types, 6 NFRs, 7 diagram types, 5 validation frameworks, and 3-band certification across every framework. But specifications alone cannot be deployed to production. The 16-week remediation roadmap (Chapter 14) converts specifications to validated code in 4 phases, after which a re-review will determine if PRODUCTION READY can be granted. Estimated date for PRODUCTION READY: <b>Week 17 (October 2026)</b> if remediation stays on schedule.'))
    s.append(p('This review is intentionally harsh. Institutional trading systems operate with real capital under regulatory scrutiny — a single critical defect can produce seven-figure losses and reputational damage that takes years to repair. The 90/100 threshold and "fix all critical issues" rule exist precisely to prevent the deployment of systems that look good on paper but fail in production. The TITAN architecture passes the design bar; the implementation must now meet the same bar. Until it does, no live capital is authorized. Paper trading and small-capital forward testing may proceed during remediation, but no live trading.'))

    # Ch 2 — Review Framework
    s.append(h1('Review Framework',2))
    s.append(p('The review framework evaluates each of the 16 modules across 13 categories, producing 208 individual scores (16 × 13, with some N/A cells where a category does not apply to a module). Each category has explicit evaluation criteria, scoring rubric, and threshold. The 13 categories are organized in 2 groups: Group A (Design &amp; Code, 5 categories: C1-C5) evaluates the architecture and engineering rigor; Group B (Tests &amp; Validation, 8 categories: C6-C13) evaluates the testing and validation coverage. The aggregate score is the weighted average across all 13 categories, with Group A weighted 40% and Group B weighted 60% (testing is weighted heavier because it is the ultimate proof of correctness).'))
    s.append(diagram('d01_overview.png',170))
    s.append(caption('Figure 2.1 — Production readiness review framework: 13 categories, 2 groups, 90/100 threshold, 3-band verdict.'))

    s.append(h2('Scoring Rubric'))
    s.append(table([
        ['Score Band', 'Verdict', 'Action'],
        ['≥ 95', 'STRONG PASS', 'No action required · monitor'],
        ['90-94', 'PASS', 'Meets threshold · minor improvements tracked'],
        ['85-89', 'CONDITIONAL', 'Below threshold · must reach 90 within remediation window'],
        ['80-84', 'WEAK', 'Below threshold · significant work required'],
        ['< 80', 'FAIL', 'Automatic veto · fundamental rework needed'],
    ], cw=[14, 18, 68]))
    s.append(Spacer(1, 8))

    s.append(h2('Critical Issue Definition'))
    s.append(p('A critical issue is any finding that, if unresolved, would cause capital loss, regulatory violation, or system unavailability in production. Critical issues are not advisory — they are release blockers. The 7 critical issues identified in this review (Chapter 11) all stem from the implementation gap: the system is specified but not built. Until code exists, is tested, and passes all 5 validation frameworks on real data, the system cannot be certified PRODUCTION READY. The "fix all critical issues" rule is non-negotiable: no waiver, no override, no exceptions.'))

    s.append(PageBreak())

    # Ch 3 — Per-Module × Per-Category Matrix
    s.append(h1('Per-Module × Per-Category Scoring Matrix',3))
    s.append(p('The matrix below shows the score for each of the 16 modules across each of the 13 categories. Cells are color-coded by score band. N/A cells indicate categories that do not apply to a module (e.g., Backtest module does not need to pass Walk-Forward — WFA runs backtests, not the other way around). The rightmost column shows the module\'s average score across applicable categories. The bottom row shows each category\'s average across all modules.'))
    s.append(diagram('d02_matrix.png',170))
    s.append(caption('Figure 3.1 — 16 modules × 13 categories scoring matrix. 4 categories below 90 threshold (C1, C4, C6, C7) — all driven by implementation gap.'))

    s.append(h2('Module-Level Observations'))
    s.append(p('The highest-scoring modules are M08 Risk Engine (94.6), M15 Validator (94.5), M16 Backtesting (94.0), M14 Licensing (93.3), and M13 Auto Retraining (92.3) — these modules have the most rigorous specifications with explicit formulas, worked examples, and clear pass/fail criteria. The lowest-scoring modules are M06 Mean Reversion (86.5) and M12 RL Trade Management (86.5) — these modules have thinner specifications with less explicit validation criteria. The remediation roadmap (Chapter 14) prioritizes strengthening the lower-scoring module specs during Phase 1-2, alongside the actual code implementation.'))

    s.append(h2('Category-Level Observations'))
    s.append(p('The 4 below-threshold categories (C1 Code Review 88, C4 Memory Leak 87, C6 Unit Tests 86, C7 Integration Tests 85) all share the same root cause: no actual code exists. Code review cannot pass on specs alone; memory leak analysis requires running code under Valgrind/ASan; unit and integration tests require code to test. Once Phase 1-3 of the remediation roadmap delivers the code, these 4 categories should rise to 92-95 (the underlying design is sound). The 9 above-threshold categories validate that the architecture itself is institutionally sound — the spec quality is high enough that implementation should be straightforward.'))

    s.append(PageBreak())

    # Ch 4 — Code Review (C1)
    s.append(h1('C1 — Code Review (88/100)',4))
    s.append(p('The code review evaluates architecture specification quality, design pattern appropriateness, cross-module consistency, and implementation readiness. The score of 88 reflects strong design (patterns, layering, UML) but cannot reach 90+ without actual code to review. The 3 findings below identify specific spec gaps that should be closed during Phase 1 implementation.'))
    s.append(diagram('d04_code_security.png',170))
    s.append(caption('Figure 4.1 — C1 Code Review (88) and C2 Security Review (94) findings with severity.'))

    s.append(h2('Findings (C1)'))
    s.append(p('<b>C1-F01 [CRITICAL]: No implementation code exists.</b> 16 specs, zero lines of code. Cannot pass code review on specs alone. Phase 1-3 implementation required. This is the single largest gap in the entire review.'))
    s.append(p('<b>C1-F02 [MAJOR]: Cross-module ID consistency.</b> Module 1 v2.0 lists M01-M20, but only 16 documents were delivered. The numbering has gaps (M02 Market Data, M07 Volatility, M12 RL Trade Mgmt, M19 Stress are referenced but not all have dedicated specs). Reconcile numbering during Phase 1.'))
    s.append(p('<b>C1-F03 [MAJOR]: PyO3 bridge spec underspecified.</b> Module 1 mentions PyO3 for C++/Python interop but no dedicated spec exists for the bridge. Data structures crossing the boundary, ownership semantics, and error propagation need explicit specification. Add as Module 1.5 (Bridge) during Phase 1.'))
    s.append(p('<b>C1-F04 [MINOR]: Worked examples use illustrative data.</b> Trend v3.2 metrics (Sharpe 2.28, MDD 8.4%, etc.) are plausible but not from real backtests. Acceptable for spec; must replace with real metrics during Phase 3 validation.'))
    s.append(p('<b>C1-F05 [PASS]: Design patterns well-chosen.</b> Strategy (regime-mapped selection), Adapter (broker abstraction), Observer (NATS events), Decorator (risk controls), Factory (model instantiation), State (risk modes), Command (orders). All appropriate. UML class diagrams in Module 1 v2.0 show mature design.'))
    s.append(p('<b>C1-F06 [PASS]: Layered architecture is sound.</b> L1-L4 layering with strict dependency direction. No circular dependencies. Initialization order explicit. Foundation modules (L1) can be tested and deployed independently of higher layers.'))

    s.append(PageBreak())

    # Ch 5 — Security Review (C2)
    s.append(h1('C2 — Security Review (94/100)',5))
    s.append(p('The security review evaluates defense-in-depth design, cryptographic stack, authentication/authorization, anti-tamper defense, and audit trail. The score of 94 reflects strong security design with 2 critical findings (HSM not provisioned, SOC2 audit not initiated) that must be resolved before production. The crypto stack (RSA-4096 + AES-256-GCM + TLS 1.3 + SHA-256) is industry standard, and the 5-layer anti-tamper defense is robust.'))
    s.append(h2('Findings (C2)'))
    s.append(p('<b>C2-F01 [CRITICAL]: HSM not provisioned.</b> Spec requires AWS KMS HSM-backed RSA-4096 for license signing. Not provisioned. Cannot issue production JWTs. This is CRIT-05 in the critical issues list. Fix: provision AWS KMS custom key store, generate RSA-4096 key, embed public key in client binary at build time. Verification: HSM-backed signing verified, key rotation tested, private key never leaves HSM.'))
    s.append(p('<b>C2-F02 [CRITICAL]: SOC2 audit not initiated.</b> Spec commits to annual SOC2 audit by 3rd party. No auditor engaged. Required for institutional licensee trust. This is CRIT-07. Fix: engage 3rd-party SOC2 auditor, complete Type I audit (3 months), then Type II (12 months monitoring). Verification: SOC2 Type I report issued, Type II monitoring started.'))
    s.append(p('<b>C2-F03 [MAJOR]: mTLS cert rotation unverified.</b> Spec says 90-day cert rotation for internal mTLS. Rotation automation not implemented. Manual rotation risk. Fix: implement cert-manager with automatic rotation, alert on rotation failure. Verification: 90-day rotation cycle tested, zero manual interventions.'))
    s.append(p('<b>C2-F04 [MINOR]: Pen test not scheduled.</b> Spec recommends annual penetration test by 3rd party. Not yet scheduled. Plan for Q3 2026. Fix: engage pen testing firm, schedule annual test. Verification: pen test report received, all critical findings remediated.'))
    s.append(p('<b>C2-F05 [PASS]: Crypto stack is sound.</b> RSA-4096 for license signing (HSM-backed), AES-256-GCM for at-rest encryption (key derived from hardware fingerprint via PBKDF2), TLS 1.3 for transport, SHA-256 for fingerprinting. All industry standard, no known weaknesses.'))
    s.append(p('<b>C2-F06 [PASS]: Anti-tamper design is robust.</b> 5-layer defense: code obfuscation (symbol stripping, LTO, Cython, string encryption), tamper detection (SHA-256 binary checksum, IAT verification), anti-debug (IsDebuggerPresent, NtQueryInformationProcess, RDTSC), anti-VM (MAC OUI, CPUID hypervisor bit), behavioral analytics (geo-IP, multi-IP, concurrent session). Server-side heartbeat is ultimate backstop.'))
    s.append(p('<b>C2-F07 [PASS]: Hardware lock is institutionally sound.</b> 3-factor fingerprint (CPUID + Motherboard ID + Windows SID). Each SHA-256 hashed, combined into composite. RSA-4096 JWT signed by HSM-backed key. Cannot be spoofed without physical hardware replacement. 3 activations/year for legitimate changes.'))

    s.append(PageBreak())

    # Ch 6 — Performance + Memory + Latency
    s.append(h1('C3/C4/C5 — Performance, Memory &amp; Latency (92/87/93)',6))
    s.append(p('The performance review (C3, 92/100), memory leak analysis (C4, 87/100), and latency analysis (C5, 93/100) collectively evaluate the system\'s ability to meet its non-functional requirements under load. The latency budget (142ms P99 vs 150ms budget, 8ms margin) is tight but achievable. The memory design (RAII + bounded queues + LRU caches) is sound but unverified — no actual Valgrind/ASan run has been performed. The performance review identifies the AI ensemble as the bottleneck (67% of latency budget), with an optimization plan to reduce it from 95ms to 70ms by Phase 3.'))
    s.append(diagram('d05_perf_memory_latency.png',170))
    s.append(caption('Figure 6.1 — Performance, memory, and latency analysis: per-stage latency bars, findings with severity.'))

    s.append(h2('C3 Performance Review (92/100) — PASS'))
    s.append(p('<b>C3-F01 [MAJOR]: AI ensemble is bottleneck.</b> 95ms of 142ms total latency (67%). Optimization plan: model pruning (reduce LSTM hidden units from 128 to 96), quantization (FP16 for Transformer), batch inference (process 4 ticks per forward pass). Target: 70ms by Phase 3, reducing total to 117ms (33ms margin, 22%). <b>C3-F02 [PASS]: Per-stage budgets realistic.</b> Each stage has 10-25% headroom over spec. Generous but achievable.'))

    s.append(h2('C4 Memory Leak Analysis (87/100) — CONDITIONAL'))
    s.append(p('<b>C4-F01 [CRITICAL]: No actual leak detection performed.</b> Spec defines RAII for C++ and bounded queues for Python, but no Valgrind/AddressSanitizer run, no 72-hour soak test. This is CRIT-02. Fix: implement Valgrind/ASan CI gate, 72-hour soak test, per-module memory profile. Verification: zero leak reports across 72h soak, RSS growth &lt; 5%, all RAII contracts verified. <b>C4-F02 [MAJOR]: Tick data cache eviction policy underspecified.</b> Module 2 mentions Parquet store but in-memory tick cache eviction policy not explicit. Risk of unbounded growth. Fix: specify LRU with 100k tick max, document in Module 2 spec.'))
    s.append(p('<b>C4-F03 [MAJOR]: Python GC tuning not configured.</b> AI layer uses Python 3.12 but no explicit gc.set_threshold() config. Default GC may pause too long. Fix: tune gc.set_threshold(700, 20, 20) for AI layer, document in Module 11 spec. <b>C4-F04 [MINOR]: Audit log rotation not specified.</b> 7-year retention specified, but rotation/compaction policy for local log files not detailed. Fix: specify logrotate config, weekly rotation + gzip. <b>C4-F05 [PASS]: RAII design correct for C++ core.</b> Smart pointers throughout. No raw new/delete. <b>C4-F06 [PASS]: Bounded queue design for event bus.</b> NATS JetStream with max-deliver + ack timeout. <b>C4-F07 [PASS]: LRU cache for idempotency.</b> ExecutionEngine uses LRUCache with bounded size.'))

    s.append(h2('C5 Latency Analysis (93/100) — PASS'))
    s.append(p('<b>C5-F01 [PASS]: Stale-signal veto protects against lag.</b> 2× budget triggers veto. Prevents stale fills. Sound design. <b>C5-F02 [MINOR]: Jitter measurement not spec\'d.</b> P99 latency spec\'d, but jitter (P99-P50) not explicitly bounded. Add jitter ≤ 50ms to spec. Fix: add jitter tracking to Module 20 (Observability) Prometheus metrics.'))

    s.append(PageBreak())

    # Ch 7 — Tests (C6/C7/C8)
    s.append(h1('C6/C7/C8 — Unit, Integration &amp; Regression Tests (86/85/91)',7))
    s.append(p('The test categories evaluate the testing pyramid: unit tests (C6, 86/100), integration tests (C7, 85/100), and regression tests (C8, 91/100). The testing pyramid is well-specified (700 unit + 600 component + 400 integration + 200 e2e + 200 chaos = 2100 tests), but no actual tests have been written. C6 and C7 fall below the 90 threshold for the same reason as C1 — no code exists to test. C8 passes because the regression detection framework (last-5 comparison, WFE/Score drop alerts) is well-specified and can be implemented independently of the strategies it monitors.'))

    s.append(h2('C6 Unit Tests (86/100) — CONDITIONAL'))
    s.append(p('Spec defines 700 unit tests targeting pure functions (math, indicators, parsers, serializers) with zero I/O, zero mocks, &lt;1ms each. Test framework: pytest for Python, GoogleTest for C++. <b>Critical gap: 0 of 700 tests written.</b> Fix: implement all 700 tests during Phase 1-2, achieve 95% line coverage on pure-function modules. Verification: CI pipeline green, 700/700 passing, coverage ≥ 95%.'))

    s.append(h2('C7 Integration Tests (85/100) — CONDITIONAL'))
    s.append(p('Spec defines 400 integration tests targeting cross-service contracts (real NATS, real mTLS, real gRPC), ~5s each. Test framework: pytest + docker-compose + kind. <b>Critical gap: 0 of 400 tests written.</b> Fix: implement all 400 tests during Phase 2-3, achieve 100% contract coverage on service-to-service interfaces. Verification: CI pipeline green, 400/400 passing, zero flaky tests over 7-day window.'))

    s.append(h2('C8 Regression Tests (91/100) — PASS'))
    s.append(p('Spec defines regression detection: each validation framework run (Backtest, WFA, MC, Stress) compared against last 5 runs of same strategy. &gt; 10% WFE drop or &gt; 15% score drop = P1 alert. The framework is well-specified and can be implemented independently of the strategies it monitors — it operates on the JSON output of the validation frameworks. <b>Minor gap: regression framework itself not yet implemented.</b> Fix: implement regression detector during Phase 3 alongside validation frameworks. Verification: regression alerts fire correctly on synthetic test data.'))

    s.append(PageBreak())

    # Ch 8 — Backtests + WFA + MC (C9/C10/C11)
    s.append(h1('C9/C10/C11 — Backtests, Walk-Forward &amp; Monte Carlo (94/93/94)',8))
    s.append(p('The validation framework categories evaluate the strategy validation pipeline: backtests (C9, 94/100), walk-forward tests (C10, 93/100), and Monte Carlo tests (C11, 94/100). All three pass the 90 threshold with strong scores — the validation frameworks (Modules 16, 17, 18) are among the highest-quality specs in the entire system. The critical gap is that no real backtest data has been validated: the worked examples use illustrative numbers, not actual results from real tick data. CRIT-03 (no real backtest data validated) must be resolved during Phase 3.'))

    s.append(h2('C9 Backtests (94/100) — PASS'))
    s.append(p('Spec defines 12-month tick-based backtest with 5 cost components (spread, commission, swap, slippage, tick data), 24 metrics (6 return + 6 risk + 6 trade + 6 cost), 3-band certification (CERTIFIED ≥ 85, CONDITIONAL 70-84, REJECTED &lt; 70). The Institutional Backtesting Framework (Module 16) is comprehensive. <b>Critical gap: no real backtest run.</b> Fix: acquire 12-month tick data from 6 brokers, run real backtests, produce actual metrics. Verification: real Sharpe ≥ 2.0, MDD ≤ 5%, cost drag ≤ 35%, all 8 KPIs met.'))

    s.append(h2('C10 Walk-Forward Tests (93/100) — PASS'))
    s.append(p('Spec defines 5-7 fold walk-forward analysis with anchored or rolling windows, WFE (Walk-Forward Efficiency) ≥ 0.85 as headline metric, 3-band certification. The Walk-Forward Framework (Module 17) is well-specified. <b>Critical gap: no real WFA run.</b> Fix: run real WFA on actual backtest results. Verification: real WFE ≥ 0.85, all folds OOS Sharpe ≥ 1.5, OOS MDD ≤ 5%.'))

    s.append(h2('C11 Monte Carlo Tests (94/100) — PASS'))
    s.append(p('Spec defines 10,000 simulations per strategy with 3 randomization dimensions (trade order, slippage, spread), Survival Score ≥ 95% as headline metric, Risk of Ruin &lt; 1%, 3-band certification. The Monte Carlo Framework (Module 18) is comprehensive. <b>Critical gap: no real MC run.</b> Fix: run real MC on actual trade ledger. Verification: real Survival Score ≥ 95%, P5 Sharpe ≥ 1.0, Risk of Ruin &lt; 1%.'))

    s.append(PageBreak())

    # Ch 9 — Stress + Broker Compatibility (C12/C13)
    s.append(h1('C12/C13 — Stress Tests &amp; Broker Compatibility (92/95)',9))
    s.append(p('The final two validation categories evaluate stress testing (C12, 92/100) and broker compatibility (C13, 95/100). Both pass the 90 threshold. The stress testing framework (Module 16) covers 6 scenarios (flash crash, high spread, server lag, broker disconnect, extreme volatility, gap open) with a 6-stage recovery protocol. The broker compatibility framework (Module 2) covers 6 brokers with runtime detection of 9 properties each. The critical gaps: DR drill never executed (CRIT-06), broker cost profiles not calibrated against live fills (CRIT-04).'))

    s.append(h2('C12 Stress Tests (92/100) — PASS'))
    s.append(p('Spec defines 6 stress scenarios with explicit simulation parameters, historical basis, expected behavior, recovery actions, and pass thresholds. 6-stage recovery protocol (detect → halt → flatten → protect → recover → resume) with kill-switch &lt;500ms SLA. 12 failure rules (5 critical + 5 major + 2 minor). 3-band certification. <b>Critical gap: DR drill never executed.</b> Fix: provision both VPS zones (London + Frankfurt), run quarterly DR drill, measure actual RPO/RTO. Verification: RPO ≤ 60s, RTO ≤ 5m, zero data loss, zero split-brain.'))

    s.append(h2('C13 Broker Compatibility Tests (95/100) — PASS'))
    s.append(p('Spec defines 6 supported brokers (Exness, IC Markets, Pepperstone, Tickmill, FP Markets, Fusion Markets) with runtime detection of 9 properties each (name, server, suffix, contract size, min lot, lot step, leverage, margin mode, timezone). 18 checks (4 critical + 7 major + 7 minor). The highest-scoring category in the review. <b>Critical gap: cost profiles not calibrated against live fills.</b> Fix: open 6 broker demo accounts, log 30 days of fills, compute actual P50/P90/P99 slippage + spread. Verification: live P50 within ±15% of spec, PSI &lt; 0.25, all 6 brokers calibrated.'))

    s.append(PageBreak())

    # Ch 10 — Critical Issues
    s.append(h1('Critical Issues — 7 Release Blockers',10))
    s.append(p('Seven critical issues were identified during the review. All seven must be resolved before PRODUCTION READY status can be granted. No waivers, no overrides, no exceptions — per the institutional rule "do not approve release until all critical issues are fixed." All seven issues stem from the same root cause: the TITAN system exists as 16 architecture specifications, not as implemented code. The 16-week remediation roadmap (Chapter 14) addresses all seven in 4 phases.'))
    s.append(diagram('d03_critical_issues.png',170))
    s.append(caption('Figure 10.1 — 7 critical issues with category, impact, fix, and verification criteria. 4-phase remediation roadmap.'))

    s.append(h2('Critical Issues Summary'))
    s.append(table([
        ['ID', 'Issue', 'Category', 'Fix Phase', 'Verification'],
        ['CRIT-01', 'No actual code implementation exists', 'C1/C6/C7', 'Phase 1-3', '2100 tests pass · 5 frameworks CERTIFIED'],
        ['CRIT-02', 'Memory leak analysis unverified', 'C4', 'Phase 3', '72h soak · zero leaks · RSS &lt;5% growth'],
        ['CRIT-03', 'No real backtest data validated', 'C9/C10/C11', 'Phase 3', 'Real Sharpe ≥ 2.0 · WFE ≥ 0.85 · Survival ≥ 95%'],
        ['CRIT-04', 'Broker cost profiles not calibrated', 'C13/C9', 'Phase 2', 'Live P50 ±15% · PSI &lt; 0.25 · 6 brokers'],
        ['CRIT-05', 'License server HSM not provisioned', 'C2', 'Phase 1', 'HSM-backed signing · key rotation tested'],
        ['CRIT-06', 'DR drill never executed', 'C12', 'Phase 4', 'RPO ≤ 60s · RTO ≤ 5m · zero data loss'],
        ['CRIT-07', 'SOC2 audit not completed', 'C2', 'Phase 4', 'SOC2 Type I report issued'],
    ], cw=[10, 30, 12, 14, 34]))
    s.append(Spacer(1, 8))

    s.append(h2('Root Cause Analysis'))
    s.append(p('All 7 critical issues trace to a single root cause: <b>the TITAN system is specified but not built.</b> The specifications are institutionally rigorous — they define every module, every interface, every validation framework, every certification criterion. But specifications cannot be deployed to production. The remediation roadmap converts specifications to running, tested, validated code over 16 weeks. After Phase 4, a re-review will determine if PRODUCTION READY can be granted. The architecture passes the design bar; the implementation must now meet the same bar.'))

    s.append(PageBreak())

    # Ch 11 — Remediation Roadmap
    s.append(h1('Remediation Roadmap — 16 Weeks to Production',11))
    s.append(p('The remediation roadmap converts the 16 architecture specifications to validated production code over 16 weeks in 4 phases. Each phase delivers verifiable milestones and resolves specific critical issues. After Phase 4, a re-review (Module 17 v2.0) will determine if PRODUCTION READY can be granted. The roadmap is aggressive but achievable — it assumes a 4-person engineering team working full-time, with the architecture specs providing sufficient detail to enable rapid implementation.'))
    s.append(table([
        ['Phase', 'Weeks', 'Scope', 'Critical Issues Resolved', 'Exit Criteria'],
        ['Phase 1 — Foundation', '1-4', 'M01 Broker, M02 Market Data, M03 Execution, M08 Risk, M14 Licensing', 'CRIT-01 (partial), CRIT-05', 'Validator M15 passes · paper trading on 1 broker'],
        ['Phase 2 — AI + Strategy', '5-9', 'M04 Regime, M05 Trend, M06 Range, M07 Vol, M11 AI, M12 RL', 'CRIT-01 (more), CRIT-04', 'Backtest M16 CERTIFIED on 3 brokers'],
        ['Phase 3 — Validation', '10-13', 'M09 Slippage, M10 Spread, M13 Retrain, M16-M19 Validation frameworks', 'CRIT-01 (complete), CRIT-02, CRIT-03', 'WFA + MC + Stress all CERTIFIED'],
        ['Phase 4 — Hardening', '14-16', 'M20 Observability, DR drill, SOC2 audit, performance tuning', 'CRIT-06, CRIT-07', 'All 7 critical issues resolved · re-review'],
    ], cw=[20, 8, 32, 18, 22]))
    s.append(Spacer(1, 8))

    s.append(h2('Phase 1 — Foundation (Weeks 1-4)'))
    s.append(p('Implement the trading core: M01 Broker Compatibility (6-broker runtime detection), M02 Market Data Engine (tick ingest, Parquet store, 14 quality gates), M03 Execution Engine (async dispatcher, 50 ops/s, idempotency), M08 Risk Engine (12 controls, kill-switch &lt;500ms, MDD &lt;5%), M14 Licensing (HW-locked JWT, 3 tiers, 5 anti-crack layers). Provision AWS KMS HSM for license signing (CRIT-05). The result is a paper-trading system that can connect to 1 broker, place orders, manage risk, and validate licenses — but with no AI-driven signals (manual signals only). Exit criterion: the Validator Framework (M15) passes on the live system.'))

    s.append(h2('Phase 2 — AI &amp; Strategy (Weeks 5-9)'))
    s.append(p('Implement the AI stack and trading strategies: M04 Regime Detection (4-state, 3-model vote), M05 Trend Strategy (5 patterns, R-multiple mgmt), M06 Range Strategy (BB+RSI+ATR+Hurst), M07 Volatility Engine (news-aware), M11 Hybrid AI Stack (XGBoost+LSTM+Transformer+RL+Ensemble), M12 RL Trade Management (scaling, exit policy). Open 6 broker demo accounts, log 30 days of fills, calibrate cost profiles (CRIT-04). Exit criterion: Backtest Framework (M16) returns CERTIFIED on 3 brokers.'))

    s.append(h2('Phase 3 — Validation Pipeline (Weeks 10-13)'))
    s.append(p('Implement the validation pipeline: M09 Slippage Intelligence, M10 Spread/Commission Intel, M13 Auto Retraining (Champion/Challenger), M16 Backtesting, M17 Walk-Forward, M18 Monte Carlo, M19 Stress Test. Run real backtests, WFA, MC, stress tests on actual tick data (CRIT-03). Implement Valgrind/ASan CI gate and 72-hour soak test (CRIT-02). Complete the 2100-test pyramid. Exit criterion: WFA, MC, and Stress Test all return CERTIFIED on real data.'))

    s.append(h2('Phase 4 — Hardening (Weeks 14-16)'))
    s.append(p('Implement M20 Monitoring &amp; Observability (Prometheus, Grafana, Loki, OpenTelemetry, PagerDuty). Provision both VPS zones (London primary + Frankfurt DR), run quarterly DR drill, measure actual RPO/RTO (CRIT-06). Engage 3rd-party SOC2 auditor, complete Type I audit (CRIT-07). Performance tuning: optimize AI ensemble to 70ms (from 95ms). Final production readiness re-review (Module 17 v2.0). Exit criterion: all 7 critical issues resolved, re-review grants PRODUCTION READY.'))

    s.append(PageBreak())

    # Ch 12 — Final Verdict
    s.append(h1('Final Production Readiness Verdict',12))
    s.append(p('The final verdict aggregates all 13 category scores and applies the 90/100 threshold rule. 10 of 13 categories meet the threshold (PASS), 3 fall below (CONDITIONAL), 0 fail outright. The aggregate weighted score is 91.0/100 — above the institutional 90/100 bar. However, per the rule "do not approve release until all critical issues are fixed," the 7 critical issues block release. The verdict is <b>CONDITIONAL APPROVAL — NOT YET PRODUCTION READY</b>.'))
    s.append(diagram('d06_final_verdict.png',170))
    s.append(caption('Figure 12.1 — Final verdict: 13-category scorecard with scores, verdicts, and required actions. Release BLOCKED.'))

    s.append(h2('Scorecard Summary'))
    s.append(table([
        ['Category', 'Score', 'Verdict', 'Action'],
        ['C2 Security Review', '94', 'PASS', 'Provision HSM · engage SOC2 auditor'],
        ['C13 Broker Compatibility', '95', 'PASS', 'Calibrate cost profiles vs live fills'],
        ['C9 Backtests', '94', 'PASS', 'Run real backtests with actual tick data'],
        ['C11 Monte Carlo Tests', '94', 'PASS', 'Run real MC with actual trade ledger'],
        ['C10 Walk Forward Tests', '93', 'PASS', 'Run real WFA with actual tick data'],
        ['C5 Latency Analysis', '93', 'PASS', 'Add jitter (P99-P50) to spec'],
        ['C3 Performance Review', '92', 'PASS', 'Optimize AI ensemble (67% of latency)'],
        ['C12 Stress Tests', '92', 'PASS', 'Execute DR drill'],
        ['C8 Regression Tests', '91', 'PASS', 'Implement after Phase 2'],
        ['C1 Code Review', '88', 'CONDITIONAL', 'Implement Phase 1-3 code (CRIT-01)'],
        ['C4 Memory Leak Analysis', '87', 'CONDITIONAL', 'Run Valgrind/ASan + 72h soak (CRIT-02)'],
        ['C6 Unit Tests', '86', 'CONDITIONAL', 'Implement 700 unit tests (CRIT-01)'],
        ['C7 Integration Tests', '85', 'CONDITIONAL', 'Implement 400 integration tests (CRIT-01)'],
    ], cw=[30, 10, 16, 44]))
    s.append(Spacer(1, 8))

    s.append(h2('Verdict Rationale'))
    s.append(p('The TITAN XAU AI architecture is institutionally rigorous. The design quality is best-in-class for an institutional trading system: 20 modules with explicit interfaces, 5-component AI stack with ensemble voting, 4-regime detection with 3-model vote, 6-broker compatibility with runtime detection, 5-framework validation pipeline with 3-band certification, Champion/Challenger model governance (no live auto-deploy), and 6 NFRs with explicit targets. The architecture specification set (Modules 1-16, 34 files, ~70 MB) is more comprehensive than most hedge fund internal documentation.'))
    s.append(p('However, the architecture is not the system. The system is the running code that implements the architecture. As of this review, zero lines of production code exist. The 7 critical issues all stem from this gap. The 16-week remediation roadmap converts specifications to validated code, at which point a re-review will determine if PRODUCTION READY can be granted. <b>Estimated date for PRODUCTION READY: Week 17 (October 2026)</b> if remediation stays on schedule. No live capital authorized until then. Paper trading and small-capital forward testing may proceed during remediation.'))

    s.append(h2('Sign-off Chain'))
    s.append(p('This review requires 4-role sign-off. No role can delegate. The verdict is binding until the re-review (Module 17 v2.0) after Phase 4.'))
    s.append(table([
        ['Role', 'Responsibility', 'Sign-off'],
        ['Audit Lead', 'Review methodology, scoring, findings', 'Required · digital signature'],
        ['CTO', 'Accept verdict, authorize remediation', 'Required · digital signature'],
        ['Risk Officer', 'Verify risk findings, capital authorization', 'Required · digital signature'],
        ['Compliance', 'Verify regulatory findings, SOC2 status', 'Required · digital signature'],
    ], cw=[20, 50, 30]))

    s.append(PageBreak())

    # Ch 13 — What's Allowed During Remediation
    s.append(h1('What Is Allowed During Remediation',13))
    s.append(p('While PRODUCTION READY is blocked, certain activities are explicitly authorized to proceed in parallel with the remediation roadmap. These activities do not risk live capital and accelerate the path to PRODUCTION READY.'))
    s.append(h2('Authorized Activities'))
    s.append(bullet('<b>Paper trading</b> on demo accounts — all 6 brokers, no real capital at risk. Useful for cost profile calibration (CRIT-04) and broker compatibility testing (C13).'))
    s.append(bullet('<b>Small-capital forward testing</b> — up to $5,000 per strategy, with manual operator supervision. Useful for validating live execution behavior. NOT live trading in the institutional sense.'))
    s.append(bullet('<b>Code implementation</b> — Phase 1-4 of the remediation roadmap. The 4-person engineering team works full-time on converting specs to code.'))
    s.append(bullet('<b>Cost profile calibration</b> — open 6 broker demo accounts, log fills, compute P50/P90/P99. Resolves CRIT-04 during Phase 2.'))
    s.append(bullet('<b>Architecture spec refinement</b> — close the spec gaps identified in this review (C1-F02 module numbering, C1-F03 PyO3 bridge spec, C4-F02 cache eviction, C4-F03 GC tuning, C5-F02 jitter).'))
    s.append(bullet('<b>HSM provisioning</b> — AWS KMS custom key store setup, RSA-4096 key generation, signing verification. Resolves CRIT-05 during Phase 1.'))
    s.append(bullet('<b>SOC2 audit engagement</b> — select auditor, sign engagement letter, begin Type I audit. Resolves CRIT-07 during Phase 4 (audit completes post-Phase 4).'))

    s.append(h2('Prohibited Activities'))
    s.append(bullet('<b>Live trading with real capital above $5,000</b> — prohibited until PRODUCTION READY. No exceptions.'))
    s.append(bullet('<b>Commercial licensing to 3rd parties</b> — prohibited until PRODUCTION READY. The system cannot be sold until it is certified ready.'))
    s.append(bullet('<b>Public performance claims</b> — prohibited until real backtest/WFA/MC results replace the illustrative numbers. No marketing based on spec-quality metrics.'))
    s.append(bullet('<b>Skip-ahead to Phase 4</b> — prohibited. Phases must be sequential. Phase 4 (hardening) without Phase 1-3 (implementation) would harden an unbuilt system.'))

    s.append(PageBreak())

    # Ch 14 — Re-Review Criteria
    s.append(h1('Re-Review Criteria — Module 17 v2.0',14))
    s.append(p('After Phase 4 of the remediation roadmap, a re-review (Module 17 v2.0) will determine if PRODUCTION READY can be granted. The re-review will repeat all 13 category evaluations against the now-implemented system, with actual code, actual tests, and actual validation results. The re-review criteria are: (1) all 13 categories score ≥ 90/100, (2) all 7 critical issues verified resolved, (3) all 8 target KPIs met on real data (Profit Factor &gt; 2.2, Sharpe &gt; 2.0, Sortino &gt; 3.0, Recovery Factor &gt; 5.0, Risk of Ruin &lt; 1%, MC Survival &gt; 95%, WFE &gt; 85%, MDD &lt; 5%), (4) 4-role sign-off (Audit Lead, CTO, Risk Officer, Compliance).'))
    s.append(h2('Re-Review Checklist'))
    s.append(bullet('C1 Code Review: actual code reviewed by 2 reviewers, static analysis clean, 2100-test pyramid passing'))
    s.append(bullet('C2 Security Review: HSM provisioned, SOC2 Type I issued, mTLS rotation automated, pen test scheduled'))
    s.append(bullet('C3 Performance Review: AI ensemble optimized to ≤ 70ms, total latency ≤ 130ms P99'))
    s.append(bullet('C4 Memory Leak Analysis: Valgrind/ASan clean, 72h soak test passed, RSS growth &lt; 5%'))
    s.append(bullet('C5 Latency Analysis: P99 ≤ 150ms, jitter ≤ 50ms, stale-veto ≥ 95%'))
    s.append(bullet('C6 Unit Tests: 700/700 passing, 95% line coverage on pure functions'))
    s.append(bullet('C7 Integration Tests: 400/400 passing, zero flaky over 7-day window'))
    s.append(bullet('C8 Regression Tests: regression detector implemented, alerts fire correctly'))
    s.append(bullet('C9 Backtests: real Sharpe ≥ 2.0, MDD ≤ 5%, cost drag ≤ 35% on real tick data'))
    s.append(bullet('C10 Walk-Forward: real WFE ≥ 0.85, all folds OOS Sharpe ≥ 1.5'))
    s.append(bullet('C11 Monte Carlo: real Survival ≥ 95%, Risk of Ruin &lt; 1%'))
    s.append(bullet('C12 Stress Tests: all 6 scenarios PASS, DR drill RPO ≤ 60s, RTO ≤ 5m'))
    s.append(bullet('C13 Broker Compatibility: 6 brokers calibrated, live P50 ± 15% of spec'))
    s.append(bullet('All 8 target KPIs met on real data (PF, Sharpe, Sortino, Recovery, RoR, MC, WFE, MDD)'))
    s.append(bullet('All 7 critical issues verified resolved with evidence'))
    s.append(bullet('4-role sign-off: Audit Lead, CTO, Risk Officer, Compliance'))

    s.append(h2('Estimated PRODUCTION READY Date'))
    s.append(p('If the remediation roadmap stays on schedule, PRODUCTION READY can be granted at <b>Week 17 (October 2026)</b>. The re-review (Module 17 v2.0) will be published at that time. If any phase slips, the date moves correspondingly — there is no fixed deadline, only the requirement that all criteria be met. The institutional rule is clear: <b>no PRODUCTION READY until all 13 categories ≥ 90/100 AND all 7 critical issues resolved AND all 8 KPIs met on real data.</b> This review (v1.0) is the baseline; the re-review (v2.0) is the gate.'))

    return s

def main():
    out = '/home/z/my-project/scripts/readiness/body.pdf'
    doc = TocDocTemplate(out, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=24*mm, bottomMargin=22*mm, title='TITAN XAU AI — Production Readiness Review', author='TITAN Quant Research Audit Office', subject='Production readiness: 13-category audit of 16 modules, 90/100 threshold, 7 critical issues, CONDITIONAL APPROVAL', creator='TITAN Architecture Workbench')
    story = build_story()
    print(f'[build] Building body PDF with {len(story)} flowables...')
    doc.multiBuild(story, onFirstPage=hf, onLaterPages=hf)
    print(f'[build] Body PDF written: {out}')
    from pypdf import PdfReader; r = PdfReader(out); print(f'[build] Page count: {len(r.pages)}')

if __name__ == '__main__': main()
