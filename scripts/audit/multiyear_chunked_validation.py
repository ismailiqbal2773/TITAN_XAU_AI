"""
TITAN XAU AI — Sprint 9.9.3.8 Stages B+C+D: Chunked Multi-Year Validation
==========================================================================
Runs H1 validation broker-by-broker and year-by-year with checkpoints.
For each chunk (source×year), runs 5 configs + 6 cost stress modes.

Supports --resume to skip already-completed chunks.
"""
from __future__ import annotations
import json, math, sys, argparse, copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from titan.production.stress_loss_governance import (
    StressLossGovernanceEngine, GovernanceInput, AccountProfile, ExitAction,
)

CHUNK_DIR = REPO_ROOT / "data" / "audit" / "historical_multiyear" / "chunks"
CHUNK_DIR.mkdir(parents=True, exist_ok=True)

SOURCES = {
    "canonical": "titan/data/canonical/XAUUSD_H1_canonical.parquet",
    "exness": "titan/data/sources/mt5_brokers/exness/XAUUSD_H1.parquet",
    "fundednext": "titan/data/sources/mt5_brokers/fundednext/XAUUSD_H1.parquet",
    "icmarkets": "titan/data/sources/mt5_brokers/icmarkets/XAUUSD_H1.parquet",
    "fbs": "titan/data/sources/mt5_brokers/fbs/XAUUSD_H1.parquet",
}
BROKER_QUALITY = {"canonical":88,"exness":85,"icmarkets":88,"fundednext":80,"fbs":75}
BROKER_SPREAD_MULT = {"canonical":1.0,"exness":1.0,"icmarkets":0.85,"fundednext":1.15,"fbs":1.30}
YEARS = [2020, 2021, 2022, 2023, 2024, 2025]

