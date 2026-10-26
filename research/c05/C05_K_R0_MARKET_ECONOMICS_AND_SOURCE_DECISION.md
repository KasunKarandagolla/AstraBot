# C05-K / P3-R0 — Real-market economics and source decision

Date: 2026-10-26 (Asia/Colombo). Original merged-main base:
`153d4d31c473e1f55c4ca62eaf5ad877629ea415`; branch
`codex/p3-r0-market-economics`. Programme issue:
<https://github.com/KasunKarandagolla/AstraBot/issues/18>.

P3 economic qualification remains `INSUFFICIENT_EVIDENCE`, T1/R1/B1 remain
`RESEARCH_ONLY`, and formal credit remains **45% / 55% unqualified**. This report
assesses whether to invest in empirical research; it does not certify trades,
positive expectancy or demo readiness. All A01–A10 and the v1.5 risk, approval,
single-writer and holding-time constraints remain in scope and unchanged.

## Executive R0 decision

**`R0_REVISE_RESEARCH_ROUTE`. Do not commission a paid 2024 full-policy backtest
or claim immediate R1/R2 readiness.** Prioritize a bounded, prospectively
authenticated T1 event study, subject to the concrete owner proposal below.
Retain B1 as a cost-constrained diagnostic hypothesis and R1 as data-censored.

The authentic September census spans **60,480 symbol-windows / 362,880
policy-side evaluations**, not the previous one-day example. T1 generated 434
price confirmations, but only **24** survive the declared base cost, known
obstacle and known extreme-volatility screens. Those occur on just **nine shared
market days**. B1 generated 32 confirmations: **zero** survive base costs, and
only one survives the optimistic cost/route screen. R1 cannot be measured from
this OHLCV-only input because its original balance qualification requires
observed spread evidence at every cutoff. These are not C02-approved trades.

This supports continued, tightly budgeted **T1 research**, not strategy GO. It
does not justify buying an expensive historical subscription that still lacks
authenticated filter history and event clearance. A credible raw vendor route
exists, but its required historical access, remaining truth gaps and unknown
annual total make it the wrong default investment for this sparse population.
The recommended alternative is a **210-day, seven-symbol read-only evidence
study**, with a proposed **US$350 total / US$50 monthly cap**, no paid historical
subscription, and source-contract acceptance before activation. No collector or
purchase is implemented or authorized by this report.

The programme risk reduced is now quantified: engineering can detect patterns,
but original geometry, friction and correlated sample scarcity discard most of
them before historical fill research. Source acquisition must be planned around
those survivors and the information needed to identify them, rather than around
billions of records or a larger test count.

## Authentic coverage and reproduction

The existing `/workspace/work/c04-data` tree was reused. The original loader
verified all 112 C04 archive sizes/hashes, members, schemas and continuity, and
normalized **356,454 bars**. No candle archive was re-downloaded. Manifest:
`research/c04/historical_manifest.json`, SHA-256
`6a34aae6b37ec9b48aa166dda52cd578a86776ef8b36be05aaaa5bf42f51058a`.

Research decisions use **2024-09-01 00:00 UTC inclusive through 2024-10-01
00:00 UTC exclusive**, every 5m candle availability cutoff: 8,640 per symbol.
July–August supplies source-only warm-up; no setup registry is advanced before
September. The first cutoff can see the final August close, known at September
00:00. October 1–14 remains validation; October 15–31 remains untouched. The
loader verifies the retained full-panel bytes, but the census does not evaluate
October policy events or outcomes. Active setups at the development end are
censored, not completed with validation data.

```sh
ASTRABOT_DATA_ROOT=/path/to/c04-data python scripts/c05_r0_market_economics.py
```

Outputs: [summary](C05_K_R0_SUMMARY.json) and
[full compressed census](C05_K_R0_CENSUS.json.gz). Census content hash:
`ac798c084efafeba4ee0bf61e9333fd5e50b077bed6f5de6db68d0c8d676df7f`.
Each confirmation records policy/symbol/side, original setup and stop-anchor
IDs, formation/confirmation times and regimes, confirmation source-bar ID,
absolute/percentage stop, actual original targets, nearest obstacle, all
scenario calculations and adverse-entry/stop sensitivity.

