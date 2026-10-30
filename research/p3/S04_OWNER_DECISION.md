# S04 economic decision and owner packet

**BENCHMARK BEATEN — NO. ECONOMIC GATE — REJECT.**

VT4.compression-breakout.v0.1 failed the frozen development test. September had 113 primary confirmations, two complete base-cost cases and zero target-first paths. August supplied additional development evidence: 122 primary confirmations, four complete base-cost cases, one target-first, two stop-first and one losing time exit.

**NEXT DECISION:** Accept the no-go for further September-only refinement of the tested families and HOLD Session 05 strategy integration until a separately reviewed economic/data proposal earns approval. Authorize no strategy-specific source spending for this candidate.

## Decision basis

The rejection is a development governance decision: VT4 failed to improve the opportunity population, diversity and payoff geometry sufficiently to warrant further integration. All eleven September advancement checks failed. Neither month reached the protocol’s large-sample hard-rejection condition; two September cases cannot establish population-wide negative expectancy. The declared fallback rule rejects a candidate that does not materially improve on PC3.

The measured failure is structural. Of 113 primary September confirmations, 110 had a target below 1.8 initial price-R and 31 had stops wider than 2%; reasons overlap. August had 117/122 targets below 1.8R and 60 wide stops. No primary case had a target above 4R. Broader structural invalidation preserved too little reachable reward when nearer known opposition took precedence. Inventing a farther target or widening the admissible geometry would change the frozen policy.

| September policy | Complete base cases | UTC days / symbols | Target-first / stop-first | Exact pairs / days |
|---|---:|---:|---:|---:|
| T1 | 24 | 9 / 7 | 0 / 24 | 11 / 5 |
| PC2 | 2 | 2 / 2 | 1 / 1 | 0 / 0 |
| PC3 | 9 | 6 / 4 | 1 / 8 | 2 / 2 |
| VT4 | 2 | 2 / 2 | 0 / 2 | 0 / 0 |

All use identical September source partitions and C05 fee/friction assumptions. The benchmark code rechecked 24,414 T1, 64,320 S01 and 80,742 S03 retained source OHLC records, and reproduced 434, 73 and 154 diagnostic paths respectively. The comparison follows each original final target; T1’s staged management is not replaced with VT4’s single-target cashflow model.

## Implemented and frozen research

Policy hash: `e3fc5c0aca4f3cb57d97dcb70f31f9779f16d76cda2dff13b2a7a879261ef2bd`. Preregistration commit: `93adad5`. One hypothesis, no parameter search or replacement candidate. The executable prototype uses a preceding 24-bar 15m range, ATR measured before the breakout bar opened, a distinct next-5m acceptance, a frozen 12-bar structural stop, a fixed range projection capped by nearer unvisited opposition, and immutable expiry/cooldown rules. It is a proposed research version with no registry authority.

The ledger contains 122,976 scan windows, 1,062 raw formations and 723 diagnostic confirmations. It preserves every raw setup, veto, state transition, frozen level and source locator. The main census and original matches were sealed before path evaluation. The targetless-breakout implementation defect was corrected before any new forward-path computation; the failed scan was rerun. A later accounting correction marks behind-entry target cashflows invalid. It changed no setup, match, base-case membership, admissible cashflow or economic verdict.

| Month | Raw / diagnostic / primary | Complete base / days / symbols | Target / stop / timeout | Base survival |
|---|---:|---:|---:|---:|
| 2024-08 | 522 / 376 / 122 | 4 / 3 / 4 | 1 / 2 / 1 | 3.28% |
| 2024-09 | 540 / 347 / 113 | 2 / 2 / 2 | 0 / 2 / 0 | 1.77% |

All eleven advancement criteria remain conjunctive: 20 complete base opportunities, eight days, four symbols, 10% confirmation survival, 35% conservative target-first, 50% exact controls over eight event days, positive 1h/4h and nonnegative 12h matched contrasts, and positive 4h day-deletion lower. The machine evidence stores each boolean. No month pooling, ablation substitution or source waiver.

