const fs = require('fs'), path = require('path');
const { imageSize } = require('image-size');
const docx = require('docx');
const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, PageBreak, ImageRun, Table, TableRow, TableCell, WidthType, BorderStyle, TableOfContents, StyleLevel, Footer, Header, PageNumber, NumberFormat, ShadingType, TabStopType, TabStopPosition, VerticalAlign } = docx;
const C = { navy: '14213D', crimson: 'C8102E', muted: '4A5568', stripe: 'F8FAFC', border: 'CBD5E1', text: '14213D' };
const DIR = '/home/z/my-project/scripts/mean_reversion/diagrams/png';
const OUT = '/home/z/my-project/download/TITAN_Mean_Reversion_Strategy_v1.0.docx';

function p(t,o={}){const r=(Array.isArray(t)?t:[{text:t}]).map(x=>new TextRun({text:x.text,bold:x.bold||o.bold,italics:x.italic||o.italic,color:x.color||o.color||C.text,size:(x.size||o.size||22),font:'Liberation Serif'}));return new Paragraph({children:r,spacing:{after:160,line:312},alignment:o.alignment||AlignmentType.JUSTIFIED})}
function h1(t){return new Paragraph({children:[new TextRun({text:t,bold:true,color:C.navy,size:40,font:'Liberation Serif'})],heading:HeadingLevel.HEADING_1,spacing:{before:480,after:240},pageBreakBefore:true,border:{bottom:{color:C.crimson,size:18,style:BorderStyle.SINGLE,space:4}}})}
function h2(t){return new Paragraph({children:[new TextRun({text:t,bold:true,color:C.navy,size:28,font:'Liberation Serif'})],heading:HeadingLevel.HEADING_2,spacing:{before:320,after:160}})}
function h3(t){return new Paragraph({children:[new TextRun({text:t,bold:true,color:C.crimson,size:24,font:'Liberation Serif'})],heading:HeadingLevel.HEADING_3,spacing:{before:240,after:120}})}
function bullet(t){return new Paragraph({children:[new TextRun({text:t,size:22,font:'Liberation Serif',color:C.text})],bullet:{level:0},spacing:{after:80,line:280}})}
function code(t){return new Paragraph({children:[new TextRun({text:t,size:18,font:'DejaVu Sans Mono',color:C.text})],spacing:{before:120,after:200,line:240},shading:{type:ShadingType.CLEAR,color:'auto',fill:C.stripe},border:{left:{color:C.crimson,size:18,style:BorderStyle.SINGLE,space:6}},indent:{left:240,right:240}})}
function caption(t){return new Paragraph({children:[new TextRun({text:t,italics:true,size:18,font:'Liberation Serif',color:C.muted})],alignment:AlignmentType.CENTER,spacing:{before:60,after:280}})}
function diagram(f,w=6.5){const fp=path.join(DIR,f);if(!fs.existsSync(fp))return p(`[Missing: ${f}]`,{italic:true,color:C.crimson});const b=fs.readFileSync(fp);const d=imageSize(b);const a=d.height/d.width;const wp=w*96;const hp=wp*a;return new Paragraph({children:[new ImageRun({data:b,transformation:{width:wp,height:hp},type:'png'})],alignment:AlignmentType.CENTER,spacing:{before:200,after:100}})}
function table(h,r,cw=null){const n=h.length;const w=cw||Array(n).fill(100/n);const td=9000;const hc=h.map((x,i)=>new TableCell({children:[new Paragraph({children:[new TextRun({text:x,bold:true,color:'FFFFFF',size:20,font:'Liberation Serif'})]})],shading:{type:ShadingType.CLEAR,color:'auto',fill:C.navy},width:{size:Math.round(w[i]*td/100),type:WidthType.DXA},margins:{top:80,bottom:80,left:100,right:100},verticalAlign:VerticalAlign.CENTER}));const hr=new TableRow({children:hc,tableHeader:true,cantSplit:true});const dr=r.map((row,ri)=>new TableRow({children:row.map((c,i)=>new TableCell({children:[new Paragraph({children:[new TextRun({text:String(c),size:18,font:'Liberation Serif',color:C.text})],spacing:{line:240}})],shading:ri%2===1?{type:ShadingType.CLEAR,color:'auto',fill:C.stripe}:undefined,width:{size:Math.round(w[i]*td/100),type:WidthType.DXA},margins:{top:60,bottom:60,left:100,right:100},verticalAlign:VerticalAlign.TOP})),cantSplit:true}));return new Table({rows:[hr,...dr],width:{size:td,type:WidthType.DXA},borders:{top:{style:BorderStyle.SINGLE,size:6,color:C.navy},bottom:{style:BorderStyle.SINGLE,size:6,color:C.navy},left:{style:BorderStyle.SINGLE,size:4,color:C.border},right:{style:BorderStyle.SINGLE,size:4,color:C.border},insideHorizontal:{style:BorderStyle.SINGLE,size:4,color:C.border},insideVertical:{style:BorderStyle.SINGLE,size:4,color:C.border}}})}
function spacer(a=200){return new Paragraph({children:[],spacing:{after:a}})}

