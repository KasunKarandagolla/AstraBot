"""Offline contract checks for bounded public Binance archive ingestion."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest
import astrabot.data.public_archive as archive_module
from astrabot.data.public_archive import (
    ArchiveError,
    CSV_COLUMNS,
    ArchiveSpec,
    _SameHostRedirect,
    _external_data_root,
    planned_archives,
    validate_archive_bytes,
)
from astrabot.research.replay import load_public_um_archive_panel


def _daily_zip(*, skip_index: int | None = None, duplicate_index: int | None = None,
               columns=CSV_COLUMNS, member="BTCUSDT-1m-2025-10-23.csv") -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    start = 1761177600000  # 2025-10-23 00:00:00 UTC
    for minute in range(1440):
        if minute == skip_index:
            continue
        actual_minute = (duplicate_index - 1 if duplicate_index is not None and minute == duplicate_index
                         else minute)
        open_time = start + actual_minute * 60_000
        price = "100.0"
        writer.writerow((open_time, price, "101.0", "99.0", price, "1.0",
            open_time + 59_999, "100.0", 10, "0.5", "50.0", "0"))
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, output.getvalue())
    return zipped.getvalue()


def test_fixed_plan_has_only_declared_smoke_and_pilot_archives():
    smoke = planned_archives("smoke")
    pilot = planned_archives("pilot")
    assert len(smoke) == 7
    assert {item.symbol for item in smoke} == {
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT"}
    assert {item.period for item in smoke} == {"2025-10-23"}
    assert {item.interval for item in smoke} == {"1m"}
    assert len(pilot) == 112
    assert {item.period for item in pilot} == {"2024-07", "2024-08", "2024-09", "2024-10"}
    assert {item.interval for item in pilot} == {"5m", "15m", "1h", "4h"}
    assert all(item.url.startswith("https://data.binance.vision/") for item in (*smoke, *pilot))


def test_archive_transport_rejects_external_root_inside_repository_and_cross_host_redirect(tmp_path, monkeypatch):
    repository = tmp_path / "repository"
    repository.mkdir()
    monkeypatch.setenv("ASTRABOT_DATA_ROOT", str(repository / "raw"))
    with pytest.raises(ArchiveError, match="inside the Git repository"):
        _external_data_root(repository)

    request = urllib.request.Request("https://data.binance.vision/archive.zip")
    handler = _SameHostRedirect()
    headers = {"Location": "https://attacker.example/archive.zip"}
    with pytest.raises(urllib.error.HTTPError, match="cross-host"):
        handler.redirect_request(request, None, 302, "Found", headers,
                                 "https://attacker.example/archive.zip")


def test_daily_archive_validates_zip_member_schema_rows_timestamps_and_continuity():
    spec = ArchiveSpec("BTCUSDT", "1m", "2025-10-23", "daily")
    evidence = validate_archive_bytes(_daily_zip(), spec)
    assert evidence["members"] == [spec.member]
    assert evidence["csv_schema"] == list(CSV_COLUMNS)
    assert evidence["quality"] == {
        "expected_rows": 1440,
        "actual_rows": 1440,
        "first_open_time": "2025-10-23T00:00:00.000Z",
        "last_open_time": "2025-10-23T23:59:00.000Z",
        "duplicate_open_times": 0,
        "out_of_order_open_times": 0,
        "missing_intervals": 0,
        "first_gap": None,
        "status": "PASS",
    }
    assert len(evidence["csv_member_sha256"]) == 64


def test_archive_marks_missing_interval_and_duplicate_as_quality_failure():
    spec = ArchiveSpec("BTCUSDT", "1m", "2025-10-23", "daily")
    gap = validate_archive_bytes(_daily_zip(skip_index=10), spec)["quality"]
    duplicate = validate_archive_bytes(_daily_zip(duplicate_index=10), spec)["quality"]
    assert gap["status"] == "FAIL"
    assert gap["missing_intervals"] == 1
    assert gap["actual_rows"] == 1439
    assert duplicate["status"] == "FAIL"
    assert duplicate["duplicate_open_times"] == 1


def test_archive_rejects_unexpected_member_and_schema():
    spec = ArchiveSpec("BTCUSDT", "1m", "2025-10-23", "daily")
    try:
        validate_archive_bytes(_daily_zip(member="other.csv"), spec)
    except RuntimeError as exc:
        assert "unexpected ZIP members" in str(exc)
    else:
        raise AssertionError("unexpected archive member was accepted")
    try:
        validate_archive_bytes(_daily_zip(columns=(*CSV_COLUMNS[:-1], "other")), spec)
    except RuntimeError as exc:
        assert "CSV schema mismatch" in str(exc)
    else:
        raise AssertionError("unexpected CSV schema was accepted")


def test_archive_panel_loader_reverifies_external_bytes_and_uses_c02_normalizer(tmp_path, monkeypatch):
    spec = ArchiveSpec("BTCUSDT", "4h", "2024-07", "monthly")
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    start = 1719792000000  # 2024-07-01 00:00:00 UTC
    for index in range(186):
        open_time = start + index * 14_400_000
        writer.writerow((open_time, "100.0", "101.0", "99.0", "100.0", "1.0",
            open_time + 14_399_999, "100.0", 10, "0.5", "50.0", "0"))
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(spec.member, output.getvalue())
    blob = zipped.getvalue()
    validation = validate_archive_bytes(blob, spec)
    monkeypatch.setattr(archive_module, "planned_archives", lambda phase: (spec,))

    repository = tmp_path / "repo"
    data_root = tmp_path / "external-data"
    manifest_path = repository / "research/c04/historical_manifest.json"
    archive_path = data_root / spec.relative_path
    archive_path.parent.mkdir(parents=True)
    archive_path.write_bytes(blob)
    record = {
        "archive_id": spec.filename, "symbol": spec.symbol, "interval": spec.interval,
        "period_utc": spec.period, "cadence": spec.cadence,
        "source_url": spec.url, "http_status": 200,
        "retrieved_at_utc": "2026-10-25T00:00:00Z", "actual_bytes": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(), "data_root_relative_path": spec.relative_path,
        **validation,
    }
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps({
        "schema_version": "astrabot.binance-um-archives.v1", "phase": "pilot",
        "archive_host": "data.binance.vision", "archive_count_planned": 1,
        "archive_count_completed": 1, "archives": [record], "symbols": ["BTCUSDT"],
        "evidence_class": "OBSERVED_HISTORICAL_ARCHIVE_DATA_WITH_CLOSE_TIME_AVAILABILITY_PROXY",
        "market": "public USDⓈ-M", "total_actual_bytes": len(blob),
        "cohort_limit": "Declared cohort only", "cadence": "monthly",
        "intervals": ["5m", "15m", "1h", "4h"],
        "window": {
            "source_only_warmup": {"start": "2024-07-01T00:00:00Z", "end_exclusive": "2024-09-01T00:00:00Z"},
            "development": {"start": "2024-09-01T00:00:00Z", "end_exclusive": "2024-10-01T00:00:00Z"},
            "validation": {"start": "2024-10-01T00:00:00Z", "end_exclusive": "2024-10-15T00:00:00Z"},
            "untouched_evaluation": {"start": "2024-10-15T00:00:00Z", "end_exclusive": "2024-11-01T00:00:00Z"},
            "outcome_purge_embargo_hours": 12,
        },
    }))

    panel = load_public_um_archive_panel(manifest_path, data_root)
    bars = panel.symbols["BTCUSDT"].candles_4h
    assert len(bars) == 186
    assert bars[0].open_time.isoformat() == "2024-07-01T00:00:00+00:00"
    assert bars[0].available_at.isoformat() == "2024-07-01T04:00:00+00:00"
    assert panel.partitions[0]["raw_archive_sha256"] == hashlib.sha256(blob).hexdigest()
    assert panel.partitions[0]["normalized_row_count"] == 186
    assert panel.source_manifest["cross_archive_continuity"]["BTCUSDT:4h"]["MISSING_INTERVAL"] == 0
    with pytest.raises(ValueError, match="outside the Git repository"):
        load_public_um_archive_panel(manifest_path, repository / "raw")

    # A development-only run must not require or open held-out October bytes.
    # Reuse the existing synthetic archive fixture; the October file is absent.
    from datetime import datetime, timezone
    october = ArchiveSpec("BTCUSDT", "4h", "2024-10", "monthly")
    monkeypatch.setattr(archive_module, "planned_archives", lambda phase: (spec, october))
    manifest = json.loads(manifest_path.read_text())
    manifest.update(archive_count_planned=2, archive_count_completed=2,
                    total_actual_bytes=len(blob)*2)
    manifest["archives"].append({**record, "archive_id": october.filename,
        "period_utc": october.period, "source_url": october.url,
        "data_root_relative_path": october.relative_path})
    manifest_path.write_text(json.dumps(manifest))
    end = datetime(2024, 10, 1, tzinfo=timezone.utc)
    bounded = load_public_um_archive_panel(manifest_path, data_root, source_end_exclusive=end)
    assert len(bounded.symbols["BTCUSDT"].candles_4h) == 186
    assert bounded.source_manifest["archive_count"] == 1
    assert bounded.source_manifest["unopened_archive_ids"] == [october.filename]
    with pytest.raises(ValueError, match="archive missing"):
        load_public_um_archive_panel(manifest_path, data_root)
    with pytest.raises(ValueError, match="UTC month boundary"):
        load_public_um_archive_panel(manifest_path, data_root,
            source_end_exclusive=end.replace(day=2))
