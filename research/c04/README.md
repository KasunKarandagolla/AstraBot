# C04 replay and data recovery

`REPORT.md` is the human handoff; `run.json` is the machine-readable event/decision ledger; `source_inventory.json` records partition hashes, source availability, limits and the bounded retrieval plan. Historical observations and synthetic fixtures stay in distinct evidence classes.

The original C04 artifacts describe the data available at PR #4 review time. The post-merge archive recovery is documented separately in [`historical_pilot.md`](historical_pilot.md), [`pilot_summary.json`](pilot_summary.json), and the checksum manifests [`historical_manifest.json`](historical_manifest.json) and [`smoke_manifest.json`](smoke_manifest.json). Raw archives remain outside Git under `ASTRABOT_DATA_ROOT`.

## Reproduce the retained panel

From the repository root, with the pinned test environment installed:

```sh
work/c04-venv/bin/python scripts/c04_replay.py --check
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 work/c04-venv/bin/python -m pytest -q
work/c04-venv/bin/python -m compileall -q src/astrabot tests scripts
work/c04-venv/bin/python -m pip check
```

The runner is offline. It verifies retained-file SHA256 values in `research/c02_panel/manifest.json`, normalizes with the existing C02 adapters, advances at declared source availability, calls `scan_universe()` and `research.engine.evaluate()`, and keeps a separate serialized `ResearchState` per symbol. Strict C03 candidates run through E0/E1/E2; E1 and E2 use separate `PortfolioLedger` instances. Approval, fill, exit, risk and funnel counters are derived from the execution-event ledger. Its exploratory diagnostic stream has no mandatory-gate bypasses.

The runner also replays a clearly labeled `SYNTHETIC_FULLY_ELIGIBLE_TEST_FIXTURE` through the same C02, C03, simulator and portfolio-ledger path. It proves the integrated path produces approvals, modeled fills, target exits, and risk reservation/release events. Synthetic outcomes are kept out of the historical panel's `scenario_outcomes`, empirical statistics and C05 recommendation. They are mechanics evidence only and do not represent historical market records or profitability.

The run computes a stable `run_id`, decision/funnel ledger hashes, counters, and bounded runtime/memory measurements. The event ledger stores source event time, `available_at`, and deterministic replay processing time separately. Re-running with the same retained manifest and config reproduces decision IDs and ledger hashes; measured runtime may vary. The actual retained panel remains `BLOCKED_BY_DATA` with a C05 recommendation of `INSUFFICIENT_EVIDENCE`.

## Retained source boundary

The verified inputs are BTCUSDT 1H bars for 2024-10-28 and the first 100 contiguous APEUSDT aggregate trades for 2024-10-18. Their source archive IDs, GitHub mirror pins, raw archive checksums, retained checksums, units, actual coverage, and availability proxies are in `../c02_panel/manifest.json` and the generated `source_inventory.json`.

The original C02 retrieval attempt received a CONNECT 403, and that C04 run stopped without bypassing the restriction. For this follow-up, the enforced network policy explicitly allows `data.binance.vision`; the configured proxy returned HTTP 200 for every bounded public archive. The older GitHub mirror fixtures remain separate from this new official-archive pilot. There are still no point-in-time exchangeInfo snapshots, trustworthy historical inactive/delisted-symbol flags, verified event/news coverage, validated historical OI units, historical quotes/depth, or historical funding. Do not populate these fields from modern exchange status or fabricated values.

## Predeclared next pilot

The bounded target study window is **2024-07-01 through 2024-11-01 UTC**. The source-only warm-up is extended into July: C02 requires 200 contiguous closed 4H bars, while August alone contains only 186. The split is frozen: source-only warm-up 2024-07-01–2024-08-31, development 2024-09-01–2024-09-30, validation 2024-10-01–2024-10-14, untouched evaluation 2024-10-15–2024-10-31, with a 12-hour outcome purge/embargo at boundaries.

The bounded follow-up pilot declares BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, ADAUSDT, and DOGEUSDT before replay. This is a fixed research cohort, not a reconstructed point-in-time or dynamic historical universe. Contract-validity history, inactive-symbol coverage, turnover ranking, and realized-volatility cohort selection remain unverified; preserve that as an explicit universe-coverage blocker.

The following URL illustrates the public archive layout; the follow-up used the bounded Python client below rather than `curl`:

```sh
curl --fail --location \
  'https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2024-08.zip' \
  --output work/BTCUSDT-1h-2024-08.zip
sha256sum work/BTCUSDT-1h-2024-08.zip
unzip -Z1 work/BTCUSDT-1h-2024-08.zip
```

The executed plan uses 112 monthly archives: the seven declared symbols × four required intervals (`5m`, `15m`, `1h`, `4h`) × July–October 2024. It avoids a full 1-minute study history; the only 1-minute files are the seven one-day ingestion smoke archives. Acquisition is sequential in 7-file batches, uses HTTPS via the approved proxy, stops on HTTP, storage, integrity, schema, or continuity errors, and writes per-archive source/size/SHA256/coverage evidence. Reproduce acquisition with:

```sh
ASTRABOT_DATA_ROOT=/path/outside/the/repository \
  work/c04-venv/bin/python scripts/c04_acquire_binance_um.py \
  --phase smoke --manifest research/c04/smoke_manifest.json
```

For the historical phase, rerun the command with `--phase pilot --manifest research/c04/historical_manifest.json` until all 16 bounded batches are complete. The offline `load_public_um_archive_panel()` verifies each committed checksum manifest and uses C02 kline normalization. `scripts/c04_historical_pilot.py` runs the existing C04 C02/C03 replay at hourly availability snapshots while retaining all four source intervals in each as-of context; this can miss setup changes between hourly evaluations and is not a full 15-minute or 5-minute execution replay.

Do not derive spread, depth, OI units, event clearance, or executable IOC/stop fills from OHLCV. Classify every feed as observed point-in-time usable, observed with an availability proxy, retrospective-only, unverified, or unavailable. If the approved source does not exist, STRICT remains NO_TRADE and the report remains `BLOCKED_BY_DATA`.

## Build-versus-reuse decision

Freqtrade and NautilusTrader are evaluated in `docs/03-COMPONENT-REUSE-REGISTER.md` §10. The C04 implementation wraps C02/C03 in a small event loop because a full framework adapter would have to recreate C03 setup persistence, C02 availability gates and the explicit research funnel while the data panel is still blocked. No replay-framework dependency was added. Revisit only after a representative full-data benchmark demonstrates a concrete limitation.
