from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from astrabot.data.historical_evidence import load_evidence, validate_evidence, CHECKS
from astrabot.data.historical_sources import HistoricalDataError
from test_c05g_historical_pipeline import T_0100, FIXTURE_DIR
import c05_historical_research as cli

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'tests/fixtures/c05h'


@pytest.fixture
def evidence_dir(tmp_path):
    target = tmp_path / 'evidence'
    shutil.copytree(EVIDENCE, target)
    return target


def _edit_manifest(root, change):
    path = root / 'manifest.json'
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value))


def _edit_claim(root, change):
    path = root / 'synthetic_assertions.json'
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _edit_manifest(root, lambda data: [record.update(sha256=digest) for record in data['records']])


def _run(root, out, *, evidence_path=None):
    args = cli.build_parser().parse_args([
        '--data-root', str(FIXTURE_DIR), '--source-manifest', str(FIXTURE_DIR / 'manifest.json'),
        '--symbol', 'SOLUSDT', '--date', '2024-10-01',
        '--decision-time', '2024-10-01T01:00:00Z', '--output-dir', str(out),
        '--evidence-manifest', str(evidence_path or root / 'manifest.json')])
    return cli.run(args)


def test_verified_contract_quantity_conversion_is_exact_and_still_fail_closed(evidence_dir, tmp_path, capsys):
    report = _run(evidence_dir, tmp_path / 'out')
    capsys.readouterr()
    snapshot = report['snapshots'][0]
    validation = snapshot['evidence_validation']
    summary = json.loads((ROOT / 'research/c05/C05_H_EVIDENCE_VALIDATION.json').read_text())
    assert summary['synthetic_assessment']['validation'] == validation
    assert summary['synthetic_assessment']['configuration_hash'] == report['configuration_hash']
    assert set(validation['checks']) == set(CHECKS)
    assert all(check['status'] == 'VERIFIED' for check in validation['checks'].values())
    assert validation['oi_notional_usdt'] == '10050.00'  # 1000 contracts * 0.1 SOL * 100.50
    assert validation['oi_measurement_at'] == '2024-10-01T00:59:59.000000Z'
    assert Decimal(validation['book_bid_notional_usdt_within_0_20']) == Decimal('789.1040')
    assert Decimal(validation['book_ask_notional_usdt_within_0_20']) == Decimal('590.6860')
    assert snapshot['latest_open_interest']['unit_validated'] is True
    assert snapshot['latest_open_interest']['open_interest'] == '100.0'
    assert snapshot['latest_depth']['unit_validated'] is True
    assert snapshot['open_interest_raw_quantity'] == '1000'
    assert snapshot['depth_raw_bid_amount_within_0_20'] == '79.0'
    assert snapshot['c02_eligibility'] == 'NOT_READY_FAIL_CLOSED'
    assert report['economic_qualification'] == 'INSUFFICIENT_EVIDENCE'
    assert 'PERIODIC_SPREAD_SAMPLER_IS_RESEARCH_OPT_IN_ONLY' in snapshot['quality_blockers']
    assert 'OPEN_INTEREST_UNIT_UNVERIFIED' not in snapshot['quality_blockers']
    first = (tmp_path / 'out/C05_G_HISTORICAL_RESEARCH_SOLUSDT_2024-10-01.json').read_bytes()
    assert _run(evidence_dir, tmp_path / 'out') == report
    capsys.readouterr()
    assert first == (tmp_path / 'out/C05_G_HISTORICAL_RESEARCH_SOLUSDT_2024-10-01.json').read_bytes()


def test_base_units_do_not_apply_contract_multiplier(evidence_dir, tmp_path, capsys):
    def edit(data):
        for kind in ('oi_unit', 'book_unit'):
            data[kind]['raw_unit'] = 'BASE_ASSET'
            del data[kind]['base_per_contract']
    _edit_claim(evidence_dir, edit)
    result = _run(evidence_dir, tmp_path / 'out')['snapshots'][0]['evidence_validation']
    capsys.readouterr()
    assert result['oi_base_multiplier'] == '1'
    assert Decimal(result['oi_notional_usdt']) == Decimal('100500')


