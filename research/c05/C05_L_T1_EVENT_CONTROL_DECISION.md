# C05-L — T1 historical event/control investment decision

Date: 2026-10-26 (Asia/Colombo). Merged base: `0d5b45c4ccdadd782f9b4f42f290f35faf445a60`. Programme [#18](https://github.com/KasunKarandagolla/AstraBot/issues/18); source-clock [#22](https://github.com/KasunKarandagolla/AstraBot/issues/22).

## Decision and immediate investment consequence

**`T1_INDETERMINATE`. Do not approve the proposed 210-day / US$350 evidence study on the strength of C05-K’s successful-ladder arithmetic. Pause that proposal for independent lead review of these actual paths.**

The price-path finding substantially weakens the investment case: **all 24 frozen base survivors touch their original stops within 12 hours; zero reach the original second structural target before the stop**, under both strict earlier-candle and favorable same-candle bounds. Twenty never touch target 2 at all within 12 hours; four touch it only after a prior stop. Six touch the first 1R level strictly before the stop; one additional case has unresolved first-target/stop ordering. These are candle observations, never executed trades, a win rate or realized economics.

The preregistered compound WEAK_REVISE rule also required a nonpositive 12h equal-day matched signed-move difference. It is **+3.88bps**, from only 11 matched survivors on five event days, and changes sign on day deletion (−38.16 to +40.56bps). Therefore that rule is not met; we retain INDETERMINATE rather than changing the rule after seeing outcomes. The conditional-justification rule fails decisively: no original full ladder precedes the stop and the 1h/4h comparisons are negative. This does not justify declaring the strategy unprofitable or spending months to acquire execution evidence for an established edge.

**One next programme action:** independently review this C05-L packet and decline/defer activation of the existing 210-day proposal pending that review. Do not start collection, buy data, alter the ladder, or consume the untouched October evaluation to rescue these results. P3 remains `INSUFFICIENT_EVIDENCE`; T1/R1/B1 remain `RESEARCH_ONLY`; formal phase credit stays **45% / 55% unqualified**.

## Preregistration, source truth and scope

- The [preregistration](C05_L_PREREGISTRATION.md) was committed locally as `b5684e0` at 2026-10-26 16:30:16 UTC, before loading forward candles or calculating outcomes. This is a recorded exploratory plan, not an independently timestamped public preregistration or confirmatory study. Membership, matching, horizons and verdict rules were not tuned after outcomes.
- The fresh executor had no `/workspace/work/c04-data` tree. Existing authenticated reports/census identify setups and source hashes but do not retain the necessary chronological future OHLC prices. Restored **84** already-pinned July–September public archives once, outside Git: **11,566,262 bytes**, verified original ZIP/member SHA-256, sizes, schemas, row counts and continuity through the existing C04 loader. **266,616** native bars were normalized. No new downloader is shipped.
- The 28 October monthly archives were neither downloaded nor opened for this study. A small optional monthly source bound on the existing loader leaves those bytes unopened while checking the complete frozen manifest structure. Its default full-panel behavior is unchanged. Existing CI checks of old tiny fixtures/retained samples are regression checks, not inspection of October panel returns.
- C04 manifest SHA-256: `6a34aae6b37ec9b48aa166dda52cd578a86776ef8b36be05aaaa5bf42f51058a`. C05-K census content hash: `ac798c084efafeba4ee0bf61e9333fd5e50b077bed6f5de6db68d0c8d676df7f`. Source partitions retain original C04 provenance/retrieval metadata; this session restored identical bytes on October 26, not new contemporaneous receipt evidence.
- Same seven symbols: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, ADAUSDT, DOGEUSDT. July–August supplies context only. September decision cutoffs are `[2024-09-01 00:00, 2024-10-01 00:00)` UTC, all 60,480 symbol-windows. No October returns enter events, controls, matching or uncertainty.
- All **624** original T1 histories were replayed through unchanged C03 formation/advancement: 434 confirmed, 162 invalidated, 28 expired. Formation IDs, frozen snapshots, chronological state transitions, terminal times/reasons, anchors and source records are retained. All 434 confirmation geometries and source-bar identities reproduce C05-K exactly. The original 24-case membership remains fixed.
- A close is available at native inclusive close time +1ms, an explicit historical proxy. It is a hypothetical observation reference, not an IOC fill within 10 seconds. Forward candles begin at that availability cutoff and exclude the confirmation candle. MFE/MAE describe the entire subsequent path even after a hypothetical stop; favorable later movements do not rehabilitate a stopped setup.
- Fixed horizons: 15m, 1h, 4h, 12h. Horizons crossing the development boundary are censored, and full-12h comparisons purge those decisions. In this actual cohort **all 434 confirmations have complete horizons; zero are split-censored**. Pool timestamps in the last 12h are ineligible controls (1,001 symbol-windows). Original split, 12h embargo, 11h55 flatten-attempt and hard 12h contracts are preserved. This diagnostic cannot establish execution at the flatten boundary.

## Cohort funnel and rejected populations

| Original confirmation classification | Cases |
|---|---:|
| `BASE_COST_REJECTED` | 124 |
| `FROZEN_BASE_SURVIVOR` | 24 |
| `KNOWN_CONTEXT_REJECTED` | 1 |
| `PRECONFIRMED_OPPOSING_TARGET_MISSING` | 6 |
| `TARGET_ORDER_INVALID` | 279 |

The 149 screenable geometries have ordered 40% at 1R / 60% at the original preconfirmed opposing swing and source-known unobstructed routes; 124 fail base cost, one further case fails known context, and 24 survive. There are zero route-rejected T1 geometries in this census. All 279 target-order failures and six missing-target confirmations remain in the event evidence and receive signed forward paths; no invalid geometry is promoted to a ladder.

| Fixed population | Cases | 12h full ladder lower–upper | 12h median signed move (bps) | Median 12h MFE / MAE (price-R) |
|---|---:|---:|---:|---:|
| All original confirmations | 434 | 49–50 | -18.41 | 3.49 / -3.25 |
| Original screenable geometry | 149 | 49–50 | -43.29 | 3.04 / -5.12 |
| Frozen base survivors | 24 | 0–0 | -52.41 | 0.85 / -4.46 |

The full cohort is context, not an alternative policy selected after results. Cost-screened survivors are economically attractive *conditional on completing distant targets*: their median second-target distance is **6.79 original price-R** (range 2.95–22.91R). The 24 comprise 17 LONG / TREND_UP and seven SHORT / TREND_DOWN confirmations. Every symbol is represented; neither simultaneous symbols nor repeated setups on the same move are independent.

## Actual survivor paths and ordering bounds

| Horizon | Complete / censored | Median signed close (bps) | Median MFE / MAE (R) | First target strictly before stop | First-target same-bar ambiguity | Full ladder lower–upper | Second target not touched |
|---|---:|---:|---:|---:|---:|---:|---:|
| 15m | 24 / 0 | -4.76 | 0.48 / -0.53 | 3 | 1 | 0–0 | 24 |
| 1h | 24 / 0 | -18.65 | 0.65 / -1.51 | 5 | 1 | 0–0 | 24 |
| 4h | 24 / 0 | -61.66 | 0.75 / -3.23 | 6 | 1 | 0–0 | 23 |
| 12h | 24 / 0 | -52.41 | 0.85 / -4.46 | 6 | 1 | 0–0 | 20 |

Lower means the target first appears in an earlier candle than the first stop; upper additionally allows both in the same candle. Touch timestamps are **five-minute intervals**, with source bar open/availability and lower/upper elapsed minutes retained. No intrabar path or price interpolation is invented. There is no second-target/stop same-bar ambiguity among the 24, so changing that assumption cannot restore a completed ladder. The first-target bound is 6–7 of 24, a price-touch count with no fill assertion. No full ladder precedes the 11h55 flatten-attempt boundary either.

C03 has armed-setup invalidation/expiry, reproduced above, but no separate frozen post-entry thesis-exit function; optional management is explicitly disabled. Applying `advance_t1` to an already confirmed position would invent a policy. Post-entry thesis invalidation is therefore **not estimable** here. The 12h close is a bounded observation, not a proven expiry fill.

## Causal matched controls and uncertainty

The full pool retains **60,480** timestamps, including **57,639** eligible non-triggers. Exclusions: 1,840 current armed/forming/terminal T1 setup cutoffs and 1,001 cutoffs crossing the full-12h split boundary. Their membership reasons, regime, ATR percentile, session, context ID, original source-bar ID and close are retained. Fresh T1 formations are explicitly screened with the frozen functions; no additional pool exclusions arose in that check.

Control selection precedes every forward-outcome calculation and reuses `statistics.matched_controls`, seed 20261026. Match exact symbol, direction, confirmation regime, causal ATR-percentile quartile and four-hour UTC session; require a September timestamp 12 hours to seven days earlier. No outcome matching, future-setup exclusion or relaxed fallback. Later setups may arise within a control’s future path: excluding them would use hindsight. Sampling is with replacement and all reuse/overlap is retained. Control R uses its own close times the event’s original stop fraction; this is a normalization, not a control strategy or transplanted executable order. Percentage/bps results are reported alongside R.

Of 434 cases, **174 match** to **161 distinct controls** (22 case days). Of the 24 survivors, **11 match** to **11 distinct controls** on **five event days**; their controls occupy six different historical days. The other **13 survivors have no exact past control**. No matched survivor is ETH, SOL or DOGE; the available subset is ADA, BNB, BTC and XRP. Early-month and unusual-context cases lack comparable prior history. This attrition can bias the matched subset; no extrapolation to all 24 is justified.

| Horizon | Pairs / event days | Equal-day case−control signed move (bps) | Day-deletion range (bps) | Matched case / control median signed move (bps) | Matched case / control median MFE (R) | Matched case / control median MAE (R) |
|---|---:|---:|---:|---:|---:|---:|
| 15m | 11 / 5 | -24.45 | -34.89 to -11.92 | -14.74 / 0.00 | 0.79 / 0.90 | -1.31 / -0.60 |
| 1h | 11 / 5 | -67.14 | -84.55 to -43.06 | -45.77 / 29.29 | 1.19 / 1.80 | -2.23 / -0.99 |
| 4h | 11 / 5 | -29.11 | -63.47 to 7.57 | -43.97 / 22.37 | 1.66 / 3.42 | -3.23 / -1.81 |
| 12h | 11 / 5 | 3.88 | -38.16 to 40.56 | -27.00 / 62.61 | 1.66 / 5.69 | -4.18 / -4.62 |

Equal-day paired differences first average within shared UTC **event day across symbols**, then average those day means. They are not the difference between pooled medians. Controls lie on earlier days and can overlap other events/controls; neither day weighting nor matching removes that dependence. The five 12h day means are +147.65, +172.04, −101.01, −142.83 and −56.44bps on September 6, 19, 24, 25 and 27 respectively. One favorable day’s removal reverses the tiny +3.88bps overall mean. Large positive 12h moves in September 6 XRP and September 19 BTC occur **after** their original stops.

The 24 survivors span **nine market days**, with counts 1,6,3,1,3,4,3,2,1. Kish concentration across those day weights is **6.70**; this describes concentration, not a proof of that many independent observations. There are **48 overlapping case/control interval pairs** and **11 temporal overlap components**, including controls on earlier days. Components are descriptive connected time intervals, not independent paired samples. The broad 434-case cohort occupies 29 market days. The predeclared minimum of 30 market days and 30 nonoverlapping shared-market components is not met: **no bootstrap CI, p-value or reliable-advantage claim is reported**. Day-deletion ranges are descriptive sensitivity, not confidence intervals.

## All 24 frozen cases

Times below are UTC confirmation cutoffs. “T1 first” is strict (`yes`), same-bar unresolved (`amb`) or not before stop (`no`). “T2” is never observed (`none`) or observed only after an earlier stop (`after stop`). Every case has a stop touch; complete chronological source-linked records are in the compressed evidence. ID prefixes locate the full immutable IDs in JSON.

| Event ID prefix | Confirmation UTC | Symbol / side | Original target 2 (R) | T1 first | T2 within 12h | Signed 12h (bps) | Matched control UTC |
|---|---|---|---:|---|---|---:|---|
| `17b5961f9e` | 2024-09-06 12:30 | XRPUSDT SHORT | 9.75 | amb | after stop | 306.63 | 2024-09-05 13:55 |
| `f2ac295fdf` | 2024-09-07 01:10 | BTCUSDT SHORT | 10.69 | yes | none | -119.94 | unmatched |
| `3744cfeebd` | 2024-09-07 01:10 | SOLUSDT SHORT | 3.28 | no | none | -218.85 | unmatched |
| `c16b3d406b` | 2024-09-07 01:40 | XRPUSDT SHORT | 8.06 | no | none | -166.86 | unmatched |
| `1e662f57da` | 2024-09-07 01:50 | XRPUSDT SHORT | 5.51 | no | none | -178.95 | unmatched |
| `c516ccd457` | 2024-09-07 02:45 | BTCUSDT SHORT | 22.91 | yes | none | -112.55 | unmatched |
| `d644f3eaf5` | 2024-09-07 02:55 | BTCUSDT SHORT | 9.00 | no | none | -157.33 | unmatched |
| `0d419b4ea2` | 2024-09-14 03:25 | ETHUSDT LONG | 5.46 | no | none | -52.94 | unmatched |
| `c75bfb8ef8` | 2024-09-14 03:40 | ETHUSDT LONG | 12.75 | no | none | -51.87 | unmatched |
| `92422bf006` | 2024-09-14 03:50 | ETHUSDT LONG | 8.93 | no | none | -67.65 | unmatched |
| `db4ee3b161` | 2024-09-19 22:25 | BTCUSDT LONG | 9.15 | no | after stop | 124.15 | 2024-09-13 21:45 |
| `0969ff1a8e` | 2024-09-24 00:20 | BNBUSDT LONG | 5.24 | no | none | -24.23 | 2024-09-19 03:45 |
| `63e47436d4` | 2024-09-24 00:30 | BNBUSDT LONG | 4.13 | no | none | -27.00 | 2024-09-19 03:55 |
| `bcba530260` | 2024-09-24 03:55 | BNBUSDT LONG | 2.95 | no | none | 13.02 | unmatched |
| `f87ae13fe4` | 2024-09-25 14:35 | ADAUSDT LONG | 13.25 | yes | none | -38.89 | 2024-09-20 13:10 |
| `4bbdd930aa` | 2024-09-25 15:00 | ADAUSDT LONG | 8.75 | yes | none | -33.70 | 2024-09-20 15:35 |
| `18bfc8be3e` | 2024-09-25 15:10 | ADAUSDT LONG | 3.37 | no | none | -46.56 | 2024-09-24 12:25 |
| `d9a4474dfd` | 2024-09-25 16:30 | ADAUSDT LONG | 3.61 | no | none | -25.88 | 2024-09-20 19:30 |
| `53e05517ee` | 2024-09-27 00:45 | BTCUSDT LONG | 4.20 | yes | after stop | 89.58 | 2024-09-20 03:35 |
| `4862ea767f` | 2024-09-27 15:20 | ADAUSDT LONG | 11.75 | no | none | -68.80 | 2024-09-25 12:55 |
| `ea64777996` | 2024-09-27 17:05 | ADAUSDT LONG | 3.82 | no | none | -98.35 | 2024-09-24 17:30 |
| `6842ef1c12` | 2024-09-28 00:55 | DOGEUSDT LONG | 2.97 | yes | none | -63.55 | unmatched |
| `ec007252dc` | 2024-09-28 04:55 | BTCUSDT LONG | 16.67 | no | none | -77.98 | unmatched |
| `ee80ca7c6a` | 2024-09-29 00:20 | XRPUSDT LONG | 3.11 | no | after stop | 157.57 | unmatched |

## Failure cases, favorable later prices and model sensitivity

- **BTC LONG, September 19 22:25, `db4ee3b161`:** original stop is touched in the very first forward 22:25–22:30 candle. The 1R level appears in the next candle and the structural target only at September 20 03:00–03:05. The 12h close is +124.15bps and MFE 27.57R, both after the initial stop. Calling this a successful strategy outcome would reverse chronology.
- **XRP SHORT, September 6 12:30, `17b5961f9e`:** first target and stop appear together at 12:30–12:35, so 40% first-leg ordering is unresolved. The second target appears only at 14:05–14:10, after that stop candle. Its +306.63bps signed 12h move and 59.52R MFE do not establish a completed ladder.
- **ADA LONG, September 25 14:35, `f87ae13fe4`:** the 1R level appears at 14:35–14:40, stop at 14:45–14:50, and structural target is never observed. This demonstrates why observing the first leg cannot validate the original 60% structural leg.
- **BTC LONG, September 28 04:55, `ec007252dc`:** the original structural target is 16.67R away, while 12h MFE is 0.28R and MAE −22.51R. The first stop appears at 05:05–05:10. The attractive conditional cost ratio gives no evidence that the distant target is practically reached.

No trade expectancy, net realized-R, profit factor or executable win rate is constructed. Original optimistic/base/stress scenarios remain frozen at 2/5/10bps fees per side, 0/2/5bps additional round-trip friction and 0/1/3bps assumed funding debit. Among the 24, their median modeled **loss-route cost drag** is 0.1591 / 0.5169 / 1.1132 original price-R, while median 12h MFE is only 0.8548R. This is conditional cost arithmetic versus an observational path statistic, not a subtraction that creates net performance. Friction cannot restore a target never reached before the stop.

Hypothetical adverse entries 0/.025/.05 original-R retain fixed absolute stop/targets and leave the original C05-K counts 24/23/22 under the base screen; these sensitivity subsets never replace the original 24. Actual next-bar open and five-minute-close deviations are retained per event. The open is not a proven post-confirmation quote, and the five-minute close is already beyond the submission deadline. Candles cannot identify a 0/5/10-second feasible price, depth, fill fraction or stop execution. At 15/60 seconds the frozen ten-second deadline has expired; no timely entry can be asserted.

The retained C05-K funding audit supplies ex-post September aggregate rates only; raw settlement records are absent in this fresh executor and were not downloaded again. The existing seven-symbol reported maximum trailing-12h absolute-rate sums (up to BNB 4.3136bps) are retained per event as an additional **aggregate ex-post stress divided by original stop fraction**. They are not event-specific settlement exposure, forecasts, pre-entry signals or actual position cash flows. The original 0/1/3bps scenario hypotheses are unchanged.

## What would change the recommendation; remaining evidence

The current month does not support conditional study justification. A different recommendation would require independently specified additional authentic evidence showing that this **same** frozen ladder reaches the second target before the original stop within the holding scope, and positive matched 1h/4h/12h comparisons that survive day deletion and conservative ordering on sufficient separate market days. Those observations must come without threshold/target retuning, outcome-selected controls or unapproved reuse of the untouched holdout. More favorable candles after stops, more validation code, or larger projected cost ratios would not change this recommendation.

Even favorable price evidence could justify only acquiring the missing facts. Still absent: dated complete instrument lifecycle/status/age, tick/lot/minimum-notional filters and contract units; contemporaneous 24h turnover/ticker; accepted distinct spread sample endpoints preserving raw source/arrival clocks and the #22 decision; independently supported OI quantity/notional and actual field measurement timestamps; independently supported depth units, size within 0.20% and freshness; verified contemporaneous event/news coverage and deterministic blackout decisions; true availability/ingestion/correction completeness; one-use human approval timing; admissible adverse-price/chase bounds; IOC submission within 10 seconds, partial fills/queue/depth/impact, actual fees and funding quantity/mark/timing; protective stop/40%/60% execution; 11h55 flatten attempts and 12h reconciliation; and portfolio admission under two positions and aggregate risk limits. Zero historical strict C02 candidates remain.

B1 retains 562 formations / 32 confirmations / zero base survivors; this T1 extension neither reopens nor qualifies it. R1 remains unidentified without genuine spread-qualified balance evidence. OpenBot remains the read-only coordination plane; no owner-host C06-F acceptance rerun, persistent capture, purchase, credentials inspection, exchange order, demo or C07/C08 implementation occurred. The ≤0.25% / ≤0.50% risk ceilings, two positions, isolated 2×, no scale-in/widened stop, one writer and explicit one-use approval remain unchanged.

## Reproduction, machine evidence and validation

```sh
python scripts/c05_t1_event_control.py --data-root /path/to/c04-data
```

The command is bounded to the frozen September population and local manifest-pinned July–September sources. It does no network work and needs no October archive. Install the existing pinned `requirements-test.txt`. Output defaults to `research/c05`; `--output-dir` can direct a verification run elsewhere. Matching is serialized and hashed **before** outcome evaluation.

- [Complete event/control evidence](C05_L_T1_EVENT_CONTROL_EVIDENCE.json.gz): all 624 setup histories, original 434 classified confirmations, matched control paths, frozen snapshots/levels, source partitions, raw indexed used 5m records, censoring and ordering assumptions.
- [Control pool and matches](C05_L_MATCHES.json.gz): all 60,480 timestamps, causal exclusions, exact cohorts, candidate counts/digests and deterministic links, including unmatched cases.
- [Summary](C05_L_T1_EVENT_CONTROL_SUMMARY.json): population/horizon distributions, equal-day matched contrasts and explicit uncertainty limitations.

Evidence content hash: `1bb69d021b70a09655bde84214364172b0e6d50a2a75d1c3e18a44522bab6a13`. Matching content hash: `e83a7eb9541c511f7e33174585b9c5429663919ad7f76a10169a67aef52d98c4`. The final matching artifact is byte-identical to the first forward-outcome-blind selection; the final full run adds retained state histories and sensitivity annotations without changing selection or findings.

Validation: 20 focused C05-L/C05-K/C04 archive checks; full relevant offline CI suite **328 passed**; compilation, dependency integrity, deterministic C03 golden/incomplete-panel checks, C04 blocker replay to scratch and `git diff --check` pass. The authentic final bounded command reproduced all original histories and geometries; artifact checks independently bind the 434/24 membership, original row fields, source paths, match embargoes and hashes. Remote final-head CI is reported with PR publication rather than inferred from these local results.
