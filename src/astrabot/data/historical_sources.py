"""Bounded-memory readers for Tardis-format Binance USD-M historical CSVs.

The adapter preserves both exchange event time (``timestamp``) and the
provider's local arrival proxy (``local_timestamp``).  It does not claim that
the latter is an AstraBot receive or execution timestamp.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
from itertools import chain
import math
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Iterator, Sequence

import numpy as np

UTC = timezone.utc
EXCHANGE = "binance-futures"
SOURCE_VERSION = "tardis-binance-futures-csv.v1"

QUOTE_HEADER = (
    "exchange", "symbol", "timestamp", "local_timestamp",
    "ask_amount", "ask_price", "bid_price", "bid_amount",
)
DERIVATIVE_HEADER = (
    "exchange", "symbol", "timestamp", "local_timestamp", "funding_timestamp",
    "funding_rate", "predicted_funding_rate", "open_interest", "last_price",
    "index_price", "mark_price",
)


class HistoricalDataError(ValueError):
    """Input failed its declared source schema or record contract."""


@dataclass
class FeedDiagnostics:
    dataset: str
    path: str
    sha256: str
    rows_seen: int = 0
    rows_valid: int = 0
    duplicates: int = 0
    event_time_ties: int = 0
    event_time_regressions: int = 0
    arrival_time_regressions: int = 0
    inverted_arrivals: int = 0
    malformed_records: int = 0
    invalid_books: int = 0
    incomplete_books: int = 0
    missing_oi: int = 0
    late_by_decision: dict[str, int] = field(default_factory=dict)
    future_by_decision: dict[str, int] = field(default_factory=dict)
    _previous_event: datetime | None = field(default=None, repr=False)
    _previous_arrival: datetime | None = field(default=None, repr=False)

    @property
    def out_of_order(self) -> bool:
        return self.event_time_regressions > 0 or self.arrival_time_regressions > 0


@dataclass(frozen=True)
class SourceObservation:
    symbol: str
    exchange: str
    event_time: datetime
    available_at: datetime
    observation_id: str
    row_number: int
    source_dataset: str
    source_sha256: str
    quality: str
    fidelity: str


@dataclass(frozen=True)
class QuoteObservation(SourceObservation):
    bid_price: Decimal
    bid_amount: Decimal
    ask_price: Decimal
    ask_amount: Decimal

    @property
    def mid_price(self) -> Decimal:
        return (self.bid_price + self.ask_price) / Decimal(2)

    @property
    def spread_fraction(self) -> Decimal:
        return (self.ask_price - self.bid_price) / self.mid_price


@dataclass(frozen=True)
class BookLevel:
    price: Decimal
    amount: Decimal


@dataclass(frozen=True)
class BookObservation(SourceObservation):
    raw_row: Sequence[str]
    missing_bid_levels: int = 0
    missing_ask_levels: int = 0

    @property
    def bids(self) -> tuple[BookLevel, ...]:
        return tuple(
            BookLevel(Decimal(self.raw_row[4 + index * 4 + 2]),
                      Decimal(self.raw_row[4 + index * 4 + 3]))
            for index in range(25)
            if self.raw_row[4 + index * 4 + 2] and self.raw_row[4 + index * 4 + 3]
        )

    @property
    def asks(self) -> tuple[BookLevel, ...]:
        return tuple(
            BookLevel(Decimal(self.raw_row[4 + index * 4]),
                      Decimal(self.raw_row[4 + index * 4 + 1]))
            for index in range(25)
            if self.raw_row[4 + index * 4] and self.raw_row[4 + index * 4 + 1]
        )

    @property
    def mid_price(self) -> Decimal:
        return (self.bids[0].price + self.asks[0].price) / Decimal(2)


@dataclass(frozen=True)
class DerivativeObservation(SourceObservation):
    open_interest: Decimal | None
    last_price: Decimal | None
    mark_price: Decimal | None
    index_price: Decimal | None
    funding_rate: Decimal | None
    predicted_funding_rate: Decimal | None
    funding_timestamp: datetime | None
    open_interest_changed_in_source: bool | None = None
    open_interest_repeat_run: int = 0
    last_open_interest_change_at: datetime | None = None


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Hash compressed source bytes in bounded memory before parsing."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def _source_row_id(dataset: str, source_sha256: str, values: Sequence[str]) -> str:
    """Hash the ordered cell sequence without materializing a JSON document per row."""
    canonical = "\x00".join(chain((dataset, source_sha256), values))
    if canonical.count("\x00") != len(values) + 1:
        raise HistoricalDataError("NUL byte is not permitted in a source CSV field")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_source(path: Path, expected_sha256: str) -> str:
    if not path.is_file():
        raise HistoricalDataError(f"source file does not exist: {path}")
    actual = sha256_file(path)
    if actual.lower() != expected_sha256.lower():
        raise HistoricalDataError(
            f"SHA-256 mismatch for {path.name}: expected {expected_sha256}, got {actual}"
        )
    return actual


def epoch_microseconds(value: str, *, field_name: str) -> datetime:
    """Parse the source's integer UTC epoch-microsecond representation exactly."""
    if not re.fullmatch(r"[0-9]{16}", value):
        raise ValueError(f"{field_name} must be a 16-digit epoch-microsecond integer")
    micros = int(value)
    try:
        return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=micros)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{field_name} is outside datetime range") from exc


