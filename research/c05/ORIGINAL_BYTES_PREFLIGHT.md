# C05-D — Original-byte Tardis-format SOLUSDT quotes preflight

**Date:** 2026-10-25. **Verdict:** `SAMPLE_ONLY / QUOTES_SCHEMA_COMPATIBLE`. **Full P3 gate:** `INSUFFICIENT_EVIDENCE`; no strategy or executable trading qualification.

## Original-file provenance and integrity

- Owner uploaded `binance-futures_quotes_2024-10-01_SOLUSDT.csv.gz` for offline inspection. Filename, identifiers, data layout and one-day timestamp coverage match the documented Tardis `binance-futures/quotes` format. **Source HTTP headers, original vendor response, contractual redistribution rights and signed origin are not independently available**; do not claim authoritative source authentication.
- Exact uploaded compressed bytes: **14,010,263**; SHA-256: `ce31562cbfa20312aeda0246caf2d83754ce90835ce7579aeca40988b50f68cc`.
- Decompressed CSV bytes: **85,563,260**; SHA-256: `67886a232c556c23b86934f534b807715e298c1a449ef31b31b740904e7d81c6`. gzip CRC/decompression completed without error. Raw CSV/gzip remains **outside Git**.
- Exact header: `exchange,symbol,timestamp,local_timestamp,ask_amount,ask_price,bid_price,bid_amount`. **1,064,711** parsed records, all `binance-futures`/`SOLUSDT`, zero malformed or nonpositive numeric values, zero crossed/locked quotes.
- Per Tardis documentation, both timestamps are **epoch microseconds**: `timestamp` is exchange event time; `local_timestamp` is provider arrival time. Downloadable CSV is ordered/partitioned by `local_timestamp` and omits connection-disconnect events. No regression or same-value consecutive timestamp found in either observed sequence.

## Coverage and as-of quote diagnostics

| Check | Measured result |
|---|---|
| Exchange event timestamps | 2024-10-01 00:00:00.284000 – 23:59:59.864000 UTC |
| Provider arrival timestamps | 2024-10-01 00:00:00.996902 – 23:59:59.867043 UTC |
| UTC minutes with at least one observed quote | **1,440/1,440**; none empty |
| Longest observed provider-arrival gap | **3.681552 seconds**; this does not prove complete feed continuity |
| Provider-arrival minus exchange-event delay | median **2.966 ms**, p95 **4.333 ms**, p99 **7.920 ms**, max **984.651 ms**; not order latency |
| Event-count-weighted quoted spread | median **0.00065448%**, p95 **0.00069516%**, p99 **0.00348540%**, maximum **0.32405014%** |
| Transient quotes wider than 0.10% | **17 quote events**; must not be hidden by a daily average |
| Last-record-of-minute spread | median **0.00065032%**, maximum **0.01871575%** |
| Rolling 60 populated one-minute spreads | **1,381/1,381** windows have median < 0.10%; maximum rolling median **0.00069487%** |
| Last minute-record age at following minute boundary | median **50.663 ms**, p99 **615.437 ms**, max **889.313 ms** |

Method: stream gzip/CSV to EOF; parse UTC epoch microseconds; verify exact 8-column header and positive numeric values; count quote/order consistency, timestamp ordering and *collector-time* minute buckets. For each bucket sample **the last observed quote in that minute** and form rolling median spreads over 60 consecutive samples. Quoted spreads are `100*(ask-bid)/((ask+bid)/2)` **in percent**. Values do not imply time-weighted spread, complete L2 reconstruction, guaranteed source continuity or trade fill quality.

## Requirement-specific qualification

| P3 required evidence | Assessment from this file |
|---|---|
| Best bid/ask format, unit of timestamp, as-of intraday spread observations | **SAMPLE-COMPATIBLE**, SOLUSDT/one day only |
| 60 consecutive one-minute observed quotes with low median spread | **SAMPLE OBSERVED**, not a qualified dynamic/continuous historical universe |
| Feed disconnect/gap semantics and exchange sequence truth | **UNVERIFIED**; vendor CSV omits disconnect markers |
| Point-in-time instrument status, tick/lot filters, listing history | **MISSING** |
| Executable side-aware depth across 0.20% | **MISSING**; quotes show best level only, displayed size units/filter semantics require independent confirmation |
| Historical OI + conversion into USDT notional | **MISSING** |
| Original funding observations | **MISSING** |
| Verified point-in-time news/event clearance | **MISSING** |
| Fees, IOC fills, partials, slippage, stop outcomes or 12h policy economics | **MISSING/NOT TESTABLE** |

## Decision and next step

**SAMPLE_ONLY** resolves the former zero-original-byte barrier for the **quotes** source, not C04 strict policy replay. Keep T1/R1/B1 `RESEARCH_ONLY`, P3 `INSUFFICIENT_EVIDENCE`, full P4 unqualified, C07/demo/live blocked and whole-project full-gate accounting **45% credited / 55% unqualified**. A one-day BBO file does not establish enough inputs, conditions or independent outcomes to claim edge.

Next smallest compatible evidence: owner-authorized original first-of-month Tardis `derivative_ticker` (OI/funding fields as actually present) and `book_snapshot_25` (deeper book levels) **for the same day and symbol**, each checked for checksum, schema, coverage, unit conversion and terms, without committing raw data. If those work, decide on an authorized continuous representative research dataset or bounded prospective collector, including metadata, verified events, cost/fill assumptions, retention/storage/horizon; no automatic collector or purchases.

Relevant vendor schema/coverage docs: https://docs.tardis.dev/downloadable-csv-files/data-types , https://docs.tardis.dev/downloadable-csv-files/api , https://docs.tardis.dev/historical-data-details/binance-futures . No additional Binance REST calls or source downloads performed during this inspection.