@pytest.mark.parametrize('change,check,reason', [
    (lambda d: d['records'].clear(), 'historical_metadata', 'NO_EFFECTIVE_EVIDENCE'),
    (lambda d: d['records'][0].update(effective_from='2026-10-25T00:00:00Z', effective_to='2026-10-26T00:00:00Z'), 'historical_metadata', 'NO_EFFECTIVE_EVIDENCE'),
    (lambda d: d['records'][0].update(available_at='2024-10-02T00:00:00Z', captured_at='2026-10-25T00:00:00Z'), 'historical_metadata', 'EVIDENCE_NOT_KNOWN_AT_DECISION'),
    (lambda d: d['records'][0].update(effective_to='2024-10-01T01:00:00Z'), 'historical_metadata', 'NO_EFFECTIVE_EVIDENCE'),
    (lambda d: d['records'][1].update(dataset_sha256='0'*64), 'oi_quantity_unit', 'DATASET_HASH_MISMATCH'),
    (lambda d: d['records'][1].update(sha256='0'*64), 'oi_quantity_unit', 'ARTIFACT_UNAVAILABLE_OR_INVALID'),
    (lambda d: d['records'][1].update(artifact='missing.json'), 'oi_quantity_unit', 'ARTIFACT_UNAVAILABLE_OR_INVALID'),
    (lambda d: d['records'][1].update(pointer='/absent'), 'oi_quantity_unit', 'ARTIFACT_UNAVAILABLE_OR_INVALID'),
    (lambda d: d['records'][1].update(artifact='../outside.json'), 'oi_quantity_unit', 'ARTIFACT_UNAVAILABLE_OR_INVALID'),
    (lambda d: d['records'][1].update(symbol='BTCUSDT'), 'oi_quantity_unit', 'NO_EFFECTIVE_EVIDENCE'),
    (lambda d: d.update(synthetic=False), 'historical_metadata', 'SYNTHETIC_SCOPE_MISMATCH'),
])
def test_missing_wrong_scope_late_or_expired_evidence_stays_unverified(evidence_dir, tmp_path, capsys, change, check, reason):
    _edit_manifest(evidence_dir, change)
    snapshot = _run(evidence_dir, tmp_path / 'out')['snapshots'][0]
    capsys.readouterr()
    result = snapshot['evidence_validation']['checks'][check]
    assert result['status'] == 'UNVERIFIED'
    assert result['reasons'] == [reason]
    assert snapshot['c02_eligibility'] == 'NOT_READY_FAIL_CLOSED'
    assert snapshot['latest_open_interest']['open_interest_notional_usdt'] is None


@pytest.mark.parametrize('kind,field,value,check', [
    ('metadata', 'contract_size', None, 'historical_metadata'),
    ('metadata', 'quote_asset', 'USD', 'historical_metadata'),
    ('metadata', 'instrument_id', 'BINANCE_USDM:PERPETUAL:BTCUSDT:SETTLE:USDT', 'historical_metadata'),
    ('metadata', 'minimum_quantity', '2', 'historical_metadata'),
    ('metadata', 'filters', [], 'historical_metadata'),
    ('oi_unit', 'base_per_contract', '1', 'oi_quantity_unit'),
    ('book_unit', 'base_asset', 'BTC', 'book_quantity_unit'),
    ('book_unit', 'price_unit', 'USD_PER_CONTRACT', 'book_quantity_unit'),
    ('oi_unit', 'base_per_contract', 'NaN', 'oi_quantity_unit'),
    ('oi_time', 'semantics', 'CARRIED_FORWARD_TICKER_TIME', 'oi_measurement_time'),
])
def test_incomplete_contradictory_or_unsupported_claims(evidence_dir, tmp_path, capsys, kind, field, value, check):
    _edit_claim(evidence_dir, lambda d: d[kind].update({field: value}))
    snapshot = _run(evidence_dir, tmp_path / 'out')['snapshots'][0]
    capsys.readouterr()
    assert snapshot['evidence_validation']['checks'][check]['status'] == 'UNVERIFIED'
    if kind == 'book_unit':
        assert snapshot['evidence_validation']['book_bid_notional_usdt_within_0_20'] is None
    else:
        assert snapshot['latest_open_interest']['open_interest_notional_usdt'] is None


def test_repeated_oi_value_is_not_measurement_evidence(evidence_dir, tmp_path, capsys):
    _edit_manifest(evidence_dir, lambda d: d.update(records=[r for r in d['records'] if r['kind'] != 'oi_time']))
    snapshot = _run(evidence_dir, tmp_path / 'out')['snapshots'][0]
    capsys.readouterr()
    checks = snapshot['evidence_validation']['checks']
    assert checks['oi_quantity_unit']['status'] == 'VERIFIED'
    assert checks['oi_measurement_time']['status'] == 'UNVERIFIED'
    assert checks['oi_notional_conversion']['status'] == 'UNVERIFIED'
    assert snapshot['open_interest_value_change_state'] == 'REPEATED_VALUE_NOT_A_CONFIRMED_REFRESH'
    assert snapshot['latest_open_interest']['unit_validated'] is True
    assert snapshot['latest_open_interest']['open_interest_notional_usdt'] is None


