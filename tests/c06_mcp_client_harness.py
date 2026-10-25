"""Standalone stdio MCP client used by the pytest protocol integration tests."""
from __future__ import annotations

from datetime import timedelta
import json
import os
from pathlib import Path
import sys
import tempfile

import anyio
from mcp import Client, StdioServerParameters

from c06_subprocess_env import isolated_child_environment

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts" / "c06_mcp_server.py"
EXPECTED_TOOLS = (
    "scan_opportunities",
    "evaluate_symbol",
    "evaluate_candidates",
    "prepare_plan",
    "get_plan_status",
    "get_operations_summary",
)

from astrabot.c06.paper_mvp import PaperPlan
from astrabot.research.demo import START

FIXTURE_AS_OF = (START + timedelta(minutes=5, seconds=5)).isoformat()


def _write_network_guard(directory: Path) -> Path:
    attempt_path = directory / "network-attempts.txt"
    (directory / "sitecustomize.py").write_text(
        """
import os
import socket
import urllib.request

_LOOPBACK = ('127.0.0.1', '::1')
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex

def _is_loopback(address):
    return isinstance(address, tuple) and bool(address) and address[0] in _LOOPBACK

def _deny(*args, **kwargs):
    with open(os.environ['ASTRABOT_NETWORK_ATTEMPTS'], 'a', encoding='utf-8') as out:
        out.write('blocked\\n')
    raise OSError('network disabled in MCP subprocess test')

def _connect(sock, address):
    if _is_loopback(address):
        return _real_connect(sock, address)
    return _deny()

def _connect_ex(sock, address):
    if _is_loopback(address):
        return _real_connect_ex(sock, address)
    return _deny()

socket.create_connection = _deny
socket.getaddrinfo = _deny
socket.socket.connect = _connect
socket.socket.connect_ex = _connect_ex
socket.socket.sendto = _deny
urllib.request.urlopen = _deny
""",
        encoding="utf-8",
    )
    return attempt_path


def _server_parameters(directory: Path, fixture: str) -> StdioServerParameters:
    attempt_path = directory / "network-attempts.txt"
    return StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER), "--fixture", fixture],
        cwd=str(ROOT),
        env=isolated_child_environment(
            PYTHONPATH=str(directory),
            PYTHONDONTWRITEBYTECODE="1",
            ASTRABOT_NETWORK_ATTEMPTS=str(attempt_path),
        ),
    )


def _text(result) -> str:
    return "\n".join(block.text for block in result.content if hasattr(block, "text"))


def _json_result(result) -> dict:
    assert result.is_error is False, _text(result)
    assert isinstance(result.structured_content, dict)
    assert json.loads(_text(result)) == result.structured_content
    return result.structured_content


async def positive(directory: Path) -> str:
    async with Client(_server_parameters(directory, "positive"), read_timeout_seconds=10) as client:
        assert client.protocol_version == "2026-07-28"
        assert client.server_info is not None
        assert client.server_info.name == "AstraBot C06 Offline MCP"
        assert client.server_capabilities.resources is None
        assert client.server_capabilities.prompts is None

        discovery = await client.list_tools()
        assert tuple(tool.name for tool in discovery.tools) == EXPECTED_TOOLS
        assert len(discovery.tools) == 6
        expected_inputs = {
            "scan_opportunities": {"as_of"},
            "evaluate_symbol": {"symbol", "as_of"},
            "evaluate_candidates": {"candidate_ids"},
            "prepare_plan": {"candidate_id"},
            "get_plan_status": {"plan_id", "as_of"},
            "get_operations_summary": {"lifecycle_id"},
        }
        for tool in discovery.tools:
            assert tool.input_schema["type"] == "object"
            assert tool.input_schema["additionalProperties"] is False
            assert tool.output_schema["type"] == "object"
            assert set(tool.input_schema["properties"]) == expected_inputs[tool.name]
        assert not {
            "approve", "claim", "submit", "place_order", "execute",
            "run_command", "set_plan_status",
        }.intersection(tool.name for tool in discovery.tools)

        scan = _json_result(await client.call_tool("scan_opportunities", {"as_of": FIXTURE_AS_OF}))
        assert scan["fixture_label"] == "SYNTHETIC_FIXTURE"
        assert scan["executable"] is False
        assert scan["symbols"] == ["ALTUSDT"]

        evaluation = _json_result(await client.call_tool(
            "evaluate_symbol", {"symbol": "ALTUSDT", "as_of": FIXTURE_AS_OF}
        ))
        assert evaluation["research_decisions"] == ["RESEARCH_CANDIDATE"]
        candidate_id = evaluation["decision_ids"][0]
        candidate = _json_result(await client.call_tool(
            "evaluate_candidates", {"candidate_ids": [candidate_id]}
        ))
        assert candidate["decision"] == "RESEARCH_CANDIDATE"
        assert candidate["research_status"] == "RESEARCH_ONLY"
        assert candidate["executable"] is False

        plan_result = await client.call_tool("prepare_plan", {"candidate_id": candidate_id})
        plan_payload = _json_result(plan_result)
        plan = PaperPlan.model_validate_json(json.dumps(plan_payload))
        assert plan.verify_hash()
        assert plan.research_status == "RESEARCH_ONLY"
        assert plan.executable is False
        repeated_plan = _json_result(await client.call_tool(
            "prepare_plan", {"candidate_id": candidate_id}
        ))
        assert repeated_plan == plan_payload

        status = _json_result(await client.call_tool(
            "get_plan_status", {"plan_id": plan.plan_id, "as_of": FIXTURE_AS_OF}
        ))
        assert status["status"] == "PROPOSED_RESEARCH_ONLY"
        assert status["executable"] is False
        summary = _json_result(await client.call_tool("get_operations_summary", {}))
        assert summary["event_count"] == 0

        rejected = await client.call_tool("approve", {"plan_id": plan.plan_id})
        assert rejected.is_error is True
        assert "Unknown C06 tool" in _text(rejected)
        return client.protocol_version