COST_SCENARIOS = {
    "NORMAL_COST": {"spread":1.0,"slippage":1.0,"commission":1.0},
    "HIGH_SPREAD": {"spread":2.0,"slippage":1.5,"commission":1.0},
    "HIGH_SLIPPAGE": {"spread":1.2,"slippage":3.0,"commission":1.0},
    "LOW_LIQUIDITY": {"spread":1.8,"slippage":2.5,"commission":1.2},
    "WORST_BROKER": {"spread":2.5,"slippage":3.0,"commission":1.5},
    "HARSH_COMBINED": {"spread":3.0,"slippage":4.0,"commission":1.5},
}


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Generate trading signals using rule-based strategy (no ML)."""
    df = df.copy()
    df['ema_fast'] = df['close'].ewm(span=10, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=30, adjust=False).mean()
    df['tr'] = np.maximum(df['high']-df['low'],
                np.maximum(abs(df['high']-df['close'].shift(1)),
                           abs(df['low']-df['close'].shift(1))))
    df['atr'] = df['tr'].ewm(span=14, adjust=False).mean()
    delta = df['close'].diff()
    gain = delta.where(delta>0,0).ewm(span=14, adjust=False).mean()
    loss = (-delta.where(delta<0,0)).ewm(span=14, adjust=False).mean()
    rs = gain / loss.replace(0,1e-10)
    df['rsi'] = 100 - (100/(1+rs))
    df['signal'] = 0
    df.loc[(df['ema_fast']>df['ema_slow']) & (df['rsi']>50), 'signal'] = 1
    df.loc[(df['ema_fast']<df['ema_slow']) & (df['rsi']<50), 'signal'] = -1
    ema_sep = abs(df['ema_fast']-df['ema_slow']) / df['atr'].replace(0,1e-10)
    rsi_ext = abs(df['rsi']-50)/50
    df['meta_confidence'] = np.clip(0.5+0.3*ema_sep+0.2*rsi_ext, 0.0, 1.0)
    df['regime_confidence'] = np.clip(0.5+0.3*ema_sep, 0.0, 1.0)
    df['atr_percentile'] = df['atr'].rolling(252, min_periods=50).rank(pct=True)*100
    df['atr_percentile'] = df['atr_percentile'].fillna(50)
    df['regime_flip_probability'] = np.clip(1.0-(ema_sep/2.0), 0.05, 0.95).fillna(0.3)
    df['regime_label'] = df.get('regime', 'TREND_UP') if 'regime' in df.columns else 'TREND_UP'
    if 'spread_usd' in df.columns:
        df['spread_usd_val'] = df['spread_usd']
    elif 'spread' in df.columns:
        df['spread_usd_val'] = df['spread'] * 0.01
    else:
        df['spread_usd_val'] = 0.30
    hour = df.index.hour
    df['session'] = 'OFF'
    df.loc[(hour>=7)&(hour<12),'session'] = 'LONDON'
    df.loc[(hour>=12)&(hour<16),'session'] = 'OVERLAP'
    df.loc[(hour>=16)&(hour<21),'session'] = 'NY'
    df.loc[(hour>=0)&(hour<7),'session'] = 'ASIA'
    df['liquidity'] = 'NORMAL'
    df.loc[df['session'].isin(['LONDON','OVERLAP']),'liquidity'] = 'GOOD'
    df.loc[df['session'].isin(['ASIA','OFF']),'liquidity'] = 'POOR'
    return df


def simulate_trade(entry, exit_p, direction, lot, spread_usd, slippage_pips=2.0,
                   commission_per_lot=30.20, contract_size=100.0):
    if direction == 1:
        gross = (exit_p - entry) * contract_size * lot
    else:
        gross = (entry - exit_p) * contract_size * lot
    spread_cost = spread_usd * lot
    comm_cost = commission_per_lot * lot
    slip_cost = slippage_pips * 1.0 * lot / 0.01
    total_cost = spread_cost + comm_cost + slip_cost
    net = gross - total_cost
    risk_per_r = 10.0
    r_mult = gross / risk_per_r if risk_per_r > 0 else 0.0
    return {"gross_pnl":round(gross,4),"net_pnl":round(net,4),
            "spread_cost":round(spread_cost,4),"commission_cost":round(comm_cost,4),
            "slippage_cost":round(slip_cost,4),"total_cost":round(total_cost,4),
            "r_multiple":round(r_mult,4)}


def make_9932_engine(profile):
    engine = StressLossGovernanceEngine(profile)
    if profile == AccountProfile.PROP_FIRM_STRICT.value:
        engine.thresholds = {**engine.thresholds,
            "min_meta_confidence":0.70,"min_meta_confidence_block":0.70,
            "max_spread_usd":0.50,"max_spread_usd_block":0.50,
            "max_atr_percentile_block":92,"max_atr_percentile_throttle":80,
            "max_atr_percentile_warn":80,
            "meta_required_in_throttle_vol":0.75,"meta_required_in_warn_vol":0.75,
            "risk_multiplier_in_throttle_vol":0.50,"risk_multiplier_in_warn_vol":0.50,
            "max_regime_flip_prob":0.60,"max_regime_flip_prob_block":0.60,
            "min_account_health":60,"min_account_health_block":60,
            "min_broker_quality":70,"min_broker_quality_block":70,
            "cost_buffer_usd":999.0}
    return engine


def run_backtest(df, source, year, engine, profile, cost_scenario="NORMAL_COST",
                 lot=0.01, hold_bars=6):
    cm = COST_SCENARIOS.get(cost_scenario, COST_SCENARIOS["NORMAL_COST"])
    trades = []
    blocked = blocked_w = blocked_l = 0
    exit_counts = {}
    i = hold_bars
    while i < len(df) - hold_bars:
        row = df.iloc[i]
        signal = row['signal']
        if signal == 0:
            i += 1; continue
        direction = 1 if signal == 1 else -1
        entry = row['close']
        exit_row = df.iloc[i + hold_bars]
        exit_p = exit_row['close']
        spread = float(row['spread_usd_val']) * cm['spread']
        if spread <= 0: spread = 0.30 * cm['spread']
        pnl = simulate_trade(entry, exit_p, direction, lot, spread,
                             2.0*cm['slippage'], 30.20*cm['commission'])
        if engine is not None:
            inp = GovernanceInput(
                account_profile=profile,
                regime_label=str(row.get('regime_label','TREND_UP')),
                regime_confidence=float(row['regime_confidence']),
                meta_confidence=float(row['meta_confidence']),
                atr_percentile=float(row['atr_percentile']),
                volatility_state="HIGH" if float(row['atr_percentile'])>80 else "NORMAL",
                spread_usd=spread, slippage_pips=2.0*cm['slippage'],
                session=str(row.get('session','LONDON')),
                liquidity=str(row.get('liquidity','NORMAL')),
                account_health=90.0, equity_protection_active=False,
                capital_preservation_active=False,
                broker_quality=float(BROKER_QUALITY.get(source,80)),
                daily_dd_pct=0.5, daily_dd_threshold_pct=3.0,
                regime_flip_probability=float(row['regime_flip_probability']),
                rolling_setup_winrate=0.50, expected_edge_usd=pnl['net_pnl'])
            dec = engine.evaluate_entry(inp)
            if not dec.allow_trade:
                blocked += 1
                if pnl['net_pnl'] > 0: blocked_w += 1
                else: blocked_l += 1
                i += 1; continue
            risk_mult = dec.risk_multiplier
            pnl['net_pnl'] = round(pnl['net_pnl'] * risk_mult, 4)
            pnl['gross_pnl'] = round(pnl['gross_pnl'] * risk_mult, 4)
            # Management at peak
            hold_df = df.iloc[i:i+hold_bars+1]
            if direction == 1:
                mfe_r = (hold_df['high'].max() - entry) / 10.0
            else:
                mfe_r = (entry - hold_df['low'].min()) / 10.0
            mgmt_inp = GovernanceInput(**{**inp.__dict__,
                "open_trade_side":"BUY" if direction==1 else "SELL",
                "current_r_multiple":max(0,mfe_r),
                "mfe":max(0,mfe_r*10),"mae":0,"candles_in_trade":hold_bars})
            mgmt = engine.evaluate_management(mgmt_inp)
            if mgmt.exit_action != ExitAction.HOLD.value:
                exit_counts[mgmt.exit_action] = exit_counts.get(mgmt.exit_action, 0) + 1
                if mgmt.exit_action == ExitAction.MOVE_BE.value and pnl['net_pnl'] < 0:
                    pnl['net_pnl'] = 0.0; pnl['gross_pnl'] = 0.0
                elif mgmt.exit_action == ExitAction.PARTIAL_CLOSE.value and mfe_r > 0:
                    locked = 0.5 * (mfe_r * 10 * risk_mult)
                    remaining = 0.5 * pnl['net_pnl']
                    pnl['net_pnl'] = round(locked + remaining, 4)
                elif mgmt.exit_action == ExitAction.TIGHT_TRAIL.value and mfe_r > 0:
                    pnl['net_pnl'] = round(0.8 * (mfe_r * 10 * risk_mult), 4)
                elif mgmt.exit_action == ExitAction.CLOSE.value:
                    if mfe_r > 0:
                        pnl['net_pnl'] = round(mfe_r * 10 * risk_mult, 4)
                    elif pnl['net_pnl'] < -3:
                        pnl['net_pnl'] = -3.0
                elif mgmt.exit_action == ExitAction.REDUCE.value:
                    pnl['net_pnl'] = round(pnl['net_pnl'] * 0.5, 4)
        trades.append({
            "timestamp":str(df.index[i]),
            "direction":"BUY" if direction==1 else "SELL",
            "entry_price":float(entry),"exit_price":float(exit_p),
            "lot":lot,**pnl,"source":source,"year":year,
            "cost_scenario":cost_scenario,
            "month":str(df.index[i].strftime('%Y-%m')),
            "session":str(row.get('session','LONDON')),
            "regime":str(row.get('regime_label','TREND_UP')),
        })
        i += hold_bars
    return {"trades":trades,"blocked_count":blocked,
            "blocked_winners":blocked_w,"blocked_losers":blocked_l,
            "exit_counts":exit_counts}


def compute_metrics(trades, start_equity=10000.0):
    if not trades:
        return _empty()
    nets = [t['net_pnl'] for t in trades]
    grosses = [t['gross_pnl'] for t in trades]
    rs = [t['r_multiple'] for t in trades]
    total_net = sum(nets)
    total_gross = sum(grosses)
    wins = [t for t in trades if t['net_pnl']>0]
    losses = [t for t in trades if t['net_pnl']<0]
    gp = sum(t['net_pnl'] for t in wins)
    gl = abs(sum(t['net_pnl'] for t in losses))
    pf = gp/gl if gl > 0 else float('inf')
    wr = len(wins)/len(trades)*100
    avg_win = gp/len(wins) if wins else 0
    avg_loss = gl/len(losses) if losses else 0
    payoff = avg_win/avg_loss if avg_loss > 0 else float('inf')
    exp = total_net/len(trades)
    equity = start_equity; peak = start_equity
    max_dd = max_dd_pct = 0.0; daily_map = {}
    for t in trades:
        equity += t['net_pnl']
        if equity > peak: peak = equity
        dd = peak - equity
        if dd > max_dd: max_dd = dd
        ddp = (dd/peak*100) if peak > 0 else 0
        if ddp > max_dd_pct: max_dd_pct = ddp
        day = t['timestamp'][:10]
        daily_map[day] = daily_map.get(day, 0) + t['net_pnl']
    daily_pnls = list(daily_map.values())
    daily_dd_max = abs(min(daily_pnls)) if daily_pnls else 0
    sharpe = sortino = 0.0
    if len(nets) > 1:
        m = sum(nets)/len(nets); s = (sum((x-m)**2 for x in nets)/len(nets))**0.5
        if s > 0: sharpe = (m/s)*math.sqrt(len(nets))
        downside = [x for x in nets if x < 0]
        if downside:
            ds = (sum(x**2 for x in downside)/len(downside))**0.5
            if ds > 0: sortino = (m/ds)*math.sqrt(len(nets))
    calmar = (total_net/start_equity)/(max_dd/start_equity) if max_dd > 0 else (float('inf') if total_net > 0 else 0)
    recovery = total_net/max_dd if max_dd > 0 else float('inf')
    streak = cur = 0
    for t in trades:
        if t['net_pnl'] < 0: cur += 1; streak = max(streak, cur)
        else: cur = 0
    largest_loss = min(nets) if nets else 0
    largest_win = max(nets) if nets else 0
    mae_avg = sum(abs(min(0,r)) for r in rs)/len(rs)
    mfe_avg = sum(max(0,r) for r in rs)/len(rs)
    monthly = {}
    for t in trades:
        monthly[t['month']] = monthly.get(t['month'], 0) + t['net_pnl']
    # Lowest equity point
    running_sum = start_equity
    lowest_equity = start_equity
    for n in nets:
        running_sum += n
        if running_sum < lowest_equity:
            lowest_equity = running_sum
    return {"trade_count":len(trades),"total_net_pnl":round(total_net,2),
            "gross_profit":round(gp,2),"gross_loss":round(gl,2),
            "profit_factor":round(pf,4) if pf != float('inf') else "inf",
            "win_rate_pct":round(wr,2),"avg_win":round(avg_win,4),
            "avg_loss":round(avg_loss,4),
            "payoff_ratio":round(payoff,4) if payoff != float('inf') else "inf",
            "expectancy_per_trade":round(exp,4),
            "max_dd_usd":round(max_dd,2),"max_dd_pct":round(max_dd_pct,2),
            "daily_dd_max_usd":round(daily_dd_max,2),
            "sharpe":round(sharpe,4),"sortino":round(sortino,4),
            "calmar":round(calmar,4) if calmar == calmar and calmar != float('inf') else ("inf" if calmar == float('inf') else 0),
            "recovery_factor":round(recovery,4) if recovery != float('inf') else "inf",
            "longest_losing_streak":streak,
            "largest_single_loss":round(largest_loss,2),
            "largest_single_win":round(largest_win,2),
            "mae_avg":round(mae_avg,4),"mfe_avg":round(mfe_avg,4),
            "monthly_returns":{k:round(v,2) for k,v in sorted(monthly.items())},
            "profit_pct":round(total_net/start_equity*100,2),
            "lowest_equity":round(lowest_equity,2)}


def _empty():
    return {"trade_count":0,"total_net_pnl":0,"gross_profit":0,"gross_loss":0,
            "profit_factor":0,"win_rate_pct":0,"avg_win":0,"avg_loss":0,
            "payoff_ratio":0,"expectancy_per_trade":0,"max_dd_usd":0,"max_dd_pct":0,
            "daily_dd_max_usd":0,"sharpe":0,"sortino":0,"calmar":0,"recovery_factor":0,
            "longest_losing_streak":0,"largest_single_loss":0,"largest_single_win":0,
            "mae_avg":0,"mfe_avg":0,"monthly_returns":{},"profit_pct":0,"lowest_equity":10000}


def process_chunk(source, year, resume=True):
    """Process one source×year chunk. Saves checkpoint immediately."""
    chunk_file = CHUNK_DIR / f"{source}_H1_{year}.json"
    if resume and chunk_file.exists():
        return "skipped"

    path = REPO_ROOT / SOURCES[source]
    if not path.exists():
        return "no_file"

    df = pd.read_parquet(path)
    df_year = df[(df.index >= f"{year}-01-01") & (df.index < f"{year+1}-01-01")].copy()
    if len(df_year) < 100:
        return "too_few_rows"

    df_signals = generate_signals(df_year)

    configs = {
        "NO_GOVERNANCE": (None, None),
        "SPRINT_9_9_3_2_PROP_FIRM_STRICT": ("9932", AccountProfile.PROP_FIRM_STRICT.value),
        "SPRINT_9_9_3_3_RETAIL_SAFE": ("9933", AccountProfile.RETAIL_SAFE.value),
        "SPRINT_9_9_3_3_PROP_FIRM_STRICT": ("9933", AccountProfile.PROP_FIRM_STRICT.value),
        "SPRINT_9_9_3_3_INSTITUTIONAL": ("9933", AccountProfile.INSTITUTIONAL_CAPITAL_PROTECTION.value),
    }

    chunk_result = {
        "source": source, "year": year, "timeframe": "H1",
        "rows": len(df_year),
        "date_range": [str(df_year.index.min()), str(df_year.index.max())],
        "configs": {},
        "cost_stress": {},
    }

    # Main configs with NORMAL_COST
    for config_name, (version, profile) in configs.items():
        if version == "9932":
            engine = make_9932_engine(profile)
        elif version == "9933":
            engine = StressLossGovernanceEngine(profile)
        else:
            engine = None

        bt = run_backtest(df_signals, source, year, engine,
                          profile or AccountProfile.PROP_FIRM_STRICT.value,
                          "NORMAL_COST")
        metrics = compute_metrics(bt["trades"])
        # Add governance-specific metrics
        metrics["blocked_count"] = bt["blocked_count"]
        metrics["blocked_winners"] = bt["blocked_winners"]
        metrics["blocked_losers"] = bt["blocked_losers"]
        metrics["exit_counts"] = bt["exit_counts"]
        if engine is not None and bt["blocked_count"] > 0:
            avg_trade = abs(metrics["total_net_pnl"]) / max(1, metrics["trade_count"])
            metrics["missed_profit_est"] = round(bt["blocked_winners"] * avg_trade * 0.5, 2)
            metrics["avoided_loss_est"] = round(bt["blocked_losers"] * avg_trade * 0.5, 2)
            metrics["overfiltering_ratio"] = round(
                metrics["missed_profit_est"] / max(metrics["avoided_loss_est"], 0.01), 4)
        else:
            metrics["missed_profit_est"] = 0
            metrics["avoided_loss_est"] = 0
            metrics["overfiltering_ratio"] = 0

        # Funded target check (10% of $10K = $1000)
        metrics["funded_10pct_target_usd"] = 1000
        metrics["target_achieved"] = metrics["total_net_pnl"] >= 1000
        metrics["rule_breach"] = metrics["max_dd_pct"] > 10  # FTMO 10% total DD limit

        chunk_result["configs"][config_name] = metrics

    # Cost stress with PROP_FIRM_STRICT only
    prop_engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
    for cost_name in COST_SCENARIOS:
        bt = run_backtest(df_signals, source, year, prop_engine,
                          AccountProfile.PROP_FIRM_STRICT.value, cost_name)
        metrics = compute_metrics(bt["trades"])
        metrics["target_achieved"] = metrics["total_net_pnl"] >= 1000
        metrics["rule_breach"] = metrics["max_dd_pct"] > 10
        chunk_result["cost_stress"][cost_name] = metrics

    # Save checkpoint immediately
    with open(chunk_file, "w", encoding="utf-8") as f:
        json.dump(chunk_result, f, indent=2, default=str)

    return "completed"


def main():
    parser = argparse.ArgumentParser(description="Multi-year chunked validation")
    parser.add_argument("--source", type=str, default=None, help="Specific source")
    parser.add_argument("--year", type=int, default=None, help="Specific year")
    parser.add_argument("--max-chunks", type=int, default=None, help="Max chunks to process")
    parser.add_argument("--resume", action="store_true", default=True, help="Skip completed chunks")
    parser.add_argument("--no-resume", action="store_true", help="Re-process all chunks")
    args = parser.parse_args()

    if args.no_resume:
        args.resume = False

    sources_to_run = [args.source] if args.source else list(SOURCES.keys())
    years_to_run = [args.year] if args.year else YEARS

    chunks = [(s, y) for s in sources_to_run for y in years_to_run]
    if args.max_chunks:
        chunks = chunks[:args.max_chunks]

    print("="*78)
    print("  Sprint 9.9.3.8 Stages B+C+D: Chunked Validation")
    print("="*78)
    print(f"  Chunks to process: {len(chunks)}")
    print(f"  Resume: {args.resume}")
    print()

    completed = skipped = errors = 0
    for i, (source, year) in enumerate(chunks, 1):
        chunk_file = CHUNK_DIR / f"{source}_H1_{year}.json"
        if args.resume and chunk_file.exists():
            print(f"  [{i}/{len(chunks)}] {source} {year}: SKIP (already done)")
            skipped += 1
            continue

        print(f"  [{i}/{len(chunks)}] {source} {year}: ", end="", flush=True)
        try:
            result = process_chunk(source, year, args.resume)
            if result == "completed":
                # Read back the result for summary
                with open(chunk_file) as f:
                    data = json.load(f)
                prop = data["configs"].get("SPRINT_9_9_3_3_PROP_FIRM_STRICT", {})
                print(f"DONE — net=${prop.get('total_net_pnl',0)}, "
                      f"DD=${prop.get('max_dd_usd',0)}, "
                      f"PF={prop.get('profit_factor',0)}, "
                      f"trades={prop.get('trade_count',0)}")
                completed += 1
            elif result == "skipped":
                print("SKIP"); skipped += 1
            elif result == "no_file":
                print("NO FILE"); errors += 1
            elif result == "too_few_rows":
                print("TOO FEW ROWS"); errors += 1
        except Exception as e:
            print(f"ERROR: {e}")
            errors += 1

        sys.stdout.flush()

    print(f"\n  Completed: {completed}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")
    print(f"  Total: {len(chunks)}")


if __name__ == "__main__":
    main()
