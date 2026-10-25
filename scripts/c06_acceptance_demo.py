#!/usr/bin/env python3
"""Run the C06 offline acceptance path across real MCP and CLI subprocesses."""
from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts" / "c06_mcp_server.py"
OWNER = ROOT / "scripts" / "c06_fixture_owner.py"
SUPERVISOR = ROOT / "scripts" / "c06_fake_supervisor.py"
ROLE = ROOT / "scripts" / "c06_fixture_role_summary.py"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))

from mcp import Client, StdioServerParameters
from c06_subprocess_env import isolated_child_environment
from c06_fixture_paths import prepare_synthetic_state_dir, reset_synthetic_state_dir
from astrabot.research.demo import START

TOOLS = ("scan_opportunities", "evaluate_symbol", "evaluate_candidates",
         "prepare_plan", "get_plan_status", "get_operations_summary")
AS_OF = (START + timedelta(minutes=5, seconds=5)).isoformat()
ATTEMPTS: Path | None = None


def _block_network(guard_dir: Path) -> Path:
    global ATTEMPTS
    attempts = guard_dir / "network-attempts.txt"
    (guard_dir / "sitecustomize.py").write_text("""
import os, socket, urllib.request
_LOOPBACK = ('127.0.0.1', '::1')
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
def _deny(*args, **kwargs):
    with open(os.environ['ASTRABOT_NETWORK_ATTEMPTS'], 'a', encoding='utf-8') as out:
        out.write('blocked\\\\n')
    raise OSError('network disabled in C06 acceptance harness')
def _loopback(address):
    return isinstance(address, tuple) and bool(address) and address[0] in _LOOPBACK
def _connect(sock, address):
    return _real_connect(sock, address) if _loopback(address) else _deny()
def _connect_ex(sock, address):
    return _real_connect_ex(sock, address) if _loopback(address) else _deny()
socket.create_connection = _deny
socket.getaddrinfo = _deny
socket.socket.connect = _connect
socket.socket.connect_ex = _connect_ex
socket.socket.sendto = _deny
urllib.request.urlopen = _deny
""", encoding="utf-8")
    ATTEMPTS = attempts
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    def deny(*args, **kwargs):
        attempts.write_text("blocked\\n", encoding="utf-8")
        raise OSError("network disabled in C06 acceptance harness")
    def loopback(address):
        return isinstance(address, tuple) and bool(address) and address[0] in {"127.0.0.1", "::1"}
    socket.create_connection = deny
    socket.getaddrinfo = deny
    socket.socket.connect = lambda sock, address: (
        real_connect(sock, address) if loopback(address) else deny())
    socket.socket.connect_ex = lambda sock, address: (
        real_connect_ex(sock, address) if loopback(address) else deny())
    socket.socket.sendto = deny
    urllib.request.urlopen = deny
    return attempts


def _env(guard_dir: Path) -> dict[str, str]:
    pythonpath = os.pathsep.join(map(str, (guard_dir, ROOT / "src", ROOT / "tests", ROOT / "scripts")))
    return isolated_child_environment(PYTHONPATH=pythonpath, PYTHONDONTWRITEBYTECODE="1",
        ASTRABOT_NETWORK_ATTEMPTS=str(ATTEMPTS))


def _params(state_dir: Path, guard_dir: Path, fixture: str = "positive"):
    return StdioServerParameters(command=sys.executable,
        args=[str(SERVER), "--fixture", fixture, "--state-dir", str(state_dir)],
        cwd=str(ROOT), env=_env(guard_dir))


def _json(result) -> dict:
    body = "\n".join(item.text for item in result.content if hasattr(item, "text"))
    if result.is_error or not isinstance(result.structured_content, dict):
        raise RuntimeError(f"MCP call failed: {body}")
    if json.loads(body) != result.structured_content:
        raise RuntimeError("MCP structured and text results disagree")
    return result.structured_content