The analysis calls the unchanged `evaluate_context`, `form_setup` and
`advance_setup`, using C05-J's bounded source-history tails. It uses no fabricated
metadata, spread, depth, OI or event clearance. Original immutable numeric inputs
are memoized within this analysis process; cached and uncached context bytes,
including future-append isolation, are regression-checked. Production functions
and strategy versions are unchanged. Historical availability is C04's explicit
bar-close+1ms proxy; actual latency and a feasible post-confirmation quote remain
unknown. No C02 admission or full selector replay is claimed by this price census.

No forward return, target-hit result, profit factor or historical expectancy was
computed. Thus no overlapping economic outcomes enter another split. The
12-hour outcome purge/embargo remains required for the next event/outcome study;
it is not falsely claimed to have been tested by an R0 cost calculation.

## Complete opportunity census

| Policy | Formations | Confirmed | Invalidated | Expired | Censored at end | Confirmation days |
|---|---:|---:|---:|---:|---:|---:|
| T1 | 624 | 434 | 162 | 28 | 0 | 29 |
| R1 | 0 measurable | 0 measurable | — | — | — | unknown |
| B1 | 562 | 32 | 295 | 233 | 2 | 19 |

All counts include both sides and deduplicate original setup-event IDs. For R1,
zero is the result of the frozen detector with missing required evidence, not an
estimate of its real market frequency. `BALANCE_SPREAD_UNAVAILABLE` occurs in all
60,480 contexts; `R1_STABLE_BALANCE_UNQUALIFIED` rejects all 120,960 R1 side
attempts. Other balance reasons also occur: missing separated edge tests in
59,892 contexts, excess drift in 43,956, ATR-width violations in 1,332 and
disqualifying volume breakouts in 4,326. These memberships overlap.

| Symbol | T1 formed / confirmed | B1 formed / confirmed | R1 measurable formed / confirmed | Base T1 survivors* |
|---|---:|---:|---:|---:|
| ADAUSDT | 96 / 73 | 71 / 4 | 0 / 0 | 6 |
| BNBUSDT | 102 / 66 | 99 / 7 | 0 / 0 | 3 |
| BTCUSDT | 127 / 94 | 88 / 4 | 0 / 0 | 6 |
| DOGEUSDT | 69 / 48 | 75 / 2 | 0 / 0 | 1 |
| ETHUSDT | 74 / 50 | 74 / 4 | 0 / 0 | 3 |
| SOLUSDT | 68 / 40 | 89 / 5 | 0 / 0 | 1 |
| XRPUSDT | 88 / 63 | 66 / 6 | 0 / 0 | 4 |

*Cost + source-known obstacle + known context screens only; no strict eligibility,
quantity feasibility, quote/chase admission, fills or portfolio admission implied.
B1 has no base survivors on any symbol.

| Development dates | T1 formations / confirmations | B1 formations / confirmations |
|---|---:|---:|
| Sep 1–7 | 184 / 125 | 151 / 12 |
| Sep 8–14 | 143 / 105 | 109 / 3 |
| Sep 15–21 | 200 / 137 | 133 / 7 |
| Sep 22–28 | 86 / 59 | 138 / 6 |
| Sep 29–30 | 11 / 8 | 31 / 4 |

Formation-week grouping is by original formation date, including later
confirmation within September. T1 formations comprise 354 in TREND_UP (254
confirmed) and 270 in TREND_DOWN (180 confirmed). All 562 B1 formations occur in
BREAKOUT_EVENT context. Total context windows: TREND_UP 11,472, TREND_DOWN 8,655,
BREAKOUT_EVENT 2,073, EXTREME_VOLATILITY 1,368, UNCLASSIFIED 36,912. No observed
spread/depth exists to label actual liquidity cohorts.

Price-formation rejections include T1 context mismatch 100,821, missing prior
VWAP cross 9,756, pullback outside the original VWAP zone 8,341 and session
rollover 202. B1 has 118,318 missing aligned-breakout rejections and 258 stale
formation-event rejections. Continuations of active setups are separate from
new-formation rejection attempts; these are not sums of independent trades.

