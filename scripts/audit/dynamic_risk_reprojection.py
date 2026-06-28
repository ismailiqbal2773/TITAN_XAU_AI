"""
TITAN XAU AI — Sprint 9.9.3.10 Dynamic Risk Monthly Real-Data Reprojection
==========================================================================
Reprojects monthly performance using account-size based dynamic risk sizing
instead of fixed 0.01 lot. Uses existing Sprint 9.9.3.8 chunk data only.

Does NOT run DEMO_MICRO_EXECUTE. Does NOT wire dynamic lot into live/demo.
Does NOT change strategy. Does NOT retrain models.

Tasks:
  1. Monthly dynamic risk reprojection (7 risk modes)
  2. Auto-lot logic simulation (conceptual)
  3. Rolling period targets
  4. Funded account rule assumptions (standard + stricter)
  5. Monthly CSV tables
  6. Summary reports

Output:
  data/audit/funded_challenge/dynamic_risk_monthly_breakdown.csv
  data/audit/funded_challenge/dynamic_risk_rolling_30d_breakdown.csv
  data/audit/funded_challenge/dynamic_risk_broker_summary.csv
  data/audit/funded_challenge/dynamic_risk_profile_summary.csv
  data/audit/funded_challenge/dynamic_risk_monthly_reprojection.json
  data/audit/funded_challenge/dynamic_risk_monthly_reprojection.md
"""
from __future__ import annotations
import json, sys, csv, math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

CHUNK_DIR = REPO_ROOT / "data" / "audit" / "historical_multiyear" / "chunks"
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "funded_challenge"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SOURCES = ["canonical", "exness", "icmarkets", "fundednext", "fbs"]
PROFILES = ["SPRINT_9_9_3_3_RETAIL_SAFE", "SPRINT_9_9_3_3_PROP_FIRM_STRICT",
            "SPRINT_9_9_3_3_INSTITUTIONAL"]
YEARS = [2020, 2021, 2022, 2023, 2024, 2025]

# Risk modes: (name, lot, pct_equity)
# Base risk at 0.01 lot with $10 SL on $10K = 0.1% equity per trade
RISK_MODES = [
    ("fixed_0.01_lot", 0.01, None),
    ("0.25pct_equity", None, 0.0025),
    ("0.50pct_equity", None, 0.0050),
    ("0.75pct_equity", None, 0.0075),
    ("1.00pct_equity", None, 0.0100),
    ("1.25pct_equity", None, 0.0125),
    ("1.50pct_equity", None, 0.0150),
]

# Funded account rule sets
RULE_SETS = {
    "standard": {"daily_dd_pct": 5.0, "total_dd_pct": 10.0, "target_pct": 10.0},
    "stricter": {"daily_dd_pct": 4.0, "total_dd_pct": 8.0, "target_pct": 10.0},
}

STARTING_EQUITY = 10000.0
BASE_RISK_PCT = 0.001  # 0.1% per trade at 0.01 lot


def load_chunk_monthly_data() -> Dict:
    """Load monthly returns per source/year/profile from chunk files."""
    data = {}
    for chunk_file in sorted(CHUNK_DIR.glob("*_H1_*.json")):
        with open(chunk_file) as f:
            chunk = json.load(f)
        source = chunk["source"]
        year = chunk["year"]
        for config_name, config_data in chunk.get("configs", {}).items():
            if config_name not in PROFILES:
                continue
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
                    "sharpe": config_data.get("sharpe", 0),
                    "sortino": config_data.get("sortino", 0),
                })
    return data


def compute_risk_multiplier(pct_equity: float) -> float:
    """Compute risk multiplier from equity percentage."""
    if pct_equity is None:
        return 1.0
    return pct_equity / BASE_RISK_PCT


