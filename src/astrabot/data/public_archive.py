"""Bounded, public Binance USDⓈ-M historical kline archive acquisition.

Only the read-only ``data.binance.vision`` archive host is accepted. This module
uses the inherited HTTPS proxy and TLS verification; it never reads credentials
or calls trading/account API endpoints.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT")
SMOKE_DATE = "2025-10-23"
PILOT_MONTHS = ("2024-07", "2024-08", "2024-09", "2024-10")
PILOT_INTERVALS = ("5m", "15m", "1h", "4h")
CSV_COLUMNS = (
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
)
INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000,
               "1h": 3_600_000, "4h": 14_400_000}
ARCHIVE_HOST = "data.binance.vision"
DEFAULT_MAX_TOTAL_BYTES = 1024 * 1024 * 1024
DEFAULT_MAX_FILE_BYTES = 256 * 1024 * 1024
MIN_FREE_RESERVE_BYTES = 64 * 1024 * 1024


class ArchiveError(RuntimeError):
    """A bounded source or archive-integrity failure; callers must stop."""


@dataclass(frozen=True)
class ArchiveSpec:
    symbol: str
    interval: str
    period: str
    cadence: str

    @property
    def filename(self) -> str:
        return f"{self.symbol}-{self.interval}-{self.period}.zip"

    @property
    def member(self) -> str:
        return self.filename[:-4] + ".csv"

    @property
    def relative_path(self) -> str:
        return f"raw/{self.cadence}/klines/{self.symbol}/{self.interval}/{self.filename}"

    @property
    def url(self) -> str:
        return (f"https://{ARCHIVE_HOST}/data/futures/um/{self.cadence}/klines/"
                f"{self.symbol}/{self.interval}/{self.filename}")


def planned_archives(phase: str) -> tuple[ArchiveSpec, ...]:
    if phase == "smoke":
        return tuple(ArchiveSpec(s, "1m", SMOKE_DATE, "daily") for s in SYMBOLS)
    if phase == "pilot":
        return tuple(ArchiveSpec(s, interval, month, "monthly")
                     for month in PILOT_MONTHS for interval in PILOT_INTERVALS for s in SYMBOLS)
    raise ValueError("phase must be smoke or pilot")


def _period_bounds(spec: ArchiveSpec) -> tuple[int, int]:
    if spec.cadence == "daily":
        start_day = date.fromisoformat(spec.period)
        start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=timezone.utc)
        end = datetime.fromtimestamp(start.timestamp() + 86_400, timezone.utc)
    elif spec.cadence == "monthly":
        year, month = (int(x) for x in spec.period.split("-"))
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=timezone.utc)
    else:
        raise ValueError(f"unsupported cadence {spec.cadence!r}")
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _iso_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def validate_archive_bytes(blob: bytes, spec: ArchiveSpec) -> dict[str, Any]:
    """Validate one complete UTC daily/monthly kline ZIP and return byte evidence."""
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            members = archive.namelist()
            bad_member = archive.testzip()
            if bad_member is not None:
                raise ArchiveError(f"ZIP integrity failure in member {bad_member!r}")
            if members != [spec.member]:
                raise ArchiveError(f"unexpected ZIP members: {members!r}; expected [{spec.member!r}]")
            csv_bytes = archive.read(spec.member)
    except zipfile.BadZipFile as exc:
        raise ArchiveError(f"invalid ZIP archive: {exc}") from exc

    start_ms, end_ms = _period_bounds(spec)
    step = INTERVAL_MS[spec.interval]
    expected_rows, remainder = divmod(end_ms - start_ms, step)
    if remainder:
        raise ArchiveError("period duration is not divisible by kline interval")
    reader = csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig", errors="strict"), newline=""))
    try:
        header = tuple(next(reader))
    except StopIteration as exc:
        raise ArchiveError("CSV has no header or data") from exc
    if header != CSV_COLUMNS:
        raise ArchiveError(f"CSV schema mismatch: {header!r}")

    previous: int | None = None
    first: int | None = None
    last: int | None = None
    row_count = 0
    duplicate_count = 0
    out_of_order_count = 0
    missing_intervals = 0
    first_gap: dict[str, str] | None = None
    for line_number, row in enumerate(reader, start=2):
        if len(row) != len(CSV_COLUMNS):
            raise ArchiveError(f"CSV row {line_number} has {len(row)} fields; expected 12")
        try:
            opened = int(row[0])
            opened_price, high, low, closed_price = map(float, row[1:5])
            volume, quote_volume = float(row[5]), float(row[7])
            close_time = int(row[6])
            trade_count = int(row[8])
            taker_volume, taker_quote_volume = float(row[9]), float(row[10])
            float(row[11])
        except (TypeError, ValueError) as exc:
            raise ArchiveError(f"CSV row {line_number} contains a non-numeric field") from exc
        if (not all(math.isfinite(x) for x in (opened_price, high, low, closed_price,
                         volume, quote_volume, taker_volume, taker_quote_volume))
                or min(opened_price, high, low, closed_price) <= 0
                or min(volume, quote_volume, taker_volume, taker_quote_volume, trade_count) < 0
                or high < max(opened_price, low, closed_price)
                or low > min(opened_price, high, closed_price)):
            raise ArchiveError(f"CSV row {line_number} has invalid OHLCV values")
        if close_time != opened + step - 1:
            raise ArchiveError(f"CSV row {line_number} close_time does not match interval")
        if opened < start_ms or opened >= end_ms or (opened - start_ms) % step:
            raise ArchiveError(f"CSV row {line_number} timestamp is outside/aligned incorrectly")
        if previous is not None:
            if opened == previous:
                duplicate_count += 1
            elif opened < previous:
                out_of_order_count += 1
            elif opened > previous + step:
                count = (opened - previous) // step - 1
                if (opened - previous) % step:
                    raise ArchiveError(f"CSV row {line_number} timestamp is off interval grid")
                missing_intervals += count
                if first_gap is None:
                    first_gap = {"start": _iso_ms(previous + step), "end": _iso_ms(opened - step)}
        if first is None:
            first = opened
        last = opened
        previous = opened
        row_count += 1

    quality = {
        "expected_rows": expected_rows,
        "actual_rows": row_count,
        "first_open_time": _iso_ms(first) if first is not None else None,
        "last_open_time": _iso_ms(last) if last is not None else None,
        "duplicate_open_times": duplicate_count,
        "out_of_order_open_times": out_of_order_count,
        "missing_intervals": missing_intervals,
        "first_gap": first_gap,
        "status": "PASS",
    }
    if (row_count != expected_rows or first != start_ms or last != end_ms - step
            or duplicate_count or out_of_order_count or missing_intervals):
        quality["status"] = "FAIL"
    return {
        "members": [spec.member],
        "csv_schema": list(header),
        "csv_member_bytes": len(csv_bytes),
        "csv_member_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "coverage_start": _iso_ms(first) if first is not None else None,
        "coverage_end": _iso_ms(last + step - 1) if last is not None else None,
        "quality": quality,
    }


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname != ARCHIVE_HOST:
            raise urllib.error.HTTPError(req.full_url, code,
                f"cross-host or non-HTTPS archive redirect rejected: {newurl}", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _external_data_root(repo_root: Path) -> Path:
    configured = os.environ.get("ASTRABOT_DATA_ROOT")
    if not configured:
        raise ArchiveError("ASTRABOT_DATA_ROOT must point outside the Git repository")
    root = Path(configured).expanduser().resolve()
    repo = repo_root.resolve()
    if root == repo or repo in root.parents:
        raise ArchiveError("ASTRABOT_DATA_ROOT resolves inside the Git repository")
    return root


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def acquire_phase(
    phase: str,
    *,
    repo_root: Path,
    manifest_path: Path,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    batch_size: int = 7,
    delay_seconds: float = 0.25,
    opener=None,
    clock=None,
) -> dict[str, Any]:
    """Download the fixed phase plan sequentially, checkpointing each archive."""
    if max_total_bytes <= 0 or max_file_bytes <= 0 or not 1 <= batch_size <= 7:
        raise ValueError("invalid bounded acquisition limits")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be nonnegative")
    root = _external_data_root(repo_root)
    root.mkdir(parents=True, exist_ok=True)
    plan = planned_archives(phase)
    manifest_path = manifest_path.resolve()
    if repo_root.resolve() not in manifest_path.parents:
        raise ArchiveError("manifest must be stored inside the Git repository")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("phase") != phase or manifest.get("schema_version") != "astrabot.binance-um-archives.v1":
            raise ArchiveError("existing manifest does not match requested phase/schema")
    else:
        manifest = {
            "schema_version": "astrabot.binance-um-archives.v1",
            "phase": phase,
            "source": "Binance public USDⓈ-M historical kline archives",
            "archive_host": ARCHIVE_HOST,
            "market": "USDⓈ-M perpetual; USDT-settled; public archives only",
            "evidence_class": "OBSERVED_HISTORICAL_ARCHIVE_DATA_WITH_CLOSE_TIME_AVAILABILITY_PROXY",
            "symbols": list(SYMBOLS),
            "cohort_limit": "Declared pilot cohort; not a reconstructed historical dynamic universe.",
            "window": ({"smoke_date_utc": SMOKE_DATE} if phase == "smoke" else {
                "source_only_warmup": {"start": "2024-07-01T00:00:00Z", "end_exclusive": "2024-09-01T00:00:00Z"},
                "development": {"start": "2024-09-01T00:00:00Z", "end_exclusive": "2024-10-01T00:00:00Z"},
                "validation": {"start": "2024-10-01T00:00:00Z", "end_exclusive": "2024-10-15T00:00:00Z"},
                "untouched_evaluation": {"start": "2024-10-15T00:00:00Z", "end_exclusive": "2024-11-01T00:00:00Z"},
                "outcome_purge_embargo_hours": 12,
            }),
            "intervals": ["1m"] if phase == "smoke" else list(PILOT_INTERVALS),
            "cadence": "daily" if phase == "smoke" else "monthly",
            "archive_count_planned": len(plan),
            "archives": [],
            "limitations": [
                "Archive candle close_time + 1 ms is an availability proxy; original publication/ingestion latency is unavailable.",
                "No historical contract metadata, validated OI, event clearance, quotes/depth, funding settlements, or observed IOC fills are inferred from klines.",
            ],
        }
    recorded = {row["archive_id"]: row for row in manifest["archives"]}
    recorded_bytes = sum(int(row["actual_bytes"]) for row in manifest["archives"])
    if recorded_bytes > max_total_bytes:
        raise ArchiveError("recorded archives exceed configured total byte cap")
    planned_ids = {spec.filename for spec in plan}
    if set(recorded) - planned_ids:
        raise ArchiveError("manifest contains records outside the fixed acquisition plan")
    handler = _SameHostRedirect()
    active_opener = opener or urllib.request.build_opener(handler)
    current_clock = clock or (lambda: datetime.now(timezone.utc))
    last_request_at: float | None = None
    batch_items = 0

    for spec in plan:
        if spec.filename in recorded:
            row = recorded[spec.filename]
            path = (root / row["data_root_relative_path"]).resolve()
            if root not in path.parents:
                raise ArchiveError(f"recorded path escapes ASTRABOT_DATA_ROOT: {spec.filename}")
            if not path.is_file() or path.stat().st_size != row["actual_bytes"]:
                raise ArchiveError(f"recorded archive missing/size mismatch: {spec.filename}")
            digest = _sha256_path(path)
            if digest != row["sha256"]:
                raise ArchiveError(f"recorded archive checksum mismatch: {spec.filename}")
            continue

        destination = root / spec.relative_path
        if destination.exists():
            raise ArchiveError(f"unmanifested destination already exists: {destination}")
        if recorded_bytes >= max_total_bytes:
            raise ArchiveError("total archive byte limit reached")
        if shutil.disk_usage(root).free < MIN_FREE_RESERVE_BYTES:
            raise ArchiveError("less than 64 MiB free-space reserve remains")
        if last_request_at is not None and delay_seconds:
            remaining = delay_seconds - (time.monotonic() - last_request_at)
            if remaining > 0:
                time.sleep(remaining)
        request = urllib.request.Request(spec.url, headers={
            "User-Agent": "AstraBot public historical archive verifier/1.0",
            "Accept": "application/zip",
        }, method="GET")
        last_request_at = time.monotonic()
        try:
            response = active_opener.open(request, timeout=60)
        except urllib.error.HTTPError as exc:
            raise ArchiveError(f"HTTP {exc.code} for {spec.url}: {exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ArchiveError(f"network error for {spec.url}: {exc}") from exc
        with response:
            status = int(getattr(response, "status", response.getcode()))
            final_url = response.geturl()
            final = urllib.parse.urlsplit(final_url)
            if status != 200:
                raise ArchiveError(f"HTTP {status} for {spec.url}")
            if final.scheme != "https" or final.hostname != ARCHIVE_HOST:
                raise ArchiveError(f"unexpected final archive URL: {final_url}")
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > max_file_bytes:
                raise ArchiveError(f"archive Content-Length exceeds per-file cap: {content_length}")
            if content_length is not None and recorded_bytes + int(content_length) > max_total_bytes:
                raise ArchiveError("archive Content-Length exceeds total byte cap")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + ".part")
            digest = hashlib.sha256()
            size = 0
            try:
                with temporary.open("wb") as stream:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        size += len(block)
                        if size > max_file_bytes:
                            raise ArchiveError(f"archive exceeds per-file cap: {spec.filename}")
                        if recorded_bytes + size > max_total_bytes:
                            raise ArchiveError("download would exceed total archive byte cap")
                        if shutil.disk_usage(root).free < max(MIN_FREE_RESERVE_BYTES, len(block)):
                            raise ArchiveError("free-space reserve exhausted during download")
                        digest.update(block)
                        stream.write(block)
                if content_length is not None and size != int(content_length):
                    raise ArchiveError(f"Content-Length mismatch for {spec.filename}: {content_length} != {size}")
                blob = temporary.read_bytes()
                archive_validation = validate_archive_bytes(blob, spec)
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary.replace(destination)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise

        row = {
            "archive_id": spec.filename,
            "symbol": spec.symbol,
            "interval": spec.interval,
            "cadence": spec.cadence,
            "period_utc": spec.period,
            "source_url": spec.url,
            "http_status": status,
            "retrieved_at_utc": current_clock().astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "final_url": final_url,
            "actual_bytes": size,
            "sha256": digest.hexdigest(),
            "data_root_relative_path": spec.relative_path,
            **archive_validation,
        }
        manifest["archives"] = [*manifest["archives"], row]
        manifest["archives"].sort(key=lambda x: (x["period_utc"], x["symbol"], x["interval"]))
        manifest["archive_count_completed"] = len(manifest["archives"])
        manifest["total_actual_bytes"] = sum(int(x["actual_bytes"]) for x in manifest["archives"])
        recorded[spec.filename] = row
        recorded_bytes += size
        _atomic_write_json(manifest_path, manifest)
        batch_items += 1
        print(f"{spec.filename}: HTTP {status}, {size} bytes, SHA256 {row['sha256']}, "
              f"rows {archive_validation['quality']['actual_rows']}/"
              f"{archive_validation['quality']['expected_rows']}, "
              f"duplicates {archive_validation['quality']['duplicate_open_times']}, "
              f"gaps {archive_validation['quality']['missing_intervals']}, "
              f"ZIP members {archive_validation['members']}")
        if archive_validation["quality"]["status"] != "PASS":
            raise ArchiveError(f"data-quality failure in {spec.filename}: {archive_validation['quality']}")
        if batch_items >= batch_size:
            batch_items = 0
            if phase == "pilot" and len(recorded) < len(plan):
                return manifest

    manifest["archive_count_completed"] = len(manifest["archives"])
    manifest["total_actual_bytes"] = sum(int(x["actual_bytes"]) for x in manifest["archives"])
    _atomic_write_json(manifest_path, manifest)
    return manifest
