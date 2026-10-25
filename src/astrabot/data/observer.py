"""Bounded, one-shot public market observation prototype for C05-C0.

This module intentionally has no streaming loop, scheduler, credential input,
signing code, private endpoint, or order surface. Raw responses are immutable
files beneath an external data root; JSON sidecars contain capture provenance
and conservative quality findings.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .models import stable_id

BASE_URL = "https://fapi.binance.com"
ALLOWED_SYMBOLS = ("SOLUSDT", "DOGEUSDT")
ALLOWED_PATHS = frozenset({
    "/fapi/v1/time",
    "/fapi/v1/exchangeInfo",
    "/fapi/v1/ticker/bookTicker",
    "/fapi/v1/depth",
    "/fapi/v1/openInterest",
    "/fapi/v1/premiumIndex",
    "/fapi/v1/aggTrades",
})
MAX_REQUESTS = 12
MAX_RESPONSE_BYTES = 5_000_000
STALE_AFTER_MS = {"time": 5_000, "openInterest": 60_000,
                  "premiumIndex": 60_000, "aggTrades": 10_000}
SCHEMA_VERSION = "c05.observer-record.v1"
SUMMARY_VERSION = "c05.observer-summary.v1"
SOURCE_VERSION = "binance-usdm-public-rest-candidate.v1"
FIXTURE_TIME = datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc)
FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "c05_observer"

UNIT_NOTES = {
    "time": "serverTime is retained as an exchange epoch-millisecond clock value; not a market event.",
    "exchangeInfo": "Exchange-native metadata and filter strings are preserved verbatim; historical effective time is unverified.",
    "bookTicker": "Raw bid/ask price and quantity strings are retained; the C02 unit convention is quote-per-base/base quantity and is not revalidated here.",
    "depth": "Raw bid/ask price and quantity strings are retained; level quantity semantics are not revalidated here.",
    "openInterest": "Raw openInterest string only; OI unit validation=UNVERIFIED; USDT notional=null.",
    "premiumIndex": "Raw mark/index/funding strings and nextFundingTime are retained; no funding settlement is asserted.",
    "aggTrades": "Raw Binance aggregate-trade fields are retained; C02 convention is quote-per-base/base quantity; event availability remains unverified.",
}


@dataclass(frozen=True)
class RequestSpec:
    feed: str
    symbol: str | None
    path: str
    params: tuple[tuple[str, str], ...]

    @property
    def key(self) -> str:
        return f"{self.feed}:{self.symbol or 'ALL'}"


@dataclass(frozen=True)
class TransportResult:
    status: int | None
    body: bytes
    headers: dict[str, str]
    error: str | None = None
    truncated: bool = False
    content_length: int | None = None


def request_specs() -> tuple[RequestSpec, ...]:
    """The fixed 12-request plan: one time, one metadata, five per symbol."""
    specs = [
        RequestSpec("time", None, "/fapi/v1/time", ()),
        RequestSpec("exchangeInfo", None, "/fapi/v1/exchangeInfo", ()),
    ]
    for symbol in ALLOWED_SYMBOLS:
        specs.extend((
            RequestSpec("bookTicker", symbol, "/fapi/v1/ticker/bookTicker", (("symbol", symbol),)),
            RequestSpec("depth", symbol, "/fapi/v1/depth", (("limit", "5"), ("symbol", symbol))),
            RequestSpec("openInterest", symbol, "/fapi/v1/openInterest", (("symbol", symbol),)),
            RequestSpec("premiumIndex", symbol, "/fapi/v1/premiumIndex", (("symbol", symbol),)),
            RequestSpec("aggTrades", symbol, "/fapi/v1/aggTrades", (("limit", "10"), ("symbol", symbol))),
        ))
    if len(specs) != MAX_REQUESTS:
        raise AssertionError("fixed request plan drifted")
    for spec in specs:
        build_url(spec.path, dict(spec.params))
    return tuple(specs)


_PARAMS_BY_PATH = {
    "/fapi/v1/time": frozenset(),
    "/fapi/v1/exchangeInfo": frozenset(),
    "/fapi/v1/ticker/bookTicker": frozenset({"symbol"}),
    "/fapi/v1/depth": frozenset({"symbol", "limit"}),
    "/fapi/v1/openInterest": frozenset({"symbol"}),
    "/fapi/v1/premiumIndex": frozenset({"symbol"}),
    "/fapi/v1/aggTrades": frozenset({"symbol", "limit"}),
}


def build_url(path: str, params: dict[str, str] | None = None) -> str:
    """Build only an approved public URL; callers cannot select host or method."""
    if path not in ALLOWED_PATHS:
        raise ValueError("endpoint is not in the C05 public GET allowlist")
    params = dict(params or {})
    if any(key.lower() in {"signature", "timestamp", "recvwindow", "apikey", "x-mbx-apikey"}
           for key in params):
        raise ValueError("authentication/signing parameters are forbidden")
    if set(params) - _PARAMS_BY_PATH[path]:
        raise ValueError("parameter is not allowed for this public endpoint")
    symbol = params.get("symbol")
    if symbol is not None and symbol not in ALLOWED_SYMBOLS:
        raise ValueError("symbol is outside the two-symbol C05 allowlist")
    if path == "/fapi/v1/depth" and params.get("limit") not in (None, "5"):
        raise ValueError("depth is limited to five levels per side")
    if path == "/fapi/v1/aggTrades" and params.get("limit") not in (None, "10"):
        raise ValueError("aggregate trades are limited to ten rows per symbol")
    query = urlencode(sorted(params.items()))
    return BASE_URL + path + ("?" + query if query else "")


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware UTC timestamp required")
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def validate_data_root(root: str | Path) -> Path:
    resolved = Path(root).expanduser().resolve()
    repo = repository_root()
    if resolved == repo or repo in resolved.parents:
        raise ValueError("ASTRABOT_DATA_ROOT must resolve outside the Git repository")
    return resolved


def _immutable_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != body:
            raise ValueError(f"refusing to overwrite immutable observer record: {path}")
        return
    path.write_bytes(body)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _read_bounded(response, byte_limit: int) -> tuple[bytes, dict[str, str], int | None, bool]:
    headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
    raw_length = headers.get("content-length")
    try:
        content_length = int(raw_length) if raw_length is not None else None
    except (TypeError, ValueError):
        content_length = None
    if content_length is not None and content_length > byte_limit:
        return b"", headers, content_length, True
    body = response.read(max(0, byte_limit))
    truncated = (content_length is not None and len(body) < content_length)
    if content_length is None and byte_limit > 0 and len(body) >= byte_limit:
        truncated = True
    return body, headers, content_length, truncated


def public_get(url: str, timeout: float, byte_limit: int) -> TransportResult:
    """Send one unauthenticated GET without following redirects or retrying."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "fapi.binance.com" or parsed.path not in ALLOWED_PATHS:
        raise ValueError("request URL is outside the approved Binance USD-M host/path allowlist")
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        params = dict(pairs)
        if len(params) != len(pairs) or build_url(parsed.path, params) != url:
            raise ValueError("request URL query is outside the approved C05 parameter allowlist")
    except ValueError as exc:
        raise ValueError("request URL query is outside the approved C05 parameter allowlist") from exc
    request = Request(url, method="GET", headers={"User-Agent": "AstraBot-C05-observer/1"})
    opener = build_opener(_NoRedirect())
    try:
        response = opener.open(request, timeout=timeout)
    except HTTPError as exc:
        response = exc
    except (URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", None)
        message = str(reason if reason is not None else exc)
        return TransportResult(None, b"", {}, error=f"{type(exc).__name__}: {message}")
    try:
        status = getattr(response, "status", None) or response.getcode()
        body, headers, content_length, truncated = _read_bounded(response, byte_limit)
        return TransportResult(status, body, headers, truncated=truncated, content_length=content_length)
    except (OSError, TimeoutError) as exc:
        return TransportResult(getattr(response, "status", None), b"", {},
                               error=f"{type(exc).__name__}: {exc}")
    finally:
        response.close()


def _fixture_payload(spec: RequestSpec, fixture_root: Path) -> bytes:
    path = fixture_root / f"{spec.feed}.json"
    body = path.read_bytes()
    if spec.symbol is not None:
        body = body.replace(b"$SYMBOL", spec.symbol.encode("ascii"))
    return body


def _default_fixture_transport(spec: RequestSpec, url: str, byte_limit: int,
                               fixture_root: Path = FIXTURE_ROOT) -> TransportResult:
    body = _fixture_payload(spec, fixture_root)
    return TransportResult(200, body[:byte_limit], {"content-length": str(len(body))},
                           truncated=len(body) > byte_limit, content_length=len(body))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _required_fields(spec: RequestSpec, payload) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    findings: list[str] = []
    if spec.feed == "time":
        if not isinstance(payload, dict) or "serverTime" not in payload:
            missing.append("serverTime")
    elif spec.feed == "exchangeInfo":
        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
            missing.append("symbols")
        else:
            present = {row.get("symbol") for row in payload["symbols"] if isinstance(row, dict)}
            for symbol in ALLOWED_SYMBOLS:
                if symbol not in present:
                    missing.append(f"symbols[{symbol}]")
            for symbol in ALLOWED_SYMBOLS:
                row = next((item for item in payload["symbols"]
                            if isinstance(item, dict) and item.get("symbol") == symbol), None)
                if row is not None:
                    for field in ("contractType", "status", "marginAsset", "filters"):
                        if field not in row:
                            missing.append(f"symbols[{symbol}].{field}")
    elif spec.feed == "bookTicker":
        fields = ("symbol", "bidPrice", "bidQty", "askPrice", "askQty")
        if not isinstance(payload, dict):
            missing.extend(fields)
        else:
            missing.extend(field for field in fields if field not in payload)
            if spec.symbol is not None and payload.get("symbol") != spec.symbol:
                findings.append("WRONG_SYMBOL")
            try:
                bid, ask = Decimal(str(payload["bidPrice"])), Decimal(str(payload["askPrice"]))
                bid_qty = Decimal(str(payload["bidQty"]))
                ask_qty = Decimal(str(payload["askQty"]))
                if not all(value.is_finite() for value in (bid, ask, bid_qty, ask_qty)):
                    findings.append("INVALID_BID_ASK_NUMBER")
                elif bid <= 0 or ask <= 0 or bid_qty <= 0 or ask_qty <= 0 or ask < bid:
                    findings.append("INVALID_OR_CROSSED_BID_ASK")
            except (KeyError, TypeError, ValueError, InvalidOperation):
                if "bidPrice" not in missing and "askPrice" not in missing:
                    findings.append("INVALID_BID_ASK_PRICE")
    elif spec.feed == "depth":
        fields = ("lastUpdateId", "bids", "asks")
        if not isinstance(payload, dict):
            missing.extend(fields)
        else:
            missing.extend(field for field in fields if field not in payload)
            if not isinstance(payload.get("bids"), list) or not payload.get("bids"):
                findings.append("MISSING_BIDS")
            if not isinstance(payload.get("asks"), list) or not payload.get("asks"):
                findings.append("MISSING_ASKS")
            else:
                findings.extend(_validate_depth(payload))
    elif spec.feed == "openInterest":
        fields = ("symbol", "openInterest", "time")
        if not isinstance(payload, dict):
            missing.extend(fields)
        else:
            missing.extend(field for field in fields if field not in payload)
            if spec.symbol is not None and payload.get("symbol") != spec.symbol:
                findings.append("WRONG_SYMBOL")
            if "openInterest" in payload and not _positive_decimal(payload["openInterest"]):
                findings.append("INVALID_OPEN_INTEREST_VALUE")
    elif spec.feed == "premiumIndex":
        fields = ("symbol", "markPrice", "indexPrice", "lastFundingRate", "nextFundingTime", "time")
        if not isinstance(payload, dict):
            missing.extend(fields)
        else:
            missing.extend(field for field in fields if field not in payload)
            if spec.symbol is not None and payload.get("symbol") != spec.symbol:
                findings.append("WRONG_SYMBOL")
            for field in ("markPrice", "indexPrice"):
                if field in payload and not _positive_decimal(payload[field]):
                    findings.append(f"INVALID_{field.upper()}")
            if "lastFundingRate" in payload and not _finite_decimal(payload["lastFundingRate"]):
                findings.append("INVALID_FUNDING_RATE")
    elif spec.feed == "aggTrades":
        if not isinstance(payload, list) or not payload:
            missing.append("trade_rows")
        else:
            for index, row in enumerate(payload):
                if not isinstance(row, dict):
                    missing.append(f"trade_rows[{index}]")
                    continue
                for field in ("a", "p", "q", "f", "l", "T", "m"):
                    if field not in row:
                        missing.append(f"trade_rows[{index}].{field}")
                if "p" in row and not _positive_decimal(row["p"]):
                    findings.append(f"INVALID_TRADE_PRICE[{index}]")
                if "q" in row and not _positive_decimal(row["q"]):
                    findings.append(f"INVALID_TRADE_QUANTITY[{index}]")
                if "m" in row and not isinstance(row["m"], bool):
                    findings.append(f"INVALID_BUYER_MAKER_FLAG[{index}]")
    return missing, findings


def _finite_decimal(value) -> bool:
    try:
        return Decimal(str(value)).is_finite()
    except (InvalidOperation, TypeError, ValueError):
        return False


def _positive_decimal(value) -> bool:
    try:
        number = Decimal(str(value))
        return number.is_finite() and number > 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def _validate_depth(payload: dict) -> list[str]:
    findings: list[str] = []
    parsed: dict[str, list[tuple[Decimal, Decimal]]] = {"bids": [], "asks": []}
    for side in ("bids", "asks"):
        for index, level in enumerate(payload.get(side, [])):
            try:
                if not isinstance(level, (list, tuple)) or len(level) < 2:
                    raise ValueError
                price, quantity = Decimal(str(level[0])), Decimal(str(level[1]))
                if not price.is_finite() or not quantity.is_finite() or price <= 0 or quantity <= 0:
                    raise ValueError
                parsed[side].append((price, quantity))
            except (InvalidOperation, TypeError, ValueError):
                findings.append(f"INVALID_{side.upper()}_LEVEL[{index}]")
    bids, asks = parsed["bids"], parsed["asks"]
    if bids and any(bids[i][0] < bids[i + 1][0] for i in range(len(bids) - 1)):
        findings.append("BIDS_OUT_OF_ORDER")
    if asks and any(asks[i][0] > asks[i + 1][0] for i in range(len(asks) - 1)):
        findings.append("ASKS_OUT_OF_ORDER")
    if bids and asks and asks[0][0] < bids[0][0]:
        findings.append("CROSSED_DEPTH")
    return findings


def _epoch_timestamp(value, field: str, *, kind: str) -> dict:
    result = {"field": field, "kind": kind, "raw_value": value, "utc": None, "valid": False}
    if isinstance(value, bool):
        result["error"] = "boolean is not an epoch timestamp"
        return result
    try:
        numeric = int(value)
        # Reject fractional strings and floats instead of silently rounding them.
        if str(value).strip() != str(numeric):
            result["error"] = "timestamp is not an integer epoch-millisecond value"
            return result
        stamp = (datetime.fromtimestamp(numeric // 1000, timezone.utc)
                 + timedelta(milliseconds=numeric % 1000))
    except (TypeError, ValueError, OverflowError, OSError):
        result["error"] = "invalid epoch-millisecond timestamp"
        return result
    result["utc"] = utc_iso(stamp)
    result["valid"] = True
    return result


def _timestamp_rows(spec: RequestSpec, payload) -> list[dict]:
    rows: list[dict] = []
    if not isinstance(payload, (dict, list)):
        return rows
    if spec.feed in ("time", "exchangeInfo") and isinstance(payload, dict) and "serverTime" in payload:
        rows.append(_epoch_timestamp(payload["serverTime"], "serverTime", kind="EXCHANGE_SERVER_CLOCK"))
    elif spec.feed == "openInterest" and isinstance(payload, dict) and "time" in payload:
        rows.append(_epoch_timestamp(payload["time"], "time", kind="SAMPLED_OBSERVATION_EVENT"))
    elif spec.feed == "premiumIndex" and isinstance(payload, dict) and "time" in payload:
        rows.append(_epoch_timestamp(payload["time"], "time", kind="SAMPLED_OBSERVATION_EVENT"))
        if "nextFundingTime" in payload:
            rows.append(_epoch_timestamp(payload["nextFundingTime"], "nextFundingTime",
                                         kind="SCHEDULED_FUNDING_TIME"))
    if spec.feed == "exchangeInfo" and isinstance(payload, dict):
        for symbol_row in payload.get("symbols", []):
            if isinstance(symbol_row, dict) and symbol_row.get("symbol") in ALLOWED_SYMBOLS:
                for field in ("onboardDate", "deliveryDate"):
                    if field in symbol_row:
                        rows.append(_epoch_timestamp(symbol_row[field],
                            f"symbols[{symbol_row['symbol']}].{field}", kind="INSTRUMENT_SCHEDULE_TIMESTAMP"))
    elif spec.feed == "aggTrades" and isinstance(payload, list):
        rows.extend(_epoch_timestamp(row.get("T"), f"[{i}].T", kind="TRADE_EVENT")
                    for i, row in enumerate(payload) if isinstance(row, dict) and "T" in row)
    return rows


def check_trade_order(rows: Iterable[dict]) -> list[str]:
    """Detect duplicate IDs and out-of-order/gapped aggregate-trade rows."""
    findings: list[str] = []
    seen: set[str] = set()
    previous_id: int | None = None
    previous_time: int | None = None
    for row in rows:
        try:
            current_id = int(row["a"])
            current_time = int(row["T"])
        except (KeyError, TypeError, ValueError):
            findings.append("INVALID_TRADE_ID_OR_TIMESTAMP")
            continue
        identity = str(row["a"])
        if identity in seen:
            findings.append("DUPLICATE_OBSERVATION")
            continue
        seen.add(identity)
        if previous_id is not None:
            if current_id <= previous_id or (previous_time is not None and current_time < previous_time):
                findings.append("OUT_OF_ORDER_OBSERVATION")
            elif current_id != previous_id + 1:
                findings.append("MISSING_TRADE_ID_INTERVAL")
        previous_id, previous_time = current_id, current_time
    return findings


def _staleness(spec: RequestSpec, timestamps: list[dict], received: datetime) -> str:
    usable = [row for row in timestamps if row["valid"] and row["kind"] in {
        "SAMPLED_OBSERVATION_EVENT", "TRADE_EVENT"}]
    max_age_ms = STALE_AFTER_MS.get(spec.feed)
    if spec.feed == "time":
        usable = [row for row in timestamps if row["valid"]]
    if not usable or max_age_ms is None:
        return "UNDETERMINED_NO_MARKET_EVENT_TIME"
    latest_ms = max(int(datetime.fromisoformat(row["utc"].replace("Z", "+00:00")).timestamp() * 1000)
                    for row in usable)
    age_ms = int(received.timestamp() * 1000) - latest_ms
    if age_ms > max_age_ms:
        return "STALE"
    if age_ms < -5_000:
        return "FUTURE_TIMESTAMP_CLOCK_REVIEW"
    return "FRESH_WITHIN_LOCAL_CLOCK_ASSUMPTION"


def _clock_offsets(timestamps: list[dict], started: datetime, received: datetime) -> list[dict]:
    offsets = []
    midpoint = started + (received - started) / 2
    for row in timestamps:
        if row["kind"] != "EXCHANGE_SERVER_CLOCK" or not row["valid"]:
            continue
        server = datetime.fromisoformat(row["utc"].replace("Z", "+00:00"))
        offsets.append({
            "field": row["field"],
            "server_minus_request_start_ms": round((server - started).total_seconds() * 1000, 3),
            "server_minus_response_receive_ms": round((server - received).total_seconds() * 1000, 3),
            "server_minus_request_midpoint_ms": round((server - midpoint).total_seconds() * 1000, 3),
            "interpretation": "offset includes request/response latency and local clock error; midpoint is an estimate, not a clock correction",
        })
    return offsets


def _capture_quality(spec: RequestSpec, result: TransportResult, started: datetime,
                     received: datetime) -> dict:
    findings: list[str] = []
    errors: list[str] = []
    missing: list[str] = []
    invalid_timestamps: list[dict] = []
    timestamps: list[dict] = []
    payload = None
    if result.error:
        errors.append(result.error)
    if result.truncated:
        findings.append("RESPONSE_TRUNCATED_OR_BYTE_BUDGET_REACHED")
    if result.status is None:
        errors.append("NO_HTTP_RESPONSE_STATUS")
    elif not 200 <= result.status < 300:
        errors.append(f"HTTP_STATUS_{result.status}")
    if not errors and not result.truncated:
        try:
            payload = json.loads(result.body)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
            errors.append(f"INVALID_JSON: {exc}")
        if not errors:
            missing, payload_findings = _required_fields(spec, payload)
            findings.extend(payload_findings)
            if missing:
                findings.append("MISSING_REQUIRED_FIELDS")
            if spec.feed == "aggTrades" and isinstance(payload, list):
                findings.extend(check_trade_order(payload))
            timestamps = _timestamp_rows(spec, payload)
            invalid_timestamps = [row for row in timestamps if not row["valid"]]
            if invalid_timestamps:
                findings.append("INVALID_TIMESTAMP")
    stale_status = _staleness(spec, timestamps, received)
    if stale_status == "STALE":
        findings.append("STALE_OBSERVATION")
    if stale_status == "FUTURE_TIMESTAMP_CLOCK_REVIEW":
        findings.append("FUTURE_TIMESTAMP_REQUIRES_CLOCK_REVIEW")
    if missing or invalid_timestamps:
        availability = "INCOMPLETE"
    elif errors or result.truncated:
        availability = "UNAVAILABLE"
    elif findings:
        availability = "QUALITY_REVIEW"
    else:
        availability = "CAPTURED_NOT_C02_READY"
    return {
        "availability": availability,
        "errors": list(dict.fromkeys(errors)),
        "missing_fields": missing,
        "invalid_timestamps": invalid_timestamps,
        "timestamp_observations": timestamps,
        "binance_event_times_utc": [row["utc"] for row in timestamps
                                    if row["valid"] and row["kind"] != "EXCHANGE_SERVER_CLOCK"],
        "exchange_server_times_utc": [row["utc"] for row in timestamps
                                       if row["valid"] and row["kind"] == "EXCHANGE_SERVER_CLOCK"],
        "clock_offsets": _clock_offsets(timestamps, started, received),
        "stale_status": stale_status,
        "findings": sorted(set(findings)),
        "oi_unit_validation": "UNVERIFIED" if spec.feed == "openInterest" else None,
        "oi_notional_usdt": None,
        "historical_availability": "UNVERIFIED",
        "event_clearance": "UNVERIFIED",
        "c02_ready": False,
    }


def _write_json(path: Path, value: dict) -> None:
    body = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
    _immutable_write(path, body)


def _fixture_clock() -> Callable[[], datetime]:
    calls = 0

    def clock() -> datetime:
        nonlocal calls
        value = FIXTURE_TIME + timedelta(milliseconds=((calls + 1) // 2) * 10)
        calls += 1
        return value

    return clock


def _fixture_monotonic() -> Callable[[], float]:
    value = 0.0

    def monotonic() -> float:
        nonlocal value
        current = value
        value += 0.001
        return current

    return monotonic


def _summary_status(record: dict) -> str:
    if not record["request_attempted"]:
        return "NOT_ATTEMPTED"
    if record["quality"]["availability"] == "CAPTURED_NOT_C02_READY":
        return "FIXTURE_VALIDATION_PASS" if record["evidence_class"] == "SYNTHETIC_FIXTURE" else "CAPTURED"
    return record["quality"]["availability"]


def run_once(*, mode: str, data_root: str | Path, transport=None,
             clock: Callable[[], datetime] | None = None,
             monotonic: Callable[[], float] | None = None,
             fixture_root: str | Path = FIXTURE_ROOT) -> dict:
    """Capture deterministic fixtures or one bounded live batch; never loops."""
    if mode not in {"fixture", "live"}:
        raise ValueError("mode must be fixture or live")
    root = validate_data_root(data_root)
    root.mkdir(parents=True, exist_ok=True)
    specs = request_specs()
    if len(specs) > MAX_REQUESTS:
        raise AssertionError("request plan exceeds hard request cap")
    if mode == "fixture":
        transport = transport or (lambda spec, url, limit:
                                  _default_fixture_transport(spec, url, limit, Path(fixture_root)))
        clock = clock or _fixture_clock()
        monotonic = monotonic or _fixture_monotonic()
    else:
        clock = clock or _now_utc
        import time
        monotonic = monotonic or time.monotonic
        transport = transport or (lambda spec, url, limit: public_get(url, timeout=10.0, byte_limit=limit))

    records: list[dict] = []
    raw_bodies: list[bytes] = []
    bytes_read = 0
    attempted = 0
    halt_reason: str | None = None
    for index, spec in enumerate(specs):
        url = build_url(spec.path, dict(spec.params))
        if halt_reason is not None:
            started = received = clock()
            result = TransportResult(None, b"", {}, error=halt_reason)
            request_attempted = False
            duration_ms = 0.0
            unavailable_reason = halt_reason
        else:
            remaining = MAX_RESPONSE_BYTES - bytes_read
            if remaining <= 0:
                halt_reason = "TOTAL_RESPONSE_BYTE_BUDGET_EXHAUSTED"
                started = received = clock()
                result = TransportResult(None, b"", {}, error=halt_reason)
                request_attempted = False
                duration_ms = 0.0
                unavailable_reason = halt_reason
            else:
                started = clock()
                tick = monotonic()
                request_attempted = True
                attempted += 1
                try:
                    result = transport(spec, url, remaining)
                    if not isinstance(result, TransportResult):
                        raise TypeError("transport must return TransportResult")
                except Exception as exc:
                    result = TransportResult(None, b"", {}, error=f"{type(exc).__name__}: {exc}")
                if len(result.body) > remaining:
                    result = TransportResult(result.status, result.body[:remaining], result.headers,
                        error=result.error, truncated=True, content_length=result.content_length)
                duration_ms = round(max(0.0, monotonic() - tick) * 1000, 3)
                received = clock()
                bytes_read += len(result.body)
                unavailable_reason = None
                if result.error or result.status is None:
                    halt_reason = result.error or "NO_HTTP_RESPONSE_STATUS"
                elif not 200 <= result.status < 300:
                    halt_reason = f"LIVE_HALTED_AFTER_HTTP_STATUS_{result.status}"
                elif result.truncated:
                    halt_reason = "LIVE_HALTED_AFTER_RESPONSE_BYTE_BUDGET_TRUNCATION"

        quality = _capture_quality(spec, result, started, received)
        raw_digest = sha256_bytes(result.body)
        source_id = stable_id("c05.source-record.v1", mode, spec.key, url,
                              utc_iso(started), raw_digest)
        record = {
            "schema_version": SCHEMA_VERSION,
            "source_id": source_id,
            "source": "BINANCE_USDM_PUBLIC_REST_CANDIDATE" if mode == "live" else "SYNTHETIC_FIXTURE",
            "evidence_class": "VENUE_RESPONSE_UNVERIFIED" if mode == "live" else "SYNTHETIC_FIXTURE",
            "feed": spec.feed,
            "symbol": spec.symbol,
            "source_url": url,
            "request_method": "GET",
            "authenticated": False,
            "request_attempted": request_attempted,
            "request_start_utc": utc_iso(started),
            "response_received_utc": utc_iso(received),
            "duration_ms": duration_ms,
            "http_status": result.status,
            "response_headers": result.headers,
            "original_units": UNIT_NOTES[spec.feed],
            "source_version": SOURCE_VERSION,
            "schema_version_record": SCHEMA_VERSION,
            "sha256": raw_digest,
            "response_bytes": len(result.body),
            "response_content_length": result.content_length,
            "response_truncated": result.truncated,
            "transport_error": result.error,
            "unavailable_reason": unavailable_reason,
            "quality": quality,
            "raw_relative_path": f"raw/{source_id}.bin",
        }
        if mode == "fixture":
            record["fixture_id"] = f"c05.observer.{spec.feed}.v1"
        records.append(record)
        raw_bodies.append(result.body)

    run_id = stable_id("c05.observer-run.v1", mode,
                       [(row["source_id"], row["sha256"], row["request_attempted"]) for row in records])
    run_dir = root / "c05-observer" / run_id
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)
    (run_dir / "records").mkdir(parents=True, exist_ok=True)
    for index, (record, body) in enumerate(zip(records, raw_bodies)):
        raw_path = run_dir / record["raw_relative_path"]
        _immutable_write(raw_path, body)
        record_path = run_dir / "records" / f"{index:02d}-{record['source_id']}.json"
        record["record_relative_path"] = str(record_path.relative_to(root))
        _write_json(record_path, record)

    summary = {
        "summary_schema_version": SUMMARY_VERSION,
        "run_id": run_id,
        "mode": mode,
        "evidence_class": "SYNTHETIC_FIXTURE" if mode == "fixture" else "VENUE_RESPONSE_UNVERIFIED",
        "symbols": list(ALLOWED_SYMBOLS),
        "request_plan_count": len(specs),
        "network_request_count": attempted if mode == "live" else 0,
        "request_count": attempted,
        "request_cap": MAX_REQUESTS,
        "downloaded_response_bytes": bytes_read,
        "response_byte_cap": MAX_RESPONSE_BYTES,
        "halt_reason": halt_reason,
        "quality_results": [
            {"source_id": row["source_id"], "feed": row["feed"], "symbol": row["symbol"],
             "http_status": row["http_status"], "status": _summary_status(row),
             "findings": row["quality"]["findings"], "errors": row["quality"]["errors"],
             "stale_status": row["quality"]["stale_status"]}
            for row in records
        ],
        "unavailable_feeds": [row["source_id"] for row in records
                              if _summary_status(row) in {"UNAVAILABLE", "INCOMPLETE", "NOT_ATTEMPTED"}],
        "event_clearance": "UNVERIFIED",
        "historical_availability": "UNVERIFIED",
        "oi_unit_validation": "UNVERIFIED",
        "oi_notional_usdt": None,
        "c02_readiness": "BLOCKED",
        "c02_blockers": [
            "one-shot snapshots do not satisfy historical warm-up or 60 consecutive one-minute spread samples",
            "OI units and USDT notional are unvalidated",
            "event clearance is not captured by these endpoints",
            "actual execution, fees, and queue/fill outcomes are absent",
        ],
        "source_records": [
            {"source_id": row["source_id"], "feed": row["feed"], "symbol": row["symbol"],
             "http_status": row["http_status"], "sha256": row["sha256"],
             "response_bytes": row["response_bytes"], "record_path": row["record_relative_path"],
             "raw_path": str((run_dir / row["raw_relative_path"]).relative_to(root)),
             "request_attempted": row["request_attempted"]}
            for row in records
        ],
    }
    _write_json(run_dir / "summary.json", summary)
    summary["summary_relative_path"] = str((run_dir / "summary.json").relative_to(root))
    summary["data_root"] = str(root)
    return summary


def _run_cli() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="One-shot, read-only C05 public-market observer")
    parser.add_argument("--live-once", action="store_true",
                        help="issue one bounded sequence of public unauthenticated GETs; never retries")
    args = parser.parse_args()
    mode = "live" if args.live_once else "fixture"
    env_root = os.environ.get("ASTRABOT_DATA_ROOT")
    if mode == "live" and not env_root:
        parser.error("--live-once requires ASTRABOT_DATA_ROOT set to an external path")
    if mode == "fixture":
        root = env_root or str(Path(tempfile.gettempdir()) / "astrabot-c05-observer-data")
    else:
        root = env_root
    try:
        summary = run_once(mode=mode, data_root=root)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by the CLI smoke check
    raise SystemExit(_run_cli())
