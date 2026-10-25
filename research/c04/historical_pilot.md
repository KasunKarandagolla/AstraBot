# C04 authentic USDⓈ-M historical pilot

**Source manifest SHA256:** `6a34aae6b37ec9b48aa166dda52cd578a86776ef8b36be05aaaa5bf42f51058a`
**Smoke manifest SHA256:** `84cc3f8f584e06982ecb644673ee88471939a11d80c0097bcf5957e34d4d9087`
**C04 run:** `812138b819227821eaa9a2f48f53665c2a647c40dbc5be92a09528c10d548a4f`
**Decision ledger SHA256:** `4369946850f06afbcc1d72d7117b2ebd19797d00ad2a92cf955b8448c32390b7`
**Funnel ledger SHA256:** `790d79355055b772ced456b7181d0eb5e375e531ab12454f65dc87cc25be5dc0`

This is an OHLCV-only historical research diagnostic. It makes no profitability or economic GO claim.

## Acquisition and coverage

- Public source: `https://data.binance.vision/`; USDⓈ-M, USDT-settled kline archives only.
- Ingestion smoke (`2025-10-23`, 1m): 7 daily archives, 414,954 bytes and 10,080 rows; HTTP statuses `{'200': 7}`, ZIP/CSV checks passed for 7, duplicates 0, out-of-order opens 0, and gaps 0. Each member, exact schema, full-day timestamps and checksum is recorded in the smoke manifest.
- Fixed declared cohort: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, ADAUSDT, DOGEUSDT. This cohort is not evidence of a point-in-time dynamic universe.
- Monthly archives: 112 files, 15,417,887 compressed bytes, 356,454 normalized rows.
- Archive HTTP statuses: `{'200': 112}`; ZIP/CSV checks passed for 112 archives.
- The bounded pilot uses one direct monthly archive for each of 7 symbols × 4 intervals × 4 months (112 files). It avoids interval resampling and full 1m history; 1m is limited to the one-day ingestion smoke test.

Smoke archive checksums and exact member/row totals:

| Archive | HTTP | Bytes | SHA256 | Member | Rows | Quality |
|---|---:|---:|---|---|---:|---|
| ADAUSDT-1m-2025-10-23.zip | 200 | 51,540 | `514df192a0b340c759ebfad5bd776ec396d7fe1a501396307032f1cf2f6690eb` | ADAUSDT-1m-2025-10-23.csv | 1,440 | PASS |
| BNBUSDT-1m-2025-10-23.zip | 200 | 59,261 | `48f0f8cd1a4c2504c0fcdce29eeb6388f4bb110ce36e7762a3d21b8962251b21` | BNBUSDT-1m-2025-10-23.csv | 1,440 | PASS |
| BTCUSDT-1m-2025-10-23.zip | 200 | 62,579 | `41e5b20e94e21c87339dee9cafbab9442bcf846a655aa51978e47331190f5b57` | BTCUSDT-1m-2025-10-23.csv | 1,440 | PASS |
| DOGEUSDT-1m-2025-10-23.zip | 200 | 58,863 | `ebb7761d7db68ef027d85b712191ee5525c7adc38f5d647bb7da90c9a4580c06` | DOGEUSDT-1m-2025-10-23.csv | 1,440 | PASS |
| ETHUSDT-1m-2025-10-23.zip | 200 | 64,851 | `700e4a10a8e423979d07d7f86878dac0fc3b30be14c3c507e2cdf17554dbfcfd` | ETHUSDT-1m-2025-10-23.csv | 1,440 | PASS |
| SOLUSDT-1m-2025-10-23.zip | 200 | 60,051 | `c9d29d9e46267b6eea0d102743323c5a45393ac2af8442d1ddfff0f49aa0910e` | SOLUSDT-1m-2025-10-23.csv | 1,440 | PASS |
| XRPUSDT-1m-2025-10-23.zip | 200 | 57,809 | `86f36a20d489eedefdd870056318df8f7c2126552b9442ae0fb6e3edc4254d21` | XRPUSDT-1m-2025-10-23.csv | 1,440 | PASS |

