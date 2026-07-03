# TITAN XAU AI — ARCHITECTURE LOCK v1.0

**Sprint v2.8.5-D — Single Source of Truth for Runtime Architecture**

> This file is the canonical architecture specification for TITAN XAU AI.
> All existing architecture PDFs (v1, v2) are historical/reference only.
> All future audits, pipeline checks, and CEO governance evaluations MUST
> reference this Architecture Lock.

---

## Intended Runtime Pipeline

```
FeatureStream
  -> Regime/Context Intelligence
  -> 3 AI Expert Roles:
     1. XGBoost = alpha/direction specialist
     2. LSTM = sequential confidence / market memory specialist
     3. Transformer = regime intelligence / regime classification specialist
  -> Meta-label / LogisticRegression trade-quality filter
  -> CEO AI Governance / Meta Decision Layer
  -> Risk + Prop + Broker + Geometry Gates
  -> Operator Token-Gated MetaQuotes-Demo Execution
  -> AI Exit + Recovery + Capital Protection
```

---

## Component Definitions

### 1. FeatureStream
- **Module:** `titan/production/feature_stream.py`
- **Class:** `H1FeatureStream`
- **Required:** YES (fail-closed if missing)
- **Role:** Produces the canonical 55-feature vector from MT5 H1 bars.

### 2. Regime/Context Intelligence
- **Module:** `titan/production/alpha_regime_entry_decision.py`
- **Function:** `evaluate_entry()`
- **Required:** YES (fail-closed if missing)
- **Role:** Detects market regime (SPREAD_EXPANSION, TREND, RANGE, etc.)
  and provides regime context before alpha execution permission.

### 3. XGBoost — Alpha/Direction Specialist
- **Artifact:** `titan/data/models/xgboost_v1.pkl`
- **Loader:** `titan/production/model_loader.py` → `load_production_models()`
- **Expert Role:** `alpha_direction_specialist`
- **Required:** YES (fail-closed if missing or fails health audit)
- **Role:** Produces directional signal (LONG/SHORT/FLAT) with confidence
  probability. Raw XGB signal can NEVER reach execution directly.

### 4. LSTM — Sequential Confidence Specialist
- **Artifact:** `titan/data/models/lstm_v1.pt` (or `lstm_v2_clean.pt`)
- **Expert Role:** `sequential_confidence_specialist` (advisory)
- **Required:** NO (advisory — may be unavailable if PyTorch not installed)
- **Role:** Provides sequential/market-memory confidence. If unavailable,
  CEO governance treats it as advisory_unavailable (non-blocking).

### 5. Transformer — Regime Intelligence Specialist
- **Artifact:** `titan/data/models/transformer_v1.pt`
- **Expert Role:** `regime_intelligence_specialist` (advisory)
- **Required:** NO (advisory — may be unavailable if PyTorch not installed)
- **Role:** Provides regime classification intelligence. If unavailable,
  CEO governance treats it as advisory_unavailable (non-blocking).

### 6. Meta-label / LogisticRegression — Trade-Quality Filter
- **Artifact:** `titan/data/models/meta_label_v2_context.pkl`
- **Loader:** `titan/production/model_loader.py` → `extract_meta_features()`
- **Expert Role:** `meta_label_quality_filter`
- **Required:** YES (fail-closed if missing or fails health audit)
- **Role:** Filters XGB alpha signal for trade quality. A trade cannot
  proceed unless meta-label quality score passes threshold.

### 7. CEO AI Governance / Meta Decision Layer
- **Module:** `titan/production/ceo_ai_governance.py`
- **Function:** `evaluate_ceo_decision()`
- **Required:** YES (fail-closed if missing, not imported, or not called)
- **Role:** Consolidates all expert model inputs, hard-gate states, and
  capital protection state into a single PASS/BLOCKED decision.
  - Receives: regime_state, xgb_alpha, lstm_confidence, transformer_regime,
    meta_label_quality, broker_state, prop_risk_state,
    capital_protection_state, model_health_state, geometry_state
  - Outputs: final_decision, allowed_to_trade, decision_confidence,
    risk_multiplier, blockers, warnings, reasoning_codes
  - risk_multiplier NEVER exceeds 1.0 (no risk increase above cap)
  - Logs CEO_AI_DECISION journal event

### 8. Risk Gate
- **Module:** `titan/production/margin_leverage_guard.py`
- **Required:** YES (fail-closed if missing)
- **Role:** Validates margin/leverage/risk constraints.

### 9. Prop Firm Gate
- **Module:** `titan/production/prop_firm_rule_engine.py`
- **Required:** YES (fail-closed if missing)
- **Role:** Validates prop firm profile rules (max positions, lot, DD).

### 10. Broker Gate
- **Module:** `titan/production/broker_scoring_engine.py`
- **Required:** YES (fail-closed if missing)
- **Role:** Validates broker quality, spread, slippage.

