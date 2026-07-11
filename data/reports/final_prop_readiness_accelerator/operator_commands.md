# Operator Commands (Sprint v2.8.7-M)

## Pull Latest

```cmd
cd "D:\Forex project\TITAN_XAU_AI"
myenv\Scripts\activate
git fetch origin
git pull --ff-only origin main
git rev-parse --short HEAD
git status --short
```

## Run Final Accelerator

```cmd
python scripts/research/run_final_prop_readiness_accelerator.py
```

## Run Exness Shadow Manually

```cmd
python scripts/operator/run_legacy_optimized_broker_shadow_readonly.py --broker exness --max-signals 300
```

## View Reports

```cmd
Get-Content data\reports\final_prop_readiness_accelerator\final_cto_prop_readiness_decision.md
Get-Content data\reports\final_prop_readiness_accelerator\exness_shadow_performance.md
Get-Content data\reports\final_prop_readiness_accelerator\exness_stress_test.md
Get-Content data\reports\final_prop_readiness_accelerator\operator_commands.md
```

## Safety

- NO live trading
- NO funded trading
- NO token creation
- NO order_send
- production_ready = False (always)
- Canonical CANNOT approve alone
- COMPETITION_DEMO_ONLY rejected for funded
- Supervised demo review is NOT automatic
- CTO must explicitly authorize
