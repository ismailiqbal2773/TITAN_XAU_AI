const fs = require('fs'), path = require('path');
const { imageSize } = require('image-size');
const docx = require('docx');
const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, PageBreak, ImageRun, Table, TableRow, TableCell, WidthType, BorderStyle, TableOfContents, StyleLevel, Footer, Header, PageNumber, NumberFormat, ShadingType, TabStopType, TabStopPosition, VerticalAlign } = docx;
const C = { navy: '14213D', crimson: 'C8102E', muted: '4A5568', stripe: 'F8FAFC', border: 'CBD5E1', text: '14213D' };
const DIR = '/home/z/my-project/scripts/risk_engine/diagrams/png';
const OUT = '/home/z/my-project/download/TITAN_Institutional_Risk_Engine_v1.0.docx';

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
  new Paragraph({children:[new TextRun({text:'M O D U L E   8   ·   R I S K   E N G I N E',size:20,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:720,after:360}}),
  new Paragraph({children:[new TextRun({text:'Institutional',size:56,font:'Liberation Serif',color:C.navy,bold:true}),new TextRun({text:' Risk',size:56,font:'Liberation Serif',color:C.crimson,bold:true}),new TextRun({text:' Engine',size:56,font:'Liberation Serif',color:C.navy,bold:true})],spacing:{after:360,line:240}}),
  new Paragraph({children:[new TextRun({text:'Multi-layered risk management: 4 modes (Conservative, Balanced, Aggressive, Competition), 6 core controls (Daily/Weekly/Monthly DD, Risk Per Trade, Max Trades, Max Exposure). Kill switch <500ms. Capital preservation: loss streak, equity guardrail, volatility throttle.',italics:true,size:24,font:'Liberation Serif',color:C.muted})],spacing:{after:720,line:360}}),
  new Paragraph({children:[new TextRun({text:'RISK MODE PARAMETERS',size:16,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:240,after:120},border:{top:{color:C.navy,size:12,style:BorderStyle.SINGLE,space:4}}}),
  table(['Parameter','Conservative','Balanced','Aggressive','Competition'],[['Risk per trade','0.5%','0.8%','1.2%','2.0%'],['Daily DD hard','1.5%','2.0%','3.0%','5.0%'],['Max open trades','2','3','4','5'],['Max exposure','3%','5%','8%','12%'],['Kill switch','<500ms','<500ms','<500ms','<500ms'],['Circuit breakers','3-tier','3-tier','3-tier','3-tier']],[22,20,20,20,18]),
  spacer(360),
  new Paragraph({children:[new TextRun({text:'Prepared by  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'TITAN Quant Research',size:18,font:'JetBrains Mono',color:C.navy,bold:true})],spacing:{after:40}}),
  new Paragraph({children:[new TextRun({text:'Reviewed by  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'CTO · Risk Officer · Compliance',size:18,font:'JetBrains Mono',color:C.navy,bold:true})],spacing:{after:40}}),
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
c.push(p('The Institutional Risk Engine (IRE) is Module 8 of the TITAN XAU AI trading architecture. It is the system\'s ultimate safety system — a multi-layered risk management framework that enforces capital preservation across 4 risk modes (Conservative, Balanced, Aggressive, Competition), 6 core controls (Daily DD, Weekly DD, Monthly DD, Risk Per Trade, Max Open Trades, Max Exposure), and 3 defense layers (loss streak management, equity guardrail, volatility throttle). The IRE has structural veto power over every order: no trade reaches the broker without passing through the pre-trade risk gate.'));
c.push(p('The engine operates on a simple principle: capital preservation takes absolute precedence over alpha generation. Every architectural decision — from the 3-tier circuit breaker system (soft throttle, hard halt, critical flatten) to the kill switch (<500ms end-to-end shutdown) to the equity guardrail (auto-degrade to Conservative at 95% of starting equity) — exists to enforce this principle. The IRE is the structural guarantee that the system cannot blow up, regardless of what the strategies or AI models do.'));
c.push(p('The 4 risk modes are swappable at runtime, allowing the system to adapt its risk posture to market conditions, account size, and operator preference. Conservative mode (0.5% risk per trade, 1.5% daily DD hard limit, 2 max trades) is the default and the auto-degrade target when any circuit breaker fires. Balanced mode (0.8% risk, 2.0% daily DD, 3 max trades) is the standard production mode for most licensees. Aggressive mode (1.2% risk, 3.0% daily DD, 4 max trades) requires supervisor authorization. Competition mode (2.0% risk, 5.0% daily DD, 5 max trades) requires triple authorization (CTO + risk officer + supervisor) and is intended only for trading competitions and prop firm challenges.'));
c.push(p('The emergency shutdown system (kill switch) is the IRE\'s last line of defense. It can be triggered by 4 sources (hard DD, manual operator, license revocation, system critical) and executes a 4-action sequence in under 500 milliseconds: halt new orders, cancel pending orders, flatten all positions, and notify the operator. A 5-minute cooldown prevents panic re-triggering, and re-arm requires supervisor authorization plus mandatory degradation to Conservative mode.'));

c.push(h1('Chapter 2 — Architecture Overview'));
c.push(p('The IRE is organized into 5 layers: risk mode selector (parameter provider), pre-trade risk gate (synchronous veto), post-trade risk monitor (async DD tracking), emergency shutdown (kill switch), and capital preservation (proactive defense). A 6th layer (audit and observability) records every decision for compliance and post-incident analysis.'));
c.push(diagram('d01_architecture.png',6.5));
c.push(caption('Figure 2.1 — IRE architecture: 5 layers + audit, showing all components.'));

c.push(h2('Layer Responsibilities'));
c.push(h3('L1 — Risk Mode Selector'));
c.push(p('RiskModeManager loads the active risk mode at startup and provides mode-specific parameters to all other layers. Modes are swappable by operators with appropriate authorization. The mode auto-degrades to Conservative on any hard circuit breaker trigger.'));

c.push(h3('L2 — Pre-Trade Risk Gate (synchronous, <0.3ms)'));
c.push(p('Three validators: PositionSizeValidator (risk per trade, leverage, exposure), ConcurrencyValidator (max open trades, duplicate symbol, correlation, session, news blackout), MarginValidator (free margin floor, post-trade margin projection). If any returns REJECT, the order is blocked — no bypass. Completes in <0.3ms p99.'));

c.push(h3('L3 — Post-Trade Risk Monitor (async, continuous)'));
c.push(p('Three drawdown monitors: DailyDDMonitor (UTC day, resets at 00:00), WeeklyDDMonitor (7-day rolling), MonthlyDDMonitor (30-day rolling). Each has soft and hard thresholds. Soft: size × 0.5. Hard: halt new entries. Updates on every fill.'));

c.push(h3('L4 — Emergency Shutdown (kill switch, <500ms)'));
c.push(p('KillSwitchController executes 4-action sequence: halt new orders (atomic flag, <1ms), cancel pending (~50ms), flatten all (~200ms), notify operator (~100ms). Total <500ms. 5-minute cooldown. Re-arm requires supervisor auth + Conservative degradation.'));

c.push(h3('L5 — Capital Preservation (proactive)'));
c.push(p('Three layers: LossStreakManager (3 losses → 0.5x, 5 → halt, 7 → flatten), EquityGuardRail (95% → degrade, 90% → halt, 85% → flatten+lock), VolatilityThrottle (ATR > 60% → 0.7x, > 80% → 0.3x, > 95% → no entries).'));

c.push(h1('Chapter 3 — 4 Risk Modes'));
c.push(p('The IRE supports 4 risk modes, each with 12+ parameters covering all 6 core controls plus additional safeguards. Modes are swappable at runtime with appropriate authorization.'));
c.push(diagram('d02_risk_modes.png',6.5));
c.push(caption('Figure 3.1 — 4 risk modes with all parameters side-by-side.'));

c.push(h2('Mode Selection Guidelines'));
c.push(bullet('Conservative (0.5% risk): Default mode. Large accounts, initial deployment, post-drawdown recovery. Auto-degrade target.'));
c.push(bullet('Balanced (0.8% risk): Standard production mode for Pro tier licensees. Accounts $50k-$500k.'));
c.push(bullet('Aggressive (1.2% risk): Experienced traders, high-conviction periods. Supervisor + risk officer auth. Accounts $500k+.'));
c.push(bullet('Competition (2.0% risk): Trading competitions, prop firm challenges. Triple auth (CTO + risk officer + supervisor). Small accounts $1k-$10k.'));

c.push(h1('Chapter 4 — Risk Formulas'));
c.push(p('All risk calculations are mode-parameterized and computed continuously.'));
c.push(diagram('d03_formulas.png',6.5));
c.push(caption('Figure 4.1 — All risk formulas: DD, position size, exposure, circuit breaker triggers.'));

c.push(h2('Drawdown Calculations'));
c.push(code(`DailyDD = (peak_equity_today - current_equity) / peak_equity_today
  peak_today = max(equity) since 00:00 UTC · resets daily

WeeklyDD = (peak_equity_7d - current_equity) / peak_equity_7d
  peak_7d = max(equity) over rolling 7-day · no reset

MonthlyDD = (peak_equity_30d - current_equity) / peak_equity_30d
  peak_30d = max(equity) over rolling 30-day · no reset

Each has soft (size x 0.5) and hard (halt) thresholds.`));

c.push(h2('Position Size Formula'));
c.push(code(`qty = (equity * risk_per_trade%) / (stop_distance * tick_value)

risk_per_trade% = mode.risk_per_trade * confidence_factor * streak_factor * vol_factor
  bounded to [mode.risk_floor, mode.risk_ceiling]`));

c.push(h2('Circuit Breaker Triggers'));
c.push(bullet('SOFT (Throttle): DD soft threshold, loss streak (halt-1), ATR > 80%. Action: size × 0.5.'));
c.push(bullet('HARD (Halt): DD hard threshold, loss streak halt, equity < guard_L1. Action: no new entries, degrade to Conservative.'));
c.push(bullet('CRITICAL (Flatten): Equity < guard_L2, kill switch, broker disconnect, license revoked. Action: flatten ALL, halt, P1.'));

c.push(h1('Chapter 5 — Emergency Shutdown Logic'));
c.push(p('The kill switch is the IRE\'s last line of defense. 4 triggers, 4 actions, <500ms total, 5-min cooldown, re-arm with Conservative degradation.'));
c.push(diagram('d04_shutdown.png',6.0));
c.push(caption('Figure 5.1 — Kill switch flowchart: 4 triggers, 4 actions, cooldown, re-arm.'));

c.push(h2('Trigger Sources'));
c.push(h3('T1: Hard Drawdown (automatic)'));
c.push(p('Any drawdown monitor (daily, weekly, monthly) hits hard threshold. No human input required.'));
c.push(h3('T2: Manual Operator (2-person rule)'));
c.push(p('TRADER initiates + SUPERVISOR approves within 5-min window.'));
c.push(h3('T3: License Revoked (automatic)'));
c.push(p('License heartbeat fail + 7-day grace expired.'));
c.push(h3('T4: System Critical (automatic)'));
c.push(p('Broker disconnect, equity < guard_L3, 2+ AI models degraded.'));

c.push(h2('Shutdown Sequence'));
c.push(p('4 actions in <500ms: (1) Halt new orders (atomic flag, <1ms), (2) Cancel pending (~50ms), (3) Flatten all (~200ms, accept slippage), (4) Notify operator (~100ms, async). 5-min cooldown prevents panic re-triggering. Re-arm requires supervisor auth + Conservative degradation + size × 0.5 for 30 min.'));

c.push(h1('Chapter 6 — Capital Preservation Logic'));
c.push(p('3 proactive defense layers: loss streak management, equity guardrail, volatility throttle.'));
c.push(diagram('d05_capital.png',6.5));
c.push(caption('Figure 6.1 — 3 capital preservation layers with triggers, actions, and reset conditions.'));

c.push(h2('Layer 1: Loss Streak Manager'));
c.push(p('Anti-martingale progressive de-risking. 0-2 losses: normal (1.0x). 3 losses: throttled (0.5x). 5 losses: halted (no new entries). 7 losses: critical (flatten + lock). Any win resets to 0.'));

c.push(h2('Layer 2: Equity Guardrail'));
c.push(p('Absolute equity protection. >= 95%: normal. 90-95%: degrade to Conservative + 0.5x for 1h. 85-90%: halt + flatten. < 85%: flatten + lock (CTO unlock only). Cannot be overridden.'));

c.push(h2('Layer 3: Volatility Throttle'));
c.push(p('ATR percentile-based. < 60%: 1.0x. 60-80%: 0.7x. > 80%: 0.3x. > 95%: no new entries. Adapts to market conditions automatically.'));

c.push(h1('Chapter 7 — Risk Controls Summary'));
c.push(p('6 core controls + 6 additional = 12 total, all mode-parameterized, all audited, all CI-tested.'));
c.push(diagram('d07_controls.png',6.5));
c.push(caption('Figure 7.1 — Complete risk controls summary across all 4 modes.'));

c.push(h1('Chapter 8 — Validation Tests'));
c.push(p('200 tests across 5 categories. Critical: kill switch < 500ms, circuit breakers fire at exact thresholds, mode switch < 1s, no position exceeds risk limit, equity guardrail flatten < 2s.'));
c.push(diagram('d06_tests.png',6.5));
c.push(caption('Figure 8.1 — Test pyramid and sample test cases.'));

c.push(h1('Chapter 9 — Integration with TITAN Core'));
c.push(p('The IRE integrates with every TITAN component that touches orders or equity. The pre-trade risk gate sits between Strategy Coordinator and Execution Engine, giving it structural veto power. The kill switch uses a dedicated reverse signal bus (not the main event bus), ensuring it can reach the OrderManager even if the main bus is saturated. The structural veto is enforced by the module dependency graph — there is no code path from Strategy to Execution that bypasses the Risk Engine.'));

return c;}

async function main(){
  console.log('[build] Generating TITAN Institutional Risk Engine DOCX...');
  const doc = new Document({
    creator:'TITAN Quant Research',title:'TITAN XAU AI — Institutional Risk Engine',
    description:'Institutional Risk Engine: 4 modes, 12 controls, kill switch',subject:'Risk engine architecture',
    styles:{default:{document:{run:{font:'Liberation Serif',size:22},paragraph:{spacing:{line:312}}},
      heading1:{run:{font:'Liberation Serif',size:40,bold:true,color:C.navy},paragraph:{spacing:{before:480,after:240}}},
      heading2:{run:{font:'Liberation Serif',size:28,bold:true,color:C.navy},paragraph:{spacing:{before:320,after:160}}},
      heading3:{run:{font:'Liberation Serif',size:24,bold:true,color:C.crimson},paragraph:{spacing:{before:240,after:120}}}}},
    sections:[
      {properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440}}},children:buildCover()},
      {properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440},pageNumbers:{start:1,formatType:NumberFormat.LOWER_ROMAN}}},footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,children:[new TextRun({children:[PageNumber.CURRENT],size:18,font:'Liberation Serif',color:C.muted})]})]})},children:buildToc()},
      {properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440},pageNumbers:{start:1,formatType:NumberFormat.DECIMAL}}},
        headers:{default:new Header({children:[new Paragraph({alignment:AlignmentType.LEFT,border:{bottom:{color:C.navy,size:6,style:BorderStyle.SINGLE,space:4}},children:[new TextRun({text:'TITAN XAU AI — Institutional Risk Engine',size:18,italics:true,font:'Liberation Serif',color:C.muted}),new TextRun({text:'\t\t',size:18}),new TextRun({text:'v1.0  ·  INTERNAL',size:18,bold:true,font:'Liberation Serif',color:C.crimson})],tabStops:[{type:TabStopType.RIGHT,position:TabStopPosition.MAX}]})]})},
        footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,border:{top:{color:C.border,size:4,style:BorderStyle.SINGLE,space:4}},children:[new TextRun({text:'© 2026 TITAN Quant Research  ·  Proprietary & Confidential\t\t',size:18,italics:true,font:'Liberation Serif',color:C.muted}),new TextRun({children:[PageNumber.CURRENT],size:20,bold:true,font:'Liberation Serif',color:C.navy})],tabStops:[{type:TabStopType.RIGHT,position:TabStopPosition.MAX}]})]})},
        children:buildBody()},
    ],
  });
  const b=await Packer.toBuffer(doc);fs.writeFileSync(OUT,b);
  console.log(`[build] DOCX written: ${OUT}`);console.log(`[build] Size: ${(b.length/1024).toFixed(1)} KB`);
}
main().catch(e=>{console.error('[FATAL]',e);process.exit(1)});