async def _research(state_dir: Path, guard_dir: Path, fixture: str = "positive") -> dict:
    async with Client(_params(state_dir, guard_dir, fixture), read_timeout_seconds=15) as client:
        names = tuple(tool.name for tool in (await client.list_tools()).tools)
        if names != TOOLS:
            raise RuntimeError(f"expected exactly the six C06 tools, found {names}")
        if fixture == "no-trade":
            evaluation = _json(await client.call_tool("evaluate_symbol",
                {"symbol": "ALTUSDT", "as_of": AS_OF}))
            decision = _json(await client.call_tool("evaluate_candidates",
                {"candidate_ids": evaluation["decision_ids"]}))
            rejected = await client.call_tool("prepare_plan", {"candidate_id": "no-trade-candidate"})
            return {"tool_names": names, "evaluation": evaluation, "decision": decision,
                "proposal_rejected": rejected.is_error}
        scan = _json(await client.call_tool("scan_opportunities", {"as_of": AS_OF}))
        evaluation = _json(await client.call_tool("evaluate_symbol",
            {"symbol": "ALTUSDT", "as_of": AS_OF}))
        candidate = _json(await client.call_tool("evaluate_candidates",
            {"candidate_ids": evaluation["decision_ids"]}))
        proposal = _json(await client.call_tool("prepare_plan",
            {"candidate_id": candidate["candidate_id"]}))
        initial_status = _json(await client.call_tool("get_plan_status",
            {"plan_id": proposal["plan_id"], "as_of": AS_OF}))
        initial_journal = _json(await client.call_tool("get_operations_summary", {}))
        return {"tool_names": names, "scan": scan, "evaluation": evaluation,
            "candidate": candidate, "proposal": proposal, "status": initial_status,
            "journal": initial_journal}


def _command(script: Path, state_dir: Path, guard_dir: Path, *args: str,
             expected_success: bool = True) -> dict | str:
    process = subprocess.run([sys.executable, str(script), "--fake-only",
        "--state-dir", str(state_dir), *args], cwd=ROOT, env=_env(guard_dir),
        capture_output=True, text=True, timeout=45, check=False)
    if expected_success and process.returncode:
        raise RuntimeError(f"{script.name}: {process.stderr.strip()}")
    if not expected_success and not process.returncode:
        raise RuntimeError(f"{script.name} unexpectedly succeeded")
    return json.loads(process.stdout) if process.returncode == 0 else process.stderr.strip()


