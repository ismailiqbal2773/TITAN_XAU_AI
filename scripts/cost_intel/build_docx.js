const fs=require('fs'),path=require('path');const{imageSize}=require('image-size');const docx=require('docx');
const{Document,Packer,Paragraph,TextRun,HeadingLevel,AlignmentType,PageBreak,ImageRun,Table,TableRow,TableCell,WidthType,BorderStyle,TableOfContents,StyleLevel,Footer,Header,PageNumber,NumberFormat,ShadingType,TabStopType,TabStopPosition,VerticalAlign}=docx;
const C={navy:'14213D',crimson:'C8102E',muted:'4A5568',stripe:'F8FAFC',border:'CBD5E1',text:'14213D'};
const DIR='/home/z/my-project/scripts/cost_intel/diagrams/png';const OUT='/home/z/my-project/download/TITAN_Execution_Cost_Intelligence_v1.0.docx';
function p(t,o={}){const r=(Array.isArray(t)?t:[{text:t}]).map(x=>new TextRun({text:x.text,bold:x.bold||o.bold,italics:x.italic||o.italic,color:x.color||o.color||C.text,size:(x.size||o.size||22),font:'Liberation Serif'}));return new Paragraph({children:r,spacing:{after:160,line:312},alignment:o.alignment||AlignmentType.JUSTIFIED})}
function h1(t){return new Paragraph({children:[new TextRun({text:t,bold:true,color:C.navy,size:40,font:'Liberation Serif'})],heading:HeadingLevel.HEADING_1,spacing:{before:480,after:240},pageBreakBefore:true,border:{bottom:{color:C.crimson,size:18,style:BorderStyle.SINGLE,space:4}}})}
function h2(t){return new Paragraph({children:[new TextRun({text:t,bold:true,color:C.navy,size:28,font:'Liberation Serif'})],heading:HeadingLevel.HEADING_2,spacing:{before:320,after:160}})}
function h3(t){return new Paragraph({children:[new TextRun({text:t,bold:true,color:C.crimson,size:24,font:'Liberation Serif'})],heading:HeadingLevel.HEADING_3,spacing:{before:240,after:120}})}
function bullet(t){return new Paragraph({children:[new TextRun({text:t,size:22,font:'Liberation Serif',color:C.text})],bullet:{level:0},spacing:{after:80,line:280}})}
function code(t){return new Paragraph({children:[new TextRun({text:t,size:18,font:'DejaVu Sans Mono',color:C.text})],spacing:{before:120,after:200,line:240},shading:{type:ShadingType.CLEAR,color:'auto',fill:C.stripe},border:{left:{color:C.crimson,size:18,style:BorderStyle.SINGLE,space:6}},indent:{left:240,right:240}})}
function caption(t){return new Paragraph({children:[new TextRun({text:t,italics:true,size:18,font:'Liberation Serif',color:C.muted})],alignment:AlignmentType.CENTER,spacing:{before:60,after:280}})}
function diagram(f,w=6.5){const fp=path.join(DIR,f);if(!fs.existsSync(fp))return p(`[Missing: ${f}]`,{italic:true,color:C.crimson});const b=fs.readFileSync(fp);const d=imageSize(b);const a=d.height/d.width;const wp=w*96;const hp=wp*a;return new Paragraph({children:[new ImageRun({data:b,transformation:{width:wp,height:hp},type:'png'})],alignment:AlignmentType.CENTER,spacing:{before:200,after:100}})}
function table(h,r){const n=h.length;const w=Array(n).fill(100/n);const td=9000;const hc=h.map((x,i)=>new TableCell({children:[new Paragraph({children:[new TextRun({text:x,bold:true,color:'FFFFFF',size:20,font:'Liberation Serif'})]})],shading:{type:ShadingType.CLEAR,color:'auto',fill:C.navy},width:{size:Math.round(w[i]*td/100),type:WidthType.DXA},margins:{top:80,bottom:80,left:100,right:100},verticalAlign:VerticalAlign.CENTER}));const hr=new TableRow({children:hc,tableHeader:true,cantSplit:true});const dr=r.map((row,ri)=>new TableRow({children:row.map((c,i)=>new TableCell({children:[new Paragraph({children:[new TextRun({text:String(c),size:18,font:'Liberation Serif',color:C.text})],spacing:{line:240}})],shading:ri%2===1?{type:ShadingType.CLEAR,color:'auto',fill:C.stripe}:undefined,width:{size:Math.round(w[i]*td/100),type:WidthType.DXA},margins:{top:60,bottom:60,left:100,right:100},verticalAlign:VerticalAlign.TOP})),cantSplit:true}));return new Table({rows:[hr,...dr],width:{size:td,type:WidthType.DXA},borders:{top:{style:BorderStyle.SINGLE,size:6,color:C.navy},bottom:{style:BorderStyle.SINGLE,size:6,color:C.navy},left:{style:BorderStyle.SINGLE,size:4,color:C.border},right:{style:BorderStyle.SINGLE,size:4,color:C.border},insideHorizontal:{style:BorderStyle.SINGLE,size:4,color:C.border},insideVertical:{style:BorderStyle.SINGLE,size:4,color:C.border}}})}
function spacer(a=200){return new Paragraph({children:[],spacing:{after:a}})}

