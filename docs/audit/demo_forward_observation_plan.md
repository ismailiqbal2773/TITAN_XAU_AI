# TITAN XAU AI — Demo Forward Observation Plan

**Status:** Foundation — no live trading, observation only.
**Last Updated:** 2026-06-29

---

## Objective

Observe, aggregate, validate, and report dry-run/demo-safe forward evidence
over time to build confidence in system stability, signal quality, safety
gates, and execution readiness — without placing trades.

---

## Observation Targets

### 7-Day Observation Target

| Metric | Target |
|---|---|
| Duration | 7 consecutive days |
| Daily heartbeats | >= 1 per day |
| Signal observations | >= 10 total |
| Execution intent observations | >= 5 total |
| Safety blocks | 0 CRITICAL (warnings acceptable) |
| Observation gaps | < 3 gaps > 4 hours |
| Journal completeness | >= 95% events normalized (not UNKNOWN) |
| Final open positions | 0 (unless explicit operator demo test running) |
| Verdict | OBSERVATION_READY or OBSERVATION_WARNINGS |

### 14-Day Observation Target

| Metric | Target |
|---|---|
| Duration | 14 consecutive days |
| Daily heartbeats | >= 1 per day |
| Signal observations | >= 20 total |
| Execution intent observations | >= 10 total |
| Exit intent observations | >= 5 total |
| Safety blocks | 0 CRITICAL |
| Observation gaps | < 5 gaps > 4 hours |
| Journal completeness | >= 95% |
| Final open positions | 0 |
| Verdict | OBSERVATION_READY |

### 30-Day Observation Target

| Metric | Target |
|---|---|
| Duration | 30 consecutive days |
| Daily heartbeats | >= 1 per day |
| Signal observations | >= 50 total |
| Execution intent observations | >= 20 total |
| Exit intent observations | >= 10 total |
| Regime observations | >= 10 total |
| Safety blocks | 0 CRITICAL |
| Observation gaps | < 10 gaps > 4 hours |
| Journal completeness | >= 95% |
| Final open positions | 0 |
| Verdict | OBSERVATION_READY |

---

## Required Daily Evidence

Each day of observation must produce:

1. **Heartbeat event** — system alive, dry_run confirmed
2. **Signal observation** — at least 1 model signal observed (BUY/SELL/NONE)
3. **Execution intent observation** — at least 1 intent evaluated (even if blocked)
4. **Broker health observation** — broker snapshot captured
5. **Runtime health observation** — health monitor check completed
6. **Journal completeness** — journal file exists and is non-empty

---

## Pass/Fail Criteria

### PASS

- All target metrics met for the observation period
- 0 CRITICAL safety blocks
- Final open positions = 0
- Verdict = OBSERVATION_READY

### FAIL

- Any CRITICAL safety block
- Final open positions > 0 (without explicit operator demo test)
- Verdict = OBSERVATION_BLOCKED
- Journal completeness < 90%
- Observation gaps exceed target

---

## Safety Criteria

- **No live trading** — dry_run=true, live_trading=false at all times
- **Demo-only** — all execution on DEMO accounts only
- **No lot increase** — max lot 0.01
- **No model changes** — no retraining, no model replacement
- **No strategy changes** — entry/exit logic unchanged
- **Final open positions must remain 0** unless explicit operator demo test is running
- **Raw execution evidence remains local/redacted** — no raw account data committed
- **No FundedNext Free Trial** — DO NOT USE
- **MetaQuotes-Demo** is the verified broker for demo micro execution

---

## Observation Verdicts

| Verdict | Meaning |
|---|---|
| OBSERVATION_READY | All metrics met, no blockers, safe to continue |
| OBSERVATION_WARNINGS | Metrics mostly met, warnings present but no critical blockers |
| OBSERVATION_BLOCKED | Critical safety events detected, observation halted |

---

## No Live Trading Rule

This observation framework is **observation-only**. It does NOT:
- Place trades
- Modify positions
- Send MT5 orders
- Enable live trading
- Increase risk
- Change strategy logic

The framework only observes, aggregates, validates, and reports.
