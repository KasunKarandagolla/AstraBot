# C05-J integrated economic research decision packet

Decision: **INSUFFICIENT_EVIDENCE**. T1/R1/B1 remain **RESEARCH_ONLY**; phase credit 45%.

Packet SHA-256: `5d1c6c6c1d4a6e38f642c7d3f6e264d9dd5f9247f4a50fd31efda5b5d4d91c20`

Verified normalized historical rows: 356,454. Symbol windows: 2,016; eligible: 0; strict candidates: 0; executable historical trades: 0.

Price-only frozen formations: 30; these never enter the trade denominator.

| C02 reason | Symbol windows vetoed |
|---|---:|
| DEPTH_MISSING | 2,016 |
| EVENT_CLEARANCE_MISSING_OR_FUTURE | 2,016 |
| METADATA_MISSING | 2,016 |
| OPEN_INTEREST_MISSING | 2,016 |
| SPREAD_WARMUP_LT_60_VALID_SAMPLES | 2,016 |
| TICKER_24H_MISSING | 2,016 |

| Policy | Strict candidates | Assessment |
|---|---:|---|
| B1 | 0 | INSUFFICIENT_EVIDENCE |
| R1 | 0 | INSUFFICIENT_EVIDENCE |
| T1 | 0 | INSUFFICIENT_EVIDENCE |

R0: **INSUFFICIENT_EVIDENCE**. Actual price patterns and veto distribution are observable; complete historical liquidity/cohort and cost feasibility are not established.

R1: **NOT_TESTABLE**. No authentic strictly eligible event/control population with declared horizons and complete mandatory evidence is certified.

R2: **NOT_TESTABLE**. E0 retains no-execution truth; E1/E2 reuse C04 costs, approval/entry delay, partial fills, exits and portfolio constraints as explicit bar models.

## market case

```json
{
  "eligible_trade": false,
  "frozen_levels": [
    {
      "available_at": "2024-10-01T02:10:00Z",
      "event_time": "2024-10-01T02:09:59.999000Z",
      "fidelity": "BAR_DERIVED_APPROX",
      "instrument_id": "BINANCE_USDM:PERPETUAL:BTCUSDT:SETTLE:USDT",
      "invalidated": false,
      "invalidation_policy": "FROZEN_SETUP_ANCHOR;TERMINAL_WITH_SETUP",
      "kind": "PULLBACK_EXTREME",
      "level_id": "52198384b3e4b603c0c3225d90720f9f380b49b379dec484aee56955a7cfafd4",
      "price": "63460.00",
      "relevance": "BOTH",
      "source_ids": [
        "1727747700000",
        "1727748000000",
        "1727748300000"
      ],
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "version": "c03.levels.v1"
    }
  ],
  "frozen_snapshot": {
    "anchors": [
      {
        "anchor_id": "52198384b3e4b603c0c3225d90720f9f380b49b379dec484aee56955a7cfafd4",
        "available_at": "2024-10-01T02:10:00Z",
        "price": "63460.00",
        "source_event_id": "cc82217caa26f8f364522d365b052f2b73220d169916594e644ee71fab070807"
      }
    ],
    "available_at": "2024-10-01T02:10:00Z",
    "confirmed_at": null,
    "confirmed_event_id": null,
    "consumed_by": null,
    "context_at_formation": "4261460003e0e89f88773fcb9bf8b4c91bd1ce31549c127dd262710cf6b16994",
    "expires_at": "2024-10-01T02:40:00Z",
    "formed_at": "2024-10-01T02:09:59.999000Z",
    "formed_event_id": "1727748300000",
    "frozen_atr": "115.81841600914574",
    "invalidation_reason": null,
    "original_risk_parameters_hash": "df95a97e591c2d0b25d18ab691c4385ced02fa9eb1f235a8a7a144bc8cd02763",
    "schema_version": "setup_snapshot.v1.5",
    "setup_id": "9653aa15cda4297c9c700ee15fb98e0d2c642af06276fe29d53351b09d50d130",
    "side": "SHORT",
    "source_snapshot_id": "1a03ecf5725d3e968eaddfc36f5de825b89582541d7537475cbb4172e279f541",
    "state": "ARMED",
    "strategy_policy_hash": "df95a97e591c2d0b25d18ab691c4385ced02fa9eb1f235a8a7a144bc8cd02763",
    "strategy_version": "T1.reclaim.v1",
    "symbol": "BTCUSDT",
    "tolerance": "51.4397862706467925",
    "venue": "BINANCE_USDM_USDT_PERPETUAL"
  },
  "setup_id": "9653aa15cda4297c9c700ee15fb98e0d2c642af06276fe29d53351b09d50d130",
  "side": "SHORT",
  "strategy": "T1",
  "symbol": "BTCUSDT",
  "timeline": [
    {
      "as_of": "2024-10-01T02:10:00+00:00",
      "c02_reasons": [
        "METADATA_MISSING",
        "TICKER_24H_MISSING",
        "SPREAD_WARMUP_LT_60_VALID_SAMPLES",
        "DEPTH_MISSING",
        "OPEN_INTEREST_MISSING",
        "EVENT_CLEARANCE_MISSING_OR_FUTURE"
      ],
      "context": {
        "adx_1h": "44.15241691764491",
        "atr_15m": "205.75914508258717",
        "atr_5m": "115.81841600914574",
        "bias": "BEARISH",
        "classification": "TREND_DOWN",
        "context_id": "4261460003e0e89f88773fcb9bf8b4c91bd1ce31549c127dd262710cf6b16994",
        "readiness": "READY",
        "threshold_status": "UNVALIDATED"
      },
      "notes": [
        "PRICE_ONLY_FORMATION"
      ],
      "source_bar": {
        "available_at": "2024-10-01T02:10:00Z",
        "close": "63321.60",
        "event_time": "2024-10-01T02:09:59.999000Z",
        "fidelity": "VENUE_REPORTED",
        "high": "63380.20",
        "low": "63264.80",
        "open": "63336.90",
        "open_time": "2024-10-01T02:05:00Z",
        "source_record_id": "1727748300000"
      },
      "state": "ARMED"
    },
    {
      "as_of": "2024-10-01T02:15:00+00:00",
      "confirmation_bar": {
        "available_at": "2024-10-01T02:15:00Z",
        "close": "63214.80",
        "event_time": "2024-10-01T02:14:59.999000Z",
        "fidelity": "VENUE_REPORTED",
        "high": "63331.60",
        "low": "63183.20",
        "open": "63321.70",
        "open_time": "2024-10-01T02:10:00Z",
        "source_record_id": "1727748600000"
      },
      "last_bar_open": "2024-10-01T02:10:00+00:00",
      "notes": [
        "PRICE_ONLY_CONFIRMATION"
      ],
      "state": "CONFIRMED"
    }
  ]
}
```