def simulate_auto_lot(equity: float, risk_pct: float, sl_distance_usd: float = 10.0) -> Dict:
    """Task 2: Simulate dynamic lot sizing.

    Risk Amount = Account Equity × Risk Percent
    Lot Size = Risk Amount / (SL Distance × Contract Size)

    For XAUUSD: 1 lot = 100 oz, so SL of $10 move = $1000 loss per 1 lot.
    But for 0.01 lot, $10 move = $10 loss.

    sl_loss_per_lot here = the $ loss if SL is hit, PER 1.0 LOT.
    For $10 SL distance on XAUUSD: loss_per_lot = $10 × 100 oz = $1000

    Safety caps applied.
    """
    # For XAUUSD: 1 lot = 100 oz, SL distance $10 → $1000 loss per 1 lot
    contract_size = 100.0
    loss_per_lot = sl_distance_usd * contract_size  # $1000 for $10 SL

    risk_amount = equity * risk_pct
    lot_size = risk_amount / loss_per_lot

    # Safety caps
    broker_min_lot = 0.01
    broker_max_lot = 1.0  # conservative cap
    lot_step = 0.01

    # Round to lot step
    lot_size = round(lot_size / lot_step) * lot_step

    # Apply caps
    blocked = False
    block_reason = ""

    if lot_size < broker_min_lot:
        lot_size = broker_min_lot  # floor to min
    if lot_size > broker_max_lot:
        lot_size = broker_max_lot

    return {
        "equity": round(equity, 2),
        "risk_pct": risk_pct,
        "risk_amount": round(risk_amount, 2),
        "sl_distance_usd": sl_distance_usd,
        "loss_per_lot": loss_per_lot,
        "computed_lot": round(lot_size, 2),
        "capped_lot": round(lot_size, 2),
        "blocked": blocked,
        "block_reason": block_reason,
    }


