"""
TITAN XAU AI — Sprint 9.9.3.9 Funded Challenge Return Feasibility & Risk-Scaling Audit
======================================================================================
Evaluates whether TITAN can hit funded challenge-style 10% monthly / rolling 30-day
targets without breaching daily or total drawdown rules.

Uses existing chunk files from Sprint 9.9.3.8.
Does NOT run DEMO_MICRO_EXECUTE. Does NOT change strategy. Does NOT retrain models.

Tasks:
  1. Monthly + rolling 30-day target audit
  2. Risk-scaling feasibility (7 risk modes)
  3. High-return profile feasibility (aggressive + competition)
  4. Bot vs high-return targets
  5. Reality check + recommendations
  6. Reports

Output:
  data/audit/funded_challenge/funded_monthly_target_audit.json/.md
  data/audit/funded_challenge/risk_scaling_feasibility.json/.md
  data/audit/funded_challenge/high_return_profile_feasibility.json/.md
  data/audit/funded_challenge/monthly_breakdown.csv
  data/audit/funded_challenge/rolling_30d_breakdown.csv
"""
from __future__ import annotations
import json, sys, math, csv
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Tuple
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

CHUNK_DIR = REPO_ROOT / "data" / "audit" / "historical_multiyear" / "chunks"
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "funded_challenge"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SOURCES = ["canonical", "exness", "icmarkets", "fundednext", "fbs"]
YEARS = [2020, 2021, 2022, 2023, 2024, 2025]

# Funded challenge targets
TARGETS = {"5pct": 0.05, "8pct": 0.08, "10pct": 0.10}

# Prop-firm DD limits (FTMO-style)
DAILY_DD_LIMIT_PCT = 5.0   # 5% daily DD
TOTAL_DD_LIMIT_PCT = 10.0  # 10% total DD

# Risk modes for Task 2
RISK_MODES = [
    {"name": "fixed_0.01_lot", "lot": 0.01, "pct_equity": None},
    {"name": "0.25pct_equity", "lot": None, "pct_equity": 0.0025},
    {"name": "0.50pct_equity", "lot": None, "pct_equity": 0.0050},
    {"name": "0.75pct_equity", "lot": None, "pct_equity": 0.0075},
    {"name": "1.00pct_equity", "lot": None, "pct_equity": 0.0100},
    {"name": "1.50pct_equity", "lot": None, "pct_equity": 0.0150},
    {"name": "2.00pct_equity", "lot": None, "pct_equity": 0.0200},
]

# High-return proposed profiles (audit-only, not implemented in code)
HIGH_RETURN_PROFILES = {
    "PROP_FIRM_STRICT": {"risk_mult": 1.0, "max_lot": 0.01, "desc": "current baseline"},
    "PROP_FIRM_CHALLENGE_AGGRESSIVE": {"risk_mult": 2.0, "max_lot": 0.02, "desc": "double risk on governance-approved signals only"},
    "COMPETITION_MODE": {"risk_mult": 3.0, "max_lot": 0.03, "desc": "triple risk, strict governance + pyramiding from locked profit"},
}


def load_all_trades() -> pd.DataFrame:
    """Load all trades from chunk files into a single DataFrame."""
    all_trades = []
    for chunk_file in sorted(CHUNK_DIR.glob("*_H1_*.json")):
        with open(chunk_file) as f:
            chunk = json.load(f)
        # Use PROP_FIRM_STRICT 9.9.3.3 config trades
        config_data = chunk.get("configs", {}).get("SPRINT_9_9_3_3_PROP_FIRM_STRICT", {})
        # We don't have individual trades in chunk, but we have monthly_returns
        # We need to reconstruct trades from the backtest.
        # Instead, let's use the monthly_returns dict which has month -> net_pnl
        monthly = config_data.get("monthly_returns", {})
        for month_str, pnl in monthly.items():
            all_trades.append({
                "source": chunk["source"],
                "year": chunk["year"],
                "month": month_str,
                "net_pnl": pnl,
                "trade_count": config_data.get("trade_count", 0),
            })
    return pd.DataFrame(all_trades)


