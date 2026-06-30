# TITAN XAU AI - Demo Micro Execution Safety Design (Sprint 9.9.3.43)

## Purpose

This document defines the safety design for future controlled demo micro
execution. **This sprint does NOT implement order execution.** It only
defines the rules that must be followed when a future separately approved
sprint implements demo micro execution.

## Future Execution Rules

1. **Separate sprint required before any order.** A dedicated sprint must
   be explicitly approved before any demo micro order execution is
   implemented.

2. **Explicit operator command required.** No automatic execution. The
   operator must explicitly run a command to execute a demo micro trade.

3. **MetaQuotes-Demo only.** No other broker may be used for demo micro
   execution until it passes compatibility verification.

4. **No real account.** Demo accounts only. No real money.

5. **Max lot 0.01.** Hard cap. Cannot be increased.

6. **Max one open position.** Hard cap. Cannot be increased.

7. **Immediate kill switch available.** The operator must have immediate
   access to a kill switch that stops all trading.

8. **Force-close plan required.** Before execution, the operator must have
   a force-close plan to close any open position.

9. **Session timeout required.** The execution session must have a timeout
   that automatically stops trading after a configured period.

10. **Daily loss guard required.** If daily loss exceeds the configured
    limit, all trading must stop immediately.

11. **No martingale.** Never increase lot after a loss.

12. **No averaging.** Never add to a losing position.

13. **No grid.** Never place multiple orders at different price levels.

14. **No duplicate orders.** Never send the same order twice.

15. **No overnight/weekend hold** unless explicitly allowed in a future
    approved sprint.

16. **Library/dependency drift must block or warn** before execution. If
    the dependency compatibility audit returns BLOCKED, execution must be
    refused. If it returns READY_WITH_WARNINGS, the operator must
    acknowledge the warnings before execution.

17. **Model artifact warnings must be acknowledged.** If the model artifact
    compatibility audit returns READY_WITH_WARNINGS, the operator must
    acknowledge the warnings before execution.

18. **No commercial/live/world-class claim.** Demo micro execution does
    NOT prove commercial readiness, live readiness, or world no.1.

## What This Sprint Does

This sprint adds:
- Dependency compatibility audit
- Environment lock report
- Model artifact compatibility audit
- Runtime self-healing audit
- Demo micro readiness controller
- Safety design document (this file)

## What This Sprint Does NOT Do

This sprint does NOT:
- Execute any orders
- Send any MT5 commands
- Enable live trading
- Create model artifacts
- Retrain models
- Run HPO
- Claim crash is impossible

## Correct Wording

The system is a **crash-tolerant fail-closed runtime with bounded
recovery**. It is NOT "crash-proof" or "crash impossible."

## Live Trading

**Live trading remains BLOCKED.** There is no path in this sprint by
which live trading can be enabled.