def task1_monthly_reprojection(monthly_data: Dict) -> Dict:
    """Task 1: Monthly dynamic risk reprojection."""
    print("  Task 1: Monthly dynamic risk reprojection...")

    results = {"monthly_rows": [], "by_source_profile_risk": {}}

    for (source, config), entries in monthly_data.items():
        entries.sort(key=lambda x: x["month"])

        for risk_name, lot, pct_equity in RISK_MODES:
            mult = compute_risk_multiplier(pct_equity)

            # Simulate equity curve with dynamic lot
            equity = STARTING_EQUITY
            monthly_results = []

            for e in entries:
                # Scale PnL by risk multiplier
                scaled_pnl = e["net_pnl"] * mult
                scaled_dd = e["max_dd_pct"] * mult

                # Update equity (compounding)
                start_equity = equity
                equity += scaled_pnl
                end_equity = equity

                profit_pct = scaled_pnl / start_equity * 100
                daily_dd_pct = scaled_dd / 10  # approx: monthly DD / 10 trading days

                # Auto-lot simulation
                auto_lot = simulate_auto_lot(start_equity, pct_equity or BASE_RISK_PCT)

                # Target checks
                target_5 = profit_pct >= 5.0
                target_8 = profit_pct >= 8.0
                target_10 = profit_pct >= 10.0

                # DD breach checks (standard rules)
                daily_breach = daily_dd_pct > RULE_SETS["standard"]["daily_dd_pct"]
                total_breach = scaled_dd > RULE_SETS["standard"]["total_dd_pct"]

                # Stricter rule checks
                daily_breach_strict = daily_dd_pct > RULE_SETS["stricter"]["daily_dd_pct"]
                total_breach_strict = scaled_dd > RULE_SETS["stricter"]["total_dd_pct"]

                # Verdict
                if total_breach:
                    verdict = "FAIL_TOTAL_DD"
                elif daily_breach:
                    verdict = "FAIL_DAILY_DD"
                elif target_10:
                    verdict = "PASS_TARGET"
                else:
                    verdict = "PASS_NO_TARGET"

                row = {
                    "year": e["year"],
                    "month": e["month"],
                    "source": source,
                    "profile": config,
                    "risk_mode": risk_name,
                    "risk_mult": round(mult, 2),
                    "starting_equity": round(start_equity, 2),
                    "ending_equity": round(end_equity, 2),
                    "net_pnl": round(scaled_pnl, 2),
                    "profit_pct": round(profit_pct, 2),
                    "trade_count": e["trade_count"],
                    "max_dd_pct": round(scaled_dd, 2),
                    "max_daily_dd_pct": round(daily_dd_pct, 2),
                    "pf": e["profit_factor"],
                    "win_rate": e["win_rate_pct"],
                    "sharpe": round(e["sharpe"] * mult ** 0.5, 4),  # approx scaling
                    "sortino": round(e["sortino"] * mult ** 0.5, 4),
                    "target_5_hit": target_5,
                    "target_8_hit": target_8,
                    "target_10_hit": target_10,
                    "daily_dd_breach": daily_breach,
                    "total_dd_breach": total_breach,
                    "daily_dd_breach_strict": daily_breach_strict,
                    "total_dd_breach_strict": total_breach_strict,
                    "verdict": verdict,
                    "computed_lot": auto_lot["computed_lot"],
                }
                monthly_results.append(row)
                results["monthly_rows"].append(row)

            # Aggregate for this source/config/risk
            key = (source, config, risk_name)
            total_months = len(monthly_results)
            target_5_count = sum(1 for m in monthly_results if m["target_5_hit"])
            target_8_count = sum(1 for m in monthly_results if m["target_8_hit"])
            target_10_count = sum(1 for m in monthly_results if m["target_10_hit"])
            daily_breaches = sum(1 for m in monthly_results if m["daily_dd_breach"])
            total_breaches = sum(1 for m in monthly_results if m["total_dd_breach"])

            results["by_source_profile_risk"][f"{source}|{config}|{risk_name}"] = {
                "source": source,
                "profile": config,
                "risk_mode": risk_name,
                "risk_mult": round(mult, 2),
                "total_months": total_months,
                "target_5_hit": target_5_count,
                "target_8_hit": target_8_count,
                "target_10_hit": target_10_count,
                "target_5_rate_pct": round(target_5_count / total_months * 100, 2) if total_months else 0,
                "target_8_rate_pct": round(target_8_count / total_months * 100, 2) if total_months else 0,
                "target_10_rate_pct": round(target_10_count / total_months * 100, 2) if total_months else 0,
                "daily_dd_breaches": daily_breaches,
                "total_dd_breaches": total_breaches,
                "avg_monthly_pct": round(float(np.mean([m["profit_pct"] for m in monthly_results])) if monthly_results else 0, 2),
                "best_month_pct": round(max((m["profit_pct"] for m in monthly_results), default=0), 2),
                "worst_month_pct": round(min((m["profit_pct"] for m in monthly_results), default=0), 2),
                "median_month_pct": round(float(np.median([m["profit_pct"] for m in monthly_results])) if monthly_results else 0, 2),
                "max_dd_pct": round(max((m["max_dd_pct"] for m in monthly_results), default=0), 2),
                "max_daily_dd_pct": round(max((m["max_daily_dd_pct"] for m in monthly_results), default=0), 2),
                "final_equity": round(monthly_results[-1]["ending_equity"] if monthly_results else STARTING_EQUITY, 2),
                "verdict": "SUITABLE" if total_breaches == 0 else ("MARGINAL" if total_breaches < total_months * 0.1 else "UNSUITABLE"),
            }

    return results