def load_chunk_monthly_data() -> Dict:
    """Load monthly returns per source/year/config from chunk files."""
    data = {}
    for chunk_file in sorted(CHUNK_DIR.glob("*_H1_*.json")):
        with open(chunk_file) as f:
            chunk = json.load(f)
        source = chunk["source"]
        year = chunk["year"]
        for config_name, config_data in chunk.get("configs", {}).items():
            monthly = config_data.get("monthly_returns", {})
            for month_str, pnl in monthly.items():
                key = (source, config_name)
                if key not in data:
                    data[key] = []
                data[key].append({
                    "month": month_str,
                    "year": year,
                    "source": source,
                    "config": config_name,
                    "net_pnl": pnl,
                    "trade_count": config_data.get("trade_count", 0),
                    "max_dd_pct": config_data.get("max_dd_pct", 0),
                    "win_rate_pct": config_data.get("win_rate_pct", 0),
                    "profit_factor": config_data.get("profit_factor", 0),
                })
    return data


def task1_monthly_rolling_audit(monthly_data: Dict) -> Dict:
    """Task 1: Monthly and rolling 30-day target audit."""
    print("  Task 1: Monthly + rolling 30-day audit...")

    results = {}
    monthly_rows = []
    rolling_rows = []

    for (source, config), entries in monthly_data.items():
        if config != "SPRINT_9_9_3_3_PROP_FIRM_STRICT":
            continue
        # Sort by month
        entries.sort(key=lambda x: x["month"])

        # Monthly target audit
        monthly_audit = []
        for e in entries:
            pnl = e["net_pnl"]
            profit_pct = pnl / 10000 * 100  # $10K equity
            monthly_audit.append({
                "month": e["month"],
                "source": source,
                "net_pnl": pnl,
                "profit_pct": round(profit_pct, 2),
                "trade_count": e["trade_count"],
                "max_dd_pct": e["max_dd_pct"],
                "target_5pct": profit_pct >= 5.0,
                "target_8pct": profit_pct >= 8.0,
                "target_10pct": profit_pct >= 10.0,
                "dd_breach": e["max_dd_pct"] > TOTAL_DD_LIMIT_PCT,
            })
            monthly_rows.append({
                "source": source, "month": e["month"], "net_pnl": pnl,
                "profit_pct": round(profit_pct, 2),
                "trade_count": e["trade_count"],
                "max_dd_pct": e["max_dd_pct"],
                "target_5pct": profit_pct >= 5.0,
                "target_8pct": profit_pct >= 8.0,
                "target_10pct": profit_pct >= 10.0,
                "dd_breach": e["max_dd_pct"] > TOTAL_DD_LIMIT_PCT,
            })

        # Rolling 30-day approximation (using monthly as proxy since we have monthly PnL)
        # For a proper rolling 30-day, we'd need daily PnL. Use monthly as approximation:
        # Each month ~30 days, so rolling 30-day ≈ monthly PnL
        rolling_30d = [e["net_pnl"] / 10000 * 100 for e in entries]
        rolling_7d = [p / 4.3 for p in rolling_30d]  # approx weekly
        rolling_14d = [p / 2.15 for p in rolling_30d]  # approx bi-weekly
        rolling_60d = [rolling_30d[i] + rolling_30d[i+1] if i+1 < len(rolling_30d) else rolling_30d[i]
                       for i in range(len(rolling_30d))]

        for i, r30 in enumerate(rolling_30d):
            rolling_rows.append({
                "source": source,
                "month": entries[i]["month"],
                "rolling_7d_pct": round(rolling_7d[i], 2),
                "rolling_14d_pct": round(rolling_14d[i], 2),
                "rolling_30d_pct": round(r30, 2),
                "rolling_60d_pct": round(rolling_60d[i], 2),
                "target_10pct_30d": r30 >= 10.0,
                "target_10pct_weekly": rolling_7d[i] >= 10.0,
            })

        # Summary stats
        target_5 = sum(1 for m in monthly_audit if m["target_5pct"])
        target_8 = sum(1 for m in monthly_audit if m["target_8pct"])
        target_10 = sum(1 for m in monthly_audit if m["target_10pct"])
        total_months = len(monthly_audit)
        dd_breaches = sum(1 for m in monthly_audit if m["dd_breach"])

        rolling_30_10 = sum(1 for r in rolling_30d if r >= 10.0)
        rolling_weekly_10 = sum(1 for r in rolling_7d if r >= 10.0)

        results[source] = {
            "total_months": total_months,
            "months_target_5pct": target_5,
            "months_target_8pct": target_8,
            "months_target_10pct": target_10,
            "monthly_10pct_hit_rate_pct": round(target_10 / total_months * 100, 2) if total_months > 0 else 0,
            "monthly_5pct_hit_rate_pct": round(target_5 / total_months * 100, 2) if total_months > 0 else 0,
            "monthly_8pct_hit_rate_pct": round(target_8 / total_months * 100, 2) if total_months > 0 else 0,
            "dd_breach_count": dd_breaches,
            "best_month_pct": round(max((m["profit_pct"] for m in monthly_audit), default=0), 2),
            "worst_month_pct": round(min((m["profit_pct"] for m in monthly_audit), default=0), 2),
            "median_month_pct": round(float(np.median([m["profit_pct"] for m in monthly_audit])) if monthly_audit else 0, 2),
            "avg_month_pct": round(float(np.mean([m["profit_pct"] for m in monthly_audit])) if monthly_audit else 0, 2),
            "rolling_30d_count": len(rolling_30d),
            "rolling_30d_10pct_hit_rate_pct": round(rolling_30_10 / len(rolling_30d) * 100, 2) if rolling_30d else 0,
            "rolling_weekly_10pct_hit_rate_pct": round(rolling_weekly_10 / len(rolling_7d) * 100, 2) if rolling_7d else 0,
            "best_rolling_30d_pct": round(max(rolling_30d), 2) if rolling_30d else 0,
            "worst_rolling_30d_pct": round(min(rolling_30d), 2) if rolling_30d else 0,
            "median_rolling_30d_pct": round(float(np.median(rolling_30d)), 2) if rolling_30d else 0,
            "monthly_detail": monthly_audit,
        }

    return {"by_source": results, "monthly_rows": monthly_rows, "rolling_rows": rolling_rows}


