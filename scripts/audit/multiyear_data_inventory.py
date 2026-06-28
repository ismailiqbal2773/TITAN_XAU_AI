"""
TITAN XAU AI — Sprint 9.9.3.8 Stage A: Multi-Year Data Inventory
=================================================================
Discovers all real XAUUSD datasets. Inventory only — no backtest.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "historical_multiyear" / "chunks"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
JSON_OUT = OUTPUT_DIR / "data_inventory.json"
MD_OUT = OUTPUT_DIR / "data_inventory.md"

DATASET_PATTERNS = [
    ("canonical", "H1", "titan/data/canonical/XAUUSD_H1_canonical.parquet"),
    ("canonical", "M30", "titan/data/canonical/XAUUSD_M30_canonical.parquet"),
    ("canonical", "M15", "titan/data/canonical/XAUUSD_M15_canonical.parquet"),
    ("canonical", "M5", "titan/data/canonical/XAUUSD_M5_canonical.parquet"),
    ("exness", "H1", "titan/data/sources/mt5_brokers/exness/XAUUSD_H1.parquet"),
    ("exness", "M30", "titan/data/sources/mt5_brokers/exness/XAUUSD_M30.parquet"),
    ("exness", "M15", "titan/data/sources/mt5_brokers/exness/XAUUSD_M15.parquet"),
    ("exness", "M5", "titan/data/sources/mt5_brokers/exness/XAUUSD_M5.parquet"),
    ("fundednext", "H1", "titan/data/sources/mt5_brokers/fundednext/XAUUSD_H1.parquet"),
    ("fundednext", "M30", "titan/data/sources/mt5_brokers/fundednext/XAUUSD_M30.parquet"),
    ("fundednext", "M15", "titan/data/sources/mt5_brokers/fundednext/XAUUSD_M15.parquet"),
    ("fundednext", "M5", "titan/data/sources/mt5_brokers/fundednext/XAUUSD_M5.parquet"),
    ("icmarkets", "H1", "titan/data/sources/mt5_brokers/icmarkets/XAUUSD_H1.parquet"),
    ("icmarkets", "M30", "titan/data/sources/mt5_brokers/icmarkets/XAUUSD_M30.parquet"),
    ("icmarkets", "M15", "titan/data/sources/mt5_brokers/icmarkets/XAUUSD_M15.parquet"),
    ("icmarkets", "M5", "titan/data/sources/mt5_brokers/icmarkets/XAUUSD_M5.parquet"),
    ("fbs", "H1", "titan/data/sources/mt5_brokers/fbs/XAUUSD_H1.parquet"),
    ("fbs", "M30", "titan/data/sources/mt5_brokers/fbs/XAUUSD_M30.parquet"),
    ("fbs", "M15", "titan/data/sources/mt5_brokers/fbs/XAUUSD_M15.parquet"),
    ("fbs", "M5", "titan/data/sources/mt5_brokers/fbs/XAUUSD_M5.parquet"),
]
BROKER_QUALITY = {"canonical":88,"exness":85,"icmarkets":88,"fundednext":80,"fbs":75}
BROKER_SPREAD_MULT = {"canonical":1.0,"exness":1.0,"icmarkets":0.85,"fundednext":1.15,"fbs":1.30}
EXPECTED_BARS = {"H1":6000,"M30":12000,"M15":24000,"M5":72000}


def analyze(source, tf, path):
    p = REPO_ROOT / path
    if not p.exists():
        return {"source":source,"timeframe":tf,"path":path,"error":"not found"}
    try:
        df = pd.read_parquet(p)
        total = len(df)
        if not isinstance(df.index, pd.DatetimeIndex):
            return {"source":source,"timeframe":tf,"path":path,"error":"no datetime index"}
        start, end = df.index.min(), df.index.max()
        rpy = {}
        for y in range(2020, 2027):
            yd = df[(df.index >= f"{y}-01-01") & (df.index < f"{y+1}-01-01")]
            if len(yd) > 0: rpy[str(y)] = len(yd)
        spread_col = spread_mean = None
        warnings = []
        if 'spread_usd' in df.columns:
            spread_col = 'spread_usd'; spread_mean = float(df[spread_col].mean())
        elif 'spread' in df.columns:
            spread_col = 'spread'; spread_mean = float(df[spread_col].mean()) * 0.01
            if spread_mean < 0.02:
                warnings.append(f"unusually low spread (${spread_mean:.4f})")
        expected = EXPECTED_BARS.get(tf,6000) * 6
        missing = max(0.0, (1 - total/expected)*100) if expected > 0 else 0
        dup = df.index.duplicated().sum()
        dup_pct = (dup/total*100) if total > 0 else 0
        if dup_pct > 1.0: warnings.append(f"{dup_pct:.2f}% duplicates")
        if missing > 50: warnings.append(f"high missing ({missing:.1f}%)")
        return {"source":source,"timeframe":tf,"path":path,"total_rows":total,
                "start":str(start),"end":str(end),"rows_per_year":rpy,
                "spread_column":spread_col,"spread_available":spread_col is not None,
                "spread_mean_usd":round(spread_mean,4) if spread_mean else None,
                "missing_pct":round(missing,2),"duplicate_pct":round(dup_pct,4),
                "warnings":warnings,"years_available":sorted(rpy.keys()),
                "broker_quality":BROKER_QUALITY.get(source,80),
                "spread_multiplier":BROKER_SPREAD_MULT.get(source,1.0)}
    except Exception as e:
        return {"source":source,"timeframe":tf,"path":path,"error":str(e)}


def main():
    print("="*78)
    print("  Sprint 9.9.3.8 Stage A: Data Inventory")
    print("="*78)
    results = []
    for s, tf, path in DATASET_PATTERNS:
        print(f"  {s}/{tf}...", end=" ", flush=True)
        info = analyze(s, tf, path)
        results.append(info)
        if "error" in info: print(f"ERROR: {info['error']}")
        else: print(f"{info['total_rows']:,} rows, {info['start'][:10]} to {info['end'][:10]}")
    report = {
        "audit":"sprint_9_9_3_8_stage_a_data_inventory",
        "timestamp_utc":datetime.now(timezone.utc).isoformat(),
        "total_datasets":len(results),"datasets":results,
        "summary":{
            "sources":sorted(set(d.get("source","?") for d in results if "error" not in d)),
            "timeframes":sorted(set(d.get("timeframe","?") for d in results if "error" not in d)),
            "total_rows":sum(d.get("total_rows",0) for d in results if "error" not in d),
            "years_covered":sorted(set(y for d in results if "error" not in d for y in d.get("years_available",[]))),
        },
    }
    with open(JSON_OUT,"w",encoding="utf-8") as f: json.dump(report,f,indent=2,default=str)
    md = ["# Sprint 9.9.3.8 Stage A — Data Inventory\n\n",
          f"**Timestamp:** {report['timestamp_utc']}\n",
          f"**Datasets:** {report['total_datasets']}\n\n"]
    md.append("| Source | TF | Rows | Start | End | Spread | Missing% | Warnings |\n|---|---|---|---|---|---|---|---|\n")
    for d in results:
        if "error" in d:
            md.append(f"| {d['source']} | {d['timeframe']} | ERROR | — | — | — | — | {d['error']} |\n")
        else:
            w = "; ".join(d.get("warnings",[])) or "none"
            md.append(f"| {d['source']} | {d['timeframe']} | {d['total_rows']:,} | {d['start'][:10]} | {d['end'][:10]} | ${d.get('spread_mean_usd','N/A')} | {d['missing_pct']}% | {w} |\n")
    md.append("\n## Rows Per Year\n\n| Source | TF | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |\n|---|---|---|---|---|---|---|---|---|\n")
    for d in results:
        if "error" in d: continue
        rpy = d.get("rows_per_year",{})
        row = f"| {d['source']} | {d['timeframe']} "
        for y in ["2020","2021","2022","2023","2024","2025","2026"]:
            row += f"| {rpy.get(y,0):,} "
        md.append(row + "|\n")
    with open(MD_OUT,"w",encoding="utf-8") as f: f.writelines(md)
    print(f"\n  JSON: {JSON_OUT}\n  MD:   {MD_OUT}")

if __name__ == "__main__": main()
