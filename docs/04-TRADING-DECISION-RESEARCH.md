# 04 — Trading Intelligence, Data Economics and Validation Playbook

**Purpose:** make the most dangerous design area executable and falsifiable, without writing ten unrelated strategies or delegating decisions to an LLM. Original mathematical and setup contracts live in `docs/reference/AGENTIC_SPEC_v1.5.md`, §§4–8,13–14. This file defines what the coding/research tasks must deliver.

## 1. Ten analytical families (ALL retain final-product scope)

| ID | Family | Decision role | Fidelity/causality checkpoint |
|---|---|---|---|
| A01 | Order flow, footprint, CVD | Trade-aggression/absorption/failed response, execution context | Actual trade sides, continuous source coverage, reset, missing data |
| A02 | VWAP/anchored VWAP | Price location, acceptance, session/event anchor | Stable anchor ID, historical contemporaneous value, rollover |
| A03 | Structure/SMC | Swing, BOS/CHOCH, structural stop, sweep levels | Right-side confirmation, avoid full-dataset future contamination |
| A04 | Liquidity/liquidation | Depth feasibility, sweep and squeeze stress | Explicit venue observations vs estimates; sampled liquidation events |
| A05 | ICT | FVG/displacement/order-block entry geometry | Defined formation, mitigation and expiry; no retrospective zones |
| A06 | OI/funding/basis | Positioning context, cost and stress | Correct units and funding known-at time |
| A07 | Price action | Sweep/reclaim, breakout, retest chronology | Event ordering and frozen original boundary |
| A08 | Volume/market profile | POC, VAH/VAL, acceptance, targets | Trade-derived buckets vs bar approximation labeled |
| A09 | Trend/momentum | Regime eligibility, directional context | Close-bar timing; indicator warm-up |
| A10 | Mean reversion/volatility | Stable balance, volatility/veto | State persistence, trend/explosion guardrails |

All families must have a planned provider/adaptation path. An analysis family does **not** vote independently if its evidence duplicates another one. For each promoted executable strategy, specify each feature as `MANDATORY`, `VETO` or `RECORD_ONLY`. Test incremental information via ablations before making optional features authoritative. Families can remain research-only if insufficient data or no demonstrated improvement.

## 1A. Expert strategy deep-dive — mandatory before promoting *each* executable policy

Do not implement a novice indicator-combination strategy and expect success. For any T1/R1/B1 version or later strategy, study its **trading hypothesis and operational interpretation**, not merely numerical thresholds. Record: market regime and multi-timeframe narrative; setup formation and confirmation chronology; context-dependent anchors and nearby liquidity; where price acceptance/rejection, aggressive flow versus price response, OI/funding and profile add **nonduplicative** evidence; invalidation versus ordinary pullback; entry location and realistic fill conditions; obstacles and target selection; post-entry supervision, partial exits, trailing and early exit; obvious failure patterns and situations requiring `NO_TRADE`. Research each family deeply where actually used, especially A01 order flow, rather than forcing all ten into one entry checklist.

Research method: read implementation source and maintained tests for leading prebuilt projects; inspect well-documented practitioner chart walkthroughs, market case studies and trading-community critiques where specific historical times/symbols and *ex-ante* rationale are visible. Separate demonstrable market behavior from a trader's unverifiable reputation or hindsight narrative. Catalog representative normal, challenging and failed examples, not only beautiful winning charts. For every case, state what the system would be able to know **at the decision time** and whether its deterministic pipeline could identify the same *setup meaning, context, risk structure and exit reasoning*. A later screenshot alone cannot prove that contemporaneous order flow, order book or fill state was available.

Use a **two-layer qualification**: (1) **case-study/trader-level parity review**, with an explicit time-ordered diagram and discrepancies to fix; (2) **historical causal replay and net-cost evaluation** over the wider opportunity funnel. Historical annotated charts can assess qualitative sophistication without reconstructing every tick, but must never substitute for replay, cost modeling or counterexamples. A failed parity case can expose simplistic logic even when a backtest looks good; passing a handpicked chart cannot establish expectancy. Deep research on a strategy is required **when its phase arrives**, not an excuse to delay the entire project by researching every market theory simultaneously.

