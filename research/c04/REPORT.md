# C04 historical replay and execution economics — research handoff

**Run:** `9344c555fe642298adf91a0ec5c17a7172734c062bd0d5f528ad85d917dc7d4b`
**Configuration hash:** `8b3b4b56ef7221227f1d7b77ad943eb020468ac7e0e68d122c04678e7a6fa799`
**Verdict:** `BLOCKED_BY_DATA`
**C05 recommendation:** `INSUFFICIENT_EVIDENCE`

This result is an engineering and source-coverage report. It does not claim an edge, owner approval, or observed exchange fills.

## Scope and provenance

The bounded retained panel contains the source partitions below. It is a parser and causal replay smoke sample; the retained symbol choice was not a strategy-performance selection and does not represent the historical tradeable universe.

| Feed | Symbol | Coverage | Rows | Fidelity | Retained SHA256 | Availability |
|---|---|---|---:|---|---|---|
| klines:1h | BTCUSDT | 2024-10-28T00:00:00.000Z–2024-10-28T23:59:59.999Z | 24 | VENUE_REPORTED | `73930ee78240d99a8184e5dedf808dbd998799c22fcc632732ffdc12dd465c1b` | OBSERVED_WITH_EXPLICIT_AVAILABILITY_PROXY |
| aggTrades:bounded-first-100 | APEUSDT | 2024-10-18T00:00:03.958Z–2024-10-18T00:01:24.156Z | 100 | TRADE_AGG | `52ff319bf0526d02d757b21939ea33f73a125d057469e775e2f119aaaf5fd778` | OBSERVED_WITH_EXPLICIT_AVAILABILITY_PROXY |

The source archive host `data.binance.vision` is outside the selected executor's restricted egress allowlist. The earlier C02 attempt received a CONNECT 403; this task reuses its verified GitHub mirror fixtures and does not repeat blocked download attempts. The historical archive does not prove original publication or transport latency. BTC hourly bars use `close_time + 1 ms` as an availability proxy; APE aggregate trades use exchange transaction time as a proxy. Neither is observed live ingestion time.

No point-in-time exchangeInfo snapshots were retained. Historical listing status, tick/step/min-notional filters, delisting state, and a reliable inactive-symbol panel are therefore unavailable. The current symbol universe was not substituted for historical metadata.

## Opportunity funnel

| Stage | Result |
|---|---:|
| Symbols present in retained panel | 2 |
| Symbols with source coverage | 2 |
| Symbols eligible at latest snapshot | 0 |
| Latest C02 eligibility states | `{'COLD': 1, 'WARMING': 1}` |
| Symbols shortlisted at latest snapshot | 0 |
| Shortlist entries across replay windows | 0 |
| STRICT C03 policy evaluations | 0 |
| Separate C03 diagnostic context evaluations | 48 |
| STRICT research candidates | 0 |
| Armed/confirmed diagnostic setups | 0/0 |
| Diagnostic C03 NO_TRADE records | 288 |
| Approval requested / granted / preauthorized | 0 / 0 / 0 |
| Order attempts / fills / partial fills | 0 / 0 / 0 |
| Protected positions / TP1 / TP2 / stops | 0 / 0 / 0 / 0 |
| Entry misses / expiries / unfilled attempts | 0 / 0 / 0 |
| Portfolio admissions / risk rejections / releases | 0 / 0 / 0 |
| Cumulative / peak reserved modeled risk (USDT) | 0 / 0 |

The strict scanner uses C02's actual eligibility and deterministic shortlist gates, capped at 15. The historical panel has no strict candidate, so its zero execution counters are derived from an empty simulated-event ledger. The separate diagnostic stream calls the actual C03 engine on panel symbols with an empty bypass list; it does not promote those records into eligible trades. The panel symbol count is source coverage, not a reconstructed historical tradeable universe. Funnel and decision details are in `run.json`.

Top missing-input vetoes include absent metadata, ticker, 5M/15M/4H history, 60 spread samples, depth, validated OI notional, and verified event clearance. The 24 BTC 1H rows also fall short of the C03 735-bar ATR percentile warm-up. APE has only 100 aggregate trades and no candle context.

## Historical examples

| Case | Source chronology | Result |
|---|---|---|
| BTCUSDT 1H | Binance public archive; 2024-10-28 00:00 through 23:59:59.999 UTC; 24 rows; replay availability through 2024-10-29 00:00 UTC | C02 ineligible; C03 diagnostic NO_TRADE. No eligible setup or execution outcome. |
| APEUSDT aggregate trades | Binance public archive; 2024-10-18 00:00:03.958 through 00:01:24.156 UTC; first 100 contiguous rows retained from a 45,342-row day | Trade-side parser evidence only; no candle context or eligible setup. |

The positive/negative C03 golden trace remains synthetic and is reported in the separate synthetic section below. No historical target/stop result can be reconstructed from these retained rows.

## Execution cases and economics

E0 records no approval and no observed fill. E1 applies an adverse-side bounded entry, fixed C03 geometry, exchange quantity filters, fees, partial exits, stop/target ambiguity, a 11h55m flatten objective and 12-hour cap as a bar-model counterfactual. E2 applies a preapproved bounded-plan variant with partial size and higher fees/friction; a separate E2 delayed case assumes 15 seconds after trigger. A delay beyond C03's ten-second trigger submission deadline becomes a missed entry. Every OHLC result remains `BAR_APPROX` and is not an IOC fill observation.

Where no observed funding settlements exist, synthetic execution scenarios charge the declared max-hold proxy against modeled remaining quantity-time; partial exits reduce later proxy exposure. This is a labeled sensitivity assumption, not historical funding data.

Historical E0/E1/E2 outcomes: no historical candidate reached this stage; there are zero modeled historical execution outcomes.

## Synthetic fully eligible end-to-end test panel

This fixture is labeled `SYNTHETIC_FULLY_ELIGIBLE_TEST_FIXTURE`. Generated observations exercise C02 eligibility, strict C03 candidate formation, and the existing E0/E1/E2 simulator with separate E1/E2 `PortfolioLedger` instances. None are historical market records, and none enter the historical run or empirical statistics.

| Pipeline stage | Result |
|---|---:|
| C02 eligible symbol windows | 2 |
| Strict C03 research candidates | 1 |
| E0 / E1 / E2 simulated outcomes | E0: UNFILLED, E1: FLAT, E2: FLAT |
| Approval requested / granted / preauthorized | 1 / 1 / 1 |
| Order attempts / fills / partial fills | 2 / 2 / 1 |
| TP1 / TP2 / stops / forced exits | 2 / 2 / 0 / 0 |
| Cumulative / peak reserved modeled risk (USDT) | 2.1599800 / 1.0799900 |

All synthetic counters above come from recorded simulator and ledger events. The scenario PnL fields in `run.json` exist only to exercise accounting and are excluded from the historical `scenario_outcomes`, performance summaries, and C05 recommendation. These mechanics results do not imply profitability.

## Additional synthetic execution mechanics

Synthetic test fixture outcomes are isolated and cannot enter historical performance summaries:

| Scenario | Status | Filled quantity | Simulated exits | Classification |
|---|---|---:|---|---|
| E0 | UNFILLED | 0 | none | NO_EXECUTION_POLICY_TRUTH |
| E1 | FLAT | 10 | TP1, TP2 | SYNTHETIC_MODELLED_EXECUTION |
| E2_PARTIAL_STRESS | FLAT | 5.0 | TP1, TP2 | SYNTHETIC_MODELLED_EXECUTION |
| E2_DELAYED | MISSED_ENTRY | 0 | none | SYNTHETIC_MODELLED_EXECUTION |
| E2_SAME_BAR_AMBIGUITY | FLAT | 10 | STOP | SYNTHETIC_MODELLED_EXECUTION |
| E2_GAP_STOP | FLAT | 10 | STOP | SYNTHETIC_MODELLED_EXECUTION |
| E2_11H55_FLATTEN | FLAT | 10 | FORCED_FLATTEN_11H55 | SYNTHETIC_MODELLED_EXECUTION |
| E2_12H_HARD_LIMIT | FLAT | 10 | FORCED_FLATTEN_12H_HARD_LIMIT | SYNTHETIC_MODELLED_EXECUTION |

Synthetic outcomes verify accounting paths only. C03's scenario net RR is a conditional successful-ladder benchmark, not expectancy. B1 retains the original 40% at +1R and 60% at +2R ladder, 1.6 gross price-R, and equal-cost threshold `c/d <= 0.04`; the empirical share meeting that threshold is not testable here.

## R0–R3 and uncertainty

| Stage | Result |
|---|---|
| R0 data/friction feasibility | `INSUFFICIENT_DATA`; no fee, funding, quote/depth or qualified opportunity distribution |
| R1 setup diagnostics | `NOT_TESTABLE`; zero causally complete setups and no matched controls |
| R2 complete policy replay | `BLOCKED_BY_DATA`; zero C02-eligible symbols and zero strict C03 candidates |
| R3 ablations | `NOT_TESTABLE`; no qualified sample for A01, funding/OI vetoes, obstacles or management comparisons |
| Cluster-aware interval | Undefined; no qualified fills or market-time outcome blocks |

A chronological split is predeclared for a future bounded pilot: dataset window 2024-08-01 through 2024-11-01 UTC; warm-up 2024-08-01–2024-08-31; development 2024-09-01–2024-09-30; validation 2024-10-01–2024-10-14; untouched evaluation 2024-10-15–2024-10-31; 12-hour purge/embargo at boundaries. This supplies more than the 735-hour C03 warm-up while leaving two months for evaluation. Retained coverage does not satisfy any split. No holdout outcome was used to choose a strategy or cohort.

## Performance and reproducibility

Measured on this executor: 0.426538s, peak traced Python allocation 6379011 bytes, 24 availability snapshots, 338 funnel events. These are measurements of the bounded in-memory replay, not archive extraction or broad-universe capacity.

Decision ledger SHA256: `a156a924ff8a236ed9da695cb7cb7a53fdcfe00a07be2ac90b5e126fe5cf54e2`
Funnel ledger SHA256: `e5a4539ab5f86323929ccc6deaad52f64a1da92d4046b912dead24b71a514b7b`

## Data blocker and next experiment

The workspace's restricted egress policy permits Binance documentation hosts but not the archive host; archive retrieval therefore remains blocked here. The existing retained GitHub mirror fixtures provide genuine Binance-origin observations but not a usable multi-symbol policy panel. Missing OI units, historical event/news coverage, quote/depth, funding, metadata changes and executable fill records remain unresolved and fail closed.

Next research task: on an executor whose approved egress permits Binance public historical archives, retrieve the fixed 2024-08-01 through 2024-11-01 pilot range using Binance UM archives for BTC/ETH context and a predeclared altcoin selection based only on point-in-time contract validity, prior 30-day turnover, and realized-volatility/liquidity cohorts. Do not use strategy outcomes for symbol selection. Preserve symbols that become inactive when historical archive and metadata evidence exist; otherwise log the gap. Store raw partitions outside Git, retain checksums and gaps, then populate 1H/4H/15M/5M and funding. Keep verified event, OI-unit, quote/depth, and contract filter status unavailable until authentic point-in-time sources are qualified.

## C05 decision boundary

This report recommends `INSUFFICIENT_EVIDENCE`. It is not the C05 economic decision. Do not advance an empirical policy GO or claim profitable, production-ready, demo-qualified or owner-approved performance from the modeled fixture.

**C04 engineering gate:** the replay, funnel, simulation adapter, statistics, deterministic artifact generation, provenance checks and offline tests are ready for independent review.
**Empirical economic evidence:** insufficient for C05.
**C06:** only a research-only paper MVP may be considered after independent C04 review; no real exposure authority is implied.
