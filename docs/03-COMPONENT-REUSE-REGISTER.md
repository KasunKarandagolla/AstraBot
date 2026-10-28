# 03 — Component Reuse Register and Qualification Plan

**Rule:** `ADOPT → CONFIGURE → WRAP → SMALL PATCH → BUILD ONLY IF NECESSARY`. A linked upstream repository is a **candidate**, never a claim it passed our tests. Store exact package version/commit, golden fixture results, integration boundary, fallback, maintenance burden and removal plan in each completed adoption record.

## 1. Target components, evidence required and minimal integration

| Capability | First choice/candidates to compare | Integration pattern | Required proof before adoption | State |
|---|---|---|---|---|
| Agent coordination | [OpenBot](https://openbot.run/) with Codex provider (owner-selected model) + six read-only MCP tools | strict stdio MCP gateway; synthetic `RESEARCH_ONLY` fixtures | PRs #11/#13/#15; official MCP SDK client subprocess integration and 221 CI tests; owner-reported Windows OpenBot negative and positive six-tool ID-handoff fixture workflows, exact plan hash/status retained after rejected extra risk field | READ-ONLY REAL-AGENT MULTI-TOOL C06-D REPORTED; MFA/OUTAGE/PRODUCTION UNQUALIFIED |
| Binance public, agent-facing skills | [Binance Skills Hub](https://github.com/binance/binance-skills-hub), CLI | import read-only skill into isolated agent environment | read-only BTC + altcoin USD-M calls, no order permissions, timeout/error behavior | CANDIDATE |
| Binance live transport | [Official USD-M modular Python SDK](https://github.com/binance/binance-connector-python/tree/master/clients/derivatives_trading_usds_futures) | adapter behind single-owner gateway | demo market/user streams, IOC/limit IDs, algo stops, restart, reconnect | PINNED / C01 provisional recommendation; §7 |
| Alternative single live owner | [Freqtrade](https://github.com/freqtrade/freqtrade) | adapt callbacks only if truly fail-closed | approval fail-closed, early fill protection, paired partial TP, safe stop replacement, unknown submits | REJECTED as live owner at C01 pin; research use unqualified |
| Alternative single live owner | [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | native event adapter | exact Binance one-way isolated/order support, bracket limitations, protection, replay/live semantics | DEFERRED after C01 source comparison; §7 |
| Generic exchange data fallback | [CCXT](https://github.com/ccxt/ccxt) | Python data-only adapter | required futures endpoint semantics, normalization, rate limits | DEFER unless SDK missing |
| Additional exchange feeds | [Cryptofeed](https://github.com/bmoscon/cryptofeed) | process-isolated feed adapter | clear data coverage benefit vs SDK WS; dependency cost | DEFER until gap proven |
| SMC/ICT | [smart-money-concepts upstream](https://github.com/joshyattridge/smart-money-concepts); comparator [pyvsmc](https://github.com/Khaymat/pyvsmc) | causal event wrapper; **do not trust retrospective labels** | expanding-prefix invariance; swing, liquidity, OB and FVG available_at; numerical golden cases | CANDIDATE |
| Classical indicators | [TA-Lib Python](https://ta-lib.github.io/ta-lib-python/) or qualified maintained package | direct Python wrapper | stable ATR/ADX/RSI/Bands warm-up and NaN behavior | CANDIDATE |
| VWAP / Anchored VWAP | prebuilt tested indicator implementation; [srl-python-indicators](https://github.com/srlcarlg/srl-python-indicators) comparator | wrapper defining session/event anchor IDs | identical historical/live rollover, correct trade-volume weighting or declared approximation | CANDIDATE |
| Order-flow delta / footprint | [Freqtrade order flow](https://www.freqtrade.io/en/stable/advanced-orderflow/) (beta) or qualified specialist package | trade-derived wrapper | aggressor side mapping, missing trade detection, reset semantics, historical replay fidelity | CANDIDATE / MANDATORY FOR A01 |
| Market/volume profile | qualified trade-derived profile calculator, `srl-python-indicators` comparator | price-bucket/POC/VAH/VAL wrapper | executed-price aggregation; no candle-close profile mislabeled tick-true | CANDIDATE |
| OI/funding/basis | Binance USD-M API and archive first | normalized read-only API | units, mark/index and funding settlement time, history coverage | CANDIDATE |
| Liquidations / heatmaps | Binance public events + properly labeled estimates; [HyperData Terminal](https://github.com/Co-Messi/HyperData-Terminal) comparator | read-only feature adapter | sampled events vs inferred maps separately, test freshness and reliability | OPTIONAL INPUT; A04 IN SCOPE |
| Event/news intelligence | Binance official announcements + verified calendars/feed | source adapter + deterministic blackout | symbol mapping, publication vs event time, correction/deduplication | CANDIDATE |
| Baseline research engine | Freqtrade backtesting, or selected reusable alternative | research-only backtest adapter | independent closed-bar chronology, fees, funding, 1M detail where needed | DECIDE IN C01/C04 |
| Tick-level fill studies | [HftBacktest](https://github.com/nkaz001/hftbacktest) | offline event replay where data supports it | market depth, queue, latency semantics, no-market-impact caveat | CONDITIONAL / DEFER |
| Statistical uncertainty | [arch bootstrap](https://arch.readthedocs.io/en/latest/bootstrap/timeseries-bootstraps.html) | market-time joint block resampling | correlated-symbol uncertainty and reproducibility | CANDIDATE |
| Storage | PostgreSQL; raw trades parquet/file archives | one logical application initially | transactional intents/reservations, append-only events, restart replay | STANDARD INFRASTRUCTURE |
| Owner approval | existing authenticated framework/UI where possible | thin custom immutable plan/hash/nonce service | one-use atomic approval, MFA, timing, negative tests | CUSTOM CONTRACT NECESSARY |

Do not silently substitute `[tpwilo/smc](https://github.com/tpwilo/smc)` for the upstream SMC package; it is a fork. Pin the actual imported artifact, not an approximate GitHub link. Prebuilt code can still be unsuitable for causal features without a wrapper or tests.

## 1A. Best-working-project selection, not a shallow library checklist

The project lead must **search for complete, mature implementations of the target trading logic** before proposing basic custom indicators. Search upstream repos, actual tested trading engines, well-maintained strategy implementations, documented example policies, and verifiable public trading analysis. For each serious candidate, record (a) **what it actually computes/decides** and under what market context, (b) whether it is executable/live/replay tested rather than README-only, (c) causal data and feature semantics, (d) stop/target and thesis-management coverage, (e) reproducible meaningful examples, negative cases and failure modes, (f) integration/maintenance cost, and (g) the thinnest viable adapter. Compare the best 2–3 credible candidates, not dozens of repositories by stars.

**Reuse substantive judgment when available**: e.g. footprint/delta calculations with price response, real structure confirmation, anchored VWAP regime interpretation, properly sourced volume profiles, not simply ten indicator values. If an expert-grade prebuilt component exists but requires adaptation, adapt it before building a toy replacement. A proven analytical library is not automatically a profitable trading strategy; the actual composed executable policy still needs a deep strategy study, practitioner-case parity checks and whole-policy economic evaluation per `04`.

Candidate demos, social-media chart annotations and claimed trader win rates are evidence of ideas/behavior **only**, not independently verified track records. Prefer unambiguous test data, code behavior and repeated out-of-sample cases. Record decisions briefly and avoid repeatedly re-shopping a qualified component absent a material deficiency.

## 2. Engine-owner feasibility decision C01 (short, hard gate)

In one scoped **GPT-6.1 Sol** session compare pinned versions of: (A) official USD-M SDK + thin durable gateway, (B) Freqtrade as *sole* writer, (C) NautilusTrader as *sole* writer. Research only exact gap costs, not generic popularity. Use fake venue plus supported Binance demo for:

1. fail-closed approved-entry boundary under callback/tool exceptions and forced-entry paths;
2. persistent intent, idempotent client IDs and unknown IOC submission reconciliation;
3. protection after first partial fill, whole-position stop, two TP legs, late fills;
4. stop tightening without cancelling the sole verified stop;
5. restart/reconnect, first-fill 12h timer, isolated one-way mode, reserved API priority.

Produce `ADR-EXEC-001` in `07` with tested matrix, release pins, unknowns, total integration/maintenance scope and one recommended owner. **SDK is provisional**, not prejudged winner. Choosing an owner is **not permission** to deploy live; owner approval is required for any significant topology deviation.

## 3. Every adapter must provide

- `build_info`: name, upstream, imported package, exact version/hash, dependencies, feature list.
- Input schema: candle/trade/depth contract, time/units and symbol mapping.
- Output schema: `event_time`, `available_at`, source IDs, numeric precision, validity, readiness and fidelity.
- Failure behavior: `UNAVAILABLE/DEGRADED` for missing inputs; no invented data, no silent fallbacks.
- `golden_fixture` and `expanding_prefix` test coverage where causal history matters.
- Performance budget: throughput/latency, memory and cost for broad scan vs shortlist, measured rather than guessed.
- Update strategy: pinned upstream; explicit fixture requalification on upgrades; rollback route.

## 4. Build-versus-reuse exception (keep short)

Before bespoke computation, record: **problem**, candidates evaluated (at least two when available), why configuration/wrapper/patch fails, minimal custom scope, expected test cost, removability and owner acknowledgment when it changes project shape. Don't invent a general plugin ecosystem merely for theoretical portability. Interfaces should be swappable where replacement is reasonably foreseeable; otherwise ordinary Python functions suffice.

## 5. Secrets and operational trust

Agent skills/LLM tools must not receive trading secrets, authenticated Binance CLI profiles or signed order endpoints. Normalized market data can be read-only. Store production credentials only in the independent execution environment, with scoped permissions and audit. Binance Agent OS/MCP is optional and **not** a second authenticated live writer. Test SDK semantics for chosen Binance account mode, especially conditional orders/position sides, rather than extrapolate from generic REST docs.

## 6. Integration status vocabulary

`CANDIDATE → PINNED → FIXTURE_TESTED → INTEGRATION_TESTED → DEMO_QUALIFIED → OWNER_LIVE_APPROVED`; `DEFERRED/REJECTED` for nonselected components. No component is `QUALIFIED` just because its repository has stars, tests or polished documentation. Update register when a candidate changes status; quote PR and test evidence. Unrelated optimization candidates remain deferred and do not block the next gate.

## 7. C01 inspected execution-owner pins — pending independent review

[ADR-EXEC-001](adr/ADR-EXEC-001.md) contains the complete 16-row comparison,
source/test references, reproducible commands, custom responsibilities and rollback
criteria. [Candidate lock](../tests/vendor/candidates.lock.json) records commits,
source/artifact/document hashes and runtime requirements. No engine is
INTEGRATION_TESTED or DEMO_QUALIFIED by this work.

| Candidate | Exact inspected pin | Actual evidence / reason |
|---|---|---|
| Official USD-M SDK | 18.1.0 + common 4.7.0; `6b3ba001274406372d376e218c8b9d04bd9c1720` | SOURCE_VERIFIED; actual full-package mocked transport: 8 checks; 20 selected upstream mocked tests passed. Provisionally retain the existing SDK/gateway topology. Approval, reservations, durable intents and supervision are future custom glue. |
| Freqtrade | 2026.9; `1f394eaebc2f46a83d26971388628707802f8602`; CCXT 4.5.84 Binance source inspected | SOURCE_VERIFIED + 9 actual AST-extracted hook scenarios FAKE_TESTED, not a full runtime. Approval exceptions permit entry, adjustments/replacements bypass the callback, send precedes durable Trade commit, stop replacement cancels first, and Binance demo is explicitly disabled. Rejected as current live owner; research reuse remains a separate qualification. |
| NautilusTrader | 1.231.0; peeled commit `27a8e54e7ac3c57d6cbf8891f0283dfbaee97317` | SOURCE_VERIFIED only; modern algo/child routing, partial-fill/cache/reconciliation machinery and explicit demo hosts exist. Native linked Binance brackets are rejected; application approval/reservations/exit latch and independent leg coordination remain. Defer until measured benefit justifies larger native/async/cache integration. |

Remaining **UNVERIFIED** for every candidate: actual account mode and demo connectivity,
whole-position stop plus two partial reduceOnly TPs, overlap replacement safety,
unknown IOC and parent/child reconciliation under venue faults, protection latency,
restart fencing and API-priority load behavior. Existing verified stops must be retained
if elective replacement cannot be qualified. No real account or exchange order was used.

C01's narrow BUILD/WRAP boundary is the already-authorized typed approval/risk/lifecycle
glue and fake fixture; it introduces no production OMS, new runtime topology or
indicator implementation. The original v1.5 reference remains unchanged.

## 8. C02 read-only data and feature evidence — pending independent review

| Capability | Exact component/pin and source inspected | Test evidence and decision | Limits and removal/upgrade plan |
|---|---|---|---|
| Binance public REST | No third-party runtime transport adopted. `src/astrabot/data/binance.py` uses Python 3.12 stdlib `urllib`; endpoint and parameter allowlists pin calls to public `/fapi` and `/futures/data` GET endpoints. | Offline transport fixtures cover endpoint rejection, auth-parameter rejection, pagination, 418/429 retry bound, malformed data, source IDs, Decimal fields and timestamps. No key/signing/account/order implementation exists in the C02 module. | Live Binance behavior is UNVERIFIED. Replace the transport only if a pinned SDK/data client passes the same public-only and endpoint-semantic tests with a smaller boundary; retain the allowlist adapter and offline suite. |
| A01 order flow / CVD | Freqtrade 2026.9 at `1f394eaebc2f46a83d26971388628707802f8602`; inspected `freqtrade/data/converter/orderflow.py` and `tests/data/test_converter_orderflow.py`. It groups CCXT trades into candle price levels with ask/bid delta, cumulative delta and imbalance. | Not adopted as CVD provider: source grouping loses the ordered aggregate-trade identities and complete-window continuity needed here. C02's minimal signed-base-volume transform is tested against maker-side mapping, duplicate/gap/order behavior, missing-coverage fail-closed behavior, and the 100-record APE archive golden `-81967 APE`. | The local A01 output is bounded-window trade-derived CVD, not a full session or footprint engine. Adopt Freqtrade's footprint transformation later only behind an adapter that retains source chronology/IDs and passes continuity and prefix tests. |
| A02 VWAP | `srl-python-indicators` repository link was not located (404 at inspection); no tested VWAP package was adopted. | C02 implements only the v1.5 formula: closed 5M typical price × base volume, UTC midnight session, zero/missing volume fail-closed. Golden arithmetic, missing bars, append-prefix invariance and midnight rollover are tested in `tests/test_c02_features.py`. | `BAR_DERIVED_APPROX`, not trade-exact. Keep the wrapper removable; replace after identifying a maintained implementation with tested live/history session parity and identical unit/anchor semantics. Event VWAP remains unimplemented. |
| A03 market structure | `smart-money-concepts@1b62fd6c41e1f508e7ed76831a039fa4c82d42f6`; inspected FVG `shift(-1)`, centered/full-series swing and BOS paths. Comparator `Khaymat/pyvsmc@55008a6dce09e0e36691d2e34150f0f499ac4f4b`; inspected centered rolling swings and future mitigation scans. | Neither package is adopted. C02 returns `UNAVAILABLE` with source commits and reason; the test appends future bars and confirms no retrospective value is emitted. | Expanding-prefix and true confirmation `available_at` qualification remains the smallest path to adoption. If either source passes all relevant event tests at a later pinned commit, replace the fail-closed adapter; no custom SMC engine is started here. |
| Shared schema and replay | Existing C01 `src/astrabot/contracts.py` plus C02 `data/models.py`, `data/replay.py` and `features/providers.py`; Pydantic `2.14.1` from the existing exact test/package pin. | C01 regression plus C02 fixture/golden/prefix tests are in the offline workflow. Stable IDs, config hashes, provenance, Decimal values, explicit UTC and readiness are exercised. | Python implementations remain small functions rather than a dynamic registry. Upgrade Pydantic only with C01 and C02 contract regression evidence; A04–A10 remain valid `A\d{2,}` family identifiers without empty implementations. |
| OI units | Inspected [Binance USDⓈ-M Open Interest](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest) and [Open Interest Statistics](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics). The current response gives `openInterest`; history gives `sumOpenInterest` and `sumOpenInterestValue`, but the published response schema does not name a unit for either value. | The adapter preserves the raw history value in `reported_open_interest_value`, leaves `unit_validated=false` and `open_interest_notional_usdt=null`, and the scanner returns WARMING. Fixtures assert this fail-closed behavior; no quote-notional conversion is inferred from the field name. | This prevents real REST OI from satisfying the 5M USDT gate yet. Enable only after Binance documents the USDⓈ-M unit or a pinned versioned cross-check against known instrument units/mark-price semantics passes numerical validation. |

The Binance [aggregate trades response](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Compressed-Aggregate-Trades-List) defines `m` as whether the buyer was maker; C02 maps `true` to SELL aggression and tests that mapping with retained archive records. The C02 feature smoke suite uses local wrappers because the reviewed prebuilt
options either do not provide required input continuity or fail causal
qualification. No runtime dependency was added for C02.

**S02 source-clock reuse (2026-10-28):** `data/source_clock.py` wraps the existing C01 frozen Decimal/UTC contracts, C02 identities/spread formula and C05-G header/time/Decimal/source-row hash helpers; the CLI also reuses G's disk duplicate detector and derivative/book audits. C05-H remains the date-effective unit/measurement authority. No package/platform is adopted. `proposed.c02.sample-clock.v2.0.0` is research-only with retained invalid rows and shared pure scanner/replay selection; production C02 and existing G versions stay unchanged. Boundary, causal-prefix, cross-source, normalization-integrity and replay reproduction tests are in `tests/test_s02_source_clock.py`. Retire the wrapper only after a separately approved replacement passes those same tests and preserves all original clocks/IDs; no historical source acceptance follows from software qualification. Full adapter map: [S02 ADR](adr/ADR-P3-SOURCE-CLOCK-AND-ACCEPTANCE-S02.md).

## 9. C03 causal policy components — ready for independent review

Exact pins, inspected source/tests, practitioner cases and external verification
are in [the evidence report](../research/c03/EXPERT_EVIDENCE.md) and
[source lock](../research/c03/sources.lock.json). Source inspection is distinct
from executed tests and from empirical market qualification.

| Component | Decision and evidence | Integration / maintenance boundary |
|---|---|---|
| TA-Lib Python 0.6.8 (`cbd8921c340c8ad330257ad807c2809cb557f6c5`), C 0.6.4 (`43f9d5042ecc4bd367941846494ad907bf20ea50`), NumPy 2.2.6 | **WRAP / FIXTURE_TESTED** ATR14, ADX14 and SMA-seeded EMA50. Local numerical, warm-up and prefix tests exercise the installed wheel; unexpected library/global configuration fails closed. Upstream full suite NOT RUN. | Two runtime dependencies, exact test pins. Float64 calculations are converted to finite Decimal observations; money/geometry stay Decimal. Requalify on upgrades. ATR percentile needs 735 raw 1H bars for 720 preceding finite ATR observations. |
| LEAN `f3d841e60dfd010ee5fc293ea893e56952484108` | Streaming strict-pivot, VWAP and Donchian source/tests inspected. **BUILD MINIMUM** explicit v1.5 strict 3-left/3-right swing; adopting the C# trading engine for this seven-bar rule is disproportionate. Pivot time is separate from third-right-bar availability. | Small removable `research/levels.py`, causal/equal-extrema/delayed-availability tests. No BOS/CHOCH/OB/FVG/ICT promotion. C02's rejected retrospective packages remain unavailable. LEAN runtime/NUnit NOT RUN. |
| DriftVwapPullback `708235769c1cebc320abbdb3f064293d8b56bbec` | Ordered trend/pullback source inspected; **9 exact-source standalone selfchecks passed**. Not adopted: different market/session, no required T1 proximity/reclaim, fixed point risk/targets; platform mirror gate unpassed. | Source evidence for state/chronology, not a profitable or qualified T1 provider. Small sweep/retest comparators and their causal/test gaps are recorded in the evidence report; no framework fork added. |
| C01/C02 accepted contracts and observations | **REUSE** `SetupSnapshotV15.advance`, `FixedGeometry`, B1 `BoundedGeometry.resolve`, `scenario_net_rr`, C02 candles/universe and historical session VWAP. `EconomicsV15` remains an empty compatibility slot until real execution evidence exists. | No C01 safety contract/reference edits. Research decisions cannot instantiate approval or signed transport. Current OI/event and broad A03 limitations remain visible. |
| T1/R1/B1 composition | **BUILD** only the project-specific versioned chronological reducers, frozen evidence validation and research decision mapper: examined complete strategies do not meet the prescribed chronology, levels or ladder. | Pure functions and immutable records; no OMS/database/replay framework. R1 balance constants and all strategy/cost assumptions remain unvalidated. Replacement must pass the same causal, geometry and economic cases. |

## 10. C04 chronological replay and execution-research adapter

| Candidate | C04 assessment | Decision |
|---|---|---|
| Freqtrade 2026.9 backtesting (`1f394eaebc2f46a83d26971388628707802f8602`) | Mature candle backtest, but its strategy/dataframe callbacks do not directly preserve C03's event IDs, immutable setup snapshots, source `available_at`, complete opportunity funnel, and separate E0/E1/E2 counterfactual lifecycle. The pinned checkout was source/probe inspected for C01; its full framework runtime and backtest suite were not installed or run. | Do not adopt for C04. A C03 adapter would reimplement the chronology and still need custom portfolio/execution accounting. |
| NautilusTrader 1.231.0 (`27a8e54e7ac3c57d6cbf8891f0283dfbaee97317`) | Event-driven engine is substantive replay reuse, but adds native/Rust build and catalog/event-model integration. Binance execution adapter evidence is unrelated to the current data-blocked research panel; runtime/tests remain unrun in this repository. | Defer. The thin adapter is smaller for causal calls into the existing pure C02/C03 modules. |
| Thin AstraBot event adapter | `research/replay.py` checksum-loads retained C02 partitions, advances at declared availability times, applies point-in-time C02 scans and calls C03 evaluators while carrying each symbol's `ResearchState`. `research/simulation.py` is a separate research-only scenario/portfolio ledger with no exchange writer. | **ADOPT/WRAP existing C02/C03; BUILD the narrow event adapter.** No framework dependency added. |

The chosen path is bounded to C04's current need: deterministic chronological evaluation and inspectable NO_TRADE reasons using the project's real policy functions. C04's retained source panel is not sufficient for a strict candidate or historical fill. See [C04 report](../research/c04/REPORT.md), [machine-readable run](../research/c04/run.json), and [source inventory](../research/c04/source_inventory.json). The measured pilot is a 24-window in-memory replay; its runtime and memory are not broad-universe capacity claims. Upgrade to a maintained replay engine only if a qualified dataset benchmark shows the thin adapter is inadequate or a native engine reduces adapter code without losing prefix/state equivalence.