## 2. Data quality comes before signals

- **Universe:** Binance perpetual contract metadata/history, status, settlement, size/filter validity, sufficient age, turnover, spread, executable depth, OI and news/time vetoes. Dynamic universe includes altcoins and delisted/inactive historical instruments where known; BTC/ETH may serve as cross-market context.
- **Two-stage selection:** broad cheap market scan → bounded expensive analysis of nearer valid setup candidates (initial budget up to 15 per closed 5M cycle, operational starting choice). DO NOT LLM-call every symbol.
- **Warm state:** each `(symbol, family)` follows `COLD → WARMING → READY → DEGRADED`; changing subscription doesn't retroactively create anchored CVD/profile history. Broad cheap trade aggregation where feasible; expensive L2 only for shortlist/positions.
- **Manifest:** `source, symbol, venue contract, start/end, units, timezone, source_timestamp, available_at, interval, gaps, fidelity, checksum, correction history` for every tested data panel. Binance public historical archive first; validate record semantics.
- **Bias prevention:** replay from an expanding prefix; data appended in the future must not change any feature *emitted as known earlier*. Confirmed swing may emit later only with appropriate available_at. Historical selection cannot use survivors-only today's universe.
- **News:** verified event feed and versioned deterministic blackout rules. News cannot directly generate BUY/SELL; missing critical event coverage vetoes affected new entries.

### C02 evidence state

The C02 implementation supplies a GET-only USD-M reader, deterministic raw
replay, point-in-time Stage A gate, and a 15-symbol maximum research shortlist.
Its tested policy requires 720 contiguous closed 1H bars, 200 contiguous closed
4H bars, 21 closed 15M bars (the latest plus 20 prior), 20 closed 5M bars for
the recent-range proximity context, 60 consecutive one-minute
spread samples, fresh ticker/depth/OI observations, validated OI notional, and
an explicit event-clearance record. The numeric filters remain v1.5 research
defaults. The shortlist sorts by recent-range edge proximity, spread, turnover
and symbol only; it does not create candidates or score profitability.

C02 freshness cutoffs are metadata ≤1 hour, ticker and latest spread sample
≤60 seconds, depth ≤10 seconds, current OI ≤300 seconds, event clearance ≤1
hour, and the newest expected 5M close available no more than 10 seconds late.
The one-hour event-clearance cutoff is a provisional C02 engineering default;
the v1.5 source requires current verified event coverage but does not prescribe
this exact duration.

The Binance USDⓈ-M OI response names a current `openInterest` quantity and the
history response includes `sumOpenInterestValue`, but the published field
schema does not state a unit. The adapter preserves that raw history value and
does not set USDT notional or `unit_validated`; the scanner therefore remains
warming for this mandatory gate until a documented or numerically validated
unit mapping is supplied. The fully ready eligibility fixture uses an explicit
validated test notional and does not claim live OI qualification.

A01 smoke output is signed Binance aggregate-trade base volume with continuity
and source-window readiness. A02 is UTC-midnight VWAP from closed 5M typical
price × base volume, explicitly approximate. A03 returns `UNAVAILABLE` while
the inspected retrospective SMC sources remain unqualified for prefix
causality. The committed actual archive panel covers only BTCUSDT 1H candles
for 2024-10-28 and the first 100 APEUSDT aggregate trades on 2024-10-18. It is
parser/feature evidence, not a strategy panel, valid warm-up, liquidity
qualification, or event/news feed. C03 must still establish its own setup
chronologies and required causal structural sources.

## 3. Regime versus persistent setup