## Costs, timing and portfolio feasibility

| Month | Optimistic / base / stress survivors | Adverse entry +0 / .025 / .05R | Mean conditional base / stress risk return |
|---|---:|---:|---:|
| 2024-08 | 4 / 4 / 2 | 4 / 3 / 3 | -0.17 / -0.23 |
| 2024-09 | 2 / 2 / 1 | 2 / 2 / 2 | -1.00 / -1.00 |

Fees are 2/5/10 bps per side, round-trip friction 0/2/5 bps and funding debits 0/1/3 bps. Entry, stop and target notionals differ and are charged correctly. Separate 5/10 bps funding, .10R stop-slippage and adverse-entry geometry screens are retained. These are cost assumptions, not original account payments.

The complete 12h path excludes the confirmation candle. Same-bar stop/target ordering is conservative, stop exits include adverse gap opens, and the conditional cashflow exits at 11h55. There are no base-case same-bar ambiguities. Rejected and invalid geometry is retained; an invalid target cannot create a successful cashflow. Later post-stop MFE is never a recovered trade.

Every event also has next-open and 300-second delayed-open feasibility diagnostics. Five-minute OHLC cannot prove 90-second approval, trigger+10-second IOC submission, two dated ticks, partial fills or protection. Actual fills remain unproven and executable/admitted counts remain zero.

A fixed-12h reservation diagnostic enforces two slots, one position per symbol, .25% per-trade and .50% aggregate modeled risk, and entry notional within 2x conditional equity. August’s conditional terminal equity multiple was 0.9983194628781409874959281214; September’s was 0.9950062500000000000000000000. All six cases fit the diagnostic capacity. This does not certify dated lot filters, liquidation, actual margin or the mark-to-market daily halt.

## Filter falsification and control support

Compression added no surviving cases when removed in either month. Removing the bias mask raised August to 16 complete cases with six targets first, but September to 14 with zero targets first. Removing compression, volume and bias together produced 19/6 in August and 18/0 in September. Removing volume alone added one case each month and no target-first case. The added-case ledgers show that the filters do not demonstrate stable improvement in signal quality. A favorable August ablation is not a replacement candidate.

Original post-trigger exact matching found only 28 controls for all 723 diagnostic confirmations. C03’s current regime partly encodes the breakout itself; excluding raw/cooldown controls creates a common-support problem. This is a strategy/evaluator identification fact, not a missing vendor field.

A separate supplement was committed at `53aa226` after the primary path program completed but before its results were read. It uses context exactly 20 minutes before entry for cases and controls, before the formation bar opened; the specification states this analyst-blind timing explicitly. Its source pool and original matches were sealed before supplementary paths. It cannot change the primary gate or promote VT4.

| Lag-context comparison | Pairs / event days | 1h / 4h / 12h equal-day contrast, bps |
|---|---:|---:|
| 2024-08 primary | 37 / 19 | -18.96 / -36.42 / -92.10 |
| 2024-08 base | 3 / 2 | -206.45 / -429.91 / -661.22 |
| 2024-09 primary | 37 / 16 | -27.93 / -62.99 / -65.93 |
| 2024-09 base | 2 / 2 | -39.31 / -158.21 / -209.56 |

Lag matching increased diagnostic coverage to 52/376 August and 70/347 September. Primary confirmations have negative 4h and 12h contrasts in both months, across 19 and 16 matched event days. The base samples remain too small for an independent economic inference. Increased matching support did not produce evidence for advancement. Continuous ADX/slope balance, control reuse, shared-market components, day-deletion ranges, descriptive joint-day resampling and side-reversed negative controls are retained. No selection-valid CI is claimed.

## Original adverse and favorable examples

Historical times below are UTC market times. Full IDs and CSV row locators resolve the source-linked ledger.

