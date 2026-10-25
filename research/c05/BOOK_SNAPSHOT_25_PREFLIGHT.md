# C05-E — Owner-reported SOLUSDT top-25 historical order-book sample preflight

**Date:** 2026-10-25. **Evidence source:** owner's pasted local OpenBot Codex-agent summary; original 94.9 MB gzip and detailed Windows Markdown file **were not available to the lead for independent hash/reparse inspection**. Treat numerical statistics as reported, not lead-reproduced.

**Reported artifact:** `C:\Users\User\Downloads\binance-futures_book_snapshot_25_2024-10-01_SOLUSDT.csv.gz`. Report at `C:\Users\User\AstraBot\research\c05\C05_E_SAMPLE_VALIDATION_SOLUSDT_2024-10-01.md` (Windows-local only; not part of this PR).

**Verdict:** `OWNER_REPORTED_SAMPLE_COMPATIBLE / FULL_P3_INSUFFICIENT_EVIDENCE`; **PASS WITH DEFERRED NONBLOCKERS** for sample schema/readability only, pending direct lead review of full local report/original bytes.

## Integrity, schema and coverage (owner-reported)

| Diagnostic | Result |
|---|---|
| Exact matching source file | One matched in `C:\Users\User\Downloads`; no re-download |
| gzip size | **94,944,824 bytes** (90.55 MiB) |
| gzip SHA-256 | `19655523821b384f741715a2d4bf5db2fe1f825fddbed66ecaf9ef1796a6e3ba` |
| gzip/CSV full-stream decode | **PASS** reported using Python 3.12.10 |
| CSV rows / columns | **1,522,898 / 104**; all `binance-futures`/`SOLUSDT` |
| Timestamp interpretation | exchange `timestamp` and arrival `local_timestamp` as epoch **microseconds**; no reordering |
| Exchange time coverage | **2024-10-01 00:00:00.284** to **23:59:59.966 UTC**; all events on designated day |
| Timestamp regressions / adjacent duplicates | **0 / 0**, per agent |
| Arrival minus event time | approximate median **2.953 ms**, max **984.651 ms** (not exchange order latency) |
| Levels | 25 bids and 25 asks per book; no empty/partial levels, crossed/locked books, invalid values or book ordering errors reported |
| Snapshot frequency | mean **17.6262/s**; event-time interval approximate median/p95 **52/104 ms** |
| Inter-update gaps | **8** event-time and **9** provider-arrival gaps >1s; largest **3.621s** and **2.932s**, respectively |
| Data rights/HTTP chain | **not independently verified**; keep original raw gzip outside Git |

## Reported top-25 depth within +/-0.20% of mid

Definition: with `mid=(best_ask+best_bid)/2`, include bid levels with `bid_price >= 0.998*mid` and ask levels with `ask_price <= 1.002*mid`. These statistics are over **all 1,522,898 snapshots**, not time-weighted or independent fills.

| Side | Mean summed raw amount | Approx median raw | Approx p95 raw | Mean sum(price × amount), **unit unverified** |
|---|---:|---:|---:|---:|
| Bid | 1,121.08 | 909 | 2,384 | 171,210 |
| Ask | 1,213.58 | 1,016 | 2,678 | 185,674 |

**Do not label** raw amounts as validated SOL quantities or the price-weighted values as certified USDⓈ notionals until instrument amount/contract multiplier is independently verified. Reported size in the reconstructed visible book is **not proof of queue position, liquidity available at submission, executable depth for a particular IOC, or realized fills**. Repeated snapshots are highly dependent and cannot be interpreted as ~1.5 million independent liquidity tests.

Tardis documents `book_snapshot_25` as reconstructed from L2 data whenever tracked top-25 book levels change; timestamps are microseconds and full rows interleave 25 ask price/amount plus bid price/amount pairs after four ID/time columns. **Crossed order-book levels are deliberately removed by Tardis reconstruction**; an absence of crossed books in this CSV is not independent evidence that the original venue feed contained none. Vendor reference: https://docs.tardis.dev/downloadable-csv-files/data-types .

## AstraBot gate assessment

This adds **one-day L2 snapshot sample availability/schema compatibility** alongside the already inspected one-day quotes and derivative-ticker files (same `binance-futures`, `SOLUSDT`, 2024-10-01). It does **not** yet establish a causal multi-feed join at each candidate decision, validated OI and depth quantity units/contract mapping, historical effective status/filters, completeness/correction history, actual funding settlements, news/event clearance, account fees, or real fill/latency/stop behavior.

`src/astrabot/universe/eligibility.py` still requires valid depth, OHLCV, 60 spread samples and their readiness, OI notional with `unit_validated`, point-in-time metadata, turnover and event clearance. No schema adapters or research-pipeline code were changed by this documentation entry.

**Official phase-gate credit stays 45% / 55% unqualified**; P3/C05=`INSUFFICIENT_EVIDENCE`, T1/R1/B1=`RESEARCH_ONLY`; C07/demo/live blocked. The original v1.5 **30-day / 50 intended paper-signal** requirement is a **downstream shadow/demo operational-governance gate**, distinct from today’s one-day P3 market-data preflight, and does not itself establish statistical edge.

**Next cheapest evidence gate:** verify source ownership/rights and **SOLUSDT USDⓈ-M contract-base quantity units plus historical exchange filters** against authoritative versioned Binance documentation and contemporaneous records; independently inspect the small local OpenBot report when attached. Then, using only an explicitly authorized dataset, perform a **fixed one-day, timestamp-causal quote/OI/top-25 alignment diagnostic** with summary metrics and fail-closed missing data (no policy GO, live execution or broad download). Before representative multi-day economics, the owner must authorize legal access, retention, horizon, storage/cost and point-in-time event-feed plan. No new Codex network probes.