`TREND_UP`, `TREND_DOWN`, `BALANCE`, `UNKNOWN` and stress/volatility/liquidity flags are context. Breakout is a **timestamped event**, not merely a mutually exclusive market regime label. Research transition persistence/hysteresis, avoid oscillation due to repeated bar checks. Unknown required context = NO TRADE, but a persisted setup does not evaporate because a breakout label disappears on the next bar. Freeze all anchors/ATR, invalidate by **strategy-specific** clauses.

Separate state objects: market-context snapshot → setup object → proposal/armed plan → exchange trade lifecycle. Each has its own version, expiry and event IDs.

## 4. Three first executable policies: concrete event sequence

These are candidates **requiring research qualification**, not proven entries. Derive exact numeric buffers/windows from v1.5 and version them; when a rule isn't precise, implement the minimum explicit test hypothesis rather than invent an optimized collection of indicators.

### T1 — VWAP trend continuation

1. Confirm 1H trend and eligible 4H context, frozen source IDs.
2. Form pullback around the *contemporaneous* session/anchored VWAP; a reclaim version must include a prior closed 5M bar at/below VWAP, then specified 5M close back above (opposite for short).
3. Freeze 15M structural stop anchor, ATR/tick buffer, session VWAP identity and setup expiry when formed; emit `CONFIRMED` only when chronology is satisfied.
4. Entry uses explicit time-limited, adverse-price-bounded execution; no chasing beyond approved bound or retrospectively moving low/high.
5. Require a credible preconfirmed opposing target; if absent, reject or test separately versioned target policy. At VWAP session rollover, don't manufacture a thesis break.

### R1 — range-edge sweep/reclaim

1. Require empirically defined stable balance; freeze the **prior 20×1H range** before the sweep, including edge/midpoint, touch tolerance and other geometry.
2. Observe 5M wick sweep of frozen edge, then close back inside, followed by required confirmation as ordered distinct events. No looking ahead to choose favorable sweep extreme.
3. Freeze sweep stop; fail/expire on reclaim failure, setup expiry or rule veto. No re-entry from the consumed setup.
4. Targets are qualified first opposing obstacles, not automatic midpoint/opposite edge if nearer barriers intervene; reject poor net economics.

### B1 — breakout acceptance/retest

1. Freeze original breakout level, ATR/penetration tolerance and **breakout event** on confirmed close; do not require breakout-regime label to persist throughout the retest.
2. Retest must occur in the **six subsequent closed 5M bars** under frozen rules; select first qualified retest, not retrospectively best; confirmation on required next close; explicit final expiration.
3. Stop beyond frozen invalidation, with no stop widening. Test whether projected 12h horizon allows full target policy.
4. **Baseline original ladder 40% at +1 price-R, 60% at +2 price-R is RESEARCH_ONLY.** Gross 1.6 price-R; under symmetric per-unit costs `c`, `(1.6d-c)/(d+c)` meets ≥1.5 only if `c/d≤0.04`. Do not promote based on 2R label or move TP irrationally to pass a numerical gate.

### Common entry policy and levels

Use preexisting level-provider IDs; event_time/available_at; validated tick/step, adverse entry bound, expiry, frozen stop and approved target schedule. For a marketable IOC limit: long adverse cap is an **upper** limit price, short adverse cap a **lower** limit. A buy limit doesn't set a minimum favorable fill. If a favorable fill crosses structural validity, reconcile and follow safe management policy; never widen stop because the fill was surprising.

## 5. Initial economics contract (do not mix these)

| Metric | Definition |
|---|---|
| `d0_price` | Absolute weighted initial filled entry price minus original protective stop distance per base asset |
| `approved_max_risk_USDT` | Owner-approved maximum modeled exposure loss; immutable authorization ceiling |
| `initial_modeled_risk_USDT` | Modeled loss at original stop of **actual initial filled quantity** plus approved cost allowance; finalize only after initial entry is terminal; freeze thereafter |
| `cost_R` | Per-unit modeled round-trip execution cost / initial price-risk distance; separately track fees, spread, funding, slippage, adverse entry, stop tail; no double counting |
| `scenario_net_RR` | Target-ladder-success **net** proceeds / modeled initial loss, including quantity fractions and entry-bound stress; not expectancy |
| `net_R` | Actual realized net P&L (USDT) / frozen `initial_modeled_risk_USDT` |
| `expectancy` | Statistical full-policy average net_R including stops, partials, nonfills, unknown submissions, approval attrition, time exits, fees/funding |

