# TITAN XAU AI — Production Release Candidate Plan

**Status:** Release Candidate Foundation
**Last Updated:** 2026-06-29
**Live Trading:** Disabled (dry_run=true, live_trading=false)

---

## What Is Already Complete

| Component | Status | Sprint |
|---|---|---|
| InferenceEngine | Complete | Original |
| MT5ExecutionAdapter | Complete (universal) | 9.9.3.17 |
| Demo Micro Full Cycle | Complete | 9.9.3.14-9.9.3.25 |
| Hard Gate (trade_expert check) | Complete | 9.9.3.14 |
| Filling Mode Auto-Detect | Complete | 9.9.3.15-9.9.3.20 |
| order_check + Send Fallback | Complete | 9.9.3.16-9.9.3.18 |
| Broker Compatibility Fallback | Complete | 9.9.3.19 |
| Raw Working Profile | Complete | 9.9.3.21 |
| Pass Evidence Archiver | Complete | 9.9.3.22-9.9.3.23 |
| Commercial Protection | Complete (stub) | 9.9.3.24 |
| Runtime Health Monitor | Complete | 9.9.3.26 |
| Broker Compatibility Matrix | Complete | 9.9.3.27 |
| Regime Detection | Complete | 9.9.3.28 |
| Signal Execution Bridge | Complete | 9.9.3.29 |
| SL Defense + Profit Capture + Exit Coordinator | Complete | 9.9.3.30 |
| Position Lifecycle + Exit Intent Bridge | Complete | 9.9.3.31 |
| Forward Observation Engine | Complete | 9.9.3.32 |
| Observation Scorecard | Complete | 9.9.3.33 |
| Production Runtime Assembly | This sprint | 9.9.3.34 |
| MetaQuotes-Demo raw probe | PASS (operator) | 9.9.3.21 |
| MetaQuotes-Demo 3-cycle repeatability | PASS (operator) | 9.9.3.25 |

---

## What Is Intentionally Blocked

| Item | Reason |
|---|---|
| Live trading | dry_run=true, live_trading=false |
| mt5.order_send | Not called in assembly |
| DEMO_MICRO_EXECUTE | Operator-only |
| BALANCED/dynamic lot | Not wired, frozen at 0.01 max |
| FundedNext Free Trial | DO_NOT_USE |
| FBS-Demo | REJECTED (10006) |
| Strategy changes | Entry/exit logic unchanged |
| Model retraining | No model changes |

---

## What Must Happen Before Observation

1. Production Runtime Assembly validated
2. All components loaded and importable
3. Safety gates inventoried
4. Broker registry verified (MetaQuotes-Demo PASS)
5. Operator runs daily observation checklist
6. Collect 7/14/30-day forward evidence
7. Daily scorecard grade = PASS or WARN

---

## What Must Happen Before Demo Autonomous Trading

1. 7-day forward observation PASS
2. All safety gates enforced in release mode
3. SecurityGate validated (License + AntiTamper)
4. Regime detection wired into trade loop
5. Signal Execution Bridge produces approved intents
6. Exit Intent Bridge produces safe exit decisions
7. Runtime Health Monitor active during execution
8. Operator manually approves each session
9. max_lot = 0.01, max_open_positions = 1, force_close = true

---

## What Must Happen Before Live Trading

1. 30-day forward observation PASS
2. SecurityGate release mode enforced
3. Full regression test suite passing
4. Operator signs off on live trading readiness
5. Broker compatibility verified for target live broker
6. Dynamic lot sizing wired (frozen BALANCED params)
7. Governance engine wired into trade loop
8. Capital protection fully active
9. Emergency stop tested and verified
10. Legal/compliance review complete

---

## Operator Responsibilities

- Run daily observation checklist
- Verify daily scorecard grade
- Run DEMO_MICRO_EXECUTE only on local Windows MT5 DEMO
- Never share account login/name/balance in committed evidence
- Never use FundedNext Free Trial
- Never enable live trading without explicit sign-off
- Archive pass evidence with redaction
- Report any safety blocks immediately

---

## Safety Gates

| Gate | Mode | Status |
|---|---|---|
| LicenseGuard | dev_mode (non-blocking) | Stub |
| AntiTamperGuard | dev_mode (non-blocking) | Stub |
| SecurityGate | dev_mode (non-blocking) | Stub |
| Hard Gate (demo_micro) | Always active | Enforced |
| DemoMicroArmedToken | Operator-only | Enforced |
| DryRunEnforced | runtime.dry_run=true | Enforced |
| LiveTradingBlocked | runtime.live_trading=false | Enforced |
| MaxLotCap | 0.01 | Enforced |
| MaxPositionsCap | 1 | Enforced |
| ForceCloseOnEnd | default true | Enforced |

---

## Broker Compatibility Status

| Broker | Status | Priority |
|---|---|---|
| MetaQuotes-Demo | VERIFIED_FOR_DEMO_MICRO | HIGH |
| FBS-Demo | REJECTED (10006) | LOW |
| FundedNext Free Trial | DO_NOT_USE | BLOCKED |
| Exness Demo | PENDING | MEDIUM |
| ICMarkets Demo | PENDING | MEDIUM |

---

## Evidence Status

- MetaQuotes-Demo raw probe: PASS (operator-verified)
- MetaQuotes-Demo 3-cycle repeatability: PASS (3/3, 0 open positions)
- Redacted execution registry: Committed
- Raw execution evidence: Local only (not committed)
- Forward observation: Framework ready, collection pending

---

## Release Candidate Checklist

- [x] All 16 required components loaded
- [x] Safety gates inventoried
- [x] Broker registry verified
- [x] MetaQuotes-Demo verified for demo micro
- [x] FundedNext Free Trial blocked
- [x] FBS-Demo rejected
- [x] dry_run=true, live_trading=false
- [x] mt5_order_send_allowed=false
- [x] max_lot=0.01, max_open_positions=1
- [x] Observation framework ready
- [x] Daily scorecard runner ready
- [x] No MT5 import in assembly
- [x] No order_send in assembly
- [ ] 7-day forward observation PASS (pending)
- [ ] 14-day forward observation PASS (pending)
- [ ] 30-day forward observation PASS (pending)
- [ ] Release mode SecurityGate enforcement (future)
- [ ] Live trading sign-off (future)
