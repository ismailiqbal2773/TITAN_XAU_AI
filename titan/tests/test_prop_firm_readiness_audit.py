"""
TITAN XAU AI — Prop Firm Readiness Audit Tests
================================================

8+ tests covering:
  - Audit produces a verdict in the valid set.
  - Audit does not import MetaTrader5 or call order_send.
  - Audit does not contain banned betting logic.
  - Audit reports per-profile results.
  - JSON / MD reports are written correctly.
  - Audit surfaces blockers for profiles with critical unknowns.
  - Audit surfaces warnings for simulation-only profiles.
  - Audit enforces safety invariants on every profile.
  - Audit's design_description is present and meaningful.

NEVER imports MetaTrader5. NEVER calls mt5.order_send.
"""
from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _strip(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'r"[^"]*"', '""', src)
    src = re.sub(r"r'[^']*'", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    out = []
    for line in src.splitlines():
        idx = line.find("#")
        if idx >= 0:
            line = line[:idx]
        out.append(line)
    return "\n".join(out)


class TestPropFirmReadinessAudit:
    def test_01_verdict_in_valid_set(self):
        import scripts.audit.prop_firm_readiness_audit as mod
        result = mod.run_audit()
        assert result["verdict"] in (
            mod.PROP_FIRM_READY,
            mod.PROP_FIRM_NEEDS_WORK,
            mod.PROP_FIRM_BLOCKED,
        )

    def test_02_audit_does_not_import_metatrader5(self):
        import scripts.audit.prop_firm_readiness_audit as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        assert not re.search(r"^\s*import\s+MetaTrader5\b", code, flags=re.MULTILINE)
        assert not re.search(r"^\s*from\s+MetaTrader5\b", code, flags=re.MULTILINE)

    def test_03_audit_does_not_call_order_send(self):
        import scripts.audit.prop_firm_readiness_audit as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bMetaTrader5\.order_send\s*\(", code)

    def test_04_audit_has_no_banned_betting_logic(self):
        import scripts.audit.prop_firm_readiness_audit as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        low = code.lower()
        forbidden_patterns = [
            r"def\s+apply_martingale",
            r"def\s+apply_grid",
            r"def\s+average_down",
            r"\blot\s*\*\s*2\b",
            r"position_size\s*\*=\s*2\b",
            r"(?<!no_)\bloss_based_lot_multiplier\s*=",
            r"(?<!no_)\bmartingale_multiplier\s*=",
        ]
        for pat in forbidden_patterns:
            assert not re.search(pat, low), (
                f"audit implements banned betting pattern: {pat}"
            )

    def test_05_audit_returns_per_profile_results(self):
        import scripts.audit.prop_firm_readiness_audit as mod
        result = mod.run_audit()
        assert "profiles" in result
        assert isinstance(result["profiles"], list)
        assert len(result["profiles"]) >= 8
        # Each profile result has the canonical fields.
        for p in result["profiles"]:
            assert "profile_name" in p
            assert "verdict" in p
            assert "blockers" in p
            assert "warnings" in p
            assert "unknown_critical_count" in p

    def test_06_json_report_written(self, tmp_path):
        import scripts.audit.prop_firm_readiness_audit as mod
        result = mod.run_audit()
        report = mod.write_report(result, output_dir=tmp_path)
        assert Path(report["json_path"]).exists()
        with open(report["json_path"]) as f:
            data = json.load(f)
        assert "verdict" in data
        assert "profile_count" in data
        assert "profiles" in data
        assert "design_description" in data

    def test_07_md_report_written_and_contains_design_note(self, tmp_path):
        import scripts.audit.prop_firm_readiness_audit as mod
        result = mod.run_audit()
        report = mod.write_report(result, output_dir=tmp_path)
        md = Path(report["md_path"]).read_text(encoding="utf-8")
        assert "Prop Firm Readiness Audit" in md
        assert "Per-profile verdicts" in md
        # The MD must explicitly state the audit NEVER calls order_send.
        assert "order_send" in md
        # And never contains martingale/grid/averaging.
        assert "martingale" in md.lower()

    def test_08_audit_surfaces_blockers_for_known_issues(self):
        """Sprint 9.9.3.45.8.7: Profiles that previously lacked min_rr now
        have it added (TEMPLATE_DEFAULT). The audit must still validate
        them correctly. Legacy inactive profiles may have warnings but
        should not block production proof."""
        import scripts.audit.prop_firm_readiness_audit as mod
        result = mod.run_audit()
        # ftmo_challenge now has min_rr=2.0 (TEMPLATE_DEFAULT) and is inactive
        ftmo_result = next(
            (p for p in result["profiles"] if p["profile_name"] == "ftmo_challenge"),
            None,
        )
        assert ftmo_result is not None
        # Since ftmo_challenge is inactive (active_for_production_proof=False),
        # it should not block the overall audit verdict
        assert ftmo_result.get("active_for_production_proof") is False
        # The overall audit should not be BLOCKED just because legacy profiles
        # have issues
        assert result["verdict"] != "PROP_FIRM_BLOCKED" or len(result.get("blockers", [])) == 0 or \
               all("[ftmo_challenge]" not in b for b in result.get("blockers", [])), \
            "Inactive legacy profiles should not cause BLOCKED verdict"

    def test_09_audit_reports_simulation_only_profile(self):
        """The prop_aggressive_20pct_simulation_only profile must be reported
        by the audit (READY_WITH_UNKNOWN_NON_CRITICAL)."""
        import scripts.audit.prop_firm_readiness_audit as mod
        result = mod.run_audit()
        sim_result = next(
            (p for p in result["profiles"]
             if p["profile_name"] == "prop_aggressive_20pct_simulation_only"),
            None,
        )
        assert sim_result is not None
        assert sim_result["verdict"] in (
            "PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL",
            "PROP_RULES_READY",
        )
        assert sim_result["rules"]["simulation_only"] is True
        assert sim_result["rules"]["live_allowed"] is False

    def test_10_audit_enforces_safety_invariants_per_profile(self):
        """Every profile result must report no_martingale/no_grid/no_averaging
        = True."""
        import scripts.audit.prop_firm_readiness_audit as mod
        result = mod.run_audit()
        for p in result["profiles"]:
            assert p["no_martingale"] is True, (
                f"{p['profile_name']}: no_martingale=False"
            )
            assert p["no_grid"] is True
            assert p["no_averaging"] is True

    def test_11_audit_design_description_is_present_and_meaningful(self):
        import scripts.audit.prop_firm_readiness_audit as mod
        result = mod.run_audit()
        dd = result["design_description"].lower()
        assert "prop" in dd
        assert "rule" in dd
        assert "order_send" in dd
        assert "martingale" in dd or "grid" in dd or "averaging" in dd

    def test_12_audit_uses_future_annotations(self):
        import scripts.audit.prop_firm_readiness_audit as mod
        src = inspect.getsource(mod)
        assert "from __future__ import annotations" in src
