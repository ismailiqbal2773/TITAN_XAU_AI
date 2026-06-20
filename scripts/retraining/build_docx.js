const fs=require('fs'),path=require('path');const{imageSize}=require('image-size');const docx=require('docx');
const{Document,Packer,Paragraph,TextRun,HeadingLevel,AlignmentType,PageBreak,ImageRun,Table,TableRow,TableCell,WidthType,BorderStyle,TableOfContents,StyleLevel,Footer,Header,PageNumber,NumberFormat,ShadingType,TabStopType,TabStopPosition,VerticalAlign}=docx;
const C={navy:'14213D',crimson:'C8102E',muted:'4A5568',stripe:'F8FAFC',border:'CBD5E1',text:'14213D'};
const DIR='/home/z/my-project/scripts/retraining/diagrams/png';const OUT='/home/z/my-project/download/TITAN_Retraining_Framework_v1.0.docx';
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
new Paragraph({children:[new TextRun({text:'M O D U L E   1 0   ·   M L   L I F E C Y C L E',size:20,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:720,after:360}}),
new Paragraph({children:[new TextRun({text:'Retraining',size:56,font:'Liberation Serif',color:C.navy,bold:true}),new TextRun({text:' Framework',size:56,font:'Liberation Serif',color:C.crimson,bold:true})],spacing:{after:360,line:240}}),
new Paragraph({children:[new TextRun({text:'Weekly + monthly retraining. Model drift detection (PSI). Performance decay detection (Sharpe/F1). Champion-challenger A/B testing. Rollback < 30s. MLflow version control. Governance board + audit trail.',italics:true,size:24,font:'Liberation Serif',color:C.muted})],spacing:{after:720,line:360}}),
new Paragraph({children:[new TextRun({text:'KEY FEATURES',size:16,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:240,after:120},border:{top:{color:C.navy,size:12,style:BorderStyle.SINGLE,space:4}}}),
table(['Feature','Value'],[['Retrain triggers','3 (weekly, monthly, emergency)'],['Rollback time','< 30 seconds'],['CI gates','8 (all must pass)'],['PSI threshold','0.25 (auto-retrain)'],['Champion-challenger','Canary 10% -> A/B 50% -> promote'],['Version control','MLflow registry + full lineage']],null),
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
c.push(p('The Retraining Framework (RTF) is Module 10 of the TITAN XAU AI trading architecture. It is the system\'s model lifecycle management layer — an automated framework that schedules, executes, validates, and governs the retraining of all 4 AI models (XGBoost, LSTM, Transformer, RL) plus the HMM regime detector. The RTF ensures that the AI models stay current as market structure evolves, with three retrain triggers: weekly scheduled (XGBoost + LSTM + Transformer), monthly scheduled (RL + HMM), and emergency (triggered by model drift or performance decay).'));
c.push(p('The framework implements a Champion-Challenger model: the current production model (champion) serves 100% of traffic, while a newly retrained model (challenger) goes through canary (10% for 1 hour) and A/B testing (50% for 24 hours) before promotion. The challenger must beat the champion on Sharpe, MaxDD, and F1 to be promoted. If the challenger fails, the champion is retained. If the challenger is promoted but later underperforms, an automated rollback reverts to the previous champion in under 30 seconds.'));
c.push(p('Model drift detection runs continuously. Feature drift is measured via Population Stability Index (PSI) per feature, computed daily: PSI < 0.10 is stable, 0.10-0.20 is watch, 0.20-0.25 is alert, and > 0.25 triggers an emergency retrain. Concept drift is measured via rolling F1 drop: a drop > 15% from baseline triggers emergency retrain. Performance decay is measured via rolling Sharpe: a drop > 25% triggers emergency retrain.'));
c.push(p('Version control is managed by MLflow, which stores every model version with full lineage: data version, feature version, model artifacts, training metrics, validation metrics, and deployment decisions. Rollback is always available — the previous champion\'s artifacts are pre-cached on inference nodes, enabling a rollback in under 30 seconds with zero downtime and zero data loss.'));

c.push(h1('Chapter 2 — Architecture Overview'));
c.push(p('The RTF is organized into 6 layers: retrain scheduler, drift and decay detection, retrain pipeline, champion-challenger, governance, and monitoring.'));
c.push(diagram('d01_architecture.png',6.5));
c.push(caption('Figure 2.1 — RTF architecture: 6 layers.'));

c.push(h2('Layer Responsibilities'));
c.push(h3('L1 — Retrain Scheduler'));
c.push(p('WeeklyRetrainer: Sunday 22:00 UTC, XGBoost + LSTM + Transformer, ~6h. MonthlyRetrainer: 1st Sunday, RL PPO + HMM, ~12h total.'));

c.push(h3('L2 — Drift & Decay Detection'));
c.push(p('ModelDriftDetector: PSI per feature (daily, > 0.25 = emergency retrain) + concept drift (F1 drop > 15% = emergency). PerformanceDecayDetector: rolling 100-trade Sharpe (drop > 25% = emergency) + per-model F1 tracking.'));

c.push(h3('L3 — Retrain Pipeline'));
c.push(p('DataPreparation → ModelTrainer (parallel, Optuna TPE, 200 trials, walk-forward 5 folds) → ValidationGate (F1 > 0.60, Sharpe > 2.0, drop < 5% vs champion).'));

c.push(h3('L4 — Champion-Challenger'));
c.push(p('Champion (100% traffic) vs Challenger (canary 10% → A/B 50% → promote if beats champion). VersionController: MLflow registry, rollback < 30s.'));

c.push(h3('L5 — Governance & Monitoring'));
c.push(p('GovernanceBoard: CTO + Lead Quant + Risk Officer + ML Engineer, monthly review. RetrainMonitor: training progress, GPU, validation, canary. AuditTrail: hash-chained WORM, full lineage.'));

c.push(h1('Chapter 3 — Retraining Workflow'));
c.push(p('The retraining workflow documents the complete end-to-end sequence: trigger → data prep → parallel training → validation → champion-challenger → deploy.'));
c.push(diagram('d02_workflow.png',6.0));
c.push(caption('Figure 3.1 — End-to-end retraining workflow.'));

c.push(h2('Weekly Retraining'));
c.push(code(`Weekly Retrain (Sunday 22:00 UTC):
  1. Data Preparation (30 min): 24mo x 6 brokers, features, labels, 80/10/10
  2. Parallel Training (~5h): XGBoost (15min) + LSTM (2h) + Transformer (4h)
  3. Walk-Forward Validation (~30 min): 5 folds, F1 > 0.60, Sharpe > 2.0
  4. Register + Deploy (~30 min): MLflow -> canary 10% -> A/B 50% -> promote
  Total: ~6 hours`));

c.push(h2('Monthly Retraining'));
c.push(p('Monthly (1st Sunday): RL PPO (8h, 10k episodes) + HMM per-session (30min x 3). Total monthly: ~12h. Separate validation: RL reward > no-RL baseline, HMM regime F1 > 0.70.'));

c.push(h1('Chapter 4 — Drift & Decay Detection'));
c.push(p('Two independent detection systems: ModelDriftDetector (PSI + concept drift) and PerformanceDecayDetector (Sharpe + F1 + PF decay).'));
c.push(diagram('d03_drift.png',6.5));
c.push(caption('Figure 4.1 — Drift detection (PSI + F1) and performance decay (Sharpe + DD + PF).'));

c.push(h2('Feature Drift (PSI)'));
c.push(p('PSI = Sum (p_new - p_old) x ln(p_new / p_old), daily per feature. < 0.10 stable, 0.20-0.25 alert, > 0.25 emergency retrain.'));

c.push(h2('Concept Drift (F1 Drop)'));
c.push(p('Rolling 100-trade F1 vs 1000-trade baseline. Drop > 10% alert, > 15% emergency retrain. Per-model tracking.'));

c.push(h2('Performance Decay (Sharpe)'));
c.push(p('Rolling 100-trade Sharpe vs baseline (2.28). Drop > 15% alert, > 25% emergency retrain. Per-model: XGBoost, LSTM, Transformer, RL tracked independently.'));

c.push(h1('Chapter 5 — Champion-Challenger & Version Control'));
c.push(p('Champion (100% traffic) vs Challenger (canary → A/B → promote). Rollback < 30s. MLflow version control with full lineage.'));
c.push(diagram('d04_champion.png',6.5));
c.push(caption('Figure 5.1 — Champion-challenger lifecycle and rollback mechanism.'));

c.push(h2('Rollback Support'));
c.push(p('5 triggers: canary Sharpe drop > 10%, A/B drop > 5%, post-promote drop > 15%, EQS < 40 for 5+ trades, manual (2-person). Rollback: revert to previous champion from MLflow cache, < 30s, zero downtime, zero data loss.'));

c.push(h2('Version Control (MLflow)'));
c.push(p('Every model version stored with: version, data version, feature version, artifacts, training metrics, validation metrics, deploy decision. Full lineage: data -> features -> model -> metrics -> decision. Full reproducibility.'));

c.push(h1('Chapter 6 — Governance Framework'));
c.push(p('Governance board (CTO + Lead Quant + Risk Officer + ML Engineer) with approval matrix. Monthly review + quarterly audit + emergency review. Full audit trail (hash-chained WORM).'));
c.push(diagram('d05_governance.png',6.5));
c.push(caption('Figure 6.1 — Governance board, approval matrix, dashboard, alert routing.'));

c.push(h2('Approval Matrix'));
c.push(bullet('Weekly retrain: Automatic (CI gate)'));
c.push(bullet('Monthly retrain: Lead Quant review (4h SLA)'));
c.push(bullet('Emergency retrain: Automatic + post-hoc review (4h)'));
c.push(bullet('Promote: Automatic (A/B gate)'));
c.push(bullet('Auto-rollback: Automatic (< 30s)'));
c.push(bullet('Manual rollback: 2-person (TRADER + SUPERVISOR, < 5min)'));

c.push(h1('Chapter 7 — Monitoring Framework'));
c.push(p('12-panel Grafana dashboard: model versions, PSI, F1, Sharpe, retrain calendar, A/B comparison, rollback history, training progress, GPU, weights, RL actions, alerts. Auto-mitigation: PSI > 0.25 → retrain, canary drop > 10% → rollback.'));

c.push(h1('Chapter 8 — Validation Process'));
c.push(p('8 CI gates (all must pass): G1 per-model F1 > 0.60, G2 ensemble Sharpe > 2.0, G3 challenger >= champion - 5%, G4 MaxDD < 5% + RoR < 1%, G5 PSI < 0.20, G6 RL reward > baseline, G7 rollback < 30s, G8 audit complete. 150 tests total.'));
c.push(diagram('d06_validation.png',6.5));
c.push(caption('Figure 8.1 — Test pyramid and 8 CI gates.'));

c.push(h1('Chapter 9 — Integration with TITAN Core'));
c.push(p('RTF integrates with: Hybrid AI Stack (Module 7) as model lifecycle manager, Risk Engine (Module 8) for DD-triggered retrain review, Cost Intelligence (Module 9) for cost-aware model evaluation.'));

c.push(h2('Retrain Calendar'));
c.push(table(['Cadence','Models','Trigger','Duration','Canary?','Approval'],[['Weekly (Sun 22:00)','XGBoost+LSTM+Transformer','Scheduled','~6h','Yes','Automatic'],['Monthly (1st Sun)','RL PPO + HMM','Scheduled','~12h','Yes','Lead Quant'],['Emergency (anytime)','Drifted model(s)','PSI > 0.25 / F1 drop > 15%','~2-6h','No (direct)','Automatic + post-hoc'],['Manual (anytime)','Specified','Operator','~2-6h','Yes','2-person']],null));

return c;}

async function main(){
console.log('[build] Generating TITAN Retraining Framework DOCX...');
const doc=new Document({creator:'TITAN Quant Research',title:'TITAN XAU AI — Retraining Framework',description:'Retraining Framework',subject:'ML lifecycle',
styles:{default:{document:{run:{font:'Liberation Serif',size:22},paragraph:{spacing:{line:312}}},heading1:{run:{font:'Liberation Serif',size:40,bold:true,color:C.navy},paragraph:{spacing:{before:480,after:240}}},heading2:{run:{font:'Liberation Serif',size:28,bold:true,color:C.navy},paragraph:{spacing:{before:320,after:160}}},heading3:{run:{font:'Liberation Serif',size:24,bold:true,color:C.crimson},paragraph:{spacing:{before:240,after:120}}}}},
sections:[
{properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440}}},children:buildCover()},
{properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440},pageNumbers:{start:1,formatType:NumberFormat.LOWER_ROMAN}}},footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,children:[new TextRun({children:[PageNumber.CURRENT],size:18,font:'Liberation Serif',color:C.muted})]})]})},children:buildToc()},
{properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440},pageNumbers:{start:1,formatType:NumberFormat.DECIMAL}}},headers:{default:new Header({children:[new Paragraph({alignment:AlignmentType.LEFT,border:{bottom:{color:C.navy,size:6,style:BorderStyle.SINGLE,space:4}},children:[new TextRun({text:'TITAN XAU AI — Retraining Framework',size:18,italics:true,font:'Liberation Serif',color:C.muted}),new TextRun({text:'\t\t',size:18}),new TextRun({text:'v1.0  ·  INTERNAL',size:18,bold:true,font:'Liberation Serif',color:C.crimson})],tabStops:[{type:TabStopType.RIGHT,position:TabStopPosition.MAX}]})]})},footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,border:{top:{color:C.border,size:4,style:BorderStyle.SINGLE,space:4}},children:[new TextRun({text:'© 2026 TITAN Quant Research  ·  Proprietary & Confidential\t\t',size:18,italics:true,font:'Liberation Serif',color:C.muted}),new TextRun({children:[PageNumber.CURRENT],size:20,bold:true,font:'Liberation Serif',color:C.navy})],tabStops:[{type:TabStopType.RIGHT,position:TabStopPosition.MAX}]})]})},children:buildBody()},
]});
const b=await Packer.toBuffer(doc);fs.writeFileSync(OUT,b);
console.log(`[build] DOCX written: ${OUT}`);console.log(`[build] Size: ${(b.length/1024).toFixed(1)} KB`);}
main().catch(e=>{console.error('[FATAL]',e);process.exit(1)});