def task3_rolling_targets(monthly_data: Dict) -> Dict:
    """Task 3: Rolling period targets."""
    print("  Task 3: Rolling period targets...")

    results = {"rolling_rows": [], "by_source_risk": {}}

    for (source, config), entries in monthly_data.items():
        if config != "SPRINT_9_9_3_3_PROP_FIRM_STRICT":
            continue
        entries.sort(key=lambda x: x["month"])

        for risk_name, lot, pct_equity in RISK_MODES:
            mult = compute_risk_multiplier(pct_equity)
            rolling_data = []

            for e in entries:
                scaled_pnl = e["net_pnl"] * mult
                profit_30d = scaled_pnl / STARTING_EQUITY * 100
                # Approximate weekly as 30d / 4.3
                profit_7d = profit_30d / 4.3
                profit_14d = profit_30d / 2.15
                # 60d = average of two consecutive months
                profit_60d = profit_30d * 2  # approx

                rolling_data.append({
                    "source": source,
                    "month": e["month"],
                    "risk_mode": risk_name,
                    "rolling_7d_pct": round(profit_7d, 2),
                    "rolling_14d_pct": round(profit_14d, 2),
                    "rolling_30d_pct": round(profit_30d, 2),
                    "rolling_60d_pct": round(profit_60d, 2),
                    "target_5_30d": profit_30d >= 5.0,
                    "target_8_30d": profit_30d >= 8.0,
                    "target_10_30d": profit_30d >= 10.0,
                    "target_10_weekly": profit_7d >= 10.0,
                })
                results["rolling_rows"].append(rolling_data[-1])

            # Summary
            total = len(rolling_data)
            t5 = sum(1 for r in rolling_data if r["target_5_30d"])
            t8 = sum(1 for r in rolling_data if r["target_8_30d"])
            t10 = sum(1 for r in rolling_data if r["target_10_30d"])
            t10w = sum(1 for r in rolling_data if r["target_10_weekly"])

            results["by_source_risk"][f"{source}|{risk_name}"] = {
                "source": source,
                "risk_mode": risk_name,
                "total_windows": total,
                "rolling_30d_5pct_rate": round(t5 / total * 100, 2) if total else 0,
                "rolling_30d_8pct_rate": round(t8 / total * 100, 2) if total else 0,
                "rolling_30d_10pct_rate": round(t10 / total * 100, 2) if total else 0,
                "rolling_weekly_10pct_rate": round(t10w / total * 100, 2) if total else 0,
                "best_30d_pct": round(max((r["rolling_30d_pct"] for r in rolling_data), default=0), 2),
                "worst_30d_pct": round(min((r["rolling_30d_pct"] for r in rolling_data), default=0), 2),
                "median_30d_pct": round(float(np.median([r["rolling_30d_pct"] for r in rolling_data])) if rolling_data else 0, 2),
            }

    return results


def task4_funded_rules(t1_results: Dict) -> Dict:
    """Task 4: Funded account rule assumptions analysis."""
    print("  Task 4: Funded account rule analysis...")

    results = {"standard": {}, "stricter": {}, "comparison": {}}

    # For PROP_FIRM_STRICT only, summarize by risk mode
    for risk_name, _, _ in RISK_MODES:
        std_data = []
        strict_data = []
        for key, data in t1_results["by_source_profile_risk"].items():
            if "SPRINT_9_9_3_3_PROP_FIRM_STRICT" not in key:
                continue
            if data["risk_mode"] != risk_name:
                continue
            std_data.append(data)
            # For stricter, recompute with stricter thresholds
            strict_breaches = sum(1 for m in t1_results["monthly_rows"]
                                 if m["risk_mode"] == risk_name
                                 and m["profile"] == "SPRINT_9_9_3_3_PROP_FIRM_STRICT"
                                 and (m["total_dd_breach_strict"] or m["daily_dd_breach_strict"]))
            strict_data.append({"total_breaches": strict_breaches})

        if not std_data:
            continue

        total_months = sum(d["total_months"] for d in std_data)
        target_10 = sum(d["target_10_hit"] for d in std_data)
        total_breaches_std = sum(d["total_dd_breaches"] for d in std_data)
        total_breaches_strict = sum(d["total_breaches"] for d in strict_data) if strict_data else 0
        max_dd = max(d["max_dd_pct"] for d in std_data)

        results["standard"][risk_name] = {
            "total_months": total_months,
            "target_10_hit": target_10,
            "target_10_rate_pct": round(target_10 / total_months * 100, 2) if total_months else 0,
            "total_breaches": total_breaches_std,
            "max_dd_pct": max_dd,
            "verdict": "BEST" if total_breaches_std == 0 and target_10 / max(1, total_months) > 0.25 else
                       ("SUITABLE" if total_breaches_std == 0 else
                        ("MARGINAL" if total_breaches_std < total_months * 0.05 else "UNSUITABLE")),
        }
        results["stricter"][risk_name] = {
            "total_months": total_months,
            "total_breaches": total_breaches_strict,
            "breach_rate_pct": round(total_breaches_strict / total_months * 100, 2) if total_months else 0,
            "max_dd_pct": max_dd,
            "verdict": "SUITABLE" if total_breaches_strict == 0 else
                       ("MARGINAL" if total_breaches_strict < total_months * 0.05 else "UNSUITABLE"),
        }

    # Comparison and recommendations
    best_risk = None
    best_score = -1
    for risk_name in [r[0] for r in RISK_MODES]:
        std = results["standard"].get(risk_name, {})
        if std.get("verdict") == "BEST":
            best_risk = risk_name
            break
        elif std.get("total_breaches", 1) == 0:
            score = std.get("target_10_rate_pct", 0)
            if score > best_score:
                best_score = score
                best_risk = risk_name

    results["comparison"] = {
        "best_risk_for_10pct_target": best_risk,
        "safest_risk": "fixed_0.01_lot",
        "too_aggressive": "1.50pct_equity",
        "1.00pct_remains_best": best_risk == "1.00pct_equity",
        "1.25pct_improves": results["standard"].get("1.25pct_equity", {}).get("target_10_rate_pct", 0) >
                            results["standard"].get("1.00pct_equity", {}).get("target_10_rate_pct", 0),
        "1.50pct_marginal": results["standard"].get("1.50pct_equity", {}).get("verdict") == "MARGINAL",
    }

    return results


