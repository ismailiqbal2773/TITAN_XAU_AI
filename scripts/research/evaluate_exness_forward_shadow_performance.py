#!/usr/bin/env python3
"""TITAN XAU AI — Evaluate Exness Forward Shadow Performance (Module 3)
========================================================================
Standalone performance evaluator for forward shadow signals.
This is the research/ version that complements scripts/audit/validate_exness_forward_shadow.py

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, json, csv, os
from pathlib import Path
from datetime import datetime, timezone
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "exness_forward_shadow"


def main():
    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  EXNESS FORWARD SHADOW PERFORMANCE EVALUATOR")
    print("=" * 70)
    print(f"  Timestamp: {ts}\n")

    signals_path = OUTPUT_DIR / "forward_shadow_signals_exness.csv"
    metrics = {
        "timestamp_utc": ts,
        "total_cycles": 0, "valid_signals": 0, "rejected_signals": 0,
        "signal_rate": 0, "avg_alpha": 0, "avg_meta": 0,
        "avg_lot": 0, "max_lot": 0, "avg_margin_usage": 0, "max_margin_usage": 0,
        "risk_violations": 0, "margin_violations": 0, "spread_violations": 0,
        "ceo_blocks": 0, "meta_blocks": 0, "prop_risk_blocks": 0,
        "stale_data_count": 0,
    }

    if signals_path.exists():
        with open(signals_path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        metrics["total_cycles"] = len(rows)
        signals = [r for r in rows if r.get("final_decision") == "SHADOW_SIGNAL"]
        rejects = [r for r in rows if r.get("final_decision", "").startswith("REJECT")]
        metrics["valid_signals"] = len(signals)
        metrics["rejected_signals"] = len(rejects)
        metrics["signal_rate"] = round(len(signals) / max(len(rows), 1), 4)

        if signals:
            alphas = [float(r.get("alpha_confidence", 0)) for r in signals if r.get("alpha_confidence")]
            metas = [float(r.get("meta_confidence", 0)) for r in signals if r.get("meta_confidence")]
            lots = [float(r.get("calculated_lot", 0)) for r in signals if r.get("calculated_lot")]
            margins = [float(r.get("margin_usage", 0)) for r in signals if r.get("margin_usage")]
            metrics["avg_alpha"] = round(float(np.mean(alphas)) if alphas else 0, 4)
            metrics["avg_meta"] = round(float(np.mean(metas)) if metas else 0, 4)
            metrics["avg_lot"] = round(float(np.mean(lots)) if lots else 0, 4)
            metrics["max_lot"] = round(float(np.max(lots)) if lots else 0, 4)
            metrics["avg_margin_usage"] = round(float(np.mean(margins)) if margins else 0, 6)
            metrics["max_margin_usage"] = round(float(np.max(margins)) if margins else 0, 6)

        for r in rejects:
            reason = r.get("final_decision", "")
            if "CEO" in reason: metrics["ceo_blocks"] += 1
            if "META" in reason: metrics["meta_blocks"] += 1
            if "SPREAD" in reason: metrics["spread_violations"] += 1
            if "MARGIN" in reason: metrics["margin_violations"] += 1
            if "PROP" in reason: metrics["prop_risk_blocks"] += 1

    # Verdict
    if metrics["total_cycles"] == 0:
        verdict = "NEEDS_MORE_FORWARD_SHADOW_DATA"
    elif metrics["valid_signals"] == 0:
        verdict = "NEEDS_MORE_FORWARD_SHADOW_DATA"
    elif metrics["max_margin_usage"] > 0.20:
        verdict = "FORWARD_SHADOW_PERFORMANCE_FAIL"
    elif metrics["valid_signals"] > 0 and metrics["max_margin_usage"] <= 0.20:
        verdict = "FORWARD_SHADOW_PERFORMANCE_PASS"
    else:
        verdict = "FORWARD_SHADOW_PERFORMANCE_WARN"

    metrics["verdict"] = verdict

    with open(OUTPUT_DIR / "forward_shadow_performance.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    with open(OUTPUT_DIR / "forward_shadow_performance.md", "w", encoding="utf-8") as f:
        f.write("# Forward Shadow Performance (Module 3)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n## Verdict: {verdict}\n\n")
        for k, v in metrics.items():
            if k not in ["timestamp_utc", "verdict"]:
                f.write(f"- {k}: {v}\n")
    with open(OUTPUT_DIR / "forward_shadow_signal_quality.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for k, v in metrics.items():
            if k not in ["timestamp_utc", "verdict"]:
                w.writerow([k, v])

    print(f"  Verdict: {verdict}")
    print(f"  Total cycles: {metrics['total_cycles']}")
    print(f"  Valid signals: {metrics['valid_signals']}")
    print(f"  Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
