# C03 expert evidence and qualification limits

Status: **RESEARCH_ONLY**. This review supports executable causal policy tests,
not profitability, a qualified fee/fill model, or trading authority. Pins and
evidence classes are machine-readable in [sources.lock.json](sources.lock.json).

## Reuse decision

The three primary comparisons were TA-Lib for conventional calculations, LEAN
for streaming structure/session semantics, and DriftVwapPullback for an actual
ordered trend/pullback policy. Reading working code was more useful than adopting
an indicator's name as a strategy. The small sweep/retest comparators below were
inspected only to test whether their existing policies could be wrapped cheaply.

| Source and exact pin | What was inspected and learned | C03 integration decision |
| --- | --- | --- |
| [TA-Lib Python 0.6.8](https://github.com/TA-Lib/ta-lib-python/tree/cbd8921c340c8ad330257ad807c2809cb557f6c5), C [0.6.4](https://github.com/TA-Lib/ta-lib/tree/43f9d5042ecc4bd367941846494ad907bf20ea50) | C `ta_ATR.c`, `ta_ADX.c`, `ta_EMA.c`; Python initializer and `tests/test_func.py`. ATR seeds mean true range, then Wilder smoothing; ADX uses Wilder directional movement/TR and ADX smoothing; EMA defaults to an SMA seed. Python tests cover NaNs, unequal lengths/types, compatibility and mutable unstable-period settings. | **WRAP** ATR14/ADX14/EMA50 over available, closed, contiguous observations. Reject nonfinite values and unexpected global compatibility/unstable settings. First finite ATR14 is index 14; ADX14 index 27; EMA50 index 49. Current plus 720 preceding finite ATR percentages needs **735 1H bars**, beyond C02's 720-bar scanner minimum. No custom replacements for these calculations. |
| [QuantConnect LEAN](https://github.com/QuantConnect/Lean/tree/f3d841e60dfd010ee5fc293ea893e56952484108) | `Indicators/PivotPointsHighLow.cs` and tests: streaming `2n+1` window, strict extrema, equal-price rejection, warm-up and per-type tests. Pivot record time is the middle bar, although emission happens only on the confirming update. `IntradayVwap.cs` and reset tests: daily typical-price volume accumulation, fill-forward exclusion, zero-volume price fallback with unready state. `DonchianChannel.cs` includes the current bar. EMA alpha and VWAP execution models were also read. | **BUILD MINIMUM v1.5 SWING**, rather than import the C#/.NET engine for a seven-bar calculation. Save pivot event time separately from third-right-close availability. Keep C02's UTC-session, missing-volume fail-closed VWAP. Exclude current bars from frozen ranges. EMA-cross insights and VWAP order scheduling do not supply T1's pullback/reclaim, stop, target or economics. No broad A03 qualification follows. |
| [DriftVwapPullback](https://github.com/jalv92/DriftVwapPullback/tree/708235769c1cebc320abbdb3f064293d8b56bbec) | `propsim/drift_vwap_pullback.py`, nine selfchecks, `research/compare_mirror.py`, README. Closed 15M VWAP/drift gates the first counter-direction 5M candle; entry is at the next open. Arming needs a state transition; tests address repeat firing, session-contained lookback, coincident closes and short geometry. | **DO NOT ADOPT POLICY**: NQ/MNQ RTH, no required VWAP touch or prior-below/later-reclaim, fixed point stops/targets. Importing its optional platform is unnecessary. Its own NinjaTrader/PropSim mirror gate is explicitly unpassed, and its reported replay results are not independently verified. Preserve the useful distinction between executable chronology and empirical qualification. |

Runtime evidence: **nine standalone Drift selfchecks passed** under NumPy 2.2.6
using the exact GitHub blob `580d3c3df368b6cbdd66b9718c781c14405b96c0` in a
credential-scrubbed subprocess. The command, SHA-256 and output are recorded in
`sources.lock.json`; no platform, mirror gate or market replay was run. LEAN's
NUnit suite and TA-Lib's upstream suite were **NOT RUN** here. AstraBot's local numerical,
causal, policy and economic regression results are recorded separately in the C03
journal/PR. Source tests read are not counted as tests passed.

The build-versus-reuse boundary is deliberately narrow: C01 economics/geometry
and `SetupSnapshotV15`, C02 observation/VWAP/provenance, and TA-Lib calculations
are reused. Versioned T1/R1/B1 reducers implement the project's specified policies
because the examined complete strategies do not have the same chronology or
immutable geometry. This is not a new general SMC engine.

## Small sweep/retest source checks

* [GoldEA](https://github.com/eamonnkennedy93-blip/GoldEA/tree/7f5ba978ab15a92e992d617f27e318dd0d859cbf):
  `session_levels.py`, `swing_structure.py`, `strategy_edge.py`, `data_fetch.py`
  and README were read. It calculates completed session levels and HTF
  sweep/reclaim signals. However extrema allow equality, confirmation time uses
  the confirming bar's index without an explicit close/availability contract,
  pending wick extremes can change, and its signal does not require C03's next
  distinct confirmation. Its eight-file root contains no test suite. The missing
  5M refinement and undistributed live EA prevent parity qualification. Claimed
  funded trading and walk-forward statistics are **NOT VERIFIED**. Not adopted.
* [break-retest-daytrader](https://github.com/Smashthehedgehog/break-retest-daytrader/tree/e1f6ec54be8e87aa3349cf0e924da8e479d32294):
  `strategy.py` and `tests/test_strategy.py` were read. Actual states preserve an
  opening range through breakout, tick touch and a volume-confirmed close; tests
  cover long/short, failed volume, once-per-day behavior and timestamp parsing.
  It couples policy to execution/database code and lacks the six-bar retest
  deadline, frozen ATR failure rule and distinct closed retest event. A tick touch
  can be followed by its enclosing bar's close. Its fixed boundary stop and
  fixed-R target do not implement B1. Tests were read, **NOT RUN**. Not adopted.

C02's Freqtrade order-flow rejection and retrospective `smart-money-concepts` /
`pyvsmc` rejection remain authoritative at their recorded pins. They were not
reinvestigated. A01 CVD is optional diagnostic evidence for this C03 baseline;
missing CVD cannot become agreement. Advanced A03 remains unavailable; the
qualified minimal swing provider does not make OB/FVG/BOS/CHOCH available.

## Practitioner cases: interpretation, not a track record

All cases below are **SOURCE/IMPLEMENTATION EVIDENCE**, with historical inputs
**NOT VERIFIED**. Publication dates are not asserted trade-event timestamps.
No underlying bars, prints, order book or fills were recovered for these cases.
Equity/ES examples are behavioral analogies, not evidence that their rules
transfer to Binance USDT perpetuals. No case is a C03 historical policy pass.

| Family / polarity | Source context | Lesson translated into a testable hypothesis |
| --- | --- | --- |
| T1 positive analogy | [SMB CLOV review, published 2021-06-29](https://www.smbtraining.com/blog/how-to-use-vwap-to-buy-a-pullback-in-a-meme-stock): relative-strength drive, lighter-volume pullback near VWAP and bids responding; later discussion distinguishes brief wicks above $18 from sustained bids. Actual session date not recovered. | A location at VWAP needs ordered evidence of response. A close above VWAP alone does not demonstrate a completed pullback or reclaim. Tape observations remain claims here; candle VWAP must not be presented as trade-exact order flow. |
| T1 negative analogy | The same CLOV review describes later steep/violent pullbacks and an attempted low-of-day catch in a downtrend as losing trades. | A familiar VWAP location does not preserve directional permission. Do not use a later low to redesign the original stop or the successful earlier trade to justify repeated attempts. |
| R1 positive analogy | [SMB ES futures 2M, 2018-05-17](https://www.smbtraining.com/blog/smb-futures-totd-5-17-18): short-term support breaks, is quickly rebid near VWAP, in a contextual uptrend. | A sweep requires breach and reclaim, followed by distinct confirmation. This example has an uptrend and does **not** establish the stable-balance permission required by C03 R1. |
| R1 negative/context-transition analogy | [Bruce Fraser, AAPL, published 2018-02-04](https://articles.stockcharts.com/article/articles-wyckoff-2018-02-aapl-pie/): distribution/UTAD interpretation; new highs fail back inside while declines have greater volatility and volume. | A rolling high/low channel is not sufficient proof of balance. Separated edge tests, controlled drift and plausible width must be frozen before a sweep. Their C03 numerical values remain research hypotheses. |
| B1 positive, conditional analogy | [Azeez Mustapha, BITSTAMP:BTCUSD daily chart, published 2024-10-27 23:18](https://www.advfn.com/newspaper/azeez-mustapha/76690/bitcoin-retests-bearish-trendline-following-breakout): a broken trendline is tested from above; continuation is conditional on holding. | Freeze the broken boundary and require later acceptance. Daily trendline commentary supplies neither Binance 15M RVOL nor the first six 5M retest bars; missing B1 inputs require NO_TRADE. |
| B1 negative analogy | [SMB ENOC, published 2016-01-26](https://www.smbtraining.com/blog/the-edge-is-not-just-in-the-chart): gap down, time below VWAP, failed breakout and fast return below; spread/tape response changes interpretation. | A visually attractive breakout can fail acceptance. Enforce the saved failure tolerance and first-retest chronology. Optional order-flow disagreement remains visible; missing flow is never invented confirmation. |

[Fraser's AAPL analysis published 2016-09-17](https://articles.stockcharts.com/article/articles-wyckoff-2016-09-an-aapl-for-your-thoughts/)
also describes a spring/test followed by substantial overhead resistance.
That is a useful target-route warning: distant projected objectives do not remove
nearer supply. C03 uses only reproducible preconfirmed level inventory, never
these discretionary chart objectives as target prices. Its staged ladder must
pass whole-plan costs; a chart's quoted gross R is insufficient.

## Evidence classes and C04 handoff

* **OBSERVED HISTORICAL FACT**: C02's retained, checksummed BTC 1H/APE trade rows
  are parser/feature observations. Their 124-row smoke panel cannot warm up this
  context engine or reconstruct the practitioner cases.
* **SOURCE/IMPLEMENTATION EVIDENCE**: the pinned code and publications above,
  with exactly the source/runtime distinction stated here and in the lock.
* **EXPLICIT RESEARCH HYPOTHESIS**: v1.5 context thresholds; C03 R1 separated
  edge-test/drift/width metric; entry and setup expiry/tolerances; conservative
  fee/slippage/funding assumptions. Chosen values are not empirically qualified.
* **SYNTHETIC TEST FIXTURE**: all C03 positive/negative chronological examples,
  including intentionally favorable low-cost B1 examples. They prove arithmetic,
  causality and lifecycle behavior, not available market edge.
* **NOT VERIFIED**: practitioner performance, complete-policy expectancy,
  historical/live fill parity, actual trade availability and production feed
  latency. B1's original 40/60 +1/+2 ladder is 1.6 gross price-R; equal modeled
  win/loss costs satisfy 1.5 net only at `c/d <= 0.04`. Do not extend targets to
  force qualification.

C04 needs a checksummed, timestamped, multi-symbol/multi-regime panel, including
delisted/listed altcoins with point-in-time eligibility. Before each evaluation,
retain at least **735 contiguous closed 1H bars**, 200 4H bars, enough 15M bars
for ATR and the preceding-20 breakout/RVOL window, and complete 5M UTC sessions
for contemporaneous VWAP, pullback and next-bar confirmation. Keep exchange
event/close time, capture/publication availability, source identity, corrections,
gaps and incomplete windows separately; preserve original setup events through
hourly/session rolls. These are minimum warm-up requirements, not sample-size
qualification.

Economic research also needs historical bid/ask and depth, trades/aggressor
mapping, venue tick/lot/min-notional filters, symbol-specific fee tier and funding
timing/rates, IOC latency/adverse-fill/partial-fill records, and stop execution
tails. Recover current OI's units and quote-notional validation, historical
event/news clearance with original publication times, and per-strategy mandatory
versus optional readiness. Treat archive close-time availability as a proxy until
capture evidence exists. The source examples need their actual event dates,
venue/contracts, adjustment/session rules and raw intraday inputs before any
causal parity claim. Predeclare cohorts, costs, untouched holdout/time blocks,
approval/unfilled/expired attrition and first-fill holding policy before measuring
full-policy results. C03 supplies policies for that study; it claims no economic
promotion or independent gate acceptance.