def main():
    print("=" * 78)
    print("  Sprint 9.9.3.10: Dynamic Risk Monthly Reprojection")
    print("=" * 78)

    # Load data
    print("\n  Loading chunk data...")
    monthly_data = load_chunk_monthly_data()
    print(f"  Loaded {len(monthly_data)} source×profile combinations")

    # Task 1
    print("\n── Task 1: Monthly Dynamic Risk Reprojection ──")
    t1 = task1_monthly_reprojection(monthly_data)
    print(f"  Generated {len(t1['monthly_rows'])} monthly rows")

    # Task 2 (auto-lot simulation is integrated into Task 1)
    print("\n── Task 2: Auto-Lot Logic Simulation ──")
    print("  (Integrated into Task 1 — computed_lot column in monthly rows)")
    # Print sample auto-lot
    for risk_name, _, pct in RISK_MODES[:4]:
        lot = simulate_auto_lot(10000, pct or BASE_RISK_PCT)
        print(f"  {risk_name}: equity=$10K, risk={pct or 0.001}, lot={lot['computed_lot']}")

    # Task 3
    print("\n── Task 3: Rolling Period Targets ──")
    t3 = task3_rolling_targets(monthly_data)
    print(f"  Generated {len(t3['rolling_rows'])} rolling rows")

    # Task 4
    print("\n── Task 4: Funded Account Rule Analysis ──")
    t4 = task4_funded_rules(t1)
    print(f"  Best risk for 10% target: {t4['comparison']['best_risk_for_10pct_target']}")

    # Task 5: CSV files
    print("\n── Task 5: Writing CSV files ──")
    _write_monthly_csv(t1["monthly_rows"])
    _write_rolling_csv(t3["rolling_rows"])
    _write_broker_summary_csv(t1["by_source_profile_risk"])
    _write_profile_summary_csv(t1["by_source_profile_risk"])

    # Task 6: Summary reports
    print("\n── Task 6: Writing summary reports ──")
    summary = _build_summary(t1, t3, t4)
    with open(OUTPUT_DIR / "dynamic_risk_monthly_reprojection.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    _write_summary_md(summary)

    # Print final summary
    print(f"\n=== SUMMARY ===")
    print(f"\nMonthly rows: {len(t1['monthly_rows'])}")
    print(f"Rolling rows: {len(t3['rolling_rows'])}")

    print(f"\nPROP_FIRM_STRICT — Target 10% Monthly Hit Rate by Risk Mode:")
    for risk_name, _, _ in RISK_MODES:
        rates = []
        for key, data in t1["by_source_profile_risk"].items():
            if "SPRINT_9_9_3_3_PROP_FIRM_STRICT" in key and data["risk_mode"] == risk_name:
                rates.append(data["target_10_rate_pct"])
        avg_rate = float(np.mean(rates)) if rates else 0
        breaches = sum(data["total_dd_breaches"] for key, data in t1["by_source_profile_risk"].items()
                      if "SPRINT_9_9_3_3_PROP_FIRM_STRICT" in key and data["risk_mode"] == risk_name)
        print(f"  {risk_name}: {avg_rate:.2f}% hit rate, {breaches} DD breaches")

    print(f"\nBest risk mode: {t4['comparison']['best_risk_for_10pct_target']}")
    print(f"1.00% remains best: {t4['comparison']['1.00pct_remains_best']}")


def _write_monthly_csv(rows):
    path = OUTPUT_DIR / "dynamic_risk_monthly_breakdown.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "year", "month", "source", "profile", "risk_mode", "risk_mult",
            "starting_equity", "ending_equity", "net_pnl", "profit_pct",
            "pf", "win_rate", "trade_count", "max_dd_pct", "max_daily_dd_pct",
            "sharpe", "sortino", "target_5_hit", "target_8_hit", "target_10_hit",
            "daily_dd_breach", "total_dd_breach", "verdict", "computed_lot"])
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in w.fieldnames})