Size using `q_raw = min(0.0025*equity, remaining_stop_risk) / (stop_distance + conservative_cost_per_unit)` and round down, then independently cap notional/leverage/free isolated margin/risk/exchange filters. Numbers are v1 ceilings not promises; projected risk can be exceeded under gaps. Minimum target-scenario net RR 1.5 from baseline; benchmark economics against actual fill/target feasibility. Do not widen stops just to make cost_R look smaller.

## 6. Selection engine and no-trade behavior

Candidate must have eligible symbol, relevant ready features, versioned executable policy, regime/context permission, confirmed setup and stop, credible target levels, acceptable complete ladder economics, event clearance, sufficient depth, portfolio slot and risk budget. Any missing mandatory dependency → `NO_TRADE` with reason. For **research-only** candidates, output analysis/report, never request real-money approval.

When qualified, rank by **strategy_version × liquidity_cohort × context** estimates with uncertainty and shrinkage for sparse symbol samples. Distinguish correlated same-market altcoin setups (market-time block inference); backtest the **entire scanner→shortlist→authorization→fill→portfolio** pipeline without seeing future outcomes. Tie-break deterministically and record nonchosen candidates.

## 7. Lean research stages and gates

**R0 Data/friction audit:** select a representative liquid-altcoin panel (diverse cohorts, past listings where possible), inventory archives/gaps, stop-size and spread distributions, B1 ladder viability, `cost_R` and setup frequency. `GO` only if enough plausible cost-adjusted candidates justify full replay; no invented profitability claim.

**R1 Event diagnostics:** causal event records, matched symbol/context/time control timestamps without triggers, signed forward moves and MAE/MFE plus actual plausible entry delays. Resample common **market-time** blocks across symbols, not independent trades. Predeclare tested horizons.

**R2 Complete policy replay:** realistic fees/funding/spread/slippage, entry/approval delay and attrition, missed/partial fills, TP ladders, stop/TP ordering uncertainty, thesis and time exits, all slot constraints and qualified registry from prior observations. Chronological dev/validation/untouched evaluation, with purged overlapping outcomes. Replay whole selector not best retrospective symbols.

**R3 Small ablations:** base setup versus optional order-flow context, profile, funding, staged exits, breakeven/trailing/early exit; add complexity only if it improves net performance and survives later evaluation. No ML required. A small calibrated meta-label model may be compared later, not entrusted with risk policy by default.

**R4 Shadow/paper, demo:** operational correctness including rejected/expired/unfilled candidates and actual observed quote/approval timing, plus 12h watchdog. A successful testnet run is **not** profitability evidence. Live pilot only after separate owner signoff.

For every replay publish: run/config/data manifest IDs; cohort/symbol breakdown; net_R, USDT P&L, costs, sample/effective sample, uncertainty intervals, fees/funding, drawdowns and tails; fill/nonfill and owner approval attrition; MFE/MAE; target before stop; duration; veto reasons; false signals; tested variants and failures. Don't relax gates after inspecting results.

## 8. Minimum unit/contract fixtures before claiming a valid strategy

- T1 past VWAP cannot change when future bars appended; VWAP session rolls at midnight without false thesis break.
- R1 swept range geometry stays frozen after hourly roll; no duplicated setup on same closed bar.
- B1 survives context label shift during retest, first qualified retest wins, expires correctly and gross ladder = 1.6 price-R.
- Swing/FVG/breakout feature created only at true `available_at`; expanding-prefix comparison and no look-ahead.
- Missing trade history → CVD `WARMING/UNAVAILABLE`, not fake zero.
- Approved worst-entry economics and all target fractions/rounded quantities are consistent.
- Whole universe/chosen portfolio replay uses point-in-time contract eligibility and never reads the future-qualified registry.