- Raw archives remain outside Git under `ASTRABOT_DATA_ROOT`; committed manifests contain source URLs, member names, actual sizes, SHA256 values, schema and continuity findings.

| Interval | Archives | Rows | Compressed bytes | Coverage UTC | Duplicate opens | Missing intervals |
|---|---:|---:|---:|---|---:|---:|
| 5m | 28 | 247,968 | 10,426,537 | 2024-07-01T00:00:00.000Z – 2024-10-31T23:59:59.999Z | 0 | 0 |
| 15m | 28 | 82,656 | 3,716,571 | 2024-07-01T00:00:00.000Z – 2024-10-31T23:59:59.999Z | 0 | 0 |
| 1h | 28 | 20,664 | 998,704 | 2024-07-01T00:00:00.000Z – 2024-10-31T23:59:59.999Z | 0 | 0 |
| 4h | 28 | 5,166 | 276,075 | 2024-07-01T00:00:00.000Z – 2024-10-31T23:59:59.999Z | 0 | 0 |

Each monthly file had the expected row count, exact Binance 12-column kline schema, one expected CSV member, valid ZIP contents, and zero timestamp duplicates, regressions or gaps. Cross-month checks also found zero duplicates, ordering errors or missing intervals for every symbol/timeframe.

## Frozen windows and warm-up

| Window | UTC range | Role |
|---|---|---|
| Source-only warm-up | 2024-07-01 through 2024-08-31 | Provide history only; no strategy outcomes used |
| Development | 2024-09-01 through 2024-09-30 | Previously declared C04 development window |
| Validation | 2024-10-01 through 2024-10-14 | Previously declared validation window |
| Untouched evaluation | 2024-10-15 through 2024-10-31 | Held out; no strategy or cohort selection from its outcomes |

C02 requires 720 1h bars and 200 4h bars; C03 context requires 735 1h bars and 53 4h bars. The longest OHLCV-only threshold was reached by **2024-08-03T08:00:00+00:00 UTC** from the first July archive bar. At the development open, every symbol had 1,488 1h and 372 4h bars available. August alone contains 186 4h bars per symbol and cannot meet C02's 200-bar gate.

These counts establish source-history warm-up only. Missing point-in-time metadata and the other C02 evidence still prevent symbol eligibility.

## C04 causal diagnostics

- C04 scanned 1,464 UTC 1h availability snapshots across 7 symbols, using the existing C02 eligibility, C03 evaluator and C04 event replay. The window begins at `2024-09-01T01:00:00+00:00` and ends at `2024-11-01T00:00:00+00:00`.
- The first September hourly evaluation starts at 01:00 UTC, when the 00:00–00:59 candle is closed; the 00:00 availability carrying the final August close is excluded from strategy diagnostics.
- Local replay runtime was 1481.1 seconds with 30,240,305 bytes of peak traced Python allocation; this is an executor-specific measurement, not a capacity guarantee.
- C02/C03 snapshot history caps were 288×5m, 21×15m, 735×1h and 200×4h bars. Raw source coverage remains complete; the bounded tails meet the existing indicator and eligibility lookbacks.
- The 1h C04 cadence bounds runtime while retaining all source intervals in the as-of context. It can miss transient setup changes between hourly snapshots; this is not a full 15m or 5m setup/execution replay.
- STRICT_POLICY_REPLAY: **BLOCKED_BY_DATA**, 0 shortlist windows, 0 strict candidates. No mandatory gates were bypassed.
- Price/setup diagnostics: `{'NO_TRADE': 61488}`; context readiness: `{'READY': 61488}`.
- Latest strict eligibility NO_TRADE reasons/counts: `{'C02_UNIVERSE_NOT_READY': 61488, 'DEPTH_MISSING': 61495, 'EVENT_CLEARANCE_MISSING_OR_FUTURE': 61495, 'EXTREME_VOLATILITY_OR_LIQUIDITY_VETO': 2874, 'METADATA_MISSING': 61495, 'OPEN_INTEREST_MISSING': 61495, 'SPREAD_WARMUP_LT_60_VALID_SAMPLES': 61495, 'TICKER_24H_MISSING': 61495}`.
- C03 price/setup NO_TRADE reason counts: `{'C02_UNIVERSE_NOT_READY': 61488, 'DEPTH_MISSING': 61488, 'EVENT_CLEARANCE_MISSING_OR_FUTURE': 61488, 'EXTREME_VOLATILITY_OR_LIQUIDITY_VETO': 2874, 'METADATA_MISSING': 61488, 'OPEN_INTEREST_MISSING': 61488, 'SPREAD_WARMUP_LT_60_VALID_SAMPLES': 61488, 'TICKER_24H_MISSING': 61488}`. These are diagnostics only; no policy-qualified trade passed.