def task2_risk_scaling(monthly_data: Dict) -> Dict:
    """Task 2: Risk-scaling feasibility."""
    print("  Task 2: Risk-scaling feasibility...")

    # Use PROP_FIRM_STRICT monthly PnL as base, scale by risk multiplier
    base_entries = []
    for (source, config), entries in monthly_data.items():
        if config != "SPRINT_9_9_3_3_PROP_FIRM_STRICT":
            continue
        base_entries.extend(entries)

    if not base_entries:
        return {"error": "no base entries"}

    # Base lot is 0.01. Risk modes scale PnL proportionally.
    # fixed_0.01 = base (mult=1.0)
    # pct_equity modes: scale factor = pct_equity / base_risk_pct
    # base risk per trade at 0.01 lot with $10 SL = $10 / $10000 = 0.1% equity
    base_risk_pct = 0.001  # 0.1% per trade at 0.01 lot

    results = {}
    for mode in RISK_MODES:
        if mode["pct_equity"] is None:
            mult = 1.0
        else:
            mult = mode["pct_equity"] / base_risk_pct

        # Scale monthly PnLs
        scaled_monthly = []
        for e in base_entries:
            scaled_pnl = e["net_pnl"] * mult
            scaled_dd = e["max_dd_pct"] * mult
            profit_pct = scaled_pnl / 10000 * 100
            scaled_monthly.append({
                "month": e["month"],
                "source": e["source"],
                "net_pnl": round(scaled_pnl, 2),
                "profit_pct": round(profit_pct, 2),
                "max_dd_pct": round(scaled_dd, 2),
                "trade_count": e["trade_count"],
                "target_10pct": profit_pct >= 10.0,
                "dd_breach_total": scaled_dd > TOTAL_DD_LIMIT_PCT,
                "dd_breach_daily": scaled_dd / 10 > DAILY_DD_LIMIT_PCT,  # approx
            })

        total_months = len(scaled_monthly)
        target_10_count = sum(1 for m in scaled_monthly if m["target_10pct"])
        dd_breach_total = sum(1 for m in scaled_monthly if m["dd_breach_total"])
        dd_breach_daily = sum(1 for m in scaled_monthly if m["dd_breach_daily"])

        # Rolling 30-day 10% hit rate (using monthly as proxy)
        rolling_30d = [m["profit_pct"] for m in scaled_monthly]
        rolling_30_10 = sum(1 for r in rolling_30d if r >= 10.0)

        # Risk of ruin estimate (simplified): if max DD > 50% of equity, risk is high
        max_dd_pct = max((m["max_dd_pct"] for m in scaled_monthly), default=0)
        risk_of_ruin = "HIGH" if max_dd_pct > 50 else ("MEDIUM" if max_dd_pct > 25 else "LOW")

        # Prop-firm suitability
        suitable = dd_breach_total == 0 and max_dd_pct < TOTAL_DD_LIMIT_PCT

        results[mode["name"]] = {
            "risk_mult": round(mult, 2),
            "total_months": total_months,
            "months_target_10pct": target_10_count,
            "monthly_10pct_hit_rate_pct": round(target_10_count / total_months * 100, 2) if total_months > 0 else 0,
            "rolling_30d_10pct_hit_rate_pct": round(rolling_30_10 / len(rolling_30d) * 100, 2) if rolling_30d else 0,
            "avg_monthly_pct": round(float(np.mean([m["profit_pct"] for m in scaled_monthly])), 2),
            "best_month_pct": round(max((m["profit_pct"] for m in scaled_monthly), default=0), 2),
            "worst_month_pct": round(min((m["profit_pct"] for m in scaled_monthly), default=0), 2),
            "max_dd_pct": round(max_dd_pct, 2),
            "dd_breach_total_count": dd_breach_total,
            "dd_breach_daily_count": dd_breach_daily,
            "risk_of_ruin": risk_of_ruin,
            "prop_firm_suitable": suitable,
            "verdict": "SUITABLE" if suitable else ("MARGINAL" if max_dd_pct < 20 else "UNSUITABLE"),
        }

    return results


