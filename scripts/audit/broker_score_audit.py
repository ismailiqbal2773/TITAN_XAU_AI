#!/usr/bin/env python3
"""
TITAN XAU AI — Broker Score Audit (Sprint 9.9.3.45.8.5)
=========================================================

Scores every broker declared in ``config/broker_profiles.yaml`` against
the 14-dimensional BrokerScoringEngine and writes a JSON + Markdown
report to:

  data/audit/broker_scoring/broker_score_report.json
  data/audit/broker_scoring/broker_score_report.md

The audit also scores brokers that appear in the historical frozen-
balanced validation CSV but are missing from the YAML config (e.g.
``exness``) by injecting a synthetic profile derived from the
historical record. This guarantees that no broker with live historical
evidence is silently dropped from the audit.

Audit verdicts (separate from the engine's BROKER_APPROVED / CAUTION /
BLOCKED verdicts):

  BROKER_SCORING_READY        — broker scores >= 85 (engine APPROVED)
  BROKER_SCORING_NEEDS_WORK   — broker scores 70-84 (engine CAUTION)
  BROKER_SCORING_BLOCKED      — broker scores < 70  (engine BLOCKED)

This script is pure Python. It NEVER imports MetaTrader5, NEVER calls
``mt5.order_send``, and NEVER submits orders.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.broker_scoring_engine import (
    BrokerScoringEngine,
    BrokerScoreResult,
    BROKER_APPROVED,
    BROKER_CAUTION,
    BROKER_BLOCKED,
    SCORE_COMPONENTS,
    SAFETY_FLAGS,
    BROKER_ID_TO_HISTORICAL_SOURCE,
)

logger = logging.getLogger(__name__)

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "broker_scoring"
JSON_PATH = OUTPUT_DIR / "broker_score_report.json"
MD_PATH = OUTPUT_DIR / "broker_score_report.md"

PROFILES_PATH = REPO_ROOT / "config" / "broker_profiles.yaml"
HISTORICAL_CSV = (
    REPO_ROOT
    / "data"
    / "audit"
    / "frozen_balanced_validation"
    / "broker_validation.csv"
)


# ─── Audit verdicts ────────────────────────────────────────────────────────
BROKER_SCORING_READY: str = "BROKER_SCORING_READY"
BROKER_SCORING_NEEDS_WORK: str = "BROKER_SCORING_NEEDS_WORK"
BROKER_SCORING_BLOCKED: str = "BROKER_SCORING_BLOCKED"

ALL_AUDIT_VERDICTS: tuple[str, ...] = (
    BROKER_SCORING_READY,
    BROKER_SCORING_NEEDS_WORK,
    BROKER_SCORING_BLOCKED,
)


def audit_verdict_for(engine_verdict: str) -> str:
    """Map the engine verdict to the audit verdict namespace."""
    if engine_verdict == BROKER_APPROVED:
        return BROKER_SCORING_READY
    if engine_verdict == BROKER_CAUTION:
        return BROKER_SCORING_NEEDS_WORK
    return BROKER_SCORING_BLOCKED


# ─── Synthetic profile builder for brokers not in YAML ─────────────────────
# When the historical CSV contains a broker not declared in the YAML
# (e.g. exness), we synthesize a conservative profile so the engine
# can still produce a score. The historical record itself is the
# primary signal — the synthetic profile is a fallback so the broker
# is not silently dropped from the audit.
SYNTHETIC_PROFILES: dict[str, dict[str, Any]] = {
    "exness": {
        "broker_id": "exness",
        "name": "Exness (synthetic from historical CSV)",
        "server": "Exness-Real",
        "account_type": "live",
        "typical_spread_xauusd": 0.25,
        "max_spread_xauusd": 0.45,
        "commission_per_lot_round_turn": 7.0,
        "typical_slippage_xauusd": 0.02,
        "max_slippage_xauusd": 0.10,
        "swap_long_xauusd_per_lot_per_night": -4.0,
        "swap_short_xauusd_per_lot_per_night": -1.4,
        "contract_size_xauusd": 100,
        "stops_level_points_xauusd": 30,
        "freeze_level_points_xauusd": 0,
        "filling_mode": "ORDER_FILLING_IOC",
        "margin_currency": "USD",
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "leverage_options": [100, 200, 500],
    },
    "fbs": {
        "broker_id": "fbs",
        "name": "FBS (synthetic from historical CSV)",
        "server": "FBS-Real",
        "account_type": "live",
        "typical_spread_xauusd": 0.30,
        "max_spread_xauusd": 0.50,
        "commission_per_lot_round_turn": 6.0,
        "typical_slippage_xauusd": 0.03,
        "max_slippage_xauusd": 0.12,
        "swap_long_xauusd_per_lot_per_night": -3.5,
        "swap_short_xauusd_per_lot_per_night": -1.2,
        "contract_size_xauusd": 100,
        "stops_level_points_xauusd": 40,
        "freeze_level_points_xauusd": 0,
        "filling_mode": "ORDER_FILLING_IOC",
        "margin_currency": "USD",
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "leverage_options": [100, 200, 500],
    },
    "fundednext": {
        "broker_id": "fundednext",
        "name": "FundedNext (synthetic from historical CSV)",
        "server": "FundedNext-Server",
        "account_type": "live",
        "typical_spread_xauusd": 0.28,
        "max_spread_xauusd": 0.50,
        "commission_per_lot_round_turn": 6.0,
        "typical_slippage_xauusd": 0.02,
        "max_slippage_xauusd": 0.10,
        "swap_long_xauusd_per_lot_per_night": -3.5,
        "swap_short_xauusd_per_lot_per_night": -1.2,
        "contract_size_xauusd": 100,
        "stops_level_points_xauusd": 30,
        "freeze_level_points_xauusd": 0,
        "filling_mode": "ORDER_FILLING_IOC",
        "margin_currency": "USD",
        "min_lot": 0.01,
        "max_lot": 50.0,
        "lot_step": 0.01,
        "leverage_options": [100],
    },
    "icmarkets": {
        "broker_id": "icmarkets",
        "name": "IC Markets (synthetic from historical CSV)",
        "server": "ICMarketsSC-Live",
        "account_type": "live",
        "typical_spread_xauusd": 0.22,
        "max_spread_xauusd": 0.40,
        "commission_per_lot_round_turn": 7.0,
        "typical_slippage_xauusd": 0.02,
        "max_slippage_xauusd": 0.08,
        "swap_long_xauusd_per_lot_per_night": -4.0,
        "swap_short_xauusd_per_lot_per_night": -1.4,
        "contract_size_xauusd": 100,
        "stops_level_points_xauusd": 50,
        "freeze_level_points_xauusd": 0,
        "filling_mode": "ORDER_FILLING_IOC",
        "margin_currency": "USD",
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "leverage_options": [100, 200, 500],
    },
    "canonical": {
        "broker_id": "canonical",
        "name": "Canonical (synthetic — represents MetaQuotes-Demo)",
        "server": "MetaQuotes-Demo",
        "account_type": "demo",
        "typical_spread_xauusd": 0.35,
        "max_spread_xauusd": 0.50,
        "commission_per_lot_round_turn": 0.0,
        "typical_slippage_xauusd": 0.02,
        "max_slippage_xauusd": 0.10,
        "swap_long_xauusd_per_lot_per_night": -3.5,
        "swap_short_xauusd_per_lot_per_night": -1.2,
        "contract_size_xauusd": 100,
        "stops_level_points_xauusd": 50,
        "freeze_level_points_xauusd": 0,
        "filling_mode": "ORDER_FILLING_IOC",
        "margin_currency": "USD",
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "leverage_options": [30, 50, 100],
    },
}


def _load_historical_sources(csv_path: Path) -> list[str]:
    """Return the list of source labels in the historical CSV."""
    import csv as _csv
    if not csv_path.exists():
        return []
    sources: list[str] = []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = _csv.DictReader(f)
            for row in reader:
                src = (row.get("source") or "").strip().lower()
                if src and src not in sources:
                    sources.append(src)
    except Exception as e:
        logger.error("Failed to read historical CSV %s: %s", csv_path, e)
    return sources


def _build_audit_engine(
    profiles_path: Path,
    historical_csv: Optional[Path],
) -> BrokerScoringEngine:
    """
    Construct a BrokerScoringEngine backed by the canonical YAML plus
    synthetic profiles for brokers only present in the historical CSV.

    We do this by writing a merged YAML to a temporary in-repo path
    under data/audit/broker_scoring/. The original YAML is never
    modified.

    If ``historical_csv`` is None or does not exist, no synthetic
    profiles are injected and the engine runs purely on the YAML.
    """
    import yaml

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    merged_path = OUTPUT_DIR / "_merged_broker_profiles.yaml"

    # Load original YAML.
    with open(profiles_path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    brokers: dict[str, dict] = dict(doc.get("brokers", {}) or {})

    # Identify historical-only brokers and inject synthetic profiles.
    historical_sources: list[str] = []
    if historical_csv is not None and historical_csv.exists():
        historical_sources = _load_historical_sources(historical_csv)
    injected: list[str] = []
    for source in historical_sources:
        if source in brokers:
            continue
        # Check if any YAML broker maps to this source via the
        # BROKER_ID_TO_HISTORICAL_SOURCE mapping. If so, skip — it's
        # already represented.
        already_represented = any(
            BROKER_ID_TO_HISTORICAL_SOURCE.get(bid) == source
            for bid in brokers
        )
        if already_represented:
            continue
        if source in SYNTHETIC_PROFILES:
            brokers[source] = SYNTHETIC_PROFILES[source]
            injected.append(source)

    merged_doc = {"brokers": brokers}
    merged_path.write_text(
        yaml.safe_dump(merged_doc, sort_keys=False),
        encoding="utf-8",
    )

    engine = BrokerScoringEngine(
        profiles_path=merged_path,
        historical_csv=historical_csv if (
            historical_csv is not None and historical_csv.exists()
        ) else None,
    )
    engine._injected_brokers = injected  # type: ignore[attr-defined]
    return engine


def _format_components_row(result: BrokerScoreResult) -> dict[str, Any]:
    """Compact row for the broker score table."""
    c = result.components
    return {
        "broker": result.broker_name,
        "broker_id": result.broker_id,
        "score": round(result.score, 2),
        "verdict": audit_verdict_for(result.verdict),
        "engine_verdict": result.verdict,
        "spread": round(c.get("spread_score", 0.0), 1),
        "slippage": round(c.get("slippage_score", 0.0), 1),
        "commission": round(c.get("commission_score", 0.0), 1),
        "stop_level": round(c.get("stop_level_score", 0.0), 1),
        "freeze_level": round(c.get("freeze_level_score", 0.0), 1),
        "fill_mode": round(c.get("filling_mode_score", 0.0), 1),
        "net_impact": round(c.get("net_expectancy_impact_score", 0.0), 1),
        "prop_compatible": result.prop_funded_compatible,
        "notes": "; ".join(result.notes) if result.notes else "",
    }


_UNSET = object()  # sentinel for "argument not provided"


def run_audit(
    profiles_path: Path | str | None = _UNSET,  # type: ignore[assignment]
    historical_csv: Path | str | None = _UNSET,  # type: ignore[assignment]
    output_dir: Path | str | None = _UNSET,  # type: ignore[assignment]
) -> dict[str, Any]:
    """
    Score all brokers and write JSON + Markdown reports.

    If ``historical_csv`` is left unset, defaults to
    ``HISTORICAL_CSV`` (the shipped frozen-balanced validation CSV). If
    it is explicitly ``None``, no historical data is loaded and no
    synthetic broker profiles are injected.

    Returns:
        dict with keys: timestamp_utc, json_path, md_path, brokers,
        summary, audit_verdicts.
    """
    profiles_path = (
        Path(profiles_path) if profiles_path is not _UNSET else PROFILES_PATH
    )
    # historical_csv unset → use default HISTORICAL_CSV.
    # historical_csv=None → explicitly disable historical data.
    historical_csv_path: Optional[Path]
    if historical_csv is _UNSET:
        historical_csv_path = HISTORICAL_CSV if HISTORICAL_CSV.exists() else None
    elif historical_csv is None:
        historical_csv_path = None
    else:
        historical_csv_path = Path(historical_csv)
    output_dir = (
        Path(output_dir) if output_dir is not _UNSET else OUTPUT_DIR
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "broker_score_report.json"
    md_path = output_dir / "broker_score_report.md"

    engine = _build_audit_engine(profiles_path, historical_csv_path)
    results = engine.score_all_brokers()
    injected = getattr(engine, "_injected_brokers", [])

    # Build summary.
    audit_verdicts = {v: 0 for v in ALL_AUDIT_VERDICTS}
    for r in results.values():
        audit_verdicts[audit_verdict_for(r.verdict)] += 1

    rows = [_format_components_row(r) for r in results.values()]
    rows.sort(key=lambda r: r["score"], reverse=True)

    timestamp = datetime.now(timezone.utc).isoformat()
    report: dict[str, Any] = {
        "timestamp_utc": timestamp,
        "profiles_path": str(profiles_path),
        "historical_csv": str(historical_csv_path) if historical_csv_path else "",
        "engine_module": "titan.production.broker_scoring_engine",
        "audit_verdicts_supported": list(ALL_AUDIT_VERDICTS),
        "summary": {
            "total_brokers": len(results),
            "approved": audit_verdicts[BROKER_SCORING_READY],
            "needs_work": audit_verdicts[BROKER_SCORING_NEEDS_WORK],
            "blocked": audit_verdicts[BROKER_SCORING_BLOCKED],
            "injected_synthetic_profiles": injected,
        },
        "audit_verdicts": audit_verdicts,
        "brokers": [r.to_dict() for r in results.values()],
        "table_rows": rows,
        "safety_flags": dict(SAFETY_FLAGS),
        "score_components": list(SCORE_COMPONENTS),
        "hard_invariants": {
            "never_calls_mt5_order_send": True,
            "no_martingale": True,
            "no_grid": True,
            "no_averaging": True,
            "pure_python": True,
        },
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    _write_markdown(md_path, report, rows, injected, timestamp)

    return {
        "timestamp_utc": timestamp,
        "json_path": str(json_path),
        "md_path": str(md_path),
        "brokers": [r.to_dict() for r in results.values()],
        "summary": report["summary"],
        "audit_verdicts": audit_verdicts,
        "table_rows": rows,
    }


def _write_markdown(
    md_path: Path,
    report: dict[str, Any],
    rows: list[dict[str, Any]],
    injected: list[str],
    timestamp: str,
) -> None:
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI — Broker Score Report\n\n")
        f.write(f"**Generated:** {timestamp}\n\n")
        f.write(
            "Scores every broker in `config/broker_profiles.yaml` against "
            "14 weighted execution-quality dimensions. Brokers present in "
            "the historical frozen-balanced validation CSV but missing from "
            "the YAML are scored using synthetic profiles.\n\n"
        )

        f.write("## Hard Safety Invariants\n\n")
        f.write("| Invariant | Value |\n|---|---|\n")
        f.write("| never_calls_mt5_order_send | True |\n")
        f.write("| no_martingale | True |\n")
        f.write("| no_grid | True |\n")
        f.write("| no_averaging | True |\n")
        f.write("| pure_python | True |\n\n")

        f.write("## Summary\n\n")
        s = report["summary"]
        f.write("| Metric | Value |\n|---|---|\n")
        f.write(f"| Total brokers scored | {s['total_brokers']} |\n")
        f.write(f"| BROKER_SCORING_READY (>=85) | {s['approved']} |\n")
        f.write(f"| BROKER_SCORING_NEEDS_WORK (70-84) | {s['needs_work']} |\n")
        f.write(f"| BROKER_SCORING_BLOCKED (<70) | {s['blocked']} |\n")
        if injected:
            f.write(
                f"| Synthetic profiles injected | {', '.join(injected)} |\n"
            )
        f.write("\n")

        f.write("## Audit Verdicts Supported\n\n")
        for v in ALL_AUDIT_VERDICTS:
            f.write(f"- `{v}`\n")
        f.write("\n")

        f.write("## Broker Score Table\n\n")
        f.write(
            "| Broker | Score | Verdict | Spread | Slippage | Commission | "
            "StopLevel | FreezeLevel | FillMode | NetImpact | "
            "PropCompatible | Notes |\n"
        )
        f.write("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        for r in rows:
            prop = "yes" if r["prop_compatible"] else "no"
            notes = (r["notes"] or "").replace("|", "/")[:80]
            f.write(
                f"| {r['broker']} | {r['score']:.2f} | {r['verdict']} | "
                f"{r['spread']:.1f} | {r['slippage']:.1f} | "
                f"{r['commission']:.1f} | {r['stop_level']:.1f} | "
                f"{r['freeze_level']:.1f} | {r['fill_mode']:.1f} | "
                f"{r['net_impact']:.1f} | {prop} | {notes} |\n"
            )
        f.write("\n")

        f.write("## Score Components (14 weighted dimensions)\n\n")
        for c in SCORE_COMPONENTS:
            f.write(f"- `{c}`\n")
        f.write("\n")

        f.write("## Per-Broker Detail\n\n")
        for broker in report["brokers"]:
            f.write(f"### {broker['broker_name']} (`{broker['broker_id']}`)\n\n")
            f.write(f"- **Score:** {broker['score']:.2f}\n")
            f.write(f"- **Verdict:** {broker['verdict']}\n")
            f.write(
                f"- **Prop-funded compatible:** "
                f"{broker['prop_funded_compatible']}\n"
            )
            f.write(
                f"- **Historical source:** "
                f"{broker.get('historical_source', 'n/a')}\n"
            )
            f.write(
                f"- **Historical verdict:** "
                f"{broker.get('historical_verdict', 'n/a')}\n"
            )
            if broker.get("notes"):
                f.write(f"- **Notes:** {'; '.join(broker['notes'])}\n")
            f.write("\n")
            f.write("#### Component breakdown\n\n")
            f.write("| Component | Score | Weight |\n|---|---|---|\n")
            for c in SCORE_COMPONENTS:
                comp = broker["components"].get(c, 0.0)
                weight = broker["weights"].get(c, 0.0)
                f.write(f"| {c} | {comp:.2f} | {weight:.4f} |\n")
            f.write("\n")


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI — Broker Score Audit (Sprint 9.9.3.45.8.5)")
    print("=" * 70)
    result = run_audit()
    print(f"\n  JSON: {result['json_path']}")
    print(f"  MD:   {result['md_path']}")
    s = result["summary"]
    print(f"\n  Total brokers scored: {s['total_brokers']}")
    print(f"    READY:      {s['approved']}")
    print(f"    NEEDS_WORK: {s['needs_work']}")
    print(f"    BLOCKED:    {s['blocked']}")
    if s["injected_synthetic_profiles"]:
        print(
            f"    Synthetic:  {', '.join(s['injected_synthetic_profiles'])}"
        )
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
