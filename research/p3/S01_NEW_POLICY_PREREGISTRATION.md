# S01 — Frozen exploratory development protocol

Status: **PROPOSED / RESEARCH_ONLY**. Base `b06079077850bf6cbc176d010e0ccf3bc42b032a`.
This document and [machine contract](S01_CANDIDATES.json) are committed **before
new forward-path calculations**. Each candidate version is identified by SHA-256
of its canonical JSON candidate definition **and the common terms** (sorted keys,
compact separators, UTF-8). The whole machine contract and this document also
have independent byte hashes in the evidence. No result may change these rules.
September already informed design through C05-K/L: this is **exploratory
development evidence**, not an independent preregistered out-of-sample experiment.
Only the two versions below are screened. Compression breakout is a design
comparator, not a third screened or registered policy. Original T1/R1/B1 stay frozen.

## Population, chronology and references

Use the existing C04 manifest, SHA-256
`6a34aae6b37ec9b48aa166dda52cd578a86776ef8b36be05aaaa5bf42f51058a`,
the seven fixed BTC/ETH/BNB/SOL/XRP/ADA/DOGE USDT perpetual symbols, all September
5m availability cutoffs. July–August is source-only warm-up. Restore absent
July–September pinned archives once outside Git; check size, ZIP/member hash,
schema and continuity through the existing C04 loader. Do not load any October
source or outcomes. Archive bar availability = inclusive close+1ms proxy;
publication, historical ingestion latency and revisions remain unverified.

Use 4h bias, 1h ADX/EMA/ATR-percentile, 15m structure and 5m confirmation.
Adopt existing C03 context/ATR, C02 session VWAP, C03 confirmed1h swings and
C05-J history limits unchanged. Evaluate from available prefixes only. Strict
swings require three right-hand hourly closes; save their **confirmation** time.
Ranges freeze before the first subsequent sweep. Save all native source IDs
scoped by symbol and interval; record level source windows and available-at.
No continuous source gaps may be filled/interpolated. An append of later bars
must not change any earlier formation, control, indicator, level or decision.

Reference `E` is the original hypothetical confirmation close, **not an entry**.
Set direction `s=+1` long, `-1` short, fixed stop `S`, distance `d=s(E-S)>0`,
fixed target `T`, reward `g=s(T-E)/d`. Both candidates use a single 100% exit
at nearest declared structure, **1.8<=g<=4**, stop fraction `0<d/E<=0.02`.
Missing target, wrong side, outside bounds or any known nearer opposition
rejects geometry; never replace the target with a farther one or widen a stop.
Keeping rejected confirmations and their paths prevents winner-only selection.

## PC2.structural-pullback.v0.1

Economic mechanism: pullbacks to session value within a directional trend may
resume toward an already observed opposing level. A 45m original pullback
extreme and quarter-ATR15 buffer allow ordinary five-minute noise; no favorable
post-stop movement is credited. This is a different proposed stop/exit policy,
not an improved historical T1 result. Its wider stop may make reward insufficient.

At a **new** completed15m bar `q`, require READY C03 TREND_UP/BULLISH for long
(TREND_DOWN/BEARISH for short), ATR-percentile<95. `q` must have a counter-
direction body. Let `X` be the lowest low (long) / highest high (short) of the
latest three closed15m bars including `q`, `A=ATR15` at formation and `V` the
current UTC-session closed5m VWAP. Require `abs(X-V)<=0.50A` and
`0<=s(q.close-V)<=A`. Missing/incomplete session VWAP rejects formation.
Stop `S=X-s*0.25A`. Freeze `q.high/q.low`, A, ATR5, X, V and all source keys.

Target inventory: all formation-confirmed opposing strict1h swings within
the unchanged hourly history, plus highest high / lowest low of latest20 closed
hours. Select the nearest level **strictly ahead of formation close**, deterministic
tie by level ID. Freeze it; if confirmation has already crossed it, reject.
It cannot jump to another level. At confirmation, any newly known nearer
opposing swing rejects the route rather than moving T.

First of the next **three** distinct5m closes with a directional body and
close beyond `q.high` (long) / `q.low` (short) confirms. Stop touch (including
same confirmation candle) wins as pre-entry invalidation. Missing context,
extreme volatility, opposite4h bias or UTC-session change cancels; ordinary
non-opposite regime changes do not erase an armed setup. Expire after third
bar, accepting a valid third-bar confirmation before expiry. One active setup
per symbol/side; never revisit a completed15m formation bar.