**Research stop/go:** If tested strategy economics fail, revise a *versioned hypothesis* or stop development of that policy. Do not let an unprofitable prototype justify building a complex platform first.

## 9. C03 implemented research-policy boundary

`src/astrabot/research/engine.py:evaluate` consumes C02 `SymbolData`, an explicit
synthetic/reconciled account snapshot, a versioned research cost profile and the
previous immutable `ResearchState`. It returns saved C01 setup lifecycles and
`RESEARCH_CANDIDATE` / `NO_TRADE` records. Persist the returned JSON between scans;
`CONSUMED` means one research candidate was emitted, not an order or approval.
The engine has no network, trading authorization or signed writer. A01–A10
remain in product scope; optional unavailable evidence is recorded without
becoming agreement. OI, verified events, C02 eligibility, context and fresh
post-confirmation quotes remain mandatory for these research candidates.

The context wrapper uses pinned TA-Lib, all-closed available prefixes and the
v1.5 thresholds. C02's 720 raw-hour scanner minimum is insufficient for the
ATR-percentile calculation: C03 requires **735 1H bars**. C02's 200 4H history
gate is retained by the integrated engine, although EMA50 plus three preceding
values needs only 53. ADX 20–25 is unclassified. A breakout event saves its
formation bias/ATR; the current label is not a setup-survival requirement.

The missing R1 balance definition is now the **unvalidated hypothesis**
`c03.stable-balance.hypothesis.v1`: prior 20 closed hours, excluding latest;
at least two tests of each edge separated by three bars; edge tolerance
0.15 ATR_1H; individual test-bar width at most 75% of range width; first-five
versus last-five mean-close drift at most 20% of width; width 2–8 ATR_1H and
at least ten current median absolute spreads. A latest 15M close beyond its
preceding-20 range with RVOL≥1.5 disqualifies new balance even without B1 bias
alignment. This is price geometry plus current cost width, not historical RVOL
applied to hourly bars. Full fee/stop/target economics are checked separately.
The range and qualification source references freeze before the sweep event.

Policy versions are `T1.reclaim.v1`, `R1.sweep.v1` and
`B1.original-ladder.v1`. T1 freezes the last three completed 5M pullback bars,
requires a prior own-VWAP observation in that window, and qualifies the final
bar's directional extreme within 0.25 saved ATR_15M of its own VWAP. Later
confirmation cannot move the stop. At unresolved midnight rollover (including
the 23:55 bar becoming available at 00:00), confirmation is suspended through
original expiry; the reset alone does not invalidate the structure. R1 arms
before a later closed sweep/reclaim and requires the next distinct close;
edge touch, non-reclaimed breach and a two-sided full-range violation fail.
B1 selects the first acceptable retest in six subsequent closes, enforces both
wick and close failure bounds, and permits exactly the next confirmation after
a bar-six retest. Ordinary label changes preserve saved R1/B1 setups; mandatory
data/safety vetoes remain immediate.

New T1/R1 setups expire after a **30-minute research formation window**. B1
ends after its six-bar search plus the selected retest's one confirmation.
Candidate proposals expire within 90 seconds, independently of the trigger
submission deadline of confirmation event close +10 seconds. Entry chase is
bounded by the minimum of two ticks, 0.10 frozen ATR_5M and 0.05 original
reference price-R. These clock/chase choices are versioned engineering
hypotheses, not measured operator/venue latency. BUY_MAX and SELL_MIN are the
enforceable adverse IOC limits; the other bound is a research validity guard,
not a guarantee of favorable fill price. No confirmation-candle entry is used.

Targets retain the original ladders. T1 uses the nearest formation-confirmed
opposing strict 1H swing; R1 retains its midpoint single-target screen **and**
50/50 midpoint/opposite-edge ladder; B1 retains 40/60 at +1/+2 price-R, gross
1.6. Every leg checks opposing structure known by the decision time, including
newly confirmed nearer obstacles. Saved levels, ATR and interaction candles
are checked against their source records before geometry is admitted.

