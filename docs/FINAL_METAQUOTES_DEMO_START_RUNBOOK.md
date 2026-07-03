# TITAN XAU AI — FINAL METAQUOTES-DEMO START RUNBOOK (v2.8.5)

**Sprint v2.8.5 — Final MetaQuotes-Demo Activation Readiness Gate**

This runbook contains exact Windows commands for the operator to start ONE
supervised MetaQuotes-Demo micro trade after all v2.8.5 readiness gates pass.

## CRITICAL SAFETY RULES

| Rule | Status |
|------|--------|
| NO live account | ENFORCED |
| NO funded account | ENFORCED |
| NO real account | ENFORCED |
| NO FundedNext execution | ENFORCED |
| NO martingale/grid/averaging/loss multiplier | ENFORCED |
| NO trade inside audits/build-request | ENFORCED |
| NO token creation inside audits/build-request | ENFORCED |
| NO mt5.order_send inside audits/build-request | ENFORCED |
| MetaQuotes-Demo only | ENFORCED |
| OPERATOR_ARM_TOKEN_REQUIRED for execution | ENFORCED |
| 0.01 lot, max 1 position, RR >= 2.0 | ENFORCED |

> FundedNext free trial does NOT allow EA/Python automated execution.
> FundedNext / prop firm layer remains simulation/rule logic only.
> Only MetaQuotes-Demo is allowed for actual trade execution.

---

## Step 1 — Pull latest and activate environment

Open PowerShell as regular user (NOT Administrator):

```powershell
cd "D:\Forex project\TITAN_XAU_AI"
git pull origin main
myenv\Scripts\activate
git status
```

**Expected:**
- `Already up to date.` OR fast-forward to latest commit
- Working tree clean
- `(myenv)` prefix in PowerShell prompt

If `git status` shows uncommitted changes, do NOT proceed. Investigate first.

---

## Step 2 — Run all readiness audits (read-only)

Run all 6 audits in sequence. Each must PASS before proceeding to Step 3.

### 2.1 Model Artifact Health Audit

```powershell
python scripts/audit/model_artifact_health_audit.py
```

**Expected:**
- Verdict: `MODEL_ARTIFACT_HEALTH_PASS` or `MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS`
- Failed required models: 0
- v2.8.4 allowed: True
- Per-model: xgboost_v1 (active_primary) PASS, meta_label_v2_context (active_primary) PASS
- Per-model: lightgbm_v1, logreg_v1_price, meta_label_v1, xgboost_v2_micro (optional) PASS or non-blocking
- Per-model: lstm_v1, lstm_v2_clean, transformer_v1 (backup) PASS_WITH_WARNINGS

If `MODEL_ARTIFACT_HEALTH_BLOCKED`: **STOP**. Do not proceed.

### 2.2 Feature Parity Audit

```powershell
python scripts/audit/feature_parity_audit.py
```

**Expected:**
- Verdict: `FEATURE_PARITY_PASS` or `FEATURE_PARITY_PASS_WITH_WARNINGS`
- Feature count: 55
- No forbidden features
- All required feature groups present

If `FEATURE_PARITY_BLOCKED`: **STOP**. Do not proceed.

### 2.3 Runtime Safety Gate Audit

```powershell
python scripts/audit/runtime_safety_gate_audit.py
```

**Expected:**
- Verdict: `RUNTIME_SAFETY_GATE_PASS`
- dry_run=true, live_trading=false
- prop_funded_safe: max_positions=1, max_lot<=0.01, risk<=0.5%
- No martingale/grid/averaging/loss multiplier
- mt5.order_send not reachable from build-request/autonomous-entry-check/audit scripts
- OPERATOR_ARM_TOKEN_REQUIRED marker present

If `RUNTIME_SAFETY_GATE_BLOCKED`: **STOP**. Do not proceed.

### 2.4 Prop Challenge Growth Profile Audit

