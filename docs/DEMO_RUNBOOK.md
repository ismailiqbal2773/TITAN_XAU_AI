# TITAN XAU AI — Demo Runbook

> **Last Updated:** Sprint 5 (2026-06-23)
> **Audience:** Operator running TITAN on a Windows demo account
> **Default Mode:** dry_run (NO real orders)

---

## 1. Windows MT5 Demo Setup

### 1.1 Prerequisites

| Requirement | Version | Verification |
|-------------|---------|--------------|
| Windows | 10/11 (64-bit) | `winver` |
| Python | 3.12+ | `python --version` |
| MetaTrader 5 | 5.0.45+ | MT5 terminal → Help → About |
| MT5 Demo Account | FundedNext or similar | Login + server + password |
| Disk space | 500 MB free | — |

### 1.2 MT5 Terminal Configuration

1. Install MT5 from broker website (e.g., FundedNext)
2. Login to demo account:
   - Login: `<your_demo_login>` (e.g., `34265693`)
   - Server: `FundedNext-Server 3` (or your broker's server)
   - Password: `<your_demo_password>`
3. Verify XAUUSD symbol:
   - View → Market Watch
   - Right-click → Show All
   - Find `XAUUSD` (or `GOLD`, `XAUUSD.c`)

### 1.3 Python Environment

```cmd
:: Clone repository
git clone https://github.com/ismailiqbal2773/TITAN_XAU_AI.git
cd TITAN_XAU_AI

:: Install dependencies
pip install -r titan\requirements.txt
pip install pyarrow structlog aiosqlite pytest-asyncio
```

---

## 2. Starting TITAN

### 2.1 One-Click Launch (Windows)

```cmd
:: Double-click TITAN.bat, OR:
TITAN.bat
```

The launcher will:
1. Verify Python + config + model files exist
2. Validate safety constraints (dry_run=True required)
3. Initialize all components (journal, kill-switch, inference, trade loop)
4. Run a single smoke test inference cycle
5. Write journal records to `data/runtime/titan_journal.jsonl`

### 2.2 Manual Launch (Python)

```cmd
set PYTHONPATH=%CD%
python -m titan.runtime.launcher --config config\runtime.yaml
```

### 2.3 Validate Config (No Start)

```cmd
python -m titan.runtime.launcher --config config\runtime.yaml --validate-only
```

---

## 3. Dry-Run Mode Explanation

### 3.1 What Dry-Run Does

| Action | Dry-Run (default) | Live Mode |
|--------|-------------------|-----------|
| Inference (XGBoost + meta-label) | ✓ Runs | ✓ Runs |
| Signal generation | ✓ Runs | ✓ Runs |
| OrderRequest construction | ✓ Builds | ✓ Builds |
| `mt5.order_send()` | ✗ SKIPPED | ✓ Submits |
| Position sync | ✓ Stub mode | ✓ MT5 polling |
| Journal logging | ✓ Full trail | ✓ Full trail |
| Kill-switch FSM | ✓ Active | ✓ Active |

### 3.2 How to Verify Dry-Run is Active

Check `config/runtime.yaml`:
```yaml
runtime:
  dry_run: true        # MUST be true for demo
  live_trading: false  # MUST be false for demo
```

Check environment variable:
```cmd
echo %TITAN_LIVE_TRADING%
:: Should output: 0  (or "Environment variable not defined")
```

### 3.3 Switching to Live Mode (NOT RECOMMENDED FOR DEMO)

```cmd
:: 1. Edit config/runtime.yaml:
::    dry_run: false
::    live_trading: true

:: 2. Set environment variable
set TITAN_LIVE_TRADING=1

:: 3. Run TITAN.bat — will require typed confirmation
TITAN.bat
```

---

## 4. Kill-Switch States

The kill-switch FSM has 5 states. Transitions are **one-way escalations** (de-escalation requires manual `reset()`).

| State | New Trades | Existing Positions | Trigger |
|-------|-----------|-------------------|---------|
| `NORMAL` | ✓ Allowed | Managed normally | Initial state |
| `CAUTION` | ✓ Allowed (size halved) | Managed normally | Latency > 500ms, Brier > 0.22, etc. |
| `HALT_NEW_TRADES` | ✗ Blocked | Managed normally | Daily loss > 3%, 5 consecutive losses, news event |
| `FLATTEN_ONLY` | ✗ Blocked | Exit manager requests flatten | Drawdown > 5% |
| `EMERGENCY_STOP` | ✗ Blocked | Flatten ALL immediately | Drawdown > 8%, latency > 1000ms |

### 4.1 How to Reset Kill-Switch

```python
from titan.production.kill_switch_fsm import KillSwitchFSM
fsm = KillSwitchFSM()
fsm.reset()  # Returns to NORMAL
```

Or via API (future Sprint 6):
```
POST /api/control {action: "reset_kill_switch"}
```

---

## 5. Journal Review

### 5.1 Journal Location

```
data/runtime/titan_journal.jsonl
```

Each line is a JSON record. Record types:

| Type | When | Example |
|------|------|---------|
| `SIGNAL` | Every inference output | `{direction: LONG, confidence: 0.75}` |
| `DECISION` | Every trade decision | `{accepted: true, dry_run: true}` |
| `ORDER` | Every accepted decision | `{order_request: {...}}` |
| `EXIT` | Every exit decision | `{exit_reason: TP_HIT, pnl_usd: 10.0}` |
| `MODIFY` | Every SL/TP modification | `{new_sl: 2000.5, reason: trailing}` |
| `HEARTBEAT` | Kill-switch transitions, blocks | `{event: trade_blocked_by_kill_switch}` |

### 5.2 Reading the Journal

```python
from titan.production.trade_journal import TradeJournal
journal = TradeJournal(path="data/runtime/titan_journal.jsonl")
records = journal.read_all()
for r in records:
    print(f"[{r['record_type']}] {r['data']}")
```

### 5.3 Filtering by Type

```python
signals = journal.read_by_type("SIGNAL")
exits = journal.read_by_type("EXIT")
blocks = [h for h in journal.read_by_type("HEARTBEAT")
          if h["data"].get("event") == "trade_blocked_by_kill_switch"]
```

---

## 6. Emergency Stop Process

### 6.1 Immediate Emergency Stop

If you need to stop TITAN immediately:

1. **Ctrl+C** in the TITAN.bat window
2. The launcher will call `shutdown()` which:
   - Logs `launcher_shutdown` heartbeat
   - Flushes journal to disk
   - Exits cleanly

### 6.2 Force-Kill (if unresponsive)

```cmd
:: Find TITAN process
tasklist | findstr python

:: Kill by PID
taskkill /F /PID <pid>
```

**Note:** Broker-side SL/TP remains active even if TITAN is killed — positions are protected by the broker, not by TITAN.

### 6.3 Manual Flatten via MT5

If TITAN is unresponsive and you need to close positions:

1. Open MT5 terminal
2. View → Toolbox → Trade tab
3. Right-click open position → Close
4. Confirm closure

---

## 7. Demo Pre-Flight Checklist

Before running TITAN on demo, verify each item:

### 7.1 Environment

- [ ] Python 3.12+ installed (`python --version`)
- [ ] All dependencies installed (`pip install -r titan/requirements.txt`)
- [ ] MT5 terminal installed + logged into demo account
- [ ] XAUUSD symbol visible in Market Watch

### 7.2 Configuration

- [ ] `config/runtime.yaml` exists
- [ ] `dry_run: true` in runtime section
- [ ] `live_trading: false` in runtime section
- [ ] `TITAN_LIVE_TRADING` env var NOT set (or set to `0`)
- [ ] Journal path writable (`data/runtime/`)

### 7.3 Models

- [ ] `titan/data/models/xgboost_v1.pkl` exists
- [ ] `titan/data/models/meta_label_v2_context.pkl` exists
- [ ] Models load successfully (run `python -m titan.production.model_loader`)

### 7.4 Data

- [ ] `titan/data/canonical/XAUUSD_H1_canonical.parquet` exists
- [ ] At least 300 bars of H1 data available

### 7.5 Safety Systems

- [ ] Kill-switch FSM initializes (run `python -m titan.production.kill_switch_fsm`)
- [ ] News filter CSV exists (or no events scheduled)
- [ ] Watchdog dry_run=true in config

### 7.6 Final Verification

```cmd
:: Run validation
python -m titan.runtime.launcher --config config\runtime.yaml --validate-only

:: Expected output:
:: ✓ Config loaded + validated
:: ✓ Safety validation passed
:: ✓ Runtime validation passed
:: Validation: PASS
```

---

## 8. Common Issues

### 8.1 "dry_run=false in config but TITAN_LIVE_TRADING env var is not '1'"

**Cause:** You set `dry_run: false` in config but didn't set the env var.

**Fix:**
```cmd
set TITAN_LIVE_TRADING=1
:: Then re-run TITAN.bat
```

### 8.2 "XGB model not found"

**Cause:** Model file path is wrong or file missing.

**Fix:**
1. Check `titan/data/models/xgboost_v1.pkl` exists
2. Verify `config/runtime.yaml` → `models.xgb_path` is correct
3. If file missing, re-clone repo or restore from backup

### 8.3 "Watchdog check error"

**Cause:** Watchdog component failed (rare).

**Fix:** Restart TITAN. If persists, set `watchdog.enabled: false` in config.

### 8.4 Kill-switch stuck in EMERGENCY_STOP

**Cause:** A trigger fired (max DD, latency, etc.) and the FSM cannot de-escalate automatically.

**Fix:**
1. Investigate the trigger (check journal `HEARTBEAT` records)
2. Fix the underlying issue (e.g., reduce position size, check VPS latency)
3. Reset the kill-switch manually:
```python
from titan.production.kill_switch_fsm import KillSwitchFSM
fsm = KillSwitchFSM()
fsm.reset()
```

---

## 9. Demo Trading Goals

Run TITAN on demo for **30 days** before considering live trading:

| Metric | Target | Why |
|--------|--------|-----|
| Uptime | >95% | Verify stability |
| Kill-switch triggers | <5 | Verify safety isn't too sensitive |
| Journal records | >1000 | Verify activity |
| Dry-run orders | >50 | Verify signal generation |
| False rejections | <10% | Verify config isn't too strict |

**If any metric fails, do NOT proceed to live trading.** Investigate + fix first.

---

## 10. Next Steps After Demo

1. Review 30-day journal for patterns
2. Tune kill-switch thresholds if needed
3. Consider L1 XGBoost retrain (per Phase F8 recommendation)
4. Set up co-located VPS for lower latency
5. Re-evaluate shadow-live gate (Sharpe ≥ 1.80)

**DO NOT skip the 30-day demo.** It is the cheapest insurance against live trading disasters.
