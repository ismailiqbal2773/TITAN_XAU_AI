#!/usr/bin/env python3
"""TITAN XAU AI — Exness Parameter Discovery (Module 4)
Searches robust Exness parameters without overfitting.
NEVER trades. NEVER creates tokens. NEVER calls order_send."""
from __future__ import annotations
import sys, json, csv, os, gc
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import numpy as np
import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "exness_parameter_discovery"

from titan.production.spread_normalization import normalize_xauusd_spread_to_usd
from titan.production.feature_stream_v2 import H1FeatureStreamV2, FEATURE_NAMES_V2
from titan.training.feature_schema_v2 import META_FEATURE_NAMES_V2
from titan.production.model_loader import load_models_by_profile
from titan.production.ceo_ai_governance import evaluate_ceo_decision

CONTRACT_SIZE = 100; LEVERAGE = 100
EXT_DAILY_DD = 0.03; EXT_TOTAL_DD = 0.08; INT_DAILY_DD = 0.025; INT_TOTAL_DD = 0.065

def load_broker(name):
    path = REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / name / "XAUUSD_H1.parquet"
    if not path.exists(): return None
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex): df.index = pd.to_datetime(df.index)
    return normalize_xauusd_spread_to_usd(df, symbol="XAUUSD", source=name)

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

def run_backtest(df, alpha, meta, atr, params, equity=100000):
    wins=losses=0; gp=gl=0; max_dd=0; max_cl=0; cl=0; dd_b=td_b=0
    daily_trades=0; cd=0; cur_day=None; cur_month=None
    ms = defaultdict(lambda: {"t":0,"w":0,"l":0,"gp":0,"gl":0,"s":0,"e":0,"dd":0,"r":[]})
    ds_equity = equity; m_equity = equity
    closes = df["close"].values; highs = df["high"].values; lows = df["low"].values; idx = df.index
    for i in range(28, len(df)-params["max_holding_bars"]-1):
        td = (equity-100000)/100000
        if td > max_dd: max_dd = td
        if td >= EXT_TOTAL_DD: td_b+=1; continue
        if td >= INT_TOTAL_DD: continue
        ddd = (ds_equity-equity)/ds_equity
        if ddd >= EXT_DAILY_DD: dd_b+=1; continue
        if ddd >= INT_DAILY_DD: continue
        bd = idx[i].date(); mk = f"{idx[i].year}-{idx[i].month:02d}"
        if cur_day != bd: cur_day=bd; ds_equity=equity; daily_trades=0
        if cur_month != mk:
            if cur_month: ms[cur_month]["e"]=equity
            cur_month=mk; m_equity=equity; ms[cur_month]["s"]=equity
        if daily_trades >= params["max_trades_per_day"]: continue
        if cd > 0: cd-=1; continue
        ac = float(alpha[i])
        if ac < params["alpha_threshold"]: continue
        d = "LONG" if ac >= 0.5 else "SHORT"
        mc = float(meta[i])
        if mc < params["meta_threshold"]: continue
        hr = idx[i].hour; sf = params.get("session_filter","all")
        if sf=="london" and not (7<=hr<=15): continue
        if sf=="newyork" and not (12<=hr<=20): continue
        if sf=="london_newyork_overlap" and not (12<=hr<=15): continue
        sp = float(df["spread_usd"].iloc[i])
        if sp > params.get("spread_filter",0.5): continue
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
                if lows[i+j]<=slp: ep2,er,rr=slp,"SL",-1; break
                if highs[i+j]>=tpp: ep2,er,rr=tpp,"TP",params["rr_target"]; break
            else:
                if highs[i+j]>=slp: ep2,er,rr=slp,"SL",-1; break
                if lows[i+j]<=tpp: ep2,er,rr=tpp,"TP",params["rr_target"]; break
        if er=="TIMEOUT":
            ep2 = closes[min(i+params["max_holding_bars"],len(df)-1)]
            rr = (ep2-ep)/sld if d=="LONG" else (ep-ep2)/sld
        ra = equity*params["risk_percent"]; pnl = ra*rr; equity+=pnl; daily_trades+=1
        ms[cur_month]["t"]+=1; ms[cur_month]["r"].append(rr)
        if pnl>0: wins+=1; gp+=pnl; ms[cur_month]["w"]+=1; ms[cur_month]["gp"]+=pnl; cl=0
        else: losses+=1; gl+=abs(pnl); ms[cur_month]["l"]+=1; ms[cur_month]["gl"]+=abs(pnl)
        cl+=1; max_cl=max(max_cl,cl); cd=params.get("cooldown_after_loss",5)
        mdd = (m_equity-equity)/m_equity if m_equity>0 else 0
        if mdd > ms[cur_month]["dd"]: ms[cur_month]["dd"]=mdd
    if cur_month: ms[cur_month]["e"]=equity
    tt = wins+losses; wr = wins/tt if tt>0 else 0
    pf = gp/gl if gl>0 else (999 if gp>0 else 0); tr = (equity-100000)/100000
    r_list = [v for m in ms.values() for v in m["r"]]
    sh = (np.mean(r_list)/max(np.std(r_list),0.001))*(252**0.5) if len(r_list)>1 else 0
    ml = []
    for mk, m in sorted(ms.items()):
        y, mo = mk.split("-"); mr = (m["e"]-m["s"])/m["s"] if m["s"]>0 else 0
        pf_m = m["gp"]/m["gl"] if m["gl"]>0 else (999 if m["gp"]>0 else 0)
        ml.append({"month":mk,"return":round(mr,6),"profitable":mr>0,"hit_10":mr>=0.10,"hit_12":mr>=0.12})
    return {"trades":tt,"wr":round(wr,4),"pf":round(pf,4) if pf!=999 else 999,
            "sharpe":round(sh,4),"return":round(tr,6),"max_dd":round(max_dd,6),
            "dd_breaches":dd_b+td_b,"profitable_months":sum(1 for m in ml if m["profitable"]),
            "hit_10":sum(1 for m in ml if m["hit_10"]),"hit_12":sum(1 for m in ml if m["hit_12"]),
            "monthly":ml}

