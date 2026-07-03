# TITAN XAU AI - Model Artifact Health Audit (v2.8.3.3)

**Verdict:** **MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS**

**Timestamp:** 2026-07-03T04:56:48.461728+00:00

**Active models discovered:** 9

**Failed required models:** 0

## Per-Model Results

### xgboost_v1 (active_primary)

| Field | Value |
|---|---|
| artifact_exists | True |
| artifact_size_bytes | 1976253 |
| loads_successfully | True |
| load_warnings_count | 0 |
| schema_match | True |
| n_features_in | 55 |
| expected_n_features | 55 |
| prediction_works | True |
| output_finite | True |
| probabilities_in_range | True |
| no_silent_fallback | True |
| latency_ms | 1.07 |
| health | **PASS** |

### meta_label_v2_context (active_primary)

| Field | Value |
|---|---|
| artifact_exists | True |
| artifact_size_bytes | 897 |
| loads_successfully | True |
| load_warnings_count | 0 |
| schema_match | True |
| n_features_in | 22 |
| expected_n_features | 22 |
| prediction_works | True |
| output_finite | True |
| probabilities_in_range | True |
| no_silent_fallback | True |
| latency_ms | 0.328 |
| health | **PASS** |

### lightgbm_v1 (ensemble_member)

| Field | Value |
|---|---|
| artifact_exists | True |
| artifact_size_bytes | 685525 |
| loads_successfully | True |
| load_warnings_count | 0 |
| schema_match | True |
| n_features_in | 55 |
| expected_n_features | 0 |
| prediction_works | True |
| output_finite | True |
| probabilities_in_range | True |
| no_silent_fallback | True |
| latency_ms | 1.444 |
| health | **PASS** |

### logreg_v1_price (ensemble_member)

| Field | Value |
|---|---|
| artifact_exists | True |
| artifact_size_bytes | 824 |
| loads_successfully | True |
| load_warnings_count | 0 |
| schema_match | True |
| n_features_in | 13 |
| expected_n_features | 0 |
| prediction_works | True |
| output_finite | True |
| probabilities_in_range | True |
| no_silent_fallback | True |
| latency_ms | 0.16 |
| health | **PASS** |

### meta_label_v1 (ensemble_member)

| Field | Value |
|---|---|
| artifact_exists | True |
| artifact_size_bytes | 833 |
| loads_successfully | True |
| load_warnings_count | 0 |
| schema_match | True |
| n_features_in | 14 |
| expected_n_features | 0 |
| prediction_works | True |
| output_finite | True |
| probabilities_in_range | True |
| no_silent_fallback | True |
| latency_ms | 0.092 |
| health | **PASS** |

### xgboost_v2_micro (ensemble_member)

| Field | Value |
|---|---|
| artifact_exists | True |
| artifact_size_bytes | 1151133 |
| loads_successfully | True |
| load_warnings_count | 0 |
| schema_match | True |
| n_features_in | 9 |
| expected_n_features | 0 |
| prediction_works | True |
| output_finite | True |
| probabilities_in_range | True |
| no_silent_fallback | True |
| latency_ms | 0.646 |
| health | **PASS** |

### lstm_v1 (backup)

| Field | Value |
|---|---|
| artifact_exists | True |
| artifact_size_bytes | 666092 |
| loads_successfully | False |
| load_warnings_count | 1 |
| schema_match | False |
| n_features_in | 0 |
| expected_n_features | 0 |
| prediction_works | False |
| output_finite | False |
| probabilities_in_range | False |
| no_silent_fallback | False |
| latency_ms | 0.0 |
| health | **PASS_WITH_WARNINGS** |

**Compatibility warnings:**

- [RuntimeWarning] PyTorch not installed in audit env; backup .pt model not loadable here

**Load errors:**

- TORCH_NOT_INSTALLED: backup .pt model not loadable in audit env

### lstm_v2_clean (backup)

| Field | Value |
|---|---|
| artifact_exists | True |
| artifact_size_bytes | 621336 |
| loads_successfully | False |
| load_warnings_count | 1 |
| schema_match | False |
| n_features_in | 0 |
| expected_n_features | 0 |
| prediction_works | False |
| output_finite | False |
| probabilities_in_range | False |
| no_silent_fallback | False |
| latency_ms | 0.0 |
| health | **PASS_WITH_WARNINGS** |

**Compatibility warnings:**

- [RuntimeWarning] PyTorch not installed in audit env; backup .pt model not loadable here

**Load errors:**

- TORCH_NOT_INSTALLED: backup .pt model not loadable in audit env

### transformer_v1 (backup)

| Field | Value |
|---|---|
| artifact_exists | True |
| artifact_size_bytes | 833922 |
| loads_successfully | False |
| load_warnings_count | 1 |
| schema_match | False |
| n_features_in | 0 |
| expected_n_features | 0 |
| prediction_works | False |
| output_finite | False |
| probabilities_in_range | False |
| no_silent_fallback | False |
| latency_ms | 0.0 |
| health | **PASS_WITH_WARNINGS** |

**Compatibility warnings:**

- [RuntimeWarning] PyTorch not installed in audit env; backup .pt model not loadable here

**Load errors:**

- TORCH_NOT_INSTALLED: backup .pt model not loadable in audit env


## Warnings

- lstm_v1 (backup): PASS_WITH_WARNINGS - 1 compatibility warnings
- lstm_v2_clean (backup): PASS_WITH_WARNINGS - 1 compatibility warnings
- transformer_v1 (backup): PASS_WITH_WARNINGS - 1 compatibility warnings

## OK Checks

- Discovered 9 models for audit
- xgboost_v1 (active_primary): PASS
- meta_label_v2_context (active_primary): PASS
- lightgbm_v1 (ensemble_member): PASS
- logreg_v1_price (ensemble_member): PASS
- meta_label_v1 (ensemble_member): PASS
- xgboost_v2_micro (ensemble_member): PASS

## Safety

- order_send_called: False
- position_modified: False
- token_created: False
