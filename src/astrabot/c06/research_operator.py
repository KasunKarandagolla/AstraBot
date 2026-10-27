"""Bridge verified offline research snapshots into the existing six C06 tools.

No qualification, authorization, fake owner, venue or network client is added.
"""
from decimal import Decimal as D
import json
from pathlib import Path

from astrabot.c06.paper_mvp import C06ToolGateway, EventJournal, PlanRegistry, JournalEvent
from astrabot.data.models import binance_usdm_instrument_id, config_hash, stable_id
from astrabot.features.providers import session_vwap, smc_structure
from astrabot.research.context import evaluate_context
from astrabot.research.engine import evaluate
from astrabot.research.integrated import HISTORY_LIMITS, safe
from astrabot.research.models import Evaluation, ResearchAccount, VERSIONS
from astrabot.research.replay import _panel_point_in_time, synthetic_cost_profile
from astrabot.universe.eligibility import SymbolData

HISTORICAL = 'OBSERVED_HISTORICAL_RESEARCH'


def feature_readiness(data, symbol, at, context):
    """Report narrow implemented providers; do not promote entire families."""
    instrument = binance_usdm_instrument_id(symbol)
    vwap = session_vwap(data.candles_5m, as_of=at, symbol=symbol, instrument_id=instrument)
    smc = smc_structure(data.candles_5m, as_of=at, symbol=symbol, instrument_id=instrument)
    rows = {f'A{i:02}': {'readiness': 'UNAVAILABLE', 'source_ids': [],
        'reason': reason} for i, reason in enumerate((
            'No continuous trade-side window supplied to the CVD provider.',
            '', '', 'Liquidation provider unqualified; visible depth is not liquidation history.',
            'ICT provider not implemented/qualified.',
            'No validated OI measurement and settled funding/basis evidence.',
            'No ready frozen policy context.', 'Trade-derived profile provider not implemented/qualified.',
            'Insufficient causal trend context.', 'Insufficient causal volatility/balance context.'), 1)}
    for name, feature in (('A02', vwap), ('A03', smc)):
        rows[name] = {'readiness': feature.readiness, 'source_ids': [feature.observation_id],
            'reason': feature.reason, 'provider': feature.feature_name,
            'fidelity': feature.fidelity}
    for family, scope in (('A07', 'Frozen T1/R1/B1 chronology only'),
                          ('A09', 'TA-Lib trend context only'),
                          ('A10', 'ATR percentile and unvalidated balance hypothesis only')):
        rows[family] = {'readiness': context.readiness, 'source_ids': list(context.source_ids),
            'reason': ';'.join(context.reason_codes), 'scope': scope,
            'qualification': 'RESEARCH_ONLY'}
    return rows


def historical_gateway(data, *, symbol, at, journal=None):
    if 'SYNTHETIC_FIXTURE' in json.dumps(safe(data)):
        raise ValueError('authentic operator refuses synthetic observations')
    # Unknown account terms must block approval. These schema placeholders are
    # explicitly unreconciled and never treated as observed balance or fees.
    account = ResearchAccount(source_id='UNAVAILABLE_NO_ACCOUNT_EVIDENCE', as_of=at,
        equity_usdt='1', pending_open_risk_usdt='0', pending_open_notional_usdt='0',
        isolated_margin_available_usdt='0', occupied_slots=0, reconciled=False,
        daily_entry_halt=True)
    evaluation = evaluate(data, symbol=symbol, instrument_id=binance_usdm_instrument_id(symbol),
        as_of=at, account=account, profile=synthetic_cost_profile(), requested_quantity=D(1))
    return C06ToolGateway(symbol=symbol, data=data, scan_notional_usdt=D(1),
        evaluation=evaluation, candidate=None, setup=None,
        plans=PlanRegistry(), journal=journal or EventJournal(),
        evidence_class=HISTORICAL), evaluation


