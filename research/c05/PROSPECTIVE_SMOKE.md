# C05-C0 prospective public-market observer smoke test

**Result:** offline fixture processing and provenance checks pass. The current environment did not deliver Binance market data: a single `GET /fapi/v1/time` returned HTTP 451 with a restricted-location message. Binance's official API documentation request was blocked by the environment's CONNECT proxy. The observer therefore remains a one-shot prototype for independent review; no continuous collection or C05 economic qualification is established.

## Scope and implementation

The new `scripts/c05_observe_once.py` runs deterministic fixtures by default. `--live-once` is required for network access and requires an explicit external `ASTRABOT_DATA_ROOT`. Its fixed request plan is one time query, one metadata query, then one each of `bookTicker`, bounded depth (five levels), open interest, premium index, and ten aggregate trades for SOLUSDT and DOGEUSDT. It only constructs unauthenticated HTTPS `GET`s for the seven candidate paths and the two declared symbols. It has no credentials, signing, private endpoints, order methods, loops, scheduler, or retry path.

Raw response bytes and per-request JSON sidecars are stored below `ASTRABOT_DATA_ROOT/c05-observer/`. The root is rejected if it resolves inside the Git checkout. Each sidecar records the source URL, request-start and response-received UTC timestamps, monotonic duration, status, source event times when present, original payload-unit notes, schema/source version, SHA256, response size, timestamp validation, stale status, and missing fields or errors. A run summary points to each source record and its quality result. The fixed live limits are 12 GET attempts maximum and 5,000,000 response-body bytes maximum. The first transport, non-2xx HTTP, or truncated response halts further requests; each skipped feed is retained as unavailable.

The offline fixtures are explicitly `SYNTHETIC_FIXTURE`. Their bid/ask, depth, OI, funding, and trade values are test inputs, not market observations. OI unit validation, OI notional, historical availability, and event clearance remain `UNVERIFIED`; no funding settlement, execution fill, or C02-ready observation is synthesized. One-shot snapshots cannot meet the C02 warm-up requirements, including 60 consecutive one-minute spread samples.

## Network observations

The one market-data probe was a connectivity check, not a capture run through the CLI:

| Request | Result | Response-body bytes |
|---|---:|---:|
| `GET https://fapi.binance.com/fapi/v1/time` | HTTP 451; body said the service was unavailable from a restricted location under Binance's eligibility terms | 224 |
| `GET https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api` | No HTTP response; `curl` reported `CONNECT tunnel failed, response 403` (`HTTP=000`) | 0 |

The public market smoke used **1 of 12 allowed GETs** and received **224 of 5,000,000 allowed response bytes**. Counting the separate documentation request, there were two outbound GET attempts and 224 response-body bytes. No metadata or symbol feed endpoint was queried after the time endpoint returned 451. There were no retries, alternate hosts, or proxy changes. The 451 body did not include `serverTime`, so no live exchange/local clock offset was measurable.

The official current endpoint documentation and its request weights/limits could not be checked here. The candidate path/field plan follows the task allowlist and existing C02 parsing conventions, but this session does **not** certify current Binance endpoint semantics or rate limits. The only observed Binance API result is the restricted-location response above. Other feeds are unobserved, not proven unavailable.

## Offline verification

The default CLI completed against all 12 deterministic fixture responses: 1,720 response-body bytes, zero network requests, reproducible source IDs and SHA256 checksums, and `C02 readiness=BLOCKED`. The fixture output was written outside Git under `/tmp/astrabot-c05-observer-test2` for this smoke run. It is disposable test data, not an owner-selected storage location.

Focused tests exercise distinct source/receive times, approved symbol/path enforcement, GET-only unauthenticated transport, invalid/missing fields, timestamp validation, duplicate and out-of-order trade detection, checksum reproduction, external-root enforcement, the OI/event fail-closed status, the 12-request plan, first-error halt, and the 5 MB byte cap.

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 work/c05-venv/bin/python -m pytest -q \
  tests/test_c05_observer.py tests/test_c02_data.py tests/test_c04_replay.py
45 passed in 5.32s
```

`compileall` for the observer, script, and focused tests passed. `git diff --check` passed. No historical archive was downloaded, no C04 replay was run, and no strategy/risk or shared C02/C04 module was changed. The observer is additive and isolated in `src/astrabot/data/observer.py`.

## Timestamp meaning and current readiness blockers

Request-start and response-received times are local UTC. Duration uses a monotonic clock. A valid Binance `serverTime` is compared with local start, receive, and midpoint times; the midpoint is only an estimate because network delay/asymmetry and local clock error remain mixed together. Sample timestamps from OI and premium index and transaction times from aggregate trades are retained separately when valid. Book ticker and depth responses do not get an invented source timestamp if none is supplied. Staleness is measured only where a source timestamp is present; otherwise the status is `UNDETERMINED`.

Prototype stale thresholds are 5 seconds for the exchange time response, 60 seconds for OI and premium-index samples, and 10 seconds for the newest aggregate trade. These are observer quality flags; they do not change C02 readiness.

This session captured no market record. Even from a permitted environment, these one-shot responses would not establish the C02 720-hour/200-four-hour warm-up, consecutive spread history, historical contract state, validated OI notional, authoritative event clearance, account-specific fees, or actual order/fill outcomes. A successful future one-shot response would establish only that a bounded public response was received and checksummed at that moment. It would not prove continuity, warm-up, strategy eligibility, economic expectancy, or execution quality.

Before continuous evidence can be trusted, the owner must separately choose a permitted runtime, observation horizon, storage retention, and monitoring/recovery plan. The live endpoint schema and limits need verification against accessible official documentation, captures need measured clock and gap behavior across restarts, OI units need independent validation, and event coverage needs a separately defined source plan. Actual fill and fee evidence remains outside this public observer.

## Runtime and external-storage recommendation for owner review

For a bounded multi-week observation period, the recommended candidate is a small owner-controlled remote Linux host with UTC time synchronization, a supervised single process, restart logs, disk alerts, and a local write buffer. Keep immutable raw partitions and checksums in a separate owner-controlled external object-storage account with versioning and lifecycle controls; choose retention only after the owner declares the horizon. Start with approximately 1 vCPU and 1–2 GiB RAM for two symbols, then size storage from measured bytes/day. This is a recommendation for an owner decision, not a deployment choice.

| Option | Reliability and restarts | Clock and monitoring | Storage and retention |
|---|---|---|---|
| Owner-controlled local host | Uses existing hardware and direct ownership; home power, internet, and device restarts can create gaps unless backed by UPS and supervised restart behavior | UTC/NTP is available, but drift and downtime need independent monitoring | Local disk is simple; external backup is needed for durable retention and recovery |
| Small always-on remote host | More stable power/network and simpler restart supervision; still needs health checks and alerting | Provider time sync is usually easier to keep stable; verify clock offset in the collector | Separate external object storage supports versioning and retention rules; provider region, access control, and restore path need owner review |

No provider price was sourced, so cost is **unknown**. Storage growth is also unknown until actual feed cadence and bytes/day are measured. No host, bucket, retention period, or horizon was provisioned or selected. The owner decision remains runtime, horizon, and retention.

## Project status

P3 remains on the research-evidence hold. `C05 = INSUFFICIENT_EVIDENCE`; T1/R1/B1 remain `RESEARCH_ONLY`; credited milestone completion remains 45%. OpenBot and C06–C09 roadmap status are unchanged. This prototype does not authorize continuous collection, strategy changes, or trading.

**Disposition:** `C05_C0_READY_FOR_INDEPENDENT_REVIEW`
