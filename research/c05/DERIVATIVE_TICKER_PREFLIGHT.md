# C05-D — Owner-provided SOLUSDT derivative-ticker original-byte preflight

**Date:** 2026-10-25. **Verdict:** `SAMPLE_ONLY / DERIVATIVE_TICKER_SCHEMA_COMPATIBLE`. P3 economic gate: `INSUFFICIENT_EVIDENCE`; no strategy qualification.

## Original bytes and format

- Uploaded `binance-futures_derivative_ticker_2024-10-01_SOLUSDT.csv.gz` (not committed). Compressed **1,833,346 bytes**, SHA-256 `8c7301a2b3aa22de1430af3844afac9bb05de061dfc28a65a7bdc4920c1357d7`; full successful gzip/CRC decode **14,645,384 CSV bytes**, SHA-256 `c296a0bb86d80785b995b0a51c56b9dcb3fb2f91c0d547f735f92349279a6277`.
- 11 fields: `exchange,symbol,timestamp,local_timestamp,funding_timestamp,funding_rate,predicted_funding_rate,open_interest,last_price,index_price,mark_price`; match documented Tardis `derivative_ticker` layout. **119,927** parsed rows, all `binance-futures` / `SOLUSDT`. No malformed numeric rows, duplicate full rows, nonpositive populated prices/OI or non-finite values. No independent vendor HTTP provenance or licence/redistribution certification.
- Both timestamps are **UTC epoch microseconds**; `timestamp` exchange event time (may have ties), `local_timestamp` arrival/CSV partition time. Event timestamps 2024-10-01 00:00:00–23:59:59 UTC; collector timestamps 00:00:00.035184–23:59:59.027523 UTC. No regressions; **16,925 exchange-time ties** and **zero collector-time ties** (preserve row order). Collector/event lag median **35.039 ms**, p95 **617.398 ms**, p99 **917.913 ms**, max **1,326.331 ms**, not order latency.
- Every collector-UTC minute has records: **1,440/1,440**, 61–103 rows per minute. Maximum recorded arrival gap **5.023032 seconds**. Tardis CSV omits disconnect messages, so populated minutes **do not prove continuous exchange-feed connectivity**.

## Derivative fields

| Field | Measured observation | Gate interpretation |
|---|---|---|
| `open_interest` | **119,913/119,927** non-null (first 14 null); first known 00:00:06.904960 UTC. Raw min **5,549,396**, median **5,798,650**, max **5,969,151**. **9,735** actual value changes, 1,429 minutes with changes; median change gap **8.81073 sec**, max **176.306783 sec** | **Historical numeric evidence**, but source units/multiplier and USDT notional NOT validated; repeated field does not equal a fresh OI observation. Never set `OpenInterestObservation.unit_validated=True` without external basis |
| `mark_price` and `index_price` | Both present in **119,927** rows | Indicative market observations; not fills |
| `last_price` | Present in **119,920** rows | Historical last-traded-price field; not independently verified trade tape |
| `funding_timestamp` | Next event transitions around 00:00:01, 08:00:01, 16:00:01 UTC; refers to 00:00, 08:00, 16:00 Oct 1 and 00:00 Oct 2 | Future scheduled funding event, not proof of settlement |
| `funding_rate` | **0.0001** (0.01%) in all 119,927 rows | Published next-event rate, not verified final settled funding payment |
| `predicted_funding_rate` | Empty in all rows | Unknown; not 0 |

Tardis documents that Binance USDT-futures open interest has been collected via its REST endpoint since 2020-05-13; the file does **not** establish the true source polling sequence or convert the OI value into USDT. Binance's public REST `openInterest` response documents the raw field, but the relevant historical contract-size/base unit needs an explicit source-backed confirmation before calculating a validated notional.

## Paired original quotes

The separate owner-uploaded original `quotes` file (validated in [the quote preflight](ORIGINAL_BYTES_PREFLIGHT.md)) is from the same `binance-futures/SOLUSDT/2024-10-01`. **All 1,440 collector-UTC minutes** contain both derivative rows and quotes. At minute end, last-observed records from both streams exist, including non-null OI. Minute overlap is **not** proof of same-instant observations; any causal join must use each row's **actual arrival timestamp <= decision timestamp** and evaluate freshness. There is no demonstrated full dynamic universe, executable market depth or fundable policy.

## P3 qualification

**SAMPLE-COMPATIBLE:** one-day original derivative schema; observed historical OI *values*, mark/index, published next-funding fields; independent quote/OI presence in all minute buckets.

**STILL NOT QUALIFIED:** OI base/contract units and validated USDT notional, effective venue filters/listing status, top-25 executable side-aware depth and impact, actual funding settlement records, complete point-in-time events, account fee tiers, queue/fill/slippage/stop outcomes, a continuous representative out-of-sample period. Do **not** claim positive expectancy or that one sampled day passes strict C02; keep T1/R1/B1 `RESEARCH_ONLY`, C05 `INSUFFICIENT_EVIDENCE`, full P4/C07/live blocked, **45% full-phase weight credited/55% unqualified**.

**Next gate:** owner-supplied, rights-checked `book_snapshot_25` for SOLUSDT 2024-10-01 and explicit OI-unit/multiplier evidence. Thereafter choose a lawful continuous representative dataset or owner-approved prospective read-only capture, including retention/storage, rather than repeating cloud network probes. No credentials, deployment or purchases.

References: https://docs.tardis.dev/downloadable-csv-files/data-types ; https://docs.tardis.dev/downloadable-csv-files ; https://docs.tardis.dev/historical-data-details/binance-futures ; https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest .
