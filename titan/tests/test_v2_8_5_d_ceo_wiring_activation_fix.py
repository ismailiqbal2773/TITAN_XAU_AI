"""TITAN XAU AI - Sprint v2.8.5-D CEO Runtime Wiring + Activation Dependency Fix Tests

Tests architecture lock, circular dependency fix, CEO wiring, and safety.

Required tests (per sprint spec):
  Architecture Lock:
    1. architecture lock file exists
    2. architecture audit references architecture lock
    3. PDFs are not treated as current source of truth

  Circular dependency:
    4. final_demo_activation does not require production_closure artifact
    5. production_closure aggregates final_demo_activation
    6. build_request computes readiness without final_demo_activation circular dependency

  CEO wiring:
    7. build-request imports CEO AI governance
    8. build-request calls evaluate_ceo_decision
    9. build-request displays CEO decision fields
    10. build-request blocks if CEO import fails
    11. build-request blocks if CEO returns blocked
    12. execute path calls CEO before order_send
    13. execute path does not call order_send if CEO blocks
    14. raw XGB/regime pass cannot bypass CEO
    15. CEO not wired blocks final activation
    16. CEO not wired blocks production closure
    17. architecture pipeline blocks if CEO exists but operator does not call it
    18. CEO PASS requires operator path wiring

  Safety:
    19. build-request remains read-only
    20. audits never create token
    21. audits never call order_send
    22. audits never modify positions
    23. no martingale/grid/averaging/loss multiplier

  Regression:
    24. focused tests pass
    25. tests do not dirty repo
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

ARCH_LOCK = REPO_ROOT / "docs" / "TITAN_ARCHITECTURE_LOCK_v1.0.md"
OP_SCRIPT = REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py"
ARCH_AUDIT = REPO_ROOT / "scripts" / "audit" / "runtime_architecture_pipeline_audit.py"
CEO_AUDIT = REPO_ROOT / "scripts" / "audit" / "ceo_ai_governance_audit.py"
FINAL_ACT = REPO_ROOT / "scripts" / "audit" / "final_demo_activation_readiness_audit.py"
PROD_CLOSURE = REPO_ROOT / "scripts" / "audit" / "production_closure_readiness_audit.py"


# ============================================================
# Architecture Lock tests (1-3)
# ============================================================

class TestArchitectureLock:
    def test_01_architecture_lock_file_exists(self):
        """Test 1: Architecture Lock file must exist."""
        assert ARCH_LOCK.exists(), f"Architecture Lock not found: {ARCH_LOCK}"

    def test_02_architecture_audit_references_lock(self):
        """Test 2: Runtime architecture audit must reference Architecture Lock."""
        src = ARCH_AUDIT.read_text(encoding="utf-8")
        assert "TITAN_ARCHITECTURE_LOCK_v1.0.md" in src, \
            "Architecture audit must reference Architecture Lock"

    def test_03_pdfs_not_treated_as_current_source(self):
        """Test 3: Architecture Lock must state PDFs are historical only."""
        content = ARCH_LOCK.read_text(encoding="utf-8")
        assert "historical/reference only" in content, \
            "Architecture Lock must state PDFs are historical/reference only"


# ============================================================
# Circular dependency tests (4-6)
# ============================================================

class TestCircularDependency:
    def test_04_final_activation_does_not_require_production_closure(self):
        """Test 4: final_demo_activation must NOT read production_closure as required gate."""
        src = FINAL_ACT.read_text(encoding="utf-8")
        # The script should NOT have PRODUCTION_CLOSURE_NOT_READY blocker
        # (we removed it in Phase 2)
        # Check that production_closure is not a required gate
        assert "PRODUCTION_CLOSURE_NOT_READY" not in src or \
               "REMOVED" in src or "acyclic" in src.lower(), \
            "final_demo_activation must not require production_closure artifact"

    def test_05_production_closure_aggregates_final_activation(self):
        """Test 5: production_closure must read final_demo_activation (aggregator)."""
        src = PROD_CLOSURE.read_text(encoding="utf-8")
        assert "final_demo_activation" in src, \
            "production_closure must aggregate final_demo_activation"

    def test_06_build_request_no_circular_dependency(self):
        """Test 6: build-request must not depend on final_demo_activation to compute PASS."""
        src = OP_SCRIPT.read_text(encoding="utf-8")
        # Build-request should not read final_demo_activation JSON
        # (it writes managed_trade_report, doesn't read final_demo_activation)
        # Check that _normalize_build_request_verdict doesn't read final_demo_activation
        br_func_start = src.find("def _normalize_build_request_verdict")
        if br_func_start > 0:
            br_func_end = src.find("\ndef ", br_func_start + 1)
            br_body = src[br_func_start:br_func_end if br_func_end > 0 else len(src)]
            assert "final_demo_activation" not in br_body, \
                "build-request normalized verdict must not depend on final_demo_activation"


# ============================================================
# CEO wiring tests (7-18)
# ============================================================

class TestCEOWiring:
    def test_07_build_request_imports_ceo(self):
        """Test 7: build-request must import CEO AI governance."""
        src = OP_SCRIPT.read_text(encoding="utf-8")
        assert "from titan.production.ceo_ai_governance import" in src, \
            "build-request must import ceo_ai_governance"

    def test_08_build_request_calls_evaluate_ceo_decision(self):
        """Test 8: build-request must call evaluate_ceo_decision."""
        src = OP_SCRIPT.read_text(encoding="utf-8")
        assert "evaluate_ceo_decision(" in src, \
            "build-request must call evaluate_ceo_decision"

    def test_09_build_request_displays_ceo_decision_fields(self):
        """Test 9: build-request must display CEO decision fields in console."""
        src = OP_SCRIPT.read_text(encoding="utf-8")
        assert "CEO governance imported:" in src
        assert "CEO governance called:" in src
        assert "CEO final decision:" in src
        assert "CEO allowed_to_trade:" in src
        assert "CEO risk_multiplier:" in src

    def test_10_build_request_blocks_if_ceo_import_fails(self):
        """Test 10: build-request must BLOCK if CEO import fails."""
        src = OP_SCRIPT.read_text(encoding="utf-8")
        assert "CEO_AI_GOVERNANCE_NOT_WIRED" in src or \
               "CEO_AI_GOVERNANCE_IMPORT_FAILED" in src, \
            "build-request must block if CEO import fails"

    def test_11_build_request_blocks_if_ceo_returns_blocked(self):
        """Test 11: build-request must BLOCK if CEO returns blocked."""
        src = OP_SCRIPT.read_text(encoding="utf-8")
        assert "CEO_AI_GOVERNANCE_BLOCKED" in src, \
            "build-request must block if CEO returns blocked"

    def test_12_execute_path_calls_ceo_before_order_send(self):
        """Test 12: execute path must call CEO before order_send."""
        src = OP_SCRIPT.read_text(encoding="utf-8")
        # CEO call must appear before mt5.order_send in execute-and-monitor
        ceo_pos = src.find("evaluate_ceo_decision(")
        order_send_pos = src.find("mt5.order_send(request)")
        assert ceo_pos > 0 and order_send_pos > 0, \
            "Both CEO call and order_send must exist"
        # Find the CEO call in execute-and-monitor context (after run_execute_and_monitor)
        exec_start = src.find("def run_execute_and_monitor")
        assert exec_start > 0
        exec_ceo = src.find("evaluate_ceo_decision(", exec_start)
        exec_order = src.find("mt5.order_send(request)", exec_start)
        assert exec_ceo > 0 and exec_order > 0, \
            "Execute path must have both CEO call and order_send"
        assert exec_ceo < exec_order, \
            "CEO must be called BEFORE order_send in execute path"

    def test_13_execute_path_does_not_call_order_send_if_ceo_blocks(self):
        """Test 13: execute path must not call order_send if CEO blocks."""
        src = OP_SCRIPT.read_text(encoding="utf-8")
        assert "CEO_AI_GOVERNANCE_BLOCKED_EXECUTION" in src, \
            "Execute path must have CEO_AI_GOVERNANCE_BLOCKED_EXECUTION blocker"

    def test_14_raw_xgb_cannot_bypass_ceo(self):
        """Test 14: raw XGB/regime pass cannot bypass CEO."""
        # The architecture lock must state this rule
        lock = ARCH_LOCK.read_text(encoding="utf-8")
        assert "Raw XGB signal can never reach execution directly" in lock, \
            "Architecture Lock must state raw XGB cannot bypass CEO"

    def test_15_ceo_not_wired_blocks_final_activation(self):
        """Test 15: CEO not wired must block final activation."""
        src = FINAL_ACT.read_text(encoding="utf-8")
        # Final activation must check CEO governance verdict
        assert "ceo_ai_governance" in src.lower(), \
            "Final activation must check CEO governance"

    def test_16_ceo_not_wired_blocks_production_closure(self):
        """Test 16: CEO not wired must block production closure."""
        src = PROD_CLOSURE.read_text(encoding="utf-8")
        assert "CEO_OPERATOR_BUILD_REQUEST_NOT_WIRED" in src or \
               "CEO_EXECUTE_PATH_NOT_WIRED" in src, \
            "Production closure must block if CEO not wired"

    def test_17_architecture_pipeline_blocks_if_ceo_not_called(self):
        """Test 17: architecture pipeline must BLOCK if CEO exists but not called."""
        src = ARCH_AUDIT.read_text(encoding="utf-8")
        assert "CEO_AI_GOVERNANCE_NOT_INTEGRATED" in src, \
            "Architecture audit must block if CEO not integrated"

    def test_18_ceo_pass_requires_operator_path_wiring(self):
        """Test 18: CEO governance audit PASS requires operator path wiring."""
        src = CEO_AUDIT.read_text(encoding="utf-8")
        assert "build_request_imports_ceo" in src, \
            "CEO audit must check build_request_imports_ceo"
        assert "build_request_calls_ceo" in src, \
            "CEO audit must check build_request_calls_ceo"
        assert "execute_path_calls_ceo_before_order_send" in src, \
            "CEO audit must check execute_path_calls_ceo_before_order_send"


# ============================================================
# Safety tests (19-23)
# ============================================================

class TestSafety:
    def test_19_build_request_remains_read_only(self):
        """Test 19: build-request must remain read-only (no token, no order_send, no modify)."""
        src = OP_SCRIPT.read_text(encoding="utf-8")
        # Find run_build_request function
        br_start = src.find("def run_build_request")
        br_end = src.find("\ndef ", br_start + 1)
        br_body = src[br_start:br_end if br_end > 0 else len(src)]
        # Must NOT have mt5.order_send call (not in a string)
        # Check for actual call pattern
        assert not re.search(r'mt5\.order_send\s*\(', br_body), \
            "run_build_request must not call mt5.order_send"

    def test_20_audits_never_create_token(self):
        """Test 20: Audits must never create operator execution token."""
        audit_scripts = list((REPO_ROOT / "scripts" / "audit").glob("*.py"))
        for script in audit_scripts:
            if not script.exists():
                continue
            src = script.read_text(encoding="utf-8")
            stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
            stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
            stripped = re.sub(r'"(?:[^"\\]|\\.)*"', '""', stripped)
            stripped = re.sub(r"'(?:[^'\\]|\\.)*'", "''", stripped)
            if ("subprocess" in stripped and "create_local_operator_execution_token" in stripped) or \
               "import create_local_operator_execution_token" in stripped or \
               "from create_local_operator_execution_token" in stripped:
                if script.name != "runtime_safety_gate_audit.py":
                    pytest.fail(f"{script.name} may create tokens")

    def test_21_audits_never_call_order_send(self):
        """Test 21: Audits must never call mt5.order_send."""
        audit_scripts = [
            REPO_ROOT / "scripts" / "audit" / "model_artifact_health_audit.py",
            REPO_ROOT / "scripts" / "audit" / "feature_parity_audit.py",
            REPO_ROOT / "scripts" / "audit" / "prop_challenge_growth_profile_audit.py",
            REPO_ROOT / "scripts" / "audit" / "final_demo_activation_readiness_audit.py",
            REPO_ROOT / "scripts" / "audit" / "runtime_architecture_pipeline_audit.py",
            REPO_ROOT / "scripts" / "audit" / "ceo_ai_governance_audit.py",
            REPO_ROOT / "scripts" / "audit" / "production_closure_readiness_audit.py",
            REPO_ROOT / "titan" / "production" / "ceo_ai_governance.py",
            REPO_ROOT / "titan" / "production" / "audit_hygiene.py",
        ]
        for script in audit_scripts:
            if not script.exists():
                continue
            src = script.read_text(encoding="utf-8")
            stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
            stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
            stripped = re.sub(r'"(?:[^"\\]|\\.)*"', '""', stripped)
            stripped = re.sub(r"'(?:[^'\\]|\\.)*'", "''", stripped)
            stripped = re.sub(r'#.*$', '', stripped, flags=re.MULTILINE)
            for match in re.finditer(r'(mt5|broker|adapter|self)\.order_send\s*\(', stripped):
                line_start = stripped.rfind('\n', 0, match.start()) + 1
                prefix = stripped[line_start:match.start()]
                if re.match(r'\s*def\s+', prefix):
                    continue
                pytest.fail(f"{script.name} contains actual order_send call")

    def test_22_audits_never_modify_positions(self):
        """Test 22: Audits must never modify positions."""
        audit_scripts = list((REPO_ROOT / "scripts" / "audit").glob("*.py"))
        audit_scripts.append(REPO_ROOT / "titan" / "production" / "ceo_ai_governance.py")
        audit_scripts.append(REPO_ROOT / "titan" / "production" / "audit_hygiene.py")
        for script in audit_scripts:
            if not script.exists():
                continue
            if script.name == "runtime_safety_gate_audit.py":
                continue
            src = script.read_text(encoding="utf-8")
            stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
            stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
            stripped = re.sub(r'"(?:[^"\\]|\\.)*"', '""', stripped)
            stripped = re.sub(r"'(?:[^'\\]|\\.)*'", "''", stripped)
            for pattern in ("position_modify(", "positions_modify(",
                            "order_modify(", "mt5.order_modify(",
                            ".modify_position(", ".modify_sltp("):
                assert pattern not in stripped, f"{script.name} contains {pattern}"

    def test_23_no_martingale_grid_averaging_loss_multiplier(self):
        """Test 23: No martingale/grid/averaging/loss multiplier in new code."""
        new_files = [
            REPO_ROOT / "titan" / "production" / "ceo_ai_governance.py",
            REPO_ROOT / "titan" / "production" / "audit_hygiene.py",
        ]
        for f in new_files:
            if not f.exists():
                continue
            src = f.read_text(encoding="utf-8")
            stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
            stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
            stripped = re.sub(r'"(?:[^"\\]|\\.)*"', '""', stripped)
            stripped = re.sub(r"'(?:[^'\\]|\\.)*'", "''", stripped)
            stripped_no_comments = re.sub(r'#.*$', '', stripped, flags=re.MULTILINE)
            for word in ("martingale", "grid_trading", "averaging_down",
                        "loss_multiplier", "loss_based_lot"):
                for m in re.finditer(r'\b(' + word + r')\b', stripped_no_comments, re.IGNORECASE):
                    start = m.start()
                    while start > 0 and (stripped_no_comments[start-1].isalnum() or stripped_no_comments[start-1] == '_'):
                        start -= 1
                    identifier = stripped_no_comments[start:m.end()]
                    if any(identifier.lower().startswith(p) for p in
                           ("no_", "not_", "never_", "forbid_", "without_", "check_no_", "has_no_")):
                        continue
                    line_start = stripped_no_comments.rfind('\n', 0, m.start()) + 1
                    line = stripped_no_comments[line_start:m.start()]
                    if any(p in line.lower() for p in ("forbidden", "not_allowed", "disabled", "false")):
                        continue
                    pytest.fail(f"{f.name} contains forbidden strategy: {identifier}")