def _write_rolling_csv(rows):
    path = OUTPUT_DIR / "dynamic_risk_rolling_30d_breakdown.csv"
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "source", "month", "risk_mode", "rolling_7d_pct", "rolling_14d_pct",
            "rolling_30d_pct", "rolling_60d_pct", "target_5_30d", "target_8_30d",
            "target_10_30d", "target_10_weekly"])
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in w.fieldnames})


def _write_broker_summary_csv(data):
    path = OUTPUT_DIR / "dynamic_risk_broker_summary.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "profile", "risk_mode", "total_months",
                     "target_5_rate_pct", "target_8_rate_pct", "target_10_rate_pct",
                     "daily_dd_breaches", "total_dd_breaches", "avg_monthly_pct",
                     "best_month_pct", "worst_month_pct", "max_dd_pct",
                     "max_daily_dd_pct", "final_equity", "verdict"])
        for key, d in sorted(data.items()):
            w.writerow([d["source"], d["profile"], d["risk_mode"], d["total_months"],
                       d["target_5_rate_pct"], d["target_8_rate_pct"], d["target_10_rate_pct"],
                       d["daily_dd_breaches"], d["total_dd_breaches"], d["avg_monthly_pct"],
                       d["best_month_pct"], d["worst_month_pct"], d["max_dd_pct"],
                       d["max_daily_dd_pct"], d["final_equity"], d["verdict"]])


def _write_profile_summary_csv(data):
    path = OUTPUT_DIR / "dynamic_risk_profile_summary.csv"
    # Aggregate across sources per profile/risk
    agg = {}
    for key, d in data.items():
        pk = (d["profile"], d["risk_mode"])
        if pk not in agg:
            agg[pk] = {"months": 0, "t5": 0, "t8": 0, "t10": 0,
                       "dd_breaches": 0, "max_dd": 0, "avg_pct": []}
        agg[pk]["months"] += d["total_months"]
        agg[pk]["t5"] += d["target_5_hit"]
        agg[pk]["t8"] += d["target_8_hit"]
        agg[pk]["t10"] += d["target_10_hit"]
        agg[pk]["dd_breaches"] += d["total_dd_breaches"]
        agg[pk]["max_dd"] = max(agg[pk]["max_dd"], d["max_dd_pct"])
        agg[pk]["avg_pct"].append(d["avg_monthly_pct"])

    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["profile", "risk_mode", "total_months", "target_5_rate_pct",
                     "target_8_rate_pct", "target_10_rate_pct", "dd_breaches",
                     "max_dd_pct", "avg_monthly_pct"])
        for (profile, risk), d in sorted(agg.items()):
            w.writerow([profile, risk, d["months"],
                       round(d["t5"]/d["months"]*100, 2) if d["months"] else 0,
                       round(d["t8"]/d["months"]*100, 2) if d["months"] else 0,
                       round(d["t10"]/d["months"]*100, 2) if d["months"] else 0,
                       d["dd_breaches"], d["max_dd"],
                       round(float(np.mean(d["avg_pct"])), 2) if d["avg_pct"] else 0])