def epoch_milliseconds(value: str, *, field_name: str) -> datetime:
    """Parse an optional exchange UTC epoch-millisecond timestamp."""
    if not re.fullmatch(r"[0-9]{13}", value):
        raise ValueError(f"{field_name} must be a 13-digit epoch-millisecond integer")
    millis = int(value)
    try:
        return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=millis)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{field_name} is outside datetime range") from exc


_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_BOOK_NUMERIC = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
_BOOK_ROW_NUMBERS = re.compile(rf"{_BOOK_NUMERIC}(?:,{_BOOK_NUMERIC}){{99}}")


def strict_decimal(value: str, *, field_name: str, minimum: Decimal | None = None) -> Decimal:
    if not value or not _DECIMAL.fullmatch(value):
        raise ValueError(f"{field_name} must be a non-empty decimal number")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} is not a decimal number") from exc
    if not result.is_finite() or (minimum is not None and result < minimum):
        raise ValueError(f"{field_name} must be finite and >= {minimum}")
    return result


def _book_header() -> tuple[str, ...]:
    columns = ["exchange", "symbol", "timestamp", "local_timestamp"]
    for level in range(25):
        columns.extend((f"asks[{level}].price", f"asks[{level}].amount"))
        columns.extend((f"bids[{level}].price", f"bids[{level}].amount"))
    return tuple(columns)


BOOK_HEADER = _book_header()


class _DiskDuplicateDetector:
    """Exact duplicate detection with disk-backed state, keeping RAM bounded."""

    def __init__(self, path: Path):
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=OFF")
        self.connection.execute("PRAGMA synchronous=OFF")
        self.connection.execute("CREATE TABLE seen (id TEXT PRIMARY KEY) WITHOUT ROWID")

    def duplicates(self, observation_ids: Sequence[str]) -> tuple[bool, ...]:
        if not observation_ids:
            return ()
        unique_ids = tuple(dict.fromkeys(observation_ids))
        values_sql = ",".join("(?)" for _ in unique_ids)
        inserted = {row[0] for row in self.connection.execute(
            f"INSERT OR IGNORE INTO seen(id) VALUES {values_sql} RETURNING id", unique_ids
        )}
        seen_in_batch: set[str] = set()
        duplicate_flags = []
        for observation_id in observation_ids:
            duplicate = observation_id not in inserted or observation_id in seen_in_batch
            duplicate_flags.append(duplicate)
            seen_in_batch.add(observation_id)
        return tuple(duplicate_flags)

    def close(self) -> None:
        self.connection.close()