```powershell
python scripts/audit/prop_challenge_growth_profile_audit.py
```

**Expected:**
- Profile: `PROP_CHALLENGE_GROWTH_30_8`
- Verdict: `PROP_CHALLENGE_GROWTH_PROFILE_PASS`
- Monthly target: 0.30 (target, NOT guarantee)
- Daily DD band: 0.01 to 0.02
- Total DD cap: 0.08
- No forced trading: True
- No martingale/grid/averaging/loss multiplier: True

If `PROP_CHALLENGE_GROWTH_PROFILE_BLOCKED`: **STOP**. Do not proceed.

### 2.5 Final Demo Activation Readiness Audit

```powershell
python scripts/audit/final_demo_activation_readiness_audit.py
```

**Expected:**
- Verdict: `FINAL_DEMO_ACTIVATION_READY_SUPERVISED`
- Final demo activation allowed: True
- MetaQuotes-Demo verified: True (requires MT5 terminal running)
- Account type: DEMO
- Open positions count: 0
- Pending orders count: 0
- Stale token detected: False
- Build-request: PASS
- execution_now_allowed: False
- execution_blocker: OPERATOR_ARM_TOKEN_REQUIRED

If `FINAL_DEMO_ACTIVATION_BLOCKED`: **STOP**. Do not proceed.

If MetaQuotes-Demo verified is False: ensure MT5 terminal is running with
MetaQuotes-Demo account logged in, then re-run this audit.

### 2.6 Production Closure Readiness Audit

```powershell
python scripts/audit/production_closure_readiness_audit.py
```

**Expected:**
- Verdict: `PRODUCTION_CLOSURE_READY_WITH_SAFE_DEFAULTS`
- Production Score: 92/100
- HIGH warnings: []
- Blockers: 0
- Autonomous execution status: SUPERVISED_READY
- v2.8.4 allowed: True
- Growth profile allowed: True
- Final demo activation allowed: True

If any blocker: **STOP**. Do not proceed.

---

## Step 3 — Run build-request (read-only)

```powershell
python scripts/operator/run_managed_demo_micro_trade.py --build-request --prop-funded-profile prop_funded_safe --use-adaptive-trailing --use-dynamic-tp-extension
```

**Expected:**
- Mode: build_request
- Verdict: PASS
- Blockers: 0
- Normalized verdict: PASS
- Request status: READY_FOR_SUPERVISED_OPERATOR_ARM
- Latest model health verdict: PASS or PASS_WITH_WARNINGS
- Failed required models: 0
- Latest feature parity verdict: PASS
- Latest runtime safety verdict: PASS
- Latest growth profile verdict: PASS
- Final demo activation verdict: FINAL_DEMO_ACTIVATION_READY_SUPERVISED
- final_demo_activation_allowed: True
- v2.8.4 allowed: True
- execution_now_allowed: False
- execution_blocker: OPERATOR_ARM_TOKEN_REQUIRED

If build-request shows BLOCKED or any gate fails: **STOP**. Do not proceed.

> Build-request is READ-ONLY. It does NOT call mt5.order_send,
> does NOT create token, does NOT modify positions.

---

## Step 4 — Create operator execution token (ONLY if all above pass)

> **WARNING:** Only run this step if:
> - All 6 audits in Step 2 PASS
> - Build-request in Step 3 shows PASS with all gates green
> - Operator has explicitly decided to start ONE supervised MetaQuotes-Demo micro trade
>
> If any audit blocks, do NOT create token.

```powershell
python scripts/operator/create_local_operator_execution_token.py --symbol XAUUSD --lot 0.01 --broker MetaQuotes-Demo --expiry-minutes 10
```

**Expected:**
- Token created at `data/runtime/operator_execution_token.json`
- Token expiry: 10 minutes from creation
- Token symbol: XAUUSD
- Token lot: 0.01
- Token broker: MetaQuotes-Demo

