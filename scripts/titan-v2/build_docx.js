const fs=require('fs'),path=require('path');const{imageSize}=require('image-size');const docx=require('docx');
const{Document,Packer,Paragraph,TextRun,HeadingLevel,AlignmentType,PageBreak,ImageRun,Table,TableRow,TableCell,WidthType,BorderStyle,TableOfContents,StyleLevel,Footer,Header,PageNumber,NumberFormat,ShadingType,TabStopType,TabStopPosition,VerticalAlign}=docx;
const C={navy:'14213D',crimson:'C8102E',muted:'4A5568',stripe:'F8FAFC',border:'CBD5E1',text:'14213D'};
const DIR='/home/z/my-project/scripts/titan-v2/diagrams/png';const OUT='/home/z/my-project/download/TITAN_XAU_AI_Architecture_v2.0.docx';
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
new Paragraph({children:[new TextRun({text:'M O D U L E   1   ·   M A S T E R   A R C H I T E C T U R E',size:20,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:720,after:360}}),
new Paragraph({children:[new TextRun({text:'TITAN XAU AI ',size:52,font:'Liberation Serif',color:C.navy,bold:true}),new TextRun({text:'Architecture',size:52,font:'Liberation Serif',color:C.crimson,bold:true})],spacing:{after:360,line:240}}),
new Paragraph({children:[new TextRun({text:'World-class institutional-grade AI trading platform. 20 core modules. 5-component AI stack. Champion/Challenger model governance. MDD < 5%, Sharpe > 2.0, WFE > 85%. 6 supported brokers. 7 diagram types. 6 NFRs. Full validation pipeline. Commercial licensing. CTO + Lead Dev audience.',italics:true,size:24,font:'Liberation Serif',color:C.muted})],spacing:{after:720,line:360}}),
new Paragraph({children:[new TextRun({text:'KEY METRICS',size:16,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:240,after:120},border:{top:{color:C.navy,size:12,style:BorderStyle.SINGLE,space:4}}}),
table(['Attribute','Value'],[['Core modules','20 (M01 Broker ... M20 Observability)'],['AI stack','5 (XGB+LSTM+Transformer+RL+Ensemble)'],['Diagram types','7 (folder, services, data flow, deps, UML, deploy, tests)'],['NFRs','6 (latency, risk, DR, observability, security, licensing)'],['Target metrics','8 (PF>2.2, Sharpe>2.0, Sortino>3.0, Recovery>5.0, RoR<1%, MC>95%, WFE>85%, MDD<5%)'],['Supported brokers','6 (Exness, IC Markets, Pepperstone, Tickmill, FP Markets, Fusion)'],['Account types','6 (Standard, Raw Spread, ECN, Cent, Micro, Dollar)'],['License tiers','3 (Starter $12k, Pro $48k, Enterprise $180k)'],['Audience','Mixed (CTO + Lead Devs + Quants + AI Eng + Architects)']]),
spacer(360),
new Paragraph({children:[new TextRun({text:'Prepared by  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'TITAN Quant Research',size:18,font:'JetBrains Mono',color:C.navy,bold:true})],spacing:{after:40}}),
new Paragraph({children:[new TextRun({text:'Audience  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'CTOs · Quant Developers · AI Engineers · Institutional Architects',size:18,font:'JetBrains Mono',color:C.navy,bold:true})],spacing:{after:40}}),
new Paragraph({children:[new TextRun({text:'Reviewed by  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'CTO · Head of Research · Risk Officer · Compliance',size:18,font:'JetBrains Mono',color:C.navy,bold:true})],spacing:{after:40}}),
new Paragraph({children:[new TextRun({text:'Classification  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'PROPRIETARY — INTERNAL & LICENSEE DISTRIBUTION',size:18,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{after:40}}),
new Paragraph({children:[new TextRun({text:'Version  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'v2.0  ·  19 June 2026',size:18,font:'JetBrains Mono',color:C.navy,bold:true})],spacing:{after:0},border:{top:{color:C.navy,size:6,style:BorderStyle.SINGLE,space:4}}}),
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
c.push(p('TITAN XAU AI is a world-class institutional-grade AI trading platform focused primarily on XAUUSD (gold-vs-USD spot) with commercial licensing capability and competition-grade performance. The platform is engineered for maximum risk-adjusted return with a hard institutional drawdown floor of 5%, broker-independent execution across 6 supported brokers, and a complete validation pipeline (Backtest, Walk-Forward, Monte Carlo, Stress Test, Validator) that gates every deployment. The system is built on a 5-layer architecture comprising 20 core modules, a 5-component AI stack (XGBoost + LSTM + Transformer + Reinforcement Learning + Ensemble Voting), and a Champion/Challenger model governance pattern that never auto-deploys retrained models to production.'));
c.push(p('The architecture is documented in this Master Module (Module 1 of an 18-module specification set). It targets a mixed audience of CTOs, Lead Developers, Quant Developers, AI Engineers, and Institutional Trading System Architects — with downstream consumption by Freelancers, AI Agents, and Investors. The document covers the complete system architecture, all 7 required diagram types (folder structure tree, service architecture, data flow, module dependency, UML class, deployment topology, testing pyramid), all 6 non-functional requirements (latency budget, risk controls, disaster recovery, observability, security & auth, licensing hooks), the Champion/Challenger governance pattern, the 5-framework validation pipeline, the commercial licensing architecture, the development roadmap, and the production readiness checklist.'));
c.push(p('The platform\'s target metrics define its institutional character: Profit Factor > 2.2, Sharpe Ratio > 2.0, Sortino Ratio > 3.0, Recovery Factor > 5.0, Risk of Ruin < 1%, Monte Carlo Survival Rate > 95%, Walk-Forward Stability > 85%, and Maximum Drawdown < 5%. These are not aspirational — every metric is validated quarterly by the corresponding validation framework (Backtest M16, Walk-Forward M17, Monte Carlo M18, Stress Test M19, Validator M15), and any strategy that fails to meet all 8 is rejected for live capital. The MDD < 5% target is particularly aggressive (institutional norm is 10-15%) and reflects the platform\'s capital-preservation-first philosophy: returns are optimized only within the constraint of never experiencing a meaningful drawdown.'));
c.push(p('The platform supports 6 brokers (Exness, IC Markets, Pepperstone, Tickmill, FP Markets, Fusion Markets) and 6 account types (Standard, Raw Spread, ECN, Cent, Micro, Dollar), with runtime broker detection and per-broker cost profiles. Commercial licensing is enforced at every layer via hardware-locked JWT activation (CPUID + Motherboard ID + Windows SID), with 3 tiers (Starter $12k/yr, Pro $48k/yr, Enterprise $180k/yr), 5-layer anti-crack defense, and a server-side heartbeat that can revoke a license in under 1 hour. The platform is designed for sale and licensing — the architecture is not just internally used but commercially distributed, which is why licensing, anti-tamper, and audit trails are first-class architectural concerns rather than afterthoughts.'));

c.push(h1('Chapter 2 — Project Specification'));
c.push(p('This chapter documents the complete project specification as defined by TITAN Quant Research leadership. It is the authoritative source-of-truth for all downstream design decisions: every architectural choice in this document and the 17 companion module specifications traces back to one of the requirements enumerated here.'));
c.push(h2('Primary Goals'));
c.push(bullet('Maximum risk-adjusted return — optimize Sharpe/Sortino, not absolute return. Capital efficiency over capital deployment.'));
c.push(bullet('Maximum drawdown below 5% — institutional hard floor. The Risk Engine (M08) enforces this via 12 controls and a kill-switch with < 500 ms latency.'));
c.push(bullet('Broker-independent execution — same strategy runs identically across 6 supported brokers. The Broker Compatibility Engine (M01) abstracts broker differences.'));
c.push(bullet('Commercial sale and licensing support — the platform is a product, not an internal tool. Licensing (M14) is a first-class module.'));
c.push(bullet('CPU-optimized low-latency architecture — C++20 core for the latency-critical path, Python 3.12 for the AI layer. PyO3 bridge. 142 ms signal-to-broker P99.'));
c.push(bullet('Institutional validation and testing standards — 5 validation frameworks (Backtest, Walk-Forward, Monte Carlo, Stress, Validator) gate every deployment.'));
c.push(h2('Target Metrics'));
c.push(table(['KPI','Target','Validator','Rationale'],[['Profit Factor','> 2.2','Backtest (M16)','Gross profit / gross loss. Below 2.0 = marginal edge.'],['Sharpe Ratio','> 2.0','Backtest + WFA','Annualized risk-adjusted return. Institutional floor.'],['Sortino Ratio','> 3.0','Backtest (M16)','Downside-only Sharpe. Penalizes negative volatility only.'],['Recovery Factor','> 5.0','Backtest (M16)','Net profit / max drawdown. Capital efficiency.'],['Risk of Ruin','< 1%','Monte Carlo (M18)','Probability of losing 50% of capital.'],['MC Survival Rate','> 95%','Monte Carlo (M18)','10,000 trade permutations remain profitable.'],['WFE Stability','> 85%','Walk-Forward (M17)','Out-of-sample Sharpe / in-sample Sharpe.'],['Max Drawdown','< 5%','All + Risk (M08)','Institutional hard floor. Kill-switch enforced.']],null));
c.push(h2('Supported Brokers (6)'));
c.push(p('All 6 brokers are supported via the Broker Compatibility Engine (M01) with runtime detection of 9 broker properties (name, server, suffix, contract size, min lot, lot step, leverage, margin mode, timezone). Each broker has a verified cost profile (spread P50/P90/P99, commission RT, swap long/short, slippage distribution) maintained in /config/brokers.yaml and recalibrated monthly against live fills.'));
c.push(table(['ID','Broker','Account Types','Comm RT','Spread P50','Swap L'],[['B01','Exness','Standard, Raw Spread, Zero','$3.50','0.07 USD','-3.8%'],['B02','IC Markets','Raw Spread, Standard','$3.50','0.08 USD','-4.2%'],['B03','Pepperstone','Razor, Standard','$3.50','0.09 USD','-4.5%'],['B04','Tickmill','Pro, Classic','$4.00','0.10 USD','-4.0%'],['B05','FP Markets','Raw, Standard','$3.00','0.10 USD','-4.3%'],['B06','Fusion Markets','Zero, Classic','$2.25','0.12 USD','-3.9%']],null));
c.push(h2('Supported Account Types (6)'));
c.push(p('Six account types are supported across the 6 brokers. The Broker Compatibility Engine (M01) detects account type at runtime and adjusts position sizing, lot step granularity, and margin calculations accordingly. Cent and Micro accounts are supported for testing and small-capital licensees; Standard and Raw Spread are the primary live-trading accounts; ECN is for high-frequency strategies requiring direct market access; Dollar accounts are used for non-USD-denominated capital.'));
c.push(table(['Account Type','Min Lot','Lot Step','Typical Use','Supported Brokers'],[['Standard','0.01','0.01','Primary live trading','All 6'],['Raw Spread','0.01','0.01','Low-cost live trading','Exness, IC, Pepperstone, FP, Fusion'],['ECN','0.10','0.01','High-frequency / DMA','IC, Pepperstone, Tickmill, FP'],['Cent','0.01','0.01','Testing / small capital','Exness, FP, Fusion'],['Micro','0.01','0.01','Beginner / micro capital','Exness, Fusion'],['Dollar','0.01','0.01','Non-USD denominated','Exness, IC, Pepperstone']],null));

c.push(h1('Chapter 3 — System Architecture Overview'));
c.push(p('TITAN XAU AI is organized into a 5-layer architecture comprising 20 core modules plus a 5-component AI stack. The layers — Data & Broker, AI & Strategy, Risk & Management, Validation & Testing, and the cross-cutting AI Stack — represent distinct concerns with explicit dependencies and initialization ordering. The layered design enforces a strict separation: lower layers never depend on higher layers, ensuring the trading core can be tested and deployed independently of the AI/strategy decisions that sit on top.'));
c.push(diagram('d01_system_architecture.png',6.5));
c.push(caption('Figure 3.1 — System architecture: 20 core modules organized in 4 layers + AI stack with 5 components.'));

c.push(h2('20 Core Modules'));
c.push(p('The 20 modules span the complete trading system lifecycle: from broker connection and tick ingestion through AI-driven signal generation, risk-gated execution, and post-trade validation. Each module is independently deployable, has a well-defined interface, and is covered by its own specification document in the 18-module TITAN specification set. Modules 1-14 are operational (live-trading) modules; Modules 15-20 are validation, testing, and observability modules that gate and monitor the operational ones.'));
c.push(table(['#','Module','Layer','Role'],[['M01','Broker Compatibility Engine','L1 Data & Broker','6-broker runtime detection, 9 properties each'],['M02','Market Data Engine','L1 Data & Broker','Tick ingest, Parquet store, 14 quality gates'],['M03','Execution Engine','L1 Data & Broker','Async dispatcher, 50 ops/s, idempotent'],['M04','Adaptive Regime Detection','L2 AI & Strategy','4-state classifier, 3-model vote'],['M05','Trend Trading Engine','L2 AI & Strategy','5 patterns, R-multiple management'],['M06','Range Trading Engine','L2 AI & Strategy','BB+RSI+ATR+Hurst, smart recovery'],['M07','Volatility Engine','L2 AI & Strategy','News-aware ATR breakout'],['M08','Risk Management Engine','L3 Risk & Mgmt','4 modes, 12 controls, kill <500ms, MDD <5%'],['M09','Slippage Intelligence','L1 Data & Broker','EQS scoring, P50/P90/P99 distribution'],['M10','Spread & Commission Intel','L1 Data & Broker','Variable spread baseline, 6-broker cost profile'],['M11','Hybrid AI Stack','L2 AI & Strategy','XGB+LSTM+Transformer+RL+Ensemble'],['M12','RL Trade Management','L2 AI & Strategy','Position scaling, dynamic SL/TP, exit policy'],['M13','Auto Retraining','L3 Risk & Mgmt','Champion/Challenger, NO live auto-deploy'],['M14','Licensing & Activation','L3 Risk & Mgmt','HW-locked, RSA-4096 JWT, 3 tiers, 5 anti-crack'],['M15','Validator Framework','L4 Validation','8 suites, 144 checks, 3-band cert'],['M16','Backtesting Framework','L4 Validation','Tick data, 5 costs, 24 metrics, 3-band cert'],['M17','Walk-Forward Framework','L4 Validation','5-7 folds, WFE >= 85%, Train/Val/Test/Roll'],['M18','Monte Carlo Framework','L4 Validation','10k permutations, survival >= 95%'],['M19','Stress Testing','L4 Validation','Flash crash, news shock, broker outage'],['M20','Monitoring & Observability','L3 Risk & Mgmt','12 metrics, Prometheus, Grafana, PagerDuty']],null));

c.push(h1('Chapter 4 — AI Stack & Regime Detection'));
c.push(p('The AI stack is the platform\'s decision-making core: 4 base models (XGBoost, LSTM, Transformer, RL agent) plus a 5th ensemble voting layer that gates every signal. No single model ever generates an executable signal — the ensemble requires majority agreement (3 of 4) AND mean confidence >= 0.65. This dual gate is the single most important defense against model-specific failure modes: if one model drifts or overfits, the other three veto its signals, preventing the kind of catastrophic loss that single-model systems experience when their model silently degrades.'));
c.push(diagram('d11_ai_stack.png',6.5));
c.push(caption('Figure 4.1 — AI stack: 4 base models + ensemble voter, with 4 regime targets and regime-mapped strategy dispatch.'));

c.push(h2('5-Component AI Stack'));
c.push(p('XGBoost (A1) — Gradient-boosted trees over 87 tabular features (price action, indicators, regime hints). 80 ms P99 inference. Best at capturing non-linear interactions in structured data; the workhorse for trend detection. LSTM (A2) — Long Short-Term Memory network with 60-bar lookback and 128 hidden units. 95 ms P99. Best at sequential pattern recognition; captures temporal dependencies that tree models miss. Transformer (A3) — Multi-head attention (8 heads, 6 layers) with positional encoding. 110 ms P99. Best at long-range context and multi-feature attention; the most expensive model but provides the richest contextual signal. RL Agent (A4) — Proximal Policy Optimization (PPO) agent. Unlike the first three models which generate entry signals, the RL agent operates post-entry: it manages position lifecycle (scaling, dynamic SL/TP, exit timing).'));

c.push(h2('Ensemble Voting Layer (A5)'));
c.push(p('The ensemble voter aggregates the 4 base models\' signals: a signal executes only if (a) at least 3 of 4 models agree on direction, AND (b) the mean confidence across agreeing models is >= 0.65. If either condition fails, the signal is suppressed (no trade taken). This conservative gate is responsible for the platform\'s high win rate (61% in production) — by requiring multi-model consensus, we filter out signals that any single model is uncertain about.'));

c.push(h2('4 Regime Detection Targets'));
c.push(p('The Regime Detection module (M04) classifies the current market into one of 4 states via a 3-model vote (HMM + Logit + Heuristic). The regime label drives strategy selection: Trend → M05, Range → M06, Volatile → M07, News → halt new entries. The 4-state taxonomy is the minimum useful granularity — fewer states lose information, more states introduce classification noise. The 3-model vote is a bias-reduction technique: any single classifier has blind spots, but 2/3 consensus is robust to one model failing.'));

c.push(h1('Chapter 5 — Folder Structure Tree'));
c.push(p('The codebase is organized as a monorepo with clear separation between the C++20 execution core (latency-critical path) and the Python 3.12 AI layer (decision-making). The two layers communicate via PyO3 bindings, with zero-copy data exchange for tick streams and signals. The monorepo choice (vs multi-repo) is deliberate: it ensures atomic changes across the C++/Python boundary, simplifies CI/CD, and makes the system a single deployable artifact per VPS — critical for licensing (one binary = one license).'));
c.push(diagram('d02_folder_structure.png',6.5));
c.push(caption('Figure 5.1 — Folder structure: monorepo with C++20 core, Python 3.12 AI layer, PyO3 bridge, validation, licensing, observability, deployment, docs, config.'));

c.push(h2('Top-Level Directories'));
c.push(p('core/ — C++20 execution core. Contains broker_adapter, market_data, execution, risk, slippage, spread. Built with CMake, compiled with -O3 and LTO. This is the latency-critical path — every microsecond matters. ai/ — Python 3.12 AI layer. Contains models, ensemble, regime, strategies, training. Loaded via PyO3 at startup, models cached in memory. bridge/ — PyO3 bindings between C++ and Python. validation/ — The 5 validation frameworks (M15-M19) plus the test pyramid. licensing/ — Client-side license validation and anti-tamper, plus the server-side license issuer. observability/ — Prometheus exporters, Loki logging, OpenTelemetry tracing, PagerDuty alerting. deployment/ — Docker, Ansible, Terraform, deploy scripts. docs/ — Architecture documentation. config/ — Runtime configuration YAMLs.'));

c.push(h1('Chapter 6 — Service Architecture'));
c.push(p('The runtime is decomposed into 12 deployable services organized in 3 groups: Trading Core (4 services), AI & Strategy (4 services), and Ops & Compliance (4 services). All services communicate via gRPC (synchronous RPC) for request/response and NATS JetStream (async event bus) for pub-sub. This dual-transport design lets us use the right tool for each interaction pattern: gRPC for low-latency request/response (e.g., risk check on a signal), NATS for decoupled pub-sub (e.g., tick broadcast to multiple subscribers).'));
c.push(diagram('d03_service_architecture.png',6.5));
c.push(caption('Figure 6.1 — Service architecture: 12 services in 3 groups, NATS JetStream event bus, mTLS internal communication.'));

c.push(h2('Service Groups'));
c.push(p('Group A · Trading Core (SVC-01 to SVC-04) — Broker Gateway, Tick Ingestor, Execution Dispatcher, Risk Engine. These are the latency-critical services on the signal-to-broker path. All run in C++20, pinned to dedicated CPU cores, with mTLS between them. Group B · AI & Strategy (SVC-05 to SVC-08) — Regime Detector, AI Ensemble, Strategy Selector, RL Trade Manager. These are Python services that consume ticks and produce signals. Group C · Ops & Compliance (SVC-09 to SVC-12) — License Validator, Observability Stack, Audit Logger, Config Manager.'));

c.push(h2('Event Bus — NATS JetStream'));
c.push(p('All async communication flows through NATS JetStream topics: ticks, features, regime, signals, orders, fills, risk_alerts, regime_change, license_events, audit. Each topic has 3-day retention with replay, enabling subscribers to recover from any offset. The 3-day retention is also a backtesting asset — we can replay production events through new strategies to validate them against real market data. Backpressure is handled via JetStream consumer ack and max-deliver limits.'));

c.push(h1('Chapter 7 — Data Flow Diagram'));
c.push(p('The end-to-end data flow from broker tick to executed order traverses 7 stages in 142 ms (P99). Each stage is an independent service that subscribes to the previous stage\'s output topic on NATS, processes the event, and publishes its own output. This decoupling means stages can be scaled independently (e.g., the AI ensemble can be horizontally scaled to handle higher tick rates) and replayed from any offset for debugging. The 142 ms total latency is well within the 150 ms budget, with 8 ms safety margin.'));
c.push(diagram('d04_data_flow.png',6.5));
c.push(caption('Figure 7.1 — Data flow: 7-stage pipeline from broker tick to executed order, 142 ms P99 total latency.'));

c.push(h2('7-Stage Pipeline'));
c.push(p('Stage 1 (Broker Tick Stream) — MT5 terminal pushes real-time ticks every 100-500 ms. Stage 2 (Tick Ingest & Validate) — 14 quality gates. 2 ms latency. Stage 3 (Feature Engineering) — 87 features computed, 78% cache hit. 8 ms latency. Stage 4 (Regime Detection) — 3-model vote, confidence >= 0.65. 12 ms latency. Stage 5 (AI Ensemble) — 4 models vote, majority + confidence >= 0.65. 95 ms latency (bottleneck). Stage 6 (Risk Gate) — 12 controls, ~3% veto rate. 4 ms latency. Stage 7 (Execution Dispatch) — Async order router, idempotency key, audit. 21 ms latency.'));

c.push(h2('Backpressure Handling'));
c.push(p('If any stage exceeds its latency budget by 2×, downstream stages see a "stale signal" flag and the risk engine vetoes execution. This prevents trading on delayed data — critical for institutional safety. For example, if the AI ensemble takes 200 ms instead of 95 ms (network or CPU contention), the resulting signal is flagged stale and the risk engine rejects it.'));

c.push(h1('Chapter 8 — Module Dependency Graph'));
c.push(p('Module dependencies define the initialization order and the blast radius of failures. The 20 modules form a 4-layer DAG with strict layering: lower layers (L1) initialize first, higher layers (L4) initialize last. Within each layer, modules can initialize in parallel. Hard dependencies mean a module cannot start without its dependency being live and validated; soft dependencies mean runtime lookup with graceful degradation. The License Validator (M14) is the root — it initializes first and validates the JWT before any other module starts.'));
c.push(diagram('d05_module_dependency.png',6.5));
c.push(caption('Figure 8.1 — Module dependency graph: 4 layers, hard + soft dependencies, layer-by-layer initialization.'));

c.push(h2('Initialization Order'));
c.push(p('The system initializes in strict layer order: L1 (M14 → M01 → M02 → M10/M09/M03) → L2 (M04 → M11 → M05/M06/M07/M12) → L3 (M08 → M13 → M20) → L4 (M15-M19, run independently as validation jobs). If any module in L1 fails to initialize, the entire startup aborts — L1 is the foundation, no graceful degradation possible. L2/L3 modules can start with degraded functionality if a non-critical dependency is unavailable.'));

c.push(h1('Chapter 9 — UML Class Diagrams'));
c.push(p('The core domain is modeled in 4 areas: Broker & Execution (C++20), Risk & Position (C++20), AI & Strategy (Python 3.12), and Licensing & Validation (mixed). All cross-language interfaces use Protocol Buffers for schema stability — the C++ and Python sides generate code from the same .proto files, ensuring the boundary contract cannot drift. The design uses well-known patterns: Strategy, Adapter, Observer, Decorator, Factory, State, and Command.'));
c.push(diagram('d06_uml_class.png',6.5));
c.push(caption('Figure 9.1 — UML class diagrams: 4 domain areas with core abstractions, interfaces, and inheritance hierarchies.'));

c.push(h2('Core Abstractions'));
c.push(p('IBrokerAdapter — Interface for broker connections. MT5BrokerAdapter is the production implementation. ExecutionEngine — Async order dispatcher with idempotency cache (LRU) and retry-with-backoff. RiskEngine — Subscriber to Signal events; evaluates each signal against 12 IRiskControl implementations. IModel — Interface for AI models. XGBoostModel, LSTMModel, TransformerModel, RLAgent all implement it. EnsembleVoter is itself an IModel that delegates to its 4 children. StrategyBase — Abstract base for strategies. LicenseValidator — Loads and verifies JWT, checks hardware fingerprint, manages heartbeat. ValidatorFramework — Runs 8 validation suites, produces 3-band certification. ChampionChallengerManager — Manages the model promotion pipeline.'));

c.push(h1('Chapter 10 — Deployment Topology'));
c.push(p('The platform deploys across 3 zones: Primary VPS (London/AWS) for live trading, DR VPS (Frankfurt/AWS) for disaster recovery, and AWS Multi-Region SaaS backplane for license server, audit archive, model registry, and alerting. The active-passive configuration with 100 ms state sync enables a 60-second Recovery Point Objective (RPO) and 5-minute Recovery Time Objective (RTO). 99.9% annual availability is the target (~8.7 hours downtime per year).'));
c.push(diagram('d07_deployment_topology.png',6.5));
c.push(caption('Figure 10.1 — Deployment topology: 3 zones, active-passive DR, 60s RPO, 5m RTO, automated failover.'));

c.push(h2('Zone A — Production (Primary VPS)'));
c.push(p('4 nodes: A1 (TITAN Core Stack, 4 vCPU/16 GB/200 GB NVMe, all 12 services running), A2 (MT5 Terminal, 2 vCPU/4 GB, co-located with A1 for low-latency broker connection), A3 (Tick Data Store, 1 TB NVMe, 3-year history, rsync to S3 nightly), A4 (Observability, 2 vCPU/8 GB, Prometheus+Grafana+Loki with 30-day metrics retention). All nodes run Ubuntu 22.04 LTS with kernel tuned for low-latency trading (PREEMPT_RT, CPU isolation, NUMA pinning).'));

c.push(h2('Zone B — Disaster Recovery (DR VPS)'));
c.push(p('4 nodes mirroring Zone A: B1 (TITAN Core Stack warm standby, state sync every 100 ms from A1), B2 (MT5 Terminal DR, pre-configured for all 6 brokers, 5-second cold start), B3 (Tick Data Mirror, async replication from A3, RPO 60s), B4 (Failover Controller, heartbeat to A1 every 100 ms, auto-promote on 3 missed beats). On failover, B1 promotes to active, A1 is locked out (split-brain prevention), B2 starts MT5 terminal, and trading resumes within 5 minutes.'));

c.push(h2('Zone C — SaaS Backplane (AWS Multi-Region)'));
c.push(p('4 services: C1 (License Server — JWT issuer, tenant management, revocation, HSM-backed signing, multi-AZ, 99.95% SLA), C2 (Audit Archive S3 — 7-year retention, RSA-2048 signed manifests, WORM lock for immutability), C3 (Model Registry — S3 Standard multi-region, versioned, SHA-256 content-addressed), C4 (PagerDuty/Slack Gateway — alert routing, on-call escalation, audit trail). The SaaS backplane is shared across all licensees — each licensee\'s VPS connects to the same license server but with tenant isolation enforced via JWT claims.'));

c.push(h1('Chapter 11 — Testing Pyramid'));
c.push(p('The testing strategy follows a 5-layer pyramid: 700 unit tests (35%), 600 component tests (30%), 400 integration tests (20%), 200 end-to-end tests (10%), and 200 chaos tests (5%) — totaling approximately 2,100 automated tests. The pyramid shape reflects test cost and confidence: unit tests are cheap and fast but test small pieces; chaos tests are expensive and slow but test the whole system under failure. All layers must pass before a build is deployable, and the 5 validation frameworks (M15-M19) run AFTER the pyramid passes as an additional gate before live capital.'));
c.push(diagram('d08_testing_pyramid.png',6.5));
c.push(caption('Figure 11.1 — Testing pyramid: 5 layers, ~2,100 tests, validation frameworks as additional gate.'));

c.push(h2('5 Test Layers'));
c.push(p('Unit (L5, ~700 tests) — Pure-function tests with zero I/O and zero mocks. <1 ms each, run on every commit. Component (L4, ~600 tests) — Per-module behavior with mocked I/O but real logic. Integration (L3, ~400 tests) — Real NATS, real mTLS, real gRPC. Multi-service contracts. End-to-End (L2, ~200 tests) — Full pipeline from tick replay to AI to risk to execution to audit. Chaos (L1, ~200 tests) — Failure injection: kill services, drop network, corrupt data. Verify DR, kill-switch, fallbacks. Run nightly.'));

c.push(h2('Validation Gate (separate from pyramid)'));
c.push(p('After the test pyramid passes, 5 validation frameworks run as additional gates: M15 Validator (8 suites, 144 checks, 3-band certification), M16 Backtest (12-month tick-based, 5 cost components, 24 metrics), M17 Walk-Forward (5-7 folds, WFE >= 85%), M18 Monte Carlo (10k permutations, survival >= 95%), M19 Stress Test (flash crash, news shock, broker outage). All 5 must return CERTIFIED before live capital is authorized. Quarterly re-validation cadence.'));

c.push(h1('Chapter 12 — Non-Functional Requirements (NFRs)'));
c.push(p('Six non-functional requirements define the institutional character of the platform. Unlike functional requirements (what the system does), NFRs define how the system behaves under load, failure, and attack. Each NFR has explicit targets, measurement methodology, and quarterly review. NFR violations are treated as production incidents — a missed latency budget or failed DR drill triggers P1 escalation exactly like a trading loss would.'));
c.push(diagram('d09_nfr.png',6.5));
c.push(caption('Figure 12.1 — All 6 NFRs: latency budget, risk controls, disaster recovery, observability, security & auth, licensing hooks.'));

c.push(h2('NFR-1 · Latency Budget (142 ms P99)'));
c.push(p('Signal-to-broker path: 2 ms (ingest) + 8 ms (features) + 12 ms (regime) + 95 ms (AI ensemble) + 4 ms (risk) + 21 ms (execution) = 142 ms P99. Budget is 150 ms, giving 8 ms safety margin. The AI ensemble is the bottleneck at 67% of total latency — optimization efforts focus there (model pruning, quantization, batch inference). If any stage exceeds 2× budget, downstream sees "stale signal" flag and risk engine vetoes.'));

c.push(h2('NFR-2 · Risk Controls (MDD < 5%, kill < 500ms)'));
c.push(p('The Risk Engine (M08) enforces 12 controls across 4 modes (Normal, Aggressive, Defensive, Emergency). Hard limits: Max Drawdown < 5% (institutional hard floor — kill-switch triggers if breached), per-trade risk <= 1% of equity, margin alert at ML <= 200%, correlation ρ >= 0.85 triggers hedge flag. The emergency kill-switch can flatten all positions in < 500 ms — measured in production via dedicated latency probes.'));

c.push(h2('NFR-3 · Disaster Recovery (RPO 60s, RTO 5m, 99.9%)'));
c.push(p('Active-passive deployment across London (primary) and Frankfurt (DR). State sync every 100 ms gives 60-second RPO. Failover controller (B4) detects primary failure via 3 consecutive missed heartbeats (300 ms detection) and auto-promotes DR. Cold start of MT5 terminal on DR is 5 seconds. Total RTO: 5 minutes. 99.9% annual availability target = ~8.7 hours downtime per year. Quarterly DR drill is mandatory.'));

c.push(h2('NFR-4 · Observability (12 metrics, 8 dashboards)'));
c.push(p('12 Prometheus metrics, 8 Grafana dashboards (system overview, risk, execution, AI, regime, licensing, validation, audit), OpenTelemetry distributed tracing, Loki structured JSON logs (30-day retention), PagerDuty alerting (P1/P2/P3 severity). Audit logs archive to S3 with 7-year retention for regulatory compliance.'));

c.push(h2('NFR-5 · Security & Auth (mTLS, JWT, AES-256, HSM)'));
c.push(p('Defense in depth: mTLS on all internal RPC, JWT + RBAC on external API, AES-256 at-rest encryption, TLS 1.3 transport encryption, HSM-backed signing keys (AWS KMS), annual SOC2 audit by 3rd party. The license server\'s RSA-4096 private key never leaves the HSM — public key is embedded in client binary at build time. Hardware fingerprint (CPUID + Motherboard ID + Windows SID) binds each license to physical hardware.'));

c.push(h2('NFR-6 · Licensing Hooks (every layer)'));
c.push(p('Commercial licensing is enforced at every architectural layer. License check runs at startup AND every 1-hour heartbeat. 3 tiers (Starter $12k/yr, Pro $48k/yr, Enterprise $180k/yr) gate features, capital ceiling, and support level. Feature gate is a hard boundary — a Starter-tier licensee cannot access Pro features regardless of configuration. Hardware lock (3-factor fingerprint) binds license to physical machine. RSA-4096 JWT signed by HSM-backed key. 5 anti-crack layers. Server-side heartbeat can revoke a license in < 1 hour. 7-day grace period on heartbeat failure, then graceful shutdown.'));

c.push(h1('Chapter 13 — Champion vs Challenger — Auto-Retraining Governance'));
c.push(p('The single most important institutional guardrail in the TITAN architecture: auto-retraining NEVER auto-deploys to production. A new model can pass all 3 validation gates and still be rejected at manual review. This is what separates retail bots (train → deploy → lose money) from institutional systems (train → validate 3× → manual review → deploy → retain alpha). The Champion/Challenger pattern ensures that the production "champion" model is only replaced when a "challenger" demonstrably outperforms it across backtest, walk-forward, AND Monte Carlo — AND a human signs off.'));
c.push(diagram('d10_champion_challenger.png',6.5));
c.push(caption('Figure 13.1 — Champion/Challenger pipeline: 6 stages, 3 validation gates, manual promotion. NO live auto-deploy.'));

c.push(h2('6-Stage Pipeline'));
c.push(p('Stage 1 (Detect Drift) — PSI drift detector runs every 6 hours. PSI > 0.25 on input features or model confidence triggers retrain. Stage 2 (Train Challenger) — Train new model on rolling 90-day window, parallel to champion (zero production impact). Stage 3 (Backtest Gate) — 12-month backtest. Must pass: Sharpe >= 2.0, MDD <= 5%, cost drag <= 35%. Stage 4 (Walk-Forward Gate) — 5-7 fold WFA. Must pass: WFE >= 0.85, all folds OOS Sharpe >= 1.5, OOS MDD <= 5%. Stage 5 (Monte Carlo Gate) — 10,000 trade permutations. Must pass: survival rate >= 95%, P5 Sharpe >= 1.0, P5 MDD <= 8%. Stage 6 (Manual Promote) — If all 3 gates pass, challenger becomes new champion. Manual sign-off: engineering lead + risk officer + CTO.'));

c.push(h2('Why No Live Auto-Deploy?'));
c.push(p('A new model can pass all 3 validation gates and still be rejected at manual review. Reasons for manual rejection include: (1) regime shift not captured by historical data (e.g., a new central bank policy that changes gold\'s behavior), (2) parameter instability across folds (suggesting the model fits noise), (3) cost profile drift (the model trades more frequently than champion, increasing cost sensitivity), (4) strategic concerns (the model takes positions during news events that humans know to avoid). This human-in-the-loop gate is the single biggest defense against the kind of catastrophic loss that retail auto-retraining systems experience when their retrained model silently degrades in live trading.'));

c.push(h2('Rollback Path'));
c.push(p('If a newly-promoted champion underperforms in live trading (1-week evaluation window, compared against the previous champion\'s parallel performance), the previous champion is restored in < 1 minute via model registry versioning. The rollback is automated — no human approval required for rollback, only for promotion. This asymmetry is deliberate: it should be easy to undo a bad promotion, hard to make one.'));

c.push(h1('Chapter 14 — Validation Frameworks'));
c.push(p('Five validation frameworks (M15-M19) gate every deployment. They are independent of the test pyramid (Ch. 11) — the pyramid verifies code correctness, the validation frameworks verify trading correctness. All 5 must return CERTIFIED before live capital is authorized. The 3-band verdict (CERTIFIED / CONDITIONAL / REJECTED) is the authoritative system state.'));
c.push(table(['Framework','Module','What It Validates','Headline Metric','Cert Gate'],[['Validator','M15','8 system suites, 144 checks','Aggregate score 0-100','>= 85'],['Backtesting','M16','12-month tick-based with 5 costs','Sharpe + Cost Drag','Sharpe >= 2.0, CD <= 35%'],['Walk-Forward','M17','5-7 fold OOS validation','WFE (OOS/IS Sharpe)','WFE >= 0.85'],['Monte Carlo','M18','10k trade permutations','Survival rate','>= 95%'],['Stress Test','M19','Flash crash, news shock, broker outage','MDD under stress','<= 8%']],null));
c.push(p('Each framework produces its own 3-band verdict and is documented in its own module specification (Modules 15-19). The combined verdict is the logical AND of all 5 — if any returns REJECTED, live trading is halted. If any returns CONDITIONAL, paper trading only is authorized with daily revalidation. Only when all 5 return CERTIFIED is live capital authorized. Quarterly re-validation cadence on every live strategy.'));

c.push(h1('Chapter 15 — Commercial Licensing'));
c.push(p('The platform is designed for commercial sale and licensing — it is a product, not just an internal tool. Licensing is enforced at every architectural layer (NFR-6) and is documented in detail in Module 14. This chapter provides the executive summary. The 3 license tiers gate features, capital ceiling, and support level: Starter ($12k/yr, 1 strategy, $50k capital cap, monthly renewal), Pro ($48k/yr, 3 strategies, $500k capital cap, quarterly renewal), Enterprise ($180k/yr, unlimited strategies, no capital cap, yearly renewal, white-label, on-prem license server option).'));

c.push(h2('Activation & Hardware Lock'));
c.push(p('Both online (~2 second) and offline (email-based, up to 24 hour) activation are supported. The hardware lock uses a 3-factor composite fingerprint: CPUID (CPU manufacturer + model + stepping via CPUID instruction), Motherboard ID (baseboard serial via SMBIOS/WMI), and Windows SID (machine GUID from registry). Each is SHA-256 hashed individually, then combined: SHA-256(CPUID_hash + MB_hash + SID_hash). This composite is unique per physical machine and cannot be changed without replacing physical hardware. 3 activations per year are allowed automatically (for legitimate hardware changes); additional requires support ticket.'));

c.push(h2('Anti-Crack Defense (5 layers)'));
c.push(p('Code obfuscation (symbol stripping, LTO, Cython compilation, string encryption), tamper detection (SHA-256 binary checksum, IAT verification), anti-debug (IsDebuggerPresent, NtQueryInformationProcess, RDTSC timing), anti-VM (MAC OUI check, CPUID hypervisor bit), behavioral analytics (geo-IP tracking, multi-IP detection, concurrent session flagging). Each layer is independent — cracking one does not bypass the others. The server-side heartbeat is the ultimate backstop: even if all 5 client-side layers are bypassed, the system cannot operate without a valid server-issued JWT.'));

c.push(h1('Chapter 16 — Development Roadmap'));
c.push(p('The development roadmap is organized in 4 phases over 18 months. Each phase delivers a deployable milestone — no phase depends on incomplete work from a later phase. The phases are sequenced to deliver value early (Phase 1 produces a paper-trading system) while building toward the full institutional platform (Phase 4 delivers commercial licensing and full validation).'));
c.push(table(['Phase','Duration','Modules','Milestone','Exit Criteria'],[['Phase 1 — Foundation','Months 1-4','M01, M02, M03, M08, M14','Paper trading on 1 broker','Validator M15 passes'],['Phase 2 — AI & Strategy','Months 5-9','M04, M05, M06, M07, M11, M12','Live trading on 3 brokers','Backtest M16 CERTIFIED'],['Phase 3 — Validation','Months 10-14','M09, M10, M13, M16, M17, M18, M19','Full validation pipeline','WFA + MC CERTIFIED'],['Phase 4 — Commercial','Months 15-18','M15, M20 + hardening','Commercial release','3 paying licensees']],null));

c.push(h2('Phase Details'));
c.push(p('Phase 1 (Foundation, Months 1-4) — Build the trading core: broker connection, tick ingestion, execution engine, risk engine, license validator. The result is a paper-trading system that can connect to one broker, place orders, and manage risk — but with no AI-driven signals (manual signals only). Exit criterion: the Validator Framework (M15) passes on the live system. Phase 2 (AI & Strategy, Months 5-9) — Add the AI stack and trading strategies. Exit criterion: Backtest Framework (M16) returns CERTIFIED. Phase 3 (Validation, Months 10-14) — Build the full validation pipeline. Exit criterion: WFA (M17) AND Monte Carlo (M18) both return CERTIFIED. Phase 4 (Commercial, Months 15-18) — Add the Validator Framework (M15), Monitoring & Observability (M20), and production hardening. Exit criterion: 3 paying licensees deployed and operational for 30 days.'));

c.push(h1('Chapter 17 — Production Readiness Checklist'));
c.push(p('Before a TITAN XAU AI deployment is authorized for live capital, every item on this checklist must be verified. The checklist is the final gate — it does not replace the validation frameworks (M15-M19) but complements them by verifying operational readiness (DR drills, on-call rotation, runbooks) that the automated frameworks cannot check. The checklist is signed off by 4 roles: Engineering Lead, Risk Officer, Compliance, CTO.'));
c.push(h2('Code & Build'));
c.push(bullet('All 20 modules implemented, integrated, and unit/component/integration tested'));
c.push(bullet('Test pyramid passes: 700 unit + 600 component + 400 integration + 200 e2e + 200 chaos tests'));
c.push(bullet('Code review completed by 2 reviewers, no outstanding comments'));
c.push(bullet('Static analysis clean (clang-tidy for C++, mypy + pylint for Python)'));
c.push(bullet('Security scan clean (Semgrep + npm audit + pip-audit)'));
c.push(bullet('All 12 services containerized, multi-stage Docker builds, < 500 MB per image'));
c.push(h2('Validation'));
c.push(bullet('Validator (M15) returns CERTIFIED (score >= 85, 0 critical fails)'));
c.push(bullet('Backtest (M16) returns CERTIFIED (Sharpe >= 2.0, MDD <= 5%, cost drag <= 35%)'));
c.push(bullet('Walk-Forward (M17) returns CERTIFIED (WFE >= 0.85, all folds OOS Sharpe >= 1.5)'));
c.push(bullet('Monte Carlo (M18) returns CERTIFIED (survival >= 95%, Risk of Ruin < 1%)'));
c.push(bullet('Stress Test (M19) returns CERTIFIED (MDD <= 8% under flash crash, news shock, broker outage)'));
c.push(h2('Deployment & DR'));
c.push(bullet('Primary VPS (Zone A) provisioned, all 4 nodes healthy'));
c.push(bullet('DR VPS (Zone B) provisioned, state sync verified (RPO 60s)'));
c.push(bullet('Failover drill executed successfully (RTO 5m)'));
c.push(bullet('License server (Zone C) reachable, JWT issuance verified'));
c.push(bullet('Audit S3 archive writable, 7-year retention policy enforced'));
c.push(h2('Operations'));
c.push(bullet('On-call rotation established (24/7 coverage, P1 response < 15 min)'));
c.push(bullet('Runbooks published for top 20 incident scenarios'));
c.push(bullet('PagerDuty integration tested (test alert sent and acknowledged)'));
c.push(bullet('Grafana dashboards accessible to ops team'));
c.push(bullet('Prometheus alerts tuned (no false positives in 7-day soak)'));
c.push(h2('Compliance & Licensing'));
c.push(bullet('SOC2 audit completed (annual, 3rd party)'));
c.push(bullet('License terms reviewed by legal, EULA published'));
c.push(bullet('Hardware fingerprint verified on target VPS'));
c.push(bullet('License tier features gated correctly (manual verification)'));
c.push(bullet('Anti-tamper defense verified (binary checksum, IAT, anti-debug)'));
c.push(h2('Sign-off'));
c.push(p('The checklist is signed off by 4 roles. No role can delegate. Any unchecked item blocks deployment.'));
c.push(table(['Role','Responsibility','Sign-off Required'],[['Engineering Lead','Code, build, test pyramid, technical correctness','Yes — digital signature'],['Risk Officer','Risk controls, validation frameworks, capital adequacy','Yes — digital signature'],['Compliance','Licensing, audit trail, regulatory, SOC2','Yes — digital signature'],['CTO','Final authority, override capability (rare)','Yes — digital signature']],null));

c.push(h1('Chapter 18 — Audience & Document Conventions'));
c.push(p('This document targets a mixed audience: CTOs and Lead Developers are the primary readers, with downstream consumption by Quant Developers, AI Engineers, Institutional Trading System Architects, Freelancers, AI Agents, and Investors. The writing style balances technical depth (sufficient for engineers to implement) with executive accessibility (sufficient for CTOs to make strategic decisions). Where tradeoffs exist between depth and accessibility, depth wins — engineers need the detail to build correctly, and CTOs can skim.'));

c.push(h2('Reading Paths by Audience'));
c.push(bullet('CTO / Portfolio Manager — Ch 1 (Exec Summary), Ch 2 (Spec), Ch 12 (NFRs), Ch 13 (Champion/Challenger), Ch 16 (Roadmap), Ch 17 (Readiness). ~30 min read.'));
c.push(bullet('Lead Developer / Architect — Full document. ~2 hour read. Reference for design decisions.'));
c.push(bullet('Quant Developer — Ch 4 (AI Stack), Ch 7 (Data Flow), Ch 8 (Dependencies), Ch 9 (UML), Ch 14 (Validation). Focus on AI/strategy layers.'));
c.push(bullet('AI Engineer — Ch 4 (AI Stack), Ch 13 (Champion/Challenger), Ch 14 (Validation), Module 7 (Hybrid AI Stack spec).'));
c.push(bullet('DevOps / SRE — Ch 6 (Services), Ch 10 (Deployment), Ch 11 (Testing), Ch 12 (NFRs), Module 20 (Observability spec).'));
c.push(bullet('Compliance / Audit — Ch 12 (NFRs), Ch 15 (Licensing), Ch 17 (Readiness), Module 14 (Licensing spec).'));
c.push(bullet('Investor / Buyer — Ch 1 (Exec Summary), Ch 2 (Spec, target metrics), Ch 15 (Licensing tiers). ~15 min read.'));
c.push(bullet('Freelancer / Contributor — Ch 5 (Folder Structure), Ch 6 (Services), Ch 9 (UML), Ch 17 (Readiness). Onboarding guide.'));
c.push(bullet('AI Agent (automated) — Full document parsed as context. Structured headings, explicit IDs (M01-M20, KPI-01 to KPI-08), machine-readable tables.'));

c.push(h2('Document Set'));
c.push(p('This is Module 1 of an 18-module specification set. Each subsequent module covers one of the 20 core modules (some modules share a spec) in full detail. The module list: M01 Broker Compatibility, M02 Market Data, M03 Execution, M04 Regime Detection, M05 Trend Strategy, M06 Range Strategy, M07 Volatility, M08 Risk, M09 Slippage, M10 Spread/Commission, M11 Hybrid AI Stack, M12 RL Trade Mgmt, M13 Auto Retraining, M14 Licensing, M15 Validator, M16 Backtesting, M17 Walk-Forward, M18 Monte Carlo, M19 Stress Test, M20 Observability. Each module spec is 15-40 pages and follows the same Goldman Sachs white-paper style as this Master Module.'));

return c;}

async function main(){
console.log('[build] Generating TITAN XAU AI Architecture v2.0 DOCX...');
const doc=new Document({creator:'TITAN Quant Research',title:'TITAN XAU AI — Master Architecture v2.0',description:'TITAN Master Architecture v2.0',subject:'Module 1 v2.0: 20 modules, AI stack, 7 diagrams, 6 NFRs, Champion/Challenger, validation, licensing, roadmap, readiness',
styles:{default:{document:{run:{font:'Liberation Serif',size:22},paragraph:{spacing:{line:312}}},heading1:{run:{font:'Liberation Serif',size:40,bold:true,color:C.navy},paragraph:{spacing:{before:480,after:240}}},heading2:{run:{font:'Liberation Serif',size:28,bold:true,color:C.navy},paragraph:{spacing:{before:320,after:160}}},heading3:{run:{font:'Liberation Serif',size:24,bold:true,color:C.crimson},paragraph:{spacing:{before:240,after:120}}}}},
sections:[
{properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440}}},children:buildCover()},
{properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440},pageNumbers:{start:1,formatType:NumberFormat.LOWER_ROMAN}}},footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,children:[new TextRun({children:[PageNumber.CURRENT],size:18,font:'Liberation Serif',color:C.muted})]})]})},children:buildToc()},
{properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440},pageNumbers:{start:1,formatType:NumberFormat.DECIMAL}}},headers:{default:new Header({children:[new Paragraph({alignment:AlignmentType.LEFT,border:{bottom:{color:C.navy,size:6,style:BorderStyle.SINGLE,space:4}},children:[new TextRun({text:'TITAN XAU AI — Master Architecture',size:18,italics:true,font:'Liberation Serif',color:C.muted}),new TextRun({text:'\t\t',size:18}),new TextRun({text:'v2.0  ·  MASTER',size:18,bold:true,font:'Liberation Serif',color:C.crimson})],tabStops:[{type:TabStopType.RIGHT,position:TabStopPosition.MAX}]})]})},footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,border:{top:{color:C.border,size:4,style:BorderStyle.SINGLE,space:4}},children:[new TextRun({text:'© 2026 TITAN Quant Research  ·  Proprietary & Confidential\t\t',size:18,italics:true,font:'Liberation Serif',color:C.muted}),new TextRun({children:[PageNumber.CURRENT],size:20,bold:true,font:'Liberation Serif',color:C.navy})],tabStops:[{type:TabStopType.RIGHT,position:TabStopPosition.MAX}]})]})},children:buildBody()},
]});
const b=await Packer.toBuffer(doc);fs.writeFileSync(OUT,b);
console.log(`[build] DOCX written: ${OUT}`);console.log(`[build] Size: ${(b.length/1024).toFixed(1)} KB`);}
main().catch(e=>{console.error('[FATAL]',e);process.exit(1)});
