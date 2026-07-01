# TITAN XAU AI - Prop Firm Readiness Audit

**Verdict:** **PROP_FIRM_BLOCKED**

**Design:** Every prop-firm profile is validated by PropFirmRuleEngine. Critical unknown rules fail closed for funded/live profiles. Simulation-only profiles (explicitly marked) may ship with unknown non-critical rules. Internal DD stops must sit below external prop-firm limits. The audit NEVER calls mt5.order_send and NEVER contains martingale/grid/averaging logic.

**Timestamp:** 2026-07-01T13:21:06.979198+00:00

**Head:** 396208a

**Profiles:** 14 (from `/home/z/my-project/TITAN_XAU_AI/config/prop_firm_profiles.yaml`)

## Per-profile verdicts

| Profile | Verdict | Unknown Critical | Blockers | Warnings |
|---|---|---|---|---|
| custom | PROP_RULES_BLOCKED | 1 | 1 | 2 |
| ftmo_challenge | PROP_RULES_BLOCKED | 1 | 1 | 2 |
| ftmo_funded | PROP_RULES_BLOCKED | 1 | 1 | 2 |
| ftmo_style_conservative | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| ftmo_verification | PROP_RULES_BLOCKED | 1 | 1 | 2 |
| fundednext_challenge | PROP_RULES_BLOCKED | 1 | 2 | 2 |
| fundednext_funded | PROP_RULES_BLOCKED | 1 | 2 | 2 |
| fundednext_style_conservative | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| generic_prop_100x_static_dd | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| generic_prop_100x_trailing_dd | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| institutional_internal_mandate | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| myfundedfx_challenge | PROP_RULES_BLOCKED | 1 | 1 | 2 |
| prop_aggressive_20pct_simulation_only | PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL | 0 | 0 | 2 |
| the5ers_challenge | PROP_RULES_BLOCKED | 1 | 2 | 2 |

## OK Checks

- PropFirmRuleEngine loaded 14 profiles from /home/z/my-project/TITAN_XAU_AI/config/prop_firm_profiles.yaml
- prop firm audit never calls mt5.order_send
- prop firm audit has no martingale/grid/averaging logic

## Warnings

- [ftmo_style_conservative] daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [ftmo_style_conservative] 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [fundednext_style_conservative] daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [fundednext_style_conservative] 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [generic_prop_100x_static_dd] daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [generic_prop_100x_static_dd] 3 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [generic_prop_100x_trailing_dd] daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [generic_prop_100x_trailing_dd] 3 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [institutional_internal_mandate] daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [institutional_internal_mandate] 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use
- [prop_aggressive_20pct_simulation_only] daily_dd_reset_time not declared — defaulting to 00:00 UTC
- [prop_aggressive_20pct_simulation_only] 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use

## Blockers

- **[custom] 1 unknown CRITICAL rule(s) on non-simulation profile — refusing to guess (fail-closed)**
- **[ftmo_challenge] 1 unknown CRITICAL rule(s) on non-simulation profile — refusing to guess (fail-closed)**
- **[ftmo_funded] 1 unknown CRITICAL rule(s) on non-simulation profile — refusing to guess (fail-closed)**
- **[ftmo_verification] 1 unknown CRITICAL rule(s) on non-simulation profile — refusing to guess (fail-closed)**
- **[fundednext_challenge] internal daily stop (daily_caution_pct=0.045) exceeds external daily DD cap (0.05 * 0.8333 = 0.0417)**
- **[fundednext_challenge] 1 unknown CRITICAL rule(s) on non-simulation profile — refusing to guess (fail-closed)**
- **[fundednext_funded] internal daily stop (daily_caution_pct=0.045) exceeds external daily DD cap (0.05 * 0.8333 = 0.0417)**
- **[fundednext_funded] 1 unknown CRITICAL rule(s) on non-simulation profile — refusing to guess (fail-closed)**
- **[myfundedfx_challenge] 1 unknown CRITICAL rule(s) on non-simulation profile — refusing to guess (fail-closed)**
- **[the5ers_challenge] internal daily stop (daily_caution_pct=0.035) exceeds external daily DD cap (0.04 * 0.8333 = 0.0333)**
- **[the5ers_challenge] 1 unknown CRITICAL rule(s) on non-simulation profile — refusing to guess (fail-closed)**

## Per-profile detail

### custom

- **Verdict:** PROP_RULES_BLOCKED
- **Unknown critical:** 1
- **Blockers:** 1
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Blockers:**
  - 1 unknown CRITICAL rule(s) on non-simulation profile — refusing to guess (fail-closed)

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### ftmo_challenge

- **Verdict:** PROP_RULES_BLOCKED
- **Unknown critical:** 1
- **Blockers:** 1
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Blockers:**
  - 1 unknown CRITICAL rule(s) on non-simulation profile — refusing to guess (fail-closed)

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### ftmo_funded

- **Verdict:** PROP_RULES_BLOCKED
- **Unknown critical:** 1
- **Blockers:** 1
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Blockers:**
  - 1 unknown CRITICAL rule(s) on non-simulation profile — refusing to guess (fail-closed)

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

- **Verdict:** PROP_RULES_BLOCKED
- **Unknown critical:** 1
- **Blockers:** 1
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Blockers:**
  - 1 unknown CRITICAL rule(s) on non-simulation profile — refusing to guess (fail-closed)

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### fundednext_challenge

- **Verdict:** PROP_RULES_BLOCKED
- **Unknown critical:** 1
- **Blockers:** 2
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Blockers:**
  - internal daily stop (daily_caution_pct=0.045) exceeds external daily DD cap (0.05 * 0.8333 = 0.0417)
  - 1 unknown CRITICAL rule(s) on non-simulation profile — refusing to guess (fail-closed)

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use

### fundednext_funded

- **Verdict:** PROP_RULES_BLOCKED
- **Unknown critical:** 1
- **Blockers:** 2
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Blockers:**
  - internal daily stop (daily_caution_pct=0.045) exceeds external daily DD cap (0.05 * 0.8333 = 0.0417)
  - 1 unknown CRITICAL rule(s) on non-simulation profile — refusing to guess (fail-closed)

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

- **Verdict:** PROP_RULES_BLOCKED
- **Unknown critical:** 1
- **Blockers:** 1
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Blockers:**
  - 1 unknown CRITICAL rule(s) on non-simulation profile — refusing to guess (fail-closed)

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

### the5ers_challenge

- **Verdict:** PROP_RULES_BLOCKED
- **Unknown critical:** 1
- **Blockers:** 2
- **Warnings:** 2
- **no_martingale / no_grid / no_averaging:** True / True / True

  **Blockers:**
  - internal daily stop (daily_caution_pct=0.035) exceeds external daily DD cap (0.04 * 0.8333 = 0.0333)
  - 1 unknown CRITICAL rule(s) on non-simulation profile — refusing to guess (fail-closed)

  **Warnings:**
  - daily_dd_reset_time not declared — defaulting to 00:00 UTC
  - 4 unknown NON-CRITICAL rule(s) — operator should resolve before live use


**The audit NEVER calls mt5.order_send and NEVER contains martingale/grid/averaging logic.**