def present_historical(panel, packet, *, at):
    """Actual typed tool flow, decision events, source bars and operator snapshots."""
    run_id = stable_id('astrabot.rc1.authentic.v1', packet['packet_sha256'], at)
    journal = EventJournal()
    decisions, snapshots = [], {}
    for symbol in sorted(panel.symbols):
        data = _panel_point_in_time(panel, symbol, at, HISTORY_LIMITS)
        if any(c.fidelity == 'SYNTHETIC_FIXTURE' for interval in ('5m','15m','1h','4h')
               for c in getattr(data, 'candles_' + interval)):
            raise ValueError('authentic operator refuses synthetic observations')
        gateway, evaluation = historical_gateway(data, symbol=symbol, at=at, journal=journal)
        scan = gateway.call('scan_opportunities', {'as_of': at})
        evaluated = gateway.call('evaluate_symbol', {'symbol': symbol, 'as_of': at})
        candidate = gateway.call('evaluate_candidates', {'candidate_ids': evaluated.decision_ids})
        try:
            gateway.call('prepare_plan', {'candidate_id': evaluated.decision_ids[0]})
        except ValueError:
            proposal_status = 'BLOCKED_RESEARCH_ONLY'
        else:
            raise RuntimeError('authentic NO_TRADE crossed the proposal boundary')
        context = evaluate_context(data, symbol=symbol, instrument_id=binance_usdm_instrument_id(symbol), as_of=at)
        sources = [safe(c) for interval in ('5m','15m','1h','4h')
            for c in getattr(data, 'candles_' + interval)]
        row = {'symbol': symbol, 'as_of': at.isoformat(), 'decision': 'NO_TRADE',
            'status': 'BLOCKED_BY_DATA', 'evidence_class': HISTORICAL,
            'scan': safe(scan), 'evaluation': safe(evaluated), 'candidate': safe(candidate),
            'proposal_status': proposal_status, 'context': safe(context),
            'features': feature_readiness(data, symbol, at, context),
            'decisions': safe(evaluation.emitted), 'source_bars': sources,
            'source_identity': 'symbol + interval + unchanged native source_record_id',
            'news_events': safe(data.event_clearance) if data.event_clearance else {
                'state': 'UNKNOWN', 'source_ids': [],
                'reason': 'No independently verified historical event clearance'},
            'account_evidence': 'UNAVAILABLE; no observed fees/equity supplied; C04 cost overlay is a hypothesis'}
        journal.append(occurred_at=at, actor='research_operator', event_type='HISTORICAL_NO_TRADE',
            plan_id=run_id, lifecycle_id=run_id,
            details={'evidence_class': HISTORICAL, 'symbol': symbol,
                'decision_sha256': config_hash(row),
                'reason_codes': '|'.join(scan.opportunities[0].reasons),
                'proposal': proposal_status})
        decisions.append(row)
        snapshot = {'schema_version': 'astrabot.operator-snapshot.v1', 'evidence_class': HISTORICAL,
            'symbol': symbol, 'as_of': at.isoformat(), 'data': safe(data),
            'evaluation': safe(evaluation), 'source_packet_sha256': packet['packet_sha256']}
        snapshot['content_sha256'] = config_hash(snapshot)
        snapshots[symbol] = snapshot
    report = {'run_id': run_id, 'evidence_class': HISTORICAL, 'decision': 'NO_TRADE',
        'status': 'BLOCKED_BY_DATA', 'qualified_policy_registry': {
            policy: {'version': version, 'status': 'RESEARCH_ONLY', 'executable': False}
            for policy, version in VERSIONS.items()},
        'source_packet_sha256': packet['packet_sha256'], 'decisions': decisions,
        'journal': {**safe(journal.summary(run_id)),
            'events': [safe(e) for e in journal.events if e.lifecycle_id == run_id]},
        'phase_gate_credit_percent': 45, 'executable': False}
    for snapshot in snapshots.values():
        snapshot.pop('content_sha256')
        snapshot['journal_events'] = safe(journal.events)
        snapshot['content_sha256'] = config_hash(snapshot)
    return report, snapshots


def load_operator_gateway(path):
    """Load one sealed historical snapshot for the unchanged stdio MCP server."""
    payload = json.loads(Path(path).read_text())
    digest = payload.pop('content_sha256')
    if config_hash(payload) != digest or payload['evidence_class'] != HISTORICAL:
        raise ValueError('historical operator snapshot integrity/evidence class mismatch')
    if payload['schema_version'] != 'astrabot.operator-snapshot.v1':
        raise ValueError('unsupported operator snapshot')
    data = SymbolData.model_validate_json(json.dumps(payload['data']))
    evaluation = Evaluation.model_validate_json(json.dumps(payload['evaluation']))
    from datetime import datetime
    at = datetime.fromisoformat(payload['as_of'])
    # Re-evaluate, rather than trust a serialized candidate or a changed policy.
    journal = EventJournal()
    for raw in payload['journal_events']:
        event = JournalEvent.model_validate_json(json.dumps(raw))
        actual = journal.append(occurred_at=event.occurred_at, received_at=event.received_at,
            actor=event.actor, event_type=event.event_type, plan_id=event.plan_id,
            lifecycle_id=event.lifecycle_id, correlation_id=event.correlation_id,
            details=dict(event.details))
        if actual != event:
            raise ValueError('historical journal event does not reproduce')
    gateway, recomputed = historical_gateway(data, symbol=payload['symbol'], at=at, journal=journal)
    if recomputed != evaluation:
        raise ValueError('historical evaluation does not reproduce under frozen policies')
    return gateway


def owner_summary(report):
    """Factual owner prose cites machine event IDs; the ledger stays authoritative."""
    events = report['journal']['events']
    lines = ['# AstraBot offline research RC1', '',
        f"Evidence: **{report['evidence_class']}**. Run `{report['run_id']}`.", '',
        'Formal phase qualification: 45%; P3 INSUFFICIENT_EVIDENCE; policies RESEARCH_ONLY.', '']
    for event in events:
        details = dict(event['details'])
        lines.append(f"- `{event['event_id']}` {event['event_type']}: " +
            '; '.join(f'{k}={v}' for k, v in sorted(details.items())))
    return '\n'.join(lines) + '\n'
