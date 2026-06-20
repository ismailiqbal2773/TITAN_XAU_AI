"""
TITAN XAU AI — Architecture Document Body Content (Part 2)
Chapters 6-23 with embedded diagram references and supporting tables.
"""

from reportlab.platypus import Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from content_part1 import (
    S, h1, h2, h3, p, bullet, code, caption, callout, hr, diagram, table,
    HEADER_FILL, ACCENT, TEXT_PRIMARY, TEXT_MUTED, BORDER, CARD_BG, SECTION_BG,
    SEM_SUCCESS, SEM_WARNING, SEM_ERROR,
)


def build_part2():
    story = []

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 6 — Deliverable 1: Complete Folder Structure
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Deliverable 1 — Complete Folder Structure', 6))
    story.append(p(
        'The repository layout is the first concrete artifact of the architecture. It encodes '
        'the module boundaries, the language split, the deployment story, and the operational '
        'tooling in a single tree that any engineer can navigate. The structure follows three '
        'principles: separation by language (C++ and Python live in distinct subtrees), '
        'separation by concern (source, tests, configs, deploy, docs are all top-level), and '
        'convention over configuration (well-known paths for well-known things, so tooling can '
        'be written once and reused).'
    ))
    story.append(p(
        'The C++ source tree lives under <font name="DejaVuSans">src/</font> with public headers '
        'mirrored under <font name="DejaVuSans">include/</font>, following the standard CMake '
        'convention. Each layer has its own subdirectory (<font name="DejaVuSans">core/</font>, '
        '<font name="DejaVuSans">market_data/</font>, <font name="DejaVuSans">bridge/</font>, '
        '<font name="DejaVuSans">risk/</font>, <font name="DejaVuSans">execution/</font>, '
        '<font name="DejaVuSans">ffi/</font>), and within each layer the files are organized by '
        'service. The Python tree mirrors this structure under <font name="DejaVuSans">python/</font> '
        'with subdirectories for strategy, features, signal, ml, backtest, and research. The FFI '
        'boundary — the PyO3 bindings and FlatBuffer schemas — lives in '
        '<font name="DejaVuSans">src/ffi/</font> and is the single point of contact between the '
        'two languages.'
    ))
    story.append(diagram('d01_folder_structure.png', width_mm=170))
    story.append(caption('Figure 6.1 — Complete repository folder structure with per-directory annotations.'))

    story.append(h2('Key Directory Responsibilities'))
    story.append(table([
        ['Path', 'Responsibility', 'Approximate LOC'],
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
    ], col_widths=[45, 95, 30]))
    story.append(Spacer(1, 8))

    story.append(h2('Build & Dependency Management'))
    story.append(p(
        'The C++ build is orchestrated by CMake 3.27+ with conan 2.x for dependency management. '
        'A top-level <font name="DejaVuSans">CMakeLists.txt</font> orchestrates the build of '
        'all C++ libraries and the titan-core executable, with subdirectory CMakeLists.txt files '
        'per layer. Release builds enable LTO and PGO; debug builds enable AddressSanitizer and '
        'UndefinedBehaviorSanitizer. The Python build uses <font name="DejaVuSans">pyproject.toml</font> '
        'with uv for dependency resolution and Cython for the sensitive modules. Both builds are '
        'reproducible: pinned dependency versions, lockfiles in git, and build cache via ccache '
        '(C++) and uv cache (Python).'
    ))
    story.append(p(
        'Third-party dependencies are vendored under <font name="DejaVuSans">third_party/</font> '
        'where their license permits (pybind11, moodycamel, flatbuffers) and managed via conan '
        'where it does not (Boost, OpenSSL, ZeroMQ). Every dependency is reviewed by the security '
        'team before addition, with the review recorded in <font name="DejaVuSans">licenses/third-party-notices.txt</font>. '
        'Dependencies with known vulnerabilities are auto-detected by Trivy in CI and block the '
        'build until upgraded or formally exception-approved.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 7 — Deliverable 2: Service Architecture
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Deliverable 2 — Service Architecture', 7))
    story.append(p(
        'The service architecture organizes the system into six logical layers, each containing '
        'a cohesive set of services with a single responsibility. The layers are stacked such '
        'that data flows downward (ingest at the top, persistence at the bottom) and control '
        'flows upward (risk veto at L4 overrides strategy at L3). A strict dependency rule — '
        'layer N may only depend on layer N-1 or below — is enforced by an architecture linter '
        'in CI; cyclic dependencies fail the build. This is the structural guarantee that risk '
        'retains veto power over every order regardless of strategy intent.'
    ))
    story.append(diagram('d02_service_architecture.png', width_mm=170))
    story.append(caption('Figure 7.1 — Six-layer service architecture. C++ services (pink) handle sub-millisecond hot path; Python services (green) handle 10ms+ intelligence layer.'))

    story.append(h2('Layer Responsibilities'))
    story.append(h3('L1 — Ingest Layer'))
    story.append(p(
        'The ingest layer is the system\'s boundary with the outside world. It contains all '
        'adapters to external feeds: the MT5 bridge that connects to the MetaTrader 5 terminal, '
        'the FIX adapter for FIX-protocol brokers (planned for v1.1), the news feed adapter '
        'that pulls Bloomberg and Reuters XML feeds, the economic calendar adapter for FOMC, '
        'CPI, and NFP events, and a feed health monitor that detects stale-tick conditions. '
        'A pcap replayer supports backtest ingest from captured packet traces. All ingest '
        'services are C++ for low latency; they push raw events onto the async event bus '
        'without any processing.'
    ))
    story.append(h3('L2 — Normalize Layer'))
    story.append(p(
        'The normalize layer transforms heterogeneous feed formats into a single canonical '
        'representation. The tick normalizer deduplicates ticks, aligns decimal precision, '
        'and tags each tick with its source feed. The session calendar attaches the trading '
        'session (Asia, EU, US, rollover) to every event. The FX converter handles cross-rate '
        'conversion for multi-currency position reporting. The bar aggregator builds M1, M5, '
        'M15, and H1 OHLCV bars from tick streams. The tick buffer is a one-million-tick ring '
        'buffer that provides O(1) random access to recent history. The time sync service '
        'disciplines the system clock against NTP and, where available, PTP hardware clocks.'
    ))
    story.append(h3('L3 — Intelligence Layer'))
    story.append(p(
        'The intelligence layer is where alpha is generated. It is the only layer implemented '
        'in Python (with selected hot-path components in C++ via the FFI). The feature engine '
        'computes over three hundred features spanning technical analysis, microstructure, '
        'session behavior, and cross-asset correlations. The signal engine combines features '
        'into directional signals using rule-based and ML ensemble methods. The ML inference '
        'engine runs PyTorch models via ONNX runtime for sub-millisecond inference. The '
        'strategy coordinator arbitrates between multiple strategies, allocating risk budget '
        'and resolving conflicts. The regime detector classifies the current market regime '
        '(trending, mean-reverting, choppy, news-driven) using a hidden Markov model, '
        'allowing strategies to adapt their behavior. The news sentiment engine applies NLP '
        'to Federal Reserve communications and geopolitical news.'
    ))
    story.append(h3('L4 — Risk Layer'))
    story.append(p(
        'The risk layer is the structural enforcement of the capital-preservation-first '
        'principle. It contains the pre-trade risk gate (synchronous veto on every order), '
        'the post-trade risk monitor (asynchronous observer that fires circuit breakers), '
        'the exposure aggregator (net and gross exposure in real time), the margin monitor '
        '(free margin floor at thirty percent), the kill switch controller (halt, flatten, '
        'cancel in under five hundred milliseconds), and the circuit breaker (three percent '
        'soft drawdown, five percent hard drawdown). All risk services are C++ for predictable '
        'latency and run on dedicated CPU cores to avoid contention.'
    ))
    story.append(h3('L5 — Execution Layer'))
    story.append(p(
        'The execution layer manages the order lifecycle from signal to fill. The order '
        'manager owns the order state machine (NEW → SENT → PARTIAL → FILLED / CANCELED / '
        'REJECTED). The smart router selects order type (market, limit, stop) and venue based '
        'on signal characteristics and current market conditions. The fill tracker handles '
        'partial fills and computes realized slippage. The slippage model estimates expected '
        'slippage for size-aware order routing. The order reconciler periodically compares '
        'local state with broker state to detect orphans (local thinks order exists, broker '
        'does not) and phantoms (broker thinks order exists, local does not). The execution '
        'auditor records every order event for trade cost analysis and compliance.'
    ))
    story.append(h3('L6 — Persistence & Operations Layer'))
    story.append(p(
        'The persistence layer is the system\'s memory and voice. The trade logger writes '
        'every fill to an append-only write-once-read-many (WORM) store for compliance. The '
        'metrics exporter emits Prometheus metrics and OpenTelemetry traces. The audit store '
        'maintains a hash-chained log of every operator action, risk decision, and order event — '
        'tamper-evident by construction. The license service validates the per-tenant JWT and '
        'enforces feature gates. The state replicator syncs hot state to the standby VPS. The '
        'operator alert gateway routes alerts to PagerDuty, Telegram, and the operator console.'
    ))

    story.append(h2('Service Responsibility Matrix'))
    story.append(table([
        ['Service', 'Layer', 'Language', 'CPU Pin', 'p99 Latency Target', 'Failure Mode'],
        ['MT5Bridge', 'L1', 'C++', '0-1', '0.5 ms', 'Broker disconnect → failover to Z2'],
        ['TickNormalizer', 'L2', 'C++', '2', '0.1 ms', 'Pass-through raw ticks'],
        ['FeatureEngine', 'L3', 'Python+C++', '4-7', '1.0 ms', 'Cache last-known features'],
        ['SignalEngine', 'L3', 'Python', '4-7', '0.5 ms', 'Withhold signal'],
        ['PreTradeRiskGate', 'L4', 'C++', '3', '0.3 ms', 'Reject by default'],
        ['KillSwitchController', 'L4', 'C++', '3', '0.5 ms', 'Fail-safe (always armed)'],
        ['OrderManager', 'L5', 'C++', '2', '0.3 ms', 'Reject new orders'],
        ['TradeLogger', 'L6', 'Python', '9', 'async', 'Buffer to disk'],
        ['LicenseService', 'L6', 'Python', '9', 'async', 'Grace period then halt'],
    ], col_widths=[35, 14, 22, 16, 32, 51]))
    story.append(Spacer(1, 8))

    story.append(h2('Data Plane vs Control Plane Separation'))
    story.append(p(
        'The architecture separates the data plane (the hot path that processes ticks and '
        'places orders) from the control plane (configuration, monitoring, operator actions). '
        'The two planes use distinct network paths, distinct CPU allocations, and distinct '
        'failure modes. A control-plane outage — Prometheus down, Grafana unreachable, '
        'operator console offline — does not affect trading. A data-plane outage does not '
        'prevent the operator from engaging the kill switch, which has its own dedicated '
        'channel. This separation is essential for the reliability target of 99.95% uptime.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 8 — Deliverable 3: Data Flow Diagrams
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Deliverable 3 — Data Flow Diagrams', 8))
    story.append(p(
        'Three data flow diagrams at increasing levels of detail document how information moves '
        'through the system. The Level-0 context diagram shows the system as a single bubble '
        'exchanging flows with external entities. The Level-1 diagram decomposes this bubble '
        'into seven internal processes and five data stores, with labeled flows between them. '
        'The tick-to-trade latency flow annotates the warm path with millisecond budgets per '
        'stage, providing the basis for the latency budget chapter that follows.'
    ))
    story.append(diagram('d03_data_flow.png', width_mm=170))
    story.append(caption('Figure 8.1 — Three DFD levels: (a) context, (b) internal processes with data stores, (c) tick-to-trade latency flow with ms budgets.'))

    story.append(h2('Context Diagram — External Entities'))
    story.append(p(
        'The system exchanges seven labeled flows with four external entities. The MT5 broker '
        'is the primary execution venue: ticks and fill confirmations flow in (F1), orders flow '
        'out (F2). The news and economic feed provides scheduled event data and real-time news '
        'sentiment (F3) used by the news-aware risk gate and the news sentiment engine. The '
        'license server is the source of truth for tenant entitlements: heartbeats flow out (F4), '
        'signed JWTs flow back (F5). The operator console is the human interface: alerts and '
        'metrics flow out (F6), kill switch and risk override commands flow in (F7). All flows '
        'except F1 and F2 are TLS-encrypted and authenticated; F1 and F2 use the MT5 terminal\'s '
        'internal protocol which is broker-managed.'
    ))

    story.append(h2('Level-1 Diagram — Internal Processes'))
    story.append(p(
        'The seven internal processes correspond to the service layers (with execution and risk '
        'collapsed into single processes for diagram clarity). Each process has well-defined '
        'inputs and outputs, and the data stores (D1-D5) provide the persistence boundary. The '
        'critical property to notice is that P5 (Risk) is a synchronous gate on the path from '
        'P4 (Signal) to P6 (Execute) — no order can reach the broker without passing through '
        'the risk process. This is the structural enforcement of the capital-preservation-first '
        'tenet.'
    ))
    story.append(table([
        ['Process', 'Inputs', 'Outputs', 'Data Stores Touched', 'Synchronous/Async'],
        ['P1 Ingest', 'F1, F3 (external feeds)', 'raw ticks → P2, → D1', 'D1 (write)', 'Async push'],
        ['P2 Normalize', 'raw ticks from P1', 'norm ticks → P3, → D1', 'D1 (write)', 'Async push'],
        ['P3 Feature', 'norm ticks from P2', 'features → P4, → D2', 'D2 (write)', 'Async push'],
        ['P4 Signal', 'features from P3', 'signal → P5', '—', 'Async push'],
        ['P5 Risk', 'signal from P4, exposure from D3', 'approved/rejected → P6', 'D3 (read), D4 (read)', 'SYNCHRONOUS'],
        ['P6 Execute', 'approved order from P5', 'order to broker, fills → P7', 'D3 (write)', 'Synchronous'],
        ['P7 Persist', 'fills from P6', 'trade + audit records', 'D4 (write), D5 (write)', 'Async'],
    ], col_widths=[20, 35, 35, 45, 30]))
    story.append(Spacer(1, 8))

    story.append(h2('Tick-to-Trade Latency Flow'))
    story.append(p(
        'The warm-path latency flow shows the millisecond budget for each stage of the hot path. '
        'The total internal latency (excluding the broker round-trip) is 1.70 ms at p50, '
        '4.80 ms at p99, and 12.0 ms at p99.9. The system is designed to a p99 budget of five '
        'milliseconds; the p99.9 budget is exceeded, which is acceptable as long as it is not '
        'sustained. A spike detector monitors the p99.9 latency over a ten-second sliding '
        'window; if it exceeds twenty-five milliseconds for the full window, the system '
        'automatically throttles non-critical feature computation and pages the operator.'
    ))
    story.append(p(
        'The largest budget consumers are the MT5 callback (0.30 ms, broker-side overhead we '
        'cannot control), the FeatureEngine (0.40 ms, the price of computing three hundred '
        'features per tick), and the MT5 send (0.50 ms, the cost of submitting an order through '
        'the MT5 terminal API). The risk gate is comparatively cheap at 0.15 ms because it '
        'performs only O(1) checks against pre-computed exposure. Strategies for reducing '
        'latency further are discussed in the Latency Budget chapter.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 9 — Deliverable 4: Module Dependency Graph
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Deliverable 4 — Module Dependency Graph', 9))
    story.append(p(
        'The module dependency graph is the structural contract of the architecture. It shows '
        'which modules import or call which, organized by layer. The graph is acyclic by '
        'construction — cyclic dependencies fail the build — and downward-only — modules at '
        'layer N may only depend on modules at layer N-1 or below. This is the formal expression '
        'of the layering rule that gives risk its structural veto power.'
    ))
    story.append(diagram('d04_module_deps.png', width_mm=170))
    story.append(caption('Figure 9.1 — Module dependency graph. Pink boxes (L1, L3, L5) are C++; green boxes (L2, L4) are Python. Solid arrows are data-plane dependencies; dashed are observability/audit.'))

    story.append(h2('Critical Edges & Their Rationale'))
    story.append(p(
        'Several dependency edges are worth highlighting because they encode critical architectural '
        'guarantees. The PreTradeRiskGate depends on the ExposureAggregator and the SessionCalendar '
        '(for news blackout), but NOT on the StrategyCoordinator — risk has no knowledge of which '
        'strategy generated the signal it is evaluating. This independence is what makes the risk '
        'veto trustworthy: there is no code path by which a strategy can influence the risk '
        'decision. The KillSwitchController depends on the OrderManager via a dedicated reverse '
        'signal bus, not the main event bus — this guarantees that the kill switch can reach the '
        'order manager even if the main bus is saturated or stuck.'
    ))
    story.append(p(
        'The StrategyCoordinator depends on SignalEngine, RegimeDetector, and MLInferenceEngine, '
        'and is consumed by the PreTradeRiskGate. This means the strategy layer is the single '
        'point at which signals are converted into actionable orders, making it the natural place '
        'for risk budget allocation, strategy arbitration, and conflict resolution. The audit '
        'store is a terminal sink — nothing depends on it — which means it can never block the '
        'hot path; if the audit store is slow, audit events queue in memory and flush when the '
        'store catches up.'
    ))

    story.append(h2('Module Inventory'))
    story.append(table([
        ['Module', 'Layer', 'Imports', 'Imported By', 'Purpose'],
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
    ], col_widths=[35, 14, 45, 40, 36]))
    story.append(Spacer(1, 8))

    story.append(h2('Layering Rule Enforcement'))
    story.append(p(
        'The layering rule is enforced automatically by an architecture linter that runs in CI. '
        'The linter parses CMakeLists.txt and Python import statements, builds the dependency '
        'graph, and rejects any commit that introduces a cyclic dependency or an upward '
        'dependency (a layer N module importing a layer N+1 module). The linter is configured '
        'in <font name="DejaVuSans">ci/arch_lint.py</font> and is part of the mandatory Gate 1 '
        'in the CI pipeline. Exceptions require an ADR and CTO approval; in practice no exception '
        'has been granted in the v1.0 cycle.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 10 — Deliverable 5: UML Class Diagrams
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Deliverable 5 — Class Diagrams (UML)', 10))
    story.append(p(
        'Three UML class diagrams document the core domain model, the risk subsystem, and the '
        'execution subsystem. The diagrams use standard UML 2.5 notation: solid arrows with '
        'hollow triangle heads for inheritance, solid arrows with filled diamond heads for '
        'composition, solid arrows with hollow diamond heads for aggregation, and dashed arrows '
        'for dependency. Visibility is denoted + (public), - (private), # (protected). Abstract '
        'classes are marked with the «abstract» stereotype; interfaces with «interface».'
    ))
    story.append(diagram('d05_class_diagrams.png', width_mm=170))
    story.append(caption('Figure 10.1 — Three UML class diagrams: (a) core domain model, (b) risk subsystem, (c) execution subsystem.'))

    story.append(h2('Core Domain Model'))
    story.append(p(
        'The core domain model captures the fundamental value objects and aggregates of the '
        'trading system. <b>Tick</b> is an immutable value object representing a single market '
        'quote: timestamp, symbol, bid, ask, last, and volume. <b>Bar</b> aggregates ticks into '
        'OHLCV bars over a configurable timeframe. <b>Order</b> is an abstract base class with '
        'three concrete subclasses: MarketOrder (immediate execution at best available price), '
        'LimitOrder (execution at a specified price or better), and StopOrder (triggered when '
        'the market reaches a stop price). <b>Fill</b> is an immutable event recording the '
        'execution of (part of) an order, carrying the fill price, quantity, commission, and '
        'realized PnL. <b>Position</b> is an aggregate root tracking the net quantity, average '
        'price, unrealized and realized PnL, and maximum adverse excursion for one symbol. '
        '<b>Signal</b> is the output of a strategy: a direction, a strength, a suggested '
        'quantity, and optional stop and target prices. <b>StrategyContext</b> is the per-strategy '
        'sandbox providing features, current position, clock, and risk budget, and the only '
        'legal channel for a strategy to emit signals.'
    ))

    story.append(h2('Risk Subsystem'))
    story.append(p(
        'The risk subsystem is organized around the <b>IRiskGate</b> interface, which defines '
        'the synchronous veto contract: every gate must implement <font name="DejaVuSans">check(ctx: RiskContext): RiskDecision</font>. '
        'Two concrete implementations exist: <b>PreTradeRiskGate</b> runs synchronously on every '
        'order, checking position size, leverage, daily trade count, news blackout windows, and '
        'margin floor. <b>PostTradeRiskMonitor</b> runs asynchronously, observing fills and '
        'equity updates and firing circuit breakers when drawdown, loss streak, or slippage '
        'thresholds are breached. The <b>ExposureAggregator</b> maintains net and gross exposure '
        'in real time, with Value-at-Risk and correlation-adjusted exposure calculations '
        'available on demand. The <b>KillSwitchController</b> is a singleton that holds an atomic '
        'armed flag, a triggered timestamp, and a reason string; engaging it halts new orders, '
        'flattens positions, cancels pending orders, and notifies the operator. The '
        '<b>RiskDecision</b> value object carries the verdict (APPROVE, REJECT, THROTTLE), a '
        'reason code, a human-readable message, an optional reduced quantity (for THROTTLE), '
        'and a serializable audit blob.'
    ))

    story.append(h2('Execution Subsystem'))
    story.append(p(
        'The execution subsystem is organized around the <b>IExecutor</b> interface, which '
        'abstracts the broker: <font name="DejaVuSans">submit(o: Order): FillPromise</font>, '
        '<font name="DejaVuSans">cancel(id: OrderId): bool</font>, <font name="DejaVuSans">modify(id: OrderId, m: Mod): bool</font>. '
        'Three concrete implementations exist: <b>MT5Executor</b> (production, binding to the '
        'MetaTrader 5 terminal via Wine), <b>SimulatedExecutor</b> (backtest, with injectable '
        'slippage, commission, and latency), and <b>FIXExecutor</b> (planned for v1.1, speaking '
        'FIX 4.4 to direct-access brokers). The <b>OrderRouter</b> selects a venue per order '
        'and handles failover across the configured chain. The <b>OrderManager</b> is the '
        'aggregate root owning the order state machine, the router, the risk gate, and the '
        'fill reconciler. The <b>FillReconciler</b> periodically compares local order state '
        'against broker snapshots to detect orphans and phantoms. The <b>ISlippageModel</b> '
        'interface has four implementations: LinearSlippageModel (constant bps), '
        'SquareRootImpactModel (Almgren-Chriss square root), AlmgrenChrissModel (full '
        'optimal execution), and LearnedSlippageModel (ML-trained on historical fills).'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 11 — Deliverable 6: Deployment Architecture
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Deliverable 6 — Deployment Architecture', 11))
    story.append(p(
        'The deployment architecture is a three-zone high-availability topology designed for '
        '99.95% uptime with sub-fifteen-minute mean time to recovery. The primary zone (Z1) '
        'runs in NY4 (Equinix New York), colocated with the broker matching engines for minimum '
        'network latency. The hot-standby zone (Z2) runs in EQ4 (Equinix NY2), a different '
        'physical facility in the same metropolitan area for low-latency replication with '
        'physical fault isolation. The disaster-recovery zone (Z3) runs in LD4 (Equinix London), '
        'geographically remote to survive metro-wide disasters, accepting higher replication '
        'latency in exchange for true geographic redundancy.'
    ))
    story.append(diagram('d06_deployment.png', width_mm=170))
    story.append(caption('Figure 11.1 — Three-zone deployment topology. Z1 active, Z2 hot-standby (<3s failover), Z3 cold-DR (<15min RTO). WireGuard mesh between zones.'))

    story.append(h2('Zone Roles & Failover'))
    story.append(h3('Z1 — Primary (NY4)'))
    story.append(p(
        'The primary zone is the active trading cluster. All services run hot: titan-core on '
        'CPU 2-3, titan-strategy on CPU 4-7, mt5-terminal on CPU 0-1, redis on CPU 8, '
        'TimescaleDB and the monitoring stack on CPU 9-11. The VRRP master priority is 200, '
        'making Z1 the default gateway for inbound broker connections. The public IP is '
        'allowlisted with the broker; only MT5 broker traffic and WireGuard (port 51820) are '
        'accepted by nftables. State is replicated synchronously to Z2 via Redis Sentinel and '
        'TimescaleDB streaming replication; the warm standby in Z2 is never more than one '
        'second behind.'
    ))
    story.append(h3('Z2 — Hot-Standby (EQ4)'))
    story.append(p(
        'The hot-standby zone mirrors Z1 but with services in a warm state — titan-core and '
        'titan-strategy are running but not actively trading, ready to take over within three '
        'seconds. The VRRP backup priority is 100. On Z1 failure (detected via VRRP health '
        'probes and application-level liveness checks), Z2 promotes to master, takes over the '
        'VRRP virtual IP, and begins trading. The MT5 terminal in Z2 uses a separate sub-account '
        'configured with the broker for failover, avoiding position conflicts. State is loaded '
        'from Redis (already replicated) within milliseconds of promotion.'
    ))
    story.append(h3('Z3 — Disaster Recovery (LD4)'))
    story.append(p(
        'The DR zone is geographically remote, accepting seventy-millisecond replication '
        'latency in exchange for true geographic redundancy. Z3 runs a cold-standby image: '
        'titan-core is paused, TimescaleDB is replaying WAL archives with sixty-second lag, '
        'Redis is an asynchronous replica with five-second lag. VRRP is disabled in Z3 — '
        'failover to Z3 is a manual decision taken only when both Z1 and Z2 are unavailable. '
        'The Recovery Time Objective (RTO) for Z3 is fifteen minutes (the time to confirm the '
        'disaster, manually failover, and resume trading); the Recovery Point Objective (RPO) '
        'is sixty seconds (the maximum data loss from WAL lag).'
    ))

    story.append(h2('Bill of Materials'))
    story.append(table([
        ['Zone', 'Location', 'Hardware', 'Monthly Cost', 'Purpose'],
        ['Z1 Primary', 'NY4 Equinix', 'Dedicated Ryzen 9 3900X, 12c/32GB, 2×1TB NVMe', '$280', 'Active trading'],
        ['Z2 Hot-Standby', 'EQ4 Equinix', 'Dedicated Ryzen 7 3700X, 8c/32GB, 1TB NVMe', '$180', '<3s failover'],
        ['Z3 DR', 'LD4 Equinix', 'Hetzner CX41 VPS, 8vCPU/16GB, 160GB SSD', '$45', '<15min RTO'],
        ['License SaaS', 'AWS eu-west-1', 't3.medium, 2vCPU/4GB, 50GB', '$30', 'JWT issuance'],
        ['Backup S3', 'AWS eu-west-1', 'S3 IA, 500GB', '$15', 'WAL archive, snapshots'],
        ['Total (single tenant)', '—', '—', '~$550', '—'],
        ['Per additional tenant', '—', '+$0 (shared infra)', '+$80 license server load', 'Marginal cost'],
    ], col_widths=[20, 24, 60, 30, 36]))
    story.append(Spacer(1, 8))

    story.append(h2('Network Architecture'))
    story.append(p(
        'All inter-zone communication flows over a WireGuard full mesh, with pre-shared keys '
        'rotated every thirty days via Vault. The WireGuard tunnels carry Redis replication, '
        'TimescaleDB streaming, state sync, and operator console traffic. Broker connections '
        '(MT5, FIX) use direct internet paths with nftables restricting source IPs to the '
        'broker\'s published ranges. The monitoring stack (Prometheus, Loki, Grafana) is '
        'federated: Z2 scrapes Z1, Z3 scrapes Z1 and Z2 asynchronously, providing a complete '
        'view from any zone even during a partial outage.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 12 — Deliverable 7: VPS Architecture
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Deliverable 7 — VPS Architecture', 12))
    story.append(p(
        'The VPS architecture is the single-host deep dive: how the operating system, kernel, '
        'container runtime, and processes are configured on the primary trading host (Z1). '
        'The goal is to extract predictable, low-latency behavior from commodity hardware by '
        'eliminating sources of jitter: kernel preemption, memory allocation stalls, network '
        'interrupt storms, and CPU frequency scaling. The configuration is captured as code '
        '(Ansible playbooks, systemd unit files, sysctl profiles) so that it can be reproduced '
        'identically across Z1, Z2, and any future primary host.'
    ))
    story.append(diagram('d07_vps.png', width_mm=170))
    story.append(caption('Figure 12.1 — Single-VPS architecture: hardware, OS, runtime, and CPU allocation map with kernel/sysctl tuning table.'))

    story.append(h2('CPU Allocation Strategy'))
    story.append(p(
        'The host has twelve physical cores split across two NUMA nodes. The allocation '
        'strategy pins latency-critical services to dedicated cores with hyper-threading '
        'disabled, isolates those cores from kernel scheduling, and confines all other '
        'workloads to the remaining cores. The mt5-terminal container runs on CPU 0-1 with '
        'SMT disabled (to avoid contention between the two hyperthreads), handling the Wine '
        'overhead and broker callback latency. The titan-core container runs on CPU 2-3, '
        'isolated from kernel scheduling via the <font name="DejaVuSans">isolcpus</font> kernel '
        'parameter, with NO_HZ_FULL to eliminate timer ticks. The titan-strategy container runs '
        'on CPU 4-7 (four cores), providing headroom for Python GIL contention and PyTorch '
        'inference. Redis runs on CPU 8, and the monitoring stack (Prometheus, Loki, Grafana) '
        'runs on CPU 9-11.'
    ))
    story.append(p(
        'CPU isolation is achieved through a combination of kernel parameters '
        '(<font name="DejaVuSans">isolcpus=2,3 nohz_full=2,3 rcu_nocbs=2,3</font>) and systemd '
        'unit directives (<font name="DejaVuSans">CPUAffinity=2,3 AllowedCPUs=2,3</font>). '
        'The kernel\'s RCUs are offloaded to other CPUs via <font name="DejaVuSans">rcu_nocbs</font>, '
        'eliminating RCU callback stalls on the isolated cores. Timer ticks are eliminated via '
        '<font name="DejaVuSans">nohz_full</font>, which is essential for sub-millisecond latency '
        'predictability. The result is that CPU 2-3 experience less than one kernel preemption '
        'per second under load, compared to thousands per second on a default-configured kernel.'
    ))

    story.append(h2('Kernel & sysctl Tuning'))
    story.append(p(
        'The kernel is Ubuntu 22.04 LTS with the PREEMPT_RT patch applied for full kernel '
        'preemption. The kernel command line includes parameters for CPU isolation, hugepages, '
        'C-state control, and watchdog disabling. The sysctl profile disables swap, caps dirty '
        'pages to prevent write stalls, enlarges network buffers to absorb tick bursts, and '
        'disables NUMA auto-balancing in favor of manual cpuset control. The complete sysctl '
        'table is shown in Figure 12.1; the most consequential entries are '
        '<font name="DejaVuSans">vm.swappiness=1</font> (effectively disable swap), '
        '<font name="DejaVuSans">kernel.sched_rt_runtime_us=-1</font> (allow RT tasks to run '
        'beyond the 95% default window), and <font name="DejaVuSans">net.core.rmem_max=134217728</font> '
        '(128MB socket recv buffer to absorb tick bursts).'
    ))

    story.append(h2('Memory & Storage'))
    story.append(p(
        'The host has 32 GB of DDR4 RAM split evenly across two NUMA nodes (16 GB per node). '
        'Four gigabytes are reserved as 2MB hugepages (2048 pages), used by titan-core for '
        'lock-free queues and ring buffers to eliminate page-fault overhead. Swap is effectively '
        'disabled (<font name="DejaVuSans">vm.swappiness=1</font>) — the OOM killer is preferred '
        'over swap-stall, because a stalled trading process is far more dangerous than a killed '
        'one. The OOM-killer configuration pins titan-core as the lowest-priority kill target, '
        'so monitoring and logging are killed first under memory pressure. Storage is two 1 TB '
        'NVMe drives in RAID1, formatted XFS with <font name="DejaVuSans">noatime</font> and '
        '<font name="DejaVuSans">allocsize=64M</font> for the tick store. The I/O scheduler is '
        'set to <font name="DejaVuSans">none</font> for NVMe (the device has its own queue '
        'management), and direct I/O is used for the tick ring buffer to bypass the page cache.'
    ))

    story.append(h2('systemd Unit Configuration'))
    story.append(p(
        'Each TITAN service runs as a systemd unit with explicit CPU affinity, NUMA policy, '
        'memory limits, I/O priority, and security hardening. The titan-core unit specifies '
        '<font name="DejaVuSans">CPUAffinity=2,3</font>, <font name="DejaVuSans">NUMAPolicy=bind</font> '
        'with <font name="DejaVuSans">NUMAMask=0</font>, <font name="DejaVuSans">Nice=-11</font>, '
        '<font name="DejaVuSans">IOSchedulingClass=realtime</font>, and memory limits of '
        '4 GB high / 6 GB max. Security hardening includes '
        '<font name="DejaVuSans">NoNewPrivileges</font>, '
        '<font name="DejaVuSans">ProtectSystem=strict</font>, '
        '<font name="DejaVuSans">ProtectHome</font>, <font name="DejaVuSans">PrivateTmp</font>, '
        'and <font name="DejaVuSans">ReadWritePaths</font> restricted to '
        '<font name="DejaVuSans">/var/lib/titan</font> and <font name="DejaVuSans">/var/log/titan</font>. '
        'The full unit file is reproduced in Figure 12.1.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 13 — Deliverable 8: Production Architecture
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Deliverable 8 — Production Architecture', 13))
    story.append(p(
        'The production architecture documents the end-to-end operating loop: how code moves '
        'from developer laptop through CI/CD to canary deployment to full production, how the '
        'system is observed in production, how operators interact with it, and how the daily, '
        'weekly, monthly, and quarterly operational rhythms are structured. This is the '
        'architecture of running the system, not just building it.'
    ))
    story.append(diagram('d08_production.png', width_mm=170))
    story.append(caption('Figure 13.1 — Production architecture: trading cluster, CI/CD pipeline with backtest regression gate, operator console, and 24h operating cycle.'))

    story.append(h2('CI/CD Pipeline'))
    story.append(p(
        'The CI/CD pipeline is built on GitLab CI with ArgoCD for deployment orchestration. '
        'Every pull request runs through five gates: (1) static analysis and unit tests '
        '(clang-tidy, pylint, mypy, pytest, GoogleTest), (2) integration tests with Pact '
        'contracts, (3) component tests with testcontainers, (4) the mandatory backtest '
        'regression gate, and (5) image build and signing with cosign. Only builds that pass '
        'all five gates are promoted to the canary stage, where Argo Rollouts deploys the '
        'new version to ten percent of traffic for thirty minutes, then fifty percent for one '
        'hour, then one hundred percent. Automatic rollback triggers if latency p99 increases '
        'by more than fifty percent or any risk gate breaches during the canary window.'
    ))
    story.append(p(
        'The backtest regression gate is the most consequential control. It runs a twenty-four '
        'month walk-forward backtest with the last twenty percent as out-of-sample, plus a '
        'thousand-path Monte Carlo simulation. The build must beat the previous build on all '
        'five target metrics (PF, Sharpe, MaxDD, Recovery, RoR) on the out-of-sample window. '
        'This prevents gradual metric decay across releases: a build that improves Sharpe but '
        'worsens MaxDD is rejected, forcing the team to find solutions that improve all '
        'dimensions simultaneously. The gate is enforced by the pipeline configuration, not '
        'by human discretion — there is no override.'
    ))

    story.append(h2('Observability Stack'))
    story.append(p(
        'Observability is built in from day one and is non-negotiable. Every service emits '
        'Prometheus metrics (scraped every fifteen seconds, five-day retention on the local '
        'instance, federated to Z2 and Z3), structured JSON logs (collected by Promtail and '
        'stored in Loki with one-year retention on S3 backend), and OpenTelemetry traces '
        '(sampled at one percent in production, one hundred percent in canary, with tick-to-trade '
        'spans for latency analysis). Grafana provides the unified dashboard view, with '
        'separate panels for traders (real-time PnL, exposure, open positions), supervisors '
        '(risk metrics, gate rejection rates, audit log search), and SREs (latency percentiles, '
        'error rates, resource utilization). AlertManager routes alerts to PagerDuty for P1/P2 '
        'incidents and to Telegram for P3 informational alerts.'
    ))

    story.append(h2('Operator Actions & Authorization'))
    story.append(p(
        'Operator actions are categorized by impact and require different authorization levels. '
        'High-impact actions — engaging the kill switch, overriding risk limits, activating a '
        'new strategy — require the two-person rule: a TRADER initiates and a SUPERVISOR '
        'approves within five minutes or the action expires. All actions are recorded in the '
        'immutable audit store with operator identity, timestamp, before/after state, and '
        'reason code. Manual order placement is disabled in production; all orders must flow '
        'through the risk gate. The complete authorization matrix is shown in Figure 13.1.'
    ))

    story.append(h2('24-Hour Operating Cycle'))
    story.append(p(
        'The system trades XAUUSD around the clock from Sunday 22:00 UTC to Friday 22:00 UTC, '
        'with a daily maintenance window during the 22:00-22:05 broker rollover (no new orders). '
        'The Asian session (00:00-07:00 UTC) typically has lower volatility and tighter ranges; '
        'the European session (07:00-16:00 UTC) is the peak liquidity window; the US session '
        '(16:00-22:00 UTC) overlaps with Europe for the first few hours and produces the '
        'highest volatility, especially around US economic releases. News blackout windows '
        '(FOMC ±15 min, NFP ±10 min, CPI ±5 min, Powell/ECB speeches ±10 min) are automatically '
        'enforced by the risk gate. Daily reporting runs at 00:30 UTC, generating the previous '
        'day\'s PnL, trade log, slippage TCA, and risk metric snapshot, emailed to the licensee '
        'and uploaded to the investor portal.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 14 — Deliverable 9: Testing Architecture
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Deliverable 9 — Testing Architecture', 14))
    story.append(p(
        'The testing architecture is a five-layer pyramid with hard gates at each CI/CD stage. '
        'The pyramid shape reflects the relative volume of tests: roughly seventy percent unit, '
        'twenty percent integration, six percent component, three percent backtest regression, '
        'and one percent chaos. Each layer has a distinct purpose, a distinct cost, and a '
        'distinct cadence — running all chaos experiments on every PR would be impractical, '
        'but running only unit tests on every PR would be irresponsible.'
    ))
    story.append(diagram('d09_testing.png', width_mm=170))
    story.append(caption('Figure 14.1 — Testing pyramid (5 layers) and CI/CD pipeline gates with thresholds.'))

    story.append(h2('Unit Tests'))
    story.append(p(
        'Unit tests cover pure functions and isolated components with all dependencies mocked. '
        'The C++ side uses GoogleTest with gmock; the Python side uses pytest with '
        'pytest-asyncio for async code and hypothesis for property-based testing. The target '
        'is eighty-five percent line coverage with one hundred percent coverage of critical '
        'paths (risk gates, order state machine, PnL calculation). Unit tests must execute in '
        'under sixty seconds total; tests that exceed this are candidates for refactoring or '
        'promotion to integration. Property-based tests are mandatory for any function with '
        'invariants (e.g., "for any tick t, TickNormalizer.normalize(t) is idempotent").'
    ))

    story.append(h2('Integration Tests'))
    story.append(p(
        'Integration tests verify service-to-service contracts using the Pact framework. Each '
        'service publishes a contract describing the requests it makes to its dependencies and '
        'the responses it expects; dependencies verify that they can satisfy those contracts. '
        'This catches breaking API changes early — a producer that changes its response shape '
        'will break its consumers\' contracts in CI before reaching production. Integration '
        'tests use a real ZeroMQ event bus but a mock broker, allowing end-to-end event flow '
        'verification without broker dependencies. The target is one hundred percent coverage '
        'of critical paths (signal → risk → order, fill → position → exposure).'
    ))

    story.append(h2('Component Tests'))
    story.append(p(
        'Component tests exercise a single service with its real infrastructure dependencies '
        'via testcontainers: Redis, PostgreSQL/TimescaleDB, and MinIO (for S3-compatible audit '
        'storage). The broker is still mocked. These tests catch infrastructure integration '
        'bugs that mock-based unit tests cannot: serialization issues, schema mismatches, '
        'transaction boundary problems. The target is seventy percent line coverage per '
        'service in the component test suite. Tests run in parallel across services to keep '
        'total wall time under ten minutes.'
    ))

    story.append(h2('Backtest Regression'))
    story.append(p(
        'The backtest regression gate is the most important and most expensive test layer. It '
        'runs a full twenty-four month walk-forward backtest with the last twenty percent as '
        'out-of-sample, plus a thousand-path Monte Carlo simulation for risk of ruin. The '
        'build must beat the previous build on all five target metrics (PF ≥ 2.0, Sharpe ≥ 2.0, '
        'MaxDD ≤ 5%, Recovery ≥ 5, RoR ≤ 1%) on the out-of-sample window. The full backtest '
        'runs on every PR (approximately thirty minutes wall time) and a smaller smoke '
        'backtest (three months, no Monte Carlo) runs nightly on the main branch. Builds that '
        'fail the gate cannot be promoted to canary — there is no override.'
    ))

    story.append(h2('Chaos Engineering'))
    story.append(p(
        'Chaos engineering is the top of the pyramid: weekly game-day exercises that inject '
        'realistic failures into a production-like staging environment. We use Gremlin for '
        'CPU contention, network latency, and packet loss, plus custom fault injectors for '
        'broker disconnect, partial fills, slippage spikes, and Z1→Z2 VRRP failover. The '
        'goal is not to verify that the system survives (we already believe it does) but to '
        'discover failure modes we have not anticipated. Every chaos experiment produces a '
        'postmortem regardless of outcome; experiments that reveal bugs feed back into unit '
        'and integration tests to prevent regression. Quarterly, a full DR drill exercises '
        'the Z1→Z3 failover path with RTO under fifteen minutes as the success criterion.'
    ))

    story.append(h2('Test Matrix'))
    story.append(p(
        'The complete test matrix is shown in Figure 14.1. The key columns are the gate '
        'threshold (what must be true for the test to pass) and the cadence (when the test '
        'runs). The matrix is reviewed quarterly by the QA lead and updated as new test types '
        'are added or thresholds are tightened. Coverage is reported weekly to the engineering '
        'team and monthly to the architecture review board.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 15 — Latency Budget & Performance Engineering
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Latency Budget & Performance Engineering', 15))
    story.append(p(
        'The latency budget is the contract between the system\'s performance aspirations and '
        'its physical reality. The warm-path p99 target is five milliseconds from broker '
        'callback to order submission, with p99.9 acceptable at twenty-five milliseconds as '
        'long as it is not sustained. This chapter breaks down the budget per stage, explains '
        'the engineering techniques used to meet it, and describes the mitigation strategies '
        'when the budget is breached.'
    ))
    story.append(diagram('d10_latency.png', width_mm=170))
    story.append(caption('Figure 15.1 — Tick-to-trade latency budget breakdown with p50/p99/p99.9 per stage.'))

    story.append(h2('Per-Stage Budget Breakdown'))
    story.append(p(
        'The warm path consists of seven stages. The MT5 callback (0.30 ms p50) is the time '
        'from when the broker sends a tick to when our code receives it in the MT5Bridge; we '
        'have limited control over this as it includes broker-side processing and MT5 terminal '
        'overhead. The normalizer (0.05 ms) is the cheapest stage, performing O(1) deduplication '
        'and decimal alignment via AVX2 SIMD. The FeatureEngine (0.40 ms) is the most expensive '
        'internal stage, computing over three hundred features per tick via vectorized NumPy '
        'operations and Numba-JIT-compiled hot paths. The SignalEngine (0.20 ms) combines '
        'features into a directional signal via ensemble methods, with ML inference via ONNX '
        'runtime. The PreTradeRiskGate (0.15 ms) performs O(1) checks against pre-computed '
        'exposure using atomic reads. The OrderManager (0.10 ms) translates the approved signal '
        'into an order and pushes it onto the SPSC queue to the MT5 send thread. The MT5 send '
        '(0.50 ms) is the second-most expensive stage, dominated by Wine overhead in '
        'translating the MT5 terminal API call.'
    ))

    story.append(h2('Mitigation Strategies per Stage'))
    story.append(table([
        ['Stage', 'p99 (ms)', 'Budget (ms)', 'Mitigation if Breached'],
        ['MT5 callback', '0.80', '1.00', 'Dedicated thread, increase recv buffer, SMT off'],
        ['Normalizer', '0.10', '0.20', 'AVX2 SIMD, branchless decimal ops'],
        ['FeatureEngine', '1.20', '1.00', 'Cache features, drop non-critical on spike'],
        ['SignalEngine', '0.60', '0.50', 'ONNX runtime, batch inference, no Python'],
        ['PreTradeRiskGate', '0.30', '0.30', 'O(1) lookups, atomic exposure reads'],
        ['OrderManager', '0.20', '0.20', 'SPSC queue, pre-allocated objects'],
        ['MT5 send', '1.50', '1.50', 'Bypass Wine, consider FIX adapter'],
        ['TOTAL internal', '4.80', '5.00', 'Spike detector throttles features on breach'],
    ], col_widths=[35, 22, 28, 85]))
    story.append(Spacer(1, 8))

    story.append(h2('Performance Engineering Techniques'))
    story.append(h3('CPU Pinning & Isolation'))
    story.append(p(
        'The titan-core process is pinned to CPU 2-3 via systemd CPUAffinity, with the kernel '
        'instructed to never schedule other tasks there via isolcpus=2,3. NO_HZ_FULL eliminates '
        'timer ticks on those cores, and rcu_nocbs=2,3 offloads RCU callbacks to other CPUs. '
        'The result is that titan-core experiences fewer than one kernel preemption per second, '
        'compared to thousands on a default kernel. This is the single most impactful change '
        'for latency predictability.'
    ))
    story.append(h3('Lock-Free Queues'))
    story.append(p(
        'Inter-thread communication uses the moodycamel ConcurrentQueue, a lock-free multi-producer '
        'multi-consumer queue with bounded latency. The hot path between the MT5 callback thread '
        'and the normalizer thread is a single-producer single-consumer (SPSC) queue, which is '
        'even cheaper — a single atomic load and store per operation. No mutexes are used anywhere '
        'on the hot path; this eliminates the priority inversion and contention jitter that '
        'mutex-based designs suffer from under load.'
    ))
    story.append(h3('Zero-Copy Serialization'))
    story.append(p(
        'All inter-process and inter-language messages are serialized with FlatBuffers, which '
        'permits zero-copy access to fields without deserialization. This is critical for the '
        'Python↔C++ boundary, where messages must cross the PyO3 bridge without copying. The '
        'FlatBuffer schema is the authoritative wire format for the entire system; new message '
        'types are added by editing the schema in src/ffi/flatbuffers/ and regenerating bindings '
        'for both languages.'
    ))
    story.append(h3('GIL Mitigation'))
    story.append(p(
        'The Python GIL is the most common source of latency spikes in Python-based trading '
        'systems. TITAN XAU AI mitigates this through several techniques: the hot path runs in '
        'C++ (no GIL), the Python intelligence layer uses uvloop for the event loop (which '
        'releases the GIL during I/O), and CPU-bound Python work is moved to a process pool '
        'via concurrent.futures. PyTorch inference releases the GIL during the forward pass, '
        'allowing concurrent feature computation. The remaining GIL-holding paths are profiled '
        'monthly with py-spy, and any path that holds the GIL for more than one millisecond is '
        'a candidate for Cython compilation.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 16 — Non-Functional Requirements
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Non-Functional Requirements', 16))
    story.append(p(
        'Non-functional requirements (NFRs) specify the qualities the system must exhibit, '
        'as distinct from the functional requirements that specify what the system does. NFRs '
        'are measurable, owned, and verified in CI. A build that meets all functional '
        'requirements but fails an NFR gate is rejected. This chapter enumerates the eight NFR '
        'categories that apply to TITAN XAU AI, with specific targets, measurement methods, '
        'and owners.'
    ))

    story.append(table([
        ['Category', 'NFR', 'Target', 'Measurement', 'Owner', 'Gate'],
        ['Performance', 'Tick-to-trade p99', '< 5 ms', 'OpenTelemetry span, p99 over 1h', 'SRE', 'CI canary'],
        ['Performance', 'Tick throughput', '50k ticks/s sustained', 'Locust load test, 1h', 'SRE', 'Nightly'],
        ['Reliability', 'Uptime', '99.95%', 'Prometheus up query, monthly', 'SRE', 'SLA report'],
        ['Reliability', 'MTTR', '< 15 min', 'Incident timestamp → recovery', 'SRE', 'Quarterly DR drill'],
        ['Availability', 'Failover time Z1→Z2', '< 3 s', 'VRRP probe + app-level check', 'SRE', 'Monthly drill'],
        ['Availability', 'Failover time Z1→Z3 (DR)', '< 15 min', 'Manual DR drill', 'SRE', 'Quarterly'],
        ['Security', 'TLS version', 'TLS 1.3 only', 'sslyze scan', 'Security', 'Every PR'],
        ['Security', 'Broker cred rotation', '≤ 30 days', 'Vault lease check', 'Security', 'Nightly'],
        ['Security', 'Critical vuln count', '0 unresolved HIGH/CRITICAL', 'Trivy + Snyk', 'Security', 'Every PR'],
        ['Observability', 'Metric scrape interval', '15 s', 'Prometheus config check', 'SRE', 'CI'],
        ['Observability', 'Log retention', '1 year', 'Loki config check', 'SRE', 'CI'],
        ['Observability', 'Trace sample rate (canary)', '100%', 'OTel config check', 'SRE', 'CI'],
        ['Scalability', 'Tenants per cluster', 'Up to 20', 'Load test, multi-tenant', 'SRE', 'Quarterly'],
        ['Scalability', 'Strategies per tenant', 'Up to 10 (Enterprise)', 'Config validation', 'Eng', 'CI'],
        ['Maintainability', 'Module LOC', '< 500 per module', 'cloc report', 'Eng', 'CI'],
        ['Maintainability', 'Test coverage', '≥ 80% line', 'Coverage report', 'Eng', 'Every PR'],
        ['Maintainability', 'Lint findings', '0 critical', 'clang-tidy, pylint', 'Eng', 'Every PR'],
        ['Compliance', 'Audit log immutability', 'Tamper-evident', 'Hash chain verify', 'Compliance', 'Nightly'],
        ['Compliance', 'Trade reconstruction', '< 5 min for any day', 'Replay from audit log', 'Compliance', 'Quarterly'],
        ['Compliance', 'License enforcement', 'Hard shutdown on revoke', 'License test in CI', 'Eng', 'Every PR'],
    ], col_widths=[20, 32, 30, 35, 14, 22]))
    story.append(Spacer(1, 8))

    story.append(h2('Availability Math'))
    story.append(p(
        'The 99.95% uptime target translates to approximately four hours and twenty-two '
        'minutes of allowed downtime per year. This budget is consumed by planned maintenance '
        '(approximately one hour per year for cert rotations and DR drills) and unplanned '
        'incidents (the remaining three hours). To stay within budget, the system is designed '
        'for sub-three-second failover from Z1 to Z2 (consuming seconds per failover, not '
        'minutes) and sub-fifteen-minute recovery from a complete primary loss via Z3. The '
        'two-person rule for high-impact actions prevents operator error from causing '
        'extended outages. Penalties for SLA breach are 5% of license fee per 0.1% below '
        'target, capped at 50% of annual license fee.'
    ))

    story.append(h2('Disaster Recovery Targets'))
    story.append(table([
        ['Scenario', 'RPO', 'RTO', 'Mechanism', 'Test Cadence'],
        ['Z1 hardware failure', '< 1 s', '< 3 s', 'VRRP failover to Z2', 'Monthly automated'],
        ['Z1+Z2 metro disaster', '< 60 s', '< 15 min', 'Manual Z3 activation, WAL replay', 'Quarterly drill'],
        ['Data corruption (logical)', '0 (point-in-time)', '< 30 min', 'TimescaleDB PITR from S3', 'Quarterly'],
        ['Ransomware / compromise', '< 24 h', '< 4 h', 'Rebuild from gold image + state restore', 'Annual'],
        ['Broker outage', '0', '< 5 min', 'Auto-detect + halt new orders (no failover)', 'Monthly'],
        ['License server outage', '0 (7-day grace)', '0', 'Offline grace period', 'Annual'],
    ], col_widths=[44, 24, 24, 50, 32]))
    story.append(Spacer(1, 8))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 17 — Risk & Compliance Architecture
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Risk & Compliance Architecture', 17))
    story.append(p(
        'The risk architecture is the structural enforcement of the capital-preservation-first '
        'principle. It is organized into three lines of defense: pre-trade gates that block '
        'orders before they reach the broker, post-trade monitors that observe the live system '
        'and fire circuit breakers when thresholds are breached, and the kill switch that '
        'provides the ultimate emergency halt. Compliance is built on top of the audit store, '
        'an immutable hash-chained log that records every order, fill, risk decision, and '
        'operator action.'
    ))

    story.append(h2('Pre-Trade Risk Gates'))
    story.append(p(
        'The PreTradeRiskGate runs synchronously in the hot path, between the SignalEngine '
        'and the OrderManager. Every order must pass through it; there is no bypass. The '
        'gate performs the following checks in order, returning REJECT on the first failure '
        'with a specific reason code:'
    ))
    story.append(bullet('<b>Position size check</b> — the resulting position must not exceed the configured maximum (default: 5% of equity per symbol).'))
    story.append(bullet('<b>Leverage check</b> — the resulting gross exposure must not exceed the configured maximum leverage (default: 10x).'))
    story.append(bullet('<b>Daily trade count</b> — the number of trades in the current UTC day must not exceed the configured maximum (default: 20).'))
    story.append(bullet('<b>News blackout</b> — the current time must not fall within any configured blackout window (FOMC ±15 min, NFP ±10 min, etc.).'))
    story.append(bullet('<b>Margin floor</b> — the post-order free margin must remain above 30% of equity.'))
    story.append(bullet('<b>Drawdown throttle</b> — if the rolling 90-day MaxDD exceeds 3% (soft), new entries are throttled to half size.'))
    story.append(bullet('<b>Loss streak check</b> — if the last N trades were all losses (default N=5), new entries are blocked for a cooldown period.'))
    story.append(p(
        'The gate returns a RiskDecision value object carrying the verdict (APPROVE, REJECT, '
        'THROTTLE), a reason code, a human-readable message, an optional reduced quantity for '
        'THROTTLE, and a serializable audit blob. APPROVE allows the order to proceed; REJECT '
        'blocks it and logs the reason; THROTTLE allows the order with a reduced quantity. '
        'Every decision is written to the audit store, providing a complete record for '
        'post-incident analysis.'
    ))

    story.append(h2('Post-Trade Risk Monitor'))
    story.append(p(
        'The PostTradeRiskMonitor runs asynchronously, observing fills and equity updates. '
        'Unlike the pre-trade gate, it does not block orders; instead, it fires circuit '
        'breakers when thresholds are breached. The monitor tracks:'
    ))
    story.append(bullet('<b>Drawdown circuit breakers</b> — soft at 3% (throttle new entries, notify operator), hard at 5% (engage kill switch).'))
    story.append(bullet('<b>Loss streak circuit</b> — 5 consecutive losses triggers cooldown, 10 triggers soft halt.'))
    story.append(bullet('<b>Slippage outlier</b> — if realized slippage exceeds 3 standard deviations above trailing mean, log + alert.'))
    story.append(bullet('<b>Margin call proximity</b> — if free margin drops below 50%, alert; below 30%, soft halt.'))
    story.append(bullet('<b>Daily loss limit</b> — if daily realized loss exceeds 2% of equity, halt new entries for the day.'))

    story.append(h2('Kill Switch'))
    story.append(p(
        'The kill switch is the system\'s emergency brake. Engaging it performs four actions '
        'in sequence: (1) halt all new orders by setting an atomic armed flag that the '
        'OrderManager checks before submitting; (2) cancel all pending orders via the broker '
        'API; (3) flatten all open positions via market orders; (4) notify the operator via '
        'PagerDuty, Telegram, and the operator console. The target end-to-end time from kill '
        'switch trigger to position flat is five hundred milliseconds. The kill switch can be '
        'triggered by: manual operator action (two-person rule), automatic PostTradeRiskMonitor '
        'detection (hard drawdown, loss streak), or license revocation. Once triggered, the '
        'system enters a cooldown period (default 5 minutes) during which it cannot be re-armed '
        'without supervisor intervention and an audit-trail entry explaining the re-arm reason.'
    ))

    story.append(h2('Compliance & Audit'))
    story.append(p(
        'The audit store is the system\'s memory and conscience. Every order event, fill, '
        'risk decision, and operator action is appended to a hash-chained log: each entry '
        'includes the previous entry\'s hash, making tampering computationally detectable. '
        'The log is stored on write-once-read-many (WORM) S3 with object lock, providing '
        'physical tamper resistance in addition to the cryptographic guarantee. The log '
        'supports arbitrary point-in-time reconstruction: given a starting state and a '
        'range of audit entries, the system can reconstruct the exact state at any past '
        'moment, enabling forensic analysis of any incident.'
    ))
    story.append(p(
        'Compliance reporting hooks are provided for licensees who must report to regulators. '
        'The MiFID-II-style trade reporting adapter exports fills in the regulatory format; '
        'the GDPR adapter handles operator personal data deletion requests. Licensees '
        'receive a daily compliance report via email and have read API access to the audit '
        'log for their tenant. The audit log is retained for the longer of the license term '
        'plus five years or the regulatory minimum for the licensee\'s jurisdiction.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 18 — Commercial Licensing Architecture
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Commercial Licensing Architecture', 18))
    story.append(p(
        'The licensing architecture is designed to be enforceable without being onerous. '
        'It uses RSA-signed JSON Web Tokens (JWTs) issued by a per-tenant license server, '
        'validated online with a seven-day offline grace period. Feature gates are encoded '
        'as claims in the JWT, allowing tiered pricing (Starter, Pro, Enterprise) without '
        'separate codebases. Hardware fingerprinting, code obfuscation, and tamper detection '
        'protect against casual piracy without imposing onerous restrictions on legitimate '
        'licensees.'
    ))

    story.append(h2('License Model'))
    story.append(p(
        'Each licensee receives a tenant ID and an RSA public key pair. The license server '
        '(SaaS, hosted by TITAN) signs JWTs containing the tenant\'s claims: tier, strategy '
        'count, capital ceiling, feature flags, expiry. The TITAN runtime validates the JWT '
        'signature on startup and on every hourly heartbeat. If validation fails (expired, '
        'revoked, signature mismatch), the system enters a grace period: seven days of '
        'continued operation with prominent operator alerts, followed by a graceful shutdown '
        'that closes positions and halts new orders. The grace period exists to handle '
        'transient network issues and to give licensees time to renew without disrupting '
        'live trading.'
    ))

    story.append(h2('Tier Matrix'))
    story.append(table([
        ['Feature', 'Starter', 'Pro', 'Enterprise'],
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
    ], col_widths=[42, 22, 28, 40]))
    story.append(Spacer(1, 8))

    story.append(h2('Anti-Piracy Measures'))
    story.append(p(
        'Casual piracy is deterred through four layered measures, each raising the cost of '
        'circumvention without burdening legitimate users. The first layer is hardware '
        'fingerprinting: the JWT is bound to a fingerprint derived from CPUID, MAC address, '
        'and disk serial number; a license used on a different machine fails validation. '
        'The second layer is code obfuscation: C++ symbols are stripped from release builds, '
        'Python sensitive modules (license validation, model decryption, strategy parameter '
        'decryption) are compiled to native code via Cython and shipped as binary wheels. '
        'The third layer is tamper detection: the runtime checksums its own binary on '
        'startup and periodically; mismatch triggers a graceful shutdown with an audit log '
        'entry. The fourth layer is behavioral analytics: the license server tracks usage '
        'patterns and flags anomalies (e.g., a single license used from IPs in five countries '
        'in one day) for manual review.'
    ))
    story.append(p(
        'None of these measures is unbreakable — determined adversaries with sufficient '
        'resources can circumvent any software protection. The goal is to raise the cost '
        'above the price of a legitimate license for the vast majority of potential pirates, '
        'while keeping the experience seamless for paying customers. The hardware fingerprint, '
        'in particular, is designed to be lenient: routine hardware changes (adding RAM, '
        'replacing a failed disk) trigger a re-activation flow rather than a lockout, with '
        'three re-activations per year allowed automatically and additional ones requiring '
        'support contact.'
    ))

    story.append(h2('License Validation Flow'))
    story.append(p(
        'On startup, the TITAN runtime loads the cached JWT from '
        '<font name="DejaVuSans">/var/lib/titan/license.jwt</font> and validates the RSA '
        'signature against the embedded TITAN public key. If valid and not expired, the '
        'runtime extracts the claims and configures feature gates accordingly. If invalid '
        'or expired, the runtime attempts to refresh the JWT by calling the license server '
        'with the tenant ID and hardware fingerprint. If the refresh succeeds, the new JWT '
        'is cached and trading proceeds. If the refresh fails (network issue, server '
        'unavailable), the runtime enters the seven-day grace period, during which it '
        'continues trading with prominent operator alerts. After seven days without a '
        'successful refresh, the runtime initiates a graceful shutdown: halt new orders, '
        'flatten positions, cancel pending orders, and exit with a non-zero status code. '
        'The hourly heartbeat during normal operation serves the same refresh logic, '
        'ensuring that a revoked license is detected within an hour of revocation.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # CHAPTER 19 — Implementation Roadmap
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Implementation Roadmap', 19))
    story.append(p(
        'The implementation roadmap spans twelve months across four phases, each with hard '
        'exit criteria tied to the target metrics. The phasing reflects the principle that '
        'foundation must precede intelligence, intelligence must precede productionization, '
        'and productionization must precede commercialization. A phase cannot be exited '
        'until all its exit criteria are met on out-of-sample data; there is no schedule '
        'override. The roadmap assumes a starting team of four FTE ramping to eight FTE by '
        'month six.'
    ))
    story.append(diagram('d11_roadmap.png', width_mm=170))
    story.append(caption('Figure 19.1 — 12-month roadmap Gantt with phase exit milestones.'))

    story.append(h2('Phase 1 — Foundation (M1-M3)'))
    story.append(p(
        'Phase 1 builds the infrastructure on which everything else depends. The folder '
        'structure, CI scaffolding, and development environment come first (M1). The MT5 '
        'bridge and tick pipeline (M2) establish the data plane, with a target p99 tick '
        'ingestion latency under two milliseconds. The backtest engine and basic risk gate '
        '(M3) close the loop, enabling the first walk-forward validation. Phase 1 exit '
        'criteria: tick pipeline p99 under 2 ms, backtest replay matches paper trade within '
        '0.1% over a one-month sample, risk gate blocks 100% of test violations. Deliverables: '
        'repo scaffold, MT5 bridge, normalizer, basic risk gate, backtest engine, CI scaffolding. '
        'Team: 4 FTE.'
    ))

    story.append(h2('Phase 2 — Intelligence (M4-M6)'))
    story.append(p(
        'Phase 2 adds the alpha generation layer. The feature engine (M4-M5) implements over '
        'three hundred features spanning technical, microstructure, and session categories. '
        'The signal engine and first live strategy (M5-M6) produce the first end-to-end '
        'signal-to-order flow. ML inference via PyTorch (M5-M6) enables model-based signal '
        'enhancement. Walk-forward validation (M6) provides the first credible performance '
        'estimate. Phase 2 exit criteria: walk-forward PF above 1.5, Sharpe above 1.5, MaxDD '
        'below 5% on out-of-sample, ML inference p99 under 1 ms. Deliverables: feature engine, '
        'signal engine, ML inference, first live strategy, walk-forward validator. Team: 6 FTE.'
    ))

    story.append(h2('Phase 3 — Productionization (M7-M9)'))
    story.append(p(
        'Phase 3 makes the system production-ready. The three-zone deployment (M7) provides '
        'the HA foundation. The monitoring stack (M7-M8) gives observability. The licensing '
        'server (M8) enables the first commercial pilots. The canary CI/CD pipeline (M8-M9) '
        'with the backtest regression gate enforces the metric discipline. The chaos game-day '
        '(M9) stress-tests the system. Phase 3 exit criteria: 99.95% uptime over 30 days, '
        'Z1→Z2 failover under 3 seconds, DR drill passed, license server live, canary '
        'auto-rollback works. Deliverables: HA deployment, monitoring, licensing, canary CI/CD, '
        'chaos game-day, runbooks. Team: 7 FTE.'
    ))

    story.append(h2('Phase 4 — Commercialization (M10-M12)'))
    story.append(p(
        'Phase 4 turns the production system into a commercial product. Multi-tenant isolation '
        '(M10) enables multiple licensees on shared infrastructure. Billing integration '
        '(M11) handles subscription and usage-based billing. White-label option (M11) allows '
        'partners to rebrand the system. Partner onboarding flow (M11-M12) streamlines new '
        'licensee activation. The v1.0 GA launch (M12) marks the end of the roadmap and the '
        'beginning of post-GA迭代. Phase 4 exit criteria: 3+ paying licensees, multi-tenant '
        'isolated, billing integrated, white-label pilot signed. Deliverables: multi-tenant, '
        'billing, white-label, partner onboarding, v1.0 GA. Team: 8 FTE.'
    ))

    story.append(h2('Post-GA Roadmap (Indicative)'))
    story.append(p(
        'Beyond v1.0 GA, the roadmap is reviewed quarterly. Likely directions include: FIX '
        'broker support (v1.1, Q1 2027) for direct-access brokers without MT5 dependency; '
        'multi-instrument support (v1.2, Q2 2027) extending to XAGUSD and other precious '
        'metals; an on-prem enterprise deployment option (v2.0, Q3 2027) for licensees who '
        'cannot use shared infrastructure; a strategy marketplace (v2.1, Q4 2027) allowing '
        'third-party strategy developers to publish strategies under revenue share. These '
        'are indicative, not committed; the actual post-GA roadmap will be set in the Q1 2027 '
        'planning cycle based on licensee feedback and market conditions.'
    ))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # APPENDIX A — Glossary
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Appendix A — Glossary & Acronyms', 20))
    story.append(p(
        'This glossary defines the terminology used throughout the document. Terms are '
        'ordered alphabetically. Acronyms are spelled out on first use in each chapter and '
        'defined here for reference.'
    ))
    glossary = [
        ('XAUUSD', 'Spot gold versus US dollar currency pair. XAU is the ISO 4217 code for one troy ounce of gold; USD is the US dollar. The most actively traded precious metals pair.'),
        ('MT5', 'MetaTrader 5. A retail and institutional trading platform developed by MetaQuotes Software, widely supported by forex and CFD brokers. TITAN\'s primary execution venue.'),
        ('FIX', 'Financial Information eXchange protocol. A vendor-neutral electronic communications protocol for the international real-time exchange of securities transaction information. Version 4.4 is used for institutional order routing.'),
        ('MQL5', 'MetaQuotes Language 5. The programming language for custom indicators and expert advisors in MT5. TITAN does not use MQL5 directly; it interfaces with MT5 via the Python MetaTrader5 package and C++ bridge.'),
        ('PyO3', 'A Rust library (with Python bindings) for writing native Python extensions in Rust. TITAN uses a similar pattern via pybind11 for C++/Python interop, sometimes loosely referred to as "PyO3-style" bindings.'),
        ('PyTorch', 'An open-source machine learning framework developed by Meta AI. Used in TITAN for ML model training and inference (via ONNX runtime in production).'),
        ('Sharpe Ratio', 'Risk-adjusted return measure: (mean return − risk-free rate) / standard deviation of returns, annualized. Higher is better. Target: > 2.0.'),
        ('Profit Factor (PF)', 'Gross profit divided by gross loss over a measurement window. PF > 2.0 is institutional grade. Target: > 2.0.'),
        ('Recovery Factor', 'Net profit divided by maximum drawdown over a window. Measures how quickly the system recovers from worst dip. Target: > 5.0.'),
        ('Risk of Ruin (RoR)', 'Monte Carlo probability of equity hitting a ruin threshold (50% drawdown) within 252 trading days. Target: < 1%.'),
        ('MaxDD', 'Maximum Drawdown. Largest peak-to-trough decline in equity curve over a window, as percentage of peak. Target: < 5%.'),
        ('Walk-Forward', 'A backtesting methodology where parameters are optimized on a rolling in-sample window and validated on the immediately following out-of-sample window, then the window rolls forward. Prevents look-ahead bias.'),
        ('Monte Carlo', 'A statistical technique using repeated random sampling to estimate the distribution of an outcome. In TITAN, used for risk-of-ruin estimation by sampling 1000 randomized return paths.'),
        ('Kill Switch', 'Emergency control that halts all new orders, cancels pending orders, and flattens open positions. TITAN\'s kill switch targets < 500ms end-to-end.'),
        ('Hot-Standby', 'A redundant system component that is running and ready to take over immediately on primary failure, with state replicated synchronously. TITAN\'s Z2 is hot-standby to Z1.'),
        ('Cold-Standby', 'A redundant system component that is configured but not running, requiring manual activation on primary failure. TITAN\'s Z3 is cold-standby for catastrophic failover.'),
        ('RPO', 'Recovery Point Objective. The maximum acceptable data loss measured in time. TITAN Z3 RPO: 60 seconds.'),
        ('RTO', 'Recovery Time Objective. The maximum acceptable time to restore service after a failure. TITAN Z3 RTO: 15 minutes.'),
        ('NUMA', 'Non-Uniform Memory Access. A multi-processor memory architecture where each CPU has local memory with lower access latency than remote memory. TITAN pins titan-core to NUMA node 0 for predictable memory access.'),
        ('PREEMPT_RT', 'A Linux kernel patch that provides full kernel preemption, allowing high-priority tasks to interrupt kernel-level work. Essential for sub-millisecond latency predictability.'),
        ('WireGuard', 'A modern, fast, and secure VPN protocol that uses state-of-the-art cryptography. TITAN uses WireGuard for inter-zone communication.'),
        ('FlatBuffers', 'A cross-platform serialization library with zero-copy access to serialized data. Used in TITAN for inter-language message passing without copy overhead.'),
        ('MLflow', 'An open-source platform for managing the ML lifecycle, including experiment tracking, model registry, and deployment. Used in TITAN for model versioning.'),
        ('OpenTelemetry (OTel)', 'An open observability framework for generating and collecting telemetry data (traces, metrics, logs). Used in TITAN for distributed tracing of tick-to-trade path.'),
        ('VRRP', 'Virtual Router Redundancy Protocol. A network protocol that provides automatic failover for default gateway. TITAN uses VRRP for Z1→Z2 failover.'),
        ('SPSC', 'Single-Producer Single-Consumer. A queue pattern with one writer and one reader, allowing lock-free implementation via atomics. Used in TITAN\'s hottest data paths.'),
        ('JWT', 'JSON Web Token. A compact, URL-safe means of representing claims to be transferred between two parties. TITAN uses RSA-signed JWTs for license tokens.'),
        ('NFR', 'Non-Functional Requirement. A requirement specifying a quality the system must exhibit (performance, reliability, security, etc.), as distinct from a functional requirement (what the system does).'),
        ('ADR', 'Architecture Decision Record. A short text document capturing a single architectural decision, its context, consequences, and alternatives considered.'),
        ('WORM', 'Write Once, Read Many. A storage model where data, once written, cannot be modified or deleted until a retention period expires. TITAN uses WORM S3 for the audit log.'),
        ('TCA', 'Transaction Cost Analysis. The process of analyzing the execution quality of trades, including realized slippage, fill rates, and venue quality.'),
        ('OIDC', 'OpenID Connect. An identity layer on top of OAuth 2.0, used in TITAN for operator console authentication.'),
        ('SLA', 'Service Level Agreement. A formal commitment to a specific level of service, with penalties for breach. TITAN offers 99.95% SLA for Enterprise tier.'),
        ('MTTR', 'Mean Time To Recovery. The average time to restore service after a failure. TITAN target: < 15 minutes.'),
    ]
    rows = [['Term', 'Definition']]
    for term, definition in glossary:
        rows.append([term, definition])
    story.append(table(rows, col_widths=[35, 135]))
    story.append(Spacer(1, 10))

    story.append(PageBreak())

    # ════════════════════════════════════════════════════════════════════
    # APPENDIX B — Reference Configurations
    # ════════════════════════════════════════════════════════════════════
    story.append(h1('Appendix B — Reference Configurations', 21))
    story.append(p(
        'This appendix contains sample configuration snippets for the key runtime components. '
        'These are reference values for a $250,000 capital deployment at the Pro tier; '
        'production deployments will deviate based on tenant risk profile, broker terms, '
        'and operational preferences. All configurations are version-controlled in '
        '<font name="DejaVuSans">configs/</font> with environment-specific overrides in '
        '<font name="DejaVuSans">configs/environments/</font>.'
    ))

    story.append(h2('titan-core.yaml — Runtime configuration'))
    story.append(code("""# titan-core.yaml — C++ execution core runtime config
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
  retention: 30d"""))

    story.append(h2('risk.yaml — Risk envelope'))
    story.append(p(
        'The risk envelope is the most consequential configuration in the system. Changes '
        'require supervisor authorization and are recorded in the audit log. Most limits '
        'auto-revert after a configurable timeout (default 4 hours) to prevent drift.'
    ))
    story.append(code("""# risk.yaml — Risk envelope (production defaults)
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
  window_days: 90"""))

    story.append(h2('strategy.yaml — Strategy parameters'))
    story.append(code("""# strategy.yaml — Strategy activation and parameters
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
  min_signal_strength: 0.4"""))

    story.append(h2('monitoring.yaml — Observability configuration'))
    story.append(code("""# monitoring.yaml — Prometheus + Loki + AlertManager
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
    severity: P1"""))

    story.append(h2('license.yaml — License client configuration'))
    story.append(code("""# license.yaml — License client (per-tenant)
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
  - { feature: white_label,         claim: white_label,        required: false }"""))

    story.append(h2('Configuration Management'))
    story.append(p(
        'All configurations are version-controlled in Git alongside the source code, with '
        'environment-specific overrides in <font name="DejaVuSans">configs/environments/</font>. '
        'Configurations are loaded at startup and hot-reloaded via inotify watchers; changes '
        'to non-critical parameters (logging level, scrape interval) take effect immediately, '
        'while changes to critical parameters (risk envelope, strategy activation) require '
        'supervisor authorization via the operator console. Every configuration change is '
        'recorded in the audit log with the operator identity, before/after diff, and reason. '
        'Configurations are validated by pydantic schemas on load; invalid configurations '
        'cause the service to refuse to start with a clear error message.'
    ))

    return story
