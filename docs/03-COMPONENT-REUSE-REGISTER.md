# 03 — Component Reuse Register and Qualification Plan

**Rule:** `ADOPT → CONFIGURE → WRAP → SMALL PATCH → BUILD ONLY IF NECESSARY`. A linked upstream repository is a **candidate**, never a claim it passed our tests. Store exact package version/commit, golden fixture results, integration boundary, fallback, maintenance burden and removal plan in each completed adoption record.

## 1. Target components, evidence required and minimal integration

| Capability | First choice/candidates to compare | Integration pattern | Required proof before adoption | State |
|---|---|---|---|---|
| Agent coordination | [OpenBot](https://openbot.run/) with its built-in free-model access | role prompts + typed facade calls | local deployment, free-model JSON/tool-call accuracy, workflow retry/outage, bounded permissions | DESIGN / UNTESTED |
| Binance public, agent-facing skills | [Binance Skills Hub](https://github.com/binance/binance-skills-hub), CLI | import read-only skill into isolated agent environment | read-only BTC + altcoin USD-M calls, no order permissions, timeout/error behavior | CANDIDATE |
| Binance live transport | [Official USD-M modular Python SDK](https://github.com/binance/binance-connector-python/tree/master/clients/derivatives_trading_usds_futures) | adapter behind single-owner gateway | demo market/user streams, IOC/limit IDs, algo stops, restart, reconnect | DEFAULT CANDIDATE |
| Alternative single live owner | [Freqtrade](https://github.com/freqtrade/freqtrade) | adapt callbacks only if truly fail-closed | approval fail-closed, early fill protection, paired partial TP, safe stop replacement, unknown submits | COMPARE, not co-run |
| Alternative single live owner | [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | native event adapter | exact Binance one-way isolated/order support, bracket limitations, protection, replay/live semantics | COMPARE |
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
