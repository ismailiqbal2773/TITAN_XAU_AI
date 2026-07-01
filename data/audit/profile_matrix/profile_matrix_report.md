# TITAN XAU AI - Profile Matrix Readiness Audit

**Verdict:** **PROFILE_MATRIX_READY_WITH_GAPS**

**Design:** Every account profile × risk mode combination is validated against the prop-firm rule engine and broker scoring engine. Combinations are BLOCKED if prop rules fail, net RR falls below min_rr, margin use exceeds the cap, or a live account is paired with a non-live risk mode. Simulation-only modes produce SIMULATION_ONLY combinations. The audit NEVER calls mt5.order_send and NEVER contains martingale/grid/averaging logic.

**Timestamp:** 2026-07-01T15:26:19.533355+00:00

**Head:** 1c580dd

**Combinations:** 48 (PASS=24, SIMULATION_ONLY=8, BLOCKED=16)

## Combination matrix

| Account | Risk Mode | Broker | Prop Firm | Risk/Trade | Daily DD (int) | Total DD (int) | Min RR | TP R | Dyn TP R | Broker Score | Prop Rules | Net RR | Margin | Final |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| funded_100x_conservative | aggressive_simulation_only | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.08 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **BLOCKED** |
| funded_100x_conservative | balanced | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.08 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| funded_100x_conservative | conservative | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.06 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| funded_100x_conservative | institutional_balanced | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.06 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| funded_100x_conservative | institutional_low_risk | ic_markets_standard | generic_prop_100x_static_dd | 0.0025 | 0.02 | 0.04 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| funded_100x_conservative | prop_challenge_aggressive_simulation_only | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.025 | 0.07 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **BLOCKED** |
| funded_100x_conservative | prop_challenge_conservative | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.025 | 0.07 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **BLOCKED** |
| funded_100x_conservative | ultra_safe_demo | ic_markets_standard | generic_prop_100x_static_dd | 0.002 | 0.02 | 0.04 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **BLOCKED** |
| institutional_balanced | aggressive_simulation_only | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.06 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **BLOCKED** |
| institutional_balanced | balanced | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.06 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| institutional_balanced | conservative | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.06 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| institutional_balanced | institutional_balanced | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.06 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| institutional_balanced | institutional_low_risk | ic_markets_standard | generic_prop_100x_static_dd | 0.0025 | 0.02 | 0.04 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| institutional_balanced | prop_challenge_aggressive_simulation_only | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.025 | 0.06 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **BLOCKED** |
| institutional_balanced | prop_challenge_conservative | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.025 | 0.06 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **BLOCKED** |
| institutional_balanced | ultra_safe_demo | ic_markets_standard | generic_prop_100x_static_dd | 0.002 | 0.02 | 0.04 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **BLOCKED** |
| institutional_low_risk | aggressive_simulation_only | ic_markets_standard | generic_prop_100x_static_dd | 0.0025 | 0.02 | 0.04 | 2.5 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **BLOCKED** |
| institutional_low_risk | balanced | ic_markets_standard | generic_prop_100x_static_dd | 0.0025 | 0.02 | 0.04 | 2.5 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| institutional_low_risk | conservative | ic_markets_standard | generic_prop_100x_static_dd | 0.0025 | 0.02 | 0.04 | 2.5 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| institutional_low_risk | institutional_balanced | ic_markets_standard | generic_prop_100x_static_dd | 0.0025 | 0.02 | 0.04 | 2.5 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| institutional_low_risk | institutional_low_risk | ic_markets_standard | generic_prop_100x_static_dd | 0.0025 | 0.02 | 0.04 | 2.5 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| institutional_low_risk | prop_challenge_aggressive_simulation_only | ic_markets_standard | generic_prop_100x_static_dd | 0.0025 | 0.02 | 0.04 | 2.5 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **BLOCKED** |
| institutional_low_risk | prop_challenge_conservative | ic_markets_standard | generic_prop_100x_static_dd | 0.0025 | 0.02 | 0.04 | 2.5 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **BLOCKED** |
| institutional_low_risk | ultra_safe_demo | ic_markets_standard | generic_prop_100x_static_dd | 0.002 | 0.02 | 0.04 | 2.5 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **BLOCKED** |
| prop_firm_100x_demo | aggressive_simulation_only | metaquotes_demo | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.08 | 2.0 | 3.0 | 2.0 | 86.26 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **SIMULATION_ONLY** |
| prop_firm_100x_demo | balanced | metaquotes_demo | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.08 | 2.0 | 3.0 | 2.0 | 86.26 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| prop_firm_100x_demo | conservative | metaquotes_demo | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.06 | 2.0 | 3.0 | 2.0 | 86.26 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| prop_firm_100x_demo | institutional_balanced | metaquotes_demo | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.06 | 2.0 | 3.0 | 2.0 | 86.26 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| prop_firm_100x_demo | institutional_low_risk | metaquotes_demo | generic_prop_100x_static_dd | 0.0025 | 0.02 | 0.04 | 2.0 | 3.0 | 2.0 | 86.26 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| prop_firm_100x_demo | prop_challenge_aggressive_simulation_only | metaquotes_demo | generic_prop_100x_static_dd | 0.005 | 0.025 | 0.07 | 2.0 | 3.0 | 2.0 | 86.26 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **SIMULATION_ONLY** |
| prop_firm_100x_demo | prop_challenge_conservative | metaquotes_demo | generic_prop_100x_static_dd | 0.005 | 0.025 | 0.07 | 2.0 | 3.0 | 2.0 | 86.26 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **SIMULATION_ONLY** |
| prop_firm_100x_demo | ultra_safe_demo | metaquotes_demo | generic_prop_100x_static_dd | 0.002 | 0.02 | 0.04 | 2.0 | 3.0 | 2.0 | 86.26 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **SIMULATION_ONLY** |
| retail_demo_micro | aggressive_simulation_only | metaquotes_demo | generic_prop_100x_static_dd | 0.01 | 0.03 | 0.08 | 2.0 | 3.0 | 2.0 | 86.26 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **SIMULATION_ONLY** |
| retail_demo_micro | balanced | metaquotes_demo | generic_prop_100x_static_dd | 0.0075 | 0.03 | 0.08 | 2.0 | 3.0 | 2.0 | 86.26 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| retail_demo_micro | conservative | metaquotes_demo | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.06 | 2.0 | 3.0 | 2.0 | 86.26 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| retail_demo_micro | institutional_balanced | metaquotes_demo | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.06 | 2.0 | 3.0 | 2.0 | 86.26 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| retail_demo_micro | institutional_low_risk | metaquotes_demo | generic_prop_100x_static_dd | 0.0025 | 0.02 | 0.04 | 2.0 | 3.0 | 2.0 | 86.26 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| retail_demo_micro | prop_challenge_aggressive_simulation_only | metaquotes_demo | generic_prop_100x_static_dd | 0.01 | 0.025 | 0.07 | 2.0 | 3.0 | 2.0 | 86.26 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **SIMULATION_ONLY** |
| retail_demo_micro | prop_challenge_conservative | metaquotes_demo | generic_prop_100x_static_dd | 0.0075 | 0.025 | 0.07 | 2.0 | 3.0 | 2.0 | 86.26 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **SIMULATION_ONLY** |
| retail_demo_micro | ultra_safe_demo | metaquotes_demo | generic_prop_100x_static_dd | 0.002 | 0.02 | 0.04 | 2.0 | 3.0 | 2.0 | 86.26 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **SIMULATION_ONLY** |
| retail_live_conservative | aggressive_simulation_only | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.06 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **BLOCKED** |
| retail_live_conservative | balanced | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.06 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| retail_live_conservative | conservative | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.06 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| retail_live_conservative | institutional_balanced | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.03 | 0.06 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| retail_live_conservative | institutional_low_risk | ic_markets_standard | generic_prop_100x_static_dd | 0.0025 | 0.02 | 0.04 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **PASS** |
| retail_live_conservative | prop_challenge_aggressive_simulation_only | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.025 | 0.06 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **BLOCKED** |
| retail_live_conservative | prop_challenge_conservative | ic_markets_standard | generic_prop_100x_static_dd | 0.005 | 0.025 | 0.06 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **BLOCKED** |
| retail_live_conservative | ultra_safe_demo | ic_markets_standard | generic_prop_100x_static_dd | 0.002 | 0.02 | 0.04 | 2.0 | 3.0 | 2.0 | 82.71 | PROP_RULES_WARN | NET_RR_OK | MARGIN_OK | **BLOCKED** |

## OK Checks

- Loaded 6 account profiles, 8 risk modes, 4 broker profiles, 18 prop-firm profiles
- All account profiles and risk modes enforce no_martingale, no_grid, no_averaging, no_loss_based_lot_multiplier
- 24 combination(s) PASS, 8 SIMULATION_ONLY, 0 critically BLOCKED, 16 expected incompatibility
- profile matrix audit never calls mt5.order_send
- profile matrix audit has no martingale/grid/averaging logic

## Warnings

- 8 combination(s) are SIMULATION_ONLY (demo or simulation-only risk mode) — operator must upgrade to PASS before live use
- 16 combination(s) are expected incompatibility (live account + simulation-only mode) — these are correctly BLOCKED and do not affect production readiness

**The audit NEVER calls mt5.order_send and NEVER contains martingale/grid/averaging logic.**