def _rows(path: Path, expected_header: Sequence[str], diagnostics: FeedDiagnostics):
    """Yield schema-checked CSV rows; reading to EOF validates gzip CRC/trailer."""
    with tempfile.TemporaryDirectory(prefix="astrabot-c05g-") as temporary:
        detector = _DiskDuplicateDetector(Path(temporary) / "seen.sqlite3")
        try:
            with gzip.open(path, mode="rt", encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream, strict=True)
                try:
                    header = next(reader)
                except StopIteration as exc:
                    raise HistoricalDataError(f"empty gzip CSV: {path.name}") from exc
                if len(header) != len(set(header)):
                    raise HistoricalDataError(f"duplicate CSV header columns in {path.name}")
                if tuple(header) != tuple(expected_header):
                    raise HistoricalDataError(
                        f"unexpected header for {path.name}; expected {len(expected_header)} "
                        f"columns and exact order, found {len(header)}"
                    )
                pending = []
                for row_number, values in enumerate(reader, start=2):
                    diagnostics.rows_seen += 1
                    if len(values) != len(expected_header):
                        diagnostics.malformed_records += 1
                        raise HistoricalDataError(
                            f"{path.name} row {row_number}: expected {len(expected_header)} "
                            f"fields, found {len(values)}"
                        )
                    row = dict(zip(expected_header, values, strict=True))
                    row_id = _source_row_id(diagnostics.dataset, diagnostics.sha256, values)
                    pending.append((row_number, row, row_id))
                    if len(pending) >= 256:
                        yield from _emit_batch(pending, detector, diagnostics)
                        pending.clear()
                if pending:
                    yield from _emit_batch(pending, detector, diagnostics)
        except (EOFError, gzip.BadGzipFile, OSError, UnicodeError, csv.Error) as exc:
            diagnostics.malformed_records += 1
            raise HistoricalDataError(f"invalid or truncated gzip CSV {path.name}: {exc}") from exc
        finally:
            detector.close()


def _raw_book_rows(path: Path, diagnostics: FeedDiagnostics):
    """Book-specific fast path avoids allocating 104-key dicts per snapshot."""
    with tempfile.TemporaryDirectory(prefix="astrabot-c05g-") as temporary:
        detector = _DiskDuplicateDetector(Path(temporary) / "seen.sqlite3")
        try:
            with gzip.open(path, mode="rt", encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream, strict=True)
                try:
                    header = next(reader)
                except StopIteration as exc:
                    raise HistoricalDataError(f"empty gzip CSV: {path.name}") from exc
                if len(header) != len(set(header)) or tuple(header) != BOOK_HEADER:
                    raise HistoricalDataError(f"unexpected full book_snapshot_25 header in {path.name}")
                pending = []
                for row_number, values in enumerate(reader, start=2):
                    diagnostics.rows_seen += 1
                    if len(values) != len(BOOK_HEADER):
                        diagnostics.malformed_records += 1
                        raise HistoricalDataError(
                            f"{path.name} row {row_number}: expected {len(BOOK_HEADER)} fields, found {len(values)}"
                        )
                    row_id = _source_row_id(diagnostics.dataset, diagnostics.sha256, values)
                    pending.append((row_number, values, row_id))
                    if len(pending) >= 256:
                        yield from _emit_batch(pending, detector, diagnostics)
                        pending.clear()
                if pending:
                    yield from _emit_batch(pending, detector, diagnostics)
        except (EOFError, gzip.BadGzipFile, OSError, UnicodeError, csv.Error) as exc:
            diagnostics.malformed_records += 1
            raise HistoricalDataError(f"invalid or truncated gzip CSV {path.name}: {exc}") from exc
        finally:
            detector.close()


def _emit_batch(pending, detector: _DiskDuplicateDetector, diagnostics: FeedDiagnostics):
    duplicate_flags = detector.duplicates([item[2] for item in pending])
    for item, duplicate in zip(pending, duplicate_flags, strict=True):
        if duplicate:
            diagnostics.duplicates += 1
        else:
            yield item


def _common(row: dict[str, str], row_number: int, row_id: str,
            diagnostics: FeedDiagnostics, symbol: str) -> tuple[str, datetime, datetime, str]:
    try:
        if row["exchange"] != EXCHANGE:
            raise ValueError(f"unexpected exchange {row['exchange']!r}")
        if row["symbol"] != symbol:
            raise ValueError(f"mixed or unexpected symbol {row['symbol']!r}; expected {symbol}")
        event_time = epoch_microseconds(row["timestamp"], field_name="timestamp")
        available_at = epoch_microseconds(row["local_timestamp"], field_name="local_timestamp")
        diagnostics.event_time_ties += int(
            diagnostics._previous_event is not None and event_time == diagnostics._previous_event
        )
        event_regression = diagnostics._previous_event is not None and event_time < diagnostics._previous_event
        arrival_regression = diagnostics._previous_arrival is not None and available_at < diagnostics._previous_arrival
        diagnostics.event_time_regressions += int(event_regression)
        diagnostics.arrival_time_regressions += int(arrival_regression)
        diagnostics._previous_event = event_time
        diagnostics._previous_arrival = available_at
        if available_at < event_time:
            diagnostics.inverted_arrivals += 1
            return symbol, event_time, available_at, "INVALID_INVERTED_ARRIVAL"
        quality = "OUT_OF_ORDER" if event_regression or arrival_regression else "VALID"
        return symbol, event_time, available_at, quality
    except (KeyError, ValueError) as exc:
        diagnostics.malformed_records += 1
        raise HistoricalDataError(f"{diagnostics.path} row {row_number}: {exc}") from exc


def iter_quotes(path: Path, *, symbol: str, source_sha256: str,
                diagnostics: FeedDiagnostics) -> Iterator[QuoteObservation]:
    if diagnostics.dataset != "quotes" or diagnostics.sha256 != source_sha256:
        raise ValueError("quote diagnostics/source identity mismatch")
    for row_number, row, row_id in _rows(path, QUOTE_HEADER, diagnostics):
        _, event_time, available_at, quality = _common(row, row_number, row_id, diagnostics, symbol)
        if quality == "INVALID_INVERTED_ARRIVAL":
            continue
        try:
            bid_price = strict_decimal(row["bid_price"], field_name="bid_price", minimum=Decimal(0))
            bid_amount = strict_decimal(row["bid_amount"], field_name="bid_amount", minimum=Decimal(0))
            ask_price = strict_decimal(row["ask_price"], field_name="ask_price", minimum=Decimal(0))
            ask_amount = strict_decimal(row["ask_amount"], field_name="ask_amount", minimum=Decimal(0))
            if bid_price <= 0 or ask_price <= 0:
                raise ValueError("best quote prices must be positive")
            if ask_price < bid_price:
                raise ValueError("crossed best bid/ask")
        except (KeyError, ValueError) as exc:
            diagnostics.malformed_records += 1
            raise HistoricalDataError(f"{path.name} row {row_number}: {exc}") from exc
        diagnostics.rows_valid += 1
        yield QuoteObservation(
            symbol=symbol, exchange=EXCHANGE, event_time=event_time, available_at=available_at,
            observation_id=row_id, row_number=row_number, source_dataset="quotes",
            source_sha256=source_sha256, quality=quality, fidelity="UNKNOWN",
            bid_price=bid_price, bid_amount=bid_amount, ask_price=ask_price,
            ask_amount=ask_amount,
        )


def _fast_numeric(value: str, *, field_name: str, minimum: float) -> float:
    if not value or value.strip() != value or "_" in value:
        raise ValueError(f"{field_name} must be a non-empty decimal number")
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a non-empty decimal number") from exc
    if not math.isfinite(number) or number < minimum:
        raise ValueError(f"{field_name} must be finite and >= {minimum}")
    return number


def _validate_book(values: Sequence[str], row_number: int, path: Path):
    """Validate a complete 25x2 book with one compiled scan and one NumPy row."""
    numeric_fields = values[4:]
    if all(numeric_fields):
        encoded = ",".join(numeric_fields)
        if not _BOOK_ROW_NUMBERS.fullmatch(encoded):
            raise HistoricalDataError(f"{path.name} row {row_number}: malformed numeric book field")
        levels = np.fromstring(encoded, dtype=np.float64, sep=",")
        if levels.size != 100 or not np.isfinite(levels).all():
            raise HistoricalDataError(f"{path.name} row {row_number}: non-finite or malformed book values")
        ask_prices, ask_amounts = levels[0::4], levels[1::4]
        bid_prices, bid_amounts = levels[2::4], levels[3::4]
        if ((ask_prices <= 0).any() or (bid_prices <= 0).any()
                or (ask_amounts < 0).any() or (bid_amounts < 0).any()):
            raise HistoricalDataError(f"{path.name} row {row_number}: non-positive prices or negative amounts")
        bids_ordered = not (np.diff(bid_prices) > 0).any()
        asks_ordered = not (np.diff(ask_prices) < 0).any()
        crossed = ask_prices[0] < bid_prices[0]
        return 0, bids_ordered, True, 0, asks_ordered, True, crossed

    missing_bids, bids_ordered, best_bid_present = _book_side(values, "bids", row_number, path)
    missing_asks, asks_ordered, best_ask_present = _book_side(values, "asks", row_number, path)
    crossed = False
    if best_bid_present and best_ask_present:
        crossed = Decimal(values[4]) < Decimal(values[6])
    return (missing_bids, bids_ordered, best_bid_present,
            missing_asks, asks_ordered, best_ask_present, crossed)


def _book_side(values: Sequence[str], side: str, row_number: int,
               path: Path) -> tuple[int, bool, bool]:
    """Validate 25 exact-schema fields quickly; Decimal objects are made only for selected rows."""
    missing = 0
    previous: float | None = None
    valid = True
    best_present = False
    for index in range(25):
        start = 4 + index * 4 + (0 if side == "asks" else 2)
        price_text = values[start]
        amount_text = values[start + 1]
        if not price_text and not amount_text:
            missing += 1
            continue
        if not price_text or not amount_text:
            missing += 1
            valid = False
            continue
        try:
            price = _fast_numeric(price_text, field_name=f"{side}[{index}].price", minimum=0)
            _fast_numeric(amount_text, field_name=f"{side}[{index}].amount", minimum=0)
            if price <= 0:
                raise ValueError("book prices must be positive")
        except ValueError as exc:
            raise HistoricalDataError(f"{path.name} row {row_number}: {exc}") from exc
        if previous is not None:
            inverted = price > previous if side == "bids" else price < previous
            if inverted:
                valid = False
        previous = price
        if index == 0:
            best_present = True
    return missing, valid, best_present


def iter_books(path: Path, *, symbol: str, source_sha256: str,
               diagnostics: FeedDiagnostics) -> Iterator[BookObservation]:
    if diagnostics.dataset != "book_snapshot_25" or diagnostics.sha256 != source_sha256:
        raise ValueError("book diagnostics/source identity mismatch")
    for row_number, values, row_id in _raw_book_rows(path, diagnostics):
        row = {"exchange": values[0], "symbol": values[1], "timestamp": values[2], "local_timestamp": values[3]}
        _, event_time, available_at, quality = _common(row, row_number, row_id, diagnostics, symbol)
        if quality == "INVALID_INVERTED_ARRIVAL":
            continue
        (missing_bids, bids_ordered, best_bid_present, missing_asks,
         asks_ordered, best_ask_present, crossed) = _validate_book(values, row_number, path)
        if not best_bid_present or not best_ask_present:
            diagnostics.invalid_books += 1
            continue
        if not bids_ordered or not asks_ordered or crossed:
            diagnostics.invalid_books += 1
            quality = "MALFORMED"
        elif missing_bids or missing_asks:
            diagnostics.incomplete_books += 1
            quality = "INCOMPLETE"
        diagnostics.rows_valid += 1
        yield BookObservation(
            symbol=symbol, exchange=EXCHANGE, event_time=event_time, available_at=available_at,
            observation_id=row_id, row_number=row_number, source_dataset="book_snapshot_25",
            source_sha256=source_sha256, quality=quality, fidelity="UNKNOWN",
            raw_row=values, missing_bid_levels=missing_bids,
            missing_ask_levels=missing_asks,
        )


def iter_derivative_tickers(path: Path, *, symbol: str, source_sha256: str,
                            diagnostics: FeedDiagnostics) -> Iterator[DerivativeObservation]:
    if diagnostics.dataset != "derivative_ticker" or diagnostics.sha256 != source_sha256:
        raise ValueError("derivative diagnostics/source identity mismatch")
    optional_decimal_fields = (
        "open_interest", "last_price", "mark_price", "index_price", "funding_rate",
        "predicted_funding_rate",
    )
    previous_oi: Decimal | None = None
    oi_repeat_run = 0
    last_oi_change_at: datetime | None = None
    for row_number, row, row_id in _rows(path, DERIVATIVE_HEADER, diagnostics):
        _, event_time, available_at, quality = _common(row, row_number, row_id, diagnostics, symbol)
        if quality == "INVALID_INVERTED_ARRIVAL":
            continue
        parsed: dict[str, Decimal | None] = {}
        try:
            for name in optional_decimal_fields:
                raw = row[name]
                parsed[name] = None if raw == "" else strict_decimal(
                    raw, field_name=name,
                    minimum=None if name in ("funding_rate", "predicted_funding_rate") else Decimal(0)
                )
                if name in ("open_interest", "last_price", "mark_price", "index_price") and parsed[name] == 0:
                    raise ValueError(f"{name} must be positive when present")
            raw_funding_time = row["funding_timestamp"]
            funding_timestamp = None if raw_funding_time == "" else epoch_microseconds(
                raw_funding_time, field_name="funding_timestamp"
            )
        except (KeyError, ValueError) as exc:
            diagnostics.malformed_records += 1
            raise HistoricalDataError(f"{path.name} row {row_number}: {exc}") from exc
        if parsed["open_interest"] is None:
            diagnostics.missing_oi += 1
            oi_changed = None
        else:
            oi_changed = None if previous_oi is None else parsed["open_interest"] != previous_oi
            if previous_oi is None:
                oi_repeat_run = 1
            elif oi_changed:
                oi_repeat_run = 1
                last_oi_change_at = event_time
            else:
                oi_repeat_run += 1
            previous_oi = parsed["open_interest"]
        diagnostics.rows_valid += 1
        yield DerivativeObservation(
            symbol=symbol, exchange=EXCHANGE, event_time=event_time, available_at=available_at,
            observation_id=row_id, row_number=row_number, source_dataset="derivative_ticker",
            source_sha256=source_sha256, quality=quality, fidelity="UNKNOWN",
            open_interest=parsed["open_interest"], last_price=parsed["last_price"],
            mark_price=parsed["mark_price"], index_price=parsed["index_price"],
            funding_rate=parsed["funding_rate"],
            predicted_funding_rate=parsed["predicted_funding_rate"],
            funding_timestamp=funding_timestamp,
            open_interest_changed_in_source=oi_changed,
            open_interest_repeat_run=oi_repeat_run,
            last_open_interest_change_at=last_oi_change_at,
        )


def new_diagnostics(dataset: str, path: Path, sha256: str) -> FeedDiagnostics:
    return FeedDiagnostics(dataset=dataset, path=str(path), sha256=sha256)