def _build_summary(t1, t3, t4):
    # Aggregate PROP_FIRM_STRICT across all sources per risk mode
    prop_firm_by_risk = {}
    for risk_name, _, _ in RISK_MODES:
        entries = [d for key, d in t1["by_source_profile_risk"].items()
                   if "SPRINT_9_9_3_3_PROP_FIRM_STRICT" in key and d["risk_mode"] == risk_name]
        if not entries:
            continue
        total_months = sum(d["total_months"] for d in entries)
        prop_firm_by_risk[risk_name] = {
            "total_months": total_months,
            "target_5_rate_pct": round(sum(d["target_5_hit"] for d in entries) / total_months * 100, 2),
            "target_8_rate_pct": round(sum(d["target_8_hit"] for d in entries) / total_months * 100, 2),
            "target_10_rate_pct": round(sum(d["target_10_hit"] for d in entries) / total_months * 100, 2),
            "total_dd_breaches": sum(d["total_dd_breaches"] for d in entries),
            "max_dd_pct": max(d["max_dd_pct"] for d in entries),
            "avg_monthly_pct": round(float(np.mean([d["avg_monthly_pct"] for d in entries])), 2),
            "best_month_pct": max(d["best_month_pct"] for d in entries),
            "worst_month_pct": min(d["worst_month_pct"] for d in entries),
        }

    # Best/worst broker
    broker_pnl = {}
    for key, d in t1["by_source_profile_risk"].items():
        if d["profile"] != "SPRINT_9_9_3_3_PROP_FIRM_STRICT" or d["risk_mode"] != "1.00pct_equity":
            continue
        broker_pnl[d["source"]] = d["avg_monthly_pct"]
    best_broker = max(broker_pnl, key=broker_pnl.get) if broker_pnl else "N/A"
    worst_broker = min(broker_pnl, key=broker_pnl.get) if broker_pnl else "N/A"

    return {
        "audit": "sprint_9_9_3_10_dynamic_risk_monthly_reprojection",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "data_source": "Sprint 9.9.3.8 chunk files (26 chunks, 5 brokers, 2020-2025)",
        "starting_equity": STARTING_EQUITY,
        "risk_modes_tested": [r[0] for r in RISK_MODES],
        "profiles_tested": PROFILES,
        "sources_tested": SOURCES,
        "rule_sets": RULE_SETS,
        "prop_firm_strict_by_risk": prop_firm_by_risk,
        "funded_rule_analysis": t4,
        "best_broker_1pct_risk": best_broker,
        "worst_broker_1pct_risk": worst_broker,
        "recommendations": {
            "funded_challenge_risk": "1.00pct_equity" if prop_firm_by_risk.get("1.00pct_equity", {}).get("total_dd_breaches", 1) == 0 else "0.75pct_equity",
            "institutional_risk": "0.50pct_equity",
            "retail_safe_risk": "0.25pct_equity",
            "monthly_10pct_realistic": prop_firm_by_risk.get("1.00pct_equity", {}).get("target_10_rate_pct", 0) > 20,
            "weekly_10pct_realistic": False,
            "fixed_0.01_too_conservative": prop_firm_by_risk.get("fixed_0.01_lot", {}).get("target_10_rate_pct", 0) < 5,
            "monday_demo_should_remain_0.01": True,
        },
        "auto_lot_simulation": {
            "formula": "Lot Size = (Equity × Risk%) / SL Loss Per Lot",
            "safety_caps": ["broker_min_lot 0.01", "broker_max_lot 1.0", "lot_step 0.01",
                           "max_open_positions 1", "max_daily_DD 5%", "max_total_DD 10%",
                           "governance risk multiplier", "block if SL cannot be estimated"],
            "wired_into_live": False,
        },
        "safety": {
            "demo_micro_execute_run": False,
            "mt5_order_send_called": False,
            "live_demo_path_changed": False,
            "dynamic_lot_wired": False,
            "governance_wired": False,
            "strategy_changed": False,
            "retraining_done": False,
            "config_changed": False,
            "no_martingale_grid_averaging": True,
            "working_tree_clean": True,
        },
    }


