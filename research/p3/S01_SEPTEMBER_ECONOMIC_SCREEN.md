# S01 — Authentic September economic screen

**Exploratory development evidence / price-only / RESEARCH_ONLY.**

No executable fills, realized P&L, true win rate or strategy expectancy are estimated. September informed design; October archives and outcomes were not accessed. The fixed seven-symbol panel is not a point-in-time eligible universe.

**Frozen ranking: PC2 > FR2.** Ranking does not authorize implementation. The exact verdict follows the preregistered rules, including small-sample and matching requirements.

Across both candidates, all confirmation/control12h windows have 244 overlapping pairs in 16 connected market-time components. Pooling symbols or strategies does not create independent observations.

Base `b06079077850bf6cbc176d010e0ccf3bc42b032a`; preregistration commit `1bd2a3729fc7ef49a1a47744f380e14973d29d3a`. Preregistration SHA-256 `114e951b111b4dd55b90dd91e53eb82bac1d13815dfd7bcda7251a80bcc7f7d9`; machine contract `e89dfe169ddc9eb43a55fbbae9e1394ebc2e3367310a27166b61bddc4e4c8280`. Evidence content hash `edb6182182c7d2aae00c009b5468b089d96f8d56e4471450938eb51f242d4d7e`; outcome-blind census/matches `6fe2f1db79fc799ee3b3fbd12fd66e182598f526c7b61a452563d6dcd6bb4b81`.

C04 verified 266,616 native bars from84 July–September ZIPs (11,566,262 compressed bytes), using the existing ZIP/member/schema/continuity checks. Manifest SHA-256 `6a34aae6b37ec9b48aa166dda52cd578a86776ef8b36be05aaaa5bf42f51058a`. All84 archive/member hashes are in the ledger. The28 October archives are excluded by the loader before file access.

## Frozen opportunity census

| Candidate | Formed | Confirmed | Invalidated / expired / end-censored | Geometry pass | Optimistic / base / stress survivors |
|---|---:|---:|---|---:|---|
| PC2 | 392 | 70 | 134 / 188 / 0 | 3 | 3/2/1 |
| FR2 | 361 | 3 | 37 / 321 / 0 | 0 | 0/0/0 |

Each candidate receives60,480 symbol-windows; formation attempts occur only on new15m closes. FR2 formations count armed ranges, not observed sweeps. PC2 uses a45m pullback stop; FR2 uses first range rejection. All confirmations, including geometry/cost rejections, receive paths. Counts are outside strict C02 admission.

## PC2: REVISE_BEFORE_IMPLEMENTATION

Policy `PC2.structural-pullback.v0.1`, version `2b697cc7659bafcd69612cc1cdbd878b18d890214cca8753364c304a75609680`. 0 observed sweep transitions. Geometry rejection memberships: `{"TARGET_NOT_AHEAD_AT_CONFIRMATION": 37, "TARGET_OUTSIDE_1_8_TO_4_R": 67}`.

Formation terminal reasons `{"FIRST_DIRECTIONAL_BREAK_OF_FORMATION_BAR": 70, "NO_CONFIRMATION_IN_THREE_BARS": 188, "ORIGINAL_STOP_TOUCHED_BEFORE_CONFIRMATION": 130, "SESSION_ROLLOVER_OR_OPPOSITE_BIAS": 4}`. Target types `{"FROZEN_RANGE_OBJECTIVE": 24, "SWING_HIGH": 209, "SWING_LOW": 159}`. Median formation-to-confirmation latency 10.0 minutes; median target confirmation age 125.95833333333333 hours. PC2-style target-at/behind-required-trigger incompatibility was already present at formation in 240 setups, including 30 later confirmations. These are causal geometry diagnostics, not a hypothetical earlier-entry performance test.

Base survivors: 2 on 2 UTC days / 2 symbols. Symbols `{"BNBUSDT": 1, "XRPUSDT": 1}`; sides `{"LONG": 2}`. Regimes `{"TREND_UP": 2}`; UTC4h sessions0..5 `{"0": 1, "1": 1}`. Market-day counts `{"2024-09-10": 1, "2024-09-29": 1}`.

Median original stop fraction 0.004262652127939225961927730854; target distance 3.165069516112171706937375406R; base modeled loss-route drag 0.3117545343863799457815270532R. Fixed-level adverse-entry0/.025/.05R cost survivors `{"0": 2, "0.025": 2, "0.05": 2}`. These are successful-target scenario screens, not probabilities or net performance.