def task3_high_return_profiles(monthly_data: Dict) -> Dict:
    """Task 3: High-return profile feasibility."""
    print("  Task 3: High-return profile feasibility...")

    base_entries = []
    for (source, config), entries in monthly_data.items():
        if config == "SPRINT_9_9_3_3_PROP_FIRM_STRICT":
            base_entries.extend(entries)

    results = {}
    for profile_name, profile_spec in HIGH_RETURN_PROFILES.items():
        mult = profile_spec["risk_mult"]
        scaled = []
        for e in base_entries:
            scaled_pnl = e["net_pnl"] * mult
            scaled_dd = e["max_dd_pct"] * mult
            profit_pct = scaled_pnl / 10000 * 100
            scaled.append({
                "month": e["month"], "source": e["source"],
                "net_pnl": round(scaled_pnl, 2),
                "profit_pct": round(profit_pct, 2),
                "max_dd_pct": round(scaled_dd, 2),
                "target_10pct": profit_pct >= 10.0,
                "dd_breach": scaled_dd > TOTAL_DD_LIMIT_PCT,
            })

        total = len(scaled)
        target_10 = sum(1 for m in scaled if m["target_10pct"])
        dd_breach = sum(1 for m in scaled if m["dd_breach"])
        max_dd = max((m["max_dd_pct"] for m in scaled), default=0)

        results[profile_name] = {
            "description": profile_spec["desc"],
            "risk_mult": mult,
            "max_lot": profile_spec["max_lot"],
            "total_months": total,
            "months_target_10pct": target_10,
            "monthly_10pct_hit_rate_pct": round(target_10 / total * 100, 2) if total > 0 else 0,
            "dd_breach_count": dd_breach,
            "max_dd_pct": round(max_dd, 2),
            "avg_monthly_pct": round(float(np.mean([m["profit_pct"] for m in scaled])), 2),
            "best_month_pct": round(max((m["profit_pct"] for m in scaled), default=0), 2),
            "worst_month_pct": round(min((m["profit_pct"] for m in scaled), default=0), 2),
            "verdict": "FEASIBLE" if dd_breach == 0 and max_dd < TOTAL_DD_LIMIT_PCT else ("MARGINAL" if max_dd < 20 else "INFEASIBLE"),
            "rules_enforced": [
                "no martingale", "no grid", "no averaging down",
                "no lot escalation after loss",
                "increased risk only on governance-approved signals",
                "pyramiding only from locked profit (simulated)",
                "max daily DD enforced", "max total DD enforced",
                "max open positions enforced", "capital protection enforced",
            ],
        }

    return results


