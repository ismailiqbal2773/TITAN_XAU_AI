# TITAN XAU AI - CEO AI Governance Audit (v2.8.5-C)

**Verdict:** **CEO_AI_GOVERNANCE_PASS_WITH_WARNINGS**

**Timestamp:** 2026-07-03T07:05:17.017376+00:00

**Module exists:** True

**Importable:** True

**Integrated in operator script:** False

## Required Inputs

- regime_state
- xgb_alpha
- meta_label_quality
- broker_state
- prop_risk_state
- capital_protection_state
- model_health_state
- geometry_state

## Advisory Inputs

- lstm_confidence
- transformer_regime

## Outputs

- final_decision
- allowed_to_trade
- decision_confidence
- risk_multiplier
- blockers
- warnings
- reasoning_codes

## Hard Rules Verified

- no_mt5_calls
- no_token_creation
- no_position_modification
- no_hard_gate_override
- no_forced_trade
- no_risk_increase_above_cap
- no_martingale_grid_averaging_loss_multiplier
- fail_closed_if_required_inputs_missing
- risk_multiplier_never_exceeds_1


## Warnings

- CEO_NOT_INTEGRATED_IN_OPERATOR_SCRIPT: run_managed_demo_micro_trade.py does not import/call ceo_ai_governance - integration pending (module exists but not wired)

## OK Checks

- CEO AI Governance module exists
- CEO AI Governance module importable
- All required inputs accepted: ['regime_state', 'xgb_alpha', 'meta_label_quality', 'broker_state', 'prop_risk_state', 'capital_protection_state', 'model_health_state', 'geometry_state']
- All advisory inputs accepted: ['lstm_confidence', 'transformer_regime']
- All outputs present: ['final_decision', 'allowed_to_trade', 'decision_confidence', 'risk_multiplier', 'blockers', 'warnings', 'reasoning_codes']
- Fail-closed: no inputs -> BLOCKED
- Fail-closed: no inputs -> allowed_to_trade=False
- Risk multiplier within cap: 1.0
- PASS decision when all inputs pass
- allowed_to_trade=True when all inputs pass
- LSTM unavailable handled honestly (advisory warning)
- Transformer unavailable handled honestly (advisory warning)
- CEO_AI_DECISION event logged in journal
- No MT5 calls in CEO governance
- No token creation in CEO governance
- No position modification in CEO governance

## Safety

- order_send_called: False
- position_modified: False
- token_created: False