| Horizon | Complete / censored | Median signed bps | Median MFE / MAE R | Target before stop lower–upper | Stop first | Same-bar ambiguous |
|---|---|---:|---|---|---:|---:|
| 15m | 2 / 0 | 27.12757307017574212032401048 | 1.392881600833716513226119459 / -0.1621094401922017587863596721 | 0–0 | 0 | 0 |
| 60m | 2 / 0 | 87.0314495005242160115984955 | 2.832647652724070994007523732 / -0.4325545790116050009262001056 | 1–1 | 0 | 0 |
| 240m | 2 / 0 | 128.6683875253890098026664084 | 3.736125250650048295797088412 / -0.686933669980350624721099523 | 1–1 | 1 | 0 |
| 720m | 2 / 0 | 324.5817517465216624048885306 | 10.01276887957148720817269778 / -0.686933669980350624721099523 | 1–1 | 1 | 0 |

Among complete12h cases, 0 touch the original stop in the first forward5m bar, 0 by15m and 0 by1h. Target-before-stop by11h55 lower=1. Whole-horizon MFE/MAE can occur after a stop; later favorable movement is not a setup success.

| Fixed population | N | Complete12h | Target lower–upper | Median12h bps |
|---|---:|---:|---|---:|
| all_confirmations | 70 | 68 | 2–2 | 35.77728943664111314774119720 |
| geometry_pass | 3 | 3 | 2–2 | 84.24619170484909142663006051 |
| base_survivors | 2 | 2 | 1–1 | 324.5817517465216624048885306 |
| rejected_confirmations | 68 | 66 | 1–1 | 30.48887708994548069023013244 |

Targets of invalid geometry are contextual touches only; full-target counts require ordered target>1R, and do not rehabilitate rejected geometry. Missing or behind targets remain failed geometry.

| All confirmations: price-path context | Complete / censored | Median signed bps | Median MFE / MAE R | Matched pairs / days | Equal-day contrast bps |
|---|---|---:|---|---|---:|
| 60m | 70 / 0 | 6.42999274605430799700525723 | 0.756779220838475746625426786 / -0.522042792873030711542464249 | 18 / 11 | 3.24001452786191355172920274 |
| 240m | 68 / 2 | 11.09326535892884408421042724 | 1.520618433538005861148232226 / -1.151479995694569824894758240 | 18 / 11 | -0.7674041662182160103696985764 |
| 720m | 68 / 2 | 35.77728943664111314774119720 | 2.947927969863906882476624196 / -2.399006586922820957873258859 | 18 / 11 | 69.00259710053787567990373134 |

These broad contrasts include rejected geometry. They cannot substitute for the declared cost/geometry population. All day-deletion ranges, per-day pair values and rejected-population contrasts are retained in machine evidence.

Outcome-blind eligible control pool=18,432; all-confirmation matched=18. Pool exclusion memberships `{"ACTIVE_OR_CURRENT_TRIGGER": 1267, "CANDIDATE_REGIME_NOT_ELIGIBLE": 40353, "CROSSES_DEVELOPMENT_END": 1001}`.

| Base matched contrast | Pairs / event days / unique controls | Equal-day case−control bps | Day-deletion range bps |
|---|---|---:|---|
| 60m | 0 / 0 / 0 | None | None |
| 240m | 0 / 0 / 0 | None | None |
| 720m | 0 / 0 / 0 | None | None |

Day-count Kish concentration=2.000; 0 overlapping case/control12h interval pairs and 2 connected market-time components. These are descriptive concentration/dependence counts, not certified independent observations. Missing controls and shared market shocks can confound contrasts; no CI/p-value is issued.

### Source-linked cases

