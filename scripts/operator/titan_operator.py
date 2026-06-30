#!/usr/bin/env python3
"""
TITAN XAU AI — Operator CLI (Sprint 9.9.3.35)
================================================

Safe Windows-friendly operator entrypoint for release-candidate checks,
reports, observation summaries, and safety status.

Usage:
    python scripts/operator/titan_operator.py status
    python scripts/operator/titan_operator.py rc-check
    python scripts/operator/titan_operator.py safety-check
    python scripts/operator/titan_operator.py broker-status
    python scripts/operator/titan_operator.py observation-report
    python scripts/operator/titan_operator.py daily-scorecard --since-hours 24
    python scripts/operator/titan_operator.py full-audit
    python scripts/operator/titan_operator.py help
    python scripts/operator/titan_operator.py status --json

NEVER imports MetaTrader5.
NEVER sends orders.
NEVER enables live trading.
"""
from __future__ import annotations
import argparse
import inspect
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.operator_control_console import (
    OperatorCommand, OperatorControlConsole, OperatorCommandResult,
)


VALID_COMMANDS = [c.value for c in OperatorCommand]


def _print_human(result: OperatorCommandResult) -> None:
    print("=" * 72)
    print(f"  TITAN XAU AI — Operator Console  |  command: {result.command}")
    print("=" * 72)
    print(f"  OK       : {result.ok}")
    print(f"  Verdict  : {result.verdict}")
    print(f"  Timestamp: {result.timestamp_utc}")
    print()
    print("  Message:")
    for line in result.message.splitlines():
        print(f"    {line}")
    print()
    if result.reports_generated:
        print("  Reports Generated:")
        for p in result.reports_generated:
            print(f"    - {p}")
        print()
    if result.blockers:
        print("  Blockers:")
        for b in result.blockers:
            print(f"    [!] {b}")
        print()
    if result.warnings:
        print("  Warnings:")
        for w in result.warnings:
            print(f"    [~] {w}")
        print()
    if result.next_steps:
        print("  Next Steps:")
        for s in result.next_steps:
            print(f"    -> {s}")
        print()
    print("=" * 72)


def main(argv: list[str] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="titan_operator",
        description="TITAN XAU AI operator control console CLI (safe, no live trading)",
    )
    parser.add_argument(
        "command",
        type=str,
        help=f"Operator command. One of: {', '.join(VALID_COMMANDS)}",
    )
    parser.add_argument(
        "--since-hours",
        type=int,
        default=24,
        help="Observation window in hours (default: 24). Used by observation-report/daily-scorecard.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output instead of human-readable text.",
    )
    args = parser.parse_args(argv)

    cmd_str = str(args.command).strip().lower()
    if cmd_str not in VALID_COMMANDS:
        print(f"ERROR: unknown command '{args.command}'.", file=sys.stderr)
        print(f"Valid commands: {', '.join(VALID_COMMANDS)}", file=sys.stderr)
        return 2

    cmd = OperatorCommand(cmd_str)
    console = OperatorControlConsole()

    # Some commands accept since_hours
    if cmd == OperatorCommand.OBSERVATION_REPORT:
        result = console.run_observation_report(since_hours=args.since_hours)
    elif cmd == OperatorCommand.DAILY_SCORECARD:
        result = console.run_daily_scorecard(since_hours=args.since_hours)
    else:
        result = console.execute(cmd)

    # Persist combined command report (the console also writes inside execute(),
    # but for observation-report/daily-scorecard we called the runner directly,
    # so we re-issue a write to capture the result).
    try:
        console._write_command_report(result)
    except Exception:
        pass

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, default=str, ensure_ascii=False))
    else:
        _print_human(result)

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