## FR2.failed-range-break.v0.1

Economic mechanism: a failed first excursion from a previously tested,
low-drift price balance may rotate back to its center. This detects **price
rejection**, not stop hunting, liquidation, absorption or measured liquidity.
It is explicitly distinct from original R1's 20h spread-qualified balance.
No R1 spread requirement is removed or passed by this experiment.

On a new15m close require READY context, ADX1h<25, absolute normalized1h EMA
slope<=0.30, ATR-percentile<95, and no latest15m close beyond preceding20 bars
with RVOL>=1.5 in either direction. Build `H,L,M` from latest20 closed15m
bars **including** this already closed bar; future sweeps start later. Let
`W=H-L`, `A=ATR15`. Require `2<=W/A<=8`; absolute first-five versus last-five
mean-close drift<=0.20W; at least two tests of **each** edge separated by>=3
bar indices. Edge tests: high>=H-0.25A / low<=L+0.25A and bar width<=0.75W.
Freeze these values and source keys. This is price balance, not C02 eligibility.

Search the next3 closed5m bars for the **first** own-edge breach. For long,
`low<L` must have `0.10A<=L-low<=0.75A` and `L<close<H`; short symmetric.
A first breach failing reclaim/penetration, or a bar with `low<L AND high>H`,
invalidates. No breach through third bar expires. Freeze the first sweep low/
high; stop is sweep extreme minus/plus `0.25A`, using original formation A.
Exactly the next distinct5m bar must stay closed strictly inside H/L, have
directional body, and close above sweep high / below sweep low. Stop touch
first (including same bar), missing/extreme context or failed confirmation
invalidates; no later retry. A third-bar sweep permits only fourth-bar confirmation.
Ordinary regime/bias change alone does not cancel an already frozen range.

Target is the nearest formation-confirmed1h opposing swing strictly ahead of
formation close **and no farther than midpoint**, or M itself when directionally
ahead. If midpoint is behind formation close, no target exists for that side.
Freeze that target before sweep. Do not select a different target after seeing
confirmation. Any new nearer opposing swing at confirmation rejects route.
One active range per symbol/side; only new15m observations may re-arm.

## A01–A10 and source acceptance

| Family | Proposed role | Legitimate September availability / later source gate |
|---|---|---|
| A01 flow/CVD | RECORD_ONLY, no decision vote | Missing continuous original aggressor trades; never inferred from candles |
| A02 VWAP | MANDATORY PC2; RECORD_ONLY FR2 | Closed5m HLC3*base-volume UTC-session approximation, not trade-exact; require full session, nonzero volume |
| A03 structure | MANDATORY narrow swing/range/stop | Original bars and C03 strict confirmation only; advanced SMC UNAVAILABLE |
| A04 liquidity/liquidations | C02 execution VETO; liquidations RECORD_ONLY | BBO/sequence-complete depth, dated units and executable size missing; no price-only pass |
| A05 ICT/FVG/OB | RECORD_ONLY | UNAVAILABLE; no retrospective labels used |
| A06 OI/funding/basis | C02 OI VETO; funding cost requirement | Dated OI units, actual measurement clock and contemporaneous mark missing; original settlement/quantity needed for full cost |
| A07 price action | MANDATORY | Original closed-bar chronological formation/sweep/confirmation; actual arrival clock still missing |
| A08 profile | RECORD_ONLY | Trade-price bucket history missing; never substitute candle volume profile |
| A09 trend | MANDATORY | Existing TA-Lib14/50 C03 context, 735h/200x4h history and frozen truncation |
| A10 volatility/balance | MANDATORY | ATR from same closed prefixes; FR2 explicit price-balance terms, not certified liquidity |

Strict source contract later: unchanged C02 dated lifecycle/status/USDT-linear
units, age/turnover and tick/step/minimum filters; fresh ticker; 60 accepted,
distinct causal spread slots preserving event/arrival/sample clocks **after**
Session02/#22 owner decision; BBO/depth freshness and validated0.20%-mid depth
notional; independent OI unit/measurement/notional evidence; original verified
news/event coverage/blackouts; complete correction/coverage and actual feed
availability. Reuse C05-G/H manifest/artifact checks, not newly asserted schemas.
No current metadata backdating. All missing mandatory source checks veto entry.
Price R0 does not assert any of these pass. Record all ten families honestly.