Causal closed-bar prices at the first availability snapshot in each frozen window (archive source bytes are pinned by the manifest):

| Window | As-of UTC | Symbol | Interval | Event close time | Close (USDT) | Available at | Source record ID |
|---|---|---|---|---|---:|---|---|
| development | 2024-09-01T00:15:00+00:00 | BTCUSDT | 15m | 2024-09-01T00:14:59.999000+00:00 | 59008.90 | 2024-09-01T00:15:00+00:00 | `1725148800000` |
| development | 2024-09-01T00:15:00+00:00 | BTCUSDT | 1h | 2024-08-31T23:59:59.999000+00:00 | 58941.90 | 2024-09-01T00:00:00+00:00 | `1725145200000` |
| development | 2024-09-01T00:15:00+00:00 | BTCUSDT | 4h | 2024-08-31T23:59:59.999000+00:00 | 58941.90 | 2024-09-01T00:00:00+00:00 | `1725134400000` |
| development | 2024-09-01T00:15:00+00:00 | BTCUSDT | 5m | 2024-09-01T00:14:59.999000+00:00 | 59008.90 | 2024-09-01T00:15:00+00:00 | `1725149400000` |
| development | 2024-09-01T00:15:00+00:00 | ETHUSDT | 15m | 2024-09-01T00:14:59.999000+00:00 | 2513.96 | 2024-09-01T00:15:00+00:00 | `1725148800000` |
| development | 2024-09-01T00:15:00+00:00 | ETHUSDT | 1h | 2024-08-31T23:59:59.999000+00:00 | 2511.91 | 2024-09-01T00:00:00+00:00 | `1725145200000` |
| development | 2024-09-01T00:15:00+00:00 | ETHUSDT | 4h | 2024-08-31T23:59:59.999000+00:00 | 2511.91 | 2024-09-01T00:00:00+00:00 | `1725134400000` |
| development | 2024-09-01T00:15:00+00:00 | ETHUSDT | 5m | 2024-09-01T00:14:59.999000+00:00 | 2513.96 | 2024-09-01T00:15:00+00:00 | `1725149400000` |
| development | 2024-09-01T00:15:00+00:00 | SOLUSDT | 15m | 2024-09-01T00:14:59.999000+00:00 | 135.4590 | 2024-09-01T00:15:00+00:00 | `1725148800000` |
| development | 2024-09-01T00:15:00+00:00 | SOLUSDT | 1h | 2024-08-31T23:59:59.999000+00:00 | 135.2660 | 2024-09-01T00:00:00+00:00 | `1725145200000` |
| development | 2024-09-01T00:15:00+00:00 | SOLUSDT | 4h | 2024-08-31T23:59:59.999000+00:00 | 135.2660 | 2024-09-01T00:00:00+00:00 | `1725134400000` |
| development | 2024-09-01T00:15:00+00:00 | SOLUSDT | 5m | 2024-09-01T00:14:59.999000+00:00 | 135.4590 | 2024-09-01T00:15:00+00:00 | `1725149400000` |
| untouched_evaluation | 2024-10-15T00:15:00+00:00 | BTCUSDT | 15m | 2024-10-15T00:14:59.999000+00:00 | 65938.50 | 2024-10-15T00:15:00+00:00 | `1728950400000` |
| untouched_evaluation | 2024-10-15T00:15:00+00:00 | BTCUSDT | 1h | 2024-10-14T23:59:59.999000+00:00 | 66064.90 | 2024-10-15T00:00:00+00:00 | `1728946800000` |
| untouched_evaluation | 2024-10-15T00:15:00+00:00 | BTCUSDT | 4h | 2024-10-14T23:59:59.999000+00:00 | 66064.90 | 2024-10-15T00:00:00+00:00 | `1728936000000` |
| untouched_evaluation | 2024-10-15T00:15:00+00:00 | BTCUSDT | 5m | 2024-10-15T00:14:59.999000+00:00 | 65938.50 | 2024-10-15T00:15:00+00:00 | `1728951000000` |
| untouched_evaluation | 2024-10-15T00:15:00+00:00 | ETHUSDT | 15m | 2024-10-15T00:14:59.999000+00:00 | 2624.77 | 2024-10-15T00:15:00+00:00 | `1728950400000` |
| untouched_evaluation | 2024-10-15T00:15:00+00:00 | ETHUSDT | 1h | 2024-10-14T23:59:59.999000+00:00 | 2628.88 | 2024-10-15T00:00:00+00:00 | `1728946800000` |
| untouched_evaluation | 2024-10-15T00:15:00+00:00 | ETHUSDT | 4h | 2024-10-14T23:59:59.999000+00:00 | 2628.88 | 2024-10-15T00:00:00+00:00 | `1728936000000` |
| untouched_evaluation | 2024-10-15T00:15:00+00:00 | ETHUSDT | 5m | 2024-10-15T00:14:59.999000+00:00 | 2624.77 | 2024-10-15T00:15:00+00:00 | `1728951000000` |
| untouched_evaluation | 2024-10-15T00:15:00+00:00 | SOLUSDT | 15m | 2024-10-15T00:14:59.999000+00:00 | 156.9100 | 2024-10-15T00:15:00+00:00 | `1728950400000` |
| untouched_evaluation | 2024-10-15T00:15:00+00:00 | SOLUSDT | 1h | 2024-10-14T23:59:59.999000+00:00 | 157.5200 | 2024-10-15T00:00:00+00:00 | `1728946800000` |
| untouched_evaluation | 2024-10-15T00:15:00+00:00 | SOLUSDT | 4h | 2024-10-14T23:59:59.999000+00:00 | 157.5200 | 2024-10-15T00:00:00+00:00 | `1728936000000` |
| untouched_evaluation | 2024-10-15T00:15:00+00:00 | SOLUSDT | 5m | 2024-10-15T00:14:59.999000+00:00 | 156.9100 | 2024-10-15T00:15:00+00:00 | `1728951000000` |
| validation | 2024-10-01T00:15:00+00:00 | BTCUSDT | 15m | 2024-10-01T00:14:59.999000+00:00 | 63193.50 | 2024-10-01T00:15:00+00:00 | `1727740800000` |
| validation | 2024-10-01T00:15:00+00:00 | BTCUSDT | 1h | 2024-09-30T23:59:59.999000+00:00 | 63309.10 | 2024-10-01T00:00:00+00:00 | `1727737200000` |
| validation | 2024-10-01T00:15:00+00:00 | BTCUSDT | 4h | 2024-09-30T23:59:59.999000+00:00 | 63309.10 | 2024-10-01T00:00:00+00:00 | `1727726400000` |
| validation | 2024-10-01T00:15:00+00:00 | BTCUSDT | 5m | 2024-10-01T00:14:59.999000+00:00 | 63193.50 | 2024-10-01T00:15:00+00:00 | `1727741400000` |
| validation | 2024-10-01T00:15:00+00:00 | ETHUSDT | 15m | 2024-10-01T00:14:59.999000+00:00 | 2605.77 | 2024-10-01T00:15:00+00:00 | `1727740800000` |
| validation | 2024-10-01T00:15:00+00:00 | ETHUSDT | 1h | 2024-09-30T23:59:59.999000+00:00 | 2601.49 | 2024-10-01T00:00:00+00:00 | `1727737200000` |
| validation | 2024-10-01T00:15:00+00:00 | ETHUSDT | 4h | 2024-09-30T23:59:59.999000+00:00 | 2601.49 | 2024-10-01T00:00:00+00:00 | `1727726400000` |
| validation | 2024-10-01T00:15:00+00:00 | ETHUSDT | 5m | 2024-10-01T00:14:59.999000+00:00 | 2605.77 | 2024-10-01T00:15:00+00:00 | `1727741400000` |
| validation | 2024-10-01T00:15:00+00:00 | SOLUSDT | 15m | 2024-10-01T00:14:59.999000+00:00 | 152.4880 | 2024-10-01T00:15:00+00:00 | `1727740800000` |
| validation | 2024-10-01T00:15:00+00:00 | SOLUSDT | 1h | 2024-09-30T23:59:59.999000+00:00 | 152.4280 | 2024-10-01T00:00:00+00:00 | `1727737200000` |
| validation | 2024-10-01T00:15:00+00:00 | SOLUSDT | 4h | 2024-09-30T23:59:59.999000+00:00 | 152.4280 | 2024-10-01T00:00:00+00:00 | `1727726400000` |
| validation | 2024-10-01T00:15:00+00:00 | SOLUSDT | 5m | 2024-10-01T00:14:59.999000+00:00 | 152.4880 | 2024-10-01T00:15:00+00:00 | `1727741400000` |