## Frozen geometry and friction capacity

Stops use the saved original extreme minus/plus **0.10 frozen 5m ATR**, as in
`decision.build_decision`, without exchange rounding. Entry is the declared
confirmation-close reference. T1 retains **40% at 1R and 60% at the nearest
formation-time opposing confirmed 1h swing**. R1 retains **50% midpoint / 50% far
edge**, with its separate midpoint net-RR screen. B1 retains **40% at 1R / 60%
at 2R**, gross 1.6 price-R. No generic 2R target is substituted.

T1's 434 confirmations include **279 invalid target orderings** (the nearest
original structural target does not extend beyond the 1R first leg) and **six
missing preconfirmed opposing targets**. Only **149** have complete, ordered
screenable geometry. All 149 have a source-known unobstructed route. Of B1's 32
screenable confirmations, **27** have known opposing-swing obstacles on at least
one target route, leaving five before costs. Absence of these known obstacles
does not establish depth, real liquidity or an executable route.

| Policy / population | Stop % p10 | Median | p90 | Min–max | Median gross price-R |
|---|---:|---:|---:|---:|---:|
| T1, all 434 confirmations | 0.14818% | 0.35568% | 0.70711% | 0.04184–1.69109% | 1.54578 across 149 complete geometries |
| B1, all 32 confirmations | 0.27270% | 0.58803% | 0.82466% | 0.09714–1.68420% | 1.60000 |
| R1 | unavailable | unavailable | unavailable | unavailable | unavailable |

Every original price-stop distance is **1 price-R by definition**; this is
distinct from fee-inclusive modelled loss. Absolute stops are in USDT per base
unit and cannot sensibly be pooled across differently priced assets:

| Symbol | Median T1 stop (USDT/unit) | Median B1 stop (USDT/unit) |
|---|---:|---:|
| ADAUSDT | 0.00156158 | 0.00249559 |
| BNBUSDT | 1.952225 | 2.500868 |
| BTCUSDT | 179.977504 | 185.968784 |
| DOGEUSDT | 0.00038055 | 0.00118396 |
| ETHUSDT | 8.502983 | 7.587230 |
| SOLUSDT | 0.767387 | 1.044844 |
| XRPUSDT | 0.00205887 | 0.00305673 |

For gross ladder reward `g*d`, equal all-in winning/losing round-trip costs `c`
and a 1.5 screen, the **symmetric diagnostic budget** is
`c/d <= (g-1.5)/2.5`. R1 must also satisfy the corresponding midpoint inequality;
use the smaller budget. T1 needs its second target beyond 1.83333R even with zero
friction. Only **80/149** complete T1 geometries have a nonnegative symmetric
budget. Negative budgets identify a free-cost structural failure, not a rebate.

| Complete geometry population | Max symmetric round-trip cost, bps of entry: p10 / median / p90 | Min / max |
|---|---:|---:|
| T1, n=149 | -6.4872 / 0.4506 / 21.3690 | -27.8523 / 68.6208 |
| B1, n=32 | 1.0908 / 2.3521 / 3.2986 | 0.3886 / 6.7368 |

B1's original ladder permits only **0.04 price-R** of symmetric total costs.
Its median 2.3521bps budget is below even 4bps of optimistic round-trip fees.
This is a whole-month structural friction finding, not the prior one-day case.

### Declared cost models and pass fractions

All assumptions were fixed before the complete census. They are hypothetical
sensitivity inputs, not published 2024 paid fees. The base 5bps fee rate matches
the existing C04 research convention. Funding is a nonnegative debit hypothesis;
no future funding credit is used to rescue a setup.

| Model | Fee per side | Additional round-trip friction, each win/loss route | Funding debit hypothesis |
|---|---:|---:|---:|
| Optimistic | 2bps | 0bps | 0bps |
| Base | 5bps | 2bps | 1bps |
| Stress | 10bps | 5bps | 3bps |

Fees use actual hypothetical entry, weighted original target prices on the
winning route, and original stop price on the loss route. The existing
`scenario_net_rr` formula is reused and tested against `evaluate_economics`.
Thus winning and losing fee costs need not be equal. Bps friction/funding is
referenced to entry notional; it is not added a second time to an observed
spread. No such observed spread is available.

| Policy/model | Cost-screen pass | After known route | After known extreme-volatility veto | Share of all confirmations | Median cost_R (complete geometry) |
|---|---:|---:|---:|---:|---:|
| T1 optimistic | 56/149 | 56 | 55 | 12.67% of 434 | 0.14486 |
| T1 base | 25/149 | 25 | 24 | 5.53% of 434 | 0.47094 |
| T1 stress | 8/149 | 8 | 8 | 1.84% of 434 | 1.01441 |
| B1 optimistic | 3/32 | 1 | 1 | 3.13% of 32 | 0.06803 |
| B1 base | 0/32 | 0 | 0 | 0% of 32 | 0.22109 |
| B1 stress | 0/32 | 0 | 0 | 0% of 32 | 0.47618 |
| R1 all models | not measurable | — | — | unknown | unknown |

The final percentage includes geometry failures in its denominator. Fractions
do not certify historical fills, venue tick/minimum-quantity feasibility, owner
approval, event clearance, two-position portfolio capacity or realized returns.
Passing a successful-ladder RR screen does not establish expectancy. The large
T1 gross-R tail also does not establish that a distant old structural target
can be reached within the unchanged 12-hour holding limit. That is a later
outcome question, not a reason to replace the target here.

### Entry, approval and stop sensitivity

Holding original absolute targets and stop fixed, adverse hypothetical entry
movement of 0 / 0.025 / 0.05 original price-R leaves **24 / 23 / 22** T1 base
cost/route/context survivors. Added stop execution loss of 0 / 0.10 / 0.25
original price-R leaves **24 / 22 / 19**. B1 has zero base survivors throughout.
These price stresses are unobserved models; the actual tick/ATR/R chase bound
may be tighter, and no admissible fill is asserted.

At unchanged reference price, an assumed zero- or five-second approval/entry
delay preserves the same cost counts as an upper bound. Fifteen- and sixty-second
delays exceed the frozen ten-second trigger submission deadline and leave
**zero timely entries**. Five-minute bars cannot identify the price, spread,
partial fill or stop execution in those seconds; no interpolation is used.

### What sample could actually be researched next?

T1's 24 base survivors occupy **nine** September market days, across all seven
symbols. Optimistic survivors occupy 16 days; stress survivors only three.
B1's single optimistic survivor is DOGEUSDT on one day. Simultaneous symbols
share market risk and are not independent samples. The strict eligible sample
remains zero; all survivor counts are ceilings before missing-data, execution
and portfolio attrition.

A 43-day untouched window at September's T1 base density would offer only about
34 diagnostic survivors on 13 active days, before further censoring—too little
to promise reliable R2 qualification. The proposed 210-day plan therefore
reserves **133 untouched days** after warm-up/development/validation. Naively
scaling September gives approximately 106 price-screen survivors on 40 active
days. **This stationarity illustration is not a forecast or a sample guarantee.**
The study stops at its horizon/cap; insufficient independent qualified blocks
remain insufficient evidence, not permission to extend or retune silently.

| Policy | R0 assessment | Next empirical use |
|---|---|---|
| T1 | Genuine patterns are frequent, but original targets eliminate 285/434 confirmations and base costs/context leave 24. Economically plausible tail; sparse, correlated survivors. | Primary frozen-policy R1 case/control hypothesis after contemporaneous evidence is accepted; full R2 still conditional on sample and execution evidence. |
| R1 | Unidentified with missing spread qualification. Neither its frequency nor its economics can be judged from zero detections here. | Measure original balance/confirmation frequency when valid quotes exist; no threshold change or fake spread. |
| B1 | Frequent formations, few confirmations, 27/32 obstructed routes, median friction capacity below optimistic round-trip fees, no base survivors. | Keep original ladder research-only; deprioritize a paid/full outcome study until defensible costs support enough unobstructed cases. No empirical STOP or ladder revision is claimed. |

## Genuine reported funding exposure

