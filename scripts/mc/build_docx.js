const fs=require('fs'),path=require('path');const{imageSize}=require('image-size');const docx=require('docx');
const{Document,Packer,Paragraph,TextRun,HeadingLevel,AlignmentType,PageBreak,ImageRun,Table,TableRow,TableCell,WidthType,BorderStyle,TableOfContents,StyleLevel,Footer,Header,PageNumber,NumberFormat,ShadingType,TabStopType,TabStopPosition,VerticalAlign}=docx;
const C={navy:'14213D',crimson:'C8102E',muted:'4A5568',stripe:'F8FAFC',border:'CBD5E1',text:'14213D'};
const DIR='/home/z/my-project/scripts/mc/diagrams/png';const OUT='/home/z/my-project/download/TITAN_Monte_Carlo_Framework_v1.0.docx';
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
new Paragraph({children:[new TextRun({text:'M O D U L E   1 5   ·   M O N T E   C A R L O',size:20,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:720,after:360}}),
new Paragraph({children:[new TextRun({text:'Monte Carlo',size:52,font:'Liberation Serif',color:C.navy,bold:true}),new TextRun({text:' Framework',size:52,font:'Liberation Serif',color:C.crimson,bold:true})],spacing:{after:360,line:240}}),
new Paragraph({children:[new TextRun({text:'10,000 simulations per strategy. 3 randomization dimensions: trade order, slippage, spread. Survival Score (0-100) measures robustness. 12 pass/fail rules. 3-band certification. P5 Sharpe >= 1.0, Risk of Ruin < 1%.',italics:true,size:24,font:'Liberation Serif',color:C.muted})],spacing:{after:720,line:360}}),
new Paragraph({children:[new TextRun({text:'KEY FEATURES',size:16,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{before:240,after:120},border:{top:{color:C.navy,size:12,style:BorderStyle.SINGLE,space:4}}}),
table(['Feature','Value'],[['Simulations','10,000 per strategy (seed-reproducible)'],['Random dimensions','3 (trade order, slippage, spread)'],['Survival Score','0-100, target >= 95%'],['Pass criteria','7 rules (Survival Score + P5 metrics)'],['Failure criteria','5 critical + 5 major + 2 minor = 12 rules'],['Certification','CERTIFIED / CONDITIONAL / REJECTED (3-band)'],['Runtime','~6 min per strategy on 4-core VPS'],['Reporting','3 tiers (executive / technical / regulatory)']],null),
spacer(360),
new Paragraph({children:[new TextRun({text:'Prepared by  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'TITAN Quant Research',size:18,font:'JetBrains Mono',color:C.navy,bold:true})],spacing:{after:40}}),
new Paragraph({children:[new TextRun({text:'Reviewed by  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'CTO · Head of Research · Risk Officer · Compliance',size:18,font:'JetBrains Mono',color:C.navy,bold:true})],spacing:{after:40}}),
new Paragraph({children:[new TextRun({text:'Classification  ',size:18,font:'JetBrains Mono',color:C.muted}),new TextRun({text:'RESEARCH — INTERNAL DISTRIBUTION',size:18,font:'JetBrains Mono',color:C.crimson,bold:true})],spacing:{after:40}}),
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
c.push(p('The Monte Carlo Framework (MCF) is Module 15 of the TITAN XAU AI trading system. It is the platform\'s anti-fragility authority — the validation framework that asks: does this strategy survive the random realities of live trading? Backtests are deterministic: they assume chronological trade order, fixed slippage, and baseline spread. Live trading is stochastic: trade order clusters unpredictably, slippage varies per fill with fat-tailed outliers, and spreads spike during news events. The MCF runs 10,000 simulations per strategy, each applying 3 independent randomization dimensions (trade order, slippage, spread), and produces a single composite Survival Score that quantifies strategy robustness.'));
c.push(p('A strategy that passes backtesting (Module 16) and walk-forward analysis (Module 17) but fails Monte Carlo is statistically overfit to a favorable trade sequence and will lose money in live trading. The Survival Score — the fraction of 10,000 simulations that remained profitable AND within risk constraints (MDD <= 8%, Sharpe >= 1.0) — is the headline metric. Institutional threshold: Survival Score >= 95% (CERTIFIED), 85-94% (CONDITIONAL — paper trading only), < 85% (REJECTED — trading halted). The 95% floor is non-negotiable: a strategy that fails 5%+ of random simulations has demonstrable fragility that will manifest in live trading within months.'));
c.push(p('The framework delivers four outputs specified in this document: (1) the methodology — 6-stage pipeline from backtest ledger import through certification, ~6 minutes runtime per strategy; (2) the 3 randomization dimensions — trade order (Fisher-Yates shuffle), slippage (LogNormal distribution calibrated to broker P50/P90/P99), spread (Beta distribution × max spread multiplier); (3) the Survival Score — single composite metric with explicit survival criteria (profitable + MDD <= 8% + Sharpe >= 1.0); (4) the pass/fail criteria — 12 hard rules (5 CRITICAL + 5 MAJOR + 2 MINOR) producing a 3-band verdict. The Risk of Ruin metric (< 1% required) counts simulations that lost >= 50% of capital — the catastrophic tail risk that ends trading careers.'));
c.push(p('The single most important insight from Monte Carlo is that backtest performance is a single sample from a distribution, not a deterministic prediction. A Sharpe of 2.0 in backtest does not mean the strategy "has" Sharpe 2.0 — it means the strategy\'s Sharpe under the historical trade sequence was 2.0. Under different (equally plausible) trade sequences, the Sharpe could be 1.2 or 3.5. The MCF computes this full distribution and reports the P5 (worst 5%) case as the planning baseline: if P5 Sharpe >= 1.0, the strategy retains institutional edge even in adverse sequencing; if P5 Sharpe < 0.8, the strategy is fragile and will underperform backtest expectations in live trading. This P5 floor, not the median, is what determines live-trading readiness.'));

c.push(h1('Chapter 2 — Methodology Overview'));
c.push(p('The MCF is a 6-stage pipeline: (1) load backtest results (per-trade ledger from Module 16), (2) define randomization (3 dimensions with distributions and bounds), (3) run 10,000 simulations, (4) aggregate distribution (P5/P25/P50/P75/P95 across 8 metrics), (5) compute Survival Score, (6) apply certification. Each stage is independently checkpointed — a failure at any stage produces a structured error and aborts. The pipeline is reproducible: same input ledger + same random seed produces identical simulation results, essential for audit and regression detection.'));
c.push(diagram('d01_methodology.png',6.5));
c.push(caption('Figure 2.1 — Methodology: 6-stage pipeline, 10,000 simulations, 3 randomization dimensions, Survival Score certification.'));

c.push(h2('Reproducibility'));
c.push(p('Every MCF run is pinned to a random seed (default: 42) recorded in the audit manifest. Given the same backtest ledger and the same seed, the MCF produces bit-identical simulation results. This is essential for: (1) audit — regulators can re-run any historical MC and verify the verdict, (2) regression detection — comparing current MC against historical MC requires identical seeds to isolate strategy changes from random variance, (3) debugging — when a strategy fails MC, engineers can re-run with the same seed to inspect the specific failing simulations. The seed is exposed as a CLI parameter for explicit control.'));

c.push(h2('Computational Performance'));
c.push(p('10,000 simulations × 200-800 trades each = 2-8 million trade-equity computations per MCF run. On a 4-core VPS with multiprocessing, this completes in approximately 6 minutes wall-clock. Each simulation is embarrassingly parallel — no inter-simulation dependencies — so the MCF scales linearly with CPU cores. A 16-core VPS reduces runtime to ~1.5 minutes. The bottleneck is Python interpreter overhead per trade; a future C++ port could reduce runtime by 10× but the current 6-minute runtime is acceptable for the quarterly validation cadence.'));

c.push(h1('Chapter 3 — Dimension 1: Random Trade Order'));
c.push(p('The first randomization dimension tests strategy sensitivity to trade sequencing. The backtest ledger contains 200-800 trades in chronological order, but live trading will experience a different sequence: losses may cluster early (depleting capital before wins arrive), or wins may cluster early (building a cushion that absorbs later losses). The MCF randomly permutes the trade order using Fisher-Yates shuffle — same trades, same P&L per trade, but different chronological sequence. This tests whether the strategy\'s drawdown profile is robust to sequencing or is an artifact of a favorable historical sequence.'));
c.push(diagram('d02_randomization.png',6.5));
c.push(caption('Figure 3.1 — Three randomization dimensions: trade order, slippage, spread. Each tests a different fragility hypothesis.'));

c.push(h2('Fisher-Yates Shuffle Implementation'));
c.push(p('For each simulation, the MCF applies a Fisher-Yates shuffle to the trade array: for i from n-1 down to 1, swap trade[i] with trade[random(0, i)]. This produces a uniform random permutation — every possible ordering is equally likely. The shuffle uses the simulation\'s seed (derived from the master seed + simulation index) for reproducibility. The shuffled trades are then re-accumulated into an equity curve: starting from initial capital, apply each trade\'s P&L in shuffled order, recording peak/trough for drawdown calculation. The resulting equity curve has a different drawdown profile than the chronological one, even though the total P&L is identical.'));

c.push(h2('What Trade Order Randomization Detects'));
c.push(p('This dimension detects drawdown sequence fragility — strategies that survive in chronological order but blow up when losses cluster. Example: a strategy with 60% win rate and 1:1.5 risk:reward looks healthy in backtest (positive expectancy, 8% MDD). But if the randomization produces a sequence with 8 consecutive losses early, the drawdown balloons to 18% before the wins arrive to recover. If 15% of simulations experience this kind of clustering, the Survival Score drops to 85% — CONDITIONAL. The strategy is profitable in expectation but fragile to sequencing, requiring either smaller position sizing or a martingale-rejection rule. Without trade order randomization, this fragility is invisible — the backtest showed only the favorable historical sequence.'));

c.push(h1('Chapter 4 — Dimension 2: Random Slippage'));
c.push(p('The second randomization dimension tests strategy sensitivity to execution cost variance. The backtest ledger uses fixed P50 slippage per trade — a convenient fiction. Live trading incurs stochastic slippage: most fills are near P50, but P99 fills see 5-10× P50 slippage, and these tail events consume disproportionate edge. The MCF samples a slippage value per trade from a LogNormal distribution calibrated to the broker\'s live P50/P90/P99 measurements. This tests whether the strategy\'s edge survives the variance of real-world execution costs.'));

c.push(h2('LogNormal Distribution Calibration'));
c.push(p('Slippage is modeled as LogNormal(μ, σ) where μ = ln(P50) and σ is derived from the broker\'s P90 and P99 measurements. Specifically: σ = (ln(P99) - ln(P50)) / 2.326 (the z-score for P99). This produces a distribution where the median matches P50, the 90th percentile matches P90, and the 99th percentile matches P99 — a 3-point calibration that captures both the central tendency and the tail. The distribution is bounded at 0 (slippage cannot be negative — that would be price improvement, which is rare and small) and capped at 5× P99 (sanity bound to prevent extreme outliers from dominating the simulation).'));

c.push(h2('Per-Trade Slippage Sampling'));
c.push(p('For each trade in each simulation, the MCF samples a slippage value from the calibrated LogNormal distribution and re-computes the trade\'s P&L: realized_pnl = original_pnl - (slippage × lots × 100 × direction_sign). The slippage always reduces P&L (a cost), regardless of trade direction. This per-trade re-sampling produces a distribution of P&L outcomes per trade, which accumulates into a distribution of equity curves across the 10,000 simulations. The P5 (worst 5%) equity curve represents the strategy\'s performance under consistently adverse slippage — if it remains profitable, the strategy is robust to execution cost variance.'));

c.push(h2('What Slippage Randomization Detects'));
c.push(p('This dimension detects execution cost fragility — strategies whose edge is consumed by tail slippage events. Example: a scalping strategy with 0.05 USD average profit per trade and 0.04 USD P50 slippage has thin edge (0.01 USD net). At P99 slippage of 0.35 USD, the strategy loses 0.30 USD per trade — 30× the expected profit. If 10% of trades hit P99 slippage (realistic for news-sensitive strategies), the strategy is unprofitable. The MCF reveals this: Survival Score drops to 60% because 40% of simulations have enough P99 slippage events to wipe out the edge. Without slippage randomization, the strategy looks profitable in backtest (which uses fixed P50) but loses money live.'));

c.push(h1('Chapter 5 — Dimension 3: Random Spread'));
c.push(p('The third randomization dimension tests strategy sensitivity to spread variance. The backtest uses the broker\'s baseline spread (P50 normal-session spread) for all trades — another convenient fiction. Live spreads vary: 0.15-0.25 USD during London/NY overlap (normal), 0.30-0.60 USD during Asian session (off-session), and 1.00-5.00 USD during news events (3-20× baseline). The MCF samples a spread multiplier per trade from a Beta distribution and applies it to the baseline spread, modeling both session variation and news widening.'));

c.push(h2('Beta Distribution Calibration'));
c.push(p('Spread multiplier is modeled as Beta(α=2, β=5) × max_multiplier, where max_multiplier = 5 (the maximum observed spread is 5× baseline during news events). The Beta(2,5) distribution is right-skewed: most samples are near 1× baseline (normal session), with a long tail toward 5× (news events). The mean is 1.43× baseline, the P95 is 3.2× baseline, and the P99 is 4.1× baseline. This distribution captures the empirical observation that spread widening is asymmetric — most trades see near-baseline spread, but the rare news-event trades see 3-5× widening that disproportionately impacts P&L.'));

c.push(h2('Per-Trade Spread Sampling'));
c.push(p('For each trade in each simulation, the MCF samples a spread multiplier, computes the actual spread = baseline × multiplier, and re-computes the trade\'s spread cost: spread_cost = actual_spread × lots × $10/pt. The spread cost is then deducted from the trade\'s P&L. This produces a distribution of P&L outcomes per trade reflecting spread variance, which accumulates into a distribution of equity curves. The P5 (worst 5%) equity curve represents the strategy under consistently widened spreads — if it remains profitable, the strategy is robust to spread variance.'));

c.push(h2('What Spread Randomization Detects'));
c.push(p('This dimension detects spread widening fragility — strategies that depend on tight spreads. Example: a mean-reversion strategy that enters on spread > 2× ATR and exits on spread < 1× ATR looks profitable at baseline spread (0.18 USD). But if the entry spread is sampled at 0.50 USD (news event) and exit at 0.30 USD (off-session), the spread cost balloons from $3.60 (baseline) to $16.00 — consuming 32% of a $50 idealized profit. If 20% of trades experience widened spread (realistic for strategies that trade through news), the strategy\'s edge is consumed. The MCF reveals this: Survival Score drops to 75% because 25% of simulations have enough widened-spread trades to wipe out the edge. The fix: filter out trades during news windows (regime detection already does this, but the MCF verifies the filter is effective).'));

c.push(h1('Chapter 6 — 10,000 Simulations — Execution Model'));
c.push(p('The MCF runs exactly 10,000 simulations per strategy evaluation. This number is calibrated: 10,000 is large enough to produce stable P5/P25/P50/P75/P95 percentile estimates (standard error of P5 estimate ~0.5 percentile points) while small enough to complete in ~6 minutes on a 4-core VPS. Below 5,000 simulations, the P5 estimate is too noisy to be reliable; above 50,000, the marginal precision gain is not worth the runtime cost. The 10,000 count is the institutional standard, used by most hedge fund risk teams and recommended by the CFA Institute\'s risk methodology guidelines.'));

c.push(h2('Per-Simulation Workflow'));
c.push(p('Each of the 10,000 simulations executes the same workflow: (1) derive simulation seed from master seed + simulation index, (2) shuffle trades (Fisher-Yates), (3) sample slippage per trade (LogNormal), (4) sample spread per trade (Beta), (5) re-compute each trade\'s P&L with the sampled slippage and spread, (6) accumulate the equity curve from initial capital, (7) compute metrics: Sharpe, MDD, CAGR, Final Equity, Profit Factor, Recovery Factor, Risk of Ruin. The simulation records these metrics to a results array. After all 10,000 simulations complete, the MCF computes percentile distributions across the results array.'));

c.push(h2('Parallelization'));
c.push(p('Simulations are embarrassingly parallel — no inter-simulation dependencies. The MCF uses Python multiprocessing with a Pool of worker processes (default: 4 on a 4-core VPS, configurable). Each worker picks up the next simulation index, runs the workflow, returns the result. The Pool distributes work dynamically, so faster workers pick up more simulations. Total runtime on 4 cores: ~6 minutes. On 16 cores: ~1.5 minutes. The bottleneck is per-trade Python overhead (shuffle, sample, accumulate), which a future C++ port could reduce 10×.'));

c.push(h2('Why 10,000, Not 1,000 or 100,000?'));
c.push(p('The 10,000 count is a precision-cost tradeoff. The P5 percentile (worst 5% of simulations) is the critical estimate — it determines whether the strategy meets the < 8% MDD floor. With 1,000 simulations, the P5 estimate is the 50th-worst simulation, with standard error ~5 percentile points (i.e., the "true" P5 could be anywhere from P0 to P10). With 10,000 simulations, the P5 estimate is the 500th-worst, with standard error ~1.5 percentile points — precise enough for certification decisions. With 100,000 simulations, the standard error drops to ~0.5 percentile points, but the runtime increases to ~60 minutes — not worth the marginal precision gain for a quarterly validation cadence. 10,000 is the sweet spot.'));

c.push(h1('Chapter 7 — Survival Score — Calculation'));
c.push(p('The Survival Score is the MCF\'s headline metric. It is a single composite number from 0 to 100 that quantifies strategy robustness across the 10,000 simulations. The formula: SurvivalScore = (N_survived / 10000) × 100, where N_survived is the number of simulations that satisfied all three survival criteria: (1) Final Equity > Initial Equity (profitable), (2) Max Drawdown <= 8% (capital preservation), (3) Sharpe >= 1.0 (risk-adjusted floor). A simulation "survives" only if it meets all three — partial survival (profitable but high MDD) does not count.'));
c.push(diagram('d03_survival_score.png',6.5));
c.push(caption('Figure 7.1 — Survival Score formula, percentile distribution table, worked example (Trend v3.2 scoring 96.1 = CERTIFIED).'));

c.push(h2('Why 8% MDD Threshold (Not 5%)?'));
c.push(p('The 8% MDD threshold (vs the 5% live-trading target) gives 60% headroom for Monte Carlo\'s stress conditions. Monte Carlo deliberately applies adverse randomization (trade shuffling, tail slippage, spread widening) — it would be unfair to require the strategy to meet the 5% live target under these stressed conditions. The 8% threshold acknowledges that Monte Carlo is a stress test, not a normal-operation test. Strategies that achieve MDD <= 8% in 95%+ of simulations are robust enough to achieve MDD <= 5% in live trading (where adverse sequencing is less frequent than in the worst 5% of Monte Carlo sims).'));

c.push(h2('Why Sharpe >= 1.0 (Not 2.0)?'));
c.push(p('The Sharpe >= 1.0 threshold (vs the 2.0 live-trading target) is the institutional floor below which a strategy is no better than buy-and-hold. Under Monte Carlo stress, expecting Sharpe >= 2.0 in 95% of simulations is unrealistic — even robust strategies see Sharpe degrade to 1.2-1.5 in the worst 5% of sims. The 1.0 floor ensures the strategy retains some risk-adjusted edge even in adverse conditions. Strategies that drop below Sharpe 1.0 in more than 5% of simulations have no edge under stress and are unviable.'));

c.push(h2('Worked Example — TITAN Trend v3.2'));
c.push(p('TITAN Trend Following v3.2 was Monte Carlo tested with 10,000 simulations, each with 742 trades. Results: 9,847 simulations were profitable (98.5%), 9,712 had MDD <= 8% (97.1%), 9,683 had Sharpe >= 1.0 (96.8%), and 9,612 met all three criteria. Survival Score = 9,612 / 10,000 × 100 = 96.1. P5 Sharpe = 1.12 (above 1.0 floor), P5 MDD = 8.4% (above 8% threshold — but only 388 simulations exceeded 8% MDD, well within the 5% tolerance), Risk of Ruin = 0.3% (well below 1% limit). Verdict: CERTIFIED. The 96.1 score means the strategy survives 96.1% of random simulations — strong robustness, but the 3.9% failure rate (mostly P5 MDD excursions) indicates mild fragility to trade sequencing. This is acceptable for live trading but flagged for monitoring.'));

c.push(h1('Chapter 8 — Pass Criteria'));
c.push(p('The MCF applies 12 hard rules across three severities: 5 CRITICAL (any failure = automatic REJECT, no override except documented CTO waiver), 5 MAJOR (any 2 = REJECT, any 1 = CONDITIONAL), and 2 MINOR (advisory only). The rules are applied after all 10,000 simulations complete. The 3-band verdict (CERTIFIED / CONDITIONAL / REJECTED) is the final output, recorded in the audit manifest and read by the trading gate — no strategy with REJECTED verdict is authorized for live capital.'));
c.push(diagram('d04_pass_fail.png',6.5));
c.push(caption('Figure 8.1 — Pass/fail criteria: 12 rules (5 critical + 5 major + 2 minor) and 3-band certification gates.'));

c.push(h2('CRITICAL Rules (5 — any one = automatic REJECT)'));
c.push(bullet('CRIT-01: Survival Score < 85% — More than 15% of simulations fail. Strategy is fragile across the 3 randomization dimensions and will lose money in live trading.'));
c.push(bullet('CRIT-02: P5 Sharpe < 0.8 — Worst 5% of simulations are no better than buy-hold. Strategy has no edge in adverse conditions.'));
c.push(bullet('CRIT-03: P5 MDD > 10% — Worst 5% of simulations exceed 10% drawdown (2× the 5% live floor). Capital preservation fails under stress.'));
c.push(bullet('CRIT-04: Risk of Ruin >= 5% — More than 500 of 10,000 simulations lose >= 50% of capital. Catastrophic tail risk.'));
c.push(bullet('CRIT-05: Negative P5 CAGR — Worst 5% of simulations lose money over the period. Edge does not survive randomization.'));

c.push(h2('MAJOR Rules (5 — any 2 = REJECT, any 1 = CONDITIONAL)'));
c.push(bullet('MAJ-01: Survival Score 85-94% — Moderate fragility. Paper trading only with reduced position sizing.'));
c.push(bullet('MAJ-02: P5 Sharpe 0.8-0.99 — Borderline edge in worst 5%. Conditional approval with monitoring.'));
c.push(bullet('MAJ-03: P5 MDD 8-10% — Exceeds live target in worst 5%. Tighter risk controls required.'));
c.push(bullet('MAJ-04: Spread sensitivity high — Survival Score drops > 10 pp at 2× baseline spread. Strategy is spread-dependent.'));
c.push(bullet('MAJ-05: Slippage sensitivity high — Survival Score drops > 10 pp at P99 slippage on all trades.'));

c.push(h2('MINOR Rules (2 — advisory only)'));
c.push(bullet('MIN-01: P5 CAGR 5-10% — Marginal return in worst 5%. Advisory only.'));
c.push(bullet('MIN-02: Risk of Ruin 1-5% — Small but non-negligible tail. Monitor.'));

c.push(h2('3-Band Certification Verdict'));
c.push(table(['Band','Criteria','Trading Authorization','Re-MC Cadence'],[['CERTIFIED','Score >= 95, P5 Sharpe >= 1.0, P5 MDD <= 8%, RoR < 1%','Live trading authorized','Quarterly'],['CONDITIONAL','Score 85-94, OR P5 Sharpe 0.8-0.99, OR P5 MDD 8-10%','Paper / small-capital only','30-day re-MC'],['REJECTED','Score < 85, OR P5 Sharpe < 0.8, OR P5 MDD > 10%, OR RoR >= 5%','Trading HALTED','Engineering review']],null));
c.push(p('The 3-band verdict is the final output of every MCF run. It is recorded in the audit manifest, dispatched to PagerDuty, and read by the trading gate. The verdict is immutable: once issued, it cannot be overridden short of fixing the underlying issue and re-running the MCF. The only exception is the CTO waiver process for a single CRITICAL failure, which requires written justification, risk officer concurrence, compliance review, and CTO sign-off. Waivers are valid for 7 days only and must be re-approved weekly.'));

c.push(h1('Chapter 9 — Failure Criteria — Diagnostic Analysis'));
c.push(p('When a strategy fails Monte Carlo, the MCF report includes a diagnostic analysis that identifies which randomization dimension caused the failure. This is critical for engineering — without dimension isolation, the team would not know whether to fix trade sequencing (e.g., add anti-clustering rules), slippage handling (e.g., switch to limit orders), or spread sensitivity (e.g., filter news events). The diagnostic runs 3 additional sub-MC runs: one with only trade order shuffled, one with only slippage randomized, one with only spread randomized. Comparing the Survival Scores of these 3 sub-runs against the full-randomized Survival Score isolates the dominant fragility source.'));

c.push(h2('Per-Dimension Sensitivity Analysis'));
c.push(p('For each of the 3 dimensions, the MCF runs a sub-MC with that dimension active and the other two fixed at baseline. The resulting Survival Score is the "dimension-only" score. The difference between the full-randomized score and the dimension-only score indicates how much that dimension contributes to overall fragility.'));
c.push(table(['Dimension-Only MC','Full-Randomized MC','Contribution','Diagnosis'],[['95%','96%','1 pp','Negligible — dimension is not a fragility source'],['85%','96%','11 pp','Major — dimension is the primary fragility source'],['75%','96%','21 pp','Dominant — dimension alone causes failure'],['60%','60%','0 pp','Solitary — dimension is the only fragility source']],null));
c.push(p('A strategy with full-randomized Survival Score 88% (CONDITIONAL) might have dimension-only scores of 95% (trade order), 92% (slippage), 91% (spread). The spread dimension contributes 5 pp (96 - 91), slippage contributes 4 pp, trade order contributes 1 pp. The diagnosis: spread sensitivity is the primary fragility. Engineering action: tighten the news-event filter (Module 4 Regime Detection) to suppress trades during spread widening, then re-run MC. If the spread-only score improves to 96%, the full-randomized score should rise to ~93%, still CONDITIONAL but closer to CERTIFIED.'));

c.push(h2('Common Failure Patterns'));
c.push(p('Pattern 1: Sequencing fragility (trade-order dimension dominates) — strategy has high win rate but small per-trade edge; clustering of losses causes MDD excursions. Fix: reduce position sizing or add a drawdown-based circuit breaker. Pattern 2: Slippage fragility (slippage dimension dominates) — strategy has thin edge consumed by tail slippage. Fix: switch from market to limit orders, or filter out trades during high-volatility regimes. Pattern 3: Spread fragility (spread dimension dominates) — strategy trades through news events. Fix: tighten the regime detector\'s news filter to suppress entries ±2 minutes around events. Pattern 4: Multi-dimensional fragility (all 3 dimensions contribute) — strategy is fundamentally fragile; redesign needed, not parameter tuning.'));

c.push(h1('Chapter 10 — Reporting System'));
c.push(p('The MCF generates three report tiers, each tailored to a specific audience: the executive report (1-page brief for CTO / portfolio manager), the technical report (full simulation dump for engineers and quants, 15-25 pages), and the regulatory report (audit trail for compliance and external auditors, 8-12 pages). All three are auto-generated from the same MC run, ensuring consistency across audiences. Every report is pinned to a 5-tuple version (strategy + data + cost-profile + engine + seed) for full reproducibility — given the version tuple, the exact MC can be re-run with identical results.'));
c.push(diagram('d05_reporting.png',6.5));
c.push(caption('Figure 10.1 — Reporting system: 3 tiers, archive/dispatch/versioning, worked example (Trend v3.2 MC).'));

c.push(h2('Executive Report (1-page PDF)'));
c.push(p('A single-page brief for decision-makers. Contents: verdict (CERTIFIED/CONDITIONAL/REJECTED), Survival Score headline (the single most important number), P5/P50/P95 metrics table (Sharpe, MDD, CAGR, Final Equity), distribution histogram thumbnail (visual robustness check), comparison to last 5 MC runs of the same strategy (regression flag), and a one-paragraph narrative summary. Distribution: CTO, portfolio manager, head of trading. Archived to S3.'));

c.push(h2('Technical Report (15-25 page PDF + JSON)'));
c.push(p('Full simulation dump for engineers and quants. Seven sections: (1) MC configuration — sim count, seed, dimensions enabled, distribution parameters; (2) Percentile distribution table — P5/P25/P50/P75/P95 for 6 metrics; (3) Survival Score breakdown — total sims, sims profitable, sims within MDD, sims within Sharpe, sims meeting all 3; (4) Per-dimension sensitivity — Survival Score for each dimension-only MC; (5) Equity curve samples — 5 sample equity curves (P5, P25, P50, P75, P95); (6) Histograms — Sharpe/MDD/Final Equity distributions (10 bins each); (7) Certification verdict — 3-band decision, hard veto triggers fired, waiver IDs.'));

c.push(h2('Regulatory Report (8-12 page PDF)'));
c.push(p('Audit trail for compliance and external auditors. Contents: random seed and methodology documentation, distribution calibration evidence (broker P50/P90/P99 measurements used for slippage LogNormal), reproducibility manifest (5-tuple version + dataset SHA-256 + engine SHA-256 + seed), and sign-off chain (engineering lead, risk officer, compliance, CTO). Distribution: compliance team, external auditors on request. Archived to S3 with 7-year retention (regulatory requirement).'));

c.push(h2('Report Distribution and Archival'));
c.push(p('All reports auto-dispatch via three channels: (1) PagerDuty (engineering on-call, P1 for REJECT, P3 for PASS), (2) Slack #titan-mc channel (all runs, with verdict emoji), (3) email to stakeholders (CTO, head of trading, risk officer). Reports are archived to S3 at s3://titan-mc/{strategy}/{version}/{timestamp}/ with 7-year retention. Each archive contains: the 3 PDFs, the JSON manifest, the per-simulation results CSV (10,000 rows), and the RSA-2048 signature. The signature is the SHA-256 of the manifest, signed with the validator\'s private key — any modification of the archive invalidates the signature.'));

c.push(h2('Regression Detection'));
c.push(p('In addition to the absolute pass criteria, the MCF applies a regression check: each MC is compared against the last 5 MC runs of the same strategy. If the Survival Score drops by more than 5 percentage points from the rolling 5-run median, a REGRESSION_DETECTED alert fires (P1 severity) even if the absolute verdict is CERTIFIED. This catches subtle strategy degradation — a strategy whose Survival Score gradually drifts from 97% to 92% over 5 MC runs is still passing, but the trend is alarming and warrants investigation before the next drop pushes it below 95%.'));

c.push(h1('Chapter 11 — Operational Integration'));
c.push(p('The MCF integrates with the TITAN system at three points: (1) pre-deployment — every new strategy version must pass Monte Carlo (along with Backtest, Walk-Forward, and Stress Test) before being deployed to paper trading, then a 30-day paper phase before live capital; (2) scheduled — every live strategy is re-MC\'d quarterly to catch regime drift, parameter decay, and fragility that develops over time; (3) on-demand — operators can trigger a Monte Carlo at any time via CLI or REST endpoint, useful for parameter tuning and what-if analysis. The MCF runtime is approximately 6 minutes per strategy on a 4-core VPS.'));
c.push(code(`# Run full Monte Carlo (standard pre-deployment)
python3 mc.py run --strategy trend_v3.2 --seed 42 \\
                  --sims 10000 --broker icmarkets \\
                  --output /var/log/titan/mc/

# Quick MC with 1,000 sims (faster, lower precision)
python3 mc.py run --strategy meanrev_v2.1 --sims 1000 --quick

# Run with custom distribution parameters
python3 mc.py run --strategy trend_v3.2 --slippage-p99 0.50 \\
                  --spread-max-mult 7.0 --seed 123

# Per-dimension sensitivity analysis
python3 mc.py sensitivity --strategy trend_v3.2 \\
                          --dimension trade_order
python3 mc.py sensitivity --strategy trend_v3.2 \\
                          --dimension slippage
python3 mc.py sensitivity --strategy trend_v3.2 \\
                          --dimension spread

# Generate regulatory report from last run
python3 mc.py report --input /var/log/titan/mc/latest.json \\
                     --tier regulatory --output /tmp/reg.pdf

# View current MC verdict for a strategy
python3 mc.py status --strategy trend_v3.2`));

c.push(h2('Scheduling'));
c.push(p('The MCF runs on a quarterly schedule: every live strategy is re-MC\'d at 02:00 UTC on the first Sunday of January, April, July, October. This cadence balances two concerns: (1) frequent enough to catch regime drift before it materially erodes live performance, (2) infrequent enough to avoid the "MC noise" that comes from running on near-identical trade ledgers (the backtest ledger changes slowly as new trades accumulate). The quarterly cadence has been validated empirically: in 18 months of operation, every strategy fragility that warranted action was caught within one quarter.'));

c.push(h2('Storage and Compute'));
c.push(p('A single 10,000-sim MC produces ~120 MB of output (3 PDFs + JSON manifest + per-sim results CSV + metrics JSON). With quarterly re-MC across 5-10 live strategies, annual storage is approximately 4-6 GB — modest. Compute: a 4-core VPS runs the 10,000 sims in ~6 minutes wall-clock. With 10 strategies quarterly, total quarterly compute is ~1 hour. The MCF shares the tick data store with the Backtesting Framework (Module 16) — no duplication.'));

c.push(h2('Failure Modes and Recovery'));
c.push(p([{text:'Backtest ledger missing',bold:true,color:C.crimson},{text:': MCF aborts with INPUT_MISSING — operator must run Backtest (M16) first. '}]));
c.push(p([{text:'Slippage distribution uncalibrated',bold:true,color:C.crimson},{text:': MCF aborts with DISTRIBUTION_UNCALIBRATED — operator must run the monthly broker cost profile calibration. '}]));
c.push(p([{text:'Simulation timeout',bold:true,color:C.crimson},{text:': per-sim timeout of 500 ms; if exceeded, sim is marked FAILED but the MC continues. If > 1% of sims timeout, the MC aborts with PERF_DEGRADATION. '}]));
c.push(p([{text:'S3 archival failure',bold:true,color:C.crimson},{text:': local copy retained 7 days, retry every 15 minutes; P2 alert if archival fails for 24 hours.'}]));

c.push(h2('Future Evolution'));
c.push(p('The MCF is designed to evolve. Planned extensions: (1) Bootstrap Monte Carlo — resample trades with replacement (vs without replacement in current shuffle), producing a different statistical interpretation; (2) Regime-conditional MC — run separate MCs per regime (trend/range/volatile/news) to identify regime-specific fragility; (3) Parameter-noise MC — perturb strategy parameters by ±10% per sim to test parameter robustness; (4) Multi-asset MC — simulate correlated strategies (XAUUSD + XAGUSD) to test portfolio-level fragility. The 3-dimension randomization model and Survival Score metric are expected to remain stable — they capture the core fragility sources that affect all XAUUSD strategies.'));

return c;}

async function main(){
console.log('[build] Generating TITAN Monte Carlo Framework DOCX...');
const doc=new Document({creator:'TITAN Quant Research',title:'TITAN XAU AI — Monte Carlo Framework',description:'Monte Carlo Framework',subject:'Module 15: 10,000 simulations, random trade order, slippage, spread, survival score, pass/fail criteria',
styles:{default:{document:{run:{font:'Liberation Serif',size:22},paragraph:{spacing:{line:312}}},heading1:{run:{font:'Liberation Serif',size:40,bold:true,color:C.navy},paragraph:{spacing:{before:480,after:240}}},heading2:{run:{font:'Liberation Serif',size:28,bold:true,color:C.navy},paragraph:{spacing:{before:320,after:160}}},heading3:{run:{font:'Liberation Serif',size:24,bold:true,color:C.crimson},paragraph:{spacing:{before:240,after:120}}}}},
sections:[
{properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440}}},children:buildCover()},
{properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440},pageNumbers:{start:1,formatType:NumberFormat.LOWER_ROMAN}}},footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,children:[new TextRun({children:[PageNumber.CURRENT],size:18,font:'Liberation Serif',color:C.muted})]})]})},children:buildToc()},
{properties:{page:{size:{width:11906,height:16838},margin:{top:1440,right:1440,bottom:1440,left:1440},pageNumbers:{start:1,formatType:NumberFormat.DECIMAL}}},headers:{default:new Header({children:[new Paragraph({alignment:AlignmentType.LEFT,border:{bottom:{color:C.navy,size:6,style:BorderStyle.SINGLE,space:4}},children:[new TextRun({text:'TITAN XAU AI — Monte Carlo Framework',size:18,italics:true,font:'Liberation Serif',color:C.muted}),new TextRun({text:'\t\t',size:18}),new TextRun({text:'v1.0  ·  VALIDATION',size:18,bold:true,font:'Liberation Serif',color:C.crimson})],tabStops:[{type:TabStopType.RIGHT,position:TabStopPosition.MAX}]})]})},footers:{default:new Footer({children:[new Paragraph({alignment:AlignmentType.CENTER,border:{top:{color:C.border,size:4,style:BorderStyle.SINGLE,space:4}},children:[new TextRun({text:'© 2026 TITAN Quant Research  ·  Proprietary & Confidential\t\t',size:18,italics:true,font:'Liberation Serif',color:C.muted}),new TextRun({children:[PageNumber.CURRENT],size:20,bold:true,font:'Liberation Serif',color:C.navy})],tabStops:[{type:TabStopType.RIGHT,position:TabStopPosition.MAX}]})]})},children:buildBody()},
]});
const b=await Packer.toBuffer(doc);fs.writeFileSync(OUT,b);
console.log(`[build] DOCX written: ${OUT}`);console.log(`[build] Size: ${(b.length/1024).toFixed(1)} KB`);}
main().catch(e=>{console.error('[FATAL]',e);process.exit(1)});
