# C05-H — Historical metadata and quantity evidence

Date: 2026-10-25 (client timezone). Base: `faee10a1ae114d3402154af3871086c8e2888853` (merged C05-G PR #24). Branch: `codex/c05h-evidence-validation`.

**NEXT_GATE:** independent engineering-lead review, then obtain reviewed, date-effective primary metadata and provider unit/measurement evidence for the already-authorized SOLUSDT day. P3 remains `INSUFFICIENT_EVIDENCE`, every replay remains `NOT_READY_FAIL_CLOSED`, and phase credit remains 45% / 55% unqualified.

## Evidence inspected and checks closed

Inspected repository contracts (`InstrumentMetadata`, `DepthSnapshot`, `OpenInterestObservation`, Decimal/UTC `Contract`), C02 freshness/conversion code, C05-G source readers/replay/CLI/tests, the committed C05-G JSON/Markdown report and earlier quote, derivative and book preflights. The original Windows market-data gzip files are unavailable here and **were not inspected or replayed**. Earlier original-byte results remain prior-session/owner-reported evidence. No Binance/Tardis requests, repeated blocked probes, collection, procurement or current exchange-metadata lookup occurred.

| Check | Historical SOLUSDT 2024-10-01 | Synthetic regression evidence |
|---|---|---|
| Instrument identity, lifecycle, filters, contract size | UNVERIFIED: no contemporary authoritative metadata artifact | VERIFIED |
| OI quantity unit and multiplier | UNVERIFIED: raw values and URLs in reports do not establish mapping | VERIFIED, base and contract quantities |
| OI measurement time | UNVERIFIED: ticker timestamps/repeated values/value changes do not identify an OI measurement | VERIFIED only with explicit field-specific timing evidence |
| OI USDT conversion | UNVERIFIED: unit, measurement and same-time mark semantics missing | VERIFIED, exact same-row indicative mark valuation |
| Book amount unit and multiplier | UNVERIFIED: reconstructed amounts do not establish base size | VERIFIED, base and contract quantities |
| Visible top-25 USDT conversion within 0.20% mid | UNVERIFIED: historical mapping missing | VERIFIED only with complete valid book and supported mapping |

The inspected C05-G JSON report has SHA-256 `1ffcc2b31c20250543915d402f5a8578d85ac021a0a8a17ea0a7e4cc1706c996`; this is a report checksum, not revalidation of its original input files.

**No real historical evidence check was closed.** The empty historical manifest is deliberate, not an implicit approval. [Machine-readable assessment](C05_H_EVIDENCE_VALIDATION.json) separates the historical missing-evidence result from the invented synthetic example. No authentic-panel replay is represented by that file. The invented contract case calculates OI as `1000 × 0.1 × 100.5 = 10050` USDT and visible bid/ask depth as `789.1040 / 590.6860` USDT; these verify arithmetic only.

## Small versioned contract

`c05h.historical-evidence.v1` has a strict `synthetic` flag and a list of evidence references. Each reference carries a unique ID, one claim kind (`metadata`, `oi_unit`, `oi_time`, `book_unit`), local artifact path and SHA-256, RFC 6901 pointer, publisher URI and precise source locator, authority, historical `available_at`, separate retrieval `captured_at`, finite half-open effective interval, exchange, symbol and adapter version. Feed claims additionally bind the exact gzip SHA-256. Paths stay inside the manifest directory; missing artifacts, digest mismatches and unsupported extracts remain unverified. Invalid manifests abort without producing a report.

The artifact pointer selects a structured source extract. Metadata uses the existing `InstrumentMetadata` schema, including consistent PRICE_FILTER / LOT_SIZE / MARKET_LOT_SIZE / MIN_NOTIONAL records, lifecycle/status, USDT quote/settlement, tick/step/minima/maxima and explicit contract size. Quantity extracts name `BASE_ASSET` or `CONTRACTS`, the base asset and `USDT_PER_BASE_ASSET` price unit; contracts require an explicit positive base-per-contract multiplier matching historical metadata. Only linear USDT perpetuals are supported. Unknown/inverse/quanto mappings fail closed.

These are **reviewed evidence inputs**, not a publisher-authentication service. A source URI, digest or normalized assertion alone cannot establish external truth. Before adding non-synthetic records, the engineering lead must inspect the cited primary source and its archived supporting material, verify that normalization faithfully preserves each field, and substantiate the declared effective interval and historical availability. `captured_at` records retrieval and cannot substitute for proof of earlier availability. The validator checks the supplied artifact/claim consistency; it cannot prove legal rights, authenticity of an arbitrary file, or infer undocumented semantics from a URL. Current documentation or today's exchangeInfo must never be backdated as October 2024 evidence. No non-synthetic assertions are supplied or verified in this PR.

Overlapping known claims must agree; there is no last-record-wins rule. Future-known evidence is excluded from earlier decisions. Metadata must cover both the decision and selected source observations. Synthetic assertions are rejected in real-data mode. Unsupported/missing metadata blocks the dependent quantity mappings. Unit verification is independent of OI timing; no numeric resemblance, polling cadence or value change certifies measurement time.

The narrow timing mode requires source-backed `ROW_TIMESTAMP_IS_OI_MEASUREMENT` for `timestamp`. OI notional additionally requires `ROW_TIMESTAMP_IS_MARK_MEASUREMENT` and a populated positive same-row mark. If the actual provider carries OI or mark across unrelated ticker updates, this mode must remain unverified; the smallest next extension would be explicit per-field measurement timestamps supported by original records, not a guessed refresh interval.

Conversion is exact Decimal arithmetic: base quantity = raw amount for BASE_ASSET, or raw amount × base-per-contract for CONTRACTS; notional = base quantity × supported USDT/base price. Book sides use each level's own price and the existing inclusive 0.20%-from-mid bounds. This is **visible reconstructed top-25 notional**, potentially a lower bound for the full price band, never executable liquidity, queue position, impact or a fill guarantee. Incomplete books can establish their unit but cannot close the notional check. OI notional is a calculated mark valuation, not a reported venue notional. Raw OI and raw depth totals remain separately available.

## Exact module changes and reuse

- New `src/astrabot/data/historical_evidence.py`: strict manifest/reference and quantity/timing contracts, pinned local artifact loader, independent check statuses/reasons/IDs, historical metadata consistency and deterministic conversions. Reuses `Contract`, UTC/Decimal types, `InstrumentMetadata`, existing source checksum validation and stable configuration hashing.
- `src/astrabot/data/historical_replay.py`: optional evidence/synthetic inputs; per-snapshot validation; only supported quantities are normalized to base using existing observation models. Adds raw OI preservation. Removes only individually verified evidence blockers, retaining unrelated readiness/economic blockers and fixed overall fail-closed status. Does not call production eligibility or modify its rules.
- `scripts/c05_historical_research.py`: `--evidence-manifest`; evidence manifest hash in configuration; JSON report version `c05h.historical-research-report.v2`; JSON and Markdown check reasons, evidence IDs, measurement time and conversion outputs. Existing C05_G filenames and CLI without evidence remain usable.
- `tests/fixtures/c05h/{manifest,synthetic_assertions}.json`: tiny pinned invented assertions bound to existing C05-G gzip fixtures. The intentionally invented 0.1 SOL/contract multiplier is **not** a statement about Binance SOLUSDT.
- `tests/test_c05h_historical_evidence.py`: positive and negative evidence regression cases. Historical manifest and JSON/Markdown assessment under `research/c05`; focused contract/roadmap/journal updates.

No production C02, C06, strategy, risk, credentials or Binance execution files change. `c05g.periodic-spread.v1` remains research-only with unchanged policy/configuration. No dependency added. A small adapter was sufficient; no evidence framework or new replay engine was adopted.

## Reproduction and validation

Use Python 3.12 and the repository's pinned `requirements-test.txt`. The tests block outbound market-data networking through existing suite safeguards.

```bash
python -m pytest -q tests/test_c05h_historical_evidence.py tests/test_c05g_historical_pipeline.py
python -m pytest -q
python -m compileall -q src/astrabot tests scripts
python -m pip check
python scripts/c03_research.py --check --summary
python scripts/c03_research.py --c02-panel --check
python scripts/c04_replay.py --check
python scripts/c05_historical_research.py --data-root tests/fixtures/c05g --source-manifest tests/fixtures/c05g/manifest.json --symbol SOLUSDT --date 2024-10-01 --decision-time 2024-10-01T01:00:00Z --evidence-manifest tests/fixtures/c05h/manifest.json --output-dir work/c05h-verified
```

Focused checks: **63 passed** (46 C05-H and 17 existing C05-G). Full regression: **307 passed in 67.82s**; compilation, dependency integrity and existing C03/C04 replay checks passed. Exact commands are recorded in the delivery journal. Byte-identical repeated JSON reports are asserted. Regressions cover base/contracts, exact price weighting, unit-vs-time independence, missing mark, incomplete book, missing/contradictory/expired/future/wrong-symbol/wrong-hash evidence, multiplier/filter inconsistency, NaN, wrong authority, path escape, unsupported schema versions and synthetic/real isolation. Future evidence cannot change earlier check outcomes.

## Remaining blockers and cheapest next P3 gate

1. Have the lead review this bounded engineering change and the evidence-input trust boundary. No phase/economic promotion follows from passing synthetic tests.
2. Supply rights-cleared, archived primary USDⓈ-M SOLUSDT metadata effective on 2024-10-01, plus authoritative provider normalization/unit and **field-specific measurement-time** documentation/records for the exact OI/book datasets. Review these before populating the historical manifest. The stored C05-G report alone and current exchangeInfo cannot close these checks.
3. When those inputs and the already-authorized original gzip files are available locally, run the existing fixed-cutoff replay with the evidence manifest. Close only individually supported checks. Carried OI may require a bounded explicit measurement-timestamp extension; defer it until evidence exists.

Funding settlement, source correction/completeness, historical events, broader point-in-time universe, fee/fill/slippage evidence and representative untouched full-policy outcomes remain outside this deliverable. P3 economic GO, production sampler promotion, further C06, C07/demo/live, purchases and persistent collection are not authorized here.
