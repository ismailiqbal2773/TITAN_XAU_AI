# TITAN XAU AI — Pre-Demo Logic Validation Report

> Generated: 2026-06-23T10:24:15.426356+00:00
> Git: 22a9298
> Checks: 34 | Passed: 33 | Failed: 1 | Blockers: 0

## Decision: PASS

## Sections
- 1_static: 3/3
- 2_runtime: 5/5
- 3_schema: 4/4
- 4_config: 7/7
- 5_state: 7/7
- 6_dry_run: 7/8

## Details
- ✓ [BLOCKER] All 24 critical modules import: 24 checked
- ✓ [BLOCKER] All 6 critical functions have callers: All found
- ✓ [BLOCKER] All .py files compile (syntax): All compile
- ✓ [BLOCKER] Launcher.start(autonomous=True) exists: sig=(self, autonomous: 'bool' = False) -> 'None'
- ✓ [BLOCKER] AutonomousRuntime has all 5 loops: All 5 present
- ✓ [BLOCKER] Inference chain: features→XGB→meta→Signal: dir=FLAT
- ✓ [BLOCKER] TradeLoop wired to KillSwitchFSM: ks=KillSwitchFSM
- ✓ [BLOCKER] AutonomousRuntime initializes all 9 components: All 9 init
- ✓ [BLOCKER] Feature stream count matches XGBoost: stream=55, xgb=55
- ✓ [BLOCKER] Meta-label feature count matches: meta=22, actual=22
- ✓ [BLOCKER] No NaN/Inf in feature vector: NaN=False, Inf=False
- ✓ [BLOCKER] Meta features subset of XGB features: All subset
- ✓ [BLOCKER] dry_run defaults True: dry_run=True
- ✓ [BLOCKER] live_trading defaults False: live_trading=False
- ✓ [BLOCKER] max_lot <= 0.01: max_lot=0.01
- ✓ [BLOCKER] max_open_positions <= 1: max_pos=1
- ✓ [HIGH] watchdog.dry_run is True: wd.dry_run=True
- ✓ [BLOCKER] XGB model path exists: /home/z/my-project/TITAN_XAU_AI/titan/data/models/xgboost_v1.pkl
- ✓ [BLOCKER] Meta-label model path exists: /home/z/my-project/TITAN_XAU_AI/titan/data/models/meta_label_v2_context.pkl
- ✓ [BLOCKER] One-way escalation (no downgrade): state=HALT_NEW_TRADES
- ✓ [BLOCKER] HALT blocks new trades: allows=False
- ✓ [BLOCKER] EMERGENCY requires flatten: flatten=True
- ✓ [HIGH] CAUTION allows trades: allows=True
- ✓ [HIGH] Reset → NORMAL: state=NORMAL
- ✓ [BLOCKER] Drift emergency → EMERGENCY_STOP: state=EMERGENCY_STOP
- ✓ [BLOCKER] ECE kill → HALT: state=HALT_NEW_TRADES
- ✓ [BLOCKER] TradeLoopConfig.dry_run=True: OK
- ✓ [BLOCKER] OrderModifier.dry_run=True: OK
- ✓ [BLOCKER] WatchdogRestarter.dry_run=True: OK
- ✓ [BLOCKER] LauncherConfig.dry_run=True: OK
- ✓ [BLOCKER] LauncherConfig.live_trading=False: OK
- ✓ [BLOCKER] Live requires TITAN_LIVE_TRADING=1: raises=True
- ✓ [BLOCKER] dry_run order_result=None: None=True
- ✗ [HIGH] No unguarded mt5.order_send in trade path: UNGUARDED!