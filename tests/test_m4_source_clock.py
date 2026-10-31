"""M4 source-clock integration tests using AstraBot's real Candle and Trade contracts.

Synthetic fixtures only: no exchange, archive retrieval, P&L or signal decisions.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from astrabot.data.models import Candle, Trade, binance_usdm_instrument_id
from astrabot.research.m4_source_clock import (
    SourceCompleteness, SourceNotReady, aggregate_verified_30s, prior_utc_day_reference,
)

UTC = timezone.utc
START = datetime(2023, 1, 3, tzinfo=UTC)
SYMBOL = "BTCUSDT"
IID = binance_usdm_instrument_id(SYMBOL)


def candle(opened: datetime, *, available_at: datetime | None = None) -> Candle:
    close = opened + timedelta(minutes=1) - timedelta(milliseconds=1)
    available = available_at or close + timedelta(milliseconds=1)
    return Candle(
        symbol=SYMBOL, instrument_id=IID, interval="1m", open_time=opened,
        close_time=close, event_time=close, available_at=available,
        ingested_at=available, as_of=available, data_source="synthetic.m4",
        source_version="m4.synthetic.v1", units="quote_per_base",
        fidelity="SYNTHETIC_FIXTURE", readiness="READY", quality="VALID",
        observation_id=f"bar:{opened.isoformat()}", config_hash="synthetic",
        open=D("100"), high=D("102"), low=D("98"), close=D("101"),
        base_volume=D("10"), trade_count=1, is_closed=True,
        source_record_id=f"source:{opened.isoformat()}",
    )


def trade(number: int, second: int, *, price="100", side="BUY", quantity="1") -> Trade:
    t = START + timedelta(seconds=second)
    buyer_is_maker = side == "SELL"
    return Trade(
        symbol=SYMBOL, instrument_id=IID,
        event_time=t, available_at=t, ingested_at=t, as_of=t,
        data_source="synthetic.m4", source_version="m4.synthetic.v1",
        units="base_quantity", fidelity="SYNTHETIC_FIXTURE",
        readiness="READY", quality="VALID", observation_id=f"t:{number}",
        config_hash="synthetic", trade_id=str(number), aggregate_trade_id=str(number),
        first_trade_id=str(number), last_trade_id=str(number),
        price=D(price), base_quantity=D(quantity),
        quote_quantity=D(price)*D(quantity), buyer_is_maker=buyer_is_maker,
        aggressor_side=side,
    )


def complete(*, observed: datetime | None = None, digest: str = "a" * 64) -> SourceCompleteness:
    return SourceCompleteness(
        complete_through=START + timedelta(seconds=30),
        replay_proxy_available_at=observed or START + timedelta(seconds=30, milliseconds=1),
        source_digest=digest, provenance="SYNTHETIC_FIXTURE",
    )


def sample_day():
    start = START - timedelta(days=1)
    return [candle(start + timedelta(minutes=i)) for i in range(1440)]


def test_uses_actual_astrabot_candle_for_midnight_reference():
    ref = prior_utc_day_reference(sample_day(), day=date(2023, 1, 3), as_of=START)
    assert (ref.high, ref.low, ref.candle_count) == (D("102"), D("98"), 1440)
    assert ref.available_at == START
    assert ref.instrument_id == IID
    assert ref.fidelity == "SYNTHETIC_FIXTURE"


def test_prior_day_reference_preserves_venue_fidelity_and_rejects_derived_bars():
    venue_rows = [c.model_copy(update={"fidelity": "VENUE_REPORTED"}) for c in sample_day()]
    ref = prior_utc_day_reference(venue_rows, day=START.date(), as_of=START)
    assert ref.fidelity == "VENUE_REPORTED_1M_EXCHANGE_CLOSE_PROXY"

    derived_rows = [c.model_copy(update={"fidelity": "BAR_DERIVED_APPROX"}) for c in sample_day()]
    with pytest.raises(SourceNotReady, match="venue-reported or synthetic candles"):
        prior_utc_day_reference(derived_rows, day=START.date(), as_of=START)


def test_actual_candle_late_availability_fails_closed():
    rows = sample_day()
    rows[-1] = rows[-1].model_copy(update={"available_at": START + timedelta(seconds=2)})
    with pytest.raises(SourceNotReady, match="not available"):
        prior_utc_day_reference(rows, day=START.date(), as_of=START)


def test_future_candle_does_not_repaint_prior_day():
    rows = sample_day()
    old = prior_utc_day_reference(rows, day=START.date(), as_of=START)
    extra = candle(START).model_copy(update={"high": D("999"), "low": D("1")})
    new = prior_utc_day_reference([*rows, extra], day=START.date(), as_of=START)
    assert (new.high, new.low, new.source_digest) == (old.high, old.low, old.source_digest)


def test_true_30s_aggregation_from_actual_trade_contract():
    rows = [trade(1, 2, price="100", quantity="2"),
            trade(2, 14, price="101", side="SELL"),
            trade(3, 29, price="99", quantity="3")]
    result = aggregate_verified_30s(
        rows, bucket_start=START, as_of=START + timedelta(seconds=30, milliseconds=1),
        completeness=complete(),
    )
    assert (result.open, result.high, result.low, result.close) == (
        D("100"), D("101"), D("99"), D("99"))
    assert (result.aggressive_buy_quantity, result.aggressive_sell_quantity,
            result.signed_aggressive_quantity) == (D("5"), D("1"), D("4"))
    assert result.fidelity == "SYNTHETIC_FIXTURE"


def test_30s_aggregation_rejects_approximate_trade_side_inputs():
    estimated = trade(1, 2).model_copy(update={"fidelity": "BAR_DERIVED_APPROX"})
    with pytest.raises(SourceNotReady, match="trade-derived fidelity"):
        aggregate_verified_30s([estimated], bucket_start=START,
                               as_of=START+timedelta(seconds=31), completeness=complete())


def test_30s_aggregation_rejects_mixed_synthetic_and_venue_fidelity():
    rows = [trade(1, 2), trade(2, 3).model_copy(update={"fidelity": "TRADE_AGG"})]
    with pytest.raises(SourceNotReady, match="consistent trade-derived fidelity"):
        aggregate_verified_30s(rows, bucket_start=START,
                               as_of=START+timedelta(seconds=31), completeness=complete())


def test_future_trade_outside_bucket_cannot_repaint_result():
    rows = [trade(1, 2), trade(2, 13)]
    kwargs = {"bucket_start": START, "as_of": START+timedelta(seconds=30, milliseconds=1),
              "completeness": complete()}
    old = aggregate_verified_30s(rows, **kwargs)
    future = trade(3, 30, price="10000")
    assert aggregate_verified_30s([*rows, future], **kwargs) == old


def test_actual_trade_quality_gap_blocks_output():
    rows = [trade(1, 2), trade(3, 13)]
    with pytest.raises(SourceNotReady, match="continuity gap"):
        aggregate_verified_30s(rows, bucket_start=START,
                               as_of=START+timedelta(minutes=1), completeness=complete())


def test_bad_source_digest_is_rejected():
    with pytest.raises(SourceNotReady, match="SHA-256"):
        aggregate_verified_30s([trade(1, 2)], bucket_start=START,
                               as_of=START+timedelta(minutes=1),
                               completeness=complete(digest="x" * 64))


def test_source_watermark_must_exist_as_of_decision():
    with pytest.raises(SourceNotReady, match="watermark unavailable"):
        aggregate_verified_30s([trade(1, 2)], bucket_start=START,
                               as_of=START+timedelta(seconds=30, milliseconds=1),
                               completeness=complete(observed=START+timedelta(seconds=31)))


def test_1m_ohlc_is_not_accepted_as_a_trade_source():
    with pytest.raises(SourceNotReady, match="not OHLC"):
        aggregate_verified_30s([candle(START)], bucket_start=START,
                               as_of=START+timedelta(seconds=31), completeness=complete())

def test_prior_day_digest_changes_if_ohlc_changes_without_id_change():
    rows = sample_day()
    old = prior_utc_day_reference(rows, day=START.date(), as_of=START)
    changed = rows.copy()
    changed[3] = changed[3].model_copy(update={"high": D("103")})
    new = prior_utc_day_reference(changed, day=START.date(), as_of=START)
    assert old.source_digest != new.source_digest
    assert old.high != new.high


def test_prior_day_digest_binds_symbol_and_instrument_identity():
    original = prior_utc_day_reference(
        sample_day(), day=START.date(), as_of=START)
    other_symbol = [
        c.model_copy(update={
            "symbol": "ETHUSDT",
            "instrument_id": binance_usdm_instrument_id("ETHUSDT"),
        })
        for c in sample_day()
    ]
    other = prior_utc_day_reference(
        other_symbol, day=START.date(), as_of=START)
    assert (other.symbol, other.instrument_id) != (original.symbol, original.instrument_id)
    assert other.source_digest != original.source_digest


def test_prior_day_digest_binds_reference_asof_clock():
    rows = sample_day()
    midnight = prior_utc_day_reference(rows, day=START.date(), as_of=START)
    later = prior_utc_day_reference(
        rows, day=START.date(), as_of=START+timedelta(minutes=1))
    assert (midnight.high, midnight.low) == (later.high, later.low)
    assert later.source_digest != midnight.source_digest


def test_prior_day_nonfinite_candle_values_fail_closed():
    rows = sample_day()
    rows[0] = rows[0].model_copy(update={"high": D("NaN")})
    with pytest.raises(SourceNotReady, match="invalid prior-day candle OHLC"):
        prior_utc_day_reference(rows, day=START.date(), as_of=START)


def test_nonfinite_trade_values_fail_closed_in_30s_aggregation():
    kwargs = dict(bucket_start=START, as_of=START+timedelta(seconds=31),
                  completeness=complete())
    with pytest.raises(SourceNotReady, match="trade price or quantity"):
        aggregate_verified_30s([trade(1, 2).model_copy(update={"price": D("NaN")})], **kwargs)
    with pytest.raises(SourceNotReady, match="trade price or quantity"):
        aggregate_verified_30s([trade(1, 2).model_copy(update={"base_quantity": D("Infinity")})], **kwargs)


def test_30s_digest_changes_if_trade_price_changes_without_id_change():
    kwargs = dict(bucket_start=START, as_of=START+timedelta(seconds=31), completeness=complete())
    original = [trade(1, 2), trade(2, 13)]
    prior = aggregate_verified_30s(original, **kwargs)
    changed = [original[0], original[1].model_copy(update={"price": D("104"),
                 "quote_quantity": D("104")})]
    after = aggregate_verified_30s(changed, **kwargs)
    assert prior.source_digest == after.source_digest
    assert prior.input_digest != after.input_digest
    assert prior.high != after.high


def test_30s_input_digest_binds_instrument_identity():
    kwargs = dict(bucket_start=START, as_of=START+timedelta(seconds=31), completeness=complete())
    btc = aggregate_verified_30s([trade(1, 2)], **kwargs)
    eth_trade = trade(1, 2).model_copy(update={
        "symbol": "ETHUSDT",
        "instrument_id": binance_usdm_instrument_id("ETHUSDT"),
    })
    eth = aggregate_verified_30s([eth_trade], **kwargs)
    assert eth.input_digest != btc.input_digest


def test_hashed_archive_attestation_requires_each_row_source_hash():
    attestation = SourceCompleteness(
        complete_through=START+timedelta(seconds=30),
        replay_proxy_available_at=START+timedelta(seconds=30, milliseconds=1),
        source_digest="a"*64, provenance="HASH_VERIFIED_ARCHIVE_REPLAY",
        verified_at=datetime(2026, 10, 31, tzinfo=UTC))
    kwargs = dict(bucket_start=START, as_of=START+timedelta(seconds=31), completeness=attestation)
    with pytest.raises(SourceNotReady, match="archive record hash"):
        aggregate_verified_30s([trade(1, 2)], **kwargs)
    hashed = trade(1, 2).model_copy(update={"source_sha256": "a"*64})
    result = aggregate_verified_30s([hashed], **kwargs)
    assert result.source_digest == "a"*64
    assert len(result.input_digest) == 64


def test_invalid_attestation_object_fails_closed():
    with pytest.raises(SourceNotReady, match="source-completeness evidence"):
        aggregate_verified_30s([trade(1, 2)], bucket_start=START,
                               as_of=START+timedelta(seconds=31), completeness=None)


def test_retrospective_archive_verification_is_not_market_arrival():
    # A 2026 audit can authenticate a 2023 file, but cannot establish original
    # 2023 owner receipt. The output is expressly an exchange-clock replay proxy.
    attestation = SourceCompleteness(
        complete_through=START+timedelta(seconds=30),
        replay_proxy_available_at=START+timedelta(seconds=30, milliseconds=1),
        source_digest="a"*64, provenance="HASH_VERIFIED_ARCHIVE_REPLAY",
        verified_at=datetime(2026, 10, 31, tzinfo=UTC))
    hashed = trade(1, 2).model_copy(update={"source_sha256": "a"*64})
    result = aggregate_verified_30s(
        [hashed], bucket_start=START, as_of=START+timedelta(seconds=31),
        completeness=attestation)
    assert result.available_at == START+timedelta(seconds=30, milliseconds=1)
    assert attestation.verified_at > result.available_at


def test_archive_claim_without_verification_time_fails_closed():
    attestation = SourceCompleteness(
        complete_through=START+timedelta(seconds=30),
        replay_proxy_available_at=START+timedelta(seconds=30, milliseconds=1),
        source_digest="a"*64, provenance="HASH_VERIFIED_ARCHIVE_REPLAY")
    hashed = trade(1, 2).model_copy(update={"source_sha256": "a"*64})
    with pytest.raises(SourceNotReady, match="verification timestamp required"):
        aggregate_verified_30s(
            [hashed], bucket_start=START, as_of=START+timedelta(seconds=31),
            completeness=attestation)
