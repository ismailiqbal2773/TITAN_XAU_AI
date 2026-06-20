/**
 * TITAN XAU AI — DOCX builder (docx-js)
 * Generates the editable Word version of the architecture document.
 *
 * Run with:
 *   NODE_PATH=/home/z/.npm-global/lib/node_modules node /home/z/my-project/scripts/titan/build_docx.js
 */
const fs = require('fs');
const path = require('path');
const { imageSize } = require('image-size');
const docx = require('docx');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  PageBreak, ImageRun, Table, TableRow, TableCell, WidthType, BorderStyle,
  TableOfContents, StyleLevel, LevelFormat, Footer, Header, PageNumber,
  NumberFormat, ShadingType, TabStopType, TabStopPosition,
  convertInchesToTwip, convertMillimetersToTwip,
  HeightRule, VerticalAlign, PageOrientation,
} = docx;

// ─── Goldman Sachs white palette ─────────────────────────────────────────
const C = {
  navy:   '14213D',
  crimson:'C8102E',
  slate:  '4A5568',
  bg:     'FFFFFF',
  card:   'F1F5F9',
  stripe: 'F8FAFC',
  border: 'CBD5E1',
  text:   '14213D',
  muted:  '4A5568',
};

const DIAGRAM_DIR = '/home/z/my-project/scripts/titan/diagrams/png';
const OUTPUT_PATH = '/home/z/my-project/download/TITAN_XAU_AI_Architecture_v1.0.docx';

// ─── Helpers ─────────────────────────────────────────────────────────────
function p(text, opts = {}) {
  // Body paragraph. opts: { bold, italic, color, size, indent }
  const runs = (Array.isArray(text) ? text : [{ text }]).map(r => new TextRun({
    text: r.text,
    bold: r.bold || opts.bold,
    italics: r.italic || opts.italic,
    color: r.color || opts.color || C.text,
    size: (r.size || opts.size || 22),  // 11pt
    font: 'Liberation Serif',
  }));
  return new Paragraph({
    children: runs,
    spacing: { after: 160, line: 312 },  // 1.3x line spacing
    alignment: opts.alignment || AlignmentType.JUSTIFIED,
    indent: opts.indent ? { firstLine: 360 } : undefined,
  });
}

function h1(text) {
  return new Paragraph({
    children: [new TextRun({ text, bold: true, color: C.navy, size: 40, font: 'Liberation Serif' })],
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 480, after: 240 },
    pageBreakBefore: true,
    border: { bottom: { color: C.crimson, size: 18, style: BorderStyle.SINGLE, space: 4 } },
  });
}

function h2(text) {
  return new Paragraph({
    children: [new TextRun({ text, bold: true, color: C.navy, size: 28, font: 'Liberation Serif' })],
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 320, after: 160 },
  });
}

function h3(text) {
  return new Paragraph({
    children: [new TextRun({ text, bold: true, color: C.crimson, size: 24, font: 'Liberation Serif' })],
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 240, after: 120 },
  });
}

function bullet(text) {
  return new Paragraph({
    children: [new TextRun({ text, size: 22, font: 'Liberation Serif', color: C.text })],
    bullet: { level: 0 },
    spacing: { after: 80, line: 280 },
  });
}

function code(text) {
  return new Paragraph({
    children: [new TextRun({ text, size: 18, font: 'DejaVu Sans Mono', color: C.text })],
    spacing: { before: 120, after: 200, line: 240 },
    shading: { type: ShadingType.CLEAR, color: 'auto', fill: C.stripe },
    border: {
      left: { color: C.crimson, size: 18, style: BorderStyle.SINGLE, space: 6 },
    },
    indent: { left: 240, right: 240 },
  });
}

function callout(text) {
  return new Paragraph({
    children: [new TextRun({ text, italics: true, size: 22, font: 'Liberation Serif', color: C.navy })],
    spacing: { before: 160, after: 200, line: 300 },
    shading: { type: ShadingType.CLEAR, color: 'auto', fill: C.card },
    border: {
      left: { color: C.crimson, size: 24, style: BorderStyle.SINGLE, space: 8 },
      top: { color: C.border, size: 4, style: BorderStyle.SINGLE, space: 4 },
      bottom: { color: C.border, size: 4, style: BorderStyle.SINGLE, space: 4 },
      right: { color: C.border, size: 4, style: BorderStyle.SINGLE, space: 4 },
    },
    indent: { left: 240, right: 240 },
  });
}

function caption(text) {
  return new Paragraph({
    children: [new TextRun({ text, italics: true, size: 18, font: 'Liberation Serif', color: C.muted })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 60, after: 280 },
  });
}

function diagram(filename, widthInches = 6.5) {
  const fullPath = path.join(DIAGRAM_DIR, filename);
  if (!fs.existsSync(fullPath)) {
    return p(`[Diagram missing: ${filename}]`, { italic: true, color: C.crimson });
  }
  const buf = fs.readFileSync(fullPath);
  const dim = imageSize(buf);
  const aspect = dim.height / dim.width;
  const widthPx = widthInches * 96;
  const heightPx = widthPx * aspect;
  return new Paragraph({
    children: [new ImageRun({
      data: buf,
      transformation: { width: widthPx, height: heightPx },
      type: 'png',
    })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 200, after: 100 },
  });
}

function table(headers, rows, colWidthPct = null) {
  // colWidthPct: array of percentages summing to 100, or null for equal
  const n = headers.length;
  const widths = colWidthPct || Array(n).fill(100 / n);
  const totalDxa = 9000;  // ~6.25 inches for content width

  const headerCells = headers.map((h, i) => new TableCell({
    children: [new Paragraph({
      children: [new TextRun({ text: h, bold: true, color: 'FFFFFF', size: 20, font: 'Liberation Serif' })],
      alignment: AlignmentType.LEFT,
    })],
    shading: { type: ShadingType.CLEAR, color: 'auto', fill: C.navy },
    width: { size: Math.round(widths[i] * totalDxa / 100), type: WidthType.DXA },
    margins: { top: 80, bottom: 80, left: 100, right: 100 },
    verticalAlign: VerticalAlign.CENTER,
  }));

  const headerRow = new TableRow({ children: headerCells, tableHeader: true, cantSplit: true });

  const dataRows = rows.map((row, ri) => new TableRow({
    children: row.map((cell, i) => new TableCell({
      children: [new Paragraph({
        children: [new TextRun({ text: String(cell), size: 18, font: 'Liberation Serif', color: C.text })],
        alignment: AlignmentType.LEFT,
        spacing: { line: 240 },
      })],
      shading: ri % 2 === 1 ? { type: ShadingType.CLEAR, color: 'auto', fill: C.stripe } : undefined,
      width: { size: Math.round(widths[i] * totalDxa / 100), type: WidthType.DXA },
      margins: { top: 60, bottom: 60, left: 100, right: 100 },
      verticalAlign: VerticalAlign.TOP,
    })),
    cantSplit: true,
  }));

  return new Table({
    rows: [headerRow, ...dataRows],
    width: { size: totalDxa, type: WidthType.DXA },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 6, color: C.navy },
      bottom: { style: BorderStyle.SINGLE, size: 6, color: C.navy },
      left: { style: BorderStyle.SINGLE, size: 4, color: C.border },
      right: { style: BorderStyle.SINGLE, size: 4, color: C.border },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 4, color: C.border },
      insideVertical: { style: BorderStyle.SINGLE, size: 4, color: C.border },
    },
  });
}

function spacer(after = 200) {
  return new Paragraph({ children: [], spacing: { after } });
}

// ════════════════════════════════════════════════════════════════════════
//  DOCUMENT CONTENT
// ════════════════════════════════════════════════════════════════════════

function buildCoverChildren() {
  return [
    // Top brand block
    new Paragraph({
      children: [
        new TextRun({ text: 'TITAN  ·  QUANT  RESEARCH', size: 18, font: 'JetBrains Mono', color: C.crimson, bold: true }),
      ],
      spacing: { before: 720, after: 120 },
      alignment: AlignmentType.LEFT,
    }),
    new Paragraph({
      children: [new TextRun({ text: 'TITAN XAU AI', size: 56, font: 'Liberation Serif', color: C.navy, bold: true })],
      spacing: { after: 80 },
    }),
    new Paragraph({
      children: [new TextRun({ text: 'INSTITUTIONAL  TRADING  SYSTEMS', size: 18, font: 'JetBrains Mono', color: C.muted })],
      spacing: { after: 720 },
      border: { bottom: { color: C.navy, size: 18, style: BorderStyle.SINGLE, space: 4 } },
    }),

    // Title
    new Paragraph({
      children: [
        new TextRun({ text: 'A R C H I T E C T U R E   S P E C I F I C A T I O N', size: 20, font: 'JetBrains Mono', color: C.crimson, bold: true }),
      ],
      spacing: { before: 720, after: 360 },
    }),
    new Paragraph({
      children: [
        new TextRun({ text: 'TITAN', size: 84, font: 'Liberation Serif', color: C.navy, bold: true }),
        new TextRun({ text: ' XAU', size: 84, font: 'Liberation Serif', color: C.crimson, bold: true }),
        new TextRun({ text: ' AI', size: 84, font: 'Liberation Serif', color: C.navy, bold: true }),
      ],
      spacing: { after: 360, line: 240 },
    }),
    new Paragraph({
      children: [new TextRun({
        text: 'An institutional-grade AI trading system for XAUUSD. Modular architecture, async event-driven design, C++ execution core with Python intelligence layer, MT5 compatible, broker independent, commercial licensing ready.',
        italics: true, size: 26, font: 'Liberation Serif', color: C.muted,
      })],
      spacing: { after: 720, line: 360 },
    }),

    // Stats
    new Paragraph({
      children: [new TextRun({ text: 'TARGET METRICS', size: 16, font: 'JetBrains Mono', color: C.crimson, bold: true })],
      spacing: { before: 240, after: 120 },
      border: { top: { color: C.navy, size: 12, style: BorderStyle.SINGLE, space: 4 } },
    }),
    table(
      ['Metric', 'Target', 'Measurement'],
      [
        ['Max Drawdown', '< 5%', 'Trailing 90 days'],
        ['Profit Factor', '> 2.0', 'Trailing 90 days'],
        ['Sharpe Ratio', '> 2.0', 'Trailing 252 days'],
        ['Recovery Factor', '> 5.0', 'Trailing 252 days'],
        ['Risk of Ruin', '< 1%', 'Monte Carlo, 1000 paths × 252 days'],
      ],
      [30, 25, 45]
    ),
    spacer(360),

    // Bottom meta
    new Paragraph({
      children: [
        new TextRun({ text: 'Prepared by  ', size: 18, font: 'JetBrains Mono', color: C.muted }),
        new TextRun({ text: 'TITAN Quant Research', size: 18, font: 'JetBrains Mono', color: C.navy, bold: true }),
      ],
      spacing: { after: 40 },
    }),
    new Paragraph({
      children: [
        new TextRun({ text: 'Reviewed by  ', size: 18, font: 'JetBrains Mono', color: C.muted }),
        new TextRun({ text: 'CTO · Risk Officer · Compliance', size: 18, font: 'JetBrains Mono', color: C.navy, bold: true }),
      ],
      spacing: { after: 40 },
    }),
    new Paragraph({
      children: [
        new TextRun({ text: 'Classification  ', size: 18, font: 'JetBrains Mono', color: C.muted }),
        new TextRun({ text: 'COMMERCIAL — LICENSEE DISTRIBUTION', size: 18, font: 'JetBrains Mono', color: C.crimson, bold: true }),
      ],
      spacing: { after: 40 },
    }),
    new Paragraph({
      children: [
        new TextRun({ text: 'Version  ', size: 18, font: 'JetBrains Mono', color: C.muted }),
        new TextRun({ text: 'v1.0  ·  19 June 2026', size: 18, font: 'JetBrains Mono', color: C.navy, bold: true }),
      ],
      spacing: { after: 0 },
      border: { top: { color: C.navy, size: 6, style: BorderStyle.SINGLE, space: 4 } },
    }),

    new Paragraph({ children: [new PageBreak()] }),
  ];
}

function buildTocChildren() {
  return [
    new Paragraph({
      children: [new TextRun({ text: 'Table of Contents', bold: true, size: 44, font: 'Liberation Serif', color: C.navy })],
      spacing: { after: 240 },
      border: { bottom: { color: C.crimson, size: 18, style: BorderStyle.SINGLE, space: 4 } },
    }),
    new Paragraph({
      children: [new TextRun({
        text: 'Right-click the table below and choose "Update Field" to refresh page numbers.',
        italics: true, size: 18, color: C.muted, font: 'Liberation Serif',
      })],
      spacing: { after: 280 },
    }),
    new TableOfContents('Table of Contents', {
      hyperlink: true,
      headingStyleRange: '1-3',
      stylesWithLevels: [
        new StyleLevel('Heading1', 1),
        new StyleLevel('Heading2', 2),
        new StyleLevel('Heading3', 3),
      ],
    }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

function buildBodyChildren() {
  const children = [];

  // ─── Document Control ─────────────────────────────────────────────────
  children.push(new Paragraph({
    children: [new TextRun({ text: 'Document Control', bold: true, size: 40, font: 'Liberation Serif', color: C.navy })],
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 240, after: 200 },
    border: { bottom: { color: C.crimson, size: 18, style: BorderStyle.SINGLE, space: 4 } },
  }));
  children.push(p('This document specifies the complete system architecture for TITAN XAU AI, an institutional-grade artificial intelligence trading system focused exclusively on the XAUUSD (spot gold versus US dollar) instrument. It is intended as the authoritative reference for engineering teams, licensees, infrastructure partners, and compliance reviewers. All design decisions captured here are binding on the v1.0 release; deviations require an Architecture Decision Record (ADR) and CTO sign-off.'));
  children.push(p('The document covers nine deliverables mandated by the project charter: complete folder structure, service architecture, data flow diagrams, module dependency graph, UML class diagrams, deployment architecture, VPS architecture, production architecture, and testing architecture. Each deliverable is presented as a dedicated chapter with a rendered diagram, supporting narrative, and reference tables. Non-functional requirements, risk controls, licensing hooks, and the implementation roadmap are covered in supporting chapters.'));

  children.push(h2('Revision History'));
  children.push(table(
    ['Version', 'Date', 'Author', 'Reviewer', 'Summary of Changes'],
    [
      ['v0.1', '2026-04-12', 'Quant Research', 'Internal', 'Initial draft, scope and outline'],
      ['v0.5', '2026-05-08', 'Quant Research', 'CTO', 'Folder structure, service architecture, DFD drafts'],
      ['v0.8', '2026-05-30', 'Quant Research', 'Risk Officer', 'Class diagrams, deployment topology, VPS deep dive'],
      ['v0.95', '2026-06-12', 'Quant Research', 'CTO+Risk+Compliance', 'Production architecture, testing, NFRs, licensing'],
      ['v1.0', '2026-06-19', 'Quant Research', 'Board sign-off', 'GA release, commercial licensing terms embedded'],
    ],
    [12, 14, 22, 28, 24]
  ));
  children.push(spacer(200));

  children.push(h2('Distribution List & Confidentiality'));
  children.push(p('This document is classified COMMERCIAL — LICENSEE DISTRIBUTION. It may be shared with prospective licensees under NDA, with the operations team responsible for running the system, and with auditors performing due diligence. It must NOT be shared publicly, posted to public repositories, or distributed to competing trading firms. Each copy carries a watermark identifying the recipient; redistribution outside the named recipient is a breach of the master license agreement.'));
  children.push(table(
    ['Recipient Class', 'Access Level', 'Watermark', 'Retention'],
    [
      ['Internal engineering', 'Full', 'Employee ID', 'Employment + 1 year'],
      ['Licensee (signed MSA)', 'Full', 'Tenant ID', 'License term + 5 years'],
      ['Prospective licensee (NDA)', 'Redacted (no licensing chapter)', 'NDA reference', 'NDA term'],
      ['Auditor / due diligence', 'Full read-only', 'Auditor firm', 'Engagement + 90 days'],
      ['Investor (Term Sheet signed)', 'Executive summary + architecture overview only', 'Investor ID', 'Indefinite'],
    ],
    [30, 32, 20, 18]
  ));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 1 — Executive Summary
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 1 — Executive Summary'));
  children.push(p('TITAN XAU AI is a modular, asynchronous, event-driven trading system engineered for institutional deployment on the XAUUSD instrument. It combines a low-latency C++ execution core with a Python-based intelligence layer, bridged via PyO3, to achieve the rare combination of microsecond-class order latency and machine-learning-class alpha generation. The system is broker-independent at the protocol layer (MT5 today, FIX and IB planned), compatible with MetaTrader 5 as its primary execution venue, and structured for commercial licensing from day one.'));
  children.push(p('The system is designed around a single non-negotiable principle: capital preservation takes absolute precedence over alpha generation. Every architectural decision — from the structural separation of the risk layer from the strategy layer, to the kill switch being a first-class citizen rather than an afterthought, to the mandatory backtest regression gate in the CI/CD pipeline — exists to enforce this principle. The target metrics reflect it: maximum drawdown below five percent, profit factor above two, Sharpe ratio above two, recovery factor above five, and a risk-of-ruin below one percent under Monte Carlo simulation. These are not aspirational numbers; they are CI/CD gate thresholds.'));
  children.push(p('The architecture comprises six logical layers (ingest, normalize, intelligence, risk, execution, persistence and operations), eleven core services, and approximately 350 modules split between C++ (latency-critical hot path) and Python (research, feature engineering, machine learning inference, orchestration). A strict layering rule — modules at layer N may only depend on modules at layer N-1 or below — guarantees that risk retains structural veto power over every order, a property that cannot be violated by accident or malice without an explicit architectural change.'));
  children.push(p('Deployment follows a three-zone high-availability topology: a primary VPS in NY4 (Equinix New York) colocated with broker matching engines, a hot-standby in EQ4 with sub-three-second VRRP failover, and a geographically remote disaster-recovery VPS in LD4 (London) for catastrophic failure scenarios. The system is designed for 99.95% uptime with a fifteen-minute mean time to recovery. Observability is built in from the kernel sysctl level up to the operator console, with Prometheus metrics, structured JSON logs in Loki, distributed traces in OpenTelemetry, and an immutable hash-chained audit store.'));
  children.push(p('Commercial licensing is enforced through a per-tenant RSA-signed JWT model with online heartbeat and a seven-day offline grace period. Three tiers (Starter, Pro, Enterprise) gate strategy count, capital ceiling, and feature access. Hardware fingerprinting, code obfuscation, and tamper detection protect against piracy without imposing onerous restrictions on legitimate licensees. The license server itself is a SaaS component running on AWS, freeing licensees from operating it themselves.'));
  children.push(p('The implementation roadmap spans twelve months across four phases: Foundation (M1-M3) delivers the core infrastructure and backtest engine; Intelligence (M4-M6) adds the feature and signal engines with the first live strategy; Productionization (M7-M9) completes the HA deployment, monitoring, licensing, and canary CI/CD pipeline; Commercialization (M10-M12) adds multi-tenant isolation, billing, and white-label capabilities culminating in v1.0 general availability. Each phase has hard exit criteria tied to the target metrics — the system cannot progress to the next phase without meeting them on out-of-sample data.'));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 2 — Vision & Philosophy
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 2 — System Vision & Design Philosophy'));
  children.push(h2('Problem Framing — Why XAUUSD Demands a Specialized Architecture'));
  children.push(p('XAUUSD, the spot gold versus US dollar pair, is one of the most actively traded instruments in the world and exhibits a set of microstructure characteristics that make it uniquely challenging for systematic trading. It trades nearly twenty-four hours a day across Asian, European, and American sessions, with liquidity and volatility regimes that shift dramatically between them. It is acutely sensitive to central bank communications, geopolitical events, and real-yield movements — a single Federal Reserve press conference can move the price by several percent in minutes. Liquidity is fragmented across multiple ECNs and broker-dealer networks, with spreads that can widen by an order of magnitude during news events. These properties rule out many naive approaches: a strategy that works in calm conditions may experience catastrophic slippage during news windows, and a single broker disconnection during a fast market can leave a position exposed to unbounded adverse selection.'));
  children.push(p('TITAN XAU AI is purpose-built for this environment. Rather than attempting to be a general-purpose trading platform, every architectural choice is optimized for the specific demands of gold: low-latency tick processing to capture microstructure signals, news-aware risk gating to avoid trading during high-impact events, broker-agnostic abstraction to enable failover when a primary venue degrades, and a regime detection subsystem that adapts strategy behavior to the prevailing volatility environment. The narrow instrument focus also dramatically reduces the attack surface — there is no need to handle corporate actions, dividend dates, or earnings surprises, allowing the team to concentrate engineering effort on the few things that matter for gold.'));

  children.push(h2('Design Philosophy'));
  children.push(p('The system is built on four philosophical commitments that together define its character and distinguish it from retail-grade trading bots. Each commitment has direct architectural consequences documented throughout this specification.'));

  children.push(h3('1. Capital Preservation First, Alpha Generation Second'));
  children.push(p('Most trading systems treat risk management as a feature to be added on top of the trading logic. TITAN XAU AI treats it as the foundation on which everything else is built. The risk layer is structurally separate from the strategy layer, with a hard architectural rule that risk never depends on strategy — only the reverse. The kill switch is a first-class service with its own communication channel to the order manager, able to halt new orders, flatten existing positions, and cancel pending orders in under five hundred milliseconds. Pre-trade risk gates run synchronously in the hot path, blocking any order that violates position, leverage, exposure, or news-blackout constraints. The CI/CD pipeline refuses to promote any build that does not meet the target risk metrics on out-of-sample data.'));

  children.push(h3('2. Deterministic Risk Envelope'));
  children.push(p('The system operates within a strictly defined risk envelope that is verifiable from outside. Position size, leverage, daily trade count, drawdown circuit breakers, and news-blackout windows are all encoded as configuration that is loaded at startup and cannot be modified by the strategy layer at runtime. Any change to the risk envelope requires a supervisor-level authorization with an audit-trail entry, and most changes auto-revert after a configurable timeout. This determinism is essential for institutional licensees who must be able to demonstrate to their own risk committees and regulators that the system operates within approved bounds.'));

  children.push(h3('3. Separation of Concerns via Strict Layering'));
  children.push(p('The six-layer architecture is enforced by a strict dependency rule: a module at layer N may only import or call modules at layer N-1 or below. This rule is verified by an automated architecture lint in CI; cyclic dependencies fail the build. The practical consequence is that the strategy layer cannot reach into the execution layer to bypass risk checks, the execution layer cannot reach into the ingest layer to manipulate tick data, and the risk layer has no knowledge of why a particular order was placed — only that it must be vetted. This makes the system auditable, testable in isolation, and resistant to the kind of subtle coupling that causes cascading failures in less disciplined systems.'));

  children.push(h3('4. Replay-Anywhere Determinism'));
  children.push(p('Every event that flows through the system — every tick, every news item, every operator action, every risk decision, every fill — is captured to an immutable log with a monotonic sequence number and a high-precision timestamp. Given the same input event stream and the same starting state, the system produces byte-identical output. This enables forensic reconstruction of any trading day, walk-forward backtesting on actual historical event streams rather than sanitized bar data, and chaos engineering replays where fault scenarios can be re-run against historical data to verify mitigation effectiveness. Determinism is the foundation of trust in an autonomous trading system.'));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 3 — Tenets
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 3 — Architectural Tenets & Principles'));
  children.push(p('The tenets below are the architectural constitution of TITAN XAU AI. They are referenced by every Architecture Decision Record and are the basis for resolving design disputes. A tenet may be overridden only by unanimous agreement of the architecture review board and only with a documented replacement.'));

  const tenets = [
    ['Single Source of Truth for Market Data',
     'All market data — ticks, bars, news, economic events — flows through a single normalization pipeline before reaching any consumer. There is exactly one TickStore and one FeatureStore per trading cluster. This eliminates the class of bugs where different strategies see slightly different views of the market due to feed timing or normalization discrepancies, and it makes the audit log authoritative: any decision can be traced back to the exact market state that produced it.'],
    ['Pure-Function Strategy Layer',
     'Strategies are implemented as pure functions of (market_state, position, config) returning a Signal. They have no side effects, no shared mutable state, and no direct access to the network, filesystem, or clock. This makes them trivially testable, parallelizable across instruments, and safe to hot-reload at runtime. Side-effecting operations — placing orders, logging, emitting metrics — are the exclusive responsibility of the framework.'],
    ['Risk as a Separate Microservice with Veto Power',
     'The risk layer runs as an independent service with its own CPU allocation, its own configuration, and its own deployment cadence. It cannot be overridden by the strategy layer, the operator console (for high-impact limits), or any other subsystem. The PreTradeRiskGate runs synchronously in the hot path; if it returns REJECT, the order is not sent. Period. This is the structural guarantee that capital preservation is enforced rather than merely encouraged.'],
    ['Deterministic Replay',
     'Given the same event stream and starting state, the system produces byte-identical output. This requires that all randomness be seeded from the configuration, all time-dependent logic read from a monotonic logical clock rather than wall time, and all external API calls be wrapped in replayable adapters. The reward is enormous: any production incident can be reproduced in a dev environment by replaying the event log, and backtests run on the same code path as live trading.'],
    ['C++ for the Latency-Critical Path, Python for the Intelligence Layer',
     'The hot path — tick ingestion, normalization, risk gating, order management — is implemented in C++20 with manual memory management, lock-free queues, and CPU pinning. The intelligence layer — feature engineering, signal generation, ML inference, strategy orchestration — is implemented in Python 3.12 with NumPy, pandas, and PyTorch. The two layers communicate via PyO3 bindings and zero-copy FlatBuffers. This division gives us sub-millisecond latency where it matters and rapid iteration where it does not.'],
    ['Async Event Bus with Backpressure',
     'All inter-service communication flows through a single async event bus implemented on ZeroMQ PUB/SUB with lock-free SPSC queues for the hottest paths. The bus implements backpressure: if a consumer falls behind, producers are throttled rather than dropping messages. This prevents cascading failures under load and ensures that the system degrades gracefully rather than catastrophically when a downstream service is slow.'],
    ['Statelessness of the Execution Layer',
     'The execution layer — OrderManager, SmartRouter, FillTracker — is stateless across restarts. All state is persisted to Redis (hot) and TimescaleDB (cold) on every transition. A crashed titan-core process can be restarted and resume trading within seconds by loading state from Redis. This dramatically simplifies operations: there is no need for graceful shutdown procedures, and rolling updates require no special coordination.'],
    ['Observability-First',
     'Every service emits Prometheus metrics, structured JSON logs, and OpenTelemetry traces from day one of development. Adding observability retroactively is far more expensive than building it in from the start, and in a trading system the absence of observability is itself a critical defect — you cannot debug what you cannot see. The default dashboard exposes real-time PnL, exposure, latency percentiles, and risk-gate rejection rates, and any deviation from baseline triggers an alert.'],
    ['Kill Switch as a First-Class Citizen',
     'The kill switch is not a feature flag or an operator action buried in a menu. It is a dedicated service with its own network path, its own authentication, and its own auditable trigger history. Engaging the kill switch halts all new orders, flattens existing positions, cancels pending orders, and notifies the operator — all in under five hundred milliseconds. The kill switch can be triggered manually from the operator console, automatically by the PostTradeRiskMonitor on hard drawdown breach, or by the license agent on revocation.'],
    ['License-Gated Features',
     'Every feature that has commercial value — strategy count, capital ceiling, ML inference, custom strategy development, white-label branding — is gated by claims in the per-tenant JWT. The license check is performed at startup and on every heartbeat refresh; a revoked or expired license triggers a graceful shutdown with a configurable grace period for closing positions. This is not a polite request; it is a hard architectural boundary that cannot be bypassed by configuration changes.'],
  ];

  tenets.forEach(([title, body], i) => {
    children.push(h3(`Tenet ${i+1}: ${title}`));
    children.push(p(body));
  });

  // ════════════════════════════════════════════════════════════════════
  // Chapter 4 — Target Performance Metrics
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 4 — Target Performance Metrics Framework'));
  children.push(p('The target metrics quoted in the project charter — maximum drawdown under five percent, profit factor above two, Sharpe ratio above two, recovery factor above five, risk of ruin under one percent — are not marketing claims. They are measurable, formula-bound quantities that are computed automatically on every backtest run and on every live trading day, and they serve as gate thresholds in the CI/CD pipeline. This chapter defines each metric precisely, specifies the measurement window and calculation method, and explains the acceptance criteria.'));

  children.push(h2('Metric Definitions'));
  children.push(table(
    ['Metric', 'Formula', 'Target', 'Measurement Window', 'Acceptance Gate'],
    [
      ['Max Drawdown (MaxDD)', 'max((peak_t - equity_t) / peak_t)', '< 5%', 'Trailing 90 trading days', 'Hard halt at 3% soft, 5% hard'],
      ['Profit Factor (PF)', 'gross_profit / gross_loss', '> 2.0', 'Trailing 90 trading days', 'CI/CD gate'],
      ['Sharpe Ratio', '(annualized_mean - rf) / annualized_std', '> 2.0', 'Trailing 252 trading days', 'CI/CD gate'],
      ['Recovery Factor', 'net_profit / MaxDD', '> 5.0', 'Trailing 252 trading days', 'CI/CD gate'],
      ['Risk of Ruin (RoR)', 'P(equity hits ruin_threshold) over N paths', '< 1%', '1000 paths × 252 days', 'Hard gate'],
    ],
    [22, 30, 12, 22, 14]
  ));
  children.push(spacer(200));

  children.push(h2('Maximum Drawdown — Detailed Calculation'));
  children.push(p('Maximum drawdown is the largest peak-to-trough decline in the equity curve over the measurement window, expressed as a percentage of the peak. Formally, given an equity series E(t) over the window, MaxDD = max over t of ( max(E(s) for s ≤ t) - E(t) ) / max(E(s) for s ≤ t). It is the most direct measure of capital risk: an investor who deposited capital at the worst possible moment would have experienced this loss. The five percent target is deliberately conservative for an XAUUSD-focused system, where volatility can produce intraday swings of one to two percent; achieving it requires both alpha generation and rigorous risk control.'));
  children.push(p('TITAN XAU AI enforces MaxDD through two circuit breakers: a soft breaker at three percent that throttles new entries and notifies the operator, and a hard breaker at five percent that engages the kill switch, flattens positions, and requires manual operator intervention to re-arm. Both breakers operate on the rolling ninety-day equity curve, computed in real time on every fill.'));

  children.push(h2('Profit Factor — Detailed Calculation'));
  children.push(p('Profit factor is the ratio of gross profit to gross loss over the measurement window. Gross profit is the sum of all positive trade PnL; gross loss is the absolute value of the sum of all negative trade PnL. A profit factor of two means the system earns two dollars for every dollar lost. Values above two are considered institutional-grade; values above three are rare in live trading and usually indicate curve-fitting in backtests. The target of two is calibrated to be ambitious but achievable on XAUUSD with disciplined risk management.'));

  children.push(h2('Sharpe Ratio — Detailed Calculation'));
  children.push(p('The Sharpe ratio measures risk-adjusted return: the excess return over the risk-free rate per unit of volatility. We use the standard annualized form: Sharpe = (mean_daily_return × 252 - risk_free_annual) / (std_daily_return × sqrt(252)). The risk-free rate is the three-month US Treasury bill yield. Daily returns are computed from the close-of-day equity including unrealized PnL. A Sharpe above two is considered excellent; above three is exceptional and typically only seen in high-frequency market making strategies. The target of two on XAUUSD reflects the system\'s design point of medium-frequency trading (a few trades per day) with rigorous volatility scaling.'));

  children.push(h2('Recovery Factor — Detailed Calculation'));
  children.push(p('Recovery factor is net profit divided by maximum drawdown over the same window. It measures how quickly the system recovers from its worst dip: a recovery factor of five means the system earns five times its worst drawdown over the period. This is a useful complement to Sharpe because it is sensitive to the temporal order of returns — a system that doubles then halves has the same Sharpe as one that halves then doubles, but very different recovery factors. The target of five ensures that drawdowns are not just shallow but also quickly recovered.'));

  children.push(h2('Risk of Ruin — Monte Carlo Specification'));
  children.push(p('Risk of ruin is the probability, under Monte Carlo simulation, that the equity curve hits a ruin threshold (defined as a fifty percent drawdown from starting capital) within a 252-trading-day horizon. The simulation generates one thousand randomized return sequences by sampling from the historical trade distribution with replacement, preserving the autocorrelation structure via block bootstrapping. A risk of ruin below one percent is the institutional standard for safe systematic strategies; we adopt it as a hard gate. Builds that exceed one percent risk of ruin on the out-of-sample window are rejected by CI/CD and cannot be promoted to canary.'));

  children.push(callout('Gate enforcement: All five metrics are computed automatically by the backtest regression stage of the CI/CD pipeline. A build is promoted to canary only if it satisfies ALL five gates on the out-of-sample window. There is no manual override — the gate is enforced by the pipeline configuration, not by human discretion.'));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 5 — Technology Stack
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 5 — Technology Stack Selection'));
  children.push(p('The choice of a dual-language architecture — C++20 for the latency-critical execution core and Python 3.12 for the intelligence layer — is the single most consequential technology decision in the system. It reflects a fundamental tension in trading system design: the hot path demands microsecond-class latency and deterministic memory behavior that interpreted languages cannot provide, while the research and ML workflow demands rapid iteration, rich libraries, and a productive REPL that compiled languages struggle to offer. The dual-language approach resolves the tension by accepting the complexity of a language boundary in exchange for getting the best of both worlds.'));

  children.push(h2('C++ Execution Core — Responsibilities'));
  children.push(p('The C++ core handles everything on the tick-to-trade hot path: MT5 broker communication, tick normalization, feature computation that must happen on every tick (microstructure features, technical indicators with tight latency budgets), the pre-trade risk gate, order management, and fill tracking. The design target is a warm-path p99 latency under five milliseconds from broker callback to order submission, with p99.9 under twenty-five milliseconds. Achieving this requires manual memory management (no garbage collection pauses), CPU pinning via systemd, lock-free queues between threads, and zero-copy serialization via FlatBuffers.'));
  children.push(p('The C++ build uses CMake with conan for dependency management. The toolchain is GCC 13 with C++20 enabled, LTO enabled in release builds, and Profile-Guided Optimization (PGO) applied to the hot path. Symbol visibility is controlled via export macros; the public API exposes only stable interfaces, with internal symbols stripped from release builds both for performance and to raise the barrier to reverse engineering.'));

  children.push(h2('Python Intelligence Layer — Responsibilities'));
  children.push(p('The Python layer handles everything off the hot path: feature engineering on aggregated bars (where ten-millisecond latency is acceptable), signal generation, ML model training and inference, strategy orchestration, backtest execution, and research workflows. Python 3.12 is chosen for its significant performance improvements over 3.11, particularly in asyncio and the GIL-aware subsystems. The runtime is uvloop for the event loop (significantly faster than the default asyncio loop), with PyTorch for ML inference, NumPy and pandas for numerical work, and numba for just-in-time compilation of hot Python paths.'));
  children.push(p('Python code is packaged with pyproject.toml and built with uv for fast, reproducible dependency resolution. Sensitive modules — the license validation, the model inference shims, the strategy parameter decryption — are compiled to native code via Cython and shipped as binary wheels, both for performance and to raise the reverse-engineering barrier. The Python layer communicates with the C++ core via PyO3 bindings, with FlatBuffers as the wire format for zero-copy message passing.'));

  children.push(h2('Language Boundary Map'));
  children.push(table(
    ['Layer', 'C++ Modules', 'Python Modules', 'Bridge'],
    [
      ['L1 Ingest', 'MT5Bridge, FIXAdapter, NewsFeedAdapter, FeedHealthMonitor', '—', '—'],
      ['L2 Normalize', 'TickNormalizer, SessionCalendar, FXConverter, BarAggregator', '—', '—'],
      ['L3 Intelligence', 'MicrostructureFeatureEngine (per-tick)', 'FeatureEngine (per-bar), SignalEngine, MLInferenceEngine, StrategyCoordinator, RegimeDetector', 'PyO3 + FlatBuffers'],
      ['L4 Risk', 'PreTradeRiskGate, PostTradeRiskMonitor, ExposureAggregator, KillSwitch', 'RiskConfigLoader', 'PyO3 (config only)'],
      ['L5 Execution', 'OrderManager, SmartRouter, FillTracker, SlippageModel, OrderReconciler', '—', '—'],
      ['L6 Ops', 'MetricsSink, Logger', 'TradeLogger, AuditStore, LicenseService, StateReplicator, OperatorAlertGateway', 'PyO3 + gRPC'],
    ],
    [14, 30, 36, 20]
  ));
  children.push(spacer(200));

  children.push(h2('Key Library Choices'));
  children.push(table(
    ['Domain', 'C++ Library', 'Python Library', 'Rationale'],
    [
      ['Async I/O', 'Boost.Asio', 'asyncio + uvloop', 'Industry standard; uvloop is 2-4x faster than default asyncio'],
      ['Messaging', 'ZeroMQ (cppzmq)', 'pyzmq', 'Low-latency pub/sub; same wire format both sides'],
      ['Serialization', 'FlatBuffers', 'flatbuffers', 'Zero-copy, schema-driven, language-agnostic'],
      ['Logging', 'spdlog', 'structlog', 'Async, structured, JSON output for Loki'],
      ['Concurrency', 'moodycamel::ConcurrentQueue', '—', 'Lock-free SPSC queues for hot path'],
      ['Numerical', 'Eigen', 'NumPy + numba', 'Eigen for C++ linear algebra; NumPy for vectorized Python'],
      ['ML', 'LibTorch (C++ PyTorch)', 'PyTorch', 'Same model format; C++ for hot inference, Python for training'],
      ['Config', 'toml++', 'pydantic + tomli', 'Type-safe config; pydantic for validation'],
      ['Testing', 'GoogleTest + gmock', 'pytest + hypothesis', 'Property-based testing for quant logic'],
      ['HTTP/gRPC', '—', 'fastapi + grpcio', 'Operator console API; license server client'],
      ['Crypto', 'OpenSSL (libcrypto)', 'cryptography (pyca)', 'RSA-JWT for licensing; TLS for transport'],
    ],
    [14, 22, 22, 42]
  ));
  children.push(spacer(200));

  children.push(h2('Why Not Pure Python?'));
  children.push(p('A common question is why not implement the entire system in Python with asyncio, given the productivity advantages. The answer is latency. CPython has a Global Interpreter Lock that serializes bytecode execution; even with asyncio, any CPU-bound work blocks the event loop. The Python interpreter itself adds overhead on every operation: a simple attribute access is tens of nanoseconds, a function call is hundreds. In a hot path that must process thousands of ticks per second with sub-millisecond risk gates, these overheads compound. Empirically, a pure-Python implementation of the TITAN hot path achieves a p99 latency of around thirty milliseconds — six times the budget. The C++ core achieves 4.8 milliseconds p99 on the same hardware.'));

  children.push(h2('Why Not Pure C++?'));
  children.push(p('The mirror question is why not implement everything in C++ for maximum performance. The answer is developer productivity and ecosystem. The Python data science ecosystem — NumPy, pandas, PyTorch, scikit-learn, matplotlib — is dramatically richer than anything available in C++. Strategy research is fundamentally an exploratory activity requiring rapid iteration on hypotheses, and a Jupyter notebook with pandas is roughly an order of magnitude more productive than a C++ compile-run-inspect cycle. The intelligence layer runs off the hot path with latency budgets in the tens of milliseconds; Python is more than fast enough for that, and the productivity multiplier is decisive.'));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 6 — Deliverable 1: Folder Structure (with diagram)
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 6 — Deliverable 1: Complete Folder Structure'));
  children.push(p('The repository layout is the first concrete artifact of the architecture. It encodes the module boundaries, the language split, the deployment story, and the operational tooling in a single tree that any engineer can navigate. The structure follows three principles: separation by language (C++ and Python live in distinct subtrees), separation by concern (source, tests, configs, deploy, docs are all top-level), and convention over configuration (well-known paths for well-known things, so tooling can be written once and reused).'));
  children.push(p('The C++ source tree lives under src/ with public headers mirrored under include/, following the standard CMake convention. Each layer has its own subdirectory (core/, market_data/, bridge/, risk/, execution/, ffi/), and within each layer the files are organized by service. The Python tree mirrors this structure under python/ with subdirectories for strategy, features, signal, ml, backtest, and research. The FFI boundary — the PyO3 bindings and FlatBuffer schemas — lives in src/ffi/ and is the single point of contact between the two languages.'));
  children.push(diagram('d01_folder_structure.png', 6.5));
  children.push(caption('Figure 6.1 — Complete repository folder structure with per-directory annotations.'));

  children.push(h2('Key Directory Responsibilities'));
  children.push(table(
    ['Path', 'Responsibility', 'Approximate LOC'],
    [
      ['src/core/', 'Event loop, lock-free queues, time service, CPU affinity', '4,500'],
      ['src/market_data/', 'Tick ingestion, normalization, bar aggregation, session calendar', '3,200'],
      ['src/bridge/', 'Broker abstraction: MT5, FIX, IB adapters', '5,800'],
      ['src/risk/', 'Pre-trade gate, post-trade monitor, exposure aggregator, kill switch', '6,400'],
      ['src/execution/', 'Order manager, smart router, fill tracker, slippage model', '5,100'],
      ['src/ffi/', 'PyO3 bindings, FlatBuffer schema compilation', '1,800'],
      ['python/strategy/', 'Strategy base class, coordinator, concrete strategies', '4,200'],
      ['python/features/', 'Feature engine, TA features, microstructure features', '6,800'],
      ['python/signal/', 'Signal engine, ensemble combiner, signal filter', '2,400'],
      ['python/ml/', 'Inference engine, model registry, training pipeline, walk-forward', '5,500'],
      ['python/backtest/', 'Replay engine, simulated executor, metrics calculator, Monte Carlo', '4,100'],
      ['configs/', 'YAML configs per environment (dev, staging, production)', '1,200'],
      ['deploy/', 'Dockerfiles, k8s manifests, Terraform, Ansible playbooks', '2,800'],
      ['tests/', 'Unit, integration, component, backtest, chaos test suites', '14,500'],
      ['monitoring/', 'Grafana dashboards, Prometheus rules, Loki config, alert templates', '1,800'],
    ],
    [25, 55, 20]
  ));
  children.push(spacer(200));

  children.push(h2('Build & Dependency Management'));
  children.push(p('The C++ build is orchestrated by CMake 3.27+ with conan 2.x for dependency management. A top-level CMakeLists.txt orchestrates the build of all C++ libraries and the titan-core executable, with subdirectory CMakeLists.txt files per layer. Release builds enable LTO and PGO; debug builds enable AddressSanitizer and UndefinedBehaviorSanitizer. The Python build uses pyproject.toml with uv for dependency resolution and Cython for the sensitive modules. Both builds are reproducible: pinned dependency versions, lockfiles in git, and build cache via ccache (C++) and uv cache (Python).'));
  children.push(p('Third-party dependencies are vendored under third_party/ where their license permits (pybind11, moodycamel, flatbuffers) and managed via conan where it does not (Boost, OpenSSL, ZeroMQ). Every dependency is reviewed by the security team before addition, with the review recorded in licenses/third-party-notices.txt. Dependencies with known vulnerabilities are auto-detected by Trivy in CI and block the build until upgraded or formally exception-approved.'));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 7 — Deliverable 2: Service Architecture
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 7 — Deliverable 2: Service Architecture'));
  children.push(p('The service architecture organizes the system into six logical layers, each containing a cohesive set of services with a single responsibility. The layers are stacked such that data flows downward (ingest at the top, persistence at the bottom) and control flows upward (risk veto at L4 overrides strategy at L3). A strict dependency rule — layer N may only depend on layer N-1 or below — is enforced by an architecture linter in CI; cyclic dependencies fail the build. This is the structural guarantee that risk retains veto power over every order regardless of strategy intent.'));
  children.push(diagram('d02_service_architecture.png', 6.5));
  children.push(caption('Figure 7.1 — Six-layer service architecture. C++ services handle sub-millisecond hot path; Python services handle 10ms+ intelligence layer.'));

  children.push(h2('Layer Responsibilities'));

  children.push(h3('L1 — Ingest Layer'));
  children.push(p('The ingest layer is the system\'s boundary with the outside world. It contains all adapters to external feeds: the MT5 bridge that connects to the MetaTrader 5 terminal, the FIX adapter for FIX-protocol brokers (planned for v1.1), the news feed adapter that pulls Bloomberg and Reuters XML feeds, the economic calendar adapter for FOMC, CPI, and NFP events, and a feed health monitor that detects stale-tick conditions. A pcap replayer supports backtest ingest from captured packet traces. All ingest services are C++ for low latency; they push raw events onto the async event bus without any processing.'));

  children.push(h3('L2 — Normalize Layer'));
  children.push(p('The normalize layer transforms heterogeneous feed formats into a single canonical representation. The tick normalizer deduplicates ticks, aligns decimal precision, and tags each tick with its source feed. The session calendar attaches the trading session (Asia, EU, US, rollover) to every event. The FX converter handles cross-rate conversion for multi-currency position reporting. The bar aggregator builds M1, M5, M15, and H1 OHLCV bars from tick streams. The tick buffer is a one-million-tick ring buffer that provides O(1) random access to recent history. The time sync service disciplines the system clock against NTP and, where available, PTP hardware clocks.'));

  children.push(h3('L3 — Intelligence Layer'));
  children.push(p('The intelligence layer is where alpha is generated. It is the only layer implemented in Python (with selected hot-path components in C++ via the FFI). The feature engine computes over three hundred features spanning technical analysis, microstructure, session behavior, and cross-asset correlations. The signal engine combines features into directional signals using rule-based and ML ensemble methods. The ML inference engine runs PyTorch models via ONNX runtime for sub-millisecond inference. The strategy coordinator arbitrates between multiple strategies, allocating risk budget and resolving conflicts. The regime detector classifies the current market regime (trending, mean-reverting, choppy, news-driven) using a hidden Markov model, allowing strategies to adapt their behavior. The news sentiment engine applies NLP to Federal Reserve communications and geopolitical news.'));

  children.push(h3('L4 — Risk Layer'));
  children.push(p('The risk layer is the structural enforcement of the capital-preservation-first principle. It contains the pre-trade risk gate (synchronous veto on every order), the post-trade risk monitor (asynchronous observer that fires circuit breakers), the exposure aggregator (net and gross exposure in real time), the margin monitor (free margin floor at thirty percent), the kill switch controller (halt, flatten, cancel in under five hundred milliseconds), and the circuit breaker (three percent soft drawdown, five percent hard drawdown). All risk services are C++ for predictable latency and run on dedicated CPU cores to avoid contention.'));

  children.push(h3('L5 — Execution Layer'));
  children.push(p('The execution layer manages the order lifecycle from signal to fill. The order manager owns the order state machine (NEW → SENT → PARTIAL → FILLED / CANCELED / REJECTED). The smart router selects order type (market, limit, stop) and venue based on signal characteristics and current market conditions. The fill tracker handles partial fills and computes realized slippage. The slippage model estimates expected slippage for size-aware order routing. The order reconciler periodically compares local state with broker state to detect orphans (local thinks order exists, broker does not) and phantoms (broker thinks order exists, local does not). The execution auditor records every order event for trade cost analysis and compliance.'));

  children.push(h3('L6 — Persistence & Operations Layer'));
  children.push(p('The persistence layer is the system\'s memory and voice. The trade logger writes every fill to an append-only write-once-read-many (WORM) store for compliance. The metrics exporter emits Prometheus metrics and OpenTelemetry traces. The audit store maintains a hash-chained log of every operator action, risk decision, and order event — tamper-evident by construction. The license service validates the per-tenant JWT and enforces feature gates. The state replicator syncs hot state to the standby VPS. The operator alert gateway routes alerts to PagerDuty, Telegram, and the operator console.'));

  children.push(h2('Service Responsibility Matrix'));
  children.push(table(
    ['Service', 'Layer', 'Language', 'CPU Pin', 'p99 Latency Target', 'Failure Mode'],
    [
      ['MT5Bridge', 'L1', 'C++', '0-1', '0.5 ms', 'Broker disconnect → failover to Z2'],
      ['TickNormalizer', 'L2', 'C++', '2', '0.1 ms', 'Pass-through raw ticks'],
      ['FeatureEngine', 'L3', 'Python+C++', '4-7', '1.0 ms', 'Cache last-known features'],
      ['SignalEngine', 'L3', 'Python', '4-7', '0.5 ms', 'Withhold signal'],
      ['PreTradeRiskGate', 'L4', 'C++', '3', '0.3 ms', 'Reject by default'],
      ['KillSwitchController', 'L4', 'C++', '3', '0.5 ms', 'Fail-safe (always armed)'],
      ['OrderManager', 'L5', 'C++', '2', '0.3 ms', 'Reject new orders'],
      ['TradeLogger', 'L6', 'Python', '9', 'async', 'Buffer to disk'],
      ['LicenseService', 'L6', 'Python', '9', 'async', 'Grace period then halt'],
    ],
    [22, 8, 14, 10, 22, 24]
  ));
  children.push(spacer(200));

  children.push(h2('Data Plane vs Control Plane Separation'));
  children.push(p('The architecture separates the data plane (the hot path that processes ticks and places orders) from the control plane (configuration, monitoring, operator actions). The two planes use distinct network paths, distinct CPU allocations, and distinct failure modes. A control-plane outage — Prometheus down, Grafana unreachable, operator console offline — does not affect trading. A data-plane outage does not prevent the operator from engaging the kill switch, which has its own dedicated channel. This separation is essential for the reliability target of 99.95% uptime.'));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 8 — Deliverable 3: Data Flow Diagrams
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 8 — Deliverable 3: Data Flow Diagrams'));
  children.push(p('Three data flow diagrams at increasing levels of detail document how information moves through the system. The Level-0 context diagram shows the system as a single bubble exchanging flows with external entities. The Level-1 diagram decomposes this bubble into seven internal processes and five data stores, with labeled flows between them. The tick-to-trade latency flow annotates the warm path with millisecond budgets per stage, providing the basis for the latency budget chapter that follows.'));
  children.push(diagram('d03_data_flow.png', 6.5));
  children.push(caption('Figure 8.1 — Three DFD levels: (a) context, (b) internal processes with data stores, (c) tick-to-trade latency flow with ms budgets.'));

  children.push(h2('Context Diagram — External Entities'));
  children.push(p('The system exchanges seven labeled flows with four external entities. The MT5 broker is the primary execution venue: ticks and fill confirmations flow in (F1), orders flow out (F2). The news and economic feed provides scheduled event data and real-time news sentiment (F3) used by the news-aware risk gate and the news sentiment engine. The license server is the source of truth for tenant entitlements: heartbeats flow out (F4), signed JWTs flow back (F5). The operator console is the human interface: alerts and metrics flow out (F6), kill switch and risk override commands flow in (F7). All flows except F1 and F2 are TLS-encrypted and authenticated; F1 and F2 use the MT5 terminal\'s internal protocol which is broker-managed.'));

  children.push(h2('Level-1 Diagram — Internal Processes'));
  children.push(p('The seven internal processes correspond to the service layers (with execution and risk collapsed into single processes for diagram clarity). Each process has well-defined inputs and outputs, and the data stores (D1-D5) provide the persistence boundary. The critical property to notice is that P5 (Risk) is a synchronous gate on the path from P4 (Signal) to P6 (Execute) — no order can reach the broker without passing through the risk process. This is the structural enforcement of the capital-preservation-first tenet.'));
  children.push(table(
    ['Process', 'Inputs', 'Outputs', 'Data Stores Touched', 'Sync/Async'],
    [
      ['P1 Ingest', 'F1, F3 (external feeds)', 'raw ticks → P2, → D1', 'D1 (write)', 'Async push'],
      ['P2 Normalize', 'raw ticks from P1', 'norm ticks → P3, → D1', 'D1 (write)', 'Async push'],
      ['P3 Feature', 'norm ticks from P2', 'features → P4, → D2', 'D2 (write)', 'Async push'],
      ['P4 Signal', 'features from P3', 'signal → P5', '—', 'Async push'],
      ['P5 Risk', 'signal from P4, exposure from D3', 'approved/rejected → P6', 'D3 (read), D4 (read)', 'SYNCHRONOUS'],
      ['P6 Execute', 'approved order from P5', 'order to broker, fills → P7', 'D3 (write)', 'Synchronous'],
      ['P7 Persist', 'fills from P6', 'trade + audit records', 'D4 (write), D5 (write)', 'Async'],
    ],
    [14, 24, 24, 24, 14]
  ));
  children.push(spacer(200));

  children.push(h2('Tick-to-Trade Latency Flow'));
  children.push(p('The warm-path latency flow shows the millisecond budget for each stage of the hot path. The total internal latency (excluding the broker round-trip) is 1.70 ms at p50, 4.80 ms at p99, and 12.0 ms at p99.9. The system is designed to a p99 budget of five milliseconds; the p99.9 budget is exceeded, which is acceptable as long as it is not sustained. A spike detector monitors the p99.9 latency over a ten-second sliding window; if it exceeds twenty-five milliseconds for the full window, the system automatically throttles non-critical feature computation and pages the operator.'));
  children.push(p('The largest budget consumers are the MT5 callback (0.30 ms, broker-side overhead we cannot control), the FeatureEngine (0.40 ms, the price of computing three hundred features per tick), and the MT5 send (0.50 ms, the cost of submitting an order through the MT5 terminal API). The risk gate is comparatively cheap at 0.15 ms because it performs only O(1) checks against pre-computed exposure. Strategies for reducing latency further are discussed in the Latency Budget chapter.'));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 9 — Deliverable 4: Module Dependencies
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 9 — Deliverable 4: Module Dependency Graph'));
  children.push(p('The module dependency graph is the structural contract of the architecture. It shows which modules import or call which, organized by layer. The graph is acyclic by construction — cyclic dependencies fail the build — and downward-only — modules at layer N may only depend on modules at layer N-1 or below. This is the formal expression of the layering rule that gives risk its structural veto power.'));
  children.push(diagram('d04_module_deps.png', 6.5));
  children.push(caption('Figure 9.1 — Module dependency graph. Solid arrows are data-plane dependencies; dashed are observability/audit.'));

  children.push(h2('Critical Edges & Their Rationale'));
  children.push(p('Several dependency edges are worth highlighting because they encode critical architectural guarantees. The PreTradeRiskGate depends on the ExposureAggregator and the SessionCalendar (for news blackout), but NOT on the StrategyCoordinator — risk has no knowledge of which strategy generated the signal it is evaluating. This independence is what makes the risk veto trustworthy: there is no code path by which a strategy can influence the risk decision. The KillSwitchController depends on the OrderManager via a dedicated reverse signal bus, not the main event bus — this guarantees that the kill switch can reach the order manager even if the main bus is saturated or stuck.'));
  children.push(p('The StrategyCoordinator depends on SignalEngine, RegimeDetector, and MLInferenceEngine, and is consumed by the PreTradeRiskGate. This means the strategy layer is the single point at which signals are converted into actionable orders, making it the natural place for risk budget allocation, strategy arbitration, and conflict resolution. The audit store is a terminal sink — nothing depends on it — which means it can never block the hot path; if the audit store is slow, audit events queue in memory and flush when the store catches up.'));

  children.push(h2('Module Inventory'));
  children.push(table(
    ['Module', 'Layer', 'Imports', 'Imported By', 'Purpose'],
    [
      ['EventBus', 'L0', '—', 'most L1+ modules', 'Async pub/sub backbone'],
      ['MT5Bridge', 'L1', 'EventBus, FlatBufferCodec', 'TickNormalizer, FillTracker', 'Broker connection'],
      ['TickNormalizer', 'L2', 'EventBus, MT5Bridge', 'FeatureEngine, BarAggregator', 'Canonical tick form'],
      ['FeatureEngine', 'L3', 'TickNormalizer, BarAggregator, MLInferenceEngine', 'SignalEngine', '300+ features per bar'],
      ['SignalEngine', 'L3', 'FeatureEngine', 'StrategyCoordinator', 'Directional signal generation'],
      ['StrategyCoordinator', 'L3', 'SignalEngine, RegimeDetector', 'PreTradeRiskGate', 'Strategy arbitration'],
      ['PreTradeRiskGate', 'L4', 'ExposureAggregator, SessionCalendar', 'OrderManager', 'SYNCHRONOUS veto'],
      ['KillSwitchController', 'L4', 'OrderManager (reverse bus)', 'Operator console only', 'Halt + flatten + cancel'],
      ['OrderManager', 'L5', 'PreTradeRiskGate, SmartRouter, FillTracker', 'TradeLogger, MetricsExporter', 'Order state machine'],
      ['AuditStore', 'L6', 'Logger, FlatBufferCodec', '(terminal sink)', 'Immutable, hash-chained log'],
    ],
    [20, 8, 24, 22, 26]
  ));
  children.push(spacer(200));

  children.push(h2('Layering Rule Enforcement'));
  children.push(p('The layering rule is enforced automatically by an architecture linter that runs in CI. The linter parses CMakeLists.txt and Python import statements, builds the dependency graph, and rejects any commit that introduces a cyclic dependency or an upward dependency (a layer N module importing a layer N+1 module). The linter is configured in ci/arch_lint.py and is part of the mandatory Gate 1 in the CI pipeline. Exceptions require an ADR and CTO approval; in practice no exception has been granted in the v1.0 cycle.'));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 10 — Deliverable 5: Class Diagrams
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 10 — Deliverable 5: Class Diagrams (UML)'));
  children.push(p('Three UML class diagrams document the core domain model, the risk subsystem, and the execution subsystem. The diagrams use standard UML 2.5 notation: solid arrows with hollow triangle heads for inheritance, solid arrows with filled diamond heads for composition, solid arrows with hollow diamond heads for aggregation, and dashed arrows for dependency. Visibility is denoted + (public), - (private), # (protected). Abstract classes are marked with the «abstract» stereotype; interfaces with «interface».'));
  children.push(diagram('d05_class_diagrams.png', 6.5));
  children.push(caption('Figure 10.1 — Three UML class diagrams: (a) core domain model, (b) risk subsystem, (c) execution subsystem.'));

  children.push(h2('Core Domain Model'));
  children.push(p('The core domain model captures the fundamental value objects and aggregates of the trading system. Tick is an immutable value object representing a single market quote: timestamp, symbol, bid, ask, last, and volume. Bar aggregates ticks into OHLCV bars over a configurable timeframe. Order is an abstract base class with three concrete subclasses: MarketOrder (immediate execution at best available price), LimitOrder (execution at a specified price or better), and StopOrder (triggered when the market reaches a stop price). Fill is an immutable event recording the execution of (part of) an order, carrying the fill price, quantity, commission, and realized PnL. Position is an aggregate root tracking the net quantity, average price, unrealized and realized PnL, and maximum adverse excursion for one symbol. Signal is the output of a strategy: a direction, a strength, a suggested quantity, and optional stop and target prices. StrategyContext is the per-strategy sandbox providing features, current position, clock, and risk budget, and the only legal channel for a strategy to emit signals.'));

  children.push(h2('Risk Subsystem'));
  children.push(p('The risk subsystem is organized around the IRiskGate interface, which defines the synchronous veto contract: every gate must implement check(ctx: RiskContext): RiskDecision. Two concrete implementations exist: PreTradeRiskGate runs synchronously on every order, checking position size, leverage, daily trade count, news blackout windows, and margin floor. PostTradeRiskMonitor runs asynchronously, observing fills and equity updates and firing circuit breakers when drawdown, loss streak, or slippage thresholds are breached. The ExposureAggregator maintains net and gross exposure in real time, with Value-at-Risk and correlation-adjusted exposure calculations available on demand. The KillSwitchController is a singleton that holds an atomic armed flag, a triggered timestamp, and a reason string; engaging it halts new orders, flattens positions, cancels pending orders, and notifies the operator. The RiskDecision value object carries the verdict (APPROVE, REJECT, THROTTLE), a reason code, a human-readable message, an optional reduced quantity (for THROTTLE), and a serializable audit blob.'));

  children.push(h2('Execution Subsystem'));
  children.push(p('The execution subsystem is organized around the IExecutor interface, which abstracts the broker: submit(o: Order): FillPromise, cancel(id: OrderId): bool, modify(id: OrderId, m: Mod): bool. Three concrete implementations exist: MT5Executor (production, binding to the MetaTrader 5 terminal via Wine), SimulatedExecutor (backtest, with injectable slippage, commission, and latency), and FIXExecutor (planned for v1.1, speaking FIX 4.4 to direct-access brokers). The OrderRouter selects a venue per order and handles failover across the configured chain. The OrderManager is the aggregate root owning the order state machine, the router, the risk gate, and the fill reconciler. The FillReconciler periodically compares local order state against broker snapshots to detect orphans and phantoms. The ISlippageModel interface has four implementations: LinearSlippageModel (constant bps), SquareRootImpactModel (Almgren-Chriss square root), AlmgrenChrissModel (full optimal execution), and LearnedSlippageModel (ML-trained on historical fills).'));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 11 — Deliverable 6: Deployment
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 11 — Deliverable 6: Deployment Architecture'));
  children.push(p('The deployment architecture is a three-zone high-availability topology designed for 99.95% uptime with sub-fifteen-minute mean time to recovery. The primary zone (Z1) runs in NY4 (Equinix New York), colocated with the broker matching engines for minimum network latency. The hot-standby zone (Z2) runs in EQ4 (Equinix NY2), a different physical facility in the same metropolitan area for low-latency replication with physical fault isolation. The disaster-recovery zone (Z3) runs in LD4 (Equinix London), geographically remote to survive metro-wide disasters, accepting higher replication latency in exchange for true geographic redundancy.'));
  children.push(diagram('d06_deployment.png', 6.5));
  children.push(caption('Figure 11.1 — Three-zone deployment topology. Z1 active, Z2 hot-standby (<3s failover), Z3 cold-DR (<15min RTO).'));

  children.push(h2('Zone Roles & Failover'));
  children.push(h3('Z1 — Primary (NY4)'));
  children.push(p('The primary zone is the active trading cluster. All services run hot: titan-core on CPU 2-3, titan-strategy on CPU 4-7, mt5-terminal on CPU 0-1, redis on CPU 8, TimescaleDB and the monitoring stack on CPU 9-11. The VRRP master priority is 200, making Z1 the default gateway for inbound broker connections. The public IP is allowlisted with the broker; only MT5 broker traffic and WireGuard (port 51820) are accepted by nftables. State is replicated synchronously to Z2 via Redis Sentinel and TimescaleDB streaming replication; the warm standby in Z2 is never more than one second behind.'));
  children.push(h3('Z2 — Hot-Standby (EQ4)'));
  children.push(p('The hot-standby zone mirrors Z1 but with services in a warm state — titan-core and titan-strategy are running but not actively trading, ready to take over within three seconds. The VRRP backup priority is 100. On Z1 failure (detected via VRRP health probes and application-level liveness checks), Z2 promotes to master, takes over the VRRP virtual IP, and begins trading. The MT5 terminal in Z2 uses a separate sub-account configured with the broker for failover, avoiding position conflicts. State is loaded from Redis (already replicated) within milliseconds of promotion.'));
  children.push(h3('Z3 — Disaster Recovery (LD4)'));
  children.push(p('The DR zone is geographically remote, accepting seventy-millisecond replication latency in exchange for true geographic redundancy. Z3 runs a cold-standby image: titan-core is paused, TimescaleDB is replaying WAL archives with sixty-second lag, Redis is an asynchronous replica with five-second lag. VRRP is disabled in Z3 — failover to Z3 is a manual decision taken only when both Z1 and Z2 are unavailable. The Recovery Time Objective (RTO) for Z3 is fifteen minutes (the time to confirm the disaster, manually failover, and resume trading); the Recovery Point Objective (RPO) is sixty seconds (the maximum data loss from WAL lag).'));

  children.push(h2('Bill of Materials'));
  children.push(table(
    ['Zone', 'Location', 'Hardware', 'Monthly Cost', 'Purpose'],
    [
      ['Z1 Primary', 'NY4 Equinix', 'Dedicated Ryzen 9 3900X, 12c/32GB, 2×1TB NVMe', '$280', 'Active trading'],
      ['Z2 Hot-Standby', 'EQ4 Equinix', 'Dedicated Ryzen 7 3700X, 8c/32GB, 1TB NVMe', '$180', '<3s failover'],
      ['Z3 DR', 'LD4 Equinix', 'Hetzner CX41 VPS, 8vCPU/16GB, 160GB SSD', '$45', '<15min RTO'],
      ['License SaaS', 'AWS eu-west-1', 't3.medium, 2vCPU/4GB, 50GB', '$30', 'JWT issuance'],
      ['Backup S3', 'AWS eu-west-1', 'S3 IA, 500GB', '$15', 'WAL archive, snapshots'],
      ['Total (single tenant)', '—', '—', '~$550', '—'],
      ['Per additional tenant', '—', '+$0 (shared infra)', '+$80', 'Marginal cost'],
    ],
    [14, 14, 38, 16, 18]
  ));
  children.push(spacer(200));

  children.push(h2('Network Architecture'));
  children.push(p('All inter-zone communication flows over a WireGuard full mesh, with pre-shared keys rotated every thirty days via Vault. The WireGuard tunnels carry Redis replication, TimescaleDB streaming, state sync, and operator console traffic. Broker connections (MT5, FIX) use direct internet paths with nftables restricting source IPs to the broker\'s published ranges. The monitoring stack (Prometheus, Loki, Grafana) is federated: Z2 scrapes Z1, Z3 scrapes Z1 and Z2 asynchronously, providing a complete view from any zone even during a partial outage.'));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 12 — Deliverable 7: VPS Architecture
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 12 — Deliverable 7: VPS Architecture'));
  children.push(p('The VPS architecture is the single-host deep dive: how the operating system, kernel, container runtime, and processes are configured on the primary trading host (Z1). The goal is to extract predictable, low-latency behavior from commodity hardware by eliminating sources of jitter: kernel preemption, memory allocation stalls, network interrupt storms, and CPU frequency scaling. The configuration is captured as code (Ansible playbooks, systemd unit files, sysctl profiles) so that it can be reproduced identically across Z1, Z2, and any future primary host.'));
  children.push(diagram('d07_vps.png', 6.5));
  children.push(caption('Figure 12.1 — Single-VPS architecture: hardware, OS, runtime, and CPU allocation map with kernel/sysctl tuning table.'));

  children.push(h2('CPU Allocation Strategy'));
  children.push(p('The host has twelve physical cores split across two NUMA nodes. The allocation strategy pins latency-critical services to dedicated cores with hyper-threading disabled, isolates those cores from kernel scheduling, and confines all other workloads to the remaining cores. The mt5-terminal container runs on CPU 0-1 with SMT disabled (to avoid contention between the two hyperthreads), handling the Wine overhead and broker callback latency. The titan-core container runs on CPU 2-3, isolated from kernel scheduling via the isolcpus kernel parameter, with NO_HZ_FULL to eliminate timer ticks. The titan-strategy container runs on CPU 4-7 (four cores), providing headroom for Python GIL contention and PyTorch inference. Redis runs on CPU 8, and the monitoring stack (Prometheus, Loki, Grafana) runs on CPU 9-11.'));
  children.push(p('CPU isolation is achieved through a combination of kernel parameters (isolcpus=2,3 nohz_full=2,3 rcu_nocbs=2,3) and systemd unit directives (CPUAffinity=2,3 AllowedCPUs=2,3). The kernel\'s RCUs are offloaded to other CPUs via rcu_nocbs, eliminating RCU callback stalls on the isolated cores. Timer ticks are eliminated via nohz_full, which is essential for sub-millisecond latency predictability. The result is that CPU 2-3 experience less than one kernel preemption per second under load, compared to thousands per second on a default-configured kernel.'));

  children.push(h2('Kernel & sysctl Tuning'));
  children.push(p('The kernel is Ubuntu 22.04 LTS with the PREEMPT_RT patch applied for full kernel preemption. The kernel command line includes parameters for CPU isolation, hugepages, C-state control, and watchdog disabling. The sysctl profile disables swap, caps dirty pages to prevent write stalls, enlarges network buffers to absorb tick bursts, and disables NUMA auto-balancing in favor of manual cpuset control. The most consequential entries are vm.swappiness=1 (effectively disable swap), kernel.sched_rt_runtime_us=-1 (allow RT tasks to run beyond the 95% default window), and net.core.rmem_max=134217728 (128MB socket recv buffer to absorb tick bursts). The complete sysctl table is shown in Figure 12.1.'));

  children.push(h2('Memory & Storage'));
  children.push(p('The host has 32 GB of DDR4 RAM split evenly across two NUMA nodes (16 GB per node). Four gigabytes are reserved as 2MB hugepages (2048 pages), used by titan-core for lock-free queues and ring buffers to eliminate page-fault overhead. Swap is effectively disabled (vm.swappiness=1) — the OOM killer is preferred over swap-stall, because a stalled trading process is far more dangerous than a killed one. The OOM-killer configuration pins titan-core as the lowest-priority kill target, so monitoring and logging are killed first under memory pressure. Storage is two 1 TB NVMe drives in RAID1, formatted XFS with noatime and allocsize=64M for the tick store. The I/O scheduler is set to none for NVMe (the device has its own queue management), and direct I/O is used for the tick ring buffer to bypass the page cache.'));

  children.push(h2('systemd Unit Configuration'));
  children.push(p('Each TITAN service runs as a systemd unit with explicit CPU affinity, NUMA policy, memory limits, I/O priority, and security hardening. The titan-core unit specifies CPUAffinity=2,3, NUMAPolicy=bind with NUMAMask=0, Nice=-11, IOSchedulingClass=realtime, and memory limits of 4 GB high / 6 GB max. Security hardening includes NoNewPrivileges, ProtectSystem=strict, ProtectHome, PrivateTmp, and ReadWritePaths restricted to /var/lib/titan and /var/log/titan. The full unit file is reproduced in Figure 12.1.'));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 13 — Deliverable 8: Production
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 13 — Deliverable 8: Production Architecture'));
  children.push(p('The production architecture documents the end-to-end operating loop: how code moves from developer laptop through CI/CD to canary deployment to full production, how the system is observed in production, how operators interact with it, and how the daily, weekly, monthly, and quarterly operational rhythms are structured. This is the architecture of running the system, not just building it.'));
  children.push(diagram('d08_production.png', 6.5));
  children.push(caption('Figure 13.1 — Production architecture: trading cluster, CI/CD pipeline with backtest regression gate, operator console, and 24h operating cycle.'));

  children.push(h2('CI/CD Pipeline'));
  children.push(p('The CI/CD pipeline is built on GitLab CI with ArgoCD for deployment orchestration. Every pull request runs through five gates: (1) static analysis and unit tests (clang-tidy, pylint, mypy, pytest, GoogleTest), (2) integration tests with Pact contracts, (3) component tests with testcontainers, (4) the mandatory backtest regression gate, and (5) image build and signing with cosign. Only builds that pass all five gates are promoted to the canary stage, where Argo Rollouts deploys the new version to ten percent of traffic for thirty minutes, then fifty percent for one hour, then one hundred percent. Automatic rollback triggers if latency p99 increases by more than fifty percent or any risk gate breaches during the canary window.'));
  children.push(p('The backtest regression gate is the most consequential control. It runs a twenty-four month walk-forward backtest with the last twenty percent as out-of-sample, plus a thousand-path Monte Carlo simulation. The build must beat the previous build on all five target metrics (PF, Sharpe, MaxDD, Recovery, RoR) on the out-of-sample window. This prevents gradual metric decay across releases: a build that improves Sharpe but worsens MaxDD is rejected, forcing the team to find solutions that improve all dimensions simultaneously. The gate is enforced by the pipeline configuration, not by human discretion — there is no override.'));

  children.push(h2('Observability Stack'));
  children.push(p('Observability is built in from day one and is non-negotiable. Every service emits Prometheus metrics (scraped every fifteen seconds, five-day retention on the local instance, federated to Z2 and Z3), structured JSON logs (collected by Promtail and stored in Loki with one-year retention on S3 backend), and OpenTelemetry traces (sampled at one percent in production, one hundred percent in canary, with tick-to-trade spans for latency analysis). Grafana provides the unified dashboard view, with separate panels for traders (real-time PnL, exposure, open positions), supervisors (risk metrics, gate rejection rates, audit log search), and SREs (latency percentiles, error rates, resource utilization). AlertManager routes alerts to PagerDuty for P1/P2 incidents and to Telegram for P3 informational alerts.'));

  children.push(h2('Operator Actions & Authorization'));
  children.push(p('Operator actions are categorized by impact and require different authorization levels. High-impact actions — engaging the kill switch, overriding risk limits, activating a new strategy — require the two-person rule: a TRADER initiates and a SUPERVISOR approves within five minutes or the action expires. All actions are recorded in the immutable audit store with operator identity, timestamp, before/after state, and reason code. Manual order placement is disabled in production; all orders must flow through the risk gate. The complete authorization matrix is shown in Figure 13.1.'));

  children.push(h2('24-Hour Operating Cycle'));
  children.push(p('The system trades XAUUSD around the clock from Sunday 22:00 UTC to Friday 22:00 UTC, with a daily maintenance window during the 22:00-22:05 broker rollover (no new orders). The Asian session (00:00-07:00 UTC) typically has lower volatility and tighter ranges; the European session (07:00-16:00 UTC) is the peak liquidity window; the US session (16:00-22:00 UTC) overlaps with Europe for the first few hours and produces the highest volatility, especially around US economic releases. News blackout windows (FOMC ±15 min, NFP ±10 min, CPI ±5 min, Powell/ECB speeches ±10 min) are automatically enforced by the risk gate. Daily reporting runs at 00:30 UTC, generating the previous day\'s PnL, trade log, slippage TCA, and risk metric snapshot, emailed to the licensee and uploaded to the investor portal.'));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 14 — Deliverable 9: Testing
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 14 — Deliverable 9: Testing Architecture'));
  children.push(p('The testing architecture is a five-layer pyramid with hard gates at each CI/CD stage. The pyramid shape reflects the relative volume of tests: roughly seventy percent unit, twenty percent integration, six percent component, three percent backtest regression, and one percent chaos. Each layer has a distinct purpose, a distinct cost, and a distinct cadence — running all chaos experiments on every PR would be impractical, but running only unit tests on every PR would be irresponsible.'));
  children.push(diagram('d09_testing.png', 6.5));
  children.push(caption('Figure 14.1 — Testing pyramid (5 layers) and CI/CD pipeline gates with thresholds.'));

  children.push(h2('Unit Tests'));
  children.push(p('Unit tests cover pure functions and isolated components with all dependencies mocked. The C++ side uses GoogleTest with gmock; the Python side uses pytest with pytest-asyncio for async code and hypothesis for property-based testing. The target is eighty-five percent line coverage with one hundred percent coverage of critical paths (risk gates, order state machine, PnL calculation). Unit tests must execute in under sixty seconds total; tests that exceed this are candidates for refactoring or promotion to integration. Property-based tests are mandatory for any function with invariants (e.g., "for any tick t, TickNormalizer.normalize(t) is idempotent").'));

  children.push(h2('Integration Tests'));
  children.push(p('Integration tests verify service-to-service contracts using the Pact framework. Each service publishes a contract describing the requests it makes to its dependencies and the responses it expects; dependencies verify that they can satisfy those contracts. This catches breaking API changes early — a producer that changes its response shape will break its consumers\' contracts in CI before reaching production. Integration tests use a real ZeroMQ event bus but a mock broker, allowing end-to-end event flow verification without broker dependencies. The target is one hundred percent coverage of critical paths (signal → risk → order, fill → position → exposure).'));

  children.push(h2('Component Tests'));
  children.push(p('Component tests exercise a single service with its real infrastructure dependencies via testcontainers: Redis, PostgreSQL/TimescaleDB, and MinIO (for S3-compatible audit storage). The broker is still mocked. These tests catch infrastructure integration bugs that mock-based unit tests cannot: serialization issues, schema mismatches, transaction boundary problems. The target is seventy percent line coverage per service in the component test suite. Tests run in parallel across services to keep total wall time under ten minutes.'));

  children.push(h2('Backtest Regression'));
  children.push(p('The backtest regression gate is the most important and most expensive test layer. It runs a full twenty-four month walk-forward backtest with the last twenty percent as out-of-sample, plus a thousand-path Monte Carlo simulation for risk of ruin. The build must beat the previous build on all five target metrics (PF ≥ 2.0, Sharpe ≥ 2.0, MaxDD ≤ 5%, Recovery ≥ 5, RoR ≤ 1%) on the out-of-sample window. The full backtest runs on every PR (approximately thirty minutes wall time) and a smaller smoke backtest (three months, no Monte Carlo) runs nightly on the main branch. Builds that fail the gate cannot be promoted to canary — there is no override.'));

  children.push(h2('Chaos Engineering'));
  children.push(p('Chaos engineering is the top of the pyramid: weekly game-day exercises that inject realistic failures into a production-like staging environment. We use Gremlin for CPU contention, network latency, and packet loss, plus custom fault injectors for broker disconnect, partial fills, slippage spikes, and Z1→Z2 VRRP failover. The goal is not to verify that the system survives (we already believe it does) but to discover failure modes we have not anticipated. Every chaos experiment produces a postmortem regardless of outcome; experiments that reveal bugs feed back into unit and integration tests to prevent regression. Quarterly, a full DR drill exercises the Z1→Z3 failover path with RTO under fifteen minutes as the success criterion.'));

  children.push(h2('Test Matrix'));
  children.push(table(
    ['Test Type', 'Tool', 'Scope', 'Target Coverage', 'Gate Threshold'],
    [
      ['Unit (C++)', 'GoogleTest + gmock', 'Pure functions, parsers, risk formulas', '85% line', '0 critical findings'],
      ['Unit (Python)', 'pytest + hypothesis', 'Strategy logic, feature functions', '85% line', '0 critical findings'],
      ['Integration', 'Pact + pytest', 'Service-to-service contracts (ZMQ bus)', '100% critical paths', '0 contract breaks'],
      ['Component', 'testcontainers', 'Single service with real infra deps', '70% line', 'All scenarios pass'],
      ['Backtest regression', 'Replay engine + Monte Carlo', '24mo walk-forward, OOS last 20%', '5 metrics gate', 'PF≥2.0 · Sharpe≥2.0 · DD≤5% · RoR≤1%'],
      ['Smoke (post-deploy)', 'Custom Python script', 'Paper-trade 5 orders, audit, kill-switch', '5 scenarios', 'All scenarios pass'],
      ['Chaos / fault', 'Gremlin + custom', 'Broker disconnect, partial fills, latency, CPU', '10 experiments', 'No P0 · MTTR < 5min'],
      ['Performance / load', 'locust + C++ bench', '50k ticks/s sustained for 1h', 'p99 latency', 'p99 < 5ms warm · < 25ms p99.9'],
      ['Security', 'Semgrep + Bandit + Trivy + Snyk', 'SAST + container scan + dep vuln', '0 HIGH/CRITICAL', '0 unresolved HIGH+'],
      ['DR drill', 'Manual + automated', 'Z1→Z3 failover, restore from backup', 'RTO < 15min · RPO < 60s', 'Successful restore + trade continuity'],
    ],
    [16, 22, 30, 18, 14]
  ));
  children.push(spacer(200));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 15 — Latency Budget
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 15 — Latency Budget & Performance Engineering'));
  children.push(p('The latency budget is the contract between the system\'s performance aspirations and its physical reality. The warm-path p99 target is five milliseconds from broker callback to order submission, with p99.9 acceptable at twenty-five milliseconds as long as it is not sustained. This chapter breaks down the budget per stage, explains the engineering techniques used to meet it, and describes the mitigation strategies when the budget is breached.'));
  children.push(diagram('d10_latency.png', 6.5));
  children.push(caption('Figure 15.1 — Tick-to-trade latency budget breakdown with p50/p99/p99.9 per stage.'));

  children.push(h2('Per-Stage Budget Breakdown'));
  children.push(p('The warm path consists of seven stages. The MT5 callback (0.30 ms p50) is the time from when the broker sends a tick to when our code receives it in the MT5Bridge; we have limited control over this as it includes broker-side processing and MT5 terminal overhead. The normalizer (0.05 ms) is the cheapest stage, performing O(1) deduplication and decimal alignment via AVX2 SIMD. The FeatureEngine (0.40 ms) is the most expensive internal stage, computing over three hundred features per tick via vectorized NumPy operations and Numba-JIT-compiled hot paths. The SignalEngine (0.20 ms) combines features into a directional signal via ensemble methods, with ML inference via ONNX runtime. The PreTradeRiskGate (0.15 ms) performs O(1) checks against pre-computed exposure using atomic reads. The OrderManager (0.10 ms) translates the approved signal into an order and pushes it onto the SPSC queue to the MT5 send thread. The MT5 send (0.50 ms) is the second-most expensive stage, dominated by Wine overhead in translating the MT5 terminal API call.'));

  children.push(h2('Mitigation Strategies per Stage'));
  children.push(table(
    ['Stage', 'p99 (ms)', 'Budget (ms)', 'Mitigation if Breached'],
    [
      ['MT5 callback', '0.80', '1.00', 'Dedicated thread, increase recv buffer, SMT off'],
      ['Normalizer', '0.10', '0.20', 'AVX2 SIMD, branchless decimal ops'],
      ['FeatureEngine', '1.20', '1.00', 'Cache features, drop non-critical on spike'],
      ['SignalEngine', '0.60', '0.50', 'ONNX runtime, batch inference, no Python'],
      ['PreTradeRiskGate', '0.30', '0.30', 'O(1) lookups, atomic exposure reads'],
      ['OrderManager', '0.20', '0.20', 'SPSC queue, pre-allocated objects'],
      ['MT5 send', '1.50', '1.50', 'Bypass Wine, consider FIX adapter'],
      ['TOTAL internal', '4.80', '5.00', 'Spike detector throttles features on breach'],
    ],
    [26, 16, 20, 38]
  ));
  children.push(spacer(200));

  children.push(h2('Performance Engineering Techniques'));
  children.push(h3('CPU Pinning & Isolation'));
  children.push(p('The titan-core process is pinned to CPU 2-3 via systemd CPUAffinity, with the kernel instructed to never schedule other tasks there via isolcpus=2,3. NO_HZ_FULL eliminates timer ticks on those cores, and rcu_nocbs=2,3 offloads RCU callbacks to other CPUs. The result is that titan-core experiences fewer than one kernel preemption per second, compared to thousands on a default kernel. This is the single most impactful change for latency predictability.'));

  children.push(h3('Lock-Free Queues'));
  children.push(p('Inter-thread communication uses the moodycamel ConcurrentQueue, a lock-free multi-producer multi-consumer queue with bounded latency. The hot path between the MT5 callback thread and the normalizer thread is a single-producer single-consumer (SPSC) queue, which is even cheaper — a single atomic load and store per operation. No mutexes are used anywhere on the hot path; this eliminates the priority inversion and contention jitter that mutex-based designs suffer from under load.'));

  children.push(h3('Zero-Copy Serialization'));
  children.push(p('All inter-process and inter-language messages are serialized with FlatBuffers, which permits zero-copy access to fields without deserialization. This is critical for the Python↔C++ boundary, where messages must cross the PyO3 bridge without copying. The FlatBuffer schema is the authoritative wire format for the entire system; new message types are added by editing the schema in src/ffi/flatbuffers/ and regenerating bindings for both languages.'));

  children.push(h3('GIL Mitigation'));
  children.push(p('The Python GIL is the most common source of latency spikes in Python-based trading systems. TITAN XAU AI mitigates this through several techniques: the hot path runs in C++ (no GIL), the Python intelligence layer uses uvloop for the event loop (which releases the GIL during I/O), and CPU-bound Python work is moved to a process pool via concurrent.futures. PyTorch inference releases the GIL during the forward pass, allowing concurrent feature computation. The remaining GIL-holding paths are profiled monthly with py-spy, and any path that holds the GIL for more than one millisecond is a candidate for Cython compilation.'));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 16 — NFRs
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 16 — Non-Functional Requirements'));
  children.push(p('Non-functional requirements (NFRs) specify the qualities the system must exhibit, as distinct from the functional requirements that specify what the system does. NFRs are measurable, owned, and verified in CI. A build that meets all functional requirements but fails an NFR gate is rejected. This chapter enumerates the eight NFR categories that apply to TITAN XAU AI, with specific targets, measurement methods, and owners.'));

  children.push(table(
    ['Category', 'NFR', 'Target', 'Measurement', 'Owner'],
    [
      ['Performance', 'Tick-to-trade p99', '< 5 ms', 'OpenTelemetry span, p99 over 1h', 'SRE'],
      ['Performance', 'Tick throughput', '50k ticks/s sustained', 'Locust load test, 1h', 'SRE'],
      ['Reliability', 'Uptime', '99.95%', 'Prometheus up query, monthly', 'SRE'],
      ['Reliability', 'MTTR', '< 15 min', 'Incident timestamp → recovery', 'SRE'],
      ['Availability', 'Failover Z1→Z2', '< 3 s', 'VRRP probe + app-level check', 'SRE'],
      ['Availability', 'Failover Z1→Z3 (DR)', '< 15 min', 'Manual DR drill', 'SRE'],
      ['Security', 'TLS version', 'TLS 1.3 only', 'sslyze scan', 'Security'],
      ['Security', 'Broker cred rotation', '≤ 30 days', 'Vault lease check', 'Security'],
      ['Security', 'Critical vuln count', '0 unresolved HIGH/CRITICAL', 'Trivy + Snyk', 'Security'],
      ['Observability', 'Metric scrape interval', '15 s', 'Prometheus config check', 'SRE'],
      ['Observability', 'Log retention', '1 year', 'Loki config check', 'SRE'],
      ['Observability', 'Trace sample rate (canary)', '100%', 'OTel config check', 'SRE'],
      ['Scalability', 'Tenants per cluster', 'Up to 20', 'Load test, multi-tenant', 'SRE'],
      ['Scalability', 'Strategies per tenant', 'Up to 10 (Enterprise)', 'Config validation', 'Eng'],
      ['Maintainability', 'Module LOC', '< 500 per module', 'cloc report', 'Eng'],
      ['Maintainability', 'Test coverage', '≥ 80% line', 'Coverage report', 'Eng'],
      ['Maintainability', 'Lint findings', '0 critical', 'clang-tidy, pylint', 'Eng'],
      ['Compliance', 'Audit log immutability', 'Tamper-evident', 'Hash chain verify', 'Compliance'],
      ['Compliance', 'Trade reconstruction', '< 5 min for any day', 'Replay from audit log', 'Compliance'],
      ['Compliance', 'License enforcement', 'Hard shutdown on revoke', 'License test in CI', 'Eng'],
    ],
    [16, 26, 24, 26, 8]
  ));
  children.push(spacer(200));

  children.push(h2('Availability Math'));
  children.push(p('The 99.95% uptime target translates to approximately four hours and twenty-two minutes of allowed downtime per year. This budget is consumed by planned maintenance (approximately one hour per year for cert rotations and DR drills) and unplanned incidents (the remaining three hours). To stay within budget, the system is designed for sub-three-second failover from Z1 to Z2 (consuming seconds per failover, not minutes) and sub-fifteen-minute recovery from a complete primary loss via Z3. The two-person rule for high-impact actions prevents operator error from causing extended outages. Penalties for SLA breach are 5% of license fee per 0.1% below target, capped at 50% of annual license fee.'));

  children.push(h2('Disaster Recovery Targets'));
  children.push(table(
    ['Scenario', 'RPO', 'RTO', 'Mechanism', 'Test Cadence'],
    [
      ['Z1 hardware failure', '< 1 s', '< 3 s', 'VRRP failover to Z2', 'Monthly automated'],
      ['Z1+Z2 metro disaster', '< 60 s', '< 15 min', 'Manual Z3 activation, WAL replay', 'Quarterly drill'],
      ['Data corruption (logical)', '0 (point-in-time)', '< 30 min', 'TimescaleDB PITR from S3', 'Quarterly'],
      ['Ransomware / compromise', '< 24 h', '< 4 h', 'Rebuild from gold image + state restore', 'Annual'],
      ['Broker outage', '0', '< 5 min', 'Auto-detect + halt new orders', 'Monthly'],
      ['License server outage', '0 (7-day grace)', '0', 'Offline grace period', 'Annual'],
    ],
    [28, 16, 14, 28, 14]
  ));
  children.push(spacer(200));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 17 — Risk & Compliance
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 17 — Risk & Compliance Architecture'));
  children.push(p('The risk architecture is the structural enforcement of the capital-preservation-first principle. It is organized into three lines of defense: pre-trade gates that block orders before they reach the broker, post-trade monitors that observe the live system and fire circuit breakers when thresholds are breached, and the kill switch that provides the ultimate emergency halt. Compliance is built on top of the audit store, an immutable hash-chained log that records every order, fill, risk decision, and operator action.'));

  children.push(h2('Pre-Trade Risk Gates'));
  children.push(p('The PreTradeRiskGate runs synchronously in the hot path, between the SignalEngine and the OrderManager. Every order must pass through it; there is no bypass. The gate performs the following checks in order, returning REJECT on the first failure with a specific reason code:'));
  children.push(bullet('Position size check — the resulting position must not exceed the configured maximum (default: 5% of equity per symbol).'));
  children.push(bullet('Leverage check — the resulting gross exposure must not exceed the configured maximum leverage (default: 10x).'));
  children.push(bullet('Daily trade count — the number of trades in the current UTC day must not exceed the configured maximum (default: 20).'));
  children.push(bullet('News blackout — the current time must not fall within any configured blackout window (FOMC ±15 min, NFP ±10 min, etc.).'));
  children.push(bullet('Margin floor — the post-order free margin must remain above 30% of equity.'));
  children.push(bullet('Drawdown throttle — if the rolling 90-day MaxDD exceeds 3% (soft), new entries are throttled to half size.'));
  children.push(bullet('Loss streak check — if the last N trades were all losses (default N=5), new entries are blocked for a cooldown period.'));
  children.push(p('The gate returns a RiskDecision value object carrying the verdict (APPROVE, REJECT, THROTTLE), a reason code, a human-readable message, an optional reduced quantity for THROTTLE, and a serializable audit blob. APPROVE allows the order to proceed; REJECT blocks it and logs the reason; THROTTLE allows the order with a reduced quantity. Every decision is written to the audit store, providing a complete record for post-incident analysis.'));

  children.push(h2('Post-Trade Risk Monitor'));
  children.push(p('The PostTradeRiskMonitor runs asynchronously, observing fills and equity updates. Unlike the pre-trade gate, it does not block orders; instead, it fires circuit breakers when thresholds are breached. The monitor tracks: drawdown circuit breakers (soft at 3% — throttle new entries and notify operator; hard at 5% — engage kill switch), loss streak circuit (5 consecutive losses triggers cooldown, 10 triggers soft halt), slippage outlier (if realized slippage exceeds 3 standard deviations above trailing mean, log and alert), margin call proximity (if free margin drops below 50%, alert; below 30%, soft halt), and daily loss limit (if daily realized loss exceeds 2% of equity, halt new entries for the day).'));

  children.push(h2('Kill Switch'));
  children.push(p('The kill switch is the system\'s emergency brake. Engaging it performs four actions in sequence: (1) halt all new orders by setting an atomic armed flag that the OrderManager checks before submitting; (2) cancel all pending orders via the broker API; (3) flatten all open positions via market orders; (4) notify the operator via PagerDuty, Telegram, and the operator console. The target end-to-end time from kill switch trigger to position flat is five hundred milliseconds. The kill switch can be triggered by: manual operator action (two-person rule), automatic PostTradeRiskMonitor detection (hard drawdown, loss streak), or license revocation. Once triggered, the system enters a cooldown period (default 5 minutes) during which it cannot be re-armed without supervisor intervention and an audit-trail entry explaining the re-arm reason.'));

  children.push(h2('Compliance & Audit'));
  children.push(p('The audit store is the system\'s memory and conscience. Every order event, fill, risk decision, and operator action is appended to a hash-chained log: each entry includes the previous entry\'s hash, making tampering computationally detectable. The log is stored on write-once-read-many (WORM) S3 with object lock, providing physical tamper resistance in addition to the cryptographic guarantee. The log supports arbitrary point-in-time reconstruction: given a starting state and a range of audit entries, the system can reconstruct the exact state at any past moment, enabling forensic analysis of any incident.'));
  children.push(p('Compliance reporting hooks are provided for licensees who must report to regulators. The MiFID-II-style trade reporting adapter exports fills in the regulatory format; the GDPR adapter handles operator personal data deletion requests. Licensees receive a daily compliance report via email and have read API access to the audit log for their tenant. The audit log is retained for the longer of the license term plus five years or the regulatory minimum for the licensee\'s jurisdiction.'));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 18 — Licensing
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 18 — Commercial Licensing Architecture'));
  children.push(p('The licensing architecture is designed to be enforceable without being onerous. It uses RSA-signed JSON Web Tokens (JWTs) issued by a per-tenant license server, validated online with a seven-day offline grace period. Feature gates are encoded as claims in the JWT, allowing tiered pricing (Starter, Pro, Enterprise) without separate codebases. Hardware fingerprinting, code obfuscation, and tamper detection protect against casual piracy without imposing onerous restrictions on legitimate licensees.'));

  children.push(h2('License Model'));
  children.push(p('Each licensee receives a tenant ID and an RSA public key pair. The license server (SaaS, hosted by TITAN) signs JWTs containing the tenant\'s claims: tier, strategy count, capital ceiling, feature flags, expiry. The TITAN runtime validates the JWT signature on startup and on every hourly heartbeat. If validation fails (expired, revoked, signature mismatch), the system enters a grace period: seven days of continued operation with prominent operator alerts, followed by a graceful shutdown that closes positions and halts new orders. The grace period exists to handle transient network issues and to give licensees time to renew without disrupting live trading.'));

  children.push(h2('Tier Matrix'));
  children.push(table(
    ['Feature', 'Starter', 'Pro', 'Enterprise'],
    [
      ['Strategies', '1 (preset)', '3 (preset + custom)', 'Unlimited (custom + on-prem)'],
      ['Capital ceiling', '$50,000', '$500,000', 'Unlimited'],
      ['ML inference', 'Linear models only', 'Full PyTorch', 'Full PyTorch + custom models'],
      ['News sentiment engine', '—', '✓', '✓'],
      ['Custom strategy development', '—', 'Python only', 'Python + C++ (subject to review)'],
      ['White-label branding', '—', '—', '✓'],
      ['On-prem license server', '—', '—', '✓ (air-gapped option)'],
      ['SLA', 'Best effort', '99.5%', '99.95% + dedicated SRE'],
      ['Support', 'Email, 48h response', 'Email + chat, 24h', 'Slack channel, 1h, named SRE'],
      ['Price (annual)', '$12,000', '$48,000', '$180,000 + revenue share'],
    ],
    [40, 18, 22, 20]
  ));
  children.push(spacer(200));

  children.push(h2('Anti-Piracy Measures'));
  children.push(p('Casual piracy is deterred through four layered measures, each raising the cost of circumvention without burdening legitimate users. The first layer is hardware fingerprinting: the JWT is bound to a fingerprint derived from CPUID, MAC address, and disk serial number; a license used on a different machine fails validation. The second layer is code obfuscation: C++ symbols are stripped from release builds, Python sensitive modules (license validation, model decryption, strategy parameter decryption) are compiled to native code via Cython and shipped as binary wheels. The third layer is tamper detection: the runtime checksums its own binary on startup and periodically; mismatch triggers a graceful shutdown with an audit log entry. The fourth layer is behavioral analytics: the license server tracks usage patterns and flags anomalies (e.g., a single license used from IPs in five countries in one day) for manual review.'));
  children.push(p('None of these measures is unbreakable — determined adversaries with sufficient resources can circumvent any software protection. The goal is to raise the cost above the price of a legitimate license for the vast majority of potential pirates, while keeping the experience seamless for paying customers. The hardware fingerprint, in particular, is designed to be lenient: routine hardware changes (adding RAM, replacing a failed disk) trigger a re-activation flow rather than a lockout, with three re-activations per year allowed automatically and additional ones requiring support contact.'));

  children.push(h2('License Validation Flow'));
  children.push(p('On startup, the TITAN runtime loads the cached JWT from /var/lib/titan/license.jwt and validates the RSA signature against the embedded TITAN public key. If valid and not expired, the runtime extracts the claims and configures feature gates accordingly. If invalid or expired, the runtime attempts to refresh the JWT by calling the license server with the tenant ID and hardware fingerprint. If the refresh succeeds, the new JWT is cached and trading proceeds. If the refresh fails (network issue, server unavailable), the runtime enters the seven-day grace period, during which it continues trading with prominent operator alerts. After seven days without a successful refresh, the runtime initiates a graceful shutdown: halt new orders, flatten positions, cancel pending orders, and exit with a non-zero status code. The hourly heartbeat during normal operation serves the same refresh logic, ensuring that a revoked license is detected within an hour of revocation.'));

  // ════════════════════════════════════════════════════════════════════
  // Chapter 19 — Roadmap
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Chapter 19 — Implementation Roadmap'));
  children.push(p('The implementation roadmap spans twelve months across four phases, each with hard exit criteria tied to the target metrics. The phasing reflects the principle that foundation must precede intelligence, intelligence must precede productionization, and productionization must precede commercialization. A phase cannot be exited until all its exit criteria are met on out-of-sample data; there is no schedule override. The roadmap assumes a starting team of four FTE ramping to eight FTE by month six.'));
  children.push(diagram('d11_roadmap.png', 6.5));
  children.push(caption('Figure 19.1 — 12-month roadmap Gantt with phase exit milestones.'));

  children.push(h2('Phase 1 — Foundation (M1-M3)'));
  children.push(p('Phase 1 builds the infrastructure on which everything else depends. The folder structure, CI scaffolding, and development environment come first (M1). The MT5 bridge and tick pipeline (M2) establish the data plane, with a target p99 tick ingestion latency under two milliseconds. The backtest engine and basic risk gate (M3) close the loop, enabling the first walk-forward validation. Phase 1 exit criteria: tick pipeline p99 under 2 ms, backtest replay matches paper trade within 0.1% over a one-month sample, risk gate blocks 100% of test violations. Deliverables: repo scaffold, MT5 bridge, normalizer, basic risk gate, backtest engine, CI scaffolding. Team: 4 FTE.'));

  children.push(h2('Phase 2 — Intelligence (M4-M6)'));
  children.push(p('Phase 2 adds the alpha generation layer. The feature engine (M4-M5) implements over three hundred features spanning technical, microstructure, and session categories. The signal engine and first live strategy (M5-M6) produce the first end-to-end signal-to-order flow. ML inference via PyTorch (M5-M6) enables model-based signal enhancement. Walk-forward validation (M6) provides the first credible performance estimate. Phase 2 exit criteria: walk-forward PF above 1.5, Sharpe above 1.5, MaxDD below 5% on out-of-sample, ML inference p99 under 1 ms. Deliverables: feature engine, signal engine, ML inference, first live strategy, walk-forward validator. Team: 6 FTE.'));

  children.push(h2('Phase 3 — Productionization (M7-M9)'));
  children.push(p('Phase 3 makes the system production-ready. The three-zone deployment (M7) provides the HA foundation. The monitoring stack (M7-M8) gives observability. The licensing server (M8) enables the first commercial pilots. The canary CI/CD pipeline (M8-M9) with the backtest regression gate enforces the metric discipline. The chaos game-day (M9) stress-tests the system. Phase 3 exit criteria: 99.95% uptime over 30 days, Z1→Z2 failover under 3 seconds, DR drill passed, license server live, canary auto-rollback works. Deliverables: HA deployment, monitoring, licensing, canary CI/CD, chaos game-day, runbooks. Team: 7 FTE.'));

  children.push(h2('Phase 4 — Commercialization (M10-M12)'));
  children.push(p('Phase 4 turns the production system into a commercial product. Multi-tenant isolation (M10) enables multiple licensees on shared infrastructure. Billing integration (M11) handles subscription and usage-based billing. White-label option (M11) allows partners to rebrand the system. Partner onboarding flow (M11-M12) streamlines new licensee activation. The v1.0 GA launch (M12) marks the end of the roadmap and the beginning of post-GA iteration. Phase 4 exit criteria: 3+ paying licensees, multi-tenant isolated, billing integrated, white-label pilot signed. Deliverables: multi-tenant, billing, white-label, partner onboarding, v1.0 GA. Team: 8 FTE.'));

  children.push(h2('Post-GA Roadmap (Indicative)'));
  children.push(p('Beyond v1.0 GA, the roadmap is reviewed quarterly. Likely directions include: FIX broker support (v1.1, Q1 2027) for direct-access brokers without MT5 dependency; multi-instrument support (v1.2, Q2 2027) extending to XAGUSD and other precious metals; an on-prem enterprise deployment option (v2.0, Q3 2027) for licensees who cannot use shared infrastructure; a strategy marketplace (v2.1, Q4 2027) allowing third-party strategy developers to publish strategies under revenue share. These are indicative, not committed; the actual post-GA roadmap will be set in the Q1 2027 planning cycle based on licensee feedback and market conditions.'));

  // ════════════════════════════════════════════════════════════════════
  // Appendix A — Glossary
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Appendix A — Glossary & Acronyms'));
  children.push(p('This glossary defines the terminology used throughout the document. Terms are ordered alphabetically. Acronyms are spelled out on first use in each chapter and defined here for reference.'));

  const glossary = [
    ['XAUUSD', 'Spot gold versus US dollar currency pair. XAU is the ISO 4217 code for one troy ounce of gold; USD is the US dollar. The most actively traded precious metals pair.'],
    ['MT5', 'MetaTrader 5. A retail and institutional trading platform developed by MetaQuotes Software, widely supported by forex and CFD brokers. TITAN\'s primary execution venue.'],
    ['FIX', 'Financial Information eXchange protocol. A vendor-neutral electronic communications protocol for the international real-time exchange of securities transaction information. Version 4.4 is used for institutional order routing.'],
    ['MQL5', 'MetaQuotes Language 5. The programming language for custom indicators and expert advisors in MT5. TITAN does not use MQL5 directly; it interfaces with MT5 via the Python MetaTrader5 package and C++ bridge.'],
    ['PyO3', 'A Rust library (with Python bindings) for writing native Python extensions in Rust. TITAN uses a similar pattern via pybind11 for C++/Python interop, sometimes loosely referred to as PyO3-style bindings.'],
    ['PyTorch', 'An open-source machine learning framework developed by Meta AI. Used in TITAN for ML model training and inference (via ONNX runtime in production).'],
    ['Sharpe Ratio', 'Risk-adjusted return measure: (mean return − risk-free rate) / standard deviation of returns, annualized. Higher is better. Target: > 2.0.'],
    ['Profit Factor (PF)', 'Gross profit divided by gross loss over a measurement window. PF > 2.0 is institutional grade. Target: > 2.0.'],
    ['Recovery Factor', 'Net profit divided by maximum drawdown over a window. Measures how quickly the system recovers from worst dip. Target: > 5.0.'],
    ['Risk of Ruin (RoR)', 'Monte Carlo probability of equity hitting a ruin threshold (50% drawdown) within 252 trading days. Target: < 1%.'],
    ['MaxDD', 'Maximum Drawdown. Largest peak-to-trough decline in equity curve over a window, as percentage of peak. Target: < 5%.'],
    ['Walk-Forward', 'A backtesting methodology where parameters are optimized on a rolling in-sample window and validated on the immediately following out-of-sample window, then the window rolls forward. Prevents look-ahead bias.'],
    ['Monte Carlo', 'A statistical technique using repeated random sampling to estimate the distribution of an outcome. In TITAN, used for risk-of-ruin estimation by sampling 1000 randomized return paths.'],
    ['Kill Switch', 'Emergency control that halts all new orders, cancels pending orders, and flattens open positions. TITAN\'s kill switch targets < 500ms end-to-end.'],
    ['Hot-Standby', 'A redundant system component that is running and ready to take over immediately on primary failure, with state replicated synchronously. TITAN\'s Z2 is hot-standby to Z1.'],
    ['Cold-Standby', 'A redundant system component that is configured but not running, requiring manual activation on primary failure. TITAN\'s Z3 is cold-standby for catastrophic failover.'],
    ['RPO', 'Recovery Point Objective. The maximum acceptable data loss measured in time. TITAN Z3 RPO: 60 seconds.'],
    ['RTO', 'Recovery Time Objective. The maximum acceptable time to restore service after a failure. TITAN Z3 RTO: 15 minutes.'],
    ['NUMA', 'Non-Uniform Memory Access. A multi-processor memory architecture where each CPU has local memory with lower access latency than remote memory. TITAN pins titan-core to NUMA node 0 for predictable memory access.'],
    ['PREEMPT_RT', 'A Linux kernel patch that provides full kernel preemption, allowing high-priority tasks to interrupt kernel-level work. Essential for sub-millisecond latency predictability.'],
    ['WireGuard', 'A modern, fast, and secure VPN protocol that uses state-of-the-art cryptography. TITAN uses WireGuard for inter-zone communication.'],
    ['FlatBuffers', 'A cross-platform serialization library with zero-copy access to serialized data. Used in TITAN for inter-language message passing without copy overhead.'],
    ['MLflow', 'An open-source platform for managing the ML lifecycle, including experiment tracking, model registry, and deployment. Used in TITAN for model versioning.'],
    ['OpenTelemetry (OTel)', 'An open observability framework for generating and collecting telemetry data (traces, metrics, logs). Used in TITAN for distributed tracing of tick-to-trade path.'],
    ['VRRP', 'Virtual Router Redundancy Protocol. A network protocol that provides automatic failover for default gateway. TITAN uses VRRP for Z1→Z2 failover.'],
    ['SPSC', 'Single-Producer Single-Consumer. A queue pattern with one writer and one reader, allowing lock-free implementation via atomics. Used in TITAN\'s hottest data paths.'],
    ['JWT', 'JSON Web Token. A compact, URL-safe means of representing claims to be transferred between two parties. TITAN uses RSA-signed JWTs for license tokens.'],
    ['NFR', 'Non-Functional Requirement. A requirement specifying a quality the system must exhibit (performance, reliability, security, etc.), as distinct from a functional requirement (what the system does).'],
    ['ADR', 'Architecture Decision Record. A short text document capturing a single architectural decision, its context, consequences, and alternatives considered.'],
    ['WORM', 'Write Once, Read Many. A storage model where data, once written, cannot be modified or deleted until a retention period expires. TITAN uses WORM S3 for the audit log.'],
    ['TCA', 'Transaction Cost Analysis. The process of analyzing the execution quality of trades, including realized slippage, fill rates, and venue quality.'],
    ['OIDC', 'OpenID Connect. An identity layer on top of OAuth 2.0, used in TITAN for operator console authentication.'],
    ['SLA', 'Service Level Agreement. A formal commitment to a specific level of service, with penalties for breach. TITAN offers 99.95% SLA for Enterprise tier.'],
    ['MTTR', 'Mean Time To Recovery. The average time to restore service after a failure. TITAN target: < 15 minutes.'],
  ];
  children.push(table(
    ['Term', 'Definition'],
    glossary,
    [20, 80]
  ));
  children.push(spacer(200));

  // ════════════════════════════════════════════════════════════════════
  // Appendix B — Reference Configurations
  // ════════════════════════════════════════════════════════════════════
  children.push(h1('Appendix B — Reference Configurations'));
  children.push(p('This appendix contains sample configuration snippets for the key runtime components. These are reference values for a $250,000 capital deployment at the Pro tier; production deployments will deviate based on tenant risk profile, broker terms, and operational preferences. All configurations are version-controlled in configs/ with environment-specific overrides in configs/environments/.'));

  children.push(h2('titan-core.yaml — Runtime configuration'));
  children.push(code(`# titan-core.yaml — C++ execution core runtime config
runtime:
  cpu_affinity: [2, 3]              # pinned cores
  numa_node: 0
  hugepages: 2048                   # 4GB at 2MB per page
  scheduling: realtime              # PREEMPT_RT
  nice: -11

event_bus:
  type: zmq_pubsub
  bind_endpoint: "ipc:///var/run/titan/bus.sock"
  hwm: 100000                       # high-water mark (messages)
  backpressure: throttle            # throttle producers on HWM

ffi:
  python_path: "/opt/titan/python"
  pyo3_module: titan_strategy
  flatbuffer_schema: "/etc/titan/schemas"

logging:
  level: info
  format: json
  sink: file+stderr
  file_path: "/var/log/titan/core.log"
  rotation: daily
  retention: 30d`));

  children.push(h2('risk.yaml — Risk envelope'));
  children.push(p('The risk envelope is the most consequential configuration in the system. Changes require supervisor authorization and are recorded in the audit log. Most limits auto-revert after a configurable timeout (default 4 hours) to prevent drift.'));
  children.push(code(`# risk.yaml — Risk envelope (production defaults)
pre_trade:
  max_position_pct: 5.0             # max 5% of equity per symbol
  max_leverage: 10                  # max 10x gross exposure
  max_daily_trades: 20
  margin_floor_pct: 30              # halt if free margin < 30%
  news_blackout_windows:
    - { event: FOMC, before_min: 15, after_min: 15 }
    - { event: NFP,  before_min: 10, after_min: 10 }
    - { event: CPI,  before_min: 5,  after_min: 5  }
    - { event: FOMC_presser, before_min: 10, after_min: 10 }

post_trade:
  dd_soft_threshold_pct: 3.0        # throttle new entries
  dd_hard_threshold_pct: 5.0        # engage kill switch
  loss_streak_soft: 5               # cooldown
  loss_streak_hard: 10              # soft halt
  slippage_outlier_z: 3.0
  daily_loss_limit_pct: 2.0         # halt new entries for the day

kill_switch:
  cooldown_s: 300                   # 5 min before re-arm
  auto_flatten: true
  notify_channels: [pagerduty, telegram, console]

circuit_breakers:
  check_interval_ms: 100
  window_days: 90`));

  children.push(h2('strategy.yaml — Strategy parameters'));
  children.push(code(`# strategy.yaml — Strategy activation and parameters
strategies:
  - id: momentum_xau_v3
    enabled: true
    allocation_pct: 40               # 40% of risk budget
    params:
      lookback_bars: 60
      threshold_z: 1.5
      stop_atr_multiple: 1.5
      target_atr_multiple: 3.0
    regime_filter:
      enabled: [trending, news_driven]
      disabled: [choppy, mean_reverting]

  - id: mean_reversion_xau_v2
    enabled: true
    allocation_pct: 35
    params:
      lookback_bars: 120
      bb_std: 2.0
      stop_atr_multiple: 1.0
      target_atr_multiple: 2.0
    regime_filter:
      enabled: [mean_reverting, choppy]
      disabled: [trending, news_driven]

  - id: news_aware_v1
    enabled: true
    allocation_pct: 25
    params:
      sentiment_threshold: 0.7
      hold_min: 30
      max_position_pct: 2.0
    regime_filter:
      enabled: [news_driven]

coordinator:
  conflict_resolution: priority     # priority > allocation
  max_concurrent_positions: 3
  min_signal_strength: 0.4`));

  children.push(h2('monitoring.yaml — Observability configuration'));
  children.push(code(`# monitoring.yaml — Prometheus + Loki + AlertManager
prometheus:
  scrape_interval: 15s
  retention: 5d
  federation:
    - { target: "z2-prometheus:9090", interval: 30s }
    - { target: "z3-prometheus:9090", interval: 60s }

alertmanager:
  routes:
    - match: { severity: P1 }
      receiver: pagerduty+telegram
      group_wait: 0s
      repeat_interval: 5m
    - match: { severity: P2 }
      receiver: pagerduty
      group_wait: 30s
      repeat_interval: 30m
    - match: { severity: P3 }
      receiver: telegram
      group_wait: 5m
      repeat_interval: 4h

loki:
  retention: 365d
  backend: s3
  s3_bucket: titan-loki-eu-west-1
  structured_metadata: [service, level, trace_id]

alerts:
  - name: LatencyP99Breach
    expr: histogram_quantile(0.99, titan_tick_to_trade_bucket) > 0.005
    for: 1m
    severity: P1
  - name: DrawdownSoftBreach
    expr: titan_drawdown_pct > 3.0
    for: 30s
    severity: P2
  - name: DrawdownHardBreach
    expr: titan_drawdown_pct > 5.0
    for: 0s
    severity: P1
  - name: BrokerDisconnect
    expr: titan_broker_connected == 0
    for: 30s
    severity: P1`));

  children.push(h2('license.yaml — License client configuration'));
  children.push(code(`# license.yaml — License client (per-tenant)
tenant:
  id: "TEN-PROD-7F4A92"             # tenant identifier
  tier: pro                          # starter | pro | enterprise
  hardware_fingerprint: true         # bind to host hardware

server:
  url: "https://license.titan.io/v1"
  heartbeat_interval: 3600          # 1 hour
  timeout: 10s
  ca_bundle: "/etc/titan/license-ca.pem"

offline_grace:
  duration: 7d                      # 7 days of offline grace
  warning_threshold: 2d             # alert when < 2d remaining

revocation:
  graceful_shutdown: true
  flatten_positions: true
  cancel_pending: true
  notify_operator: true

feature_gates:
  - { feature: ml_inference,        claim: ml_inference,       required: true }
  - { feature: news_sentiment,      claim: news_sentiment,     required: false }
  - { feature: custom_strategies,   claim: custom_strategies,  required: false }
  - { feature: white_label,         claim: white_label,        required: false }`));

  children.push(h2('Configuration Management'));
  children.push(p('All configurations are version-controlled in Git alongside the source code, with environment-specific overrides in configs/environments/. Configurations are loaded at startup and hot-reloaded via inotify watchers; changes to non-critical parameters (logging level, scrape interval) take effect immediately, while changes to critical parameters (risk envelope, strategy activation) require supervisor authorization via the operator console. Every configuration change is recorded in the audit log with the operator identity, before/after diff, and reason. Configurations are validated by pydantic schemas on load; invalid configurations cause the service to refuse to start with a clear error message.'));

  return children;
}

// ════════════════════════════════════════════════════════════════════════
//  BUILD & SAVE
// ════════════════════════════════════════════════════════════════════════

async function main() {
  console.log('[build] Generating TITAN XAU AI DOCX...');

  const coverChildren = buildCoverChildren();
  const tocChildren = buildTocChildren();
  const bodyChildren = buildBodyChildren();

  const doc = new Document({
    creator: 'TITAN Quant Research',
    title: 'TITAN XAU AI — Architecture Specification',
    description: 'Institutional-grade AI trading system architecture for XAUUSD',
    subject: 'Trading system architecture',
    styles: {
      default: {
        document: {
          run: { font: 'Liberation Serif', size: 22 },
          paragraph: { spacing: { line: 312 } },
        },
        heading1: {
          run: { font: 'Liberation Serif', size: 40, bold: true, color: C.navy },
          paragraph: { spacing: { before: 480, after: 240 } },
        },
        heading2: {
          run: { font: 'Liberation Serif', size: 28, bold: true, color: C.navy },
          paragraph: { spacing: { before: 320, after: 160 } },
        },
        heading3: {
          run: { font: 'Liberation Serif', size: 24, bold: true, color: C.crimson },
          paragraph: { spacing: { before: 240, after: 120 } },
        },
      },
    },
    sections: [
      // Cover section — no header/footer
      {
        properties: {
          page: {
            size: { width: 11906, height: 16838 },
            margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
          },
        },
        children: coverChildren,
      },
      // TOC section
      {
        properties: {
          page: {
            size: { width: 11906, height: 16838 },
            margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
            pageNumbers: { start: 1, formatType: NumberFormat.LOWER_ROMAN },
          },
        },
        footers: {
          default: new Footer({
            children: [new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, font: 'Liberation Serif', color: C.muted })],
            })],
          }),
        },
        children: tocChildren,
      },
      // Body section — Arabic page numbers starting at 1
      {
        properties: {
          page: {
            size: { width: 11906, height: 16838 },
            margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
            pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL },
          },
        },
        headers: {
          default: new Header({
            children: [new Paragraph({
              alignment: AlignmentType.LEFT,
              border: { bottom: { color: C.navy, size: 6, style: BorderStyle.SINGLE, space: 4 } },
              children: [
                new TextRun({ text: 'TITAN XAU AI — Architecture Specification', size: 18, italics: true, font: 'Liberation Serif', color: C.muted }),
                new TextRun({ text: '\t\t', size: 18 }),
                new TextRun({ text: 'v1.0  ·  COMMERCIAL — LICENSEE', size: 18, bold: true, font: 'Liberation Serif', color: C.crimson }),
              ],
              tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
            })],
          }),
        },
        footers: {
          default: new Footer({
            children: [new Paragraph({
              alignment: AlignmentType.CENTER,
              border: { top: { color: C.border, size: 4, style: BorderStyle.SINGLE, space: 4 } },
              children: [
                new TextRun({ text: '© 2026 TITAN Quant Research  ·  Proprietary & Confidential\t\t', size: 18, italics: true, font: 'Liberation Serif', color: C.muted }),
                new TextRun({ children: [PageNumber.CURRENT], size: 20, bold: true, font: 'Liberation Serif', color: C.navy }),
              ],
              tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
            })],
          }),
        },
        children: bodyChildren,
      },
    ],
  });

  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(OUTPUT_PATH, buffer);
  console.log(`[build] DOCX written: ${OUTPUT_PATH}`);
  console.log(`[build] Size: ${(buffer.length / 1024).toFixed(1)} KB`);
}

main().catch(e => {
  console.error('[FATAL]', e);
  process.exit(1);
});