function buildCover(){return[
new Paragraph({children:[new TextRun({text:'TITAN  ·  QUANT  RESEARCH',size:18,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:720,after:120},alignment:AlignmentType.LEFT}),
new Paragraph({children:[new TextRun({text:'TITAN XAU AI',size:56,font:'Liberation Serif',color:C.navy,bold:true})],spacing:{after:80}}),
new Paragraph({children:[new TextRun({text:'INSTITUTIONAL  TRADING  SYSTEMS',size:18,font:'JetBrains Mono',color:C.muted})],spacing:{after:720},border:{bottom:{color:C.navy,size:18,style:BorderStyle.SINGLE,space:4}}}),
new Paragraph({children:[new TextRun({text:'M O D U L E   9   ·   C O S T   I N T E L',size:20,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:720,after:360}}),
new Paragraph({children:[new TextRun({text:'Execution Cost',size:56,font:'Liberation Serif',color:C.navy,bold:true}),new TextRun({text:' Intelligence',size:56,font:'Liberation Serif',color:C.crimson,bold:true})],spacing:{after:360,line:240}}),
new Paragraph({children:[new TextRun({text:'5 cost components (spread, commission, swap, slippage, latency) in bps. Trade only if expected edge remains positive. EQS per-trade scoring. BQS broker ranking. Adaptive cost learning.',italics:true,size:24,font:'Liberation Serif',color:C.muted})],spacing:{after:720,line:360}}),
new Paragraph({children:[new TextRun({text:'KEY METRICS',size:16,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:240,after:120},border:{top:{color:C.navy,size:12,style:BorderStyle.SINGLE,space:4}}}),
table(['Metric','Value'],[['Cost components','5 (spread, commission, swap, slippage, latency)'],['Min edge threshold','3.0 bps'],['Brokers ranked','6 (BQS monthly)'],['EQS factors','5 (per-trade, 0-100)'],['Decision','Trade only if edge > 0']],[40,60]),
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
c.push(p('The Execution Cost Intelligence (ECI) module is Module 9 of the TITAN XAU AI trading architecture. It is the system\'s cost-awareness layer — a real-time cost measurement, modeling, and decision framework that ensures no trade is placed unless the expected edge remains positive after all execution costs. The ECI measures 5 cost components (spread, commission, swap, slippage, latency), aggregates them into a total cost estimate in basis points, and computes the expected net edge: signal_edge minus total_cost. If the net edge is negative, the trade is rejected.'));
c.push(p('The module\'s core innovation is the EdgeCalculator — a pre-trade decision model that normalizes all costs to basis points of notional, making them comparable across brokers. Two scoring systems provide ongoing quality assessment: EQS (per-trade, 5-factor) and BQS (per-broker, comparative ranking). A Cost Learning Engine continuously updates slippage and latency models from realized fills.'));

c.push(h1('Chapter 2 — Architecture Overview'));
c.push(p('The ECI is organized into 6 layers: cost measurement, cost model, decision model, performance scoring, broker quality scoring, and audit/observability.'));
c.push(diagram('d01_architecture.png',6.5));
c.push(caption('Figure 2.1 — ECI architecture: 6 layers, 5 cost meters, decision model, scoring, learning.'));

c.push(h1('Chapter 3 — Decision Model'));
c.push(p('The decision model computes expected net edge for every signal: expected_edge = signal_edge - total_cost. If edge <= 0: NO TRADE. If 0 < edge < 3 bps: REDUCE SIZE. If edge >= 3 bps: TRADE (full size).'));
c.push(diagram('d02_decision.png',6.0));
c.push(caption('Figure 3.1 — Decision model flowchart.'));

c.push(h1('Chapter 4 — 5 Cost Components'));
c.push(p('All costs normalized to bps: spread (bid-ask), commission (per lot/million/pct), swap (overnight), slippage (size-dependent), latency (price drift during signal-to-fill).'));
c.push(diagram('d03_components.png',6.5));
c.push(caption('Figure 4.1 — 5 cost components with formulas and ranges.'));

c.push(h1('Chapter 5 — Performance & Broker Scoring'));
c.push(p('EQS = 5-factor per-trade score (spread 0.30, slip 0.25, comm 0.20, latency 0.15, swap 0.10). BQS = 6-broker comparative ranking, monthly recompute.'));
c.push(diagram('d04_scoring.png',6.5));
c.push(caption('Figure 5.1 — EQS 5-factor model and BQS 6-broker ranking.'));

c.push(h1('Chapter 6 — Validation Logic'));
c.push(p('8 pre-trade checks + 6 post-trade verifications. Key: V6 (edge > 0), V7 (edge > 3 bps), V10 (slip <= 1.5x predicted), V14 (EQS >= 40).'));
c.push(diagram('d05_validation.png',6.5));
c.push(caption('Figure 6.1 — 8 pre-trade + 6 post-trade validation checks.'));

c.push(h1('Chapter 7 — Cost Learning Engine'));
c.push(p('Continuous model calibration from realized fills. EMA updates (alpha=0.05) on slippage, latency, and spread models. Per-broker, per-session, per-regime.'));
c.push(diagram('d07_learning.png',6.5));
c.push(caption('Figure 7.1 — Learning loop: fill → compare → update → better estimates.'));

c.push(h1('Chapter 8 — Validation Tests'));
c.push(p('180 tests. CI gates: no negative-edge trade, EQS >= 60 rolling, realized <= 1.5x expected (95%), BQS monthly.'));
c.push(diagram('d06_tests.png',6.5));
c.push(caption('Figure 8.1 — Test pyramid and sample cases.'));

c.push(h1('Chapter 9 — Integration with TITAN Core'));
c.push(p('ECI sits between Strategy Coordinator and Execution Engine. Consumes BrokerProfile (Module 2), emits cost-adjusted signals to Execution Engine (Module 3), respects Risk Engine (Module 8) ceiling.'));
c.push(code(`Signal from Strategy / AI Ensemble
  -> ECI pre-trade check:
    -> compute total_cost_bps (5 components)
    -> expected_edge = signal_edge - total_cost
    -> if edge <= 0: NO TRADE
    -> if 0 < edge < 3 bps: REDUCE SIZE
    -> if edge >= 3 bps: TRADE (full size)
    -> select best broker (highest BQS)
    -> risk gate check (Module 8)
    -> emit cost-adjusted signal to Execution Engine
  -> Post-trade: update models, compute EQS, daily TCA report`));

return c;}

async function main(){
console.log('[build] Generating TITAN Execution Cost Intelligence DOCX...');
const doc=new Document({creator:'TITAN Quant Research',title:'TITAN XAU AI — Execution Cost Intelligence',description:'Execution Cost Intelligence',subject:'Cost intelligence',
styles:{default:{document:{run:{font:'Liberation Serif',size:22},paragraph:{spacing:{line:312}}},heading1:{run:{font:'Liberation Serif',size:40,bold:true,color:C.navy},paragraph:{spacing:{before:480,after:240}}},heading2:{run:{font:'Liberation Serif',size:28,bold:true,color:C.navy},paragraph:{spacing:{before:320,after:160}}},heading3:{run:{font:'Liberation Serif',size:24,bold:true,color:C.crimson},paragraph:{spacing:{before:240,after:120}}}}},
sections:[
{properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440}}},children:buildCover()},
{properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440},pageNumbers:{start:1,formatType:NumberFormat.LOWER_ROMAN}}},footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,children:[new TextRun({children:[PageNumber.CURRENT],size:18,font:'Liberation Serif',color:C.muted})]})]})},children:buildToc()},
{properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440},pageNumbers:{start:1,formatType:NumberFormat.DECIMAL}}},headers:{default:new Header({children:[new Paragraph({alignment:AlignmentType.LEFT,border:{bottom:{color:C.navy,size:6,style:BorderStyle.SINGLE,space:4}},children:[new TextRun({text:'TITAN XAU AI — Execution Cost Intelligence',size:18,italics:true,font:'Liberation Serif',color:C.muted}),new TextRun({text:'\t\t',size:18}),new TextRun({text:'v1.0  ·  INTERNAL',size:18,bold:true,font:'Liberation Serif',color:C.crimson})],tabStops:[{type:TabStopType.RIGHT,position:TabStopPosition.MAX}]})]})},footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,border:{top:{color:C.border,size:4,style:BorderStyle.SINGLE,space:4}},children:[new TextRun({text:'© 2026 TITAN Quant Research  ·  Proprietary & Confidential\t\t',size:18,italics:true,font:'Liberation Serif',color:C.muted}),new TextRun({children:[PageNumber.CURRENT],size:20,bold:true,font:'Liberation Serif',color:C.navy})],tabStops:[{type:TabStopType.RIGHT,position:TabStopPosition.MAX}]})]})},children:buildBody()},
]});
const b=await Packer.toBuffer(doc);fs.writeFileSync(OUT,b);
console.log(`[build] DOCX written: ${OUT}`);console.log(`[build] Size: ${(b.length/1024).toFixed(1)} KB`);}
main().catch(e=>{console.error('[FATAL]',e);process.exit(1)});