def test_missing_mark_semantics_blocks_notional_only(evidence_dir, tmp_path, capsys):
    _edit_claim(evidence_dir, lambda d: d['oi_time'].pop('mark_price_semantics'))
    checks = _run(evidence_dir, tmp_path / 'out')['snapshots'][0]['evidence_validation']['checks']
    capsys.readouterr()
    assert checks['oi_measurement_time']['status'] == 'VERIFIED'
    assert checks['oi_notional_conversion']['status'] == 'UNVERIFIED'


def test_overlapping_conflicting_claims_do_not_choose_a_winner(evidence_dir, tmp_path, capsys):
    path = evidence_dir / 'synthetic_assertions.json'
    data = json.loads(path.read_text())
    data['conflict'] = {**data['oi_unit'], 'raw_unit': 'BASE_ASSET'}
    del data['conflict']['base_per_contract']
    _edit_claim(evidence_dir, lambda d: d.update(conflict=data['conflict']))
    def edit(manifest):
        original = next(r for r in manifest['records'] if r['kind'] == 'oi_unit')
        manifest['records'].append({**original, 'evidence_id': 'conflicting-unit', 'pointer': '/conflict'})
    _edit_manifest(evidence_dir, edit)
    checks = _run(evidence_dir, tmp_path / 'out')['snapshots'][0]['evidence_validation']['checks']
    capsys.readouterr()
    assert checks['oi_quantity_unit']['reasons'] == ['CONTRADICTORY_EVIDENCE']
    assert checks['oi_notional_conversion']['status'] == 'UNVERIFIED'


@pytest.mark.parametrize('change', [
    lambda d: d.update(manifest_version='future.v99'),
    lambda d: d.update(synthetic='false'),
    lambda d: d['records'][0].update(effective_to='2024-09-01T00:00:00Z'),
    lambda d: d['records'][0].update(effective_from='2024-10-01T00:00:00'),
    lambda d: d['records'].append(d['records'][0]),
])
def test_invalid_manifest_aborts_instead_of_producing_verified_report(evidence_dir, change):
    _edit_manifest(evidence_dir, change)
    with pytest.raises(HistoricalDataError, match='invalid evidence manifest'):
        load_evidence(evidence_dir / 'manifest.json')


def _observations():
    from astrabot.data.historical_sources import iter_books, iter_derivative_tickers, new_diagnostics
    from astrabot.data.historical_sources import sha256_file
    def rows(pattern, dataset, iterator):
        path = next(FIXTURE_DIR.glob(pattern))
        digest = sha256_file(path)
        return list(iterator(path, symbol='SOLUSDT', source_sha256=digest,
                             diagnostics=new_diagnostics(dataset, path, digest)))
    return (rows('*book*.gz', 'book_snapshot_25', iter_books)[-1],
            rows('*derivative*.gz', 'derivative_ticker', iter_derivative_tickers)[-2])


def _validate(root, book, oi, *, decision=T_0100):
    return validate_evidence(evidence=load_evidence(root / 'manifest.json'), symbol='SOLUSDT',
                             decision_time=decision, synthetic=True, book=book, oi=oi)


def test_incomplete_book_keeps_unit_verified_but_blocks_notional(evidence_dir):
    book, oi = _observations()
    result = _validate(evidence_dir, replace(book, quality='INCOMPLETE', missing_bid_levels=1), oi)
    assert result.checks['book_quantity_unit'].status == 'VERIFIED'
    assert result.checks['book_notional_conversion'].status == 'UNVERIFIED'
    assert result.book_bid_notional_usdt_within_0_20 is None


@pytest.mark.parametrize('field,value', [('mark_price', None), ('open_interest', None)])
def test_missing_oi_or_mark_cannot_produce_notional(evidence_dir, field, value):
    book, oi = _observations()
    result = _validate(evidence_dir, book, replace(oi, **{field: value}))
    assert result.oi_notional_usdt is None
    assert result.checks['oi_notional_conversion'].status == 'UNVERIFIED'


@pytest.mark.parametrize('field,value', [
    ('available_at', datetime(2024, 10, 1, 1, 0, 1, tzinfo=timezone.utc)),
    ('symbol', 'BTCUSDT'), ('quality', 'MALFORMED'), ('exchange', 'other'),
])
def test_wrong_or_noncausal_observation_cannot_use_valid_evidence(evidence_dir, field, value):
    book, oi = _observations()
    result = _validate(evidence_dir, replace(book, **{field: value}), replace(oi, **{field: value}))
    for check in ('oi_quantity_unit', 'oi_measurement_time', 'oi_notional_conversion',
                  'book_quantity_unit', 'book_notional_conversion'):
        assert result.checks[check].status == 'UNVERIFIED'


