"""Operator scenario assembly over C06 MCP, owner and supervisor; no simulator."""
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

from astrabot.c06.paper_mvp import EventJournal
from astrabot.data.models import stable_id
from astrabot.research.integrated import safe
from c06_acceptance_demo import (_block_network, _command, _research,
    OWNER, SUPERVISOR, _journal_role)
from c06_fixture_owner import _read_store
from c06_fixture_paths import prepare_synthetic_state_dir


def _audit_step(state_dir, result):
    journal = EventJournal(state_dir/'c06_state.sqlite')
    plan_id = result['plan_id']
    lifecycle = stable_id('c06.fake_lifecycle', plan_id)
    journal.append(occurred_at=journal.events[-1].occurred_at,
        actor='offline_test_driver', event_type='RC1_OPERATOR_OBSERVATION',
        plan_id=plan_id, lifecycle_id=lifecycle, details={
            'evidence_class': 'SYNTHETIC_ONLY',
            **{k: result[k] for k in ('action', 'position_state', 'position_quantity',
                'first_fill_at', 'protection', 'venue_write_count', 'entry_intent_state',
                'deadline_11h55', 'emergency_boundary_12h', 'fault_halt') if k in result}})


async def _scenario(root, guard, name):
    state_dir = prepare_synthetic_state_dir(root/name)
    research = await _research(state_dir, guard)
    plan = research['proposal']
    pid = plan['plan_id']
    steps = []
    if name in ('rejected', 'expired'):
        result = _command(OWNER, state_dir, guard, 'reject' if name == 'rejected' else 'expire', pid)
        refused = _command(OWNER, state_dir, guard, 'consume', pid, expected_success=False)
        assert result['venue_write_count'] == 0 and isinstance(refused, str)
        return {'evidence_class': 'SYNTHETIC_ONLY', 'result': result,
            'consume_refused': True, 'journal': safe(EventJournal(state_dir/'c06_state.sqlite').events)}
    approved = _command(OWNER, state_dir, guard, 'approve', pid)
    if name == 'stale_input':
        # Approval exists but original trigger-to-send freshness is already lost.
        expires = datetime.fromisoformat(plan['expires_at'])
        at = (expires-timedelta(seconds=60)).isoformat()
        refused = _command(OWNER, state_dir, guard, 'consume', pid, '--now', at, expected_success=False)
        state = _read_store(state_dir/'venue.sqlite')
        assert isinstance(refused, str) and not state['writes']
        return {'evidence_class': 'SYNTHETIC_ONLY', 'approval': approved['status'],
            'consume_refused': True, 'venue_write_count': 0,
            'observed_at': at, 'proposal_expires_at': plan['expires_at'],
            'reason': 'ORIGINAL_TRIGGER_STALE_BEFORE_PROPOSAL_EXPIRY',
            'journal': safe(EventJournal(state_dir/'c06_state.sqlite').events)}
    consumed = _command(OWNER, state_dir, guard, 'consume', pid)
    duplicate = _command(OWNER, state_dir, guard, 'consume', pid)
    assert duplicate['status'] == 'ALREADY_CONSUMED' and duplicate['venue_write_count'] == 0
    def supervise(action, *flags, failure=False):
        result = _command(SUPERVISOR, state_dir, guard, action, *flags,
            expected_success=not failure)
        if not failure:
            steps.append(result)
            _audit_step(state_dir, result)
        return result
    submitted = supervise('submit-entry', '--entry-result', 'UNKNOWN')
    restarted = supervise('submit-entry')
    assert submitted['venue_write_count'] == restarted['venue_write_count']
    if name == 'critical_protection_failure':
        supervise('fill-entry', '--stop-result', 'REJECTED', failure=True)
        unsafe = _command(SUPERVISOR, state_dir, guard, 'status')
        _audit_step(state_dir, {**unsafe, 'action': 'REJECTED_PROTECTION_OBSERVED'})
        assert unsafe['protection'] == 'MISSING'
        supervise('emergency', '--coordinator-unavailable')
        final = supervise('fill-exit', '--coordinator-unavailable')
    else:
        filled = supervise('partial-entry', '--coordinator-unavailable')
        assert filled['protection'] == 'VERIFIED'
        # Cancel the unfilled IOC remainder through the existing C01 timer.
        intent = _command(OWNER, state_dir, guard, 'show', pid)['entry_intent']
        at = (datetime.fromisoformat(intent['submitted_at'])+timedelta(seconds=11)).isoformat()
        supervise('tick', '--at', at, '--coordinator-unavailable')
        partial = supervise('partial-tp1', '--coordinator-unavailable')
        assert partial['first_fill_at'] == filled['first_fill_at'] and partial['protection'] == 'VERIFIED'
        # Each CLI opens the same durable stores in a new process.
        status = _command(SUPERVISOR, state_dir, guard, 'status')
        assert status['position_quantity'] == partial['position_quantity']
        flatten = supervise('time-exit', '--unknown-exit-ack', '--coordinator-unavailable')
        assert flatten['exit_request'] and flatten['protection'] == 'VERIFIED'
        emergency = supervise('emergency', '--coordinator-unavailable')
        owner_state = _read_store(state_dir/'owner.sqlite')
        assert 'TIME_EXIT_BREACH' in owner_state['faults']
        final = supervise('fill-exit', '--coordinator-unavailable')
    assert final['position_state'] == 'FLAT_RECONCILED' and final['position_quantity'] in ('0', '0.0')
    journal = _journal_role(state_dir, guard, final['lifecycle_id'])
    assert journal['verification_state'] == 'VERIFIED'
    return {'evidence_class': 'SYNTHETIC_ONLY', 'research': research,
        'approval': approved, 'consume': consumed, 'duplicate_consume': duplicate,
        'steps': steps, 'final': final, 'journal_role': journal,
        'owner_state': _read_store(state_dir/'owner.sqlite'),
        'venue_state': _read_store(state_dir/'venue.sqlite'),
        'journal': safe(EventJournal(state_dir/'c06_state.sqlite').events)}


def run_synthetic(root):
    """Complete RC1 operator scenarios; C06-F acceptance is not invoked."""
    root = Path(root)
    if root.exists():
        raise FileExistsError('choose a fresh synthetic state directory; existing evidence is preserved')
    with tempfile.TemporaryDirectory(prefix='astrabot-rc1-network-guard-') as temp:
        guard = Path(temp)
        attempts = _block_network(guard)
        async def all_scenarios():
            return {name: await _scenario(root, guard, name) for name in (
                'positive', 'rejected', 'expired', 'stale_input', 'critical_protection_failure')}
        scenarios = asyncio.run(all_scenarios())
        if attempts.exists():
            raise RuntimeError('offline operator attempted networking')
    positive = scenarios['positive']
    run_id = stable_id('astrabot.rc1.synthetic.v1', positive['research']['proposal']['immutable_hash'])
    events = positive['journal']
    return {'run_id': run_id, 'evidence_class': 'SYNTHETIC_ONLY',
        'executable': False, 'network_attempts': 0, 'scenarios': scenarios,
        'journal': {'events': events, 'event_ids': [e['event_id'] for e in events]},
        'phase_gate_credit_percent': 45}
