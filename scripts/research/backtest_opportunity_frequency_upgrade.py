#!/usr/bin/env python3
"""TITAN XAU AI — Opportunity Frequency Upgrade Backtest (Sprint v2.8.7-P)
==========================================================================
Compares H1-only vs H1/M15/M5 opportunity scanner for signal frequency.
NEVER trades. NEVER creates tokens. NEVER calls order_send.
"""
from __future__ import annotations
import sys, json, csv, os, gc
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "opportunity_frequency_upgrade"

from titan.production.spread_normalization import normalize_xauusd_spread_to_usd
from titan.production.feature_stream_v2 import H1FeatureStreamV2, FEATURE_NAMES_V2
from titan.training.feature_schema_v2 import META_FEATURE_NAMES_V2
from titan.production.model_loader import load_models_by_profile
from titan.production.ceo_ai_governance import evaluate_ceo_decision
from titan.production.opportunity_scanner import scan_opportunities, SignalClass, classify_regime, scan_m15_setup, check_m5_entry_timing, classify_signal

CONTRACT_SIZE = 100; LEVERAGE = 100
EXT_DAILY_DD = 0.03; EXT_TOTAL_DD = 0.08


def load_broker(name):
    path = REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / name / "XAUUSD_H1.parquet"
    if not path.exists(): return None
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex): df.index = pd.to_datetime(df.index)
    return normalize_xauusd_spread_to_usd(df, symbol="XAUUSD", source=name)


def load_canonical_m15():
    path = REPO_ROOT / "titan" / "data" / "canonical" / "XAUUSD_M15_canonical.parquet"
    if not path.exists(): return None
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex): df.index = pd.to_datetime(df.index)
    return normalize_xauusd_spread_to_usd(df, symbol="XAUUSD", source="canonical_m15")


def load_canonical_m5():
    path = REPO_ROOT / "titan" / "data" / "canonical" / "XAUUSD_M5_canonical.parquet"
    if not path.exists(): return None
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex): df.index = pd.to_datetime(df.index)
    return normalize_xauusd_spread_to_usd(df, symbol="XAUUSD", source="canonical_m5")


