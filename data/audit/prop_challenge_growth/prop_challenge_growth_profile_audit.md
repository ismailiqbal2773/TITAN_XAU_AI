# TITAN XAU AI - Prop Challenge Growth Profile Audit (v2.8.4)

**Profile:** PROP_CHALLENGE_GROWTH_30_8

**Verdict:** **PROP_CHALLENGE_GROWTH_PROFILE_PASS**

**Timestamp:** 2026-07-03T05:41:02.781960+00:00

## Findings

| Field | Value |
|---|---|
| profile_name | PROP_CHALLENGE_GROWTH_30_8 |
| monthly_target_pct | 0.3 |
| prop_challenge_target_pct | 0.1 |
| daily_dd_soft_limit_pct | 0.01 |
| daily_dd_hard_limit_pct | 0.02 |
| max_total_dd_pct | 0.08 |
| max_open_positions | 1 |
| max_lot_cap_demo | 0.01 |
| base_risk_per_trade_pct | 0.005 |
| min_RR | 2.0 |
| preferred_RR | 3.0 |
| latest_model_health_verdict | MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS |
| latest_feature_parity_verdict | FEATURE_PARITY_PASS |
| latest_runtime_safety_verdict | RUNTIME_SAFETY_GATE_PASS |
| model_health_pass | True |
| feature_parity_pass | True |
| runtime_safety_pass | True |

## Risk Tiers

| Tier | Present |
|---|---|
| TIER_0_CAPITAL_PRESERVATION | True |
| TIER_1_STANDARD | True |
| TIER_2_GROWTH_CONTROLLED | True |

## No-Forced-Trade Rules

| Rule | Enabled |
|---|---|
| NO_TRADE_VALID_DECISION | True |
| TARGET_NOT_FORCED | True |
| ALPHA_REQUIRED | True |
| REGIME_REQUIRED | True |
| RISK_GATE_REQUIRED | True |

## Forbidden Strategies

| Strategy | Disabled |
|---|---|
| martingale | True |
| grid | True |
| averaging_down | True |
| loss_based_lot_multiplier | True |
| forced_recovery | True |
| lot_increase_after_loss | True |


## OK Checks

- Profile name matches: PROP_CHALLENGE_GROWTH_30_8
- Monthly target is marked as 'target' (not guarantee)
- Prop challenge target is marked as 'target' (not guarantee)
- Daily DD soft limit valid: 0.01
- Daily DD hard limit valid: 0.02
- Total DD cap <= 8%: 0.08
- Kill switch enabled on daily DD hard breach
- Forced recovery after loss: DISABLED
- Lot increase after loss: DISABLED
- Max open positions = 1
- Max lot cap <= 0.01: 0.01
- Base risk per trade <= 0.5%: 0.005
- Min RR >= 2.0: 2.0
- Preferred RR >= 3.0: 3.0
- Risk tier present: TIER_0_CAPITAL_PRESERVATION
- Risk tier present: TIER_1_STANDARD
- Risk tier present: TIER_2_GROWTH_CONTROLLED
- Tier 2 risk <= 0.5%: 0.005
- Tier 2 lot <= 0.01: 0.01
- No-forced-trade rule enabled: NO_TRADE_VALID_DECISION
- No-forced-trade rule enabled: TARGET_NOT_FORCED
- No-forced-trade rule enabled: ALPHA_REQUIRED
- No-forced-trade rule enabled: REGIME_REQUIRED
- No-forced-trade rule enabled: RISK_GATE_REQUIRED
- Execution venue: MetaQuotes-Demo only
- FundedNext-Demo blocked
- Execution token required: OPERATOR_ARM_TOKEN_REQUIRED
- Execution blocker: OPERATOR_ARM_TOKEN_REQUIRED
- Forbidden strategy disabled: martingale
- Forbidden strategy disabled: grid
- Forbidden strategy disabled: averaging_down
- Forbidden strategy disabled: loss_based_lot_multiplier
- Forbidden strategy disabled: forced_recovery
- Forbidden strategy disabled: lot_increase_after_loss
- Build-request: order_send disabled
- Build-request: token creation disabled
- Build-request: position modification disabled
- v2.8.3.3.1 model health pass: MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS
- v2.8.3.3.1 feature parity pass: FEATURE_PARITY_PASS
- v2.8.3.3.1 runtime safety pass: RUNTIME_SAFETY_GATE_PASS

## Safety

- order_send_called: False
- position_modified: False
- token_created: False