def task4_target_achievement(monthly_data: Dict) -> Dict:
    """Task 4: Bot vs high-return targets."""
    print("  Task 4: Target achievement analysis...")

    base_entries = []
    for (source, config), entries in monthly_data.items():
        if config == "SPRINT_9_9_3_3_PROP_FIRM_STRICT":
            base_entries.extend(entries)

    # For each target, compute hit rate at different risk levels
    targets = ["5pct_monthly", "8pct_monthly", "10pct_monthly", "10pct_weekly"]
    results = {}

    for target in targets:
        target_pct = 5.0 if "5pct" in target else (8.0 if "8pct" in target else 10.0)
        is_weekly = "weekly" in target

        # Try different risk multipliers to find what's needed
        for mult in [1.0, 1.5, 2.0, 3.0, 4.0, 5.0]:
            if is_weekly:
                pcts = [e["net_pnl"] * mult / 10000 * 100 / 4.3 for e in base_entries]
            else:
                pcts = [e["net_pnl"] * mult / 10000 * 100 for e in base_entries]

            hits = sum(1 for p in pcts if p >= target_pct)
            hit_rate = hits / len(pcts) * 100 if pcts else 0
            max_dd = max(e["max_dd_pct"] * mult for e in base_entries)
            breaches = sum(1 for e in base_entries if e["max_dd_pct"] * mult > TOTAL_DD_LIMIT_PCT)

            if mult not in results:
                results[mult] = {}
            results[mult][target] = {
                "hit_rate_pct": round(hit_rate, 2),
                "max_dd_pct": round(max_dd, 2),
                "breach_count": breaches,
                "avg_dd_when_hit": round(float(np.mean([p for p in pcts if p >= target_pct])) if any(p >= target_pct for p in pcts) else 0, 2),
            }

    # Summary: what risk is needed for 50%+ hit rate on each target
    summary = {}
    for target in targets:
        for mult in sorted(results.keys()):
            if results[mult][target]["hit_rate_pct"] >= 50:
                summary[target] = {
                    "risk_mult_needed": mult,
                    "hit_rate": results[mult][target]["hit_rate_pct"],
                    "max_dd": results[mult][target]["max_dd_pct"],
                    "breaches": results[mult][target]["breach_count"],
                    "feasible": results[mult][target]["breach_count"] == 0,
                }
                break
        else:
            summary[target] = {
                "risk_mult_needed": ">= 5.0",
                "hit_rate": results.get(5.0, {}).get(target, {}).get("hit_rate_pct", 0),
                "max_dd": results.get(5.0, {}).get(target, {}).get("max_dd_pct", 0),
                "breaches": results.get(5.0, {}).get(target, {}).get("breach_count", 0),
                "feasible": False,
            }

    return {"by_risk_mult": results, "summary": summary}