Representative C03 diagnostics at the first hourly snapshot in each frozen window retain their dependency reasons:

| As-of UTC | Symbol | Strategy / side | Decision | C02/C03 reasons |
|---|---|---|---|---|
| 2024-09-01T01:00:00Z | BTCUSDT | T1 / LONG | NO_TRADE | C02_UNIVERSE_NOT_READY, METADATA_MISSING, TICKER_24H_MISSING, SPREAD_WARMUP_LT_60_VALID_SAMPLES, DEPTH_MISSING, OPEN_INTEREST_MISSING, EVENT_CLEARANCE_MISSING_OR_FUTURE |
| 2024-09-01T01:00:00Z | ETHUSDT | T1 / LONG | NO_TRADE | C02_UNIVERSE_NOT_READY, METADATA_MISSING, TICKER_24H_MISSING, SPREAD_WARMUP_LT_60_VALID_SAMPLES, DEPTH_MISSING, OPEN_INTEREST_MISSING, EVENT_CLEARANCE_MISSING_OR_FUTURE |
| 2024-09-01T01:00:00Z | SOLUSDT | T1 / LONG | NO_TRADE | C02_UNIVERSE_NOT_READY, METADATA_MISSING, TICKER_24H_MISSING, SPREAD_WARMUP_LT_60_VALID_SAMPLES, DEPTH_MISSING, OPEN_INTEREST_MISSING, EVENT_CLEARANCE_MISSING_OR_FUTURE |
| 2024-10-01T01:00:00Z | BTCUSDT | T1 / LONG | NO_TRADE | C02_UNIVERSE_NOT_READY, METADATA_MISSING, TICKER_24H_MISSING, SPREAD_WARMUP_LT_60_VALID_SAMPLES, DEPTH_MISSING, OPEN_INTEREST_MISSING, EVENT_CLEARANCE_MISSING_OR_FUTURE |
| 2024-10-01T01:00:00Z | ETHUSDT | T1 / LONG | NO_TRADE | C02_UNIVERSE_NOT_READY, METADATA_MISSING, TICKER_24H_MISSING, SPREAD_WARMUP_LT_60_VALID_SAMPLES, DEPTH_MISSING, OPEN_INTEREST_MISSING, EVENT_CLEARANCE_MISSING_OR_FUTURE |
| 2024-10-01T01:00:00Z | SOLUSDT | T1 / LONG | NO_TRADE | C02_UNIVERSE_NOT_READY, METADATA_MISSING, TICKER_24H_MISSING, SPREAD_WARMUP_LT_60_VALID_SAMPLES, DEPTH_MISSING, OPEN_INTEREST_MISSING, EVENT_CLEARANCE_MISSING_OR_FUTURE |
| 2024-10-15T01:00:00Z | BTCUSDT | T1 / LONG | NO_TRADE | C02_UNIVERSE_NOT_READY, METADATA_MISSING, TICKER_24H_MISSING, SPREAD_WARMUP_LT_60_VALID_SAMPLES, DEPTH_MISSING, OPEN_INTEREST_MISSING, EVENT_CLEARANCE_MISSING_OR_FUTURE |
| 2024-10-15T01:00:00Z | ETHUSDT | T1 / LONG | NO_TRADE | C02_UNIVERSE_NOT_READY, METADATA_MISSING, TICKER_24H_MISSING, SPREAD_WARMUP_LT_60_VALID_SAMPLES, DEPTH_MISSING, OPEN_INTEREST_MISSING, EVENT_CLEARANCE_MISSING_OR_FUTURE |
| 2024-10-15T01:00:00Z | SOLUSDT | T1 / LONG | NO_TRADE | C02_UNIVERSE_NOT_READY, METADATA_MISSING, TICKER_24H_MISSING, SPREAD_WARMUP_LT_60_VALID_SAMPLES, DEPTH_MISSING, OPEN_INTEREST_MISSING, EVENT_CLEARANCE_MISSING_OR_FUTURE |

