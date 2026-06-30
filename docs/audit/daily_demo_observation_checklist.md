# TITAN XAU AI — Daily Demo Observation Checklist

**Last Updated:** 2026-06-29
**Safety:** No market execution. Observation only.

---

## Daily Command

```bash
python scripts/audit/daily_demo_observation_runner.py --since-hours 24
```

### Optional Flags

| Flag | Default | Description |
|---|---|---|
| `--since-hours` | 24 | Only look at events from the last N hours |
| `--journal` | demo_micro + repeatability journals | Add custom journal paths |
| `--max-gap-seconds` | 3600 | Max acceptable gap between events (1 hour) |
| `--final-open-positions` | 0 | Set if operator knows open positions count |

---

## Files Generated

| File | Location |
|---|---|
| JSON scorecard | `data/audit/forward_observation/daily_demo_observation_scorecard.json` |
| MD scorecard | `data/audit/forward_observation/daily_demo_observation_scorecard.md` |

These files are in `.gitignore` (runtime-generated). Do not commit raw versions.

---

## Grade Meanings

| Grade | Meaning | Action |
|---|---|---|
| **PASS** | All metrics met, no blockers, no warnings | Continue daily collection |
| **WARN** | Minor issues (gaps, low completeness, high unknown ratio) | Monitor, continue observation |
| **FAIL** | Critical issues (open positions, safety blocks, excessive gaps) | Address blockers before continuing |
| **INSUFFICIENT_DATA** | No journal events found | Run demo micro DRY_ARM_CHECK_ONLY to generate events |

---

## Score Meanings

| Score | Range | Description |
|---|---|---|
| Safety | 0–100 | 100 = no safety issues; reduced by open positions, safety blocks, gaps |
| Completeness | 0–100 | Coverage of required event categories (signal, execution, exit, regime, health, heartbeat) |
| Execution Readiness | 0–100 | Weighted combination of safety + completeness + signal/intent evidence |
| Observation Quality | 0–100 | Overall weighted quality (40% safety + 30% completeness + 30% readiness) |

---

## How to Interpret INSUFFICIENT_DATA

If the scorecard returns `INSUFFICIENT_DATA`:
1. No journal files were found or they were empty
2. Run `python scripts/audit/demo_micro_hard_gate.py` to generate a hard gate report
3. Run `python scripts/audit/demo_micro_full_cycle.py --mode DRY_ARM_CHECK_ONLY` to generate journal events
4. Re-run the daily observation runner

---

## Safety Requirements

- **Do not use live trading** — dry_run=true, live_trading=false at all times
- **Demo-only** — all execution on DEMO accounts only
- **Final open positions must be 0** unless explicit operator demo test is running
- **Do not commit raw runtime logs** if they include private account details
- **No FundedNext Free Trial** — DO NOT USE
- **MetaQuotes-Demo** is the verified broker for demo micro execution
- **No lot changes** — max lot 0.01
- **No model changes** — no retraining, no model replacement
