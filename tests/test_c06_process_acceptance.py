from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from c06_subprocess_env import isolated_child_environment


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "c06_acceptance_demo.py"


def test_end_to_end_restartable_multiprocess_acceptance(tmp_path):
    state_dir = tmp_path / "c06-synthetic-only"
    result = subprocess.run([sys.executable, str(SCRIPT), "--fake-only",
        "--state-dir", str(state_dir)], cwd=ROOT,
        env=isolated_child_environment(PYTHONDONTWRITEBYTECODE="1"),
        capture_output=True, text=True, timeout=240, check=False)
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    report = json.loads(result.stdout)
    assert report["fixture"] == "SYNTHETIC_ONLY"
    assert report["mcp_tool_names"] == [
        "scan_opportunities", "evaluate_symbol", "evaluate_candidates", "prepare_plan",
        "get_plan_status", "get_operations_summary"]
    assert report["owner"]["concurrent_consume_processes"] == 2
    assert report["owner"]["consume"] == "CONSUMED"
    assert report["supervisor"]["disconnected_exit_write_delta"] == 0
    assert report["supervisor"]["journal_reader_during_supervisor_recovery"] == "VERIFIED"
    assert report["supervisor"]["terminal_position_state"] == "FLAT_RECONCILED"
    assert report["supervisor"]["terminal_plan_status"] == "CLOSED_RECONCILED"
    assert report["supervisor"]["unknown_exit_management_intents"]
    assert report["journal_role"]["verification_state"] == "VERIFIED"
    assert report["negative"]["no_trade"] == "NO_TRADE_NO_PROPOSAL_NO_VENUE_STORE"
    assert report["negative"]["rejected"]["venue_write_count"] == 0
    assert report["negative"]["expired"]["venue_write_count"] == 0
    assert report["negative"]["process_faults"]["unknown_entry_absent"]["resubmission"] == "HALTED"
    assert report["negative"]["process_faults"]["rejected_stop_and_12h_emergency"]["position_state"] == "FLAT_RECONCILED"
    assert report["negative"]["process_faults"]["late_fill"]["position_state"] == "RECONCILING"
    assert report["network_attempts"] == 0
    assert report["owner_openbot_acceptance"] == "OWNER_OPENBOT_ACCEPTANCE_PENDING"
    assert (state_dir / ".astrabot-c06-synthetic").read_text(encoding="utf-8") == "SYNTHETIC_ONLY\n"
