# ADR-P3-ECONOMIC-RECOVERY-S01 — Entry, invalidation and objective must fit together

**PROPOSED; owner policy approval outstanding.** Requested profile: Session01/10,
Sol. Base/main reviewed at `b06079077850bf6cbc176d010e0ccf3bc42b032a`.
Branch `codex/final-s01-economic-recovery-sol`. Issues [18](https://github.com/KasunKarandagolla/AstraBot/issues/18)
and [22](https://github.com/KasunKarandagolla/AstraBot/issues/22) were read through
the GitHub connector. No production registry, policy, risk or source-clock edit.

**Decision:** PC2 ranks ahead of FR2, but **both proposed v0.1 versions are
REVISE_BEFORE_IMPLEMENTATION**. Do not approve either for Session04 activation
or commission new strategy-specific data. The economic route is conditional on
solving a demonstrated entry/target compatibility problem, not simply obtaining
more expensive feeds. Source-clock work remains necessary for eventual strict
eligibility; it cannot repair this geometry. There is no new economic GO.

The complete original-data results are in the single generated
[September report](../../research/p3/S01_SEPTEMBER_ECONOMIC_SCREEN.md).
[Preregistration](../../research/p3/S01_NEW_POLICY_PREREGISTRATION.md) and
[machine policy terms](../../research/p3/S01_CANDIDATES.json) were frozen in
`1bd2a3729fc7ef49a1a47744f380e14973d29d3a` before new outcome calculations.
September had already informed design through C05-K/L: all new results are
**exploratory development evidence**, not independent validation. October
forward outcomes remain unopened.

## What actually failed in the original evidence

The new command independently verifies the original C05-L source OHLC against
the restored C04 inputs: **24,414 retained bars and all434 original T1 paths**.
It also obtains original B1 price paths without changing that policy or using
October. These rechecks and their input hashes are in
`S01_EVIDENCE.json.gz.original_policy_diagnosis`; this ADR is interpretation,
not a separate empirical report or a replacement C05-L decision.

| Cause | Quantified authentic observation | What it supports / does not establish |
|---|---|---|
| Original T1 target ordering |434 confirmations:279 target-order failures,6 missing targets,149 ordered geometries;124 further base-cost rejections and1 context veto leave24 | Nearby opposition frequently fails the original two-leg geometry. The24 are a selected5.53% of confirmations, not the entire T1 population. |
| Distant objective selection |24 base survivors: median target2 **6.7853R**, range2.9451–22.9116R; zero target2 before stop under either candle-order bound | Conditional cost filtering favors large reward/R. It does not show the market can reach that reward within12h. Twenty never touch target2; four do so only after stop. |
| Stop and early follow-through |Median stop **0.251983%**; median first-stop candle upper time30m;2/24 stop in first5m,8/24 by15m,15/24 by1h; all24 by320m | Failure is not solely a far target problem. Median favorable excursion strictly **before** the stop candle is only **0.3737R**. No intrabar path or optimal alternate stop can be inferred. |
| Whole-path excursions |Base median12h MFE/MAE0.8548/−4.4648R, median signed close−52.4065bps | Persistent adverse paths weaken the continuation story. Favorable post-stop movement is never a recovered strategy success. |
| Confirmation latency |Original434: median formation→confirmation5m,90th percentile15m; base24 median5m, maximum20m | There is an observed confirmation wait. Earlier entry advantage,10s feasibility, true spread and fill improvement remain unmeasured. Moving entry earlier would be a different policy. |
| Regime/session selection |Base24:17 TREND_UP/7 TREND_DOWN;15/24 in00–04UTC; median ATR percentile71.04, range16.25–93.89 | Strong concentration is observable. With nine shared days and no eligible comparison cohort, this cannot identify a causal best session/volatility filter. No session rule is tuned here. |
| Weak selectivity / dependence |Only11/24 controls on five event days; nine-day Kish concentration6.70;48 overlapping case/control intervals in11 connected components | Effective independent evidence is far smaller than24. Original matched1h/4h contrasts−67.14/−29.11bps;12h+3.88bps changes sign under day deletion. Original **T1_INDETERMINATE** is preserved. |
| Friction |Original optimistic/base/stress T1 survivors55/24/8; base24 median loss-route drag0.5169R versus0.8548R whole-path MFE | Costs materially consume narrow-stop opportunity, but subtracting these statistics does not create expectancy. Fees/funding/stop execution were modeled, not observed. |
| Source failures |Zero strict C02-qualified historical population; no original dated BBO/depth/OI/metadata/ticker/events or executable fills for this cohort | Missing evidence prevents trading qualification. It cannot erase an observed price stop/target ordering or prove the setups would have filled. |

T1 is therefore squeezed between nearby objectives that cannot support its
ladder and rare distant objectives with poor early continuation. Increasing
target R to pass costs magnifies the reachability problem. Increasing stop
distance may reduce cost/R but simultaneously reduces structural reward/R.
Neither remedy may be applied to v1 after inspecting its paths.

### B1: a friction-capacity problem with separate price-path evidence

Original40%@1R+60%@2R gives gross1.6R. A1.5 successful-ladder ratio requires
`c_win + 1.5*c_loss <= 0.10*d`; under equal c, **c/d<=0.04**.
Median original stop0.58803% permits only **2.3521bps** symmetric round-trip
cost, versus4bps optimistic fees alone and13bps base fees+friction+funding
hypothesis. Exact notional-aware C05-K arithmetic leaves **0/32 base survivors**.
Twenty-seven of32 also have known opposing-swing obstacles; only five routes
remain before costs. This is a logical payoff-budget failure, not an estimate
of realized profitability.

The new unchanged B1 diagnostic has31 complete12h paths and one temporally
censored case. **8/31** reach original target2 before stop under both bounds;
23 stop first. Median whole12h MFE3.5277R and MAE−2.1320R are not realized
returns; some extremes occur after stop. A few favorable price trajectories
do not fix zero base-cost admissions. Preserve original B1 RESEARCH_ONLY and
do not replace its ladder with a farther target under the same version.

### R1: missing causal evidence, not an economic rejection

Original balance has `BALANCE_SPREAD_UNAVAILABLE` in all60,480 contexts.
Other overlapping reasons include59,892 missing separated edge tests,43,956
drift failures,1,332 ATR-width violations and4,326 volume-breakout vetoes.
The price restrictions appear selective, but the qualified spread-dependent
population remains unknown. There is no measured R1 setup frequency or
economic rejection. FR2 is a different5h price-range hypothesis, not a
substitute for authentic R1 spread qualification or inferred liquidity evidence.

## Reuse and the three approaches considered

The existing [C03 source assessment](../../research/c03/EXPERT_EVIDENCE.md) and
[pins](../../research/c03/sources.lock.json) were reused rather than reopening
settled engineering choices. This session additionally re-read the pinned
Drift core, break/retest strategy and LEAN Donchian source through GitHub.

| Reusable implementation / exact pin | What it actually provides | Adoption boundary and limits |
|---|---|---|
| [DriftVwapPullback](https://github.com/jalv92/DriftVwapPullback/blob/708235769c1cebc320abbdb3f064293d8b56bbec/propsim/drift_vwap_pullback.py), `708235769c1cebc320abbdb3f064293d8b56bbec` | Closed15m regime/VWAP, ordered counter-direction5m pullback, state/rearm and session-contained chronology. NQ/MNQ RTH defaults:80-point stop versus40/50-point targets. | Reuse chronology lessons, **not its policy or performance claims**. Fixed equity-index points/RTH and unpassed platform mirror do not transfer to crypto. Nine standalone selfchecks were passed by C03, not rerun/recertified here. |
| [QuantConnect LEAN](https://github.com/QuantConnect/Lean/tree/f3d841e60dfd010ee5fc293ea893e56952484108), `f3d841e60dfd010ee5fc293ea893e56952484108` | Streaming strict pivot confirmation, intraday VWAP and Donchian high/low/midpoint. Donchian updates **include current input**. Existing C03 wrappers already preserve closed-bar confirmation. | Adopt the tested local wrappers. Freeze a range before later sweep/break; never use a later Donchian update as the original boundary. LEAN supplies primitives, not a proven complete reversal/acceptance edge. No new C# engine or upstream test pass claimed. |
| [break-retest-daytrader](https://github.com/Smashthehedgehog/break-retest-daytrader/blob/e1f6ec54be8e87aa3349cf0e924da8e479d32294/strategy.py), `e1f6ec54be8e87aa3349cf0e924da8e479d32294` | Persistent opening range→break→tick touch→closed-bar volume confirmation and explicit failure/reset. | Useful state chronology comparator; execution/database coupling, equity-session scope and enclosing-bar/tick semantics do not implement this contract. Not imported; its upstream tests were not run here. |

The known retrospective SMC comparators remain unavailable under their existing
pins; no OB/FVG/absorption/liquidation evidence is manufactured. Freqtrade's
order-flow grouping and full engine cannot supply missing original trades or
fix frozen target geometry. Its live-owner rejection remains separate from
potential future research-engine reuse. This bounded diagnostic needs no second
engine or dependency: **Adopt** C04 sources and C05 statistics; **Configure**
TA-Lib/context and declared costs; **Wrap** existing swing/VWAP/path functions;
**Build only** the two proposed event reducers, source-linked comparison and
report. No production reducer or approved registry entry was added.

| Selection criterion | Structural pullback continuation (PC2) | Failed range-break rejection (FR2) | Compression→acceptance comparator |
|---|---|---|---|
| Market mechanism | Resumption after value pullback in aligned trend | Failed first excursion rotates toward balance center | Volatility contraction releases into directional acceptance |
|12h frequency |392 formations/70 confirmations,22 confirmation days |361 range arms/11 sweeps/3 confirmations | Original B1 has562 formations/32 confirmations; **not** a measurement of a new compression policy |
| Causal entry | New15m pullback, then first later5m break | Qualified frozen range, first breach/reclaim, exact next close | Would need explicit pre-break compression, frozen boundary and first acceptance; no outcome-selected retest |
| Invalidation feasibility |45m extreme±0.25ATR15, median confirmation stop0.5860% | Sweep extreme±0.25ATR15, median0.4441% | Wider meaningful stop reduces reward/R; B1's fixed ladder cannot just be inherited |
| Reachable structural objective | Nearest prior swing/20h extreme; reject outside1.8–4R | Nearest opposition no farther than midpoint | Nearest obstruction must precede measured-move projection |
| Friction | Only3 geometry passes;2 base survivors | Zero geometry/cost survivors | B1 gives direct evidence against unmodified1.6R ladder; no independent new feasibility result |
| Legitimate measurements | Bars/VWAP/ATR/confirmed swings sufficient for R0 only | Bars sufficient for price rejection, not liquidity/absorption | Compression can be bar-derived; real acceptance/fill strength still needs qualified evidence |
| Independence from old assumptions | Different45m stop, single structural exit, hard4R ceiling |5h price balance rather than original20h spread-qualified R1 | A new fixed-R breakout with B1 timing would remain heavily dependent on failed assumptions |
| Complexity | Existing context + short reducer | More range/first-breach attrition but still bounded | Additional compression, event and retest state; little justified incremental evidence now |
| Falsifier / selection | Frozen minimum-sample/cost/path/matching rules; **screened** | Same rules; **screened** | Defer; no third version, parameter search or outcome calculation |

These are credible market-behavior hypotheses and reusable implementations,
not audited profitable expert systems. There is no claim that a public project
has a transferable verified track record. The simpler compression alternative
was considered before custom work and was not forced into a third experiment.

## What the two new versions taught us

**PC2.structural-pullback.v0.1** (`2b697cc7659bafcd69612cc1cdbd878b18d890214cca8753364c304a75609680`):
70 confirmations include37 whose frozen target is already behind confirmation;
67 fail the1.8–4R interval (overlapping memberships). **240/392 formations**
already have T at/before their required confirmation boundary; **30/70**
confirmed setups inherit this logically incompatible geometry. Another seven
cross T during confirmation. The median target confirmation age is125.96h;
the existing swing provider deliberately retains previously broken correct-side
levels. Their economic relevance is an **unvalidated modeling assumption**,
not authentic present resting liquidity. This is a target-lifecycle question,
not permission to skip a nearby obstacle and pick a profitable farther level.

Only3 confirmations have valid geometry; two pass base costs,2.86% of70,
on two symbols/two days. One (BNB September10) stops before a later target;
one (XRP September29) reaches target first. Neither has an exact past control.
The favorable XRP path does not certify an edge. The70-confirmation population
has18 matched controls on11 days: equal-day1h/4h/12h differences
**+3.24/−0.77/+69.00bps**. Only the last horizon is consistently positive
under event-day deletion; these rejected-geometry-inclusive contrasts cannot
replace the admitted population. Two late cases are12h censored.

**FR2.failed-range-break.v0.1** (`c1c21cd63612a5278e0578e9188fa0d15cf288dfccce43a7392bfa44435a54cc`):
321/361 arms expire without sweep;29 fail first-breach reclaim/penetration,
seven fail distinct confirmation and one touches its frozen stop before
confirmation. Only three confirm; target distances are **−0.00836R SOL,
0.04947R DOGE and0.71514R BTC**. All fail geometry; the two forward targets
fail even optimistic costs. No exact controls exist for those three cases.
This is measurable price-only attrition and unsuitable geometry, not a source
dependent inability to observe the trigger. It is also below the declared20-
confirmation rejection threshold: **do not relabel it REJECT retrospectively**.

Both versions fail the frozen ADVANCE gate, and neither meets the compound
minimum-sample REJECT trigger. Thus **REVISE_BEFORE_IMPLEMENTATION** is the
correct decision for both, rather than a manufactured winner or statistically
unsupported universal rejection. PC2 ranks first on its greater measurable
population and two plausible geometries; neither has adequate executable or
independent economic evidence. Do not optimize either on these paths here.

## Owner decision and exact Sessions02–06 handoff

Two concrete choices, both respecting unchanged risk/authority:

| Choice | Consequence | Recommendation |
|---|---|---|
| A: approve the exact listed v0.1 policy hashes for research implementation after S02 | Session04 would reproduce a version with only2/0 base survivors and absent matched survivor evidence. Owner approval would still confer no qualification or trading authority. | **Do not select on current evidence.** |
| B: accept this research milestone and HOLD both v0.1 activations | Preserve the contracts, failed populations and October reserve; no strategy-specific source spend, collector or automatic full replay. PC2 is the first family to reconsider only under a separately authorized/frozen revision addressing level relevance and entry/objective compatibility. | **Select B.** |

No permission request blocks the present authorized PR. Approval of this study
is distinct from approval of a policy version. New source sampling, future
policy versions and any data investment need their own exact owner decisions.
The proposed single100% structural exit is itself a policy change from original
staged ladders and is **not implemented for execution** by this ADR.

1. **Session02:** resolve source field/measurement semantics and issue22 through
   its already assigned contract work. Consume `source_acceptance_contract` in
   the evidence and the preregistration A01–A10 table. Preserve C02 production
   behavior until owner approves an exact clock version; save raw event,
   arrival/availability and sample clocks separately. No current metadata
   backdating, repeated quote reuse or candle-derived order flow.
2. **Session03:** the approved source pipeline may accept only independently
   supported original artifacts through existing G/H interfaces. Missing
   metadata, units, timing, events, fee/fill/approval evidence remains missing.
   Source acceptance alone cannot promote PC2/FR2 or resurrect original T1/B1.
3. **Session04:** no approval inferred for either v0.1. The machine contract
   gives exact frozen entry/exit formulas and source requirements if the owner
   explicitly chooses A; reproduce all failed geometry, not only2 survivors.
   A change to target lifetime, formation headroom, confirmation or stop is a
   **new version** requiring a fresh preregistration before its own diagnostics.
4. **Sessions05–06:** strict R1/R2 requires accepted source/owner version plus
   the preregistered sample, controls, chronology and objective economic gates.
   Minimum100 admissible intended signals,30 market days and30 nonoverlapping
   shared-market components,4symbols/2liquidity cohorts do not exist here.
   Primary4h matched contrast and full-policy net initial-monetary-R require
   joint24h-market-block97.5% lower bounds above zero for the two-candidate
   family, plus declared PF/drawdown/stress screens. Do not replace block
   independence with signal count. October1–14 validation and15–31 evaluation
   can falsify a frozen approved policy later; their length cannot guarantee
   adequate qualification. No unapproved data extension is implied.

All future R2 must include whole-universe availability, rejected/nonchosen
candidates, human approval attrition, IOC10s deadline, adverse entry bounds,
quantity rounding, actual fees/funding, partial/nonfills, original protection,
two-position allocation and first-fill11h55/12h exits. There is no historical
account/quantity in this study. Per-trade0.25%, aggregate0.50%, isolated2x,
one writer, one-use approval, no widening and no losing-position additions
remain binding. The explicit source/economic stop conditions in preregistration
halt new expenditure now; the deferred210-day/$350 study remains deferred.

**Exact future source-cohort annex (proposed after this September screen,
unused in S01, before reserved outcomes):** the evidence's
`source_acceptance_contract.future_liquidity_cohort_annex` fixes two research
strata, `Q20_100` for fresh original24h quote turnover **20M<=Q<100M USDT** and
`Q100_PLUS` for **Q>=100M USDT**, assigned only after every unchanged C02 gate
passes at that decision. Missing original ticker means UNVERIFIED/no cohort;
never classify by symbol reputation or daily candle volume. Require at least25
admissible intended signals on eight market days **in each** stratum, in
addition to the frozen overall minimums. Future strict controls also match this
point-in-time stratum exactly, without fallback. These are transparent sampling
and adequacy definitions, not new predictive indicators or relaxed eligibility.
The annex requires explicit owner acceptance with the Session02 source contract
before strict R1/R2. It does not amend the hashed September selection protocol
or confer independent validation on this post-development design choice.

## Delivery and acceptance

One bounded diagnostic script, focused math/causality/evidence tests, one frozen
preregistration, this ADR and one generated empirical report with two lossless
compressed ledgers. Raw84 archives stay outside Git. The one reproduction
command is in the empirical report; existing pinned dependencies are unchanged.
GitHub PR/final head and observed CI are recorded in its metadata and final
handoff. Local/full CI results and exact artifact hashes are recorded in the
same-PR journal entry. No self-merge or independent acceptance is claimed.

Source gaps, small matched sample and uncertain execution are material limits.
They do not diminish the concrete negative design result: **confirmation,
stop scale and nearby objective cannot be designed independently**. This
session completed both declared screens; it leaves no unfinished second
hypothesis to an unspecified session and does not use October as a rescue set.
