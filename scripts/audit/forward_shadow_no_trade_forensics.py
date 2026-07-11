#!/usr/bin/env python3
"""TITAN XAU AI — No-Trade Forensics Audit (Sprint v2.8.7-P)
=============================================================
Forensic analysis of why forward shadow produced 0 signals.
NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, json, csv, os
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter, defaultdict
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "no_trade_forensics"
INPUT_DIR = REPO_ROOT / "data" / "reports" / "exness_forward_shadow"


def main():
    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  NO-TRADE FORENSICS AUDIT (Sprint v2.8.7-P)")
    print("=" * 70)
    print(f"  Timestamp: {ts}\n")

    # Read journal
    journal_path = INPUT_DIR / "forward_shadow_journal_exness.jsonl"
    entries = []
    if journal_path.exists():
        for line in journal_path.read_text(encoding="utf-8").strip().split("\n"):
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    # Read CSV
    csv_path = INPUT_DIR / "forward_shadow_signals_exness.csv"
    csv_rows = []
    if csv_path.exists():
        with open(csv_path, encoding="utf-8") as f:
            csv_rows = list(csv.DictReader(f))

    # Read summary
    summary_path = INPUT_DIR / "forward_shadow_summary_exness.json"
    summary = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

    # Analysis
    total_cycles = len(entries)
    rejection_breakdown = Counter()
    timestamps_seen = []
    alphas = []
    metas = []

    for e in entries:
        decision = e.get("final_decision", "UNKNOWN")
        rejection_breakdown[decision] += 1
        ts_val = e.get("timestamp", "")
        timestamps_seen.append(ts_val)
        if "alpha_confidence" in e:
            try:
                alphas.append(float(e["alpha_confidence"]))
            except (ValueError, TypeError):
                pass
        if "meta_confidence" in e:
            try:
                metas.append(float(e["meta_confidence"]))
            except (ValueError, TypeError):
                pass

    # Unique candles
    unique_candles = len(set(timestamps_seen))
    repeated_candle_count = total_cycles - unique_candles

    # Nearest missed signal (highest alpha that was rejected)
    nearest_missed_alpha = max(alphas) if alphas else 0
    nearest_missed_meta = max(metas) if metas else 0

    # Determine root cause
    alpha_rejects = rejection_breakdown.get("REJECT_ALPHA", 0)
    meta_rejects = rejection_breakdown.get("REJECT_META", 0)
    ceo_rejects = rejection_breakdown.get("REJECT_CEO", 0)
    spread_rejects = rejection_breakdown.get("REJECT_SPREAD", 0)
    margin_rejects = rejection_breakdown.get("REJECT_MARGIN", 0)
    market_data_rejects = rejection_breakdown.get("REJECT_MARKET_DATA", 0) + rejection_breakdown.get("SAFETY_BLOCK", 0)

    if total_cycles == 0:
        root_cause = "NO_TRADE_CAUSE_MARKET_DATA"
    elif market_data_rejects == total_cycles:
        root_cause = "NO_TRADE_CAUSE_MARKET_DATA"
    elif alpha_rejects > 0 and alpha_rejects >= max(meta_rejects, ceo_rejects, spread_rejects):
        root_cause = "NO_TRADE_CAUSE_ALPHA"
    elif meta_rejects > 0 and meta_rejects >= max(alpha_rejects, ceo_rejects, spread_rejects):
        root_cause = "NO_TRADE_CAUSE_META"
    elif ceo_rejects > 0 and ceo_rejects >= max(alpha_rejects, meta_rejects, spread_rejects):
        root_cause = "NO_TRADE_CAUSE_CEO"
    elif spread_rejects > 0:
        root_cause = "NO_TRADE_CAUSE_SPREAD"
    elif repeated_candle_count > total_cycles * 0.5:
        root_cause = "NO_TRADE_CAUSE_H1_ONLY"
    else:
        root_cause = "NO_TRADE_CAUSE_UNKNOWN"

    # H1-only issue: if repeated candle count is high, runner is checking same candle
    h1_only_issue = repeated_candle_count > total_cycles * 0.3 if total_cycles > 0 else False

    # Threshold sensitivity
    threshold_rows = []
    for alpha_t in [0.48, 0.50, 0.52, 0.55]:
        for meta_t in [0.48, 0.50, 0.52, 0.55]:
            would_pass = sum(1 for a, m in zip(alphas, metas) if a >= alpha_t and m >= meta_t)
            threshold_rows.append({
                "alpha_threshold": alpha_t,
                "meta_threshold": meta_t,
                "would_pass_count": would_pass,
                "would_pass_pct": round(would_pass / max(total_cycles, 1) * 100, 2),
            })

    # Write outputs
    result = {
        "timestamp_utc": ts,
        "total_cycles": total_cycles,
        "unique_candles": unique_candles,
        "repeated_candle_count": repeated_candle_count,
        "alpha_reject_count": alpha_rejects,
        "meta_reject_count": meta_rejects,
        "ceo_reject_count": ceo_rejects,
        "spread_reject_count": spread_rejects,
        "margin_reject_count": margin_rejects,
        "market_data_reject_count": market_data_rejects,
        "average_alpha": round(float(np.mean(alphas)), 6) if alphas else 0,
        "average_meta": round(float(np.mean(metas)), 6) if metas else 0,
        "max_alpha": round(float(max(alphas)), 6) if alphas else 0,
        "max_meta": round(float(max(metas)), 6) if metas else 0,
        "nearest_missed_alpha": round(nearest_missed_alpha, 6),
        "nearest_missed_meta": round(nearest_missed_meta, 6),
        "root_cause": root_cause,
        "h1_only_issue": h1_only_issue,
        "rejection_breakdown": dict(rejection_breakdown),
    }

    with open(OUTPUT_DIR / "no_trade_forensics.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    with open(OUTPUT_DIR / "no_trade_forensics.md", "w", encoding="utf-8") as f:
        f.write("# No-Trade Forensics Audit (Sprint v2.8.7-P)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"## Root Cause: {root_cause}\n\n")
        f.write("## Summary\n\n")
        f.write(f"- Total cycles: {total_cycles}\n")
        f.write(f"- Unique candles: {unique_candles}\n")
        f.write(f"- Repeated candle count: {repeated_candle_count}\n")
        f.write(f"- H1-only issue (repeated candles): {h1_only_issue}\n\n")
        f.write("## Rejection Breakdown\n\n")
        f.write("| Decision | Count |\n|---|---|\n")
        for k, v in sorted(rejection_breakdown.items(), key=lambda x: -x[1]):
            f.write(f"| {k} | {v} |\n")
        f.write(f"\n## Alpha/Meta Distribution\n\n")
        f.write(f"- Average alpha: {result['average_alpha']}\n")
        f.write(f"- Max alpha: {result['max_alpha']}\n")
        f.write(f"- Average meta: {result['average_meta']}\n")
        f.write(f"- Max meta: {result['max_meta']}\n")
        f.write(f"- Nearest missed alpha: {result['nearest_missed_alpha']}\n")
        f.write(f"- Nearest missed meta: {result['nearest_missed_meta']}\n\n")
        f.write("## Threshold Sensitivity\n\n")
        f.write("| Alpha | Meta | Would Pass | Pct |\n|---|---|---|---|\n")
        for r in threshold_rows:
            f.write(f"| {r['alpha_threshold']} | {r['meta_threshold']} | "
                    f"{r['would_pass_count']} | {r['would_pass_pct']}% |\n")

    with open(OUTPUT_DIR / "rejection_breakdown.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["decision", "count"])
        for k, v in sorted(rejection_breakdown.items(), key=lambda x: -x[1]):
            w.writerow([k, v])

    with open(OUTPUT_DIR / "threshold_sensitivity.csv", "w", newline="", encoding="utf-8") as f:
        if threshold_rows:
            w = csv.DictWriter(f, fieldnames=list(threshold_rows[0].keys()))
            w.writeheader()
            for r in threshold_rows:
                w.writerow(r)

    print(f"  Root cause: {root_cause}")
    print(f"  Total cycles: {total_cycles}")
    print(f"  Repeated candles: {repeated_candle_count}")
    print(f"  H1-only issue: {h1_only_issue}")
    print(f"  Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