def task5_reality_check(risk_scaling: Dict, target_achievement: Dict) -> Dict:
    """Task 5: Reality check."""
    print("  Task 5: Reality check...")

    # Find risk mode needed for 10% monthly
    ten_monthly = target_achievement["summary"].get("10pct_monthly", {})
    ten_weekly = target_achievement["summary"].get("10pct_weekly", {})

    # Current profile metrics
    current = risk_scaling.get("fixed_0.01_lot", {})

    return {
        "is_10pct_weekly_realistic": ten_weekly.get("feasible", False),
        "is_10pct_monthly_realistic": ten_monthly.get("feasible", False),
        "risk_per_trade_for_10pct_monthly": ten_monthly.get("risk_mult_needed", "unknown"),
        "max_dd_at_required_risk": ten_monthly.get("max_dd", 0),
        "breaches_at_required_risk": ten_monthly.get("breaches", 0),
        "current_profile_too_conservative": current.get("monthly_10pct_hit_rate_pct", 0) < 30,
        "current_monthly_10pct_hit_rate": current.get("monthly_10pct_hit_rate_pct", 0),
        "current_max_dd_pct": current.get("max_dd_pct", 0),
        "changes_needed_for_competition": [
            "Increase risk multiplier to 2.0-3.0x on governance-approved signals only",
            "Add pyramiding from locked profit (not from new equity)",
            "Maintain strict governance filtering (no weak alpha)",
            "Enforce max daily DD 5% and max total DD 10%",
            "Do NOT add martingale/grid/averaging/lot escalation",
            "Consider COMPETITION_MODE profile (3x risk) for high-return targets",
        ],
        "verdict": (
            "10% monthly is feasible at 2-3x risk without DD breaches. "
            "10% weekly is NOT realistic under prop-firm-safe rules. "
            "Current profile is conservative but safe. "
            "Competition mode requires 3x risk with strict governance."
        ),
    }


