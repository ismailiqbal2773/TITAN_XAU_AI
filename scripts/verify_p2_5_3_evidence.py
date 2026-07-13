#!/usr/bin/env python3
"""TITAN XAU AI — v2.8.7-P2.5.3 Evidence Verifier
===================================================

Independently verifies every report value against committed artifacts.
Fails on any mismatch.

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, json, hashlib, pickle, csv
from pathlib import Path
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

REPORTS_DIR = REPO_ROOT / "data/reports/competition_candidate"
ARTIFACTS_DIR = REPO_ROOT / "data/artifacts/p2_5_1"
REGISTRY_PATH = REPO_ROOT / "data/artifacts/p2_5_3/baseline_registry.json"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def verify():
    errors = []
    warnings = []

    # 1. Load baseline registry
    with open(REGISTRY_PATH) as f:
        registry = json.load(f)

    # 2. Verify fold artifacts
    for fold in registry["folds"]:
        fold_dir = REPO_ROOT / fold["artifact_directory"]
        # Recompute alpha hash
        actual_alpha = sha256_file(fold_dir / "alpha_model.pkl")
        if actual_alpha != fold["alpha_model_hash"]:
            errors.append(f"Fold {fold['fold']}: alpha hash mismatch")
        # Recompute meta hash
        actual_meta = sha256_file(fold_dir / "meta_model.pkl")
        if actual_meta != fold["meta_model_hash"]:
            errors.append(f"Fold {fold['fold']}: meta hash mismatch")

    # 3. Verify fold boundaries are chronological and non-overlapping
    folds = sorted(registry["folds"], key=lambda f: f["fold"])
    for i in range(len(folds) - 1):
        if folds[i]["oos_end"] >= folds[i + 1]["oos_start"]:
            errors.append(f"Fold {folds[i]['fold']} OOS end ({folds[i]['oos_end']}) >= Fold {folds[i+1]['fold']} OOS start ({folds[i+1]['oos_start']})")

    # 4. Verify all OOS before 2026
    for f in folds:
        if f["oos_end"] >= "2026-01-01":
            errors.append(f"Fold {f['fold']} OOS end ({f['oos_end']}) >= 2026-01-01")

    # 5. Recompute metrics from trade ledger
    ledger_path = REPORTS_DIR / "trade_ledger.csv"
    if ledger_path.exists():
        df = pd.read_csv(ledger_path)
        dev_trades = df[df["segment"] == "dev_wfo"]

        # Recompute trades
        actual_trades = len(dev_trades)
        actual_wins = len(dev_trades[dev_trades["pnl_net"] > 0])
        actual_win_rate = actual_wins / actual_trades if actual_trades > 0 else 0

        # Recompute PF
        pos_net = dev_trades[dev_trades["pnl_net"] > 0]["pnl_net"].sum()
        neg_net = abs(dev_trades[dev_trades["pnl_net"] <= 0]["pnl_net"].sum())
        actual_pf_net = pos_net / neg_net if neg_net > 0 else 999

        pos_gross = dev_trades[dev_trades["pnl_gross"] > 0]["pnl_gross"].sum()
        neg_gross = abs(dev_trades[dev_trades["pnl_gross"] <= 0]["pnl_gross"].sum())
        actual_pf_gross = pos_gross / neg_gross if neg_gross > 0 else 999

        # Recompute expectancy
        actual_expectancy = dev_trades["r_net"].mean() if len(dev_trades) > 0 else 0

        # Recompute long/short
        actual_long = len(dev_trades[dev_trades["direction"] == "LONG"])
        actual_short = len(dev_trades[dev_trades["direction"] == "SHORT"])

        # Recompute costs
        actual_total_cost = dev_trades["total_cost"].sum()

        # Recompute net profit
        actual_net_profit = dev_trades["pnl_net"].sum()

        # Compare with baseline_metrics.json
        baseline = json.load(open(REPORTS_DIR / "baseline_metrics.json"))
        if baseline.get("trades") != actual_trades:
            errors.append(f"trades mismatch: report={baseline.get('trades')} actual={actual_trades}")
        if abs(baseline.get("win_rate", 0) - round(actual_win_rate, 4)) > 0.001:
            errors.append(f"win_rate mismatch: report={baseline.get('win_rate')} actual={round(actual_win_rate, 4)}")
        if abs(baseline.get("pf_net", 0) - round(actual_pf_net, 4)) > 0.01:
            errors.append(f"pf_net mismatch: report={baseline.get('pf_net')} actual={round(actual_pf_net, 4)}")
        if abs(baseline.get("pf_gross", 0) - round(actual_pf_gross, 4)) > 0.01:
            errors.append(f"pf_gross mismatch: report={baseline.get('pf_gross')} actual={round(actual_pf_gross, 4)}")
        if abs(baseline.get("expectancy", 0) - round(actual_expectancy, 4)) > 0.001:
            errors.append(f"expectancy mismatch: report={baseline.get('expectancy')} actual={round(actual_expectancy, 4)}")
        if baseline.get("long_trades") != actual_long:
            errors.append(f"long_trades mismatch: report={baseline.get('long_trades')} actual={actual_long}")
        if baseline.get("short_trades") != actual_short:
            errors.append(f"short_trades mismatch: report={baseline.get('short_trades')} actual={actual_short}")

        # Verify pf_gross != pf_net when costs exist
        if actual_total_cost > 0 and abs(actual_pf_gross - actual_pf_net) < 0.001:
            errors.append("pf_gross equals pf_net despite non-zero costs")

        print(f"Trade ledger verified: {actual_trades} trades, pf_net={actual_pf_net:.4f}, pf_gross={actual_pf_gross:.4f}")
        print(f"  LONG={actual_long}, SHORT={actual_short}, win_rate={actual_win_rate:.4f}")
        print(f"  expectancy={actual_expectancy:.4f}, total_cost={actual_total_cost:.2f}")

    # 6. Verify report hash manifest
    manifest_path = REPORTS_DIR / "report_hash_manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
        for name, expected_hash in manifest.get("artifacts", {}).items():
            filepath = REPORTS_DIR / name
            if filepath.exists() and name != "report_hash_manifest.json":
                actual_hash = sha256_file(filepath)
                if actual_hash != expected_hash:
                    errors.append(f"Report hash mismatch: {name}")

    # 7. Verify training provenance matches registry
    prov_path = REPORTS_DIR / "training_provenance.json"
    if prov_path.exists():
        with open(prov_path) as f:
            prov = json.load(f)
        for fh in prov.get("fold_hashes", []):
            fold_num = fh["fold"]
            fold_dir = REPO_ROOT / f"data/artifacts/p2_5_1/fold_{fold_num:02d}"
            if fold_dir.exists():
                fold_prov = json.load(open(fold_dir / "provenance.json"))
                if fh["alpha_model_hash"] != fold_prov["alpha_model_hash"][:16]:
                    errors.append(f"Fold {fold_num}: report alpha hash != provenance alpha hash")
                if fh["oos_end_date"] != fold_prov["oos_end"]:
                    errors.append(f"Fold {fold_num}: report OOS end ({fh['oos_end_date']}) != provenance OOS end ({fold_prov['oos_end']})")

    # 8. Verify continuous equity
    if ledger_path.exists():
        df = pd.read_csv(ledger_path)
        dev_trades = df[df["segment"] == "dev_wfo"].sort_values("timestamp_entry")
        mismatches = 0
        for i in range(len(dev_trades) - 1):
            eq_after = dev_trades.iloc[i]["equity_after"]
            eq_before_next = dev_trades.iloc[i + 1]["equity_before"]
            if abs(eq_after - eq_before_next) > 0.50:
                mismatches += 1
                if mismatches <= 3:
                    errors.append(f"Equity discontinuity at trade {i}: after={eq_after} before_next={eq_before_next}")
        print(f"Continuous equity transitions checked: {len(dev_trades) - 1}, mismatches: {mismatches}")

    # Summary
    print(f"\n=== VERIFICATION SUMMARY ===")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    for e in errors:
        print(f"  ERROR: {e}")

    # Write verification result
    result = {
        "verified_at_utc": pd.Timestamp.utcnow().isoformat(),
        "errors": errors,
        "warnings": warnings,
        "pass": len(errors) == 0,
    }
    with open(REPORTS_DIR / "evidence_verification.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    return len(errors) == 0


if __name__ == "__main__":
    ok = verify()
    sys.exit(0 if ok else 1)
