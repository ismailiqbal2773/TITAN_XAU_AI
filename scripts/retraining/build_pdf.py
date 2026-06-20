"""
TITAN XAU AI — Retraining Framework (Module 10)
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
DIAGRAM_DIR = '/home/z/my-project/scripts/retraining/diagrams/png'

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
    c.setFont('FreeSerif-Italic',8.5); c.setFillColor(TEXT_MUTED); c.drawString(20*mm, A4[1]-14*mm, 'TITAN XAU AI — Retraining Framework')
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
    s.append(p('The Retraining Framework (RTF) is Module 10 of the TITAN XAU AI trading architecture. It is the system\'s model lifecycle management layer — an automated framework that schedules, executes, validates, and governs the retraining of all 4 AI models (XGBoost, LSTM, Transformer, RL) plus the HMM regime detector. The RTF ensures that the AI models stay current as market structure evolves, with three retrain triggers: weekly scheduled (XGBoost + LSTM + Transformer), monthly scheduled (RL + HMM), and emergency (triggered by model drift or performance decay).'))
    s.append(p('The framework implements a Champion-Challenger model: the current production model (champion) serves 100% of traffic, while a newly retrained model (challenger) goes through canary (10% for 1 hour) and A/B testing (50% for 24 hours) before promotion. The challenger must beat the champion on Sharpe, MaxDD, and F1 to be promoted. If the challenger fails, the champion is retained. If the challenger is promoted but later underperforms, an automated rollback reverts to the previous champion in under 30 seconds.'))
    s.append(p('Model drift detection runs continuously. Feature drift is measured via Population Stability Index (PSI) per feature, computed daily: PSI < 0.10 is stable, 0.10-0.20 is watch, 0.20-0.25 is alert, and > 0.25 triggers an emergency retrain. Concept drift is measured via rolling F1 drop: a drop > 15% from baseline triggers emergency retrain. Performance decay is measured via rolling Sharpe: a drop > 25% triggers emergency retrain. All three detection mechanisms run independently and can trigger retrains independently.'))
    s.append(p('Version control is managed by MLflow, which stores every model version with full lineage: data version, feature version, model artifacts, training metrics, validation metrics, and deployment decisions. Rollback is always available — the previous champion\'s artifacts are pre-cached on inference nodes, enabling a rollback in under 30 seconds with zero downtime and zero data loss. The entire retrain-promote-rollback lifecycle is governed by a board (CTO + Lead Quant + Risk Officer + ML Engineer) with a defined approval matrix and full audit trail.'))

    s.append(h1('Architecture Overview',2))
    s.append(p('The RTF is organized into 6 layers: retrain scheduler (weekly + monthly), drift and decay detection (continuous), retrain pipeline (automated + CI-gated), champion-challenger (A/B testing + canary), governance (board + approval matrix + audit), and monitoring (dashboard + alerts). All layers are automated except governance, which requires human review at defined checkpoints.'))
    s.append(diagram('d01_architecture.png',170))
    s.append(caption('Figure 2.1 — RTF architecture: 6 layers with scheduler, drift detector, pipeline, champion-challenger, governance, and monitoring.'))

    s.append(h2('Layer Responsibilities'))
    s.append(h3('L1 — Retrain Scheduler'))
    s.append(p('WeeklyRetrainer runs every Sunday at 22:00 UTC, retraining XGBoost (15 min), LSTM (2 hours), and Transformer (4 hours) on 24 months of rolling data across 6 brokers. MonthlyRetrainer runs on the 1st Sunday, retraining RL PPO (8 hours, 10k episodes) and HMM (30 min, per-session). Total weekly compute: ~6 hours. Total monthly compute: ~12 hours (additional RL + HMM).'))

    s.append(h3('L2 — Drift & Decay Detection (continuous)'))
    s.append(p('ModelDriftDetector computes PSI per feature daily (threshold: > 0.25 = emergency retrain) and concept drift via F1 drop (threshold: > 15% = emergency). PerformanceDecayDetector tracks rolling 100-trade Sharpe (threshold: > 25% drop = emergency) and per-model F1. DataQualityMonitor blocks retrain if data quality fails (NaN > 0.5%, coverage < 99.5%).'))

    s.append(h3('L3 — Retrain Pipeline (automated, CI-gated)'))
    s.append(p('DataPreparation (24mo data, feature engineering, 80/10/10 split) → ModelTrainer (parallel, Optuna TPE, 200 trials, walk-forward 5 folds) → ValidationGate (F1 > 0.60, ensemble Sharpe > 2.0, Sharpe drop < 5% vs champion). If validation fails, the model is rejected and the champion is retained.'))

    s.append(h3('L4 — Champion-Challenger (A/B testing + canary)'))
    s.append(p('ChampionModel serves 100% traffic. ChallengerModel goes through canary (10% for 1 hour) → A/B test (50% for 24 hours) → promote (if beats champion on Sharpe + MaxDD + F1). VersionController manages MLflow registry with full version history and rollback capability (< 30 seconds).'))

    s.append(h3('L5 — Governance & Monitoring'))
    s.append(p('GovernanceBoard (CTO + Lead Quant + Risk Officer + ML Engineer) reviews monthly. RetrainMonitor tracks training progress, GPU utilization, validation metrics, and canary performance. AuditTrail records every retrain, promote, and rollback with full model lineage in a hash-chained WORM store.'))

    s.append(PageBreak())

    s.append(h1('Retraining Workflow',3))
    s.append(p('The retraining workflow (Figure 3.1) documents the complete end-to-end sequence from trigger to deployment. The workflow has 8 stages: trigger, data preparation, parallel training, walk-forward validation, register as challenger, canary deploy, A/B test, and promote (or archive/rollback). Emergency retrains skip the canary and A/B stages, going directly from validation to promotion.'))
    s.append(diagram('d02_workflow.png',170))
    s.append(caption('Figure 3.1 — End-to-end retraining workflow: trigger → data → train → validate → champion-challenger → deploy.'))

    s.append(h2('Weekly Retraining Schedule'))
    s.append(code("""Weekly Retrain (Sunday 22:00 UTC):
  1. Data Preparation (30 min)
     - 24mo × 6 brokers historical data
     - Feature engineering (8 features)
     - Label construction (direction, trend_continue, regime context)
     - 80/10/10 train/val/test split

  2. Parallel Model Training (~5h total)
     - XGBoost: 500 trees, Optuna TPE, 200 trials (~15 min)
     - LSTM: 2 layers, 128 hidden, Adam, 100 epochs (~2h)
     - Transformer: 4 heads, 2 layers, AdamW, warmup (~4h)
     - All 3 train in parallel on separate GPUs

  3. Walk-Forward Validation (~30 min)
     - 5 folds × 4mo OOS
     - Per-model F1 > 0.60
     - Ensemble Sharpe > 2.0
     - Challenger Sharpe >= Champion - 5%

  4. Register + Deploy (~30 min)
     - MLflow version + artifacts + lineage
     - Canary 10% (1h) → A/B 50% (24h) → Promote 100%
     - OR: Reject + keep champion + audit

  Total: ~6 hours (Sunday 22:00 → Monday 04:00 UTC)"""))

    s.append(h2('Monthly Retraining Schedule'))
    s.append(p('Monthly retraining (1st Sunday) adds RL PPO retraining (8 hours, 10k episodes) and HMM per-session retraining (30 min per session × 3 sessions = 1.5 hours). The RL retrain uses a simulated XAUUSD environment with the latest market data, and the HMM retrain uses the last 90 days of session-specific data. Total monthly compute: ~12 hours (weekly 6h + additional RL + HMM 6h). The monthly retrain follows the same champion-challenger pipeline as weekly, but with separate validation gates for RL (episode reward > no-RL baseline) and HMM (regime F1 > 0.70).'))

    s.append(PageBreak())

    s.append(h1('Model Drift & Performance Decay Detection',4))
    s.append(p('Two independent detection systems run continuously: ModelDriftDetector (feature drift via PSI + concept drift via F1 drop) and PerformanceDecayDetector (Sharpe + DD + PF decay). Either system can trigger an emergency retrain independently.'))
    s.append(diagram('d03_drift.png',170))
    s.append(caption('Figure 4.1 — Drift detection (PSI + concept drift) and performance decay detection (Sharpe + F1 + PF).'))

    s.append(h2('Feature Drift (PSI)'))
    s.append(p('PSI = Σ (p_new - p_old) × ln(p_new / p_old), computed daily per feature. p_new is the current 7-day feature distribution; p_old is the training distribution (binned into 10 buckets). PSI < 0.10 is stable (no action). PSI 0.10-0.20 is watch (log and monitor). PSI 0.20-0.25 is alert (P2 email, investigate). PSI > 0.25 triggers an emergency retrain that skips the canary stage and deploys directly.'))

    s.append(h2('Concept Drift (F1 Drop)'))
    s.append(p('Concept drift is detected when the model\'s predictive accuracy degrades over time. Measured as the rolling 100-trade F1 vs the 1000-trade baseline F1. A drop > 10% triggers an alert; > 15% triggers an emergency retrain. Per-model tracking: XGBoost, LSTM, Transformer, and RL are tracked independently, so a drift in one model does not necessarily trigger a full retrain of all models.'))

    s.append(h2('Performance Decay (Sharpe + DD + PF)'))
    s.append(p('Rolling 100-trade Sharpe vs baseline (2.28). A drop > 15% triggers an alert (investigate + retrain); > 25% triggers an emergency retrain. MaxDD is monitored continuously by the Risk Engine (Module 8) — a hard DD breaker halt also triggers a retrain review. Profit Factor drop > 20% triggers an alert. RL episode reward below the no-RL baseline triggers an RL-only retrain.'))

    s.append(PageBreak())

    s.append(h1('Champion-Challenger & Version Control',5))
    s.append(p('The Champion-Challenger system ensures that no model is promoted to production without proving itself against the current champion. The challenger goes through a 3-stage pipeline: canary (10% traffic for 1 hour), A/B test (50% traffic for 24 hours), and promote (if it beats the champion). If it fails at any stage, it is archived and the champion is retained. Emergency retrains skip canary and A/B, deploying directly.'))
    s.append(diagram('d04_champion.png',170))
    s.append(caption('Figure 5.1 — Champion-challenger lifecycle, rollback triggers, and rollback mechanism.'))

    s.append(h2('Rollback Support'))
    s.append(p('Rollback is always available. MLflow stores all model versions (champion + archived challengers). The previous champion\'s artifacts are pre-cached on inference nodes, so rollback is simply a pointer change — no model download needed. Rollback latency: < 30 seconds (model load + cache warm + traffic switch). Zero downtime, zero data loss, fully audited. Rollback triggers: canary Sharpe drop > 10%, A/B Sharpe drop > 5%, post-promote Sharpe drop > 15%, EQS < 40 CRITICAL for 5+ trades, or manual operator rollback (2-person rule).'))

    s.append(h2('Version Control (MLflow)'))
    s.append(p('MLflow registry stores every model version with: version number, training data version, feature version, model artifacts (weights + config), training metrics (loss, F1, Sharpe), validation metrics (walk-forward results), and deployment decision (promoted / archived / rolled back). Full model lineage is maintained: data → features → model → metrics → decision. This enables full reproducibility — any past model can be recreated from its lineage chain.'))

    s.append(PageBreak())

    s.append(h1('Governance Framework',6))
    s.append(p('The RTF is governed by a board (CTO + Lead Quant + Risk Officer + ML Engineer) with a defined approval matrix. Most actions are automated (weekly retrain, canary, A/B, promote, auto-rollback), but certain actions require human approval (monthly retrain review, manual rollback, risk mode changes). All actions are audited in a hash-chained immutable log.'))
    s.append(diagram('d05_governance.png',170))
    s.append(caption('Figure 6.1 — Governance board, approval matrix, 12-panel dashboard, and alert routing.'))

    s.append(h2('Approval Matrix'))
    s.append(bullet('Weekly retrain: Automatic (CI gate only, no human approval needed)'))
    s.append(bullet('Monthly retrain: Lead Quant review (4h SLA)'))
    s.append(bullet('Emergency retrain: Automatic + post-hoc review (within 4h)'))
    s.append(bullet('Promote challenger: Automatic (A/B gate, no human approval)'))
    s.append(bullet('Auto-rollback: Automatic (< 30s, no human approval)'))
    s.append(bullet('Manual rollback: 2-person rule (TRADER + SUPERVISOR, < 5min)'))
    s.append(bullet('Risk mode change (to Aggressive/Competition): SUPERVISOR + RISK OFFICER (1h SLA)'))

    s.append(h2('Audit Trail'))
    s.append(p('Every retrain, promote, rollback, and mode change is recorded in a hash-chained immutable audit log (WORM S3). Each entry includes: timestamp, action type, model version, trigger reason, metrics (before/after), approver identity, and model lineage. The audit log supports full regulatory compliance (MiFID-II trade reconstruction, model risk management) and post-incident forensic analysis.'))

    s.append(PageBreak())

    s.append(h1('Monitoring Framework',7))
    s.append(p('The RTF monitoring framework provides real-time visibility into all aspects of the model lifecycle. A 12-panel Grafana dashboard displays: active model versions, PSI per feature, per-model F1, ensemble Sharpe, retrain calendar, champion vs challenger A/B comparison, rollback history, training progress, GPU utilization, model weight distribution, RL action distribution, and alert log. Alerts are routed by severity: P1 (PagerDuty), P2 (email), P3 (log only).'))

    s.append(h2('Auto-Mitigation'))
    s.append(p('The monitoring framework includes automatic mitigation: PSI > 0.25 triggers auto-retrain (skip canary); canary Sharpe drop > 10% triggers auto-rollback (< 30s); F1 drop > 15% triggers emergency retrain; performance degradation triggers weight reduction to floor (0.10). These auto-actions ensure the system adapts without waiting for human intervention.'))

    s.append(h1('Validation Process',8))
    s.append(p('Every retrained model must pass 8 CI gates before it can be promoted: (G1) per-model F1 > 0.60, (G2) ensemble Sharpe > 2.0, (G3) challenger Sharve >= champion - 5%, (G4) MaxDD < 5% and RoR < 1%, (G5) PSI < 0.20 (no drift after retrain), (G6) RL reward > no-RL baseline, (G7) rollback verified (< 30s), (G8) audit log complete. All 8 gates must pass — any failure rejects the model and retains the champion.'))
    s.append(diagram('d06_validation.png',170))
    s.append(caption('Figure 8.1 — Test pyramid (150 tests) and 8 CI gates.'))

    s.append(h1('Integration with TITAN Core',9))
    s.append(p('The RTF integrates with the Hybrid AI Stack (Module 7) as the model lifecycle manager. It consumes performance metrics from the AI Stack\'s monitoring framework, triggers retrains based on drift/decay signals, and deploys new models via the champion-challenger pipeline. The RTF also integrates with the Risk Engine (Module 8) — if a hard DD breaker fires, the RTF reviews whether a model retrain is needed. The Execution Cost Intelligence (Module 9) feeds cost data to the RTF for cost-aware model evaluation (a model that produces more signals but at higher cost may not be promoted even if its Sharpe is higher).'))

    s.append(h2('Retrain Calendar Summary'))
    s.append(table([
        ['Cadence', 'Models', 'Trigger', 'Duration', 'Canary?', 'Approval'],
        ['Weekly (Sun 22:00 UTC)', 'XGBoost + LSTM + Transformer', 'Scheduled', '~6 hours', 'Yes (10% → 50% → 100%)', 'Automatic (CI gate)'],
        ['Monthly (1st Sun)', 'RL PPO + HMM (all sessions)', 'Scheduled', '~12 hours (incl weekly)', 'Yes (separate track)', 'Lead Quant review'],
        ['Emergency (anytime)', 'Drifted model(s) only', 'PSI > 0.25 or F1 drop > 15%', '~2-6 hours', 'No (direct promote)', 'Automatic + post-hoc'],
        ['Manual (anytime)', 'Specified by operator', 'Operator request', '~2-6 hours', 'Yes', '2-person (TRADER + SUPERVISOR)'],
    ], cw=[22, 26, 18, 12, 14, 18]))
    s.append(Spacer(1, 8))

    return s

def main():
    out = '/home/z/my-project/scripts/retraining/body.pdf'
    doc = TocDocTemplate(out, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=24*mm, bottomMargin=22*mm, title='TITAN XAU AI — Retraining Framework', author='TITAN Quant Research', subject='Retraining Framework: weekly/monthly retrain, drift detection, champion-challenger, rollback', creator='TITAN Architecture Workbench')
    story = build_story()
    print(f'[build] Building body PDF with {len(story)} flowables...')
    doc.multiBuild(story, onFirstPage=hf, onLaterPages=hf)
    print(f'[build] Body PDF written: {out}')
    from pypdf import PdfReader; r = PdfReader(out); print(f'[build] Page count: {len(r.pages)}')

if __name__ == '__main__': main()