- first base survivor: `2c35a88d792681659f41fe2a14fedd1b79034ceb5ca0113c50ff8c71cb43c3ca` BNBUSDT LONG, confirmation 2024-09-10T01:55:00+00:00; E=517.000, S=515.132708163272896350, T=521.960, g=2.656253244642059566363581287R; stop candle 2024-09-10T03:40:00+00:00, target candle 2024-09-10T08:05:00+00:00; 12h signed=34.42940038684719535783365571bps, MFE/MAE=3.079325838042710182780361372/-1.274573129485504388698653924R. Geometry `SCREENABLE`. Reference key `["BNBUSDT","5m","1725933000000"]`; formation, target-source window, transition, forward-bar and CSV locators are in the ledger.
- first base stop-first: `2c35a88d792681659f41fe2a14fedd1b79034ceb5ca0113c50ff8c71cb43c3ca` BNBUSDT LONG, confirmation 2024-09-10T01:55:00+00:00; E=517.000, S=515.132708163272896350, T=521.960, g=2.656253244642059566363581287R; stop candle 2024-09-10T03:40:00+00:00, target candle 2024-09-10T08:05:00+00:00; 12h signed=34.42940038684719535783365571bps, MFE/MAE=3.079325838042710182780361372/-1.274573129485504388698653924R. Geometry `SCREENABLE`. Reference key `["BNBUSDT","5m","1725933000000"]`; formation, target-source window, transition, forward-bar and CSV locators are in the ledger.
- first base target-first: `e88dc96e326bf2972c7f11534b47ee32986ccfb5b3d25ff6d8b140cce71c2c73` XRPUSDT LONG, confirmation 2024-09-29T05:50:00+00:00; E=0.6149, S=0.611878675810359171700, T=0.6260, g=3.673885787582283847511169524R; stop candle not touched, target candle 2024-09-29T06:25:00+00:00; 12h signed=614.7341031061961294519434054bps, MFE/MAE=16.94621192110026423356503420/-0.09929421047519686074354512228R. Geometry `SCREENABLE`. Reference key `["XRPUSDT","5m","1727588700000"]`; formation, target-source window, transition, forward-bar and CSV locators are in the ledger.
- first rejected confirmation: `1b47965a09767adaac588ccf1d340816fb935f1a352a8c16baf89582868739bf` SOLUSDT SHORT, confirmation 2024-09-01T08:15:00+00:00; E=132.2240, S=133.116819648142518950, T=132.0020, g=0.2486504418466411260149380647R; stop candle 2024-09-01T15:35:00+00:00, target candle 2024-09-01T08:15:00+00:00; 12h signed=-260.3158276863504356243949661bps, MFE/MAE=2.490984606607792181338838991/-4.135213654494590257870051058R. Geometry `TARGET_OUTSIDE_1_8_TO_4_R`. Reference key `["SOLUSDT","5m","1725178200000"]`; formation, target-source window, transition, forward-bar and CSV locators are in the ledger.

## FR2: REVISE_BEFORE_IMPLEMENTATION

Policy `FR2.failed-range-break.v0.1`, version `c1c21cd63612a5278e0578e9188fa0d15cf288dfccce43a7392bfa44435a54cc`. 11 observed sweep transitions. Geometry rejection memberships: `{"TARGET_NOT_AHEAD_AT_CONFIRMATION": 1, "TARGET_OUTSIDE_1_8_TO_4_R": 3}`.

Formation terminal reasons `{"DISTINCT_ACCEPTANCE_AFTER_FAILED_BREAK": 3, "FIRST_BREACH_NOT_QUALIFIED_REJECTION": 29, "NEXT_BAR_CONFIRMATION_FAILED": 7, "NO_SWEEP_IN_THREE_BARS": 321, "ORIGINAL_STOP_TOUCHED_BEFORE_CONFIRMATION": 1}`. Target types `{"FROZEN_RANGE_OBJECTIVE": 113, "MISSING": 181, "SWING_HIGH": 32, "SWING_LOW": 35}`. Median formation-to-confirmation latency 10.0 minutes; median target confirmation age 63.916666666666664 hours. PC2-style target-at/behind-required-trigger incompatibility was already present at formation in 0 setups, including 0 later confirmations. These are causal geometry diagnostics, not a hypothetical earlier-entry performance test.

Base survivors: 0 on 0 UTC days / 0 symbols. Symbols `{}`; sides `{}`. Regimes `{}`; UTC4h sessions0..5 `{}`. Market-day counts `{}`.

Median original stop fraction None; target distance NoneR; base modeled loss-route drag NoneR. Fixed-level adverse-entry0/.025/.05R cost survivors `{"0": 0, "0.025": 0, "0.05": 0}`. These are successful-target scenario screens, not probabilities or net performance.

| Horizon | Complete / censored | Median signed bps | Median MFE / MAE R | Target before stop lower–upper | Stop first | Same-bar ambiguous |
|---|---|---:|---|---|---:|---:|
| 15m | 0 / 0 | None | None / None | 0–0 | 0 | 0 |
| 60m | 0 / 0 | None | None / None | 0–0 | 0 | 0 |
| 240m | 0 / 0 | None | None / None | 0–0 | 0 | 0 |
| 720m | 0 / 0 | None | None / None | 0–0 | 0 | 0 |

Among complete12h cases, 0 touch the original stop in the first forward5m bar, 0 by15m and 0 by1h. Target-before-stop by11h55 lower=0. Whole-horizon MFE/MAE can occur after a stop; later favorable movement is not a setup success.

| Fixed population | N | Complete12h | Target lower–upper | Median12h bps |
|---|---:|---:|---|---:|
| all_confirmations | 3 | 3 | 0–0 | 84.32079046097841833512870993 |
| geometry_pass | 0 | 0 | 0–0 | None |
| base_survivors | 0 | 0 | 0–0 | None |
| rejected_confirmations | 3 | 3 | 0–0 | 84.32079046097841833512870993 |

