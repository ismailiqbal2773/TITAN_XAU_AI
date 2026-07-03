# TITAN XAU AI - Feature Parity Audit (v2.8.3.3)

**Verdict:** **FEATURE_PARITY_PASS**

**Timestamp:** 2026-07-03T04:56:52.907436+00:00

**Feature count:** 55

## Findings

| Field | Value |
|---|---|
| canonical_feature_count | 55 |
| xgb_expected_features | 55 |
| meta_expected_features | 22 |
| feature_order_stable | True |
| forbidden_features_found | [] |
| canonical_parquet_exists | True |
| can_generate_feature_row | True |

## Required Feature Groups

| Group | Present | Matched Features |
|---|---|---|
| spread | True | spread_pct, spread_zscore_60 |
| session | True | hour_sin, hour_cos, asia_session, eu_session, us_session |
| regime_context | True | rsi, adx, atr, realized_vol_20 |
| price_action | True | ret_1, ret_5, hl_range, close_pos_in_range |


## OK Checks

- Canonical FEATURE_NAMES loaded: 55 features
- Model expected features: XGB=55, META=22
- Feature count matches XGB expected
- No forbidden target/leakage/timestamp features
- All required feature groups present: ['spread', 'session', 'regime_context', 'price_action']

## Safety

- order_send_called: False
- position_modified: False
- token_created: False
