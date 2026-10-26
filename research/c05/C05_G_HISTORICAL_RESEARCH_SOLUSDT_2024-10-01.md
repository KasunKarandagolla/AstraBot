# C05-G historical research replay - SOLUSDT 2024-10-01

**Source integrity:** SHA-256 verified original feeds; configuration `e55de586e01f498a3be8f949f45af789107cf3c071fd41444e116d63b7a08f02`.

## Feed validation

| Dataset | Rows | SHA-256 | Duplicates | Event ties | Event regressions | Arrival regressions |
|---|---:|---|---:|---:|---:|---:|
| quotes | 1,064,711 | `ce31562cbfa20312aeda0246caf2d83754ce90835ce7579aeca40988b50f68cc` | 0 | 0 | 0 | 0 |
| derivative_ticker | 119,927 | `8c7301a2b3aa22de1430af3844afac9bb05de061dfc28a65a7bdc4920c1357d7` | 0 | 16925 | 0 | 0 |
| book_snapshot_25 | 1,522,898 | `19655523821b384f741715a2d4bf5db2fe1f825fddbed66ecaf9ef1796a6e3ba` | 0 | 0 | 0 | 0 |

## Causal decision snapshots

`event_time` and provider `available_at` are preserved. `available_at` is the source's `local_timestamp` arrival proxy. The minute sampler uses separate endpoint timestamps and does not change the C02 production scanner.

| Decision UTC | Quote age | Book age | Spread slots | Median spread | Raw event 60s intervals | Raw bid / ask amount within 0.20% | Late derivative rows excluded | C02 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 2024-10-01T00:30:00.000000Z | 0.199s | 0.04s | 30/60 | N/A | 1/59 | 778 / 1079 (raw units) | 1 | `NOT_READY_FAIL_CLOSED` |
| 2024-10-01T01:05:00.000000Z | 0.025s | 0.025s | 60/60 | 0.0000065459 | 2/59 | 751 / 1682 (raw units) | 1 | `NOT_READY_FAIL_CLOSED` |
| 2024-10-01T03:05:00.000000Z | 0.081s | 0.029s | 60/60 | 0.0000065118 | 0/59 | 1115 / 1135 (raw units) | 0 | `NOT_READY_FAIL_CLOSED` |
| 2024-10-01T08:05:00.000000Z | 0.011s | 0.011s | 60/60 | 0.0000063897 | 0/59 | 1532 / 1108 (raw units) | 1 | `NOT_READY_FAIL_CLOSED` |
| 2024-10-01T12:05:00.000000Z | 0.665s | 0.192s | 60/60 | 0.0000063810 | 0/59 | 1029 / 818 (raw units) | 0 | `NOT_READY_FAIL_CLOSED` |
| 2024-10-01T16:05:00.000000Z | 0.032s | 0.032s | 60/60 | 0.0000066951 | 1/59 | 565 / 435 (raw units) | 1 | `NOT_READY_FAIL_CLOSED` |
| 2024-10-01T20:05:00.000000Z | 0.023s | 0.023s | 60/60 | 0.0000068135 | 1/59 | 7759 / 1836 (raw units) | 1 | `NOT_READY_FAIL_CLOSED` |
| 2024-10-01T23:59:00.000000Z | 0.265s | 0.042s | 60/60 | 0.0000068938 | 0/59 | 1042 / 1131 (raw units) | 2 | `NOT_READY_FAIL_CLOSED` |

The spread statistic is a research-only periodic sample on UTC minute boundaries using the latest quote in each `(endpoint - 60s, endpoint]` interval, with both source timestamps no later than that endpoint and a strict maximum age below 60 seconds. The median threshold remains 0.10%; 60 distinct occupied endpoints are required. The adjacent raw event-time count is reported separately.

Raw L2 amounts are not certified quantity or USDT notional. OI remains raw with unverified units and measurement-refresh time. Reported funding fields are not classified as settled funding. No historical instrument metadata, event clearance, candles, fee schedule, fills, or complete C02 eligibility is inferred.

## Unresolved blockers

- `CANDLE_CONTEXT_MISSING`
- `DEPTH_AMOUNT_UNIT_UNVERIFIED`
- `EVENT_CLEARANCE_UNVERIFIED`
- `EXECUTABLE_FILL_AND_FEE_EVIDENCE_MISSING`
- `FEED_COMPLETENESS_AND_CORRECTION_HISTORY_UNVERIFIED`
- `FUNDING_SETTLEMENT_STATUS_UNVERIFIED`
- `FUNDING_TIMESTAMP_SEMANTICS_UNVERIFIED`
- `HISTORICAL_INSTRUMENT_METADATA_MISSING`
- `OPEN_INTEREST_REFRESH_TIME_UNVERIFIED`
- `OPEN_INTEREST_UNIT_UNVERIFIED`
- `PERIODIC_SPREAD_SAMPLER_IS_RESEARCH_OPT_IN_ONLY`
- `SPREAD_WARMUP_LT_60_PERIODIC_SLOTS`

C02 eligibility and economic qualification remain fail-closed. This replay establishes data normalization and causal timing only; it does not establish profitability.