Seven small original September funding ZIPs were downloaded **once** from the
official archive, matched to their published `.CHECKSUM` files, and read to EOF:
**5,979 compressed bytes / 630 rows**, 90 records per symbol. This is a new
multi-week source fact, not repetition of the C05-I three-feed audit. Raw ZIPs
and checksum files remain outside Git in `/workspace/work/c05k-funding`.
The [funding audit](C05_K_FUNDING_AUDIT.json) records exact URLs, digests, sizes,
native `calc_time` endpoints, reported 8-hour intervals and rate distributions.
Milliseconds after an 8-hour boundary are preserved, not rounded.

| Symbol | Reported rate, bps: min / median / max | Negative records | Maximum trailing-12h sum of absolute reported rates, bps |
|---|---:|---:|---:|
| ADAUSDT | -1.1363 / 0.8175 / 1.0000 | 19 | 2.0000 |
| BNBUSDT | -3.5746 / 0 / 0.6712 | 12 | 4.3136 |
| BTCUSDT | -0.8953 / 0.17945 / 1.0000 | 30 | 2.0000 |
| DOGEUSDT | -1.7853 / 0.64945 / 1.0000 | 21 | 2.0906 |
| ETHUSDT | -0.6942 / 0.45175 / 1.0000 | 10 | 1.9734 |
| SOLUSDT | -0.8288 / 0.3324 / 1.0000 | 24 | 2.0000 |
| XRPUSDT | -1.3070 / 0.5348 / 1.0000 | 9 | 2.0000 |