def test_absent_observations_do_not_close_units_or_conversions(evidence_dir):
    result = _validate(evidence_dir, None, None)
    assert result.checks['historical_metadata'].status == 'VERIFIED'
    assert all(result.checks[name].status == 'UNVERIFIED' for name in CHECKS if name != 'historical_metadata')


def test_metadata_must_also_cover_observation_time(evidence_dir):
    _edit_manifest(evidence_dir, lambda d: d['records'][0].update(effective_from='2024-10-01T01:00:00Z'))
    book, oi = _observations()
    result = _validate(evidence_dir, book, oi)
    assert result.checks['historical_metadata'].status == 'VERIFIED'
    assert result.checks['oi_quantity_unit'].status == 'UNVERIFIED'
    assert result.checks['book_quantity_unit'].status == 'UNVERIFIED'


def test_future_claims_do_not_change_an_earlier_result(evidence_dir):
    book, oi = _observations()
    original = _validate(evidence_dir, book, oi)
    def edit(data):
        ref = next(r for r in data['records'] if r['kind'] == 'oi_unit')
        data['records'].append({**ref, 'evidence_id': 'future-unsupported', 'pointer': '/absent',
                               'available_at': '2024-10-02T00:00:00Z', 'captured_at': '2024-10-02T00:00:00Z'})
    _edit_manifest(evidence_dir, edit)
    result = _validate(evidence_dir, book, oi)
    assert result.checks == original.checks
    assert result.oi_notional_usdt == original.oi_notional_usdt


def test_changed_oi_value_still_does_not_prove_measurement_time(evidence_dir):
    _edit_manifest(evidence_dir, lambda d: d.update(records=[r for r in d['records'] if r['kind'] != 'oi_time']))
    book, oi = _observations()
    result = _validate(evidence_dir, book, replace(oi, open_interest_changed_in_source=True))
    assert result.checks['oi_measurement_time'].status == 'UNVERIFIED'
    assert result.oi_notional_usdt is None


def test_real_empty_manifest_closes_no_historical_check():
    result = validate_evidence(evidence=load_evidence(ROOT / 'research/c05/C05_H_EVIDENCE_SOLUSDT_2024-10-01.json'),
                               symbol='SOLUSDT', decision_time=T_0100, synthetic=False)
    assert all(check.status == 'UNVERIFIED' for check in result.checks.values())


def test_authority_must_support_the_claim_kind(evidence_dir):
    _edit_manifest(evidence_dir, lambda d: d['records'][1].update(authority='VENUE'))
    book, oi = _observations()
    result = _validate(evidence_dir, book, oi)
    assert result.checks['oi_quantity_unit'].reasons == ('UNSUPPORTED_AUTHORITY',)


def test_synthetic_metadata_payload_cannot_be_relabeled_as_real(evidence_dir):
    def edit(data):
        data['synthetic'] = False
        for ref in data['records']:
            ref['authority'] = 'VENUE' if ref['kind'] == 'metadata' else 'PROVIDER'
    _edit_manifest(evidence_dir, edit)
    book, oi = _observations()
    result = validate_evidence(evidence=load_evidence(evidence_dir / 'manifest.json'),
                               symbol='SOLUSDT', decision_time=T_0100, synthetic=False, book=book, oi=oi)
    assert result.checks['historical_metadata'].status == 'UNVERIFIED'
    assert result.oi_notional_usdt is None
    assert result.book_bid_notional_usdt_within_0_20 is None


def test_duplicate_json_claim_fields_are_rejected(evidence_dir):
    artifact = evidence_dir / 'synthetic_assertions.json'
    artifact.write_text('{"oi_unit":{"raw_unit":"BASE_ASSET","raw_unit":"CONTRACTS"}}')
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    _edit_manifest(evidence_dir, lambda data: [ref.update(sha256=digest) for ref in data['records']])
    book, oi = _observations()
    result = _validate(evidence_dir, book, oi)
    assert all(check.status == 'UNVERIFIED' for check in result.checks.values())
    path = evidence_dir / 'manifest.json'
    path.write_text('{"synthetic":true,"synthetic":false}')
    with pytest.raises(HistoricalDataError, match='duplicate JSON key'):
        load_evidence(path)
