# S03 — Frozen September strategy test

**Exploratory development / original OHLCV / RESEARCH_ONLY.** No executed P&L or net expectancy.

Preregistration `d54dcfc`, protocol `2e24286cb178f4906f61eba37cc53b704f4ad02a94b405ca6df9b488cc49903e`. Census `6d38ffc4a1814236eafa7b39835b1944b10804c8e334250416549ce6b7892e3a`; evidence `3d161aa50d4117ffb9d81cd78ef8f1a0015f22d30920b5d4a2343eecd2665942`.

Verified 266,616 bars in84 pinned July–September archives. October archives/outcomes unopened. Seven fixed symbols are not a historically qualified universe. Source acceptance remains7 PARTIAL/2 UNVERIFIED/0 accepted.

| Candidate | Raw formations / accepted arms | Diagnostic / primary confirmations | Optimistic / base / stress | Decision |
|---|---:|---:|---:|---|
| PC3 | 392 / 245 | 145 / 84 | 9 / 9 / 2 | REVISE_BEFORE_R1 |
| FA3 | 182 / 4 | 9 / 1 | 1 / 1 / 0 | REJECT |

PC3 instantiates the lead reference with early acceptance, causal unvisited objectives and explicit formation headroom. FA3 tests a distinct previous-day failed-auction mechanism. A verbal benchmark has no independent third-policy results.

PC2/FR2 use the identical84 archives, manifest, split and C05 cost/path formulas:392/70/2 and361/3/0 formations/confirmations/base survivors. PC2 conservative target-first1/2, exact controls0/2; FR2 has no surviving paths. Entry/management differ by frozen version.

## PC3: REVISE_BEFORE_R1

`PC3.value-acceptance.v0.1` / `4b5120bea7991544cbae13d1f1f2c77684e03836a1662d1f52973c6e74a299a9`.

Base population 9; complete12h 9, censored 0; 6 complete UTC days, 4 symbols. Target first conservative–optimistic 1–1; stop first 8, same candle 0.

Symbols `{"BNBUSDT": 4, "BTCUSDT": 2, "ETHUSDT": 2, "SOLUSDT": 1}`; sides `{"LONG": 5, "SHORT": 4}`; regimes `{"TREND_DOWN": 4, "TREND_UP": 5}`; UTC4h sessions `{"1": 2, "2": 2, "3": 1, "4": 2, "5": 2}`. Days `{"2024-09-01": 1, "2024-09-05": 1, "2024-09-10": 1, "2024-09-12": 3, "2024-09-16": 2, "2024-09-22": 1}`.

Median stop fraction 0.003655501297631905956401216365, target price-R 3.164295025683692499587025997, base loss cost-R 0.3561283787512704332660408971. Adverse0/.025/.05R survivors `{"0": 9, "0.025": 6, "0.05": 3}`; funding5/10bps survivors `{"10": 5, "5": 7}`. These are planned successful-target scenarios, not returns.

| Horizon | Complete/censored | Target lower/upper | Stop first | Median signed bps | Paired N/days | Equal-day contrast bps | Day-deletion range |
|---|---:|---:|---:|---:|---:|---:|---|
| 15m | 9/0 | 0/0 | 1 | -0.1900782604037607847812976816 | 2/2 | 9.873613557487112785238037616 | ['-0.307876231804439260004999577', '20.05510334677866483048107481'] |
| 60m | 9/0 | 0/0 | 5 | -9.770846007779805689213354719 | 2/2 | 43.87611347297030684996202497 | ['-2.734148710844178196629875135', '90.48637565678479189655392507'] |
| 240m | 9/0 | 1/1 | 6 | -36.47483604745413013042517132 | 2/2 | 18.90820873122286453747594342 | ['14.74172596119886546089525177', '23.07469150124686361405663508'] |
| 720m | 9/0 | 1/1 | 8 | -12.90822253775655092293791145 | 2/2 | -189.495062407724891408178242 | ['-238.6329165502087944645075102', '-140.3572082652409883518489738'] |

Original stop by5m/15m/1h: 0/1/5; target first by11h55: 1. Kish day concentration 4.765; 4 overlapping intervals, 8 connected market-time components. No independent-trade or significance claim.

Formation vetoes `{"FORMATION_BASE_HEADROOM_FAILED": 147}`; terminal reasons `{"ACCEPTANCE_DEADLINE_FAILED": 119, "DISTINCT_PRICE_ACCEPTANCE": 145, "ORIGINAL_STOP_TOUCHED_BEFORE_CONFIRMATION": 125, "UTC_SESSION_ROLLOVER": 3}`; confirmation geometry vetoes `{"TARGET_OUTSIDE_1_8_TO_4_R": 89}`; cap vetoes 105.

| Frozen population / ablation | N | Complete12h | Target lower/upper | 4h equal-day contrast bps |
|---|---:|---:|---:|---:|
| all_diagnostic_confirmations | 145 | 142 | 50/50 | -31.09979486979100121927129503 |
| all_confirmations | 84 | 81 | 32/32 | -5.386115262919240507510742839 |
| base_survivors | 9 | 9 | 1/1 | 18.90820873122286453747594342 |
| rejected_confirmations | 136 | 133 | 49/49 | -32.94759242488295945840986657 |
| no_headroom | 12 | 12 | 3/3 | 58.72100823990425352637399898 |
| no_entry_cap | 38 | 36 | 18/18 | -50.71322238879072034644727722 |
| neither_headroom_nor_cap | 41 | 39 | 20/20 | -40.46257014349434616683613999 |

Ablations are descriptive masks, not candidates eligible for advancement; no policy is replaced after observing these results. All rejected confirmations retain signed paths. Invalid geometry target touches are context, not admissible trades. Full MFE/MAE, volatility strata, per-day contrasts, matched pool hashes and source CSV locators are in the evidence.