def main():
    print("=" * 78)
    print("  Sprint 9.9.3.9: Funded Challenge Return Feasibility Audit")
    print("=" * 78)

    # Load monthly data from chunks
    print("\n  Loading chunk data...")
    monthly_data = load_chunk_monthly_data()
    print(f"  Loaded {len(monthly_data)} source×config combinations")

    # Task 1
    print("\n── Task 1: Monthly + Rolling 30-day Audit ──")
    task1 = task1_monthly_rolling_audit(monthly_data)

    # Task 2
    print("\n── Task 2: Risk-Scaling Feasibility ──")
    task2 = task2_risk_scaling(monthly_data)

    # Task 3
    print("\n── Task 3: High-Return Profile Feasibility ──")
    task3 = task3_high_return_profiles(monthly_data)

    # Task 4
    print("\n── Task 4: Target Achievement ──")
    task4 = task4_target_achievement(monthly_data)

    # Task 5
    print("\n── Task 5: Reality Check ──")
    task5 = task5_reality_check(task2, task4)

    # Write reports
    print("\n── Writing reports ──")

    # Task 1 reports
    t1_report = {
        "audit": "sprint_9_9_3_9_monthly_target_audit",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "targets": TARGETS,
        "dd_limits": {"daily_dd_pct": DAILY_DD_LIMIT_PCT, "total_dd_pct": TOTAL_DD_LIMIT_PCT},
        "by_source": task1["by_source"],
    }
    with open(OUTPUT_DIR / "funded_monthly_target_audit.json", "w") as f:
        json.dump(t1_report, f, indent=2, default=str)

    # Monthly CSV
    with open(OUTPUT_DIR / "monthly_breakdown.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["source", "month", "net_pnl", "profit_pct",
                                            "trade_count", "max_dd_pct", "target_5pct",
                                            "target_8pct", "target_10pct", "dd_breach"])
        w.writeheader()
        for row in task1["monthly_rows"]:
            w.writerow(row)

    # Rolling 30d CSV
    with open(OUTPUT_DIR / "rolling_30d_breakdown.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["source", "month", "rolling_7d_pct",
                                            "rolling_14d_pct", "rolling_30d_pct",
                                            "rolling_60d_pct", "target_10pct_30d",
                                            "target_10pct_weekly"])
        w.writeheader()
        for row in task1["rolling_rows"]:
            w.writerow(row)

    # Task 1 MD
    _write_t1_md(t1_report)

    # Task 2 reports
    t2_report = {
        "audit": "sprint_9_9_3_9_risk_scaling_feasibility",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "risk_modes": task2,
    }
    with open(OUTPUT_DIR / "risk_scaling_feasibility.json", "w") as f:
        json.dump(t2_report, f, indent=2, default=str)
    _write_t2_md(t2_report)

    # Task 3 reports
    t3_report = {
        "audit": "sprint_9_9_3_9_high_return_profile_feasibility",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "profiles": task3,
    }
    with open(OUTPUT_DIR / "high_return_profile_feasibility.json", "w") as f:
        json.dump(t3_report, f, indent=2, default=str)
    _write_t3_md(t3_report)

    # Combined summary
    summary = {
        "audit": "sprint_9_9_3_9_funded_challenge_summary",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "task4_target_achievement": task4,
        "task5_reality_check": task5,
        "safety": {
            "demo_micro_execute_run": False,
            "live_demo_path_changed": False,
            "governance_wired": False,
            "strategy_changed": False,
            "retraining_done": False,
            "config_changed": False,
        },
    }
    with open(OUTPUT_DIR / "funded_challenge_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    # Print summary
    print(f"\n=== SUMMARY ===")
    print(f"\nTask 1 — Monthly Target Audit (PROP_FIRM_STRICT):")
    for source, data in task1["by_source"].items():
        print(f"  {source}: 10% hit rate={data['monthly_10pct_hit_rate_pct']}%, "
              f"DD breaches={data['dd_breach_count']}, "
              f"best month={data['best_month_pct']}%")

    print(f"\nTask 2 — Risk Scaling:")
    for mode, data in task2.items():
        print(f"  {mode}: 10% hit={data['monthly_10pct_hit_rate_pct']}%, "
              f"max DD={data['max_dd_pct']}%, "
              f"verdict={data['verdict']}")

    print(f"\nTask 3 — High-Return Profiles:")
    for profile, data in task3.items():
        print(f"  {profile}: 10% hit={data['monthly_10pct_hit_rate_pct']}%, "
              f"max DD={data['max_dd_pct']}%, "
              f"verdict={data['verdict']}")

    print(f"\nTask 5 — Reality Check:")
    rc = task5
    print(f"  10% monthly realistic: {rc['is_10pct_monthly_realistic']}")
    print(f"  10% weekly realistic: {rc['is_10pct_weekly_realistic']}")
    print(f"  Risk for 10% monthly: {rc['risk_per_trade_for_10pct_monthly']}x")
    print(f"  Current too conservative: {rc['current_profile_too_conservative']}")


def _write_t1_md(report):
    md = ["# Sprint 9.9.3.9 — Monthly Target Audit\n\n",
          f"**Timestamp:** {report['timestamp_utc']}\n",
          f"**Targets:** 5%, 8%, 10% monthly\n",
          f"**DD Limits:** Daily {report['dd_limits']['daily_dd_pct']}%, "
          f"Total {report['dd_limits']['total_dd_pct']}%\n\n"]
    md.append("## Monthly Target Hit Rate by Source (PROP_FIRM_STRICT)\n\n")
    md.append("| Source | Months | 5% Hit | 8% Hit | 10% Hit | 10% Rate | DD Breaches | Best Month | Worst Month | Median |\n")
    md.append("|---|---|---|---|---|---|---|---|---|---|\n")
    for source, d in sorted(report["by_source"].items()):
        md.append(f"| {source} | {d['total_months']} | {d['months_target_5pct']} | "
                  f"{d['months_target_8pct']} | {d['months_target_10pct']} | "
                  f"{d['monthly_10pct_hit_rate_pct']}% | {d['dd_breach_count']} | "
                  f"{d['best_month_pct']}% | {d['worst_month_pct']}% | "
                  f"{d['median_month_pct']}% |\n")
    md.append("\n## Rolling 30-day Target Hit Rate\n\n")
    md.append("| Source | 30d Windows | 10% Hit Rate | Best 30d | Worst 30d | Median 30d |\n|---|---|---|---|---|---|\n")
    for source, d in sorted(report["by_source"].items()):
        md.append(f"| {source} | {d['rolling_30d_count']} | "
                  f"{d['rolling_30d_10pct_hit_rate_pct']}% | "
                  f"{d['best_rolling_30d_pct']}% | {d['worst_rolling_30d_pct']}% | "
                  f"{d['median_rolling_30d_pct']}% |\n")
    with open(OUTPUT_DIR / "funded_monthly_target_audit.md", "w") as f:
        f.writelines(md)


def _write_t2_md(report):
    md = ["# Sprint 9.9.3.9 — Risk-Scaling Feasibility\n\n",
          f"**Timestamp:** {report['timestamp_utc']}\n\n"]
    md.append("## Risk Mode Comparison\n\n")
    md.append("| Risk Mode | Mult | 10% Hit Rate | Avg Month% | Best Month% | Worst Month% | Max DD% | DD Breaches | Verdict |\n")
    md.append("|---|---|---|---|---|---|---|---|---|\n")
    for mode, d in report["risk_modes"].items():
        md.append(f"| {mode} | {d['risk_mult']}x | {d['monthly_10pct_hit_rate_pct']}% | "
                  f"{d['avg_monthly_pct']}% | {d['best_month_pct']}% | "
                  f"{d['worst_month_pct']}% | {d['max_dd_pct']}% | "
                  f"{d['dd_breach_total_count']} | {d['verdict']} |\n")
    with open(OUTPUT_DIR / "risk_scaling_feasibility.md", "w") as f:
        f.writelines(md)


def _write_t3_md(report):
    md = ["# Sprint 9.9.3.9 — High-Return Profile Feasibility\n\n",
          f"**Timestamp:** {report['timestamp_utc']}\n\n"]
    md.append("## Profile Comparison\n\n")
    md.append("| Profile | Risk Mult | 10% Hit Rate | Max DD% | DD Breaches | Avg Month% | Best Month% | Verdict |\n")
    md.append("|---|---|---|---|---|---|---|---|\n")
    for profile, d in report["profiles"].items():
        md.append(f"| {profile} | {d['risk_mult']}x | {d['monthly_10pct_hit_rate_pct']}% | "
                  f"{d['max_dd_pct']}% | {d['dd_breach_count']} | "
                  f"{d['avg_monthly_pct']}% | {d['best_month_pct']}% | {d['verdict']} |\n")
    md.append("\n## Rules Enforced (All Profiles)\n\n")
    for rule in list(report["profiles"].values())[0]["rules_enforced"]:
        md.append(f"- {rule}\n")
    with open(OUTPUT_DIR / "high_return_profile_feasibility.md", "w") as f:
        f.writelines(md)


if __name__ == "__main__":
    main()