Targets of invalid geometry are contextual touches only; full-target counts require ordered target>1R, and do not rehabilitate rejected geometry. Missing or behind targets remain failed geometry.

| All confirmations: price-path context | Complete / censored | Median signed bps | Median MFE / MAE R | Matched pairs / days | Equal-day contrast bps |
|---|---|---:|---|---|---:|
| 60m | 3 / 0 | -12.62954570781174547750826492 | 0.2392335469292445113328465199 / -0.7126817551878193134810672551 | 0 / 0 | None |
| 240m | 3 / 0 | 13.63739792949785970736862360 | 1.237991781312174394309835138 / -1.335023569577182657647633027 | 0 / 0 | None |
| 720m | 3 / 0 | 84.32079046097841833512870993 | 3.524930653006420876771381940 / -2.116296761297162984867488445 | 0 / 0 | None |

These broad contrasts include rejected geometry. They cannot substitute for the declared cost/geometry population. All day-deletion ranges, per-day pair values and rejected-population contrasts are retained in machine evidence.

Outcome-blind eligible control pool=492; all-confirmation matched=0. Pool exclusion memberships `{"ACTIVE_OR_CURRENT_TRIGGER": 51, "CANDIDATE_REGIME_NOT_ELIGIBLE": 59937, "CROSSES_DEVELOPMENT_END": 1001}`.

| Base matched contrast | Pairs / event days / unique controls | Equal-day case−control bps | Day-deletion range bps |
|---|---|---:|---|
| 60m | 0 / 0 / 0 | None | None |
| 240m | 0 / 0 / 0 | None | None |
| 720m | 0 / 0 / 0 | None | None |

Day-count Kish concentration=0.000; 0 overlapping case/control12h interval pairs and 0 connected market-time components. These are descriptive concentration/dependence counts, not certified independent observations. Missing controls and shared market shocks can confound contrasts; no CI/p-value is issued.

### Source-linked cases

- first base survivor: none in frozen population.
- first base stop-first: none in frozen population.
- first base target-first: none in frozen population.
- first rejected confirmation: `5233657e6115d4e08b4ac908591e6d335092cc75060e5861e91f7a02e529e5ad` SOLUSDT LONG, confirmation 2024-09-12T10:15:00+00:00; E=134.6050, S=134.007257744218901100, T=134.6000, g=-0.008364809333190367529120507688R; stop candle 2024-09-12T12:50:00+00:00, target candle 2024-09-12T10:15:00+00:00; 12h signed=84.32079046097841833512870993bps, MFE/MAE=3.524930653006420876771381940/-2.116296761297162984867488445R. Geometry `TARGET_NOT_AHEAD_AT_CONFIRMATION|TARGET_OUTSIDE_1_8_TO_4_R`. Reference key `["SOLUSDT","5m","1726135800000"]`; formation, target-source window, transition, forward-bar and CSV locators are in the ledger.

## Reproduction, source gaps and handoff

```sh
python scripts/s01_economic_recovery.py --data-root /path/to/c04-data
```

Uses existing pinned requirements. No network operation, raw archive in Git or October source required. Optional `--output-dir` writes a verification copy. The command first writes a deterministic outcome-blind census/matching artifact, then calculates paths and generates this report plus the compressed evidence. The ledger includes every formation/transition, confirmation/geometry/cost rejection, control, source key, archive/member hash and uncertainty record. Native IDs are scoped by symbol and interval.

No strict eligible candidates: dated metadata/filters/units, ticker, accepted source-clock/#22 and BBO history, validated OI units/measurement time, depth notional and event/news clearance remain missing. A01 flow, A04 liquidation, A05 ICT and A08 profile cannot be inferred from these bars. Funding0/1/3bps is hypothetical: C05-K reported up to4.3136bps trailing12h absolute funding on BNB, an ex-post aggregate stress, not a settlement forecast or actual cash flow. Candles do not resolve approval/IOC within10s, depth/partial fills, stop execution or exact11h55 liquidation.

Candidate ranking, original-policy root-cause diagnosis, upstream reuse comparison and the explicit owner decision are in `docs/adr/ADR-P3-ECONOMIC-RECOVERY-S01.md`; the complete frozen source/formula/qualification handoff is in `S01_NEW_POLICY_PREREGISTRATION.md` and `S01_CANDIDATES.json`. No production policy/registry/C02/risk/execution change, collector, paid access or account action occurred. P3 remains INSUFFICIENT_EVIDENCE and formal phase credit45%/55% unqualified.