> Token expires after 10 minutes. If you need more time, recreate the token.
> Never share the token file. Never commit it to git.

---

## Step 5 — Run ONE supervised MetaQuotes-Demo micro trade

> **WARNING:** This step calls mt5.order_send only after explicit token AND
> all confirmations are passed. This is the ONLY step in this runbook that
> executes a real trade (on MetaQuotes-Demo, NOT live/funded/real).
>
> Do NOT run this on FundedNext.
> Do NOT run on live/real/funded account.
> Only MetaQuotes-Demo is allowed.
> If any audit blocks, do NOT create token (Step 4) and do NOT run this step.

```powershell
python scripts/operator/run_managed_demo_micro_trade.py --execute-and-monitor --use-adaptive-trailing --use-dynamic-tp-extension --adaptive-policy-mode balanced_conservative --i-understand-demo-risk --confirm-symbol XAUUSD --confirm-lot 0.01 --confirm-broker MetaQuotes-Demo --confirm-one-order-only --confirm-not-live --confirm-environment-locked --confirm-model-parity-pass --confirm-local-operator --confirm-managed-trailing --monitor-duration-minutes 30 --monitor-interval-seconds 5
```

**Expected behavior:**
1. Script validates operator token (must be present and not stale)
2. Script validates all confirmations (8 confirm flags required)
3. Script validates account is MetaQuotes-Demo DEMO (NOT live/funded/real)
4. Script validates no open XAUUSD position exists
5. Script validates symbol XAUUSD available and spread within limit
6. Script calls `mt5.order_send` ONCE with 0.01 lot
7. Script monitors position for 30 minutes (or until closed)
8. Script writes execution receipt to `data/runtime/demo_micro_execution_receipt.json`
9. Script writes monitor log to `data/audit/demo_micro_execution/`
10. On completion, position is closed (if still open) and receipt finalized

**If anything goes wrong:**
- Script will fail-closed and NOT send order
- If order sent but monitor fails, position may remain open - check MT5 terminal manually
- If token is stale or invalid, re-create token (Step 4) and retry

---

## Post-Trade Steps (after Step 5 completes)

After the supervised micro trade completes (position closed, monitor finished):

### 6.1 Verify receipt was written

```powershell
python scripts/audit/demo_micro_evidence_verifier.py
```

**Expected:** MICRO_PROOF_PASS

### 6.2 Verify execution geometry

```powershell
python scripts/audit/execution_geometry_receipt_audit.py
```

**Expected:** EXECUTION_GEOMETRY_PASS

### 6.3 Run forensics reconciliation

```powershell
python scripts/audit/demo_micro_forensics_reconciliation.py
```

**Expected:** DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED

### 6.4 Re-run final demo activation audit (should now block until receipt resolved)

```powershell
python scripts/audit/final_demo_activation_readiness_audit.py
```

**Expected:** Either READY_SUPERVISED (if receipt auto-resolved) or BLOCKED with `UNRESOLVED_ACTIVE_RECEIPT` (operator must archive/clear the receipt before next trade)

### 6.5 Delete operator token (security hygiene)

```powershell
del data\runtime\operator_execution_token.json
```

---

## Troubleshooting

### Issue: MT5_NOT_AVAILABLE on final demo activation audit

**Cause:** MetaTrader5 Python package not installed in myenv, OR MT5 terminal not running.

**Fix:**
1. Ensure MT5 terminal is running and logged into MetaQuotes-Demo account
2. Install MetaTrader5 package: `pip install MetaTrader5`
3. Re-run: `python scripts/audit/final_demo_activation_readiness_audit.py`

### Issue: ACCOUNT_SERVER_NOT_METAQUOTES_DEMO

**Cause:** MT5 terminal logged into wrong server (e.g. FundedNext, ICMarkets-Live, etc.)

**Fix:**
1. Open MT5 terminal
2. Logout of current account
3. Login to MetaQuotes-Demo account (login credentials from operator)
4. Re-run final demo activation audit

### Issue: OPEN_XAUUSD_POSITION_EXISTS

**Cause:** A previous XAUUSD position is still open on MetaQuotes-Demo.

**Fix:**
1. Open MT5 terminal
2. Manually close the open XAUUSD position
3. Wait 30 seconds for state to propagate
4. Re-run: `python scripts/audit/final_demo_activation_readiness_audit.py`

### Issue: STALE_OPERATOR_TOKEN

**Cause:** An old operator token file exists at `data/runtime/operator_execution_token.json` and is older than 1 hour.

**Fix:**
1. Delete the stale token: `del data\runtime\operator_execution_token.json`
2. Re-run: `python scripts/audit/final_demo_activation_readiness_audit.py`
3. If you need a new token for a new trade, recreate via Step 4

### Issue: UNRESOLVED_ACTIVE_RECEIPT

**Cause:** A previous execution receipt exists at `data/runtime/demo_micro_execution_receipt.json` AND there is an open XAUUSD position.

**Fix:**
1. Close the open XAUUSD position in MT5 terminal
2. Run: `python scripts/audit/demo_micro_evidence_verifier.py` to verify receipt
3. Archive the receipt: `python scripts/audit/archive_pass_evidence.py`
4. Re-run: `python scripts/audit/final_demo_activation_readiness_audit.py`

### Issue: Build-request shows BLOCKED but audits all pass

**Cause:** Build-request reads cached audit JSONs. If audits were re-run after the last build-request, the cached report may be stale.

**Fix:**
1. Re-run: `python scripts/operator/run_managed_demo_micro_trade.py --build-request --prop-funded-profile prop_funded_safe --use-adaptive-trailing --use-dynamic-tp-extension`
2. The new build-request will read fresh audit JSONs

---

## Reference

- Latest verified commit: see `git log --oneline -1`
- Audit outputs: `data/audit/`
- Runtime receipts: `data/runtime/`
- Operator token: `data/runtime/operator_execution_token.json`
- Execution receipt: `data/runtime/demo_micro_execution_receipt.json`
- Managed trade report: `data/audit/demo_micro_execution/managed_trade_report.json`
- Production closure report: `data/audit/demo_micro_execution/production_closure_readiness_audit.json`
- Final demo activation report: `data/audit/final_demo_activation/final_demo_activation_readiness_audit.json`

---

## Safety Checklist (verify before Step 5)

- [ ] All 6 audits in Step 2 PASS
- [ ] Build-request in Step 3 shows PASS with all gates green
- [ ] Operator token created (Step 4) with valid expiry
- [ ] MT5 terminal running with MetaQuotes-Demo DEMO account
- [ ] No open XAUUSD position
- [ ] No pending XAUUSD order
- [ ] No stale operator token
- [ ] 0.01 lot confirmed
- [ ] 1 order only confirmed
- [ ] NOT live confirmed
- [ ] Environment locked confirmed
- [ ] Model parity pass confirmed
- [ ] Local operator confirmed
- [ ] Managed trailing confirmed
- [ ] Monitor duration set to 30 minutes
- [ ] Monitor interval set to 5 seconds

**Only after all checkboxes are verified, proceed to Step 5.**

---

## Emergency Stop

If at any point during Step 5 (monitoring) you need to emergency-stop:

1. **DO NOT** close the PowerShell window (the script may leave position open)
2. Open MT5 terminal
3. Manually close the XAUUSD position
4. Wait for the script to detect position close and exit gracefully
5. If script hangs, press `Ctrl+C` in PowerShell
6. Verify position is closed in MT5 terminal
7. Run: `python scripts/audit/demo_micro_evidence_verifier.py` to verify receipt
8. Delete token: `del data\runtime\operator_execution_token.json`

---

**End of Runbook — Sprint v2.8.5**