Economics uses worst permitted entry, quantity-weighted exit fees, separate
ordinary/stop spread and slippage, and a conservative funding debit. Entry
spread/slippage is embedded once in the assumed adverse price. Tick/lot/
minimum filters and exact fractional leg feasibility can reduce or reject
quantity. Stop-loss stress uses the adverse bound; short notional/margin stress
uses the upper admitted price separately. Per-trade/aggregate risk, two slots,
2× notional and isolated margin cap the requested quantity. Approved risk,
actual-filled risk, realized net_R and expectancy remain absent. All profiles
and all three strategies remain **RESEARCH_ONLY**. If candidates overlap for
one symbol, the specified alphabetical strategy fallback emits only one;
there is no qualified expectancy registry yet.

Run `python scripts/c03_research.py --check --summary` for the committed
[synthetic golden trace](../research/c03/golden_trace.json). It produces a T1
candidate and a cost-stress NO_TRADE with identical geometry, not historical
profitability. [Evidence and C04 inputs](../research/c03/EXPERT_EVIDENCE.md)
separate source claims, observed smoke data, synthetic fixtures and missing
empirical qualification. C02's 124 smoke rows do not constitute a strategy study.
`python scripts/c03_research.py --c02-panel --check` also verifies the retained
actual BTC archive checksum and produces T1/R1/B1 NO_TRADE records for its
missing mandatory coverage, with an explicitly synthetic account/cost overlay.

## 10. C04 replay evidence and data blocker

C04 adds `research/replay.py`, a time-ordered adapter around the existing C02
point-in-time universe scan and C03 pure evaluator; it does not duplicate the
T1/R1/B1 policies. C03 `ResearchState` is retained per symbol between source
availability snapshots. The strict scanner emits no C03 policy evaluation
unless C02 selects the symbol. Separate diagnostics may call C03 on panel
symbols, with an empty mandatory-gate bypass list; those results never enter
strict expectancy.

The retained source sample is unchanged: BTCUSDT 1H for 2024-10-28 (24 rows)
and the first 100 APEUSDT aggregate trades for 2024-10-18. No point-in-time
instrument metadata, delisted contract history, complete 5M/15M/4H coverage,
verified event clearance, validated OI units, historical quotes/depth, funding
or fill observations are present. The archive host remains blocked by the
selected executor's restricted egress policy. C04 therefore records
`BLOCKED_BY_DATA`; R0 is `INSUFFICIENT_DATA`, R1/R3 are `NOT_TESTABLE`, and R2
has zero eligible strict symbols/candidates. This is not a policy stop or an
economic GO/REVISE decision.

`research/simulation.py` contains named E0 (no-execution truth), E1 (adverse
bounded bar-model scenario) and E2 stress mechanics for fees, partial size,
approval delay, same-bar ambiguity, gaps, target-leg rounding and the 11h55m /
12h timer. It never imports a Binance order client. OHLC-based outcomes are
`BAR_APPROX`, separated from observed fills. Synthetic E1/E2 cases verify
mechanics and are excluded from historical statistics. The declared fallback
funding proxy integrates each remaining quantity over its modeled holding
time, so partial exits reduce subsequent proxy exposure; it is not historical
settlement data. `statistics.py`
provides deterministic joint market-time-block bootstrap and pre-outcome
matched-control sampling; with no qualified historical outcomes its interval
is intentionally undefined.

Reproduce the bounded artifact with `python scripts/c04_replay.py --check`.
The exact source hashes, availability proxies, gaps and retrieval blocker are
in [C04 source inventory](../research/c04/source_inventory.json) and
[C04 research report](../research/c04/REPORT.md). A future pilot must collect a
predeclared window long enough for 735 contiguous hourly bars plus untouched
post-warm-up development/validation/evaluation blocks; no current-symbol
metadata may stand in for historical eligibility.