## FA3: REJECT

`FA3.prior-day-failed-auction.v0.1` / `7a2401a489473b823dfe5a7d5cf74eddec1712a33a59672ff0b8eabb038ed81a`.

Base population 1; complete12h 1, censored 0; 1 complete UTC days, 1 symbols. Target first conservative–optimistic 0–0; stop first 1, same candle 0.

Symbols `{"ADAUSDT": 1}`; sides `{"LONG": 1}`; regimes `{"UNCLASSIFIED": 1}`; UTC4h sessions `{"2": 1}`. Days `{"2024-09-22": 1}`.

Median stop fraction 0.003319274541682436716077537058, target price-R 3.564062711299757979293762094, base loss cost-R 0.3911518455087088262354523531. Adverse0/.025/.05R survivors `{"0": 1, "0.025": 1, "0.05": 1}`; funding5/10bps survivors `{"10": 1, "5": 1}`. These are planned successful-target scenarios, not returns.

| Horizon | Complete/censored | Target lower/upper | Stop first | Median signed bps | Paired N/days | Equal-day contrast bps | Day-deletion range |
|---|---:|---:|---:|---:|---:|---:|---|
| 15m | 1/0 | 0/0 | 0 | 0 | 1/1 | -2.83286118980169971671388102 | None |
| 60m | 1/0 | 0/0 | 0 | 45.61003420752565564424173318 | 1/1 | 17.28142230950865847710292298 | None |
| 240m | 1/0 | 0/0 | 1 | -65.56442417331812998859749145 | 1/1 | -116.5559255897487248894473498 | None |
| 720m | 1/0 | 0/0 | 1 | -17.10376282782212086659064994 | 1/1 | -153.0810999383037072688569389 | None |

Original stop by5m/15m/1h: 0/0/0; target first by11h55: 0. Kish day concentration 1.000; 0 overlapping intervals, 2 connected market-time components. No independent-trade or significance claim.

Formation vetoes `{"FIRST_BREACH_NOT_RECLAIMED": 110, "FIRST_BREACH_PENETRATION_FAILED": 63, "FORMATION_BASE_HEADROOM_FAILED": 14, "MISSING_OR_EXTREME_FORMATION_CONTEXT": 2, "OPPOSITE_4H_BIAS": 100, "RECLAIM_DIRECTIONAL_BODY_FAILED": 165}`; terminal reasons `{"ACCEPTANCE_DEADLINE_FAILED": 5, "DISTINCT_PRICE_ACCEPTANCE": 9, "FIRST_BREACH_NOT_RECLAIMED|RECLAIM_DIRECTIONAL_BODY_FAILED": 61, "FIRST_BREACH_NOT_RECLAIMED|RECLAIM_DIRECTIONAL_BODY_FAILED|MISSING_OR_EXTREME_FORMATION_CONTEXT": 1, "FIRST_BREACH_PENETRATION_FAILED": 3, "FIRST_BREACH_PENETRATION_FAILED|FIRST_BREACH_NOT_RECLAIMED|RECLAIM_DIRECTIONAL_BODY_FAILED": 47, "FIRST_BREACH_PENETRATION_FAILED|FIRST_BREACH_NOT_RECLAIMED|RECLAIM_DIRECTIONAL_BODY_FAILED|MISSING_OR_EXTREME_FORMATION_CONTEXT": 1, "FIRST_BREACH_PENETRATION_FAILED|RECLAIM_DIRECTIONAL_BODY_FAILED": 12, "RECLAIM_DIRECTIONAL_BODY_FAILED": 43}`; confirmation geometry vetoes `{"TARGET_OUTSIDE_1_8_TO_4_R": 6}`; cap vetoes 4.

| Frozen population / ablation | N | Complete12h | Target lower/upper | 4h equal-day contrast bps |
|---|---:|---:|---:|---:|
| all_diagnostic_confirmations | 9 | 9 | 3/3 | -109.9876735499170846599289904 |
| all_confirmations | 1 | 1 | 0/0 | -116.5559255897487248894473498 |
| base_survivors | 1 | 1 | 0/0 | -116.5559255897487248894473498 |
| rejected_confirmations | 8 | 8 | 3/3 | -103.4194215100854444304106309 |
| no_headroom | 1 | 1 | 0/0 | -116.5559255897487248894473498 |
| no_entry_cap | 1 | 1 | 0/0 | -116.5559255897487248894473498 |
| neither_headroom_nor_cap | 1 | 1 | 0/0 | -116.5559255897487248894473498 |
| no_4h_bias_veto | 3 | 3 | 1/1 | -116.5559255897487248894473498 |

Ablations are descriptive masks, not candidates eligible for advancement; no policy is replaced after observing these results. All rejected confirmations retain signed paths. Invalid geometry target touches are context, not admissible trades. Full MFE/MAE, volatility strata, per-day contrasts, matched pool hashes and source CSV locators are in the evidence.

## Reproduction and scope

```sh
python scripts/s03_strategy_research.py --data-root /workspace/work/c04-data
```

Use requirements-test.txt in an isolated environment. No command downloads data or opens October. `--output-dir` writes a comparison copy; `--census-only` stops before outcomes; `--reuse-census` validates and reopens the frozen causal census. Census is written and sealed before any new path call. Candidate/contract/source/code/dependency hashes are retained.

See S03_OWNER_DECISION.md for the falsification examples, complete gate checklist and S04/S05 handoff. No strict C02 eligibility, actual fees/funding/fills, approval/IOC feasibility or full-policy net_R is established. P3 INSUFFICIENT_EVIDENCE; formal qualification remains45%/55% unqualified.