## Authorization, exits, costs and quantities

Both are PROPOSED fixed-stop/single-target management baselines; no elective
trailing, breakeven, partial TP, scale-in, stop widening or retrospective thesis
exit. Emergency protection/data handling and absolute time exits remain mandatory.
This simplification requires explicit owner policy approval and later full-policy
comparison; it is not an edit of v1.5 original staged ladders. New opposing levels
never move a stop/target farther away. Supervisor keeps original protection.

A bounded preapproved plan binds exact policy/feature/anchor/management hashes,
one-use owner nonce, side, fixed stop/target and bounded confirmation-close
entry formula, maximum quantity/risk, expire/cancel rules. Approval expires by
setup expiry (FR2 no later than fourth5m close); maximum request validity90s.
After confirmation submit adverse-bounded IOC by confirmation+10s, or skip.
Adverse cap=min(2 historically valid ticks,0.10 frozenATR5,0.05 originalR).
Recheck cost/geometry/filters at worst admitted price, consume approval and
reserve risk atomically before one writer submits. Without approval, fresh
quotes/depth or dated filters, there is no executable opportunity. Candle close
cannot prove availability or fill within10s. 0/5/10s is unresolved;15/60s is late.

Sizing/risk remains <=0.25% reconciled equity per trade, <=0.50% aggregate
pending/open modeled stop risk, two slots, one position per symbol, isolated
<=2x, daily1% entry halt. Use existing C01/C03 loss-inclusive quantity arithmetic,
step rounding, equity/margin/notional caps. R0 reports **per base unit only**,
with no account, quantity or fill assertion. Initial protective stop always S;
after actual initial fills become terminal freeze actual initial risk; first
partial fill starts protective operations and the absolute clock. Start flatten
attempt at first confirmed fill+11h55; hard12h emergency; never reset clock.

Reuse C05-K `cost_screen`: optimistic/base/stress fees **2/5/10bps per side**,
additional round-trip friction **0/2/5bps**, nonnegative funding debit hypothesis
**0/1/3bps**, not an upper bound. Winning fees use target notional; losing fees
use stop notional. Require `(s(T-E)-c_win)/(d+c_loss)>=1.5` per base unit.
One100% leg, no old R1 midpoint extra test. With symmetric c the admissible
cost is `(g-1.5)/2.5` originalR, distinct from likelihood of reaching T.
Also record entry shifts0/.025/.05 originalR with S/T fixed; no survivor
replacement. Funding requires original12h exposure qualification later; the
C05-K monthly maxima are ex-post stress context only, never event-level cash flow.

## Outcome-blind matching and forward diagnostics

Before outcomes serialize/hash all formations, confirmations, rejections,
causal metadata pool and matches. Seed20261027 existing `matched_controls`,
one control per confirmation, replacement allowed, no fallback. Exact symbol,
side, candidate regime (PC2 trend direction / FR2 PRICE_BALANCE), ATR-percentile
quartile and UTC four-hour session; September controls12h..7d earlier, with
complete12h September horizon. PC2 nontrigger excludes current active/terminal
setup and fresh formation on either side. FR2 excludes current sweep/pending
or terminal trigger on either side; unswept armed range is allowed. FR2 control
must itself meet price-balance formation conditions at its latest15m snapshot.
Never exclude a control because a future setup appears. Retain every candidate
pool ID/count/hash, exclusions and unmatchable event. Control stop/target
fractions copy case geometry about own close for normalization only; neither
those levels nor the control is a tradable policy.

Horizon15m/1h/4h/12h, exclude confirmation candle and begin at next5m open.
Require contiguous forward bars; clip at October1 00:00UTC. Split-crossing
horizons are censored; no continuation into October. Preserve original12h
split purge/embargo. All confirmed/rejected geometry gets signed-close bps,
MFE>=0/MAE<=0 in originalR, source-key-linked stop/target touch intervals,
target-first LOWER=strictly earlier candle and UPPER=earlier-or-same candle,
stop-first and ambiguous/unresolved counts. Also report target by11h55, first
bar/15m/1h stop concentration, conditional paths and delay/cost sensitivities.
MFE after stop is **not success**. No assumed intrabar paths, fills, realized
P&L, true win rate or net strategy expectancy. Invalid targets have signed
paths but no successful target geometry. Representative cases: chronological
first base survivor, first stop-first base survivor, first target-first base
survivor and first rejected confirmation; selection rules fixed here.

