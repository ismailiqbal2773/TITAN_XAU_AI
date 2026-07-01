# TITAN XAU AI - Prop Firm Readiness Audit

**Verdict:** **PROP_FIRM_NEEDS_WORK**

**Design:** Every prop-firm profile is validated by PropFirmRuleEngine. Critical unknown rules fail closed for funded/live profiles. Simulation-only profiles (explicitly marked) may ship with unknown non-critical rules. Internal DD stops must sit below external prop-firm limits. The audit NEVER calls mt5.order_send and NEVER contains martingale/grid/averaging logic.

**Timestamp:** 2026-07-01T15:41:00.877641+00:00

**Head:** 1454334

**Profiles:** 18 (from `/home/z/my-project/TITAN_XAU_AI/config/prop_firm_profiles.yaml`)

## Per-profile verdicts

| Profile | Verdict | Unknown Critical | Blockers | Warnings |
|---|---|---|---|---|
| custom | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| ftmo_challenge | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| ftmo_funded | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| ftmo_style_conservative | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| ftmo_verification | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| funded_conservative_generic | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 1 |
| fundednext_challenge | PROP_RULES_BLOCKED | 0 | 1 | 2 |
| fundednext_funded | PROP_RULES_BLOCKED | 0 | 1 | 2 |
| fundednext_style_conservative | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| generic_prop_100x_static_dd | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| generic_prop_100x_trailing_dd | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| institutional_internal_mandate | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| myfundedfx_challenge | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| prop_aggressive_20pct_simulation_only | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| prop_funded_aggressive_20pct_simulation | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| prop_funded_growth | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| prop_funded_safe | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| the5ers_challenge | PROP_RULES_BLOCKED | 0 | 1 | 2 |

## OK Checks

- PropFirmRuleEngine loaded 18 profiles from /home/z/my-project/TITAN_XAU_AI/config/prop_firm_profiles.yaml
- prop firm audit never calls mt5.order_send
- prop firm audit has no martingale/grid/averaging logic

## Warnings

- [custom] LEGACY: daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [custom] LEGACY: 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [ftmo_challenge] LEGACY: daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [ftmo_challenge] LEGACY: 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [ftmo_funded] LEGACY: daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [ftmo_funded] LEGACY: 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [ftmo_style_conservative] daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [ftmo_style_conservative] 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [ftmo_verification] LEGACY: daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [ftmo_verification] LEGACY: 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [funded_conservative_generic] 3 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [fundednext_challenge] LEGACY_REVIEW: internal daily stop (daily_caution_pct=0.045) exceeds external daily DD cap (0.05 * 0.8333 = 0.0417)
- [fundednext_funded] LEGACY_REVIEW: internal daily stop (daily_caution_pct=0.045) exceeds external daily DD cap (0.05 * 0.8333 = 0.0417)
- [fundednext_style_conservative] daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [fundednext_style_conservative] 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [generic_prop_100x_static_dd] daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [generic_prop_100x_static_dd] 3 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [generic_prop_100x_trailing_dd] LEGACY: daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [generic_prop_100x_trailing_dd] LEGACY: 3 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [institutional_internal_mandate] LEGACY: daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [institutional_internal_mandate] LEGACY: 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [myfundedfx_challenge] LEGACY: daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [myfundedfx_challenge] LEGACY: 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [prop_aggressive_20pct_simulation_only] daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [prop_aggressive_20pct_simulation_only] 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [prop_funded_aggressive_20pct_simulation] daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [prop_funded_aggressive_20pct_simulation] 3 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [prop_funded_growth] daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [prop_funded_growth] 3 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [prop_funded_safe] daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [prop_funded_safe] 3 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [the5ers_challenge] LEGACY_REVIEW: internal daily stop (daily_caution_pct=0.035) exceeds external daily DD cap (0.04 * 0.8333 = 0.0333)

## Per-profile detail

### custom

- **Verdict:** PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
- **Unknown critical:** 0
- **Blockers:** 0
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### ftmo_challenge

- **Verdict:** PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
- **Unknown critical:** 0
- **Blockers:** 0
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### ftmo_funded

- **Verdict:** PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
- **Unknown critical:** 0
- **Blockers:** 0
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### ftmo_style_conservative

- **Verdict:** PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
- **Unknown critical:** 0
- **Blockers:** 0
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### ftmo_verification

- **Verdict:** PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
- **Unknown critical:** 0
- **Blockers:** 0
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### funded_conservative_generic

- **Verdict:** PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
- **Unknown critical:** 0
- **Blockers:** 0
- **Warnings:** 1
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Warnings:**
  - 3 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### fundednext_challenge

- **Verdict:** PROP_RULES_BLOCKED
- **Unknown critical:** 0
- **Blockers:** 1
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Blockers:**
  - internal daily stop (daily_caution_pct=0.045) exceeds external daily DD cap (0.05 * 0.8333 = 0.0417)

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### fundednext_funded

- **Verdict:** PROP_RULES_BLOCKED
- **Unknown critical:** 0
- **Blockers:** 1
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Blockers:**
  - internal daily stop (daily_caution_pct=0.045) exceeds external daily DD cap (0.05 * 0.8333 = 0.0417)

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### fundednext_style_conservative

- **Verdict:** PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
- **Unknown critical:** 0
- **Blockers:** 0
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### generic_prop_100x_static_dd

- **Verdict:** PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
- **Unknown critical:** 0
- **Blockers:** 0
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 3 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### generic_prop_100x_trailing_dd

- **Verdict:** PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
- **Unknown critical:** 0
- **Blockers:** 0
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 3 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### institutional_internal_mandate

- **Verdict:** PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
- **Unknown critical:** 0
- **Blockers:** 0
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### myfundedfx_challenge

- **Verdict:** PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
- **Unknown critical:** 0
- **Blockers:** 0
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### prop_aggressive_20pct_simulation_only

- **Verdict:** PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
- **Unknown critical:** 0
- **Blockers:** 0
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### prop_funded_aggressive_20pct_simulation

- **Verdict:** PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
- **Unknown critical:** 0
- **Blockers:** 0
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 3 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### prop_funded_growth

- **Verdict:** PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
- **Unknown critical:** 0
- **Blockers:** 0
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 3 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### prop_funded_safe

- **Verdict:** PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
- **Unknown critical:** 0
- **Blockers:** 0
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 3 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### the5ers_challenge

- **Verdict:** PROP_RULES_BLOCKED
- **Unknown critical:** 0
- **Blockers:** 1
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Blockers:**
  - internal daily stop (daily_caution_pct=0.035) exceeds external daily DD cap (0.04 * 0.8333 = 0.0333)

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use


**The audit NEVER calls mt5.order_send and NEVER contains martingale/grid/averaging logic.**
