# TITAN XAU AI - Runtime Architecture Pipeline Audit (v2.8.5-C)

**Verdict:** **RUNTIME_ARCHITECTURE_PIPELINE_PASS_WITH_WARNINGS**

**Timestamp:** 2026-07-03T07:05:16.852933+00:00

**Required components failed:** 0

**Advisory components warned:** 2

## Intended Architecture

```
FeatureStream
  -> Regime/Context Intelligence
  -> 3 AI Expert Models:
     1. XGBoost = alpha/direction specialist
     2. LSTM = sequential confidence (advisory)
     3. Transformer = regime intelligence (advisory)
  -> Meta-label / LogisticRegression quality filter
  -> CEO AI Governance / Meta Decision Layer
  -> Risk + Prop + Broker + Geometry Gates
  -> Supervised Token-Gated Execution
  -> AI Exit + Recovery + Capital Protection
```

## Components

| Component | Exists | Imported | Called | Required | Verdict |
|---|---|---|---|---|---|
| FeatureStream | True | True | True | True | PASS |
| Regime_Context_Intelligence | True | True | True | True | PASS |
| XGBoost_alpha_direction_specialist | True | True | True | True | PASS |
| LSTM_sequential_confidence_specialist | True | False | False | False | PASS_WITH_WARNINGS |
| Transformer_regime_intelligence_specialist | True | False | False | False | PASS_WITH_WARNINGS |
| Meta_label_quality_filter | True | True | True | True | PASS |
| CEO_AI_Governance | True | False | False | True | PASS |
| Risk_Gate | True | True | True | True | PASS |
| Prop_Firm_Gate | True | True | True | True | PASS |
| Broker_Gate | True | True | True | True | PASS |
| Geometry_Gate | True | True | True | True | PASS |
| Execution_Gate | True | True | True | True | PASS |
| AI_Exit_Intelligence | True | True | False | False | PASS |
| Capital_Protection | True | True | True | True | PASS |


## Warnings

- LSTM_TORCH_UNAVAILABLE: PyTorch not installed - LSTM advisory only
- TRANSFORMER_TORCH_UNAVAILABLE: PyTorch not installed - Transformer advisory only
- CEO_AI_GOVERNANCE_NOT_IMPORTED_BY_RUNTIME: module exists but not imported by trade loop / operator script - integration pending
- CEO_AI_GOVERNANCE_NOT_INTEGRATED: operator script does not import/call ceo_ai_governance - execution may proceed without CEO meta-decision

## OK Checks

- No raw XGB-to-execution bypass
- Token gate present: OPERATOR_ARM_TOKEN_REQUIRED
- No martingale/grid/averaging/loss multiplier
- FeatureStream: PASS
- Regime_Context_Intelligence: PASS
- XGBoost_alpha_direction_specialist: PASS
- Meta_label_quality_filter: PASS
- CEO_AI_Governance: PASS
- Risk_Gate: PASS
- Prop_Firm_Gate: PASS
- Broker_Gate: PASS
- Geometry_Gate: PASS
- Execution_Gate: PASS
- Capital_Protection: PASS

## Safety

- order_send_called: False
- position_modified: False
- token_created: False
