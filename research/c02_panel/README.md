# C02 bounded market panel

`manifest.json` describes the exact source ranges, units, checksums, timestamps,
normalization version, and known coverage limits. The checked-in BTCUSDT candles
and APEUSDT aggregate trades are actual Binance USDⓈ-M archive records mirrored
in Freqtrade's pinned `2026.9` testdata commit. The APE file is only the first 100
of 45,342 records in its source-day archive; the larger archive is not committed.

These records exercise parsing, precision, trade-side mapping, UTC timing, and
deterministic replay. The availability timestamps are exchange-time proxies;
the original archive publication and ingestion latency were not recorded. They
do not establish historical feed latency, current market eligibility, 720/200
bar warm-up, depth/spread/OI coverage, or trading performance. There is no ETH
archive in this inspected fixture set. Synthetic deterministic fixtures live
separately under `tests/fixtures/c02_binance/` and are labeled as synthetic.

Run `.venv/bin/python scripts/c02_replay.py` for an offline end-to-end replay.
It checksum-verifies both retained files, normalizes 24 BTC candles and 100 APE
aggregate trades, emits the A01 golden delta `-81967.0 APE`, reports A02 as
warming because the panel has no 5M candles, reports A03 unavailable, and
records an empty research shortlist with the actual missing-coverage reasons.

## Bounded storage and throughput sample

Run `python scripts/c02_bench.py` (or `.venv/bin/python
scripts/c02_bench.py` in the task environment) to repeat the offline raw
normalization of these files. On Python 3.12.14, the latest sample had 124
actual rows, 9,321 retained raw CSV bytes, 109,643 bytes when the normalized
observations were encoded as one JSON panel, and 47,581.6 normalized rows per
second across 200 repetitions (0.52121 seconds). Timing varies with the shared
environment. The number is a small in-memory parser/model measurement only. It
excludes downloads, archive expansion, storage indexes, network latency and
production concurrency; it is not a capacity forecast.
