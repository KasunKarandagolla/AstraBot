"""Small safety and provenance checks for the isolated C05 one-shot observer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from astrabot.data import observer
from astrabot.data.observer import (
    ALLOWED_SYMBOLS,
    FIXTURE_ROOT,
    MAX_REQUESTS,
    MAX_RESPONSE_BYTES,
    TransportResult,
    build_url,
    check_trade_order,
    public_get,
    run_once,
    sha256_bytes,
)


def _fixture_transport(spec, url, limit):
    body = (FIXTURE_ROOT / f"{spec.feed}.json").read_bytes()
    if spec.symbol:
        body = body.replace(b"$SYMBOL", spec.symbol.encode("ascii"))
    return TransportResult(200, body[:limit], {"content-length": str(len(body))},
                           truncated=len(body) > limit, content_length=len(body))


def test_fixture_default_records_distinct_times_raw_bytes_and_reproducible_checksums(tmp_path):
    first = run_once(mode="fixture", data_root=tmp_path)
    second = run_once(mode="fixture", data_root=tmp_path)

    assert first["run_id"] == second["run_id"]
    assert first["network_request_count"] == 0
    assert first["request_plan_count"] == MAX_REQUESTS == 12
    assert first["downloaded_response_bytes"] <= MAX_RESPONSE_BYTES
    assert len(first["source_records"]) == 12
    assert all(item["status"] == "FIXTURE_VALIDATION_PASS" for item in first["quality_results"])

    time_record = next(row for row in first["source_records"] if row["feed"] == "time")
    metadata = json.loads((tmp_path / time_record["record_path"]).read_text())
    raw = (tmp_path / time_record["raw_path"]).read_bytes()
    payload = json.loads(raw)
    assert sha256_bytes(raw) == metadata["sha256"] == time_record["sha256"]
    server_time = payload["serverTime"]
    assert metadata["request_start_utc"] != metadata["response_received_utc"]
    assert metadata["quality"]["exchange_server_times_utc"]
    assert metadata["quality"]["clock_offsets"][0]["server_minus_request_start_ms"] != 0
    assert server_time > 0


def test_endpoint_and_symbol_allowlists_reject_unapproved_requests():
    with pytest.raises(ValueError, match="allowlist"):
        build_url("/fapi/v1/account")
    with pytest.raises(ValueError, match="two-symbol"):
        build_url("/fapi/v1/openInterest", {"symbol": "BTCUSDT"})
    with pytest.raises(ValueError, match="authentication"):
        build_url("/fapi/v1/openInterest", {"symbol": "SOLUSDT", "timestamp": "1"})
    with pytest.raises(ValueError, match="five levels"):
        build_url("/fapi/v1/depth", {"symbol": "DOGEUSDT", "limit": "1000"})
    assert ALLOWED_SYMBOLS == ("SOLUSDT", "DOGEUSDT")


def test_transport_can_only_send_an_unauthenticated_public_get(monkeypatch):
    seen = {}

    class Response:
        status = 200
        headers = {"Content-Length": "2"}

        def read(self, limit):
            seen["read_limit"] = limit
            return b"{}"

        def getcode(self):
            return self.status

        def close(self):
            pass

    class Opener:
        def open(self, request, timeout):
            seen["method"] = request.get_method()
            seen["url"] = request.full_url
            seen["headers"] = dict(request.header_items())
            seen["timeout"] = timeout
            return Response()

    monkeypatch.setattr(observer, "build_opener", lambda *_: Opener())
    result = public_get("https://fapi.binance.com/fapi/v1/time", 2.0, 128)
    assert result.status == 200 and result.body == b"{}"
    assert seen["method"] == "GET"
    assert seen["url"] == "https://fapi.binance.com/fapi/v1/time"
    assert not any(name.lower() in {"authorization", "x-mbx-apikey"}
                   for name, _ in seen["headers"].items())
    with pytest.raises(ValueError, match="query"):
        public_get("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT", 2.0, 128)


def test_missing_fields_and_invalid_timestamps_fail_closed(tmp_path):
    def malformed(spec, url, limit):
        if spec.feed == "time":
            body = b'{"serverTime":"not-a-timestamp"}'
        elif spec.feed == "openInterest":
            body = json.dumps({"symbol": spec.symbol, "openInterest": "10"}).encode()
        elif spec.feed == "premiumIndex":
            body = b"null"
        else:
            return _fixture_transport(spec, url, limit)
        return TransportResult(200, body, {"content-length": str(len(body))}, content_length=len(body))

    summary = run_once(mode="fixture", data_root=tmp_path, transport=malformed)
    rows = {row["feed"] + ":" + str(row["symbol"]): row for row in summary["quality_results"]}
    time_quality = json.loads((tmp_path / summary["source_records"][0]["record_path"]).read_text())["quality"]
    assert rows["time:None"]["status"] == "INCOMPLETE"
    assert time_quality["invalid_timestamps"][0]["field"] == "serverTime"
    oi = next(row for row in summary["source_records"]
              if row["feed"] == "openInterest" and row["symbol"] == "SOLUSDT")
    oi_quality = json.loads((tmp_path / oi["record_path"]).read_text())["quality"]
    assert oi_quality["availability"] == "INCOMPLETE"
    assert "time" in oi_quality["missing_fields"]
    premium = next(row for row in summary["source_records"]
                   if row["feed"] == "premiumIndex" and row["symbol"] == "SOLUSDT")
    premium_quality = json.loads((tmp_path / premium["record_path"]).read_text())["quality"]
    assert premium_quality["availability"] == "INCOMPLETE"
    assert "symbol" in premium_quality["missing_fields"]
    assert summary["c02_readiness"] == "BLOCKED"


def test_duplicate_and_out_of_order_trade_observations_are_detectable():
    first = {"a": 10, "T": 100, "p": "1", "q": "1", "m": False}
    duplicate = {**first}
    out_of_order = {"a": 9, "T": 90, "p": "1", "q": "1", "m": False}
    findings = check_trade_order([first, duplicate])
    assert "DUPLICATE_OBSERVATION" in findings
    findings = check_trade_order([{**first, "a": 11}, out_of_order])
    assert "OUT_OF_ORDER_OBSERVATION" in findings


def test_stale_source_timestamp_is_reported_not_replaced_by_receive_time(tmp_path):
    def stale_oi(spec, url, limit):
        if spec.feed == "openInterest":
            body = json.dumps({"symbol": spec.symbol, "openInterest": "10", "time": 1000}).encode()
            return TransportResult(200, body, {"content-length": str(len(body))}, content_length=len(body))
        return _fixture_transport(spec, url, limit)

    summary = run_once(mode="fixture", data_root=tmp_path, transport=stale_oi)
    oi = next(row for row in summary["source_records"]
              if row["feed"] == "openInterest" and row["symbol"] == "SOLUSDT")
    sidecar = json.loads((tmp_path / oi["record_path"]).read_text())
    assert sidecar["quality"]["stale_status"] == "STALE"
    assert sidecar["quality"]["binance_event_times_utc"] == ["1970-01-01T00:00:01.000Z"]
    assert "STALE_OBSERVATION" in sidecar["quality"]["findings"]


def test_unvalidated_oi_and_missing_event_clearance_never_become_ready(tmp_path):
    summary = run_once(mode="fixture", data_root=tmp_path)
    oi = next(row for row in summary["source_records"]
              if row["feed"] == "openInterest" and row["symbol"] == "DOGEUSDT")
    oi_sidecar = json.loads((tmp_path / oi["record_path"]).read_text())
    assert oi_sidecar["quality"]["oi_unit_validation"] == "UNVERIFIED"
    assert oi_sidecar["quality"]["oi_notional_usdt"] is None
    assert oi_sidecar["quality"]["event_clearance"] == "UNVERIFIED"
    assert summary["event_clearance"] == "UNVERIFIED"
    assert summary["historical_availability"] == "UNVERIFIED"
    assert summary["c02_readiness"] == "BLOCKED"


def test_repository_path_is_rejected_before_any_files_or_requests(tmp_path):
    repository_path = observer.repository_root() / "raw-data-c05-test"
    called = []
    with pytest.raises(ValueError, match="outside the Git repository"):
        run_once(mode="live", data_root=repository_path,
                 transport=lambda *_: called.append(True))
    assert called == []
    assert not repository_path.exists()


def test_live_policy_error_stops_without_retries_or_remaining_requests(tmp_path):
    calls = []

    def blocked(spec, url, limit):
        calls.append(url)
        body = b"restricted location"
        return TransportResult(451, body, {"content-length": str(len(body))}, content_length=len(body))

    summary = run_once(mode="live", data_root=tmp_path, transport=blocked)
    assert len(calls) == 1
    assert summary["request_count"] == 1
    assert summary["downloaded_response_bytes"] == len(b"restricted location")
    assert summary["halt_reason"] == "LIVE_HALTED_AFTER_HTTP_STATUS_451"
    assert sum(row["request_attempted"] for row in summary["source_records"]) == 1
    assert all(not row["request_attempted"] for row in summary["source_records"][1:])


def test_global_body_budget_is_enforced_for_a_transport_result(tmp_path):
    calls = []

    def oversized(spec, url, limit):
        calls.append(limit)
        return TransportResult(200, b"x" * (limit + 1), {}, content_length=limit + 1)

    summary = run_once(mode="live", data_root=tmp_path, transport=oversized)
    assert len(calls) == 1
    assert summary["downloaded_response_bytes"] == MAX_RESPONSE_BYTES
    assert summary["downloaded_response_bytes"] <= MAX_RESPONSE_BYTES
    assert summary["halt_reason"] == "LIVE_HALTED_AFTER_RESPONSE_BYTE_BUDGET_TRUNCATION"
