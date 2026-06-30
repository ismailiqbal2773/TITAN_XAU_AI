# TITAN XAU AI — Demo Micro Execution Registry

**Last Updated:** 2026-06-29
**Safety:** No raw account evidence committed. All account identifiers redacted.
**Live Trading:** Disabled (dry_run=true, live_trading=false)

---

## MetaQuotes-Demo

| Field | Value |
|---|---|
| Server | MetaQuotes-Demo |
| Account Type | DEMO |
| Raw Probe | PASS |
| Raw Probe Open Retcode | 10009 |
| Raw Probe Close Retcode | 10009 |
| Demo Micro Full-Cycle | PASS |
| Repeatability (3-cycle) | PASS |
| Cycles Passed | 3/3 |
| Cycles Failed | 0 |
| Final Open Positions | 0 |
| Preferred Filling | IOC (naked open + SLTP modify) |
| Status | VERIFIED_FOR_DEMO_MICRO |
| Priority | HIGH |
| Executed By | Operator (local Windows MT5) |
| Z AI Executed | NO |

**Notes:**
- Raw MT5 probe succeeded with naked IOC order (sl=0, tp=0).
- SLTP modify applied after open via TRADE_ACTION_SLTP.
- Force close succeeded after 60s hold per cycle.
- 3 cycles (BUY, SELL, BUY) all passed with 0 open positions remaining.
- Account login/name/balance redacted — no raw evidence committed.

---

## FBS-Demo

| Field | Value |
|---|---|
| Server | FBS-Demo |
| Account Type | DEMO |
| Status | REJECTED |
| Known Retcode | 10006 (TRADE_RETCODE_REJECT) |
| Behavior | Rejects both protected and naked FOK orders |
| Priority | LOW |

**Notes:**
- FBS DEMO rejected all order_send attempts despite passing hard gate checks.
- Broker compatibility fallback (naked + SLTP modify) also rejected.
- Low priority — may require broker-specific configuration.

---

## FundedNext Free Trial

| Field | Value |
|---|---|
| Server | FundedNext Free Trial |
| Account Type | DEMO |
| Status | DO_NOT_USE |
| Reason | EA/Python automation not allowed on Free Trial |
| Priority | BLOCKED |

**Notes:**
- FundedNext support confirmed: Free Trial accounts do not allow EA/Python automated trading.
- Must upgrade to paid FundedNext account for automation support.
- **DO NOT USE.**

---

## Exness Demo

| Field | Value |
|---|---|
| Server | Exness Demo |
| Status | PENDING |
| Priority | MEDIUM |

**Notes:** Not yet tested. Run raw_mt5_probe.py to verify.

---

## ICMarkets Demo

| Field | Value |
|---|---|
| Server | ICMarkets Demo |
| Status | PENDING |
| Priority | MEDIUM |

**Notes:** Not yet tested. Run raw_mt5_probe.py to verify.

---

## Safety & Privacy

- No raw pass_evidence folder committed to repository
- No raw_mt5_working_profile.json committed
- No demo_micro_journal.jsonl committed
- No broker_execution_profile.json committed
- Account login/name/balance/equity redacted in all committed reports
- Local Windows paths redacted
- Execution evidence is local/operator-run only
- Live trading remains disabled (dry_run=true, live_trading=false)