| Case | Frozen geometry and observed result |
|---|---|
| August first loss: ADA short, Aug 8 12:20 | Entry .33130, stop .336069250222728954125, target .32180. Stop touched in 12:30–12:35; no target within 12h. Conditional base return −1 initial modeled monetary risk. |
| August first winner: SOL short, Aug 11 18:35 | Entry 147.4030, stop 150.125358784570265550, target 141.3150. Target touched in 22:25–22:30, no stop within 12h; conditional base return +2.0236. |
| August timeout: BNB long, Aug 25 13:35 | Entry 577.350, stop 569.92694836261064525, target 591.040. Neither level reached; 11h55 exit loses .6864 modeled risk. |
| September first loss: DOGE short, Sep 3 08:50 | Entry .098930, stop .099893496907404272625, target .096100. Stop touched in 12:15–12:20; no target within 12h. |

The first rejected September BNB short (Sep 1 00:50) later touches its target but has inadmissible reward geometry. It stays rejected. No September base winner or base ambiguity exists; none is invented.

## Genuine sources and unresolved qualification

The existing loader verified all 84 pinned July–September archives: 11,566,262 compressed bytes and 266,616 normalized bars. Archive/member hashes, schema, native clocks, continuity and source CSV locators are retained. Current restoration timestamps are separate from the original manifest retrieval dates. July is warmup; August is additional development previously used as indicator history; September is heavily selected development. Neither is an untouched test. Month-end crossing paths are censored. All 28 reserved October monthly archives remain unfetched and unopened.

The owner-host S02 facts are recorded separately with issues #18/#22 citations and original report/feed hashes. Cloud did not reprocess those owner files. The proposed provider sampler passed three of four cutoffs, strict v1 passed none, and owner-receipt selection was zero. Reconstructed L2 quotes and provider receipt do not establish native BBO or owner arrival. Source acceptance remains 7 PARTIAL / 2 UNVERIFIED / 0 SOURCE_ACCEPTED; production C02v1 is unchanged.

Strict after-cost qualification still requires dated identity/lifecycle and complete filters, OI-specific measurement time/units and contemporaneous mark, depth units/sequence/gaps, accepted spread and arrival semantics, original publication-time news/event coverage, account fees, approval/order/fill/nonfill/partial/protection clocks and actual funding exposure. No source adapter can supply these facts by inference or convert this price rejection into a pass.

`S04_ORIGINAL_SOURCE_AUDIT.json` records a separate CSV re-read of all 266,616 retained records across all 84 original members: exact values, native IDs, availability proxies, CSV row locators and archive/member hashes matched. Reopening the sealed census reproduced the main census, evidence and generated result report byte for byte.

## Minimum lawful data requirement and economic value

The price mechanism was measurable with existing free originals. Further quote data is not needed to determine that this frozen version failed development. Its base-case sample cannot quantify a small independent expected profit.

For any later reviewed independent policy, retain the original minimum of 100 legitimate intended signals, 30 UTC days, 30 nonoverlapping shared-market 12h components, four symbols including two altcoins, two dated liquidity cohorts and at least 50% source-aware exact controls. Require at least 735 hourly bars (30d15h) of context, complete 12h forward paths, 60 distinct predecision spread slots and the same original non-price feeds at all relevant cutoffs. One hundred signals plus fifty controls means at least 150 source-linked records, not 150 independent trades.

At September’s price-screen rate, collecting 100 such opportunities would take approximately 1,500 calendar days across this fixed seven-symbol cohort, before source attrition. August’s rate implies 775 days. These are conditional rate extrapolations, not forecasts. The previously proposed 133-day evaluation would yield about 8.9 September-rate price opportunities, far below 100; even 210 days would imply only 14. This candidate does not justify that investment.

A planning comparison of 35% versus 25% target-first requires approximately 157 independent trials (one-sided 97.5%, 80% power, normal approximation), before cluster inflation. For matched 4h effects of 10/20/40 bps, August’s two-day standard-deviation estimate implies 18,721/4,681/1,171 independent joint days; that unstable two-day estimate is a warning about power, not a qualification requirement or reliable calendar forecast. September’s original sample cannot estimate this variance at all. Actual source-eligible signal rates remain unknown.