async def no_trade(directory: Path) -> str:
    async with Client(_server_parameters(directory, "no-trade"), read_timeout_seconds=10) as client:
        discovery = await client.list_tools()
        assert tuple(tool.name for tool in discovery.tools) == EXPECTED_TOOLS
        evaluation = _json_result(await client.call_tool(
            "evaluate_symbol", {"symbol": "ALTUSDT", "as_of": FIXTURE_AS_OF}
        ))
        assert evaluation["research_decisions"] == ["NO_TRADE"]
        decision = _json_result(await client.call_tool(
            "evaluate_candidates", {"candidate_ids": evaluation["decision_ids"]}
        ))
        assert decision["decision"] == "NO_TRADE"
        assert decision["research_status"] == "RESEARCH_ONLY"
        assert decision["executable"] is False
        rejected = await client.call_tool(
            "prepare_plan", {"candidate_id": decision["candidate_id"]}
        )
        assert rejected.is_error is True
        assert "candidate cannot produce a paper plan" in _text(rejected)
        return client.protocol_version


async def invalid_calls(directory: Path) -> str:
    async with Client(_server_parameters(directory, "positive"), read_timeout_seconds=10) as client:
        evaluation = _json_result(await client.call_tool(
            "evaluate_symbol", {"symbol": "ALTUSDT", "as_of": FIXTURE_AS_OF}
        ))
        candidate_id = evaluation["decision_ids"][0]

        invalid_symbol = await client.call_tool(
            "evaluate_symbol", {"symbol": "BTCUSDT", "as_of": FIXTURE_AS_OF}
        )
        assert invalid_symbol.is_error is True
        assert "symbol is outside this offline fixture" in _text(invalid_symbol)

        invalid_timestamp = await client.call_tool(
            "scan_opportunities", {"as_of": "not-a-timestamp"}
        )
        assert invalid_timestamp.is_error is True
        assert "as_of" in _text(invalid_timestamp)

        wrong_snapshot = await client.call_tool(
            "scan_opportunities", {"as_of": "2025-02-01T08:05:06+00:00"}
        )
        assert wrong_snapshot.is_error is True
        assert "immutable offline evaluation snapshot" in _text(wrong_snapshot)

        bad_candidate = await client.call_tool(
            "prepare_plan", {"candidate_id": "unknown-candidate"}
        )
        assert bad_candidate.is_error is True

        unknown_plan = await client.call_tool(
            "get_plan_status", {"plan_id": "unknown-plan", "as_of": FIXTURE_AS_OF}
        )
        assert unknown_plan.is_error is True
        assert "Unknown plan ID" in _text(unknown_plan)

        override = await client.call_tool(
            "prepare_plan",
            {"candidate_id": candidate_id, "approved_max_risk_usdt": "999999"},
        )
        assert override.is_error is True
        assert "approved_max_risk_usdt" in _text(override)

        first = _json_result(await client.call_tool(
            "prepare_plan", {"candidate_id": candidate_id}
        ))
        second = _json_result(await client.call_tool(
            "prepare_plan", {"candidate_id": candidate_id}
        ))
        assert first == second
        assert first["research_status"] == "RESEARCH_ONLY"
        assert first["executable"] is False
        return client.protocol_version


async def run_scenario(scenario: str) -> None:
    with tempfile.TemporaryDirectory(prefix="astrabot-c06-mcp-") as temp:
        directory = Path(temp)
        attempt_path = _write_network_guard(directory)
        os.environ["ASTRABOT_NETWORK_ATTEMPTS"] = str(attempt_path)
        sys.path.insert(0, str(directory))
        # Import the guard in the client process too. The event loop uses a local
        # socketpair, but all outbound connect/DNS calls remain denied.
        __import__("sitecustomize")
        with anyio.fail_after(20):
            protocol = await {
                "positive": positive,
                "no-trade": no_trade,
                "invalid": invalid_calls,
            }[scenario](directory)
        assert not attempt_path.exists(), "client or MCP server attempted an outbound connection"
    print(f"MCP_PROTOCOL_TESTS_PASSED scenario={scenario} protocol={protocol} tools=6")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"positive", "no-trade", "invalid"}:
        raise SystemExit("usage: c06_mcp_client_harness.py positive|no-trade|invalid")
    anyio.run(run_scenario, sys.argv[1])