Binance describes funding as a rate applied to position notional at settlement
([funding explanation](https://www.binance.com/en/support/faq/detail/360033525031)).
The absolute-rate sum is a descriptive conservative exposure illustration,
not an actual cash payment: side, settlement marks, position quantity and exact
entry/exit ordering are unknown. Archive calculation time is not proven live
receipt time. These ex-post rates are never supplied as pre-entry knowledge.
Notably, **1bps base funding and even 3bps stress funding are not universal
12-hour upper bounds** in the observed records; BNB reaches 4.3136bps of absolute
rate exposure. Models remain labelled hypotheses rather than being optimized
after this check. Actual R2 funding must use authenticated settlement timing,
mark notional and remaining quantity-time.

With local funding ZIPs plus their published checksum files, the same command
also reproduces the separate funding audit:

```sh
ASTRABOT_DATA_ROOT=/path/to/c04-data python scripts/c05_r0_market_economics.py --funding-root /path/to/september-funding
```

No download code is included in the research command. The exact seven source
URLs are in the audit; the funding function can also be called independently on
those retained files without repeating the price census.

## Source feasibility: what was actually established

The authoritative materials below were inspected through the connected web
research service on 2026-10-26. They establish current provider documentation,
not authenticated 2024 instrument facts. No failed Tardis/Binance network probe
was repeated, no new archive downloader was built, and no purchase, subscription,
collector or exchange/account action was initiated.

| Requirement | Authentic retained evidence | Credible additional source | Unclosed boundary |
|---|---|---|---|
| 5m/15m/1h/4h candles | C04: 112 checksummed ZIPs, 356,454 bars, July–October 2024; the existing local bytes are reused | [Binance public-data guide](https://github.com/binance/binance-public-data#data-information) documents public daily/monthly kline/trade archives | Bar close+1ms remains an availability proxy. A fixed seven-symbol panel does not reconstruct the historical exchange universe. |
| Lifecycle, filters, contract size | No qualifying historical H assertions | [Tardis instrument metadata](https://docs.tardis.dev/api/instruments-metadata-api) provides lifecycle and filter fields; current `changes` documentation guarantees completeness only for contract-multiplier changes | Other historical filters are best effort; current `active` and provider availability are not historical trading status. Require dated source extracts and complete effective intervals. No paid metadata response was inspected. |
| Quotes and spread readiness | Owner-host C05-I/G one-day SOL quote stream; no September quote files in this executor | [Tardis native replay channels](https://docs.tardis.dev/historical-data-details/binance-futures) include `bookTicker` and L2 | Coverage is documented, not authenticated for all seven symbols/dates. Issue #22's raw-event versus periodic-sample clock mismatch remains open; no production C02 change here. |
| Depth units and quality | Owner-host reconstructed top-25 sample; historical unit assertions unverified | [CSV schemas](https://docs.tardis.dev/downloadable-csv-files/data-types) document source-native amounts and reconstructed top-25 snapshots, including removal of crossed levels | Quantity mapping, contract multiplier, band completeness, disconnects and sequencing need evidence. Visible L2 cannot certify an IOC fill or queue position. |
| OI units, measurement and mark timing | Raw derivative CSV values; no field-specific historical H timing proof | Provider documents a separate raw `openInterest` channel from REST polling approximately every six seconds; raw mark stream is separate ([collection details](https://docs.tardis.dev/historical-data-details/binance-futures)) | A ticker-row clock is not every field's measurement clock. Obtain original OI response `time`, arrival and separate mark update; verify units and valuation alignment. Current Binance docs call `time` transaction time, without establishing the requested 2024 measurement semantics. |
| 24h ticker / universe inputs | Kline quote-volume sums are only a rolling-bar turnover proxy | Provider raw `ticker` and `!contractInfo` channels are documented; `!contractInfo` collection is listed since 2023-07-24 | Those channels are absent from the three normalized C05-I CSV types. Need per-date channel coverage, status/filter history and inactive/delisted universe membership. |
| Event/news blackout | No complete point-in-time clearance ledger | [Federal Reserve calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm), [BLS releases](https://www.bls.gov/schedule/news_release/), exchange/project/security notices | Public calendars cover named scheduled events, not all crypto/security news. Retain original publication, receipt, revisions, symbol mapping and explicit coverage. Absence of an article does not establish CLEAR. |
| Funding settlements | C05 derivative ticker contains next-event indications, not verified settlements | Binance funding-history/archive route already identified in C05 feasibility; original rate records plus aligned marks and position quantity would support outcome costs | Seven September funding ZIPs and their published checksums were inspected: 630 reported calculation records; see the funding audit below. Current provider `fundingRate` raw channel is documented only from 2026-10-16, so cannot supply a 2024 recording. A predicted/last-indicative rate cannot replace settlement. |
| Fees and fills | Existing research assumptions only; no historical account executions | [Binance fee page](https://www.binance.com/en/fee/futureFee) and independently documented fee tier; public quotes/trades permit bounded market-impact modelling | The inspected fee page rendered no rate records. No 2024 paid-fee schedule or actual IOC/stop/partial-fill behaviour established. Costs in this study remain declared models. No orders are needed or authorized for R0. |

[Binance's current OI history documentation](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics)
limits the endpoint to the latest month. It cannot recover September 2024 in
October 2026. The current public-data guide confirms free downloads and
checksums/corrections for documented datasets; it does not establish complete
historical filters, event clearance, local receipt times or execution records.
Earlier HEAD-only object checks in `DATA_FEASIBILITY.md` remain HEAD-only evidence
and were not repeated or promoted into inspected datasets.

### Path A — public retrospective archives

**Keep as the candle and outcome-cost supplement; reject as the complete source
route.** The already retained C04 inputs solve price chronology and warm-up at
zero incremental download cost. Trade/funding archives may support further
research after payload verification. They do not supply the complete mandatory
historical state. Code in a public repository does not grant blanket rights to
redistribute exchange data; keep raw inputs outside Git and review applicable
exchange terms before any expanded access or external publication.

### Path B — specialist retrospective provider

This is a technically credible **candidate**, not an authenticated complete
dataset. [Provider documentation](https://docs.tardis.dev/historical-data-details/binance-futures)
lists Binance USD-M history from 2019-11-17, OI from May 2020, native ticker,
book, mark and OI channels, plus contract-info updates since July 2023. Per-symbol
2024 raw channel coverage, incidents and artefacts still need inspection.
The metadata API's filter-history limitations are material even if access is
purchased. The three normalized CSV types alone are not sufficient.

The [published pricing page](https://tardis.dev/#pricing) displayed Perpetuals
Solo **US$700/month**, Professional **US$1,000/month**, Business **US$3,000/month**.
These are displayed monthly prices, **not an authenticated yearly checkout
quote**, tax total or promise that a short subscription opens 2024 history.
[Current subscription terms](https://docs.tardis.dev/faq/billing-and-subscriptions)
give four months of history for monthly billing, twelve months for quarterly,
and four years for yearly. Professional/Business add raw replay and metadata;
Solo is CSV-only. Thus a new standard subscription covering 2024 now requires
yearly access. Actual annual charge/tax and owner eligibility remain unknown.
The current free trial covers days 1–10 of the preceding calendar month with
20GB transfer; it cannot be selected for 2024. First-of-month free samples do not
make a continuous representative month. No subscription was started.

[Transfer limits](https://docs.tardis.dev/api/rate-limits) are 20TB monthly /
240TB yearly for Solo/Professional; raw Professional request limit is 3,000/min.
These limits exceed the simple three-feed volume illustration below, but full
native L2/channel volume is unmeasured. [Current licence clauses 9.1–9.6](https://docs.tardis.dev/legal/terms-of-service)
permit internal research and specified processing, restrict sharing raw or
manipulated data beyond authorized users, and separately permit certain derived
reports. Lawful sample access does not permit uploading raw datasets to public
GitHub. The owner must approve the exact plan, permitted users/storage and total
charge before procurement; none is authorized here.

### Path C — bounded prospective evidence proposal

Prospective capture can retain instrument/filter revisions, field-specific OI
responses, source/arrival clocks, raw books and event-feed coverage as they are
observed. It avoids trying to infer 2024 state from today's API. It still needs
source-unit substantiation, a reviewed periodic spread interpretation and an
event coverage contract; simply running a recorder does not solve these.

**Proposed scope, requiring owner approval:** the same seven symbols, one
read-only host, 210 consecutive UTC days after acceptance: 35 source-only
warm-up days, 28 development/event-research days, 14 validation days and 133
untouched evaluation days. Original 2024 splits remain frozen. Purge every
event whose declared maximum outcome horizon crosses a split, and apply the
12-hour embargo before the following split; do not shorten the holding horizon
after seeing results. Freeze event horizons and matching rules before outcomes.
This is a proposed future study, not a collector implemented in this PR.

Required observations: hourly/version-on-change full exchange metadata, native
24h ticker, source BBO plus designated minute sample endpoints, sequenced L2 and
initial snapshots, OI original responses and per-field measurement/receipt
clocks, mark/index updates, actual funding settlements, candles and provenance,
and source-backed news/calendar coverage with explicit UNKNOWN gaps. Preserve
native sequence/gap/reset records; a mandatory source outage censors the window.
Public order-book data supports conservative fill/impact bounds, not observed
AstraBot fills. Actual execution calibration remains a later separately
authorized gate; this proposal includes no orders or account credentials.

| Planning illustration | Symbol-days | Three-feed compressed bytes | Rows |
|---|---:|---:|---:|
| Seven symbols × September's 30 days | 210 | 23.27GB | 568,582,560 |
| Seven symbols × September–October's 61 days | 427 | 47.31GB | 1,156,117,872 |
| Seven symbols × proposed 210 days | 1,470 | 162.86GB | 3,980,077,920 |

These are **linear extrapolations, not measured seven-symbol sizes**: C05-I/G
SOL 2024-10-01 had 110,788,433 compressed bytes and 2,707,536 rows across the
three original feeds. Native L2, trades, other symbols and volatility can differ
substantially; normalized snapshots can be much larger than incremental feeds.
Propose a **250GB compressed research-data cap**, separate backup capacity and
at least 500GB working/storage allocation; stop and censor if the cap or source
continuity budget is exceeded. Do not silently expand retention. Stream daily
compressed partitions instead of loading billions of rows into RAM.

Runtime/storage/cloud charges are **not quoted**: no host or paid infrastructure
was selected or provisioned. Proposed approval ceiling: **US$50/month and US$350
total for the 210-day study**, including runtime and backup, with **US$0 paid
historical subscriptions**. These are proposed spending limits, not vendor
prices. The owner must name a permitted continuously available host and operator,
approve an actual quote within those limits (or an existing host with sufficient
capacity), and accept retention/deletion terms. If no acceptable host fits the
cap, do not activate or silently raise it.
The first 72 hours should measure actual volume, CPU, lag and loss against that
already approved cap; failure stops the study rather than creating a new source
or topology. All endpoints remain unauthenticated/read-only. An unavailable or
geographically restricted source must not be bypassed.

Before activation, the lead must accept source-supported field/unit/measurement
and news-coverage contracts, rather than infer them from captured values, and decide
[issue #22](https://github.com/KasunKarandagolla/AstraBot/issues/22)
explicitly. No prospective archive can manufacture C02's exact raw-event minute
spacing from irregular native ticks; any approved interpretation must preserve
the original clocks and thresholds and be separately versioned/reviewed. If
measurement semantics or event coverage cannot be substantiated, **stop this
source route before deployment**. Neither a recorder nor a paid feed can certify
unknown semantics by accumulating more rows. This is a time-bounded investment
decision with explicit exit conditions, not an instruction to keep rebuilding
the six evidence checks.

## Programme boundary

No strategy or C02 threshold is changed. No C06 work, C07 implementation, demo
activation, order submission, credential use, subscription or persistent
collection occurs in this milestone. Independent lead review of the R0 evidence
and the proposed investment is required before a new empirical study starts.

The concrete owner decision is whether to approve the 210-day scope, US$350
total cap, named host/operator and storage/backup allocation above, conditional
on source-contract acceptance. Approval of this research report alone does not
activate collection or spending. If those conditions cannot be met, record a
blocked investment rather than proceeding with incomplete eligibility.

| Remaining milestone | Required evidence before advancement |
|---|---|
| R0 acceptance | Independent review of this census, conditional costs and source decision; no economic qualification credit. |
| Source acceptance | Historical/contemporaneous lifecycle and filters; valid periodic spread readiness; depth quantities and usable bands; field-specific OI units/measurement and aligned marks; genuine ticker/universe inputs; verified event coverage. Missing mandatory facts remain vetoes. |
| R1 causal event research | Preregistered frozen-policy events, matched controls and horizons; representative C02-approved population, complete missingness accounting, chronological splits and 12h purge/embargo. Report dependence and uncertainty; diagnostic counts cannot substitute for eligible events. |
| R2 complete-policy backtest | Unchanged entries/stops/ladders, quantity and portfolio constraints, fees/funding and conservative fill/stop evidence, approval latency, earliest first-fill +11h55m flatten attempt and 12h hard boundary; independent untouched evaluation with adequate effective sample and uncertainty. |
| P3 qualification | Independent acceptance of the existing statistical/economic gates on qualified R1/R2 evidence. No positive-expectancy, strategy GO, demo or phase-credit promotion from this R0 report. |

## Acceptance and delivery

The complete September census was run once on the authentic pinned panel; a
bounded two-hour source run preceded it. All 1,186 formation records and 466
confirmations are retained, including rejected geometries. Native frozen
numeric functions are called through bounded immutable-input memoization; no
threshold or indicator formula was rewritten. All recorded stops are positive;
the explicit nonpositive-stop guard does not alter this population.

Validation: **six focused checks passed**, covering all three original target
definitions, fee-route equality with existing economics, R1's independent
midpoint veto, cached/native context identity and future-append causality, and
native funding clocks / absolute exposure without invented position payments.
Full repository regression: **320 passed in 176.11s**. Compilation, dependency
integrity and diff checks passed. Production C02, C03 policies/context/levels,
economics, simulation, risk contracts and C06 sources are unchanged. Final-head
GitHub CI and exact publication hashes are reported separately after push.

No C05-I report/original Windows gzip bytes were present in this executor. Its
completion is taken from the owner's assignment; the earlier G/H/J reports were
read as existing evidence, not re-presented as a fresh original-feed run. Two
parallel assistants supplied initial method observations, but service usage
limits stopped their work before code delivery; the complete quantitative and
source work was performed directly in this session. No model/quota estimate is
invented.

Implementation and report form one cohesive PR against the original base above.
Independent engineering-lead review is required; no self-merge or economic gate
promotion follows from these tests.