### 11. Geometry Gate
- **Module:** `titan/production/demo_micro_order_builder.py`
- **Required:** YES (fail-closed if missing)
- **Role:** Validates RR geometry (min RR >= 2.0, preferred RR = 3.0).

### 12. Operator Token-Gated MetaQuotes-Demo Execution
- **Module:** `scripts/operator/run_managed_demo_micro_trade.py`
- **Required:** YES (fail-closed if missing)
- **Role:** Executes ONE supervised MetaQuotes-Demo micro trade after:
  - Operator arm token created (10-minute expiry)
  - 8 confirmation flags passed
  - MetaQuotes-Demo DEMO account verified
  - No open/pending XAUUSD position
  - CEO AI Governance approved (allowed_to_trade = True)
  - All hard gates pass
  - OPERATOR_ARM_TOKEN_REQUIRED marker present

### 13. AI Exit Intelligence
- **Module:** `titan/production/ai_exit_engine.py`
- **Required:** NO (advisory — called AFTER execution for exit logic)
- **Role:** Manages trade exit via adaptive trailing, breakeven, profit lock.

### 14. Capital Protection
- **Module:** `titan/production/capital_protection.py`
- **Required:** YES (fail-closed if missing)
- **Role:** Monitors drawdown, activates capital preservation mode.

---

## Hard Rules (NEVER Violated)

1. **Raw XGB signal can never reach execution directly.**
   - XGB alpha must pass through CEO AI Governance before any order_send.

2. **Regime/Context must be evaluated before alpha execution permission.**
   - CEO governance requires regime_state input. Missing regime = BLOCKED.

3. **CEO AI Governance must approve/block before any possible order_send.**
   - If CEO is not imported, not called, or returns BLOCKED, no order_send.
   - execute-and-monitor mode MUST call evaluate_ceo_decision() before
     mt5.order_send and must NOT call order_send if CEO blocks.

4. **LSTM/Transformer may be advisory/unavailable.**
   - If PyTorch not installed or .pt artifacts unavailable, CEO governance
     treats them as advisory_unavailable (non-blocking).

5. **LightGBM is optional/challenger.**
   - LightGBM is NOT required for runtime. Failure is non-blocking.
   - LightGBM is NOT wired into the active inference chain.

6. **No martingale/grid/averaging/loss multiplier.**
   - All forbidden strategies are disabled in growth profile config.
   - No code path may implement these strategies.

7. **No live/funded/real execution.**
   - Only MetaQuotes-Demo DEMO account allowed.
   - LIVE/CONTEST accounts are BLOCKED.

8. **MetaQuotes-Demo only until explicit future approval.**
   - FundedNext demo is BLOCKED for execution.
   - FundedNext / prop firm layer is simulation/rule logic only.

9. **OPERATOR_ARM_TOKEN_REQUIRED for all execution.**
   - execution_now_allowed is always False without operator token.
   - Token expires after 10 minutes.

10. **No circular dependencies in audit readiness chain.**
    - Acyclic order: base audits -> build-request -> final_demo_activation
      -> production_closure
    - final_demo_activation does NOT read production_closure artifact.
    - production_closure may aggregate final_demo_activation.

---

## Audit Dependency Order (Acyclic)

```
1. Base audits (independent):
   - model_artifact_health_audit
   - feature_parity_audit
   - runtime_safety_gate_audit
   - prop_challenge_growth_profile_audit
   - runtime_architecture_pipeline_audit
   - ceo_ai_governance_audit

2. Build-request (reads base audits + live state):
   - Computes operator readiness (read-only)
   - Calls CEO AI Governance
   - Does NOT depend on final_demo_activation verdict

3. Final demo activation (reads base audits + build-request + live MT5):
   - Does NOT read production_closure artifact
   - Requires fresh build-request report
   - Requires Windows + MT5 + MetaQuotes-Demo

4. Production closure (final aggregator):
   - Reads final_demo_activation
   - Reads all base audits
   - Does NOT feed back into final_demo_activation
```

---

## Expert Model Role Summary

| Model | Expert Role | Required | Advisory |
|-------|-------------|----------|----------|
| XGBoost | alpha_direction_specialist | YES | - |
| meta_label_v2_context | meta_label_quality_filter | YES | - |
| LSTM | sequential_confidence_specialist | NO | YES |
| Transformer | regime_intelligence_specialist | NO | YES |
| LightGBM | optional_challenger | NO | - |

---

## References

- Architecture Lock: this file (`docs/TITAN_ARCHITECTURE_LOCK_v1.0.md`)
- CEO AI Governance: `titan/production/ceo_ai_governance.py`
- Runtime Architecture Audit: `scripts/audit/runtime_architecture_pipeline_audit.py`
- CEO Governance Audit: `scripts/audit/ceo_ai_governance_audit.py`
- Growth Profile: `config/prop_challenge_growth_profile.yaml`
- Operator Runbook: `docs/FINAL_METAQUOTES_DEMO_START_RUNBOOK.md`

---

**End of Architecture Lock v1.0**
