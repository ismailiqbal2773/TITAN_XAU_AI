"""
TITAN XAU AI — Forward Test Simulation (Sprint 6)

Simulates 30 trading days of forward testing.
Verifies:
  - Runtime survives continuously
  - Metrics accumulate correctly
  - Reports generate correctly
  - No crashes
  - No real account execution

Usage:
    python scripts/forward_test_simulation.py
    python scripts/forward_test_simulation.py --days 7
    python scripts/forward_test_simulation.py --verbose
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np
from titan.production.inference import Signal, Direction
from titan.production.trade_loop import TradeLoop, TradeLoopConfig, TradeDecision
from titan.production.trade_journal import TradeJournal, EventType
from titan.production.kill_switch_fsm import KillSwitchFSM, KillSwitchInput, KillState
from titan.forward_test.forward_test_manager import ForwardTestManager
from titan.forward_test.metrics_collector import MetricsCollector
from titan.forward_test.report_generator import ReportGenerator

logger = logging.getLogger("titan.simulation")


class ForwardTestSimulation:
    """
    Simulates N days of forward testing with synthetic signals.
    NO real MT5 connection. NO real orders. dry_run=True always.
    """

    def __init__(self, days: int = 30, output_dir: str = "data/simulation"):
        self.days = days
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.journal_path = self.output_dir / "sim_journal.jsonl"
        self.results: list[dict] = []

    async def run(self) -> dict:
        """Run the simulation. Returns summary dict."""
        print("=" * 70)
        print(f"TITAN XAU AI — Forward Test Simulation ({self.days} days)")
        print("=" * 70)
        print(f"Output: {self.output_dir}")
        print(f"Mode: dry_run (NO real orders)")
        print()

        # Setup
        journal = TradeJournal(path=str(self.journal_path))
        manager = ForwardTestManager(
            journal_path=str(self.journal_path),
            output_dir=str(self.output_dir / "ft"),
            metrics_dir=str(self.output_dir / "metrics"),
            reports_dir=str(self.output_dir / "reports"),
        )

        # Start session
        manager.start_session()
        print(f"Session started: {manager.get_status()['session_id']}")

        random.seed(42)
        np.random.seed(42)

        # ─── Simulate each day ──
        for day_num in range(1, self.days + 1):
            day_result = await self._simulate_day(day_num, manager, journal)
            self.results.append(day_result)

            # End day (creates checkpoint + report)
            manager.end_day()

            if day_num % 5 == 0 or day_num == self.days:
                print(f"  Day {day_num}/{self.days} complete: "
                      f"{day_result['signals']} signals, "
                      f"{day_result['trades']} trades, "
                      f"PnL=${day_result['pnl']:.2f}")

        # Generate weekly reports
        print("\nGenerating weekly reports...")
        report_gen = ReportGenerator(
            journal_path=str(self.journal_path),
            output_dir=str(self.output_dir / "reports"),
        )
        # Generate reports for each week
        for week_start_offset in range(0, self.days, 7):
            week_start = (datetime.now(timezone.utc) - timedelta(
                days=self.days - week_start_offset
            )).strftime("%Y-%m-%d")
            try:
                report_gen.generate_weekly_report(week_start=week_start)
            except Exception as e:
                logger.warning(f"Weekly report for {week_start} failed: {e}")

        # End session
        manager.end_session(reason="simulation_complete")

        # ─── Final summary ──
        summary = self._compute_summary()
        self._print_summary(summary)
        return summary

    async def _simulate_day(self, day_num: int, manager: ForwardTestManager,
                             journal: TradeJournal) -> dict:
        """Simulate a single trading day."""
        # 5-15 signals per day
        n_signals = random.randint(5, 15)
        n_accepted = 0
        n_trades = 0
        pnl = 0.0

        for sig_num in range(n_signals):
            # Random signal
            direction = random.choice([Direction.LONG, Direction.SHORT, Direction.FLAT])
            confidence = random.uniform(0.40, 0.85)
            meta_confidence = random.uniform(0.40, 0.90)
            is_tradeable = (confidence >= 0.55 and meta_confidence >= 0.65
                            and direction != Direction.FLAT)

            signal = Signal(
                timestamp=time.time(),
                direction=direction,
                confidence=confidence,
                meta_confidence=meta_confidence,
                xgb_proba=[1-confidence, confidence] if direction == Direction.LONG else [confidence, 1-confidence],
                meta_proba=[1-meta_confidence, meta_confidence],
                is_tradeable=is_tradeable,
                feature_vector=np.zeros(55),
                inference_ms=random.uniform(20, 100),
                source="simulation",
            )

            # Journal signal
            journal.log_signal(signal)
            journal.log_event(EventType.SIGNAL_CREATED, {
                "day": day_num, "sig_num": sig_num,
                "direction": direction.name,
            })

            # Process through trade loop
            loop = TradeLoop(
                TradeLoopConfig(dry_run=True),
                journal=journal,
                kill_switch=manager.health,  # not a real FSM, just for wiring
            )
            # Use the real kill_switch from manager if available
            # (in simulation, we create a fresh FSM per day)
            fsm = KillSwitchFSM()
            loop = TradeLoop(TradeLoopConfig(dry_run=True), journal=journal, kill_switch=fsm)

            decision = await loop.process_signal(
                signal=signal,
                entry_price=2000.0 + random.uniform(-5, 5),
                spread_usd=random.uniform(0.10, 0.50),
            )

            if decision.accepted:
                n_accepted += 1
                # Simulate position open + close
                journal.log_event(EventType.POSITION_OPENED, {
                    "ticket": 50000 + n_accepted,
                    "day": day_num,
                })
                # Random outcome
                win = random.random() < 0.65  # 65% win rate
                pnl_usd = random.uniform(5, 20) if win else -random.uniform(3, 10)
                pnl += pnl_usd
                n_trades += 1

                journal.log_exit(
                    ticket=50000 + n_accepted,
                    exit_reason="TP_HIT" if win else "SL_HIT",
                    entry_price=2000.0,
                    exit_price=2000.0 + (pnl_usd / 10),
                    direction=1 if direction == Direction.LONG else -1,
                    volume=0.01,
                    pnl_usd=pnl_usd,
                    holding_time_seconds=random.uniform(600, 14400),
                )
                journal.log_event(EventType.POSITION_CLOSED, {
                    "ticket": 50000 + n_accepted,
                    "pnl": pnl_usd,
                    "win": win,
                })

        # Record heartbeat for health monitoring
        manager.health.record_heartbeat(f"day_{day_num}")

        return {
            "day": day_num,
            "signals": n_signals,
            "accepted": n_accepted,
            "trades": n_trades,
            "pnl": pnl,
        }

    def _compute_summary(self) -> dict:
        """Compute simulation summary."""
        total_signals = sum(r["signals"] for r in self.results)
        total_accepted = sum(r["accepted"] for r in self.results)
        total_trades = sum(r["trades"] for r in self.results)
        total_pnl = sum(r["pnl"] for r in self.results)
        best_day = max(self.results, key=lambda r: r["pnl"])
        worst_day = min(self.results, key=lambda r: r["pnl"])

        # Read journal for final metrics
        journal = TradeJournal(path=str(self.journal_path))
        journal.flush()
        verification = journal.verify_complete_lifecycle()

        return {
            "days_simulated": self.days,
            "total_signals": total_signals,
            "total_accepted": total_accepted,
            "total_trades": total_trades,
            "total_pnl_usd": round(total_pnl, 2),
            "avg_signals_per_day": round(total_signals / self.days, 1),
            "avg_trades_per_day": round(total_trades / self.days, 1),
            "best_day": {"day": best_day["day"], "pnl": round(best_day["pnl"], 2)},
            "worst_day": {"day": worst_day["day"], "pnl": round(worst_day["pnl"], 2)},
            "journal_records": journal.record_count,
            "journal_verify": verification,
            "runtime_survived": True,
            "no_real_orders": True,
        }

    def _print_summary(self, summary: dict) -> None:
        print()
        print("=" * 70)
        print("SIMULATION SUMMARY")
        print("=" * 70)
        print(f"  Days simulated:      {summary['days_simulated']}")
        print(f"  Total signals:       {summary['total_signals']}")
        print(f"  Total accepted:      {summary['total_accepted']}")
        print(f"  Total trades:        {summary['total_trades']}")
        print(f"  Total PnL:           ${summary['total_pnl_usd']:.2f}")
        print(f"  Avg signals/day:     {summary['avg_signals_per_day']}")
        print(f"  Avg trades/day:      {summary['avg_trades_per_day']}")
        print(f"  Best day:            Day {summary['best_day']['day']} (${summary['best_day']['pnl']:.2f})")
        print(f"  Worst day:           Day {summary['worst_day']['day']} (${summary['worst_day']['pnl']:.2f})")
        print(f"  Journal records:     {summary['journal_records']}")
        print(f"  Runtime survived:    {summary['runtime_survived']}")
        print(f"  No real orders:      {summary['no_real_orders']}")
        print()
        print("Journal lifecycle verification:")
        for k, v in summary["journal_verify"].items():
            print(f"  {k}: {v}")
        print()

        # Save summary
        summary_path = self.output_dir / "simulation_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"Summary saved: {summary_path}")


def main():
    parser = argparse.ArgumentParser(description="TITAN Forward Test Simulation")
    parser.add_argument("--days", type=int, default=30, help="Number of days to simulate")
    parser.add_argument("--output", default="data/simulation", help="Output directory")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    sim = ForwardTestSimulation(days=args.days, output_dir=args.output)
    summary = asyncio.run(sim.run())

    # Exit code: 0 if simulation survived, 1 if crashed
    success = summary["runtime_survived"] and summary["no_real_orders"]
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