## no trade case

```json
{
  "as_of": "2024-10-01T00:00:00+00:00",
  "c02_reasons": [
    "METADATA_MISSING",
    "TICKER_24H_MISSING",
    "SPREAD_WARMUP_LT_60_VALID_SAMPLES",
    "DEPTH_MISSING",
    "OPEN_INTEREST_MISSING",
    "EVENT_CLEARANCE_MISSING_OR_FUTURE"
  ],
  "context": {
    "adx_1h": "47.013646258042094",
    "atr_15m": "0.0019302906760408928",
    "atr_5m": "0.0014135871732956881",
    "bias": "BEARISH",
    "classification": "TREND_DOWN",
    "context_id": "e671742cb7c6ba84baa6243019ecc992b0710e9d18f4ed43878e0a06b97602c2",
    "readiness": "READY",
    "threshold_status": "UNVALIDATED"
  },
  "reasons": [
    "T1_CONTEXT_NOT_ALIGNED"
  ],
  "side": "LONG",
  "source_bar": {
    "available_at": "2024-10-01T00:00:00Z",
    "close": "0.37320",
    "event_time": "2024-09-30T23:59:59.999000Z",
    "fidelity": "VENUE_REPORTED",
    "high": "0.37360",
    "low": "0.37270",
    "open": "0.37280",
    "open_time": "2024-09-30T23:55:00Z",
    "source_record_id": "1727740500000"
  },
  "strategy": "T1",
  "symbol": "ADAUSDT"
}
```

## B1 friction sensitivity

(1.6*d - c)/(d+c) >= 1.5 requires symmetric cost c/d <= 0.04

All fee/friction scenarios are declared models. Source-backed price geometry is diagnostic; no fill, return or profitability is certified.

## Remaining evidence

- Contemporaneous instrument metadata/filters, venue ticker, validated OI measurement/units, complete fresh depth and verified event clearance for the same instrument and cutoff.
- Strict spread observations retain raw event-time cadence; C05 periodic endpoints are research diagnostics and do not change C02.
- Date-matched historical funding/fees and higher-frequency observed execution or defensible calibrated fill evidence.
- Representative historical selector/cohorts, independent later-window R1 controls/horizons and R2 uncertainty with purged overlapping outcomes.

Owner supplies original G feeds and H artifacts for a bounded matched historical interval; independently review strict admissions and R0 friction feasibility before R1/R2 qualification.

Full chronology, source IDs/hashes, original-feed evidence checks, sensitivity rows, E0/E1/E2 outcomes and uncertainty are in the accompanying JSON packet.