def _concurrent_consumes(state_dir: Path, guard_dir: Path, plan_id: str) -> list[dict | str]:
    command = [sys.executable, str(OWNER), "--fake-only", "--state-dir",
        str(state_dir), "consume", plan_id]
    children = [subprocess.Popen(command, cwd=ROOT, env=_env(guard_dir),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    results = []
    for child in children:
        stdout, stderr = child.communicate(timeout=45)
        if child.returncode == 0:
            results.append(json.loads(stdout))
        else:
            results.append(stderr.strip())
    statuses = [item.get("status") for item in results if isinstance(item, dict)]
    if statuses.count("CONSUMED") != 1 or any(
        status not in {"CONSUMED", "ALREADY_CONSUMED"} for status in statuses):
        raise RuntimeError(f"concurrent one-use claims did not yield one winner: {results}")
    return results


def _parallel_supervisor_and_reader(state_dir: Path, guard_dir: Path,
                                    lifecycle_id: str) -> dict:
    supervisor = [sys.executable, str(SUPERVISOR), "--fake-only", "--state-dir",
        str(state_dir), "--coordinator-unavailable", "tick"]
    reader = [sys.executable, str(ROLE), "--fake-only", "journal", "--state-dir",
        str(state_dir), "--lifecycle-id", lifecycle_id]
    writer_child = subprocess.Popen(supervisor, cwd=ROOT, env=_env(guard_dir),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    reader_child = subprocess.Popen(reader, cwd=ROOT, env=_env(guard_dir),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    writer_out, writer_err = writer_child.communicate(timeout=45)
    reader_out, reader_err = reader_child.communicate(timeout=45)
    if writer_child.returncode or reader_child.returncode:
        raise RuntimeError(f"concurrent writer/reader failed: {writer_err} {reader_err}")
    report = json.loads(reader_out)
    if report["verification_state"] not in {"VERIFIED", "UNAVAILABLE"}:
        raise RuntimeError(f"journal reader observed an inconsistent transition: {report}")
    return {"supervisor": json.loads(writer_out), "reader": report}


def _journal_role(state_dir: Path, guard_dir: Path, lifecycle_id: str) -> dict:
    process = subprocess.run([sys.executable, str(ROLE), "--fake-only", "journal",
        "--state-dir", str(state_dir), "--lifecycle-id", lifecycle_id], cwd=ROOT,
        env=_env(guard_dir), capture_output=True, text=True, timeout=20, check=False)
    if process.returncode:
        raise RuntimeError(f"Journal role CLI failed: {process.stderr.strip()}")
    return json.loads(process.stdout)


def _clean_fixture(path: Path) -> Path:
    path = prepare_synthetic_state_dir(path)
    if any((path / name).exists() for name in ("c06_state.sqlite", "owner.sqlite", "venue.sqlite")):
        raise FileExistsError("acceptance needs a clean marked directory; choose an empty fixture path")
    return path


async def _approved_consumed_fixture(state_dir: Path, guard_dir: Path) -> dict:
    state_dir = prepare_synthetic_state_dir(state_dir)
    research = await _research(state_dir, guard_dir)
    plan_id = research["proposal"]["plan_id"]
    _command(OWNER, state_dir, guard_dir, "approve", plan_id)
    _command(OWNER, state_dir, guard_dir, "consume", plan_id)
    return {"research": research, "plan_id": plan_id}


async def _process_fault_scenarios(guard_dir: Path) -> dict:
    results = {}

    # A missing entry acknowledgment with no correlated venue record remains
    # UNKNOWN_SUBMISSION and blocks resubmission after the process restarts.
    with tempfile.TemporaryDirectory(prefix="astrabot-c06-entry-unknown-") as temp:
        state_dir = Path(temp) / "fixture"
        prepared = await _approved_consumed_fixture(state_dir, guard_dir)
        first = _command(SUPERVISOR, state_dir, guard_dir, "submit-entry", "--entry-absent-ack")
        second = _command(SUPERVISOR, state_dir, guard_dir, "submit-entry", expected_success=False)
        status = _command(SUPERVISOR, state_dir, guard_dir, "status")
        journal = _journal_role(state_dir, guard_dir, status["lifecycle_id"])
        if first["entry_intent_state"] != "UNKNOWN_SUBMISSION" or status["venue_write_count"] != 0:
            raise RuntimeError("absent unknown entry was not retained without a venue write")
        if "reconciliation failed" not in second.lower():
            raise RuntimeError("ambiguous absent entry did not halt the fresh supervisor")
        if journal["readiness"] != "UNRESOLVED" or journal["reservation_status"] != "UNKNOWN":
            raise RuntimeError("unknown entry did not keep its durable risk reservation unresolved")
        results["unknown_entry_absent"] = {"state": status["entry_intent_state"],
            "venue_write_count": status["venue_write_count"],
            "reservation_status": journal["reservation_status"], "resubmission": "HALTED"}

    # A rejected stop sets the C01 fault halt. Only the already-correlated
    # reduce-only exit may proceed through close-only recovery.
    with tempfile.TemporaryDirectory(prefix="astrabot-c06-stop-rejected-") as temp:
        state_dir = Path(temp) / "fixture"
        await _approved_consumed_fixture(state_dir, guard_dir)
        _command(SUPERVISOR, state_dir, guard_dir, "submit-entry")
        _command(SUPERVISOR, state_dir, guard_dir, "fill-entry", "--stop-result", "REJECTED",
            expected_success=False)
        unsafe = _command(SUPERVISOR, state_dir, guard_dir, "status")
        emergency = _command(SUPERVISOR, state_dir, guard_dir, "emergency",
            "--coordinator-unavailable")
        final = _command(SUPERVISOR, state_dir, guard_dir, "fill-exit",
            "--coordinator-unavailable")
        if unsafe["protection"] != "MISSING" or not emergency["fault_halt"]:
            raise RuntimeError("rejected protection did not fail closed into emergency handling")
        if final["position_state"] != "FLAT_RECONCILED":
            raise RuntimeError("correlated reduce-only close did not reconcile after stop rejection")
        results["rejected_stop_and_12h_emergency"] = {
            "protection": unsafe["protection"], "fault_halt": emergency["fault_halt"],
            "position_state": final["position_state"]}

    # A partial IOC entry is canceled by the C01 stale-intent timer. A later
    # venue-confirmed fill after risk finalization is discovered and halted.
    with tempfile.TemporaryDirectory(prefix="astrabot-c06-late-fill-") as temp:
        state_dir = Path(temp) / "fixture"
        await _approved_consumed_fixture(state_dir, guard_dir)
        _command(SUPERVISOR, state_dir, guard_dir, "submit-entry")
        partial = _command(SUPERVISOR, state_dir, guard_dir, "partial-entry")
        owner = _command(OWNER, state_dir, guard_dir, "show", partial["plan_id"])
        from datetime import datetime
        submitted_at = datetime.fromisoformat(owner["entry_intent"]["submitted_at"])
        _command(SUPERVISOR, state_dir, guard_dir, "tick", "--at",
            (submitted_at + timedelta(seconds=11)).isoformat())
        late = _command(SUPERVISOR, state_dir, guard_dir, "late-entry-fill")
        if not late["fault_halt"] or late["position_state"] != "RECONCILING":
            raise RuntimeError("late entry fill after finalization did not halt reconciliation")
        results["late_fill"] = {"fault_halt": late["fault_halt"],
            "position_state": late["position_state"], "protection": late["protection"]}

    return results


async def _run(state_dir: Path, guard_dir: Path) -> dict:
    state_dir = _clean_fixture(state_dir)
    # MCP subprocess 1 creates a plan; closing this Client stops the server.
    research = await _research(state_dir, guard_dir)
    proposal = research["proposal"]
    if proposal["executable"] or proposal["research_status"] != "RESEARCH_ONLY":
        raise RuntimeError("MCP proposal crossed the research-only boundary")
    plan_id = proposal["plan_id"]

    # These commands are separate fixture-owner processes. The inspection must
    # be read-only, and duplicate approve/consume calls cannot reuse a nonce.
    listed = _command(OWNER, state_dir, guard_dir, "list")
    owner_venue_before_show = ((state_dir / "owner.sqlite").exists(),
        (state_dir / "venue.sqlite").exists())
    inspected = _command(OWNER, state_dir, guard_dir, "show", plan_id)
    if owner_venue_before_show != ((state_dir / "owner.sqlite").exists(),
        (state_dir / "venue.sqlite").exists()):
        raise RuntimeError("owner inspection initialized or modified C01 stores")
    approved = _command(OWNER, state_dir, guard_dir, "approve", plan_id)
    approved_again = _command(OWNER, state_dir, guard_dir, "approve", plan_id)
    concurrent_consumes = _concurrent_consumes(state_dir, guard_dir, plan_id)
    consumed_again = _command(OWNER, state_dir, guard_dir, "consume", plan_id)
    if consumed_again["status"] != "ALREADY_CONSUMED":
        raise RuntimeError("duplicate owner consume was not rejected")
    if consumed_again["venue_write_count"]:
        raise RuntimeError("one-use claim wrote to the fake venue")
    consumed = next(item for item in concurrent_consumes
        if isinstance(item, dict) and item["status"] == "CONSUMED")
    if consumed["venue_write_count"]:
        raise RuntimeError("concurrent C01 one-use claim wrote to the fake venue")

    # Every supervisor step is a new process reopening the same owner, venue,
    # plan and machine-event databases.
    submitted = _command(SUPERVISOR, state_dir, guard_dir, "submit-entry",
        "--entry-result", "UNKNOWN")
    if submitted["entry_intent_state"] != "UNKNOWN_SUBMISSION":
        raise RuntimeError("unknown entry acknowledgment was not retained durably")
    submitted_again = _command(SUPERVISOR, state_dir, guard_dir, "submit-entry")
    if submitted["venue_write_count"] != submitted_again["venue_write_count"]:
        raise RuntimeError("repeated entry supervision created a duplicate venue write")
    if submitted_again["entry_intent_state"] != "RECONCILED":
        raise RuntimeError("correlated unknown entry order was not reconciled from fake venue truth")
    filled = _command(SUPERVISOR, state_dir, guard_dir, "fill-entry",
        "--coordinator-unavailable")
    partial = _command(SUPERVISOR, state_dir, guard_dir, "partial-tp1",
        "--coordinator-unavailable")
    if partial["first_fill_at"] != filled["first_fill_at"] or partial["protection"] != "VERIFIED":
        raise RuntimeError("partial exit altered first-fill time or lost verified protection")
    concurrent_read = _parallel_supervisor_and_reader(state_dir, guard_dir, partial["lifecycle_id"])
    disconnected = _command(SUPERVISOR, state_dir, guard_dir, "disconnect-exit",
        "--coordinator-unavailable", "--journal-unavailable")
    if disconnected["venue_write_delta"] != 0 or not disconnected["exit_request"]:
        raise RuntimeError("disconnected exit was not durably retained without venue IO")
    exit_step = _command(SUPERVISOR, state_dir, guard_dir, "time-exit",
        "--coordinator-unavailable", "--journal-unavailable", "--unknown-exit-ack")
    time_exit = _command(SUPERVISOR, state_dir, guard_dir, "status")
    if (time_exit["exit_request"]["status"] != "ORDER_OBSERVED"
        or not time_exit["exit_request"].get("exchange_order_id")
        or time_exit["venue_write_count"] != disconnected["venue_write_count"] + 1):
        raise RuntimeError(f"unknown exit acknowledgment was not retained: step={exit_step}, status={time_exit}, disconnected={disconnected}")
    observed_exit_id = time_exit["exit_request"]["client_order_id"]
    reconciled_exit_intents = [item for item in time_exit["management_intents"]
        if item["client_order_id"] == observed_exit_id
        and item["status"] == "RECONCILED"
        and item.get("exchange_order_id") == time_exit["exit_request"]["exchange_order_id"]]
    if not reconciled_exit_intents:
        raise RuntimeError("unknown exit intent did not reconcile to its correlated venue order")
    final = _command(SUPERVISOR, state_dir, guard_dir, "fill-exit",
        "--coordinator-unavailable", "--journal-unavailable")
    if final["position_state"] != "FLAT_RECONCILED" or final["position_quantity"] not in {"0", "0.0"}:
        raise RuntimeError("fake lifecycle did not reach verified FLAT_RECONCILED")
    resumed_journal = _command(SUPERVISOR, state_dir, guard_dir, "tick",
        "--coordinator-unavailable")
    if resumed_journal["plan_status"] != "CLOSED_RECONCILED":
        raise RuntimeError("C06 plan mirror did not recover from the supervisor journal outage")

    # MCP subprocess 2 reopens status and events after the supervisor exits.
    async with Client(_params(state_dir, guard_dir), read_timeout_seconds=15) as client:
        status = _json(await client.call_tool("get_plan_status",
            {"plan_id": plan_id, "as_of": AS_OF}))
        events = _json(await client.call_tool("get_operations_summary",
            {"lifecycle_id": final["lifecycle_id"]}))
        repeated = await client.call_tool("prepare_plan",
            {"candidate_id": research["candidate"]["candidate_id"]})
        if not repeated.is_error:
            raise RuntimeError("finalized immutable plan was reused through MCP")
    if status["status"] != "CLOSED_RECONCILED" or events["event_count"] < 2:
        raise RuntimeError("fresh MCP process did not observe the durable terminal outcome")
    journal = _journal_role(state_dir, guard_dir, final["lifecycle_id"])
    if journal["verification_state"] != "VERIFIED" or journal["lifecycle_state"] != "FLAT_RECONCILED":
        raise RuntimeError("read-only Journal role did not verify the closed lifecycle")

    # Separate NO_TRADE case. No proposal means there is no owner approval path.
    with tempfile.TemporaryDirectory(prefix="astrabot-c06-no-trade-") as temp:
        no_trade_dir = prepare_synthetic_state_dir(Path(temp) / "fixture")
        no_trade = await _research(no_trade_dir, guard_dir, "no-trade")
        no_trade_list = _command(OWNER, no_trade_dir, guard_dir, "list")
        if (no_trade["decision"]["decision"] != "NO_TRADE" or no_trade_list["proposals"]
            or (no_trade_dir / "venue.sqlite").exists()):
            raise RuntimeError("NO_TRADE produced proposal, owner approval or venue state")

    # Rejection and expiry are independent proposals in disposable state dirs.
    negatives = {}
    for choice in ("reject", "expire"):
        with tempfile.TemporaryDirectory(prefix=f"astrabot-c06-{choice}-") as temp:
            negative_dir = prepare_synthetic_state_dir(Path(temp) / "fixture")
            negative_research = await _research(negative_dir, guard_dir)
            negative_plan = negative_research["proposal"]
            decision = _command(OWNER, negative_dir, guard_dir, choice, negative_plan["plan_id"])
            inspection = _command(OWNER, negative_dir, guard_dir, "show", negative_plan["plan_id"])
            negatives[choice] = {"status": decision["status"],
                "approval_present": inspection["approval_present"],
                "venue_write_count": inspection["venue_write_count"]}
            if inspection["approval_present"] or inspection["venue_write_count"]:
                raise RuntimeError(f"{choice} case acquired approval or wrote to fake venue")

    faults = await _process_fault_scenarios(guard_dir)

    return {
        "fixture": "SYNTHETIC_ONLY", "mcp_tool_names": list(research["tool_names"]),
        "plan_id": plan_id, "plan_hash": proposal["immutable_hash"],
        "owner": {"listed": len(listed["proposals"]), "show_read_only": True,
            "approval": approved["status"], "duplicate_approval": approved_again["status"],
            "consume": consumed["status"], "duplicate_consume": consumed_again["status"],
            "concurrent_consume_processes": len(concurrent_consumes)},
        "supervisor": {"first_fill_at": filled["first_fill_at"],
            "partial_quantity": partial["position_quantity"],
            "coordinator_unavailable": True,
            "disconnected_exit_write_delta": disconnected["venue_write_delta"],
            "journal_reader_during_supervisor_recovery": concurrent_read["reader"]["verification_state"],
            "journal_step_state_during_outage": final["journal_state"],
            "unknown_exit_ack_reconciled": time_exit["exit_request"]["status"],
            "unknown_exit_management_intents": reconciled_exit_intents,
            "unknown_exit_write_count": time_exit["venue_write_count"],
            "journal_resumed_plan_status": resumed_journal["plan_status"],
            "terminal_position_state": final["position_state"],
            "terminal_plan_status": status["status"]},
        "journal_role": {"verification_state": journal["verification_state"],
            "event_count": journal["event_count"], "event_digest": journal["event_digest"]},
        "negative": {"no_trade": "NO_TRADE_NO_PROPOSAL_NO_VENUE_STORE",
            "rejected": negatives["reject"], "expired": negatives["expire"],
            "process_faults": faults},
        "owner_openbot_acceptance": "OWNER_OPENBOT_ACCEPTANCE_PENDING",
        "network_attempts": 0,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake-only", action="store_true",
        help="required acknowledgement that the workflow is synthetic")
    parser.add_argument("--state-dir", type=Path,
        help="clean dedicated synthetic directory; omitted uses a temporary directory")
    parser.add_argument("--reset", action="store_true",
        help="delete only known SQLite files in an existing marked fixture directory")
    args = parser.parse_args(argv)
    if not args.fake_only:
        parser.error("--fake-only is required; this harness cannot access Binance")
    if args.reset:
        if args.state_dir is None:
            parser.error("--reset requires an explicit --state-dir")
        reset_synthetic_state_dir(args.state_dir)
    with tempfile.TemporaryDirectory(prefix="astrabot-c06-network-guard-") as temp:
        guard_dir = Path(temp)
        attempts = _block_network(guard_dir)
        if args.state_dir:
            report = asyncio.run(_run(args.state_dir, guard_dir))
        else:
            with tempfile.TemporaryDirectory(prefix="astrabot-c06-acceptance-") as data:
                report = asyncio.run(_run(Path(data) / "fixture", guard_dir))
        if attempts.exists():
            count = len(attempts.read_text(encoding="utf-8").splitlines())
            raise RuntimeError(f"offline harness attempted outbound networking {count} time(s)")
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