def compute_predictions(df, bundle):
    df_use = df[["open","high","low","close"]].copy()
    df_use["volume"] = df.get("tick_volume", 0)
    df_use["spread"] = df["spread_usd"]
    stream = H1FeatureStreamV2(); stream._bars = df_use
    feats = stream._compute_features()
    fm = np.nan_to_num(feats.values.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    fm = stream._standardize(fm)
    alpha = bundle.xgb.predict_proba(fm)[:, 1]
    ni = {n: i for i, n in enumerate(FEATURE_NAMES_V2)}
    mi = [ni[n] for n in META_FEATURE_NAMES_V2]
    meta = bundle.meta.predict_proba(fm[:, mi])[:, 1]
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    atr = np.zeros(len(df))
    for i in range(14, len(df)): atr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    for i in range(28, len(df)): atr[i] = np.mean(atr[i-14:i])
    return alpha, meta, atr


def run_h1_only_backtest(df, alpha, meta, atr, params, starting_equity=100000):
    """Run H1-only backtest."""
    equity = starting_equity; ds = equity; wins=losses=0; gp=gl=0; max_dd=0; max_cl=0; cl=0
    dd_b=td_b=0; dt=0; cd=0; cur_day=None; signals=0
    closes = df["close"].values; index = df.index

    for i in range(28, len(df)-params["max_holding_bars"]-1):
        td_dd = (starting_equity - equity) / starting_equity
        if td_dd > max_dd: max_dd = td_dd
        if td_dd >= EXT_TOTAL_DD: td_b+=1; continue
        ddd = (ds - equity) / ds
        if ddd >= EXT_DAILY_DD: dd_b+=1; continue
        bd = index[i].date()
        if cur_day != bd: cur_day=bd; ds=equity; dt=0
        if dt >= params["max_trades_per_day"]: continue
        if cd > 0: cd-=1; continue
        ac = float(alpha[i])
        if ac < params["alpha_threshold"]: continue
        d = "LONG" if ac >= 0.5 else "SHORT"
        mc = float(meta[i])
        if mc < params["meta_threshold"]: continue
        ceo = evaluate_ceo_decision(
            regime_state={"detected":True,"regime_value":"MARKET_OPEN","confidence":ac},
            xgb_alpha={"direction":d,"confidence":ac,"pass":True}, lstm_confidence=None,
            transformer_regime=None, meta_label_quality={"quality_score":mc,"pass":True},
            broker_state={"broker_pass":True,"spread_pass":True,"slippage_pass":True},
            prop_risk_state={"risk_pass":True,"prop_funded_pass":True,"max_positions_ok":True},
            capital_protection_state={"capital_preservation_active":False,"dd_breach":False},
            model_health_state={"model_health_pass":True,"failed_required":0},
            geometry_state={"geometry_pass":True,"actual_RR":params["rr_target"],"minimum_RR":2.0})
        if not ceo.allowed_to_trade: continue
        a = atr[i] if atr[i]>0 else 3.0
        sld = a*params["sl_atr_multiplier"]; tpd = sld*params["rr_target"]
        ep = closes[i]
        if d=="LONG": slp=ep-sld; tpp=ep+tpd
        else: slp=ep+sld; tpp=ep-tpd
        ep2, er, rr = ep, "TIMEOUT", 0.0
        for j in range(1, params["max_holding_bars"]+1):
            if i+j >= len(df): break
            if d=="LONG":
                if df["low"].iloc[i+j] <= slp: ep2,er,rr=slp,"SL",-1; break
                if df["high"].iloc[i+j] >= tpp: ep2,er,rr=tpp,"TP",params["rr_target"]; break
            else:
                if df["high"].iloc[i+j] >= slp: ep2,er,rr=slp,"SL",-1; break
                if df["low"].iloc[i+j] <= tpp: ep2,er,rr=tpp,"TP",params["rr_target"]; break
        if er=="TIMEOUT":
            ep2 = closes[min(i+params["max_holding_bars"],len(df)-1)]
            rr = (ep2-ep)/sld if d=="LONG" else (ep-ep2)/sld
        signals += 1; dt += 1
        ra = equity*params["risk_percent"]; pnl = ra*rr; equity += pnl
        if pnl>0: wins+=1; gp+=pnl; cl=0
        else: losses+=1; gl+=abs(pnl); cl+=1; max_cl=max(max_cl,cl); cd=params.get("cooldown_after_loss",5)
    tt = wins+losses; wr = wins/tt if tt>0 else 0
    pf = gp/gl if gl>0 else (999 if gp>0 else 0); tr = (equity-starting_equity)/starting_equity
    return {"signals":signals,"trades":tt,"wr":round(wr,4),"pf":round(pf,4) if pf!=999 else 999,
            "return":round(tr,6),"max_dd":round(max_dd,6),"dd_breaches":dd_b+td_b,
            "max_consecutive_losses":max_cl,"final_equity":round(equity,2)}


def run_mtf_backtest(df_h1, df_m15, df_m5, alpha, meta, atr, params, starting_equity=100000):
    """Run MTF opportunity scanner backtest."""
    equity = starting_equity; ds = equity; wins=losses=0; gp=gl=0; max_dd=0; max_cl=0; cl=0
    dd_b=td_b=0; dt=0; cd=0; cur_day=None; signals=0; rejection_counter = defaultdict(int)
    closes = df_h1["close"].values; index = df_h1.index

    for i in range(28, len(df_h1)-params["max_holding_bars"]-1):
        td_dd = (starting_equity - equity) / starting_equity
        if td_dd > max_dd: max_dd = td_dd
        if td_dd >= EXT_TOTAL_DD: td_b+=1; continue
        ddd = (ds - equity) / ds
        if ddd >= EXT_DAILY_DD: dd_b+=1; continue
        bd = index[i].date()
        if cur_day != bd: cur_day=bd; ds=equity; dt=0
        if dt >= params["max_trades_per_day"]: continue
        if cd > 0: cd-=1; continue

        ts = index[i]
        ac = float(alpha[i]); mc = float(meta[i])
        a = atr[i] if atr[i]>0 else 3.0
        spread = float(df_h1["spread_usd"].iloc[i]) if "spread_usd" in df_h1.columns else 0.3

        # Get M15/M5 windows up to current H1 timestamp
        h1_window = df_h1.iloc[max(0,i-60):i+1]
        m15_window = df_m15.loc[:ts].tail(60) if df_m15 is not None and len(df_m15) > 0 else pd.DataFrame()
        m5_window = df_m5.loc[:ts].tail(60) if df_m5 is not None and len(df_m5) > 0 else pd.DataFrame()

        if len(m15_window) < 20 or len(m5_window) < 5:
            rejection_counter["insufficient_mtf_data"] += 1
            continue

        # Scan opportunities
        candidates = scan_opportunities(h1_window, m15_window, m5_window, ac, mc, a, spread,
                                         params["sl_atr_multiplier"], params["rr_target"])

        if not candidates:
            rejection_counter["no_opportunity"] += 1
            continue

        # Take first non-C candidate
        trade_candidate = None
        for c in candidates:
            if c.expected_frequency_class != "C_SHADOW_ONLY":
                trade_candidate = c
                break

        if trade_candidate is None:
            rejection_counter["c_shadow_only"] += 1
            continue

        # CEO
        d = trade_candidate.direction
        ceo = evaluate_ceo_decision(
            regime_state={"detected":True,"regime_value":"MARKET_OPEN","confidence":ac},
            xgb_alpha={"direction":d,"confidence":ac,"pass":True}, lstm_confidence=None,
            transformer_regime=None, meta_label_quality={"quality_score":mc,"pass":True},
            broker_state={"broker_pass":True,"spread_pass":True,"slippage_pass":True},
            prop_risk_state={"risk_pass":True,"prop_funded_pass":True,"max_positions_ok":True},
            capital_protection_state={"capital_preservation_active":False,"dd_breach":False},
            model_health_state={"model_health_pass":True,"failed_required":0},
            geometry_state={"geometry_pass":True,"actual_RR":params["rr_target"],"minimum_RR":2.0})
        if not ceo.allowed_to_trade:
            rejection_counter["ceo_block"] += 1
            continue

        # Risk per signal class
        risk_pct = params["risk_percent"]
        if trade_candidate.expected_frequency_class == "B":
            risk_pct *= 0.5  # B class gets half risk
        elif trade_candidate.expected_frequency_class == "A_PLUS":
            risk_pct = min(risk_pct * 1.25, 0.015)  # A_PLUS gets 1.25x (capped)

        # Execute
        sld = a * params["sl_atr_multiplier"]; tpd = sld * params["rr_target"]
        ep = closes[i]
        if d=="LONG": slp=ep-sld; tpp=ep+tpd
        else: slp=ep+sld; tpp=ep-tpd
        ep2, er, rr = ep, "TIMEOUT", 0.0
        for j in range(1, params["max_holding_bars"]+1):
            if i+j >= len(df_h1): break
            if d=="LONG":
                if df_h1["low"].iloc[i+j] <= slp: ep2,er,rr=slp,"SL",-1; break
                if df_h1["high"].iloc[i+j] >= tpp: ep2,er,rr=tpp,"TP",params["rr_target"]; break
            else:
                if df_h1["high"].iloc[i+j] >= slp: ep2,er,rr=slp,"SL",-1; break
                if df_h1["low"].iloc[i+j] <= tpp: ep2,er,rr=tpp,"TP",params["rr_target"]; break
        if er=="TIMEOUT":
            ep2 = closes[min(i+params["max_holding_bars"],len(df_h1)-1)]
            rr = (ep2-ep)/sld if d=="LONG" else (ep-ep2)/sld

        signals += 1; dt += 1
        ra = equity*risk_pct; pnl = ra*rr; equity += pnl
        if pnl>0: wins+=1; gp+=pnl; cl=0
        else: losses+=1; gl+=abs(pnl); cl+=1; max_cl=max(max_cl,cl); cd=params.get("cooldown_after_loss",5)

    tt = wins+losses; wr = wins/tt if tt>0 else 0
    pf = gp/gl if gl>0 else (999 if gp>0 else 0); tr = (equity-starting_equity)/starting_equity
    return {"signals":signals,"trades":tt,"wr":round(wr,4),"pf":round(pf,4) if pf!=999 else 999,
            "return":round(tr,6),"max_dd":round(max_dd,6),"dd_breaches":dd_b+td_b,
            "max_consecutive_losses":max_cl,"final_equity":round(equity,2),
            "rejection_breakdown":dict(rejection_counter)}


def main():
    ts = datetime.now(timezone.utc).isoformat(); OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("="*70); print("  OPPORTUNITY FREQUENCY UPGRADE BACKTEST (v2.8.7-P)"); print("="*70); print(f"  {ts}\n")
    bundle = load_models_by_profile("v2_feature_normalized")
    if not bundle.ok: print("  ERROR: model load failed"); return
    df_h1 = load_broker("exness")
    if df_h1 is None: print("  ERROR: exness data not found"); return
    df_m15 = load_canonical_m15()
    df_m5 = load_canonical_m5()
    alpha, meta, atr = compute_predictions(df_h1, bundle)
    oos = (df_h1.index.year >= 2025) & (df_h1.index.year <= 2026)
    df_oos = df_h1[oos]; om = np.asarray(oos)

    params = {"alpha_threshold":0.50,"meta_threshold":0.50,"risk_percent":0.0125,
              "sl_atr_multiplier":2.0,"rr_target":3.0,"max_holding_bars":3,
              "max_trades_per_day":2,"cooldown_after_loss":5}

    print("  Running H1-only backtest...")
    h1_result = run_h1_only_backtest(df_oos, alpha[om], meta[om], atr[om], params)
    print(f"    H1: signals={h1_result['signals']}, pf={h1_result['pf']}, dd={h1_result['max_dd']}")

    print("  Running MTF opportunity scanner backtest...")
    mtf_result = run_mtf_backtest(df_oos, df_m15, df_m5, alpha[om], meta[om], atr[om], params)
    print(f"    MTF: signals={mtf_result['signals']}, pf={mtf_result['pf']}, dd={mtf_result['max_dd']}")
    print(f"    Rejections: {mtf_result.get('rejection_breakdown', {})}")

    # OOS days for signals/day calculation
    oos_days = max(1, (df_oos.index[-1] - df_oos.index[0]).days)
    h1_signals_per_day = h1_result["signals"] / oos_days
    mtf_signals_per_day = mtf_result["signals"] / oos_days

    # Verdict
    dd_safe = mtf_result["max_dd"] < EXT_TOTAL_DD and mtf_result["dd_breaches"] == 0
    pf_ok = mtf_result["pf"] >= 1.15 or mtf_result["pf"] == 999
    freq_ok = mtf_signals_per_day >= 1
    if dd_safe and pf_ok and freq_ok:
        verdict = "FREQUENCY_UPGRADE_PASS"
    elif dd_safe and mtf_signals_per_day > h1_signals_per_day:
        verdict = "FREQUENCY_UPGRADE_NEAR_PASS"
    else:
        verdict = "FREQUENCY_UPGRADE_FAIL"

    # Write outputs
    comparison = [{"mode":"H1_only",**h1_result,"signals_per_day":round(h1_signals_per_day,4)},
                  {"mode":"MTF_scanner",**{k:v for k,v in mtf_result.items() if k!="rejection_breakdown"},
                   "signals_per_day":round(mtf_signals_per_day,4)}]
    with open(OUTPUT_DIR/"h1_vs_mtf_comparison.csv","w",newline="",encoding="utf-8") as f:
        if comparison: w=csv.DictWriter(f,fieldnames=list(comparison[0].keys())); w.writeheader(); [w.writerow(r) for r in comparison]

    result = {"timestamp_utc":ts,"verdict":verdict,"h1_result":h1_result,"mtf_result":{k:v for k,v in mtf_result.items() if k!="rejection_breakdown"},
              "h1_signals_per_day":round(h1_signals_per_day,4),"mtf_signals_per_day":round(mtf_signals_per_day,4),
              "rejection_breakdown":mtf_result.get("rejection_breakdown",{})}
    with open(OUTPUT_DIR/"frequency_upgrade_backtest.json","w") as f: json.dump(result,f,indent=2,default=str)
    with open(OUTPUT_DIR/"frequency_upgrade_backtest.md","w",encoding="utf-8") as f:
        f.write("# Frequency Upgrade Backtest (Sprint v2.8.7-P)\n\n"); f.write(f"**{ts}**\n\n## Verdict: {verdict}\n\n")
        f.write("| Metric | H1-only | MTF Scanner |\n|---|---|---|\n")
        for k in ["signals","trades","wr","pf","return","max_dd","dd_breaches","signals_per_day"]:
            h1_v = h1_result.get(k, "N/A"); mtf_v = mtf_result.get(k, "N/A")
            f.write(f"| {k} | {h1_v} | {mtf_v} |\n")
        f.write(f"\n## MTF Rejection Breakdown\n\n")
        for k,v in mtf_result.get("rejection_breakdown",{}).items(): f.write(f"- {k}: {v}\n")
    # Selected profile YAML
    import yaml
    profile = {"mode":"mtf_opportunity_scanner","alpha_threshold":0.50,"meta_threshold":0.50,
               "risk_percent":0.0125,"sl_atr_multiplier":2.0,"rr_target":3.0,"max_holding_bars":3,
               "max_trades_per_day":2,"cooldown_after_loss":5,"verdict":verdict,
               "signals_per_day":round(mtf_signals_per_day,4)}
    with open(OUTPUT_DIR/"selected_frequency_profile.yaml","w") as f: yaml.dump(profile,f,default_flow_style=False)

    print(f"\n  Verdict: {verdict}")
    print(f"  H1 signals/day: {h1_signals_per_day:.2f}")
    print(f"  MTF signals/day: {mtf_signals_per_day:.2f}")
    print(f"  Output: {OUTPUT_DIR}")

if __name__ == "__main__": main()
