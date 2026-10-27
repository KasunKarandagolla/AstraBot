"""Acceptance of the newly combined operator flow, across the real six-tool MCP."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys

import pytest

from astrabot.c06.paper_mvp import EventJournal, PlanRegistry, C06ToolGateway
from astrabot.c06.research_operator import load_operator_gateway
from astrabot.data.models import config_hash
from c06_subprocess_env import isolated_child_environment

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT/'scripts/c05_integrated_research.py'


def command(output, mode, *flags, success=True):
    result = subprocess.run([sys.executable, str(CLI), '--mode', mode,
        '--output-dir', str(output), *map(str, flags)], cwd=ROOT,
        env=isolated_child_environment(PYTHONDONTWRITEBYTECODE='1'),
        capture_output=True, text=True, timeout=180)
    assert (result.returncode == 0) == success, result.stdout + result.stderr
    return result


@pytest.fixture(scope='module')
def operator_outputs(tmp_path_factory):
    root = tmp_path_factory.mktemp('rc1')
    command(root, 'authentic')
    command(root, 'synthetic')
    return root


def packet(root, mode):
    value = json.loads((root/mode/'OPERATOR_PACKET.json').read_text())
    digest = value.pop('content_sha256')
    assert config_hash(value) == digest
    return value


def test_authentic_decision_flows_to_operator_with_sources_and_no_proposal(operator_outputs):
    report = packet(operator_outputs, 'authentic')
    assert report['decision'] == 'NO_TRADE' and report['status'] == 'BLOCKED_BY_DATA'
    assert report['evidence_class'] == 'OBSERVED_HISTORICAL_RESEARCH'
    assert report['phase_gate_credit_percent'] == 45
    assert set(report['qualified_policy_registry']) == {'T1','R1','B1'}
    assert all(p['status'] == 'RESEARCH_ONLY' and not p['executable']
        for p in report['qualified_policy_registry'].values())
    assert len(report['journal']['events']) == 2
    btc = next(r for r in report['decisions'] if r['symbol'] == 'BTCUSDT')
    assert len(btc['source_bars']) == 24
    assert len({(b['symbol'], b['interval'], b['source_record_id']) for b in btc['source_bars']}) == 24
    assert all(b['fidelity'] != 'SYNTHETIC_FIXTURE' for b in btc['source_bars'])
    assert set(btc['features']) == {f'A{i:02}' for i in range(1,11)}
    assert 'METADATA_MISSING' in btc['scan']['opportunities'][0]['reasons']
    assert btc['proposal_status'] == 'BLOCKED_RESEARCH_ONLY'
    assert {d['strategy_id'] for d in btc['decisions']} == {'T1','R1','B1'}
    summary = (operator_outputs/'authentic/OWNER_SUMMARY.md').read_text()
    assert all(e['event_id'] in summary for e in report['journal']['events'])
    assert not list((operator_outputs/'authentic').rglob('*.sqlite'))


def test_complete_fake_lifecycle_retains_durable_approval_protection_and_deadlines(operator_outputs):
    report = packet(operator_outputs, 'synthetic')
    assert report['evidence_class'] == 'SYNTHETIC_ONLY' and report['network_attempts'] == 0
    case = report['scenarios']['positive']
    assert case['consume']['status'] == 'CONSUMED'
    assert case['duplicate_consume']['status'] == 'ALREADY_CONSUMED'
    steps = {s['action']: s for s in case['steps']}
    assert steps['partial-entry']['position_quantity'] == '5'
    assert steps['partial-tp1']['position_quantity'] == '3.0'
    assert steps['partial-entry']['protection'] == steps['partial-tp1']['protection'] == 'VERIFIED'
    assert steps['partial-entry']['first_fill_at'] == steps['partial-tp1']['first_fill_at']
    first = datetime.fromisoformat(steps['partial-entry']['first_fill_at'])
    assert datetime.fromisoformat(steps['time-exit']['deadline_11h55']) == first+timedelta(hours=11,minutes=55)
    assert datetime.fromisoformat(steps['emergency']['emergency_boundary_12h']) == first+timedelta(hours=12)
    assert 'TIME_EXIT_BREACH' in case['owner_state']['faults']
    assert case['final']['position_state'] == 'FLAT_RECONCILED'
    assert case['final']['position_quantity'] == case['final']['venue_position'] == '0.0'
    assert not case['final']['unresolved_entry_intents'] and not case['final']['unresolved_management_intents']
    state = operator_outputs/'synthetic/state/positive/c06_state.sqlite'
    assert len(PlanRegistry(state)) == 1
    assert len(EventJournal(state).events) == len(case['journal'])
    assert case['journal_role']['verification_state'] == 'VERIFIED'
    for event in report['journal']['events']:
        assert event['event_id'] in (operator_outputs/'synthetic/OWNER_SUMMARY.md').read_text()
    for name in ('rejected', 'expired', 'stale_input'):
        negative = report['scenarios'][name]
        assert negative['consume_refused']
        assert negative.get('venue_write_count', negative.get('result', {}).get('venue_write_count')) == 0
    failed = report['scenarios']['critical_protection_failure']
    assert failed['final']['position_state'] == 'FLAT_RECONCILED'
    assert 'MISSING_PROTECTION' in failed['owner_state']['faults']
    stale = report['scenarios']['stale_input']
    assert datetime.fromisoformat(stale['observed_at']) < datetime.fromisoformat(stale['proposal_expires_at'])


def test_same_commands_reproduce_exact_packets_and_preserve_existing_state(operator_outputs, tmp_path):
    for mode in ('authentic', 'synthetic'):
        command(tmp_path, mode)
        assert (tmp_path/mode/'OPERATOR_PACKET.json').read_bytes() == (
            operator_outputs/mode/'OPERATOR_PACKET.json').read_bytes()
        assert (tmp_path/mode/'EVENTS.jsonl').read_bytes() == (operator_outputs/mode/'EVENTS.jsonl').read_bytes()
    before = (operator_outputs/'synthetic/OPERATOR_PACKET.json').read_bytes()
    command(operator_outputs, 'synthetic', success=False)
    assert before == (operator_outputs/'synthetic/OPERATOR_PACKET.json').read_bytes()


def test_authentic_snapshot_serves_six_tools_after_process_restart(operator_outputs):
    snapshot = operator_outputs/'authentic/BTCUSDT_MCP_SNAPSHOT.json'
    at = json.loads(snapshot.read_text())['as_of']
    result = subprocess.run([sys.executable, str(ROOT/'tests/rc1_mcp_client_harness.py'), str(snapshot)],
        cwd=ROOT, env=isolated_child_environment(PYTHONPATH=str(ROOT/'src')),
        capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'RC1_HISTORICAL_MCP_PASS' in result.stdout


def test_tampered_or_synthetic_snapshots_and_mixed_modes_fail_closed(operator_outputs, tmp_path):
    original = json.loads((operator_outputs/'authentic/BTCUSDT_MCP_SNAPSHOT.json').read_text())
    original['data']['candles_1h'][0]['close'] = '999999'
    target = tmp_path/'changed.json'
    target.write_text(json.dumps(original))
    with pytest.raises(ValueError, match='integrity'):
        load_operator_gateway(target)
    original = json.loads((operator_outputs/'authentic/BTCUSDT_MCP_SNAPSHOT.json').read_text())
    original['data']['candles_1h'][0]['fidelity'] = 'SYNTHETIC_FIXTURE'
    original.pop('content_sha256')
    original['content_sha256'] = config_hash(original)
    target.write_text(json.dumps(original))
    with pytest.raises(ValueError, match='synthetic'):
        load_operator_gateway(target)
    command(tmp_path, 'synthetic', '--c02-panel', ROOT/'research/c02_panel', success=False)
    command(tmp_path, 'authentic', '--c02-panel', ROOT/'research/c02_panel', '--start',
        '2024-10-30T00:00:00Z', '--end', '2024-10-29T00:00:00Z', success=False)
