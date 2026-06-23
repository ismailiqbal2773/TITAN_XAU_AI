# -*- mode: python ; coding: utf-8 -*-
# TITAN XAU AI — PyInstaller Spec (Sprint 7.5)
# Build: pyinstaller TITAN.spec
# Output: dist/TITAN.exe

import os
import sys
from pathlib import Path

block_cipher = None

# Project root (parent of this spec file)
PROJECT_ROOT = Path(SPECPATH).resolve()

a = Analysis(
    [str(PROJECT_ROOT / 'titan_launcher.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # Bundle config templates
        ('config/runtime.yaml', 'config'),
        # Bundle model files
        ('titan/data/models/xgboost_v1.pkl', 'titan/data/models'),
        ('titan/data/models/meta_label_v2_context.pkl', 'titan/data/models'),
        ('titan/data/models/xgboost_v2_micro.pkl', 'titan/data/models'),
        ('titan/data/models/lstm_v1.pt', 'titan/data/models'),
        ('titan/data/models/transformer_v1.pt', 'titan/data/models'),
        ('titan/data/models/lightgbm_v1.pkl', 'titan/data/models'),
        ('titan/data/models/logreg_v1_price.pkl', 'titan/data/models'),
        ('titan/data/models/meta_label_v1.pkl', 'titan/data/models'),
        # Bundle canonical data
        ('titan/data/canonical/XAUUSD_H1_canonical.parquet', 'titan/data/canonical'),
        # Bundle HPO params
        ('titan/data/hpo/best_params_xgb.json', 'titan/data/hpo'),
        ('titan/data/hpo/best_params_lgbm.json', 'titan/data/hpo'),
        ('titan/data/hpo/best_params_lstm.json', 'titan/data/hpo'),
        ('titan/data/hpo/best_params_transformer.json', 'titan/data/hpo'),
        # Bundle documentation
        ('docs/USER_GUIDE.md', 'docs'),
        ('docs/DEMO_RUNBOOK.md', 'docs'),
        # Bundle monitoring specs
        ('monitoring/dashboard_spec.json', 'monitoring'),
        ('monitoring/forward_test_dashboard.json', 'monitoring'),
    ],
    hiddenimports=[
        'xgboost',
        'sklearn',
        'sklearn.linear_model',
        'pandas',
        'numpy',
        'yaml',
        'structlog',
        'aiosqlite',
        'pyarrow',
        'MetaTrader5',
        'titan.production',
        'titan.production.feature_stream',
        'titan.production.model_loader',
        'titan.production.inference',
        'titan.production.trade_loop',
        'titan.production.position_sync',
        'titan.production.cold_start',
        'titan.production.exit_manager',
        'titan.production.order_modifier',
        'titan.production.trade_journal',
        'titan.production.kill_switch_fsm',
        'titan.production.news_filter',
        'titan.production.slippage_monitor',
        'titan.production.drift_monitor',
        'titan.production.watchdog_restarter',
        'titan.forward_test',
        'titan.forward_test.forward_test_manager',
        'titan.forward_test.metrics_collector',
        'titan.forward_test.report_generator',
        'titan.forward_test.mt5_demo_adapter',
        'titan.forward_test.runtime_health',
        'titan.runtime.launcher',
        'titan.setup.mt5_validator',
        'titan.setup.setup_wizard',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',  # Not needed at runtime
        'pytest',
        'torch',       # Not needed for inference (XGBoost only)
        'onnxruntime', # Not needed (using sklearn/xgboost directly)
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TITAN',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Set to False for GUI-only mode (future)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon='titan.ico' when icon is created
)
