from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests" / "c06_mcp_client_harness.py"


def _run_protocol_scenario(scenario: str) -> None:
    result = subprocess.run(
        [sys.executable, str(HARNESS), scenario],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert f"MCP_PROTOCOL_TESTS_PASSED scenario={scenario}" in result.stdout


def test_mcp_stdio_discovery_schemas_and_positive_fixture():
    _run_protocol_scenario("positive")


def test_no_trade_fixture_cannot_produce_a_plan():
    _run_protocol_scenario("no-trade")


def test_malformed_inputs_and_numeric_override_fail_closed():
    _run_protocol_scenario("invalid")