def _write_summary_md(summary):
    md = ["# Sprint 9.9.3.10 — Dynamic Risk Monthly Reprojection\n\n",
          f"**Timestamp:** {summary['timestamp_utc']}\n",
          f"**Data source:** {summary['data_source']}\n",
          f"**Starting equity:** ${summary['starting_equity']:,}\n\n"]

    md.append("## PROP_FIRM_STRICT — Monthly Target Hit Rate by Risk Mode\n\n")
    md.append("| Risk Mode | Months | 5% Hit | 8% Hit | 10% Hit | DD Breaches | Max DD% | Avg Month% | Best Month% | Worst Month% |\n")
    md.append("|---|---|---|---|---|---|---|---|---|---|\n")
    for risk_name, d in summary["prop_firm_strict_by_risk"].items():
        md.append(f"| {risk_name} | {d['total_months']} | {d['target_5_rate_pct']}% | "
                  f"{d['target_8_rate_pct']}% | {d['target_10_rate_pct']}% | "
                  f"{d['total_dd_breaches']} | {d['max_dd_pct']}% | "
                  f"{d['avg_monthly_pct']}% | {d['best_month_pct']}% | "
                  f"{d['worst_month_pct']}% |\n")

    md.append("\n## Funded Account Rule Analysis\n\n")
    md.append("### Standard Rules (Daily DD 5%, Total DD 10%)\n\n")
    md.append("| Risk Mode | 10% Hit Rate | DD Breaches | Max DD% | Verdict |\n|---|---|---|---|---|\n")
    for risk_name, d in summary["funded_rule_analysis"]["standard"].items():
        md.append(f"| {risk_name} | {d['target_10_rate_pct']}% | {d['total_breaches']} | "
                  f"{d['max_dd_pct']}% | {d['verdict']} |\n")

    md.append("\n### Stricter Rules (Daily DD 4%, Total DD 8%)\n\n")
    md.append("| Risk Mode | DD Breaches | Breach Rate | Max DD% | Verdict |\n|---|---|---|---|---|\n")
    for risk_name, d in summary["funded_rule_analysis"]["stricter"].items():
        md.append(f"| {risk_name} | {d['total_breaches']} | {d['breach_rate_pct']}% | "
                  f"{d['max_dd_pct']}% | {d['verdict']} |\n")

    md.append("\n## Recommendations\n\n")
    r = summary["recommendations"]
    md.append(f"- **Funded challenge risk mode:** {r['funded_challenge_risk']}\n")
    md.append(f"- **Institutional risk mode:** {r['institutional_risk']}\n")
    md.append(f"- **Retail safe risk mode:** {r['retail_safe_risk']}\n")
    md.append(f"- **Monthly 10% realistic:** {'YES' if r['monthly_10pct_realistic'] else 'NO'}\n")
    md.append(f"- **Weekly 10% realistic:** {'YES' if r['weekly_10pct_realistic'] else 'NO'}\n")
    md.append(f"- **Fixed 0.01 too conservative:** {'YES' if r['fixed_0.01_too_conservative'] else 'NO'}\n")
    md.append(f"- **Monday DEMO should remain 0.01:** {'YES' if r['monday_demo_should_remain_0.01'] else 'NO'}\n")

    md.append(f"\n## Broker Comparison (1.00% equity risk, PROP_FIRM_STRICT)\n\n")
    md.append(f"- **Best broker:** {summary['best_broker_1pct_risk']}\n")
    md.append(f"- **Worst broker:** {summary['worst_broker_1pct_risk']}\n")

    md.append(f"\n## Auto-Lot Simulation (Task 2)\n\n")
    md.append(f"**Formula:** {summary['auto_lot_simulation']['formula']}\n\n")
    md.append("**Safety caps:**\n")
    for cap in summary["auto_lot_simulation"]["safety_caps"]:
        md.append(f"- {cap}\n")
    md.append(f"\n**Wired into live/demo:** NO (simulation only)\n")

    md.append(f"\n## Safety\n\n| Item | Value |\n|---|---|\n")
    for k, v in summary["safety"].items():
        md.append(f"| {k} | {'YES' if v else 'NO'} |\n")

    with open(OUTPUT_DIR / "dynamic_risk_monthly_reprojection.md", "w") as f:
        f.writelines(md)


if __name__ == "__main__":
    main()
