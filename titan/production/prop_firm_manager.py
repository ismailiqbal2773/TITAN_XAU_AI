"""
TITAN XAU AI — PropFirmProfileManager (Sprint 9.0)
====================================================

Institutional prop-firm adaptive risk layer.

Loads prop-firm-specific risk profiles from config/prop_firm_profiles.yaml
and exposes them to KillSwitchFSM, TradeLoop, RiskEngine, NewsFilter,
PositionSync, and ChallengeScorecard.

Safety invariants (HARD — cannot be overridden at runtime):
  1. Profile max_lot can only DECREASE risk. The hard-coded trade_loop
     MAX_LOT_CAP = 0.01 always wins; profile max_lot is min(profile, cap).
  2. Profile NEVER changes dry_run / live_trading flags.
  3. Profile NEVER changes models, thresholds, or ATR formulas.
  4. Profile NEVER auto-applies from MT5 auto-detection — suggestion only.
  5. If prop_firm.enabled=true but profile is missing/unknown → REFUSE to start.
  6. All profile decisions are journaled via EventType.PROFILE_* events.

Usage:
    mgr = PropFirmProfileManager(
        profiles_path="config/prop_firm_profiles.yaml",
        journal=journal,
    )
    mgr.load_profile("ftmo_challenge")   # explicit manual load
    mgr.lock()                            # lock for challenge duration
    profile = mgr.active_profile          # FirmProfile dataclass
    mgr.auto_detect(mt5_account_info)     # suggest only, does not apply
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Any

import yaml

from titan.production.trade_journal import TradeJournal, EventType

logger = logging.getLogger(__name__)


# ─── Hard safety caps (mirror titan/production/trade_loop.py) ─────────────────
HARD_MAX_LOT_CAP = 0.01              # Institutional hard cap — profile cannot exceed
HARD_MAX_OPEN_POSITIONS = 1          # One position at a time


# ─── Enums (mirror titan/compliance/profiles.py to avoid cross-module dep) ────
class DrawdownMode:
    STATIC = "static"
    TRAILING = "trailing"
    HYBRID = "hybrid"


class DailyLossMode:
    BALANCE_BASED = "balance_based"
    PEAK_EQUITY_BASED = "peak_equity_based"


class Phase:
    CHALLENGE = "challenge"
    VERIFICATION = "verification"
    FUNDED = "funded"


# ─── Profile dataclass ────────────────────────────────────────────────────────
@dataclass
class FirmProfile:
    """Single prop-firm profile loaded from YAML."""
    profile_id: str                   # e.g. "ftmo_challenge"
    firm_id: str                      # e.g. "ftmo"
    name: str                         # human-readable
    initial_balance: float
    profit_target_pct: float          # 0.10 = 10%
    max_daily_loss_pct: float         # 0.05 = 5%
    max_total_loss_pct: float         # 0.10 = 10%
    emergency_halt_pct: float         # 0.08 = 8%
    daily_caution_pct: float          # 0.04 = 4%
    drawdown_mode: str                # static | trailing | hybrid
    daily_loss_mode: str              # balance_based | peak_equity_based
    min_trading_days: int
    max_trading_days: int             # 0 = unlimited
    consistency_rule_enabled: bool
    consistency_pct: float            # 0.40 = 40%
    weekend_close_required: bool
    use_news_filter: bool
    news_blackout_minutes: int
    max_open_positions: int
    max_lot: float                    # capped at HARD_MAX_LOT_CAP
    risk_per_trade_pct: float
    max_symbol_exposure: float
    atr_profile: str                  # challenge | balanced | production_aggressive
    phase: str                        # challenge | verification | funded
    hedging_allowed: bool = True
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def effective_max_lot(self) -> float:
        """Return min(profile.max_lot, HARD_MAX_LOT_CAP)."""
        return min(self.max_lot, HARD_MAX_LOT_CAP)

    @property
    def effective_max_open_positions(self) -> int:
        """Return min(profile.max_open_positions, HARD_MAX_OPEN_POSITIONS)."""
        return min(self.max_open_positions, HARD_MAX_OPEN_POSITIONS)


# ─── Manager ──────────────────────────────────────────────────────────────────
class PropFirmProfileManager:
    """
    Manages prop-firm profile lifecycle: load → lock → expose → unlock → switch.

    All state changes are journaled. Auto-detection is advisory only.
    """

    def __init__(
        self,
        profiles_path: str | Path,
        journal: Optional[TradeJournal] = None,
    ):
        self.profiles_path = Path(profiles_path)
        self.journal = journal
        self._profiles: dict[str, dict] = {}
        self._auto_detect_rules: dict = {}
        self._active_profile: Optional[FirmProfile] = None
        self._active_profile_id: Optional[str] = None
        self._locked: bool = False
        self._load_yaml()

    # ─── YAML loading ─────────────────────────────────────────────────────

    def _load_yaml(self) -> None:
        if not self.profiles_path.exists():
            raise FileNotFoundError(
                f"Prop firm profiles YAML not found: {self.profiles_path}"
            )
        # Sprint 9.0.1: explicit UTF-8 — Windows defaults to cp1252 which
        # raises UnicodeDecodeError on non-ASCII chars in profile notes.
        with open(self.profiles_path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        self._profiles = doc.get("profiles", {}) or {}
        self._auto_detect_rules = doc.get("auto_detect", {}) or {}
        logger.info(
            f"PropFirmProfileManager loaded {len(self._profiles)} profiles "
            f"from {self.profiles_path}"
        )

    # ─── Public API ───────────────────────────────────────────────────────

    def list_profiles(self) -> list[str]:
        """Return all available profile IDs."""
        return sorted(self._profiles.keys())

    def has_profile(self, profile_id: str) -> bool:
        return profile_id in self._profiles

    @property
    def active_profile(self) -> Optional[FirmProfile]:
        return self._active_profile

    @property
    def active_profile_id(self) -> Optional[str]:
        return self._active_profile_id

    @property
    def is_locked(self) -> bool:
        return self._locked

    @property
    def has_active_profile(self) -> bool:
        return self._active_profile is not None

    # ─── Manual profile loading ───────────────────────────────────────────

    def load_profile(
        self,
        profile_id: str,
        custom_overrides: Optional[dict] = None,
    ) -> FirmProfile:
        """
        Explicitly load a profile by ID.

        Fails closed (raises) if:
          - profile_id is "none" or empty
          - profile_id is "auto" (use auto_detect + apply_suggestion instead)
          - profile_id is unknown
          - manager is locked and profile_id differs from active

        Returns the loaded FirmProfile. Also journals PROFILE_LOADED.
        """
        if profile_id in ("none", "", None):
            self._refuse("profile is 'none' or empty — refusing to start challenge mode")
            raise ValueError("profile cannot be 'none' when loading")

        if profile_id == "auto":
            self._refuse(
                "profile='auto' requires auto_detect() + apply_suggestion() — "
                "load_profile('auto') is not allowed"
            )
            raise ValueError("profile='auto' cannot be loaded directly")

        if profile_id not in self._profiles:
            self._refuse(f"unknown profile_id: {profile_id!r}")
            raise KeyError(f"unknown profile_id: {profile_id!r}")

        # Lock check
        if self._locked and self._active_profile_id != profile_id:
            msg = (
                f"manager is locked on profile {self._active_profile_id!r} — "
                f"cannot switch to {profile_id!r} without unlock()"
            )
            self._refuse(msg)
            raise PermissionError(msg)

        raw = dict(self._profiles[profile_id])

        # Apply custom overrides if provided
        if custom_overrides:
            raw.update(custom_overrides)

        # Build FirmProfile with hard-cap enforcement
        profile = self._build_profile(profile_id, raw)

        was_switch = (
            self._active_profile_id is not None
            and self._active_profile_id != profile_id
        )
        self._active_profile = profile
        self._active_profile_id = profile_id

        # Journal
        if was_switch:
            self._journal_event(EventType.PROFILE_SWITCHED, {
                "from_profile": self._active_profile_id,
                "to_profile": profile_id,
                "profile": profile.to_dict(),
            })
        else:
            self._journal_event(EventType.PROFILE_LOADED, {
                "profile_id": profile_id,
                "profile": profile.to_dict(),
                "effective_max_lot": profile.effective_max_lot,
                "effective_max_open_positions": profile.effective_max_open_positions,
            })
        logger.info(f"Profile loaded: {profile_id} (name={profile.name})")
        return profile

    # ─── Auto-detection (advisory only) ───────────────────────────────────

    def auto_detect(self, mt5_account_info: Any) -> Optional[str]:
        """
        Suggest a profile based on MT5 account_info().company / .server / .name.

        Returns the suggested profile_id, or None if no match.
        Does NOT apply the suggestion — operator must call apply_suggestion().
        Journals PROFILE_SUGGESTION with the suggestion + reasoning.
        """
        if mt5_account_info is None:
            self._journal_event(EventType.PROFILE_SUGGESTION, {
                "suggestion": None,
                "reason": "mt5_account_info is None",
            })
            return None

        rules = self._auto_detect_rules.get("rules", []) or []
        for rule in rules:
            field_name = rule.get("field", "company")
            pattern = rule.get("match", "")
            target_profile = rule.get("profile", "")
            actual_value = str(getattr(mt5_account_info, field_name, "") or "")
            if pattern.lower() in actual_value.lower():
                self._journal_event(EventType.PROFILE_SUGGESTION, {
                    "suggestion": target_profile,
                    "matched_field": field_name,
                    "matched_value": actual_value,
                    "pattern": pattern,
                    "reason": f"MT5 {field_name} matches {pattern!r}",
                })
                logger.info(
                    f"Auto-detect suggestion: {target_profile!r} "
                    f"(field={field_name} value={actual_value!r})"
                )
                return target_profile

        # No match
        on_no_match = self._auto_detect_rules.get("on_no_match", "refuse_start")
        self._journal_event(EventType.PROFILE_SUGGESTION, {
            "suggestion": None,
            "reason": f"no auto-detect rule matched (on_no_match={on_no_match})",
            "mt5_company": str(getattr(mt5_account_info, "company", "") or ""),
            "mt5_server": str(getattr(mt5_account_info, "server", "") or ""),
        })
        return None

    def apply_suggestion(self, suggested_id: str) -> FirmProfile:
        """
        Operator explicitly accepts an auto-detection suggestion.

        Journals PROFILE_LOADED (not auto-applied silently).
        """
        return self.load_profile(suggested_id)

    # ─── Lock / unlock ────────────────────────────────────────────────────

    def lock(self) -> None:
        """Lock the active profile — prevents switching without unlock."""
        if self._active_profile is None:
            raise RuntimeError("cannot lock — no active profile")
        self._locked = True
        self._journal_event(EventType.PROFILE_LOCKED, {
            "profile_id": self._active_profile_id,
        })
        logger.info(f"Profile locked: {self._active_profile_id}")

    def unlock(self, reason: str) -> None:
        """Unlock — requires explicit reason (journaled)."""
        if not reason or not reason.strip():
            raise ValueError("unlock requires a non-empty reason")
        if not self._locked:
            return  # already unlocked, no-op
        prev = self._active_profile_id
        self._locked = False
        self._journal_event(EventType.PROFILE_UNLOCKED, {
            "profile_id": prev,
            "reason": reason,
        })
        logger.warning(f"Profile unlocked: {prev} (reason: {reason})")

    # ─── Internal helpers ─────────────────────────────────────────────────

    def _build_profile(self, profile_id: str, raw: dict) -> FirmProfile:
        """Build FirmProfile from raw YAML dict, enforcing hard caps."""
        # Hard-cap max_lot and max_open_positions
        raw_max_lot = float(raw.get("max_lot", HARD_MAX_LOT_CAP))
        raw_max_pos = int(raw.get("max_open_positions", HARD_MAX_OPEN_POSITIONS))
        max_lot = min(raw_max_lot, HARD_MAX_LOT_CAP)
        max_open_positions = min(raw_max_pos, HARD_MAX_OPEN_POSITIONS)

        if max_lot != raw_max_lot:
            logger.warning(
                f"Profile {profile_id} max_lot={raw_max_lot} capped to "
                f"HARD_MAX_LOT_CAP={HARD_MAX_LOT_CAP}"
            )
        if max_open_positions != raw_max_pos:
            logger.warning(
                f"Profile {profile_id} max_open_positions={raw_max_pos} capped to "
                f"HARD_MAX_OPEN_POSITIONS={HARD_MAX_OPEN_POSITIONS}"
            )

        return FirmProfile(
            profile_id=profile_id,
            firm_id=str(raw.get("firm_id", profile_id)),
            name=str(raw.get("name", profile_id)),
            initial_balance=float(raw.get("initial_balance", 100000.0)),
            profit_target_pct=float(raw.get("profit_target_pct", 0.10)),
            max_daily_loss_pct=float(raw.get("max_daily_loss_pct", 0.05)),
            max_total_loss_pct=float(raw.get("max_total_loss_pct", 0.10)),
            emergency_halt_pct=float(raw.get("emergency_halt_pct", 0.08)),
            daily_caution_pct=float(raw.get("daily_caution_pct", 0.04)),
            drawdown_mode=str(raw.get("drawdown_mode", DrawdownMode.STATIC)),
            daily_loss_mode=str(raw.get("daily_loss_mode", DailyLossMode.BALANCE_BASED)),
            min_trading_days=int(raw.get("min_trading_days", 0)),
            max_trading_days=int(raw.get("max_trading_days", 0)),
            consistency_rule_enabled=bool(raw.get("consistency_rule_enabled", False)),
            consistency_pct=float(raw.get("consistency_pct", 0.0)),
            weekend_close_required=bool(raw.get("weekend_close_required", True)),
            use_news_filter=bool(raw.get("use_news_filter", True)),
            news_blackout_minutes=int(raw.get("news_blackout_minutes", 30)),
            max_open_positions=max_open_positions,
            max_lot=max_lot,
            risk_per_trade_pct=float(raw.get("risk_per_trade_pct", 0.01)),
            max_symbol_exposure=float(raw.get("max_symbol_exposure", 0.01)),
            atr_profile=str(raw.get("atr_profile", "balanced")),
            phase=str(raw.get("phase", Phase.CHALLENGE)),
            hedging_allowed=bool(raw.get("hedging_allowed", True)),
            notes=str(raw.get("notes", "")),
        )

    def _refuse(self, reason: str) -> None:
        """Journal a profile refusal (fail-closed event)."""
        self._journal_event(EventType.PROFILE_REFUSED, {"reason": reason})
        logger.error(f"Profile refused: {reason}")

    def _journal_event(self, event_type: EventType, data: dict) -> None:
        if self.journal is None:
            return
        try:
            self.journal.log_event(event_type, data)
        except Exception as e:
            logger.error(f"Journal event {event_type.value} failed: {e}")


# ─── Convenience: apply profile to existing components ────────────────────────
def apply_profile_to_kill_switch(profile: FirmProfile, ks_config) -> None:
    """
    Override KillSwitchConfig thresholds with profile values (in-place).
    Only called when prop_firm.enabled=true.
    """
    # Convert decimal (0.05) to percent (5.0) for KillSwitchFSM
    ks_config.max_daily_loss_pct = profile.max_daily_loss_pct * 100
    ks_config.max_drawdown_pct = profile.max_total_loss_pct * 100
    ks_config.emergency_daily_loss_pct = profile.emergency_halt_pct * 100
    ks_config.emergency_drawdown_pct = profile.max_total_loss_pct * 100


def apply_profile_to_trade_loop(profile: FirmProfile, loop_config) -> None:
    """
    Override TradeLoopConfig with profile values (in-place).
    Hard caps are enforced via FirmProfile.effective_max_lot.
    """
    loop_config.max_lot = profile.effective_max_lot
    loop_config.max_open_positions = profile.effective_max_open_positions


def apply_profile_to_news_filter(profile: FirmProfile, news_filter) -> None:
    """Override NewsFilter blackout minutes with profile value."""
    if hasattr(news_filter, "block_window_minutes"):
        news_filter.block_window_minutes = profile.news_blackout_minutes


def apply_profile_to_atr(profile: FirmProfile, loop_config) -> None:
    """
    Override TradeLoopConfig ATR multipliers based on profile.atr_profile.
    Reads from runtime.yaml atr_profiles section (passed in via loop_config
    or hard-coded mapping).
    """
    # Mapping is enforced here as a safety net (also defined in runtime.yaml)
    ATR_MAPPING = {
        "challenge": (1.5, 3.0),
        "balanced": (2.0, 4.0),
        "production_aggressive": (3.0, 6.0),
    }
    if profile.atr_profile in ATR_MAPPING:
        sl_mult, tp_mult = ATR_MAPPING[profile.atr_profile]
        loop_config.atr_sl_multiplier = sl_mult
        loop_config.atr_tp_multiplier = tp_mult
        logger.info(
            f"ATR profile applied: {profile.atr_profile} → "
            f"sl_mult={sl_mult} tp_mult={tp_mult}"
        )