Recommended new source spend for this tested family: **$0**. The prior $350 prospective proposal remains unspent and unapproved. The value of this study is rejecting a specific unpromising investment route without a data purchase; expected trading profit or a commercial dataset’s value cannot be priced from these observations.

## Owner choice and exact Session 05 contract

Option A, recommended: accept the no-go for further September-only tuning of T1/PC2/PC3, first-breach failed auctions and this frozen VT4 continuation route; preserve the code/evidence and HOLD strategy-specific source spending and Session 05 integration. This does not assert that every possible trading mechanism is unprofitable.

Option B: require a separately reviewed independent hypothesis/data proposal before spending another implementation session. It must solve the observed payoff geometry, sampling rate and common-support problem before opening reserved outcomes. PC3.v0.2 and favorable ablations remain unapproved.

`S04_SESSION05_CONTRACT.json` is the machine handoff: exact artifact hashes, functions, existing S02/G/H/C02/A01–A10 interfaces, conditional file-level recipe, adverse tests and independent R1/R2 gates. Default action is `HOLD_NO_POLICY_INTEGRATION`; approved policies are empty. The conditional recipe requires a later accepted economic result, exact owner research-version approval and original source acceptance. It grants no production clock migration, registry write, procurement, collector, Demo or trading permission.

Keep .25%/.50% modeled risk, two slots, isolated 2x, 1% daily entry halt, authenticated one-use approval, a single exchange writer, no stop widening or timer reset, and 11h55/12h clocks from the first actual fill. All original policies remain RESEARCH_ONLY. P3 is INSUFFICIENT_EVIDENCE; formal project qualification remains 45%.

## Reproduction and provenance

- Protocol: `c64c81cad1963d16fa66054d9c327483af311320cb16ed717aa41c98a2b68938`.
- Candidate contract: `3dd0d38c1187c8d75e141f7dc4c1d76bdcde183accd7e22365a7dd0f50222792`.
- Census: `ae1fee4e10382106d8992b091946706137c76c597641263facf02ec12aa22c88`.
- Main evidence: `84cb5afcca3190b323eb7a528462b68427a79be409a715b61c24589352a5c19c`.
- Supplement evidence: `bf644b3639fb1c21decf01f20d01ec316889a27c10b27e530656a4e39ee6e6cf`.
- Original archive/member hashes: unchanged `research/c04/historical_manifest.json`.
- Current retrieval audit: `S04_RESTORATION_AUDIT.json`.

```sh
python -m venv work/venv
work/venv/bin/pip install -r requirements-test.txt
work/venv/bin/python scripts/s04_economic_rescue.py --data-root /workspace/work/c04-data --workers 2 --output-dir work/s04-reproduction
work/venv/bin/python scripts/s04_control_support.py
work/venv/bin/python scripts/s04_verify_sources.py --data-root /workspace/work/c04-data
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 work/venv/bin/python -m pytest -q
```

Restore only the 84 pre-October files from their exact manifest source URLs to an external data root and verify their pinned hashes. The evaluator performs no network request. Use `--workers 1` on Windows. `--census-only` stops before outcomes; `--reuse-census` validates source/version/code binding before path assembly. Evidence retains source locators, full original 12h paths and package code/dependency hashes. Final-head CI and independent review belong in PR metadata, avoiding a self-referential commit hash.

**WHAT NOW WORKS:** executable causal research, full rejection census, genuine source-linked controls and paths, cost/entry/stop/time stress, conditional monetary cashflows, portfolio-capacity diagnostics and independent source/path arithmetic tests.

**WHAT IS STILL UNPROVEN:** an independently qualified positive-after-cost full policy, source eligibility, real fees/fills/approval latency and genuine operator/Demo acceptance. This session provides a decisive tested no-go.
