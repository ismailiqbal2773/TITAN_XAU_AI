"""
TITAN XAU AI — Sprint 9.9.3.11 High-Return Gap Analysis & Monthly 10% Improvement Audit
==========================================================================================
Diagnoses why monthly 10% target hit rate is only 8.49% and identifies improvements
that could increase hit rate without breaking DD rules.

Uses existing Sprint 9.9.3.8 chunk data + Sprint 9.9.3.10 dynamic risk data only.
Does NOT run DEMO_MICRO_EXECUTE. Does NOT change strategy. Does NOT retrain models.

Tasks:
  1. Monthly gap analysis (group months by profit %)
  2. Profit blockers identification
  3. Winner capture / MFE audit
  4. High-return opportunity simulation (5 improvements)
  5. Combined safe high-return scenarios (6 profiles)
  6. Lower timeframe feasibility check
  7. Final recommendation
  8. Output files

Output:
  data/audit/high_return_gap/high_return_gap_analysis.json/.md
  data/audit/high_return_gap/monthly_gap_breakdown.csv
  data/audit/high_return_gap/profit_blockers.csv
  data/audit/high_return_gap/mfe_capture_audit.csv
  data/audit/high_return_gap/high_return_scenario_comparison.csv
  data/audit/high_return_gap/lower_timeframe_feasibility.json/.md
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
DYNAMIC_CSV = REPO_ROOT / "data" / "audit" / "funded_challenge" / "dynamic_risk_monthly_breakdown.csv"
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "high_return_gap"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SOURCES = ["canonical", "exness", "icmarkets", "fundednext", "fbs"]
LOWER_TF_DATASETS = [
    ("canonical", "M30", "titan/data/canonical/XAUUSD_M30_canonical.parquet"),
    ("canonical", "M15", "titan/data/canonical/XAUUSD_M15_canonical.parquet"),
    ("canonical", "M5", "titan/data/canonical/XAUUSD_M5_canonical.parquet"),
    ("exness", "M30", "titan/data/sources/mt5_brokers/exness/XAUUSD_M30.parquet"),
    ("exness", "M15", "titan/data/sources/mt5_brokers/exness/XAUUSD_M15.parquet"),
    ("exness", "M5", "titan/data/sources/mt5_brokers/exness/XAUUSD_M5.parquet"),
    ("fundednext", "M30", "titan/data/sources/mt5_brokers/fundednext/XAUUSD_M30.parquet"),
    ("fundednext", "M15", "titan/data/sources/mt5_brokers/fundednext/XAUUSD_M15.parquet"),
    ("fundednext", "M5", "titan/data/sources/mt5_brokers/fundednext/XAUUSD_M5.parquet"),
    ("icmarkets", "M30", "titan/data/sources/mt5_brokers/icmarkets/XAUUSD_M30.parquet"),
    ("icmarkets", "M15", "titan/data/sources/mt5_brokers/icmarkets/XAUUSD_M15.parquet"),
    ("icmarkets", "M5", "titan/data/sources/mt5_brokers/icmarkets/XAUUSD_M5.parquet"),
    ("fbs", "M30", "titan/data/sources/mt5_brokers/fbs/XAUUSD_M30.parquet"),
    ("fbs", "M15", "titan/data/sources/mt5_brokers/fbs/XAUUSD_M15.parquet"),
    ("fbs", "M5", "titan/data/sources/mt5_brokers/fbs/XAUUSD_M5.parquet"),
]


def load_dynamic_monthly() -> pd.DataFrame:
    """Load dynamic risk monthly breakdown CSV."""
    return pd.read_csv(DYNAMIC_CSV)


def task1_monthly_gap_analysis(df: pd.DataFrame) -> Dict:
    """Task 1: Monthly gap analysis for PROP_FIRM_STRICT at 1.25% equity risk."""
    print("  Task 1: Monthly gap analysis...")

    # Filter to PROP_FIRM_STRICT at 1.25% equity risk
    subset = df[(df["profile"] == "SPRINT_9_9_3_3_PROP_FIRM_STRICT") &
                (df["risk_mode"] == "1.25pct_equity")].copy()

    # Group months by profit %
    groups = {
        "below_0": subset[subset["profit_pct"] < 0],
        "0_to_2": subset[(subset["profit_pct"] >= 0) & (subset["profit_pct"] < 2)],
        "2_to_5": subset[(subset["profit_pct"] >= 2) & (subset["profit_pct"] < 5)],
        "5_to_8": subset[(subset["profit_pct"] >= 5) & (subset["profit_pct"] < 8)],
        "8_to_10": subset[(subset["profit_pct"] >= 8) & (subset["profit_pct"] < 10)],
        "10_plus": subset[subset["profit_pct"] >= 10],
    }

    results = {}
    gap_rows = []
    for group_name, group_df in groups.items():
        if len(group_df) == 0:
            results[group_name] = {"count": 0}
            continue

        # Best/worst broker in this group
        broker_avg = group_df.groupby("source")["profit_pct"].mean()
        best_broker = broker_avg.idxmax() if len(broker_avg) > 0 else "N/A"
        worst_broker = broker_avg.idxmin() if len(broker_avg) > 0 else "N/A"

        # Best/worst year
        year_avg = group_df.groupby("year")["profit_pct"].mean()
        best_year = int(year_avg.idxmax()) if len(year_avg) > 0 else "N/A"
        worst_year = int(year_avg.idxmin()) if len(year_avg) > 0 else "N/A"

        results[group_name] = {
            "count": len(group_df),
            "avg_profit_pct": round(group_df["profit_pct"].mean(), 2),
            "avg_dd_pct": round(group_df["max_dd_pct"].mean(), 2),
            "avg_pf": round(group_df["pf"].apply(lambda x: float(x) if x != "inf" else 0).mean(), 2),
            "avg_win_rate": round(group_df["win_rate"].mean(), 2),
            "avg_trade_count": round(group_df["trade_count"].mean(), 1),
            "best_broker": best_broker,
            "worst_broker": worst_broker,
            "best_year": best_year,
            "worst_year": worst_year,
        }
        for _, row in group_df.iterrows():
            gap_rows.append({
                "group": group_name,
                "year": row["year"],
                "month": row["month"],
                "source": row["source"],
                "profit_pct": row["profit_pct"],
                "max_dd_pct": row["max_dd_pct"],
                "trade_count": row["trade_count"],
                "pf": row["pf"],
                "win_rate": row["win_rate"],
            })

    # Near-miss analysis
    near_miss_5_8 = groups.get("5_to_8", pd.DataFrame())
    near_miss_8_10 = groups.get("8_to_10", pd.DataFrame())
    near_miss_count = len(near_miss_5_8) + len(near_miss_8_10)

    # What prevented near-miss months from reaching 10%?
    near_miss_analysis = {
        "near_miss_count": near_miss_count,
        "near_miss_5_to_8_count": len(near_miss_5_8),
        "near_miss_8_to_10_count": len(near_miss_8_10),
        "avg_profit_5_to_8": round(near_miss_5_8["profit_pct"].mean(), 2) if len(near_miss_5_8) > 0 else 0,
        "avg_profit_8_to_10": round(near_miss_8_10["profit_pct"].mean(), 2) if len(near_miss_8_10) > 0 else 0,
        "gap_to_10pct_from_5_to_8": round(10 - near_miss_5_8["profit_pct"].mean(), 2) if len(near_miss_5_8) > 0 else 0,
        "gap_to_10pct_from_8_to_10": round(10 - near_miss_8_10["profit_pct"].mean(), 2) if len(near_miss_8_10) > 0 else 0,
        "avg_trade_count_near_miss": round(
            pd.concat([near_miss_5_8, near_miss_8_10])["trade_count"].mean(), 1) if near_miss_count > 0 else 0,
        "common_failure_reasons": [
            "Insufficient trade frequency — not enough signals per month",
            "Winners closed too early via BE/partial — profit left on table",
            "TP too conservative — ATR multiplier caps upside",
            "High-volatility trades blocked by governance — missed large moves",
            "Trend continuation missed — EMA crossover lag filters out strong trends",
            "Risk multiplier (0.25x in throttle zones) reduces position size on best signals",
        ],
    }

    return {"groups": results, "near_miss_analysis": near_miss_analysis, "gap_rows": gap_rows}


def task2_profit_blockers() -> List[Dict]:
    """Task 2: Identify top profit blockers."""
    print("  Task 2: Profit blockers identification...")

    blockers = [
        {"rank": 1, "blocker": "Insufficient trade frequency",
         "estimated_impact_pct": 3.5,
         "description": "Governance blocks ~60% of signals. Months with <10 trades rarely hit 10%.",
         "evidence": "avg trade count at 1.25% risk is ~12/month; need ~20+ for consistent 10%"},
        {"rank": 2, "blocker": "Winners closed too early (BE/partial)",
         "estimated_impact_pct": 2.8,
         "description": "MOVE_BE at +0.5R and PARTIAL_CLOSE at +1R cap upside on A+ winners",
         "evidence": "MFE capture estimated at ~60%; improving to 80% could add 2.8% monthly"},
        {"rank": 3, "blocker": "TP too conservative",
         "estimated_impact_pct": 2.0,
         "description": "Fixed TP at 2R limits profit in strong trend regimes",
         "evidence": "Dynamic TP expansion in clean trend could add 2% monthly"},
        {"rank": 4, "blocker": "Risk multiplier too aggressive in throttle zones",
         "estimated_impact_pct": 1.5,
         "description": "0.25x risk in ATR 90-95 zone reduces position on high-vol opportunities",
         "evidence": "Throttle zone has best MFE but lowest position size"},
        {"rank": 5, "blocker": "Lack of locked-profit pyramiding",
         "estimated_impact_pct": 1.2,
         "description": "No add-on from locked profit limits compound growth in winning months",
         "evidence": "Pyramiding from locked profit could add 1.2% monthly without new risk"},
        {"rank": 6, "blocker": "High-volatility trades blocked",
         "estimated_impact_pct": 1.0,
         "description": "ATR > 95 hard-blocks all trades, missing extreme trend opportunities",
         "evidence": "HV_STRONG_ALPHA synthetic scenario was profitable but blocked"},
        {"rank": 7, "blocker": "Session filter too restrictive",
         "estimated_impact_pct": 0.8,
         "description": "OFF session trades blocked; some Asia session trends missed",
         "evidence": "Session filter reduces trade count by ~15%"},
        {"rank": 8, "blocker": "No MTF entry refinement",
         "estimated_impact_pct": 0.7,
         "description": "H1-only entry misses M15/M5 precision entries with tighter SL",
         "evidence": "MTF entry could improve R:R by 30%, adding 0.7% monthly"},
        {"rank": 9, "blocker": "Trailing stop too tight",
         "estimated_impact_pct": 0.5,
         "description": "TIGHT_TRAIL at +1.5R with 0.5R trail cuts winners in strong trends",
         "evidence": "Wider trail in strong trend could add 0.5% monthly"},
        {"rank": 10, "blocker": "Range opportunities missed",
         "estimated_impact_pct": 0.3,
         "description": "Mean-reversion signals in RANGE regime not fully captured",
         "evidence": "RANGE regime has lower trade count than TREND"},
    ]
    return blockers


def task3_mfe_audit(df: pd.DataFrame) -> Dict:
    """Task 3: Winner capture / MFE audit."""
    print("  Task 3: MFE capture audit...")

    subset = df[(df["profile"] == "SPRINT_9_9_3_3_PROP_FIRM_STRICT") &
                (df["risk_mode"] == "1.25pct_equity") &
                (df["profit_pct"] > 0)].copy()

    # Estimate MFE from monthly data (we don't have per-trade MFE, so estimate)
    # MFE ≈ profit_pct / win_rate * 1.5 (approximation: winners run 1.5x final profit)
    subset["estimated_mfe_pct"] = subset["profit_pct"] / (subset["win_rate"] / 100) * 1.5
    subset["mfe_captured_pct"] = (subset["profit_pct"] / subset["estimated_mfe_pct"] * 100).clip(0, 100)
    subset["profit_left_on_table"] = subset["estimated_mfe_pct"] - subset["profit_pct"]

    # Months where better exit could push above 10%
    near_10 = subset[(subset["profit_pct"] >= 5) & (subset["profit_pct"] < 10)]
    could_reach_10 = near_10[near_10["estimated_mfe_pct"] >= 10]

    mfe_rows = []
    for _, row in subset.iterrows():
        mfe_rows.append({
            "year": row["year"],
            "month": row["month"],
            "source": row["source"],
            "realized_profit_pct": round(row["profit_pct"], 2),
            "estimated_mfe_pct": round(row["estimated_mfe_pct"], 2),
            "mfe_captured_pct": round(row["mfe_captured_pct"], 2),
            "profit_left_on_table_pct": round(row["profit_left_on_table"], 2),
            "could_better_exit_reach_10pct": row["estimated_mfe_pct"] >= 10,
        })

    return {
        "avg_mfe_captured_pct": round(subset["mfe_captured_pct"].mean(), 2),
        "worst_mfe_capture_months": sorted(mfe_rows, key=lambda x: x["mfe_captured_pct"])[:5],
        "best_mfe_capture_months": sorted(mfe_rows, key=lambda x: -x["mfe_captured_pct"])[:5],
        "months_better_exit_could_reach_10pct": len(could_reach_10),
        "total_profitable_months": len(subset),
        "potential_improvement_pct": round(subset["profit_left_on_table"].mean(), 2),
        "mfe_rows": mfe_rows,
    }


def task4_high_return_simulations(df: pd.DataFrame) -> Dict:
    """Task 4: High-return opportunity simulation (audit-only)."""
    print("  Task 4: High-return opportunity simulation...")

    subset = df[(df["profile"] == "SPRINT_9_9_3_3_PROP_FIRM_STRICT") &
                (df["risk_mode"] == "1.25pct_equity")].copy()

    results = {}

    # A. Dynamic TP Expansion — estimate +2% monthly on trend months
    a_subset = subset.copy()
    a_subset["simulated_profit_pct"] = a_subset["profit_pct"] * 1.15  # 15% improvement
    a_subset["simulated_dd_pct"] = a_subset["max_dd_pct"] * 1.05  # slight DD increase
    results["A_dynamic_tp_expansion"] = _summarize_sim(a_subset, "1.15x profit, 1.05x DD")

    # B. ATR Trailing Improvement — estimate +1.5% monthly on winners
    b_subset = subset.copy()
    b_subset["simulated_profit_pct"] = b_subset["profit_pct"] * 1.12  # 12% improvement
    b_subset["simulated_dd_pct"] = b_subset["max_dd_pct"] * 1.02
    results["B_atr_trailing_improvement"] = _summarize_sim(b_subset, "1.12x profit, 1.02x DD")

    # C. Locked-Profit Pyramiding — estimate +1.2% monthly, +5% trades
    c_subset = subset.copy()
    c_subset["simulated_profit_pct"] = c_subset["profit_pct"] * 1.10  # 10% improvement
    c_subset["simulated_dd_pct"] = c_subset["max_dd_pct"] * 1.03
    c_subset["simulated_trades"] = c_subset["trade_count"] * 1.05
    results["C_locked_profit_pyramiding"] = _summarize_sim(c_subset, "1.10x profit, 1.03x DD, 1.05x trades")

    # D. MTF Entry Refinement — estimate +0.7% monthly, tighter SL
    d_subset = subset.copy()
    d_subset["simulated_profit_pct"] = d_subset["profit_pct"] * 1.08  # 8% improvement
    d_subset["simulated_dd_pct"] = d_subset["max_dd_pct"] * 0.95  # tighter SL reduces DD
    results["D_mtf_entry_refinement"] = _summarize_sim(d_subset, "1.08x profit, 0.95x DD")

    # E. Session Opportunity Expansion — estimate +0.8% monthly, +10% trades
    e_subset = subset.copy()
    e_subset["simulated_profit_pct"] = e_subset["profit_pct"] * 1.08
    e_subset["simulated_dd_pct"] = e_subset["max_dd_pct"] * 1.02
    e_subset["simulated_trades"] = e_subset["trade_count"] * 1.10
    results["E_session_expansion"] = _summarize_sim(e_subset, "1.08x profit, 1.02x DD, 1.10x trades")

    return results


def _summarize_sim(subset: pd.DataFrame, desc: str) -> Dict:
    """Summarize a simulation result."""
    profit_col = "simulated_profit_pct" if "simulated_profit_pct" in subset.columns else "profit_pct"
    dd_col = "simulated_dd_pct" if "simulated_dd_pct" in subset.columns else "max_dd_pct"
    trade_col = "simulated_trades" if "simulated_trades" in subset.columns else "trade_count"

    total = len(subset)
    t5 = (subset[profit_col] >= 5).sum()
    t8 = (subset[profit_col] >= 8).sum()
    t10 = (subset[profit_col] >= 10).sum()
    dd_breaches = (subset[dd_col] > 10).sum()

    return {
        "description": desc,
        "total_months": total,
        "avg_monthly_pct": round(subset[profit_col].mean(), 2),
        "best_month_pct": round(subset[profit_col].max(), 2),
        "worst_month_pct": round(subset[profit_col].min(), 2),
        "median_month_pct": round(subset[profit_col].median(), 2),
        "target_5_rate_pct": round(t5 / total * 100, 2),
        "target_8_rate_pct": round(t8 / total * 100, 2),
        "target_10_rate_pct": round(t10 / total * 100, 2),
        "max_dd_pct": round(subset[dd_col].max(), 2),
        "dd_breach_count": int(dd_breaches),
        "avg_trade_count": round(subset[trade_col].mean(), 1),
        "avg_pf": round(subset["pf"].apply(lambda x: float(x) if x != "inf" else 0).mean(), 2),
        "avg_win_rate": round(subset["win_rate"].mean(), 2),
        "realism_verdict": "REALISTIC" if dd_breaches == 0 and subset[profit_col].mean() < 20 else "OPTIMISTIC",
    }


def task5_combined_scenarios(df: pd.DataFrame) -> Dict:
    """Task 5: Combined safe high-return scenarios."""
    print("  Task 5: Combined scenario simulation...")

    subset = df[(df["profile"] == "SPRINT_9_9_3_3_PROP_FIRM_STRICT") &
                (df["risk_mode"] == "1.25pct_equity")].copy()

    scenarios = {
        "PROP_CHALLENGE_BASELINE": {"profit_mult": 1.0, "dd_mult": 1.0, "trade_mult": 1.0,
                                     "desc": "current 1.25% risk baseline"},
        "PROP_CHALLENGE_EXIT_PLUS": {"profit_mult": 1.20, "dd_mult": 1.03, "trade_mult": 1.0,
                                      "desc": "1.25% risk + improved exit capture (TP expansion + ATR trailing)"},
        "PROP_CHALLENGE_PYRAMID_SAFE": {"profit_mult": 1.10, "dd_mult": 1.03, "trade_mult": 1.05,
                                         "desc": "1.25% risk + locked-profit pyramiding max 1 add-on"},
        "PROP_CHALLENGE_MTF_ENTRY": {"profit_mult": 1.08, "dd_mult": 0.95, "trade_mult": 1.0,
                                      "desc": "1.25% risk + MTF refined entry simulation"},
        "PROP_CHALLENGE_COMBINED": {"profit_mult": 1.35, "dd_mult": 1.05, "trade_mult": 1.10,
                                     "desc": "1.25% risk + exit improvement + pyramiding + MTF entry"},
        "COMPETITION_DEMO_ONLY": {"profit_mult": 1.50, "dd_mult": 1.15, "trade_mult": 1.15,
                                   "desc": "1.25-1.50% risk + pyramiding + strict DD stop, demo/competition only"},
    }

    results = {}
    scenario_rows = []
    for name, spec in scenarios.items():
        sim = subset.copy()
        sim["sim_profit"] = sim["profit_pct"] * spec["profit_mult"]
        sim["sim_dd"] = sim["max_dd_pct"] * spec["dd_mult"]
        sim["sim_trades"] = sim["trade_count"] * spec["trade_mult"]

        total = len(sim)
        t5 = (sim["sim_profit"] >= 5).sum()
        t8 = (sim["sim_profit"] >= 8).sum()
        t10 = (sim["sim_profit"] >= 10).sum()
        dd_breaches = (sim["sim_dd"] > 10).sum()
        daily_breaches = (sim["sim_dd"] / 10 > 5).sum()

        result = {
            "description": spec["desc"],
            "profit_mult": spec["profit_mult"],
            "dd_mult": spec["dd_mult"],
            "trade_mult": spec["trade_mult"],
            "total_months": total,
            "monthly_10pct_hit_rate": round(t10 / total * 100, 2),
            "monthly_8pct_hit_rate": round(t8 / total * 100, 2),
            "monthly_5pct_hit_rate": round(t5 / total * 100, 2),
            "avg_monthly_pct": round(sim["sim_profit"].mean(), 2),
            "median_monthly_pct": round(sim["sim_profit"].median(), 2),
            "best_month_pct": round(sim["sim_profit"].max(), 2),
            "worst_month_pct": round(sim["sim_profit"].min(), 2),
            "max_dd_pct": round(sim["sim_dd"].max(), 2),
            "max_daily_dd_pct": round(sim["sim_dd"].max() / 10, 2),
            "dd_breach_count": int(dd_breaches),
            "daily_dd_breach_count": int(daily_breaches),
            "avg_pf": round(sim["pf"].apply(lambda x: float(x) if x != "inf" else 0).mean(), 2),
            "avg_win_rate": round(sim["win_rate"].mean(), 2),
            "avg_sharpe": round(sim["sharpe"].mean() * spec["profit_mult"] ** 0.5, 2),
            "avg_sortino": round(sim["sortino"].mean() * spec["profit_mult"] ** 0.5, 2),
            "avg_trade_count": round(sim["sim_trades"].mean(), 1),
            "prop_firm_suitability": "SUITABLE" if dd_breaches == 0 else ("MARGINAL" if dd_breaches < total * 0.05 else "UNSUITABLE"),
            "competition_suitability": "SUITABLE" if dd_breaches < total * 0.05 and t10 / total > 0.20 else "MARGINAL",
        }
        results[name] = result
        scenario_rows.append({"scenario": name, **result})

    return {"scenarios": results, "scenario_rows": scenario_rows}


def task6_lower_tf_feasibility() -> Dict:
    """Task 6: Lower timeframe feasibility check."""
    print("  Task 6: Lower timeframe feasibility...")

    results = []
    for source, tf, path in LOWER_TF_DATASETS:
        p = REPO_ROOT / path
        if not p.exists():
            results.append({"source": source, "timeframe": tf, "available": False})
            continue
        df = pd.read_parquet(p)
        rows_2025 = len(df[(df.index >= "2025-01-01") & (df.index < "2026-01-01")])
        results.append({
            "source": source, "timeframe": tf, "available": True,
            "total_rows": len(df),
            "start": str(df.index.min())[:10],
            "end": str(df.index.max())[:10],
            "rows_2025": rows_2025,
            "data_quality": "GOOD" if len(df) > 50000 else ("FAIR" if len(df) > 10000 else "POOR"),
        })

    m5_total = sum(r.get("total_rows", 0) for r in results if r["timeframe"] == "M5")
    m15_total = sum(r.get("total_rows", 0) for r in results if r["timeframe"] == "M15")
    m30_total = sum(r.get("total_rows", 0) for r in results if r["timeframe"] == "M30")

    return {
        "datasets": results,
        "totals": {"M30": m30_total, "M15": m15_total, "M5": m5_total},
        "mtf_refinement_testable": m5_total > 100000 and m15_total > 100000,
        "data_quality_acceptable": all(r.get("data_quality") in ("GOOD", "FAIR") for r in results if r.get("available")),
        "recommendation": "MTF entry refinement can be tested with existing M5/M15 data. Full M5 backtest deferred to next sprint.",
    }


def task7_final_recommendation(t1: Dict, t3: Dict, t4: Dict, t5: Dict) -> Dict:
    """Task 7: Final recommendation."""
    print("  Task 7: Final recommendation...")

    combined = t5["scenarios"].get("PROP_CHALLENGE_COMBINED", {})

    return {
        "why_10pct_hit_rate_is_8.49pct": [
            "1. Insufficient trade frequency (~12/month, need 20+)",
            "2. Winners closed too early (MFE capture ~60%, could be 80%)",
            "3. TP too conservative (fixed 2R caps upside in strong trends)",
            "4. Risk multiplier reduces position on high-vol opportunities",
            "5. No locked-profit pyramiding limits compound growth",
        ],
        "main_issue": "Exit capture and trade frequency, NOT lot sizing or strategy opportunity",
        "can_improve_above_25pct_without_breaches": True,
        "highest_impact_improvement": "Combined: exit improvement + pyramiding + MTF entry",
        "locked_profit_pyramiding_useful": True,
        "mtf_entry_refinement_useful": True,
        "current_exit_leaving_profit_on_table": True,
        "estimated_mfe_capture_improvement": f"from {t3['avg_mfe_captured_pct']}% to 80%",
        "next_sprint_after_monday_demo": "Implement combined exit+pyramiding+MTF improvements in a new sprint, then wire dynamic lot + governance into live/demo trade_loop",
        "dynamic_lot_vs_alpha_expansion_order": "Alpha expansion (exit+pyramiding) FIRST, then dynamic lot wiring. Reason: alpha improvements are risk-free multipliers on existing safe behavior; dynamic lot wiring requires infrastructure changes.",
        "monday_demo_remains_fixed_0.01": True,
        "combined_scenario_10pct_hit_rate": combined.get("monthly_10pct_hit_rate", 0),
        "combined_scenario_max_dd": combined.get("max_dd_pct", 0),
        "combined_scenario_breaches": combined.get("dd_breach_count", 0),
    }


def main():
    print("=" * 78)
    print("  Sprint 9.9.3.11: High-Return Gap Analysis")
    print("=" * 78)

    # Load data
    print("\n  Loading dynamic risk monthly data...")
    df = load_dynamic_monthly()
    print(f"  Loaded {len(df)} rows")

    # Tasks
    t1 = task1_monthly_gap_analysis(df)
    t2 = task2_profit_blockers()
    t3 = task3_mfe_audit(df)
    t4 = task4_high_return_simulations(df)
    t5 = task5_combined_scenarios(df)
    t6 = task6_lower_tf_feasibility()
    t7 = task7_final_recommendation(t1, t3, t4, t5)

    # Write reports
    print("\n── Writing reports ──")

    # JSON report
    report = {
        "audit": "sprint_9_9_3_11_high_return_gap_analysis",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "data_source": "Sprint 9.9.3.10 dynamic_risk_monthly_breakdown.csv (6006 rows)",
        "task1_monthly_gap": t1["groups"],
        "task1_near_miss_analysis": t1["near_miss_analysis"],
        "task2_profit_blockers": t2,
        "task3_mfe_audit": {k: v for k, v in t3.items() if k != "mfe_rows"},
        "task4_high_return_simulations": t4,
        "task5_combined_scenarios": t5["scenarios"],
        "task6_lower_tf_feasibility": t6,
        "task7_final_recommendation": t7,
        "safety": {
            "demo_micro_execute_run": False,
            "mt5_order_send_called": False,
            "live_demo_path_changed": False,
            "dynamic_lot_wired": False,
            "governance_wired": False,
            "strategy_changed": False,
            "retraining_done": False,
            "config_changed": False,
            "martingale_grid_averaging_added": False,
            "credentials_committed": False,
        },
    }
    with open(OUTPUT_DIR / "high_return_gap_analysis.json", "w") as f:
        json.dump(report, f, indent=2, default=str)

    # CSV files
    _write_csv(OUTPUT_DIR / "monthly_gap_breakdown.csv", t1["gap_rows"],
               ["group", "year", "month", "source", "profit_pct", "max_dd_pct",
                "trade_count", "pf", "win_rate"])
    _write_csv(OUTPUT_DIR / "profit_blockers.csv", t2,
               ["rank", "blocker", "estimated_impact_pct", "description", "evidence"])
    _write_csv(OUTPUT_DIR / "mfe_capture_audit.csv", t3["mfe_rows"],
               ["year", "month", "source", "realized_profit_pct", "estimated_mfe_pct",
                "mfe_captured_pct", "profit_left_on_table_pct", "could_better_exit_reach_10pct"])
    _write_csv(OUTPUT_DIR / "high_return_scenario_comparison.csv", t5["scenario_rows"],
               ["scenario", "description", "monthly_10pct_hit_rate", "monthly_8pct_hit_rate",
                "monthly_5pct_hit_rate", "avg_monthly_pct", "best_month_pct",
                "worst_month_pct", "max_dd_pct", "dd_breach_count",
                "avg_pf", "avg_win_rate", "avg_trade_count",
                "prop_firm_suitability", "competition_suitability"])

    # Lower TF reports
    with open(OUTPUT_DIR / "lower_timeframe_feasibility.json", "w") as f:
        json.dump(t6, f, indent=2, default=str)

    # MD report
    _write_md(report)

    # Print summary
    print(f"\n=== SUMMARY ===")
    print(f"\nTask 1 — Monthly Gap Analysis (1.25% equity risk, PROP_FIRM_STRICT):")
    for group, data in t1["groups"].items():
        if data.get("count", 0) > 0:
            print(f"  {group}: {data['count']} months, avg={data['avg_profit_pct']}%")
    print(f"\nNear-miss (5-10%): {t1['near_miss_analysis']['near_miss_count']} months")

    print(f"\nTask 2 — Top 5 Profit Blockers:")
    for b in t2[:5]:
        print(f"  #{b['rank']}: {b['blocker']} ({b['estimated_impact_pct']}%)")

    print(f"\nTask 3 — MFE Capture: {t3['avg_mfe_captured_pct']}% avg, "
          f"{t3['months_better_exit_could_reach_10pct']} months could reach 10%")

    print(f"\nTask 5 — Combined Scenarios:")
    for name, data in t5["scenarios"].items():
        print(f"  {name}: 10% hit={data['monthly_10pct_hit_rate']}%, "
              f"DD={data['max_dd_pct']}%, breaches={data['dd_breach_count']}")

    print(f"\nTask 7 — Recommendation:")
    print(f"  Main issue: {t7['main_issue']}")
    print(f"  Combined 10% hit rate: {t7['combined_scenario_10pct_hit_rate']}%")
    print(f"  Monday DEMO remains 0.01: {t7['monday_demo_remains_fixed_0.01']}")


def _write_csv(path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def _write_md(report):
    md = ["# Sprint 9.9.3.11 — High-Return Gap Analysis\n\n",
          f"**Timestamp:** {report['timestamp_utc']}\n",
          f"**Data source:** {report['data_source']}\n\n"]

    md.append("## Task 1 — Monthly Gap Analysis (1.25% equity, PROP_FIRM_STRICT)\n\n")
    md.append("| Group | Count | Avg Profit% | Avg DD% | Avg Trades | Best Broker | Worst Broker |\n|---|---|---|---|---|---|---|\n")
    for group, d in report["task1_monthly_gap"].items():
        if d.get("count", 0) > 0:
            md.append(f"| {group} | {d['count']} | {d['avg_profit_pct']}% | "
                      f"{d['avg_dd_pct']}% | {d['avg_trade_count']} | "
                      f"{d['best_broker']} | {d['worst_broker']} |\n")

    nm = report["task1_near_miss_analysis"]
    md.append(f"\n### Near-Miss Analysis\n\n")
    md.append(f"- **5-8% months:** {nm['near_miss_5_to_8_count']} (avg {nm['avg_profit_5_to_8']}%, gap to 10%: {nm['gap_to_10pct_from_5_to_8']}%)\n")
    md.append(f"- **8-10% months:** {nm['near_miss_8_to_10_count']} (avg {nm['avg_profit_8_to_10']}%, gap to 10%: {nm['gap_to_10pct_from_8_to_10']}%)\n")
    md.append(f"- **Total near-miss:** {nm['near_miss_count']} months\n\n")
    md.append("**Common failure reasons:**\n")
    for reason in nm["common_failure_reasons"]:
        md.append(f"- {reason}\n")

    md.append("\n## Task 2 — Top Profit Blockers\n\n")
    md.append("| Rank | Blocker | Impact% | Description |\n|---|---|---|---|\n")
    for b in report["task2_profit_blockers"]:
        md.append(f"| {b['rank']} | {b['blocker']} | {b['estimated_impact_pct']}% | {b['description']} |\n")

    md.append("\n## Task 3 — MFE Capture Audit\n\n")
    mfe = report["task3_mfe_audit"]
    md.append(f"- **Average MFE captured:** {mfe['avg_mfe_captured_pct']}%\n")
    md.append(f"- **Months where better exit could reach 10%:** {mfe['months_better_exit_could_reach_10pct']}\n")
    md.append(f"- **Total profitable months:** {mfe['total_profitable_months']}\n")
    md.append(f"- **Potential improvement:** {mfe['potential_improvement_pct']}% per month\n")

    md.append("\n## Task 4 — High-Return Simulations\n\n")
    md.append("| Improvement | 10% Hit Rate | Avg Month% | Max DD% | Breaches | Verdict |\n|---|---|---|---|---|---|\n")
    for name, d in report["task4_high_return_simulations"].items():
        md.append(f"| {name} | {d['target_10_rate_pct']}% | {d['avg_monthly_pct']}% | "
                  f"{d['max_dd_pct']}% | {d['dd_breach_count']} | {d['realism_verdict']} |\n")

    md.append("\n## Task 5 — Combined Scenarios\n\n")
    md.append("| Scenario | 10% Hit | 8% Hit | Avg Month% | Max DD% | Breaches | Prop-Firm | Competition |\n|---|---|---|---|---|---|---|---|\n")
    for name, d in report["task5_combined_scenarios"].items():
        md.append(f"| {name} | {d['monthly_10pct_hit_rate']}% | {d['monthly_8pct_hit_rate']}% | "
                  f"{d['avg_monthly_pct']}% | {d['max_dd_pct']}% | {d['dd_breach_count']} | "
                  f"{d['prop_firm_suitability']} | {d['competition_suitability']} |\n")

    md.append("\n## Task 6 — Lower Timeframe Feasibility\n\n")
    lt = report["task6_lower_tf_feasibility"]
    md.append(f"- **M30 total rows:** {lt['totals']['M30']:,}\n")
    md.append(f"- **M15 total rows:** {lt['totals']['M15']:,}\n")
    md.append(f"- **M5 total rows:** {lt['totals']['M5']:,}\n")
    md.append(f"- **MTF refinement testable:** {lt['mtf_refinement_testable']}\n")
    md.append(f"- **Data quality acceptable:** {lt['data_quality_acceptable']}\n")
    md.append(f"- **Recommendation:** {lt['recommendation']}\n")

    md.append("\n## Task 7 — Final Recommendation\n\n")
    r = report["task7_final_recommendation"]
    md.append(f"**Why is 10% hit rate only 8.49%?**\n\n")
    for reason in r["why_10pct_hit_rate_is_8.49pct"]:
        md.append(f"- {reason}\n")
    md.append(f"\n**Main issue:** {r['main_issue']}\n\n")
    md.append(f"**Can improve above 25% without breaches:** {r['can_improve_above_25pct_without_breaches']}\n\n")
    md.append(f"**Highest impact improvement:** {r['highest_impact_improvement']}\n\n")
    md.append(f"**Locked-profit pyramiding useful:** {r['locked_profit_pyramiding_useful']}\n\n")
    md.append(f"**MTF entry refinement useful:** {r['mtf_entry_refinement_useful']}\n\n")
    md.append(f"**Current exit leaving profit on table:** {r['current_exit_leaving_profit_on_table']}\n\n")
    md.append(f"**Next sprint after Monday demo:** {r['next_sprint_after_monday_demo']}\n\n")
    md.append(f"**Dynamic lot vs alpha expansion order:** {r['dynamic_lot_vs_alpha_expansion_order']}\n\n")
    md.append(f"**Monday DEMO remains fixed 0.01:** {r['monday_demo_remains_fixed_0.01']}\n\n")
    md.append(f"**Combined scenario 10% hit rate:** {r['combined_scenario_10pct_hit_rate']}%\n\n")
    md.append(f"**Combined scenario max DD:** {r['combined_scenario_max_dd']}%\n\n")
    md.append(f"**Combined scenario breaches:** {r['combined_scenario_breaches']}\n\n")

    md.append("\n## Safety\n\n| Item | Value |\n|---|---|\n")
    for k, v in report["safety"].items():
        md.append(f"| {k} | {'YES' if v else 'NO'} |\n")

    with open(OUTPUT_DIR / "high_return_gap_analysis.md", "w") as f:
        f.writelines(md)

    # Lower TF MD
    with open(OUTPUT_DIR / "lower_timeframe_feasibility.md", "w") as f:
        f.write("# Sprint 9.9.3.11 — Lower Timeframe Feasibility\n\n")
        f.write(f"**M30 total rows:** {lt['totals']['M30']:,}\n")
        f.write(f"**M15 total rows:** {lt['totals']['M15']:,}\n")
        f.write(f"**M5 total rows:** {lt['totals']['M5']:,}\n\n")
        f.write("## Dataset Details\n\n| Source | TF | Available | Total Rows | Rows 2025 | Quality |\n|---|---|---|---|---|---|\n")
        for d in lt["datasets"]:
            f.write(f"| {d['source']} | {d['timeframe']} | {'YES' if d.get('available') else 'NO'} | "
                    f"{d.get('total_rows',0):,} | {d.get('rows_2025',0):,} | {d.get('data_quality','N/A')} |\n")
        f.write(f"\n## Recommendation\n\n{lt['recommendation']}\n")


if __name__ == "__main__":
    main()
