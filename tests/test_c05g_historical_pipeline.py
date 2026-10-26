from __future__ import annotations

import csv
import gzip
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import shutil
import sys

import pytest

from astrabot.data.historical_replay import FreshnessLimits, replay_observations
from astrabot.data.historical_sources import (
    BOOK_HEADER,
    DERIVATIVE_HEADER,
    QUOTE_HEADER,
    HistoricalDataError,
    iter_books,
    iter_derivative_tickers,
    iter_quotes,
    new_diagnostics,
    sha256_file,
    verify_source,
)
from astrabot.data.models import SpreadSample

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "c05g"
sys.path.insert(0, str(ROOT / "scripts"))
import c05_historical_research as cli  # noqa: E402

UTC = timezone.utc
T_0100 = datetime(2024, 10, 1, 1, 0, tzinfo=UTC)
T_0030 = datetime(2024, 10, 1, 0, 30, tzinfo=UTC)


def _rows(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _write_rows(path: Path, header: tuple[str, ...] | list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as packed:
            import io
            with io.TextIOWrapper(packed, encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=header, lineterminator="\n", extrasaction="raise")
                writer.writeheader()
                writer.writerows(rows)


def _copy_feeds(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for path in FIXTURE_DIR.glob("*.csv.gz"):
        shutil.copy2(path, target / path.name)


def _run_sources(root: Path, decisions=(T_0100,), *, freshness=None):
    q_path = next(root.glob("*quotes*.csv.gz"))
    d_path = next(root.glob("*derivative_ticker*.csv.gz"))
    b_path = next(root.glob("*book_snapshot_25*.csv.gz"))
    q_hash, d_hash, b_hash = sha256_file(q_path), sha256_file(d_path), sha256_file(b_path)
    q_diag = new_diagnostics("quotes", q_path, q_hash)
    d_diag = new_diagnostics("derivative_ticker", d_path, d_hash)
    b_diag = new_diagnostics("book_snapshot_25", b_path, b_hash)
    snapshots = replay_observations(
        symbol="SOLUSDT", decision_times=decisions,
        quotes=iter_quotes(q_path, symbol="SOLUSDT", source_sha256=q_hash, diagnostics=q_diag),
        books=iter_books(b_path, symbol="SOLUSDT", source_sha256=b_hash, diagnostics=b_diag),
        derivatives=iter_derivative_tickers(
            d_path, symbol="SOLUSDT", source_sha256=d_hash, diagnostics=d_diag
        ),
        quote_diagnostics=q_diag, book_diagnostics=b_diag, derivative_diagnostics=d_diag,
        freshness=freshness,
    )
    return snapshots, q_diag, d_diag, b_diag


def _epoch_us(value: datetime) -> str:
    delta = value - datetime(1970, 1, 1, tzinfo=UTC)
    return str(delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds)


def test_all_three_adapters_stream_validated_fixtures_and_preserve_uncertainty(tmp_path):
    _copy_feeds(tmp_path)
    snapshots, q, d, b = _run_sources(tmp_path)
    snapshot = snapshots[0]
    assert (q.rows_seen, q.rows_valid, q.duplicates) == (63, 62, 1)
    assert (d.rows_seen, d.rows_valid, d.event_time_ties) == (4, 4, 1)
    assert (b.rows_seen, b.rows_valid) == (2, 2)
    assert snapshot.latest_quote is not None
    assert snapshot.latest_quote.source_sha256 == q.sha256
    assert snapshot.latest_quote.source_record_number == 61
    assert snapshot.latest_quote.fidelity == "UNKNOWN"
    assert snapshot.latest_quote.ingestion_time_semantics == "PROVIDER_ARRIVAL_PROXY"
    assert snapshot.spread_slots_occupied == 60
    assert snapshot.spread_sample_endpoints_distinct == 60
    assert snapshot.spread_threshold_pass
    assert snapshot.spread_source_event_exact_minute_intervals < 59
    assert all(sample.sampled_at is not None and sample.event_time <= sample.sampled_at
               and sample.available_at <= sample.sampled_at for sample in snapshot.periodic_spread_samples)
    assert snapshot.latest_depth is not None
    assert snapshot.latest_depth.unit_validated is False
    assert snapshot.latest_depth.quantity_unit == "UNVERIFIED_RAW_BOOK_AMOUNT"
    assert snapshot.depth_raw_bid_amount_within_0_20 == Decimal("79.0")
    assert snapshot.depth_raw_ask_amount_within_0_20 == Decimal("59.0")
    assert snapshot.latest_open_interest is not None
    assert snapshot.latest_open_interest.unit_validated is False
    assert snapshot.latest_open_interest.open_interest_notional_usdt is None
    assert snapshot.latest_open_interest.open_interest == Decimal("1000")
    assert snapshot.open_interest_value_change_state == "REPEATED_VALUE_NOT_A_CONFIRMED_REFRESH"
    assert snapshot.open_interest_equal_value_run_length == 3
    assert snapshot.mark_index is not None and snapshot.mark_index.next_funding_time is None
    assert snapshot.reported_funding_timestamp == datetime(2024, 10, 1, 8, tzinfo=UTC)
    assert snapshot.funding_settlement_status == "UNVERIFIED_NOT_REPORTED_AS_SETTLED"
    assert snapshot.c02_eligibility == "NOT_READY_FAIL_CLOSED"
    assert snapshot.economic_qualification == "NOT_ASSESSED_INSUFFICIENT_EVIDENCE"
    assert "OPEN_INTEREST_UNIT_UNVERIFIED" in snapshot.quality_blockers
    assert "DEPTH_AMOUNT_UNIT_UNVERIFIED" in snapshot.quality_blockers


def test_fixed_0030_cutoff_has_only_30_prior_minute_samples_and_late_rows_are_excluded(tmp_path):
    _copy_feeds(tmp_path)
    at_0030, at_0100 = _run_sources(tmp_path, decisions=(T_0030, T_0100))[0]
    assert at_0030.spread_slots_occupied == 30
    assert not at_0030.spread_threshold_pass
    assert "SPREAD_WARMUP_LT_60_PERIODIC_SLOTS" in at_0030.quality_blockers
    assert at_0100.excluded_late_rows["quotes"] == 1
    assert at_0100.excluded_late_rows["derivative_ticker"] == 1
    assert at_0100.latest_quote is not None and at_0100.latest_quote.bid_price == Decimal("100.59")
    assert at_0100.latest_open_interest is not None and at_0100.latest_open_interest.open_interest == Decimal("1000")


def test_future_event_and_late_arrival_never_leak_into_earlier_cutoff(tmp_path):
    _copy_feeds(tmp_path)
    early, late = _run_sources(
        tmp_path,
        decisions=(T_0100, datetime(2024, 10, 1, 1, 2, tzinfo=UTC)),
    )[0]
    assert early.latest_quote is not None and early.latest_quote.bid_price == Decimal("100.59")
    assert early.latest_open_interest is not None and early.latest_open_interest.open_interest == Decimal("1000")
    assert early.excluded_future_event_rows["quotes"] == 1
    assert early.excluded_late_rows["derivative_ticker"] == 1
    assert late.latest_quote is not None and late.latest_quote.bid_price == Decimal("100.62")


def test_periodic_sample_endpoints_are_utc_minute_aligned_for_off_minute_cutoffs(tmp_path):
    _copy_feeds(tmp_path)
    cutoff = datetime(2024, 10, 1, 1, 0, 30, tzinfo=UTC)
    snapshot = _run_sources(tmp_path, decisions=(cutoff,))[0][0]
    endpoints = [sample.sampled_at for sample in snapshot.periodic_spread_samples]
    assert len(endpoints) == 60
    assert endpoints[-1] == datetime(2024, 10, 1, 1, 0, tzinfo=UTC)
    assert all(value is not None and value.second == 0 and value.microsecond == 0 for value in endpoints)


def test_stale_quote_depth_and_open_interest_row_are_reported(tmp_path):
    _copy_feeds(tmp_path)
    snapshot = _run_sources(
        tmp_path,
        freshness=FreshnessLimits(
            quote=timedelta(milliseconds=100),
            depth=timedelta(milliseconds=100),
            open_interest_row=timedelta(milliseconds=500),
        ),
    )[0][0]
    assert "QUOTE_STALE" in snapshot.quality_blockers
    assert "DEPTH_STALE" in snapshot.quality_blockers
    assert "OPEN_INTEREST_TICKER_ROW_STALE" in snapshot.quality_blockers
    assert snapshot.spread_slots_occupied == 60


def test_derivative_equal_event_time_tie_uses_latest_arrival_deterministically(tmp_path):
    _copy_feeds(tmp_path)
    cutoff = datetime(2024, 10, 1, 0, 59, 58, 500_000, tzinfo=UTC)
    snapshot, _, diag, _ = _run_sources(tmp_path, decisions=(cutoff,))
    assert diag.event_time_ties == 1
    assert snapshot[0].mark_index is not None
    assert snapshot[0].mark_index.mark_price == Decimal("100.6")


def test_quote_event_time_regression_is_counted_and_bad_row_is_not_selected(tmp_path):
    _copy_feeds(tmp_path)
    path = next(tmp_path.glob("*quotes*.csv.gz"))
    quote_rows = _rows(path)[:2]
    quote_rows[0]["timestamp"] = _epoch_us(datetime(2024, 10, 1, 0, 2, tzinfo=UTC))
    quote_rows[0]["local_timestamp"] = _epoch_us(datetime(2024, 10, 1, 0, 2, 0, 10_000, tzinfo=UTC))
    quote_rows[1]["timestamp"] = _epoch_us(datetime(2024, 10, 1, 0, 1, tzinfo=UTC))
    quote_rows[1]["local_timestamp"] = _epoch_us(datetime(2024, 10, 1, 0, 1, 0, 10_000, tzinfo=UTC))
    _write_rows(path, QUOTE_HEADER, quote_rows)
    snapshot, diag, _, _ = _run_sources(tmp_path, decisions=(datetime(2024, 10, 1, 0, 3, tzinfo=UTC),))
    assert diag.event_time_regressions == 1
    assert "QUOTES_SOURCE_ORDER_ANOMALY" in snapshot[0].quality_blockers
    assert snapshot[0].latest_quote is not None
    assert snapshot[0].latest_quote.event_time == datetime(2024, 10, 1, 0, 2, tzinfo=UTC)


@pytest.mark.parametrize("field,value", [("bid_price", "NaN"), ("bid_amount", "bad"), ("ask_price", "0")])
def test_malformed_quote_price_and_quantity_fail_closed(tmp_path, field, value):
    _copy_feeds(tmp_path)
    path = next(tmp_path.glob("*quotes*.csv.gz"))
    rows = _rows(path)[:1]
    rows[0][field] = value
    _write_rows(path, QUOTE_HEADER, rows)
    digest = sha256_file(path)
    diag = new_diagnostics("quotes", path, digest)
    with pytest.raises(HistoricalDataError):
        list(iter_quotes(path, symbol="SOLUSDT", source_sha256=digest, diagnostics=diag))
    assert diag.malformed_records == 1


def test_unexpected_header_mixed_symbol_and_wrong_checksum_are_rejected(tmp_path):
    _copy_feeds(tmp_path)
    path = next(tmp_path.glob("*quotes*.csv.gz"))
    rows = _rows(path)[:1]
    _write_rows(path, (*QUOTE_HEADER, "unexpected"), rows)
    digest = sha256_file(path)
    diag = new_diagnostics("quotes", path, digest)
    with pytest.raises(HistoricalDataError, match="unexpected header"):
        list(iter_quotes(path, symbol="SOLUSDT", source_sha256=digest, diagnostics=diag))
    with pytest.raises(HistoricalDataError, match="SHA-256 mismatch"):
        verify_source(path, "0" * 64)

    _write_rows(path, QUOTE_HEADER, [{**_rows(FIXTURE_DIR / path.name)[0], "symbol": "BTCUSDT"}])
    digest = sha256_file(path)
    diag = new_diagnostics("quotes", path, digest)
    with pytest.raises(HistoricalDataError, match="mixed or unexpected symbol"):
        list(iter_quotes(path, symbol="SOLUSDT", source_sha256=digest, diagnostics=diag))


def test_truncated_gzip_is_detected_when_stream_reads_through_eof(tmp_path):
    source = next(FIXTURE_DIR.glob("*quotes*.csv.gz"))
    target = tmp_path / source.name
    target.write_bytes(source.read_bytes()[:-8])
    digest = sha256_file(target)
    diag = new_diagnostics("quotes", target, digest)
    with pytest.raises(HistoricalDataError, match="truncated gzip"):
        list(iter_quotes(target, symbol="SOLUSDT", source_sha256=digest, diagnostics=diag))


def test_inverted_arrival_is_counted_and_skipped(tmp_path):
    path = tmp_path / "inverted.csv.gz"
    row = _rows(next(FIXTURE_DIR.glob("*quotes*.csv.gz")))[0]
    row["local_timestamp"] = row["timestamp"][:-1] + str(int(row["timestamp"][-1]) - 1)
    # Use an unambiguous earlier timestamp while keeping the exact 16-digit schema.
    row["local_timestamp"] = str(int(row["timestamp"]) - 1_000)
    _write_rows(path, QUOTE_HEADER, [row])
    digest = sha256_file(path)
    diag = new_diagnostics("quotes", path, digest)
    assert list(iter_quotes(path, symbol="SOLUSDT", source_sha256=digest, diagnostics=diag)) == []
    assert diag.inverted_arrivals == 1


def test_book_crossing_order_and_missing_levels_are_detected(tmp_path):
    _copy_feeds(tmp_path)
    path = next(tmp_path.glob("*book_snapshot_25*.csv.gz"))
    source_rows = _rows(path)
    crossed = dict(source_rows[0])
    crossed["asks[0].price"] = "99.98"
    _write_rows(path, BOOK_HEADER, [crossed])
    digest = sha256_file(path)
    diag = new_diagnostics("book_snapshot_25", path, digest)
    rows = list(iter_books(path, symbol="SOLUSDT", source_sha256=digest, diagnostics=diag))
    assert rows[0].quality == "MALFORMED"
    assert diag.invalid_books == 1

    inverted_level = dict(source_rows[0])
    inverted_level["asks[1].price"] = "100.00"
    _write_rows(path, BOOK_HEADER, [inverted_level])
    digest = sha256_file(path)
    diag = new_diagnostics("book_snapshot_25", path, digest)
    rows = list(iter_books(path, symbol="SOLUSDT", source_sha256=digest, diagnostics=diag))
    assert rows[0].quality == "MALFORMED"
    assert diag.invalid_books == 1

    incomplete = dict(source_rows[1])
    incomplete["asks[24].price"] = ""
    incomplete["asks[24].amount"] = ""
    _write_rows(path, BOOK_HEADER, [incomplete])
    digest = sha256_file(path)
    diag = new_diagnostics("book_snapshot_25", path, digest)
    rows = list(iter_books(path, symbol="SOLUSDT", source_sha256=digest, diagnostics=diag))
    assert rows[0].quality == "INCOMPLETE"
    assert rows[0].missing_ask_levels == 1
    snapshot = replay_observations(
        symbol="SOLUSDT", decision_times=(T_0100,), quotes=iter(()), books=rows, derivatives=iter(()),
        quote_diagnostics=new_diagnostics("quotes", path, digest), book_diagnostics=diag,
        derivative_diagnostics=new_diagnostics("derivative_ticker", path, digest),
    )[0]
    assert "DEPTH_LEVELS_INCOMPLETE" in snapshot.quality_blockers


def test_source_timestamp_parsing_rejects_non_microsecond_and_non_utc_decisions(tmp_path):
    from astrabot.data.historical_sources import epoch_microseconds

    with pytest.raises(ValueError, match="16-digit"):
        epoch_microseconds("1727740800000", field_name="timestamp")
    _copy_feeds(tmp_path)
    with pytest.raises(ValueError, match="UTC"):
        _run_sources(tmp_path, decisions=(datetime(2024, 10, 1, 1, 0, tzinfo=timezone(timedelta(hours=1))),))


def test_fixture_cli_outputs_deterministic_machine_and_markdown_reports_in_windows_path(tmp_path, capsys):
    data_root = tmp_path / "source data with spaces"
    _copy_feeds(data_root)
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    manifest_path = data_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    args = cli.build_parser().parse_args([
        "--data-root", str(data_root), "--source-manifest", str(manifest_path),
        "--symbol", "SOLUSDT", "--date", "2024-10-01",
        "--decision-time", "2024-10-01T01:00:00Z", "--output-dir", str(tmp_path / "output"),
    ])
    first = cli.run(args)
    capsys.readouterr()
    first_json = (tmp_path / "output" / "C05_G_HISTORICAL_RESEARCH_SOLUSDT_2024-10-01.json").read_bytes()
    second = cli.run(args)
    capsys.readouterr()
    second_json = (tmp_path / "output" / "C05_G_HISTORICAL_RESEARCH_SOLUSDT_2024-10-01.json").read_bytes()
    assert first_json == second_json
    assert first["synthetic"] is True
    assert first["snapshots"][0]["spread_slots_occupied"] == 60
    assert first["c02_complete_eligibility"] is False
    assert (tmp_path / "output" / "C05_G_HISTORICAL_RESEARCH_SOLUSDT_2024-10-01.md").exists()
    moved = data_root / "quotes-after-run.csv.gz"
    (data_root / manifest["feeds"]["quotes"]["file"]).rename(moved)
    assert moved.is_file()  # all gzip and CSV handles have been closed on Windows


def test_periodic_sample_clock_is_explicit_and_c02_scanner_still_uses_event_time():
    from test_c02_universe import SCAN, eligible_data
    from astrabot.universe.eligibility import scan_universe

    data = eligible_data(as_of=SCAN)
    endpoints = [SCAN - timedelta(minutes=offset) for offset in range(59, -1, -1)]
    adjusted = []
    for index, (sample, endpoint) in enumerate(zip(data.spread_samples, endpoints, strict=True)):
        event_time = endpoint - timedelta(milliseconds=100 + (index % 7) * 50)
        adjusted.append(sample.model_copy(update={
            "event_time": event_time,
            "available_at": endpoint,
            "ingested_at": endpoint,
            "as_of": SCAN,
            "sampled_at": endpoint,
        }))
    research_samples = tuple(adjusted)
    assert all(sample.sampled_at == endpoint for sample, endpoint in zip(research_samples, endpoints, strict=True))
    result = scan_universe({"ALTUSDT": data.model_copy(update={"spread_samples": research_samples})},
                           SCAN, Decimal("100000"))
    assert not result.considered[0].eligible
    assert "SPREAD_SAMPLE_GAP_DUPLICATE_OR_ORDER" in result.considered[0].reasons