## Execution limits and statistics

- STRICT_POLICY_REPLAY remains fail-closed because point-in-time contract metadata and exchange filters, fresh ticker, spread samples, depth, validated OI notional, and verified event clearance are absent.
- Historical funding settlements, bid/ask depth, market impact, original archive publication latency, and observed IOC fills are unavailable and are not inferred from OHLCV.
- Any E1/E2 OHLC execution is a counterfactual bar model, not a historical fill. The model's one-second IOC cannot be resolved from 5m OHLCV; no execution scenarios were eligible in this pilot.
- 1h diagnostic snapshots can miss transient setup changes between hourly evaluations; they are not a full 15m or 5m setup/execution replay. C03 outputs remain strict NO_TRADE diagnostics.

Statistics status is **NOT_TESTABLE**: there are 0 strict historical execution outcomes, so no expectancy interval or performance statistic is reported. The 12-hour purge/embargo remains declared at the split boundaries; no outcome-based holdout analysis was performed.

## Next data requirements

- Dated USDⓈ-M contract listing/status and exchange-filter snapshots, plus a point-in-time universe with historical inactive/delisted contracts and turnover inputs.
- Historical ticker and bid/ask quote/depth snapshots sufficient to reproduce spread, executable liquidity and impact at each decision time.
- Validated open-interest observations with documented units, freshness and contract conversion; authoritative event clearance records with observed availability times.
- Historical funding, mark/index price and liquidation evidence where the strategy policy uses them.
- Exchange publication/ingestion latency and calibrated IOC/partial-fill/stop execution traces or higher-frequency quote/trade data. Do not infer these from klines.

## Reproduction

```sh
ASTRABOT_DATA_ROOT=/path/outside/the/repository work/c04-venv/bin/python scripts/c04_historical_pilot.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 work/c04-venv/bin/python -m pytest -q
```

The acquisition can be replayed in 7-archive batches with `scripts/c04_acquire_binance_um.py`; manifests pin the exact source bytes. Existing C04 `--check` remains the offline regression for the original retained panel.