Report all formation/confirmation/expired/invalidated/end-censored counts,
geometry reason membership, scenario cost versus cost+geometry+route counts,
symbols/days/regime/session, overlaps within/across candidates and controls,
day concentration Kish, reuse, match attrition, equal-event-day paired signed
1h/4h/12h differences and leave-one-event-day-out ranges. Matching is
observational, not causal identification: trend/balance selection and missing
controls can confound. Correlated shared market days are not independent trials.
Suppress CI/p-values below30 market days **and**30 nonoverlapping shared-market
12h components; this month is descriptive only. No multiplicity-corrected
significance or reliable edge claim is possible from these design-used data.

## Frozen S01 decisions and later qualification

Apply in order to each version:

1. SOURCE_DEPENDENT_NOT_YET_DISCRIMINATED if essential price trigger is
   legitimately unmeasurable (missing execution facts alone do not erase R0).
2. REJECT_ECONOMIC_HYPOTHESIS if >=20 confirmations and **zero** base-cost+
   geometry+route survivors, OR >=20 complete12h base survivors and favorable
   target-before-stop **UPPER<=20%**. Stop this version; do not optimize it here.
3. ADVANCE_TO_SOURCE_QUALIFICATION only if >=20 complete12h base survivors,
   >=8 UTC market days, >=4 symbols, base survivors>=10% of confirmations,
   target-before-stop LOWER>=35%, >=50% matched on>=8 event days, positive
   equal-day signed case-control differences at1h AND4h, nonnegative at12h,
   and4h leave-one-event-day-out lower>0. This funds no source route by itself.
4. Otherwise REVISE_BEFORE_IMPLEMENTATION, stating the exact unresolved design
   or sample problem; no same-path retuning. Small sample alone cannot reject.

Rank ADVANCE, REVISE, SOURCE_DEPENDENT, REJECT; ties by larger4h equal-day
matched contrast, then lower base costR, then PC2. A priority is a research
decision, never automatic implementation. If both reject, recommend no candidate
activation and halt new strategy-specific data expenditure.

Before strict R1/R2 later: owner approval of exact version/source-clock contract;
freeze signal+management+costs; minimum100 genuine admissible intended signals,
30UTC market days,30 nonoverlapping shared-market components,4symbols including
>=2altcoins and2 point-in-time liquidity cohorts with predefined source-based
membership; >=50% exact controls without relaxed fallback. These are governance
minimums, not claims of adequate power. October1–14 validation and15–31 untouched
evaluation remain reserved, with12h purge/embargo; their short length cannot
automatically meet the minimums. No extra data acquisition is authorized.

Later R1 continuation requires conservative target reachability>=35%, positive
1h/4h matched contrasts with simultaneous joint-market24h block bootstrap
97.5% lower bound>0 for the primary4h contrast (two-candidate family), and
documented approval/10s executable feasibility. R2 requires full scanner/selector,
one-use approval/IOC/nonfill/partial/stop/target/time/portfolio replay, actual
fee/funding qualification and independently supported execution models; positive
net mean initial-monetary-R with joint24h-block97.5% lower>0, provisional
profit factor>1.20 and equity drawdown<=10%, no hidden symbol tail failure,
stress net mean>=0, original risk unchanged. No inferential interval when
independence/source requirements fail. Freeze any future amendment **before**
opening reserved outcomes; an amendment consumes research degrees of freedom.

Halt source expenditure on failed source-clock/unit/coverage acceptance, failed
S01 rejection, fewer than20 reachable base cases here, absent owner version
approval, unqualified rights/price/host, or later conservative out-of-sample
economic falsification. Do not revive the deferred210-day/$350 study implicitly.
Owner chooses approval of exact proposed version(s) for S04 after S02 source
review, HOLD, or rejection. This session implements only this bounded diagnostic;
no approved policy registry, production policy, C02, order or account changes.