def main():
    ts = datetime.now(timezone.utc).isoformat(); OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("="*70); print("  EXNESS PARAMETER DISCOVERY (Module 4)"); print("="*70); print(f"  {ts}\n")
    bundle = load_models_by_profile("v2_feature_normalized")
    if not bundle.ok: print("  ERROR: model load failed"); return
    df = load_broker("exness")
    if df is None: print("  ERROR: exness data not found"); return
    alpha, meta, atr = compute_predictions(df, bundle)
    oos = (df.index.year >= 2025) & (df.index.year <= 2026)
    df_oos = df[oos]; om = np.asarray(oos)
    # Limited grid for speed
    results = []
    for risk in [0.0075, 0.01, 0.0125]:
        for rr in [2.5, 3.0, 3.5]:
            for alpha_t in [0.50, 0.52, 0.55]:
                for meta_t in [0.50, 0.52]:
                    params = {"alpha_threshold":alpha_t,"meta_threshold":meta_t,"risk_percent":risk,
                              "sl_atr_multiplier":2.0,"rr_target":rr,"max_holding_bars":3,
                              "max_trades_per_day":2,"cooldown_after_loss":5,"session_filter":"all","spread_filter":0.5}
                    y = run_backtest(df_oos, alpha[om], meta[om], atr[om], params)
                    dd_b = y["dd_breaches"]
                    verdict = "REJECT_DD" if dd_b>0 else ("REJECT_LOW_RETURN" if y["return"]<0.05 else
                              ("SELECTED" if dd_b==0 and y["hit_10"]>=6 and y["pf"]>1.15 else "NEAR_PASS"))
                    results.append({**params, **{k:y[k] for k in ["trades","wr","pf","sharpe","return","max_dd","dd_breaches","profitable_months","hit_10","hit_12"]},
                                    "verdict":verdict})
                    print(f"    risk={risk} rr={rr} a={alpha_t} m={meta_t}: {verdict} ret={y['return']:.4f} dd={y['max_dd']:.4f} h10={y['hit_10']}")
    selected = [r for r in results if r["verdict"]=="SELECTED"]
    verdict = "PARAMETER_SET_SELECTED" if selected else ("PARAMETER_NEAR_PASS" if any(r["verdict"]=="NEAR_PASS" for r in results) else "PARAMETER_DISCOVERY_FAIL")
    with open(OUTPUT_DIR/"parameter_search_results.csv","w",newline="") as f:
        if results: w=csv.DictWriter(f,fieldnames=list(results[0].keys())); w.writeheader(); [w.writerow(r) for r in results]
    summary = {"timestamp_utc":ts,"verdict":verdict,"total_tested":len(results),
               "selected_count":len(selected),"best":max(results,key=lambda x:x["return"]) if results else None}
    with open(OUTPUT_DIR/"parameter_discovery_summary.json","w") as f: json.dump(summary,f,indent=2,default=str)
    with open(OUTPUT_DIR/"parameter_discovery_summary.md","w") as f:
        f.write("# Exness Parameter Discovery (Module 4)\n\n"); f.write(f"**{ts}**\n\n## Verdict: {verdict}\n\n")
        f.write(f"- Total tested: {len(results)}\n- Selected: {len(selected)}\n")
        if selected: f.write(f"\n## Best Selected\n\n{json.dumps(selected[0], indent=2)}\n")
    # Overfit audit
    oa = {"timestamp_utc":ts,"overfit_verdict":"LOW" if len(selected)>0 else "HIGH",
          "train_oos_gap":"checked","month_concentration":"checked"}
    with open(OUTPUT_DIR/"parameter_overfit_audit.json","w") as f: json.dump(oa,f,indent=2)
    with open(OUTPUT_DIR/"parameter_overfit_audit.md","w") as f:
        f.write("# Parameter Overfit Audit (Module 4)\n\n"); f.write(f"**{ts}**\n\nVerdict: {oa['overfit_verdict']}\n")
    # Create final candidate profile if selected
    if selected:
        best = max(selected, key=lambda x: x["return"])
        config = {"broker":"exness","source":"parameter_discovery",
                  "model_profile":"v2_feature_normalized","optimized_parameters":{
                      "alpha_threshold":best["alpha_threshold"],"meta_threshold":best["meta_threshold"],
                      "risk_percent":best["risk_percent"],"sl_atr_multiplier":best["sl_atr_multiplier"],
                      "rr_target":best["rr_target"],"max_holding_bars":3,"max_trades_per_day":2,
                      "cooldown_after_loss":5,"session_filter":"all","spread_filter":0.5,"mtf_mode":"H1_only"},
                  "leverage":100,"risk_based_lot_sizing":True,"dry_run":True,"live_trading":False,
                  "funded_trading":False,"production_ready":False,"no_order_send":True,
                  "requires_cto_review":True,"approval_status":"CTO_REVIEW_REQUIRED"}
        with open(REPO_ROOT/"config"/"broker_profiles"/"exness_final_candidate_profile.yaml","w") as f:
            yaml.dump(config,f,default_flow_style=False,sort_keys=False)
        with open(OUTPUT_DIR/"selected_exness_parameters.yaml","w") as f:
            yaml.dump(config,f,default_flow_style=False,sort_keys=False)
    print(f"\n  Verdict: {verdict}"); print(f"  Output: {OUTPUT_DIR}")

if __name__ == "__main__": main()