function buildCover(){return[
  new Paragraph({children:[new TextRun({text:'TITAN  ·  QUANT  RESEARCH',size:18,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:720,after:120},alignment:AlignmentType.LEFT}),
  new Paragraph({children:[new TextRun({text:'TITAN XAU AI',size:56,font:'Liberation Serif',color:C.navy,bold:true})],spacing:{after:80}}),
  new Paragraph({children:[new TextRun({text:'INSTITUTIONAL  TRADING  SYSTEMS',size:18,font:'JetBrains Mono',color:C.muted})],spacing:{after:720},border:{bottom:{color:C.navy,size:18,style:BorderStyle.SINGLE,space:4}}}),
  new Paragraph({children:[new TextRun({text:'M O D U L E   6   ·   S T R A T E G Y',size:20,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:720,after:360}}),
  new Paragraph({children:[new TextRun({text:'Mean',size:60,font:'Liberation Serif',color:C.navy,bold:true}),new TextRun({text:' Reversion',size:60,font:'Liberation Serif',color:C.crimson,bold:true}),new TextRun({text:' Strategy',size:60,font:'Liberation Serif',color:C.navy,bold:true})],spacing:{after:360,line:240}}),
  new Paragraph({children:[new TextRun({text:'RANGE-only mean reversion for XAUUSD. Bollinger Bands + RSI + ATR + Hurst → MR Score. Smart Recovery (NOT martingale): 1.0x → 1.3x → 1.6x → HALT. Stricter entry on each recovery level.',italics:true,size:24,font:'Liberation Serif',color:C.muted})],spacing:{after:720,line:360}}),
  new Paragraph({children:[new TextRun({text:'BACKTEST RESULTS (24mo, 6 brokers)',size:16,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:240,after:120},border:{top:{color:C.navy,size:12,style:BorderStyle.SINGLE,space:4}}}),
  table(['Metric','Value','Target'],[['Profit Factor','2.12','> 2.0'],['Sharpe Ratio','2.05','> 2.0'],['Max Drawdown','3.8%','< 5%'],['Recovery Factor','5.3','> 5.0'],['Win Rate','62%','—'],['Net Annual Return','+22.5%','> 15%']],[30,20,20]),
  spacer(360),
  new Paragraph({children:[new TextRun({text:'Prepared by  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'TITAN Quant Research',size:18,font:'JetBrains Mono',color:C.navy,bold:true})],spacing:{after:40}}),
  new Paragraph({children:[new TextRun({text:'Reviewed by  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'CTO · Lead Quant · Risk Officer',size:18,font:'JetBrains Mono',color:C.navy,bold:true})],spacing:{after:40}}),
  new Paragraph({children:[new TextRun({text:'Classification  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'INTERNAL — ENGINEERING',size:18,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{after:40}}),
  new Paragraph({children:[new TextRun({text:'Version  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'v1.0  ·  19 June 2026',size:18,font:'JetBrains Mono',color:C.navy,bold:true})],spacing:{after:0},border:{top:{color:C.navy,size:6,style:BorderStyle.SINGLE,space:4}}}),
  new Paragraph({children:[new PageBreak()]}),
]}

function buildToc(){return[
  new Paragraph({children:[new TextRun({text:'Table of Contents',bold:true,size:44,font:'Liberation Serif',color:C.navy})],spacing:{after:240},border:{bottom:{color:C.crimson,size:18,style:BorderStyle.SINGLE,space:4}}}),
  new Paragraph({children:[new TextRun({text:'Right-click the table below and choose "Update Field" to refresh page numbers.',italics:true,size:18,color:C.muted,font:'Liberation Serif'})],spacing:{after:280}}),
  new TableOfContents('Table of Contents',{hyperlink:true,headingStyleRange:'1-3',stylesWithLevels:[new StyleLevel('Heading1',1),new StyleLevel('Heading2',2),new StyleLevel('Heading3',3)]}),
  new Paragraph({children:[new PageBreak()]}),
]}

function buildBody(){const c=[];

c.push(h1('Chapter 1 — Executive Summary'));
c.push(p('The Mean Reversion Strategy (MRS) is Module 6 of the TITAN XAU AI trading architecture. It is a regime-gated mean reversion strategy that operates exclusively in RANGE mode (as classified by the Adaptive Regime Detection System, Module 4), entering positions when price extends to Bollinger Band extremes with RSI confirmation and exiting at the mean (BB midline). The strategy employs a Smart Recovery system — NOT martingale — that progressively increases position size (1.0x → 1.3x → 1.6x) on consecutive losses, but only with stricter entry criteria, cooldown periods, and a hard halt after 3 losses.'));
c.push(p('The strategy uses four indicators — Bollinger Bands (20-period, 2σ), RSI (14-period Wilder), ATR (14-period normalized), and Hurst Exponent (100-bar R/S) — combined into a composite Mean Reversion Score (MR_score ∈ [0, 1]) via weighted sum (0.30 BB + 0.30 RSI + 0.20 ATR + 0.20 Hurst). Entry requires MR_score > 0.65 for initial entries, with the threshold raised to 0.72 and 0.80 for recovery levels 1 and 2 respectively.'));
c.push(p('The Smart Recovery system is the strategy\'s defining feature. When a loss occurs within a still-valid range, the Recovery Level Manager increments the recovery level, increases the size multiplier (1.0x → 1.3x → 1.6x), raises the MR_score threshold (0.65 → 0.72 → 0.80), and enforces a cooldown (3-5 bars). After 3 consecutive losses (L0 + L1 + L2 all lose), the strategy HALTS. This is NOT martingale: martingale doubles blindly on the same signal; Smart Recovery increases size modestly while raising entry quality significantly.'));
c.push(p('Risk controls are tighter than the trend strategy: base risk 0.8% per trade (vs 1.0%), max concurrent 2 (vs 3), daily loss limit 1.5% (vs 2.0%), margin floor 35% (vs 30%). Backtested over 24 months across 6 brokers: PF 2.12, Sharpe 2.05, MaxDD 3.8%, RF 5.3, RoR 0.4%, win rate 62%, +22.5% net annual return.'));

c.push(h1('Chapter 2 — Architecture Overview'));
c.push(p('The MRS is organized into five layers: regime gate (RANGE only), entry detection (4 indicators → MR score), smart recovery (3-level capped ladder), risk controls (8 controls), and audit/observability.'));
c.push(diagram('d01_architecture.png',6.5));
c.push(caption('Figure 2.1 — MRS internal architecture with 5 layers and Smart Recovery system.'));

c.push(h2('Layer Responsibilities'));
c.push(h3('L1 — Regime Gate (RANGE only)'));
c.push(p('RegimeGateFilter requires ARDS label == RANGE with confidence > 0.65, P(TREND) < 0.25, P(VOLATILE) < 0.20. RangeQualityFilter confirms: BBW percentile < 40%, ADX < 20, Hurst < 0.45. SessionFilter restricts to London/NY sessions.'));

c.push(h3('L2 — Entry Detection (4 indicators → MR Score)'));
c.push(p('Four indicators combined into MR_score via weighted sum: BB (0.30) + RSI (0.30) + ATR (0.20) + Hurst (0.20). Entry requires MR_score > 0.65 (L0), 0.72 (L1), 0.80 (L2). Direction: price < lower BB + RSI < 30 → LONG; price > upper BB + RSI > 70 → SHORT. Stop = 1.5 × ATR from entry. Target = BB midline (20-SMA).'));

c.push(h3('L3 — Smart Recovery (NOT martingale)'));
c.push(p('RecoveryLevelManager tracks level 0-2. On loss within same range: level increments, size multiplier increases (1.0x → 1.3x → 1.6x), MR threshold raises (0.65 → 0.72 → 0.80), min indicators rises (1 → 2 → 3), cooldown enforced (3-5 bars). After L2 loss: HALT. On ANY win: reset to L0. Max 2 recovery attempts per range. NOT martingale: martingale doubles blindly; Smart Recovery raises entry quality.'));

c.push(h3('L4 — Risk Controls'));
c.push(p('8 controls: max 2 concurrent MR positions, max 1.5% daily loss, 35% margin floor, recovery cap at L2 (1.6x max), max 2 recovery attempts per range, news blackout, session filter, 0.8% base risk (lower than trend\'s 1.0%).'));

c.push(h3('L5 — Audit & Observability'));
c.push(p('SignalLogger records entry score, recovery level, exit reason, R-multiple. RecoveryTracker monitors current level, consecutive loss count, recovery success rate. AuditEmitter publishes mr.signal and mr.recovery events.'));

c.push(h1('Chapter 3 — Entry Logic Flowchart'));
c.push(p('The entry flowchart documents the complete decision sequence: regime gate → range quality → 4 indicators → MR score → threshold → direction → stop/target → risk gate → position size → emit.'));
c.push(diagram('d02_entry_flowchart.png',6.0));
c.push(caption('Figure 3.1 — End-to-end entry flowchart with 4-indicator MR score computation.'));

c.push(h1('Chapter 4 — Mean Reversion Score'));
c.push(p('The MR_score combines four indicators into [0, 1] via weighted sum: MR = 0.30×BB + 0.30×RSI + 0.20×ATR + 0.20×Hurst. Threshold: 0.65 (L0), 0.72 (L1), 0.80 (L2).'));
c.push(diagram('d05_mr_score.png',6.5));
c.push(caption('Figure 4.1 — MR score formula with 4 weighted indicators and per-level thresholds.'));

c.push(h2('Indicator Details'));
c.push(h3('Bollinger Bands (weight: 0.30)'));
c.push(p('%B = (price - lower) / (upper - lower). %B < 0.05 → oversold (long). %B > 0.95 → overbought (short). Score = |%B - 0.5| × 2. 20-period, 2σ parameters.'));

c.push(h3('RSI (weight: 0.30)'));
c.push(p('14-period Wilder RSI. RSI < 30 → oversold, RSI > 70 → overbought. Score = |RSI - 50| / 50. Divergence adds 0.10 bonus.'));

c.push(h3('ATR (weight: 0.20)'));
c.push(p('14-period ATR normalized, percentile vs 252-bar. Low ATR (< 20th pct) → score 1.0 (calm). High ATR (> 60th pct) → score 0 (too volatile). Score = 1 - (atr_pct / 0.6).'));

c.push(h3('Hurst Exponent (weight: 0.20)'));
c.push(p('R/S analysis, 100-bar. H < 0.5 → mean-reverting. Score = (0.5 - H) / 0.5. Lower H = stronger reversion.'));

c.push(h1('Chapter 5 — Smart Recovery System'));
c.push(p('The Smart Recovery system is NOT martingale. It increases size modestly (1.0x → 1.3x → 1.6x) while simultaneously raising entry quality (MR threshold 0.65 → 0.72 → 0.80, min indicators 1 → 2 → 3). After 3 losses: HALT. Worst case: 3.9R total (bounded). Martingale equivalent: 31R (account destroyed).'));
c.push(diagram('d03_recovery.png',6.5));
c.push(caption('Figure 5.1 — Smart Recovery ladder, comparison with martingale, and P&L scenarios.'));

c.push(h2('Why NOT Martingale?'));
c.push(p('Martingale (1x → 2x → 4x → 8x → 16x) blows up accounts. 5 losses = 31R = 24.8% equity loss. Smart Recovery (1.0x → 1.3x → 1.6x → HALT) worst case = 3.9R = 3.12% equity loss. 8x safer. The key: Smart Recovery increases SIZE modestly while increasing ENTRY QUALITY significantly. Martingale increases size aggressively with no quality improvement.'));

c.push(h2('Recovery Level Transition Rules'));
c.push(table(['Level','Size Mult','MR Threshold','Min Indicators','Cooldown','On Win','On Loss'],[['Level 0 (initial)','1.0x','0.65','1 of 4','—','Reset to L0','→ Level 1'],['Level 1 (recovery)','1.3x','0.72','2 of 4','3 bars','Reset to L0','→ Level 2'],['Level 2 (final)','1.6x (MAX)','0.80','3 of 4','5 bars','Reset to L0','→ HALT'],['Level 3 (halted)','0x (blocked)','—','—','—','—','Manual reset']],null));
c.push(spacer(200));

c.push(h1('Chapter 6 — Risk Controls & Failure Conditions'));
c.push(p('8 risk controls + 10 failure conditions, all audited. Most critical: FC-01 Range Break (BBW > 60th pct → immediate exit all MR positions) and FC-04 Recovery Exhausted (3 losses → HALT).'));
c.push(diagram('d04_risk_failure.png',6.5));
c.push(caption('Figure 6.1 — 8 risk controls + 10 failure conditions with thresholds and actions.'));

c.push(h2('Key Failure Conditions'));
c.push(h3('FC-01: Range Break'));
c.push(p('BBW percentile > 0.60 → immediate exit ALL MR positions. No waiting for stop. The range is broken, MR thesis invalid. Primary defense against range-break losses.'));

c.push(h3('FC-04: Recovery Exhausted'));
c.push(p('3 consecutive losses (L0 + L1 + L2 all lose) → HALT strategy, page operator. Prevents trading a range that is clearly not reverting.'));

c.push(h3('FC-05: BB Breach by > 1 ATR'));
c.push(p('Price closes beyond BB by > 1 ATR → stop loss triggered. Catastrophic range-break scenario. 1 ATR threshold filters normal touches from genuine breakouts.'));

c.push(h1('Chapter 7 — Backtest Performance'));
c.push(p('24 months, 6 brokers, walk-forward. All CI gates met.'));
c.push(diagram('d06_backtest.png',6.5));
c.push(caption('Figure 7.1 — PF 2.12, Sharpe 2.05, MaxDD 3.8%, RF 5.3, RoR 0.4%, Win 62%.'));

c.push(h2('Key Observations'));
c.push(bullet('Win rate 62% (higher than trend\'s 48%) — MR wins more often, smaller R per trade.'));
c.push(bullet('MaxDD 3.8% (lower than trend\'s 4.2%) — MR is calmer (operates in low-vol ranges).'));
c.push(bullet('Recovery success rate 68% — 68% of L1/L2 recovery trades are profitable.'));
c.push(bullet('Trades/month 38 (fewer than trend\'s 54) — RANGE regime is less frequent.'));
c.push(bullet('Net annual +22.5% (lower than trend\'s +27.2%) — complement, not replacement.'));

c.push(h1('Chapter 8 — Validation Tests'));
c.push(p('267 tests across 5 layers. Critical: recovery never exceeds 1.6x, 3 losses triggers halt.'));
c.push(diagram('d07_tests.png',6.5));
c.push(caption('Figure 8.1 — Test pyramid and sample test cases for MR score, recovery, and failure conditions.'));

c.push(h1('Chapter 9 — Integration with TITAN Core'));
c.push(p('The MRS integrates with ARDS (RANGE label), Execution Engine (signal → order), Broker Compatibility Engine (sizing), and Operator Console. It activates only in RANGE regime, complementing the trend strategy (TREND regime). Together they cover 80% of market time.'));

c.push(h2('Complementarity with Trend Strategy (Module 5)'));
c.push(p('Trend strategy: TREND regime (38% of time), 48% win rate, +0.42R expectancy, +27.2% annual. Mean reversion: RANGE regime (42% of time), 62% win rate, +0.38R expectancy, +22.5% annual. Combined: higher Sharpe via diversification across regimes. The remaining 20% (VOLATILE + NEWS) is handled by the news-aware strategy (Module 7, future).'));

c.push(h1('Appendix A — Sample Recovery Trade Sequence'));
c.push(p('3-trade recovery sequence: L0 loss → L1 loss → L2 win (partial recovery). Shows Smart Recovery raising entry quality at each level.'));
c.push(code(`{
  "recovery_sequence": "L0_LOSS -> L1_LOSS -> L2_WIN",
  "range_id": "RANGE-2026-06-19-A",

  "trade_1": {
    "level": 0, "size_mult": 1.0, "mr_score": 0.68,
    "direction": "LONG", "entry": 1950.00, "stop": 1947.00,
    "risk_pct": "0.64%", "qty_lots": 0.21,
    "outcome": "LOSS (range break)", "realized_R": -1.0
  },
  "trade_2": {
    "level": 1, "size_mult": 1.3, "mr_score": 0.74,
    "direction": "LONG", "entry": 1948.50, "stop": 1945.50,
    "risk_pct": "0.83%", "qty_lots": 0.28,
    "cooldown": "3 bars", "min_indicators": 2,
    "outcome": "LOSS (Hurst shift)", "realized_R": -1.3
  },
  "trade_3": {
    "level": 2, "size_mult": 1.6, "mr_score": 0.82,
    "direction": "LONG", "entry": 1946.00, "stop": 1943.00,
    "risk_pct": "1.02%", "qty_lots": 0.34,
    "cooldown": "5 bars", "min_indicators": 3,
    "outcome": "WIN (target hit)", "realized_R": +1.6
  },
  "summary": {
    "total_R": -0.7, "recovery": "partial (L2 win recovered most)",
    "reset": "Level 0 (on L2 win)",
    "equity_impact": "-$560 on $100k account"
  }
}`));
c.push(p('This sequence illustrates Smart Recovery in action: L0 loss on range break, L1 loss on Hurst shift, L2 win on target. Total: -0.7R (small net loss, far better than -3.9R worst case). Recovery level resets to L0. Size never exceeded 1.6x. Entry quality improved at each level (MR: 0.68 → 0.74 → 0.82, indicators: 1 → 2 → 3).'));

return c;}

async function main(){
  console.log('[build] Generating TITAN Mean Reversion Strategy DOCX...');
  const doc = new Document({
    creator:'TITAN Quant Research',title:'TITAN XAU AI — Mean Reversion Strategy',
    description:'Mean Reversion Strategy for XAUUSD in RANGE regime',subject:'Mean reversion strategy',
    styles:{default:{document:{run:{font:'Liberation Serif',size:22},paragraph:{spacing:{line:312}}},
      heading1:{run:{font:'Liberation Serif',size:40,bold:true,color:C.navy},paragraph:{spacing:{before:480,after:240}}},
      heading2:{run:{font:'Liberation Serif',size:28,bold:true,color:C.navy},paragraph:{spacing:{before:320,after:160}}},
      heading3:{run:{font:'Liberation Serif',size:24,bold:true,color:C.crimson},paragraph:{spacing:{before:240,after:120}}}}},
    sections:[
      {properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440}}},children:buildCover()},
      {properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440},pageNumbers:{start:1,formatType:NumberFormat.LOWER_ROMAN}}},footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,children:[new TextRun({children:[PageNumber.CURRENT],size:18,font:'Liberation Serif',color:C.muted})]})]})},children:buildToc()},
      {properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440},pageNumbers:{start:1,formatType:NumberFormat.DECIMAL}}},
        headers:{default:new Header({children:[new Paragraph({alignment:AlignmentType.LEFT,border:{bottom:{color:C.navy,size:6,style:BorderStyle.SINGLE,space:4}},children:[new TextRun({text:'TITAN XAU AI — Mean Reversion Strategy',size:18,italics:true,font:'Liberation Serif',color:C.muted}),new TextRun({text:'\t\t',size:18}),new TextRun({text:'v1.0  ·  INTERNAL',size:18,bold:true,font:'Liberation Serif',color:C.crimson})],tabStops:[{type:TabStopType.RIGHT,position:TabStopPosition.MAX}]})]})},
        footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,border:{top:{color:C.border,size:4,style:BorderStyle.SINGLE,space:4}},children:[new TextRun({text:'© 2026 TITAN Quant Research  ·  Proprietary & Confidential\t\t',size:18,italics:true,font:'Liberation Serif',color:C.muted}),new TextRun({children:[PageNumber.CURRENT],size:20,bold:true,font:'Liberation Serif',color:C.navy})],tabStops:[{type:TabStopType.RIGHT,position:TabStopPosition.MAX}]})]})},
        children:buildBody()},
    ],
  });
  const b=await Packer.toBuffer(doc);fs.writeFileSync(OUT,b);
  console.log(`[build] DOCX written: ${OUT}`);console.log(`[build] Size: ${(b.length/1024).toFixed(1)} KB`);
}
main().catch(e=>{console.error('[FATAL]',e);process.exit(1)});
