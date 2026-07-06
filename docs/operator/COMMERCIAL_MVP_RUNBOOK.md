# TITAN XAU AI — Commercial MVP Runbook

**Sprint v2.8.7-F**
**Status: SKELETON — Not for production use**

## Overview

This runbook describes the structural readiness of TITAN XAU AI for
commercial MVP deployment. The system is **structurally ready** (all
components wired, safety gates in place) but **NOT trading-ready**
(no safe parameter set found, no demo shadow authorization).

## Current Status

| Component | Status |
|---|---|
| Model profiles (v1, v2, v2_multibroker) | ✅ Wired |
| CEO governance | ✅ Wired |
| Meta-label filter | ✅ Wired |
| MTF confirmation | ✅ Wired |
| Risk gates | ✅ Wired |
| Spread normalization | ✅ Wired |
| Commercial profile skeleton | ✅ Created |
| License policy skeleton | ✅ Created |
| Demo shadow authorization | ❌ NOT GRANTED |
| Live trading | ❌ BLOCKED |
| Funded trading | ❌ BLOCKED |
| production_ready | ❌ False (always) |

## Safety Guarantees

The following are **hard guarantees** that cannot be overridden:

1. **production_ready = False** — always, in all sprints
2. **dry_run = true** — default, until explicit future approval
3. **live_trading = false** — default, until explicit future approval
4. **funded_trading = false** — default, until explicit future approval
5. **No order_send** — research scripts never call order_send
6. **No token auto-creation** — operator must explicitly create tokens
7. **CEO not bypassed** — all trades require CEO governance approval
8. **Meta-label not bypassed** — all trades require meta-label pass
9. **Default model = v1_legacy** — conservative, until v2 validated
10. **MetaQuotes-Demo only** — no live/funded brokers in whitelist

## Operator Warnings

- **DO NOT** attempt to set production_ready=True
- **DO NOT** attempt to enable live_trading
- **DO NOT** attempt to bypass CEO or meta-label
- **DO NOT** attempt to lower thresholds blindly
- **DO NOT** use martingale, grid, or averaging strategies
- **DO NOT** trade on any account until demo_go_decision = DEMO_SHADOW_ALLOWED
- **DO NOT** create execution tokens without explicit CTO review

## Debug Commands

### Check model profiles
```bash
python3 -c "from titan.production.model_registry import list_profiles; print(list_profiles())"
```

### Load each profile
```bash
python3 -c "
from titan.production.model_loader import load_models_by_profile
for p in ['v1_legacy', 'v2_feature_normalized', 'v2_multibroker']:
    b = load_models_by_profile(p)
    print(f'{p}: ok={b.ok}')
"
```

### Check demo_go_decision
```bash
cat data/reports/parameter_discovery_v2/demo_go_decision.md
cat data/reports/parameter_discovery_v2_multibroker/demo_go_decision.md
```

### Run commercial MVP readiness audit
```bash
python3 scripts/audit/final_commercial_mvp_readiness_audit.py
```

### Run broker generalization audit
```bash
python3 scripts/research/run_broker_generalization_audit_v2.py
```

## Crash Recovery

If the system crashes:
1. All positions are closed immediately (fail-closed)
2. No auto-restart (crash_recovery.auto_restart = false)
3. Operator must manually investigate and restart
4. Journal and logs are preserved in data/journal/ and data/logs/

## Next Steps

1. **CTO Review** — review all v2.8.7-F findings
2. **Broker Generalization** — the v2_feature_normalized model works well on
   canonical (PF 4.08) and exness (PF 1.16) but not other brokers
3. **Parameter Discovery** — full 5-broker sweep requires >=8GB RAM machine
4. **Demo Shadow Test** — only if demo_go_decision becomes DEMO_SHADOW_ALLOWED

## No Trade Policy

**No demo trade is allowed unless demo_go_decision = DEMO_SHADOW_ALLOWED.**

Even if allowed:
- No automatic trade
- No token without operator
- CTO review required first
- MetaQuotes-Demo only
- Max lot 0.01
- Max 2 trades/day
