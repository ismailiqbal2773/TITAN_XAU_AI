"""TITAN XAU AI - Archive Micro Proof Pass Tests (Sprint 9.9.3.45.9)"""
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
    """Remove docstrings + string literals so regex scanning does not match
    identifiers that only appear inside string literals (e.g. 'order_send'
    inside a docstring)."""
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'r"[^"]*"', '""', src)
    src = re.sub(r"r'[^']*'", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


def _write_pass_forensics(dir_path: Path) -> Path:
    """Create a forensics JSON that produces MICRO_PROOF_PASS."""
    p = dir_path / "post_trade_forensics.json"
    p.write_text(json.dumps({
        "timestamp_utc": "2026-07-02T03:28:06.307126+00:00",
        "verdict": "DEMO_MICRO_EVIDENCE_PASS",
        "ok_checks": ["receipt matched", "entry deal found", "exit deal found"],
        "blockers": [],
        "warnings": [],
        "findings": {
            "receipt_match_found": True,
            "fallback_used": False,
            "entry_deals_count": 1,
            "exit_deals_count": 1,
            "open_positions_count": 0,
            "root_cause": "RECEIPT_MATCHED",
        },
        "safety": {"order_send_called": False, "position_modified": False},
    }), encoding="utf-8")
    return p


def _write_diagnostic(dir_path: Path) -> Path:
    p = dir_path / "latest_receipt_diagnostic.json"
    p.write_text(json.dumps({
        "timestamp_utc": "2026-07-02T03:28:06.266100+00:00",
        "verdict": "RECEIPT_MATCHED",
        "ok_checks": ["open position match"],
        "blockers": [],
        "warnings": [],
        "findings": {"receipt_exists": True, "open_position_match": True},
        "safety": {"order_send_called": False, "position_modified": False},
    }), encoding="utf-8")
    return p


def _write_receipt(dir_path: Path) -> Path:
    p = dir_path / "demo_micro_execution_receipt.json"
    p.write_text(json.dumps({
        "timestamp_utc": "2026-07-02T03:27:00.000000+00:00",
        "success": True,
        "symbol": "XAUUSD",
        "volume": 0.01,
        "order_ticket": 5001,
        "deal_ticket": 6001,
        "detected_position_identifier": 5001,
    }), encoding="utf-8")
    return p


class TestArchiveMicroProofPass:
    def test_01_module_imports(self):
        """The archive module must import cleanly and expose run_archive."""
        import scripts.audit.archive_micro_proof_pass as mod
        assert hasattr(mod, "run_archive")
        assert hasattr(mod, "main")
        assert mod.MICRO_PROOF_ARCHIVED == "MICRO_PROOF_ARCHIVED"
        assert mod.MICRO_PROOF_ARCHIVE_BLOCKED == "MICRO_PROOF_ARCHIVE_BLOCKED"

    def test_02_returns_result_dict(self):
        """run_archive() must always return a result dict with verdict."""
        import scripts.audit.archive_micro_proof_pass as mod
        # No receipt present -> blocked, but still returns dict
        result = mod.run_archive(
            receipt_path=Path("/nonexistent/receipt.json"),
            diagnostic_path=Path("/nonexistent/diag.json"),
            forensics_path=Path("/nonexistent/forensics.json"),
        )
        assert isinstance(result, dict)
        assert "verdict" in result
        assert "timestamp_utc" in result
        assert "safety" in result

    def test_03_verdicts_supported(self):
        """Module must declare both supported verdicts."""
        import scripts.audit.archive_micro_proof_pass as mod
        src = inspect.getsource(mod)
        assert "MICRO_PROOF_ARCHIVED" in src
        assert "MICRO_PROOF_ARCHIVE_BLOCKED" in src
        assert "DEMO_MICRO_EVIDENCE_PASS" in src

    def test_04_blocks_if_no_receipt(self, tmp_path):
        """Missing receipt must produce MICRO_PROOF_ARCHIVE_BLOCKED."""
        import scripts.audit.archive_micro_proof_pass as mod
        result = mod.run_archive(
            receipt_path=tmp_path / "missing_receipt.json",
            diagnostic_path=_write_diagnostic(tmp_path),
            forensics_path=_write_pass_forensics(tmp_path),
            archive_root=tmp_path,
        )
        assert result["verdict"] == mod.MICRO_PROOF_ARCHIVE_BLOCKED
        assert any("RECEIPT" in b for b in result["blockers"])

    def test_05_blocks_if_forensics_not_pass(self, tmp_path):
        """Forensics verdict != DEMO_MICRO_EVIDENCE_PASS must block."""
        import scripts.audit.archive_micro_proof_pass as mod
        forensics = tmp_path / "post_trade_forensics.json"
        forensics.write_text(json.dumps({
            "verdict": "DEMO_MICRO_EVIDENCE_INCOMPLETE",
            "findings": {"fallback_used": False, "open_positions_count": 0},
        }), encoding="utf-8")
        result = mod.run_archive(
            receipt_path=_write_receipt(tmp_path),
            diagnostic_path=_write_diagnostic(tmp_path),
            forensics_path=forensics,
            archive_root=tmp_path,
        )
        assert result["verdict"] == mod.MICRO_PROOF_ARCHIVE_BLOCKED
        assert any("FORENSICS_NOT_PASS" in b for b in result["blockers"])

    def test_06_no_order_send(self):
        """Module source must never call mt5.order_send."""
        import scripts.audit.archive_micro_proof_pass as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\border_send\s*\(", code)
        # No MetaTrader5 import at all
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_07_no_martingale(self):
        """Module source must never reference martingale/grid/averaging/loss-based lot multipliers.

        The safety fingerprint key 'no_martingale' is the only legitimate
        occurrence of the word - we strip it before scanning for forbidden
        strategy patterns.
        """
        import scripts.audit.archive_micro_proof_pass as mod
        src = inspect.getsource(mod)
        code = _strip(src).lower()
        # Strip the legitimate safety-field name (no_martingale) first.
        code = code.replace("no_martingale", "")
        for term in ["martingale", "grid_trade", "averaging_down",
                     "loss_based_lot", "loss_multiplier"]:
            assert term not in code, f"forbidden term {term!r} present in module"

    def test_08_writes_json_and_md(self, tmp_path):
        """A successful archive must write micro_proof_summary.json + .md."""
        import scripts.audit.archive_micro_proof_pass as mod
        result = mod.run_archive(
            receipt_path=_write_receipt(tmp_path),
            diagnostic_path=_write_diagnostic(tmp_path),
            forensics_path=_write_pass_forensics(tmp_path),
            archive_root=tmp_path,
        )
        assert result["verdict"] == mod.MICRO_PROOF_ARCHIVED
        json_path = Path(result["json_path"])
        md_path = Path(result["md_path"])
        assert json_path.exists()
        assert md_path.exists()
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["verdict"] == mod.MICRO_PROOF_ARCHIVED
        assert data["safety"]["order_send_called"] is False
        assert data["safety"]["no_martingale"] is True
        md = md_path.read_text(encoding="utf-8")
        assert "Micro Proof Pass Archive Summary" in md
        assert "MICRO_PROOF_ARCHIVED" in md

    def test_09_blocks_if_fallback_used(self, tmp_path):
        """fallback_used=True must block archiving."""
        import scripts.audit.archive_micro_proof_pass as mod
        forensics = tmp_path / "post_trade_forensics.json"
        forensics.write_text(json.dumps({
            "verdict": "DEMO_MICRO_EVIDENCE_PASS",
            "findings": {
                "fallback_used": True,
                "open_positions_count": 0,
                "receipt_match_found": True,
            },
        }), encoding="utf-8")
        result = mod.run_archive(
            receipt_path=_write_receipt(tmp_path),
            diagnostic_path=_write_diagnostic(tmp_path),
            forensics_path=forensics,
            archive_root=tmp_path,
        )
        assert result["verdict"] == mod.MICRO_PROOF_ARCHIVE_BLOCKED
        assert any("FALLBACK_USED" in b for b in result["blockers"])

    def test_10_blocks_if_open_positions_remain(self, tmp_path):
        """open_positions_count > 0 must block archiving."""
        import scripts.audit.archive_micro_proof_pass as mod
        forensics = tmp_path / "post_trade_forensics.json"
        forensics.write_text(json.dumps({
            "verdict": "DEMO_MICRO_EVIDENCE_PASS",
            "findings": {
                "fallback_used": False,
                "open_positions_count": 1,
                "receipt_match_found": True,
            },
        }), encoding="utf-8")
        result = mod.run_archive(
            receipt_path=_write_receipt(tmp_path),
            diagnostic_path=_write_diagnostic(tmp_path),
            forensics_path=forensics,
            archive_root=tmp_path,
        )
        assert result["verdict"] == mod.MICRO_PROOF_ARCHIVE_BLOCKED
        assert any("UNMANAGED_OPEN_POSITION" in b for b in result["blockers"])

    def test_11_copies_all_three_artifacts(self, tmp_path):
        """Successful archive must copy receipt, diagnostic, forensics."""
        import scripts.audit.archive_micro_proof_pass as mod
        result = mod.run_archive(
            receipt_path=_write_receipt(tmp_path),
            diagnostic_path=_write_diagnostic(tmp_path),
            forensics_path=_write_pass_forensics(tmp_path),
            archive_root=tmp_path,
        )
        assert result["verdict"] == mod.MICRO_PROOF_ARCHIVED
        archive_dir = Path(result["archive_dir"])
        assert (archive_dir / "demo_micro_execution_receipt.json").exists()
        assert (archive_dir / "latest_receipt_diagnostic.json").exists()
        assert (archive_dir / "post_trade_forensics.json").exists()
        assert "demo_micro_execution_receipt.json" in result["files_archived"]
        assert "latest_receipt_diagnostic.json" in result["files_archived"]
        assert "post_trade_forensics.json" in result["files_archived"]

    def test_12_safety_fingerprint_always_present(self, tmp_path):
        """Every result (blocked or archived) must carry the safety fingerprint."""
        import scripts.audit.archive_micro_proof_pass as mod
        blocked = mod.run_archive(
            receipt_path=Path("/nonexistent/receipt.json"),
            diagnostic_path=Path("/nonexistent/diag.json"),
            forensics_path=Path("/nonexistent/forensics.json"),
        )
        assert blocked["safety"]["order_send_called"] is False
        assert blocked["safety"]["position_modified"] is False
        assert blocked["safety"]["no_martingale"] is True

        ok = mod.run_archive(
            receipt_path=_write_receipt(tmp_path),
            diagnostic_path=_write_diagnostic(tmp_path),
            forensics_path=_write_pass_forensics(tmp_path),
            archive_root=tmp_path,
        )
        assert ok["safety"]["order_send_called"] is False
        assert ok["safety"]["position_modified"] is False
        assert ok["safety"]["no_martingale"] is True

    def test_13_no_position_modification(self):
        """Module source must never call mt5.order_modify / positions_modify."""
        import scripts.audit.archive_micro_proof_pass as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        assert not re.search(r"\bmt5\.(order_modify|positions_modify)\s*\(", code)
