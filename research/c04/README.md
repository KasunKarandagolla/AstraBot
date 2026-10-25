# C04 replay and data recovery

`REPORT.md` is the human handoff; `run.json` is the machine-readable event/decision ledger; `source_inventory.json` records partition hashes, source availability, limits and the bounded retrieval plan. Historical observations and synthetic fixtures stay in distinct evidence classes.

## Reproduce the retained panel

From the repository root, with the pinned test environment installed:

```sh
work/c04-venv/bin/python scripts/c04_replay.py --check
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 work/c04-venv/bin/python -m pytest -q
work/c04-venv/bin/python -m compileall -q src/astrabot tests scripts
work/c04-venv/bin/python -m pip check
```

The runner is offline. It verifies the retained-file SHA256 values in `research/c02_panel/manifest.json`, normalizes with the existing C02 adapters, advances at declared source availability, calls `scan_universe()` and `research.engine.evaluate()`, and keeps a separate serialized `ResearchState` per symbol. Its exploratory diagnostic stream has no mandatory-gate bypasses. `E0`, `E1` and `E2` simulation outputs remain separate from historical decisions.

The run computes a stable `run_id`, decision/funnel ledger hashes, counters, and bounded runtime/memory measurements. The event ledger stores source event time, `available_at`, and deterministic replay processing time separately. Re-running with the same retained manifest and config reproduces decision IDs and both ledger hashes; measured runtime may vary.

## Retained source boundary

The verified inputs are BTCUSDT 1H bars for 2024-10-28 and the first 100 contiguous APEUSDT aggregate trades for 2024-10-18. Their source archive IDs, GitHub mirror pins, raw archive checksums, retained checksums, units, actual coverage, and availability proxies are in `../c02_panel/manifest.json` and the generated `source_inventory.json`.

The previous C02 retrieval attempt to `data.binance.vision` received a CONNECT 403; this executor's current restricted egress allowlist does not include that hostname. C04 did not repeat the denied download or try an unapproved route. GitHub mirror fixtures were already retained and checksum-verified. There are no point-in-time exchangeInfo snapshots, trustworthy historical inactive/delisted-symbol flags, verified event/news coverage, validated historical OI units, historical quotes/depth, or historical funding in the retained panel. Do not populate these fields from modern exchange status or fabricated values.

## Predeclared next pilot

The bounded target study window is **2024-08-01 through 2024-11-01 UTC**, chosen to allow a 735-hour history warm-up and two months after warm-up. The split is frozen before any replay result: warm-up 2024-08-01–2024-08-31, development 2024-09-01–2024-09-30, validation 2024-10-01–2024-10-14, untouched evaluation 2024-10-15–2024-10-31, with a 12-hour outcome purge/embargo at boundaries. Existing records cover only isolated feeds within this date range and satisfy none of the splits.

Use BTC and ETH for context. Select altcoin study symbols without looking at strategy returns: require evidence of point-in-time Binance USDⓈ-M contract validity, then stratify on the prior 30-day quote turnover and realized volatility. Keep every in-scope symbol's source gaps and ineligibility. Include later-inactive symbols only where dated metadata/archive evidence supports their historical identity. If reliable historical contract metadata is unavailable, preserve that as an explicit universe-coverage blocker.

On an executor whose approved egress allows the archive host, fetch bounded monthly public files and record the exact response bytes and hashes before parsing. Example only; this command was **not** run in C04:

```sh
curl --fail --location \
  'https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2024-08.zip' \
  --output work/BTCUSDT-1h-2024-08.zip
sha256sum work/BTCUSDT-1h-2024-08.zip
unzip -Z1 work/BTCUSDT-1h-2024-08.zip
```

Repeat only for the predeclared symbol/feed list and exact months in the study window. Store larger raw partitions outside Git and keep a versioned manifest in the repository. The current loader accepts C02 manifest partitions such as `klines:1h`, `klines:4h`, `klines:15m`, `klines:5m`, and bounded `aggTrades` CSVs. `derive_4h_from_1h()` is available for complete contiguous UTC groups and records `BAR_DERIVED_APPROX`, component IDs, aggregation semantics and latest-component `available_at`; missing groups are skipped, never interpolated.

Do not derive spread, depth, OI units, event clearance, or executable IOC/stop fills from OHLCV. Classify every feed as observed point-in-time usable, observed with an availability proxy, retrospective-only, unverified, or unavailable. If the approved source does not exist, STRICT remains NO_TRADE and the report remains `BLOCKED_BY_DATA`.

## Build-versus-reuse decision

Freqtrade and NautilusTrader are evaluated in `docs/03-COMPONENT-REUSE-REGISTER.md` §10. The C04 implementation wraps C02/C03 in a small event loop because a full framework adapter would have to recreate C03 setup persistence, C02 availability gates and the explicit research funnel while the data panel is still blocked. No replay-framework dependency was added. Revisit only after a representative full-data benchmark demonstrates a concrete limitation.
