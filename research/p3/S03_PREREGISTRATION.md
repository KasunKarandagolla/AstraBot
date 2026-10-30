# S03 — Frozen two-hypothesis development experiment

PROPOSED / RESEARCH_ONLY. Base `654b6c96aefcd537d7f10bf10361ee896c515f97`.
Commit this protocol and S03_CANDIDATES.json before any new forward-path run.
September has already influenced S01 and this design: these are exploratory
development results, never independent validation. No third candidate, parameter
search, best-symbol selection, or same-sample replacement after outcomes.

## Mechanisms and reuse decision

PC3.value-acceptance.v0.1 tests whether **early acceptance after a value pullback**
can retain useful reward that PC2's break of the whole 15m bar destroyed. Keep
S01's qualified higher-timeframe trend, contemporaneous VWAP and 45m structural
invalidation. Require headroom at formation and an upper entry boundary. Replace
the old indefinitely reusable, already-crossed swing objectives with *unvisited
since confirmation* opposing swings. This is a new testable price-level policy,
not evidence of unobserved resting liquidity. Its vulnerability is weaker early
confirmation and still-too-tight invalidation in ordinary noise.

FA3.prior-day-failed-auction.v0.1 tests a different mechanism: the first attempt
outside an entire previous UTC day's price range fails, price returns inside,
then a distinct bar accepts the old range. Seek the nearest still-unvisited
opposition or previous-day midpoint. A directional higher-timeframe veto avoids
fading a clearly opposed 4h trend. Unlike FR2, this does not need a rare five-hour
two-edge balance or a break beyond the entire sweep candle. The previous day is
an observable price auction, not a certified value profile, liquidation map or
R1 stable balance. A sustained new trend defeats this mechanism.

Re-read pinned LEAN DonchianChannel.cs (`f3d841e60dfd010ee5fc293ea893e56952484108`)
and DriftVwapPullback's executable core/selfchecks
(`708235769c1cebc320abbdb3f064293d8b56bbec`). LEAN includes the current bar, so
freeze the completed previous day *before* the excursion; its channel is not an
entry strategy. Drift consumes a regime transition on the first counter candle,
enters next open and uses 80-point stop versus 40/50-point targets in NQ/MNQ RTH.
Those rules neither implement this market nor certify its economics. Adopt the
existing C03/TA-Lib context, C02 VWAP, C03 strict swings and C05 cost/path/control
functions. Build only these two short chronological reducers and a causal
visited-level wrapper; neither upstream engine supplies our immutable census,
cost screening and approvals. No new dependency or production policy.

## Data, clocks and immutable identity

Only the original 84 July–September C04 archives (266,616 bars), manifest hash
`6a34aae6b37ec9b48aa166dda52cd578a86776ef8b36be05aaaa5bf42f51058a`.
Restore absent pinned bytes once outside Git; verify archive/member hashes,
schema, counts and continuity with the existing loader. Retain actual current
restoration metadata separately from the original manifest retrieval times.
July–August is history, September all seven symbols is development. Exclude
October archives before opening files. Never open reserved October outcomes.
Use close+1ms availability proxy, explicitly not original feed arrival.

Existing HISTORY_LIMITS and TA-Lib/strict-three-right-hour swing confirmation
are unchanged. At each cutoff use only available closed prefixes. Hourly swing
is visited if **any closed hourly bar after its confirmation** touches/crosses it,
or a closed 5m bar since the last completed hour touches it. Include equality.
Do not classify the pivot's own seven-bar source window as later visitation.
Save active and excluded level IDs and a source-span hash. Original S01 levels
remain unchanged. New objective inventory selects the nearest active opposing
swing strictly ahead of formation reference, plus the declared boundary below,
tie by level ID. Freeze it; never move it after confirmation. Check for new
nearer active opposition at confirmation. No farther-target rescue.

IDs bind strategy/version/symbol/side/formation time; native candle IDs are
scoped by symbol AND interval. Save source keys, context spans and anchor IDs.
All formations, rejected raw formations, transitions and confirmations remain
in the ledger. Main policy and the predeclared descriptive ablation populations
share the raw-formation schedule; no outcome-dependent rearming.

## PC3 exact reducer (both directions symmetric)

At each new closed 15m `q`, use S01 `pc_formation` unchanged: READY TREND_UP with
BULLISH 4h bias for long (down/bearish short), ATR percentile<95, counter body,
latest three 15m extreme X within 0.50 ATR15 of full current-session bar VWAP V,
and `0 <= s*(q.close-V) <= ATR15`. `s=+1` long, -1 short.
Freeze `A=ATR15`, `ATR5`, `S=X-s*0.25A`, and **last closed 5m high/low** as
confirmation boundary B. Target = nearest active opposing swing or preceding
20 closed-hour extreme strictly ahead of q.close. This rolling extreme includes
the latest closed hour but never later bars.

Worst allowed reference `U=q.close+s*0.25A`. Primary formation veto if target
missing, not ahead of U, or C05 base successful-target net RR at U<1.5. No
formation upper-4R veto: enforce 1.8–4R on actual confirmation reference instead.
Store raw formations even when vetoed; shadow transitions permit the frozen
headroom ablation. Within next three distinct 5m closes, first directional body
closing beyond B confirms; it need not break q's 15m extreme. Stop touch on any
pre-entry/confirmation candle wins and invalidates. Opposite 4h bias, missing or
extreme context, session rollover invalidate. Third-bar confirmation wins before
expiry; otherwise expire. Confirmation beyond U is an entry-chase rejection,
not a delayed fill. Target crossed, closer new opposition, invalid stop, stop
fraction>2%, gross target R outside 1.8–4 reject. No stop widening.

## FA3 exact reducer

Use exactly 24 contiguous original hourly bars of the **previous UTC day** to
freeze H, L and M=(H+L)/2 before today's first bar. Keep a seen-edge flag for
each side/day; the first breach consumes that edge even if rejected. Both-edge
breach consumes both and rejects. If the day starts outside, first breach still
consumes the edge; do not select a later prettier reclaim. A breach at the first
September cutoff may reference August31, which is source history only.

At first closed5m breach below L (long) / above H (short), retain a raw formation.
Primary veto unless READY, ATR-percentile<95 and 4h bias not BEARISH (long) /
BULLISH (short). Require penetration 0.10–1.00 current ATR15, close strictly
inside H/L, and directional body; otherwise mark REJECTED immediately. Freeze
formation ATRs and S=sweep extreme-s*0.25ATR15. Target nearest active opposing
swing not beyond M, or M, strictly ahead of reclaim close. Freeze U=reclaim
close+s*0.25ATR15; same formation-time missing/headroom base-cost veto as PC3.

Exactly the **next** distinct 5m close must stay strictly inside H/L, have a
directional body, close farther into the range than the reclaim close and beyond
the frozen breached edge by at least 0.10ATR15. No whole-sweep-high/low break.
Stop touch first, missing/extreme context, opposite 4h bias or day rollover
invalidates. Failed next-bar acceptance expires. Confirmation beyond U rejects.
Apply identical final geometry, route, 1.8–4R and cost rules. A visited old swing
is not asserted to be a fresh obstacle. Midpoint is a price objective, not proof
that price will return. At most one excursion per side per UTC day.

## Costs, controls and outcome-blind seal

C05-K fees 2/5/10bps per side, round-trip friction 0/2/5bps, funding debit
0/1/3bps; target and stop notionals correctly differ. Final reference E is a
hypothetical close, not a fill. `d=s*(E-S)`, `g=s*(T-E)/d`.
`scenario_net_RR=(s*(T-E)-c_win)/(d+c_loss)>=1.5`.
Additional fixed 0/.025/.05R adverse entry, and funding debit5/10bps stresses
keep S/T fixed and never replace cases. Recalculate geometry as well as costs
after entry shifts. Funding is an assumption, not original event cash flow.

Controls: one per every diagnostic confirmation, replacement allowed, fixed
seed20261029. Exact symbol, side, **current C03 classification AND 4h bias**, ATR
quartile, UTC four-hour session. Past12h..7d, complete September12h horizon;
READY nonextreme and no active, terminal or fresh raw setup of that candidate
on either side at cutoff. No relaxed fallback. Controls do not need the setup
trigger/location (that is the treatment), but must share directional permission
(PC3 matching trend; FA3 not opposite bias). No future-trigger exclusions.
Record pool IDs/count/hash, unmatched cases, reuse and control-to-case covariate
differences (ADX, slope, stop normalization). Future returns never select matches.
Control geometry copies case stop/target fractions for normalization only.

Serialize and hash full causal census, economics, exclusions and matches BEFORE
new paths. Then reuse C05-L/S01 `price_path`, `calculate_paths`, `group_summary`
and equal-event-day matched contrasts for 15m/1h/4h/12h. Exclude confirmation
candle, next5m open starts path; complete contiguous original bars only. Clip
at October1, censor split-crossing horizons; never import October for completion.
Report target/stop intervals, conservative/optimistic same-candle bounds, signed
close bps, MFE>=0/MAE<=0, stops by5m/15m/1h and target by11h55. Post-stop MFE
is not success. Candle ordering is not fill ordering or a profitability model.

## Falsification, ablations and fixed selection

For each candidate report all raw formations; primary accepted/rejected arms;
confirmation, invalidation/expiry and reason census; all diagnostic confirmations
and primary/base/rejected paths. Descriptive ablations: (a) remove formation
headroom veto, (b) remove entry cap, (c) remove both, (d) FA3 remove 4h-bias veto.
These are fixed nested diagnostic masks on the SAME frozen raw schedule, not
extra candidate versions eligible for promotion. Final geometry/cost/route
always apply. Do not switch the selected policy to a better ablation afterward.
Record prior PC2/FR2 source-identical results; PC3 is the instantiated repair of
the project-lead reference, FA3 is the competing mechanism. No claim the verbal
reference is an independently executable third policy.

Break down long/short, symbol, UTC day, regime, volatility quartile and session;
record overlaps and Kish concentration. Equal-day1h/4h/12h paired contrasts and
leave-one-event-day-out ranges; no inferential p-values/CI from this design-used
one-month sample. Report unpaired selection and weaker-control imbalances.
Cases selected chronologically: first base survivor, first base target-first,
first base stop-first, first late/behind-target rejection, first failed acceptance,
first formation-headroom veto and first adverse-bias refusal. Save source IDs,
not just favorable anecdotes. Explicitly report missing example classes.

Gate is at least the S01 reference: >=20 COMPLETE12h base survivors, >=8 UTC
days, >=4 symbols, survivors>=10% primary confirmations, conservative target
first>=35%, >=50% exact matches on>=8 event days, positive equal-day1h AND4h,
nonnegative12h, **4h day-deletion lower>0**. All are conjunctive. Apply REJECT
if >=20 primary confirmations with zero survivors, or >=20 complete base cases
with favorable target-first UPPER<=20%. ADVANCE_TO_R1_SOURCE_QUALIFICATION only
if all gates pass. Otherwise REVISE_BEFORE_R1 only for demonstrable geometry/
population improvement with a specific falsifiable correction; otherwise REJECT.
SOURCE_DEPENDENT only if the actual price mechanism cannot be measured, not as
an excuse to discard adverse OHLC evidence. Rank by verdict, then larger4h
matched contrast (missing ranks last), then larger complete base population,
then PC3. No ADVANCE by pooling candidates or ablations.

## Source, risk and later approval contract

A01 RECORD_ONLY unavailable original aggressor trades; A02 MANDATORY bar-VWAP
PC3, RECORD_ONLY FA3; A03 MANDATORY narrow confirmed/unvisited price structure,
advanced SMC unavailable; A04 mandatory execution depth VETO, liquidation record
only; A05 RECORD_ONLY unavailable; A06 mandatory C02 OI VETO and funding cost
qualification, original measurements missing; A07 MANDATORY causal price action;
A08 RECORD_ONLY unavailable trade profile; A09/A10 MANDATORY C03 trend/ATR and
volatility. Never synthesize missing flow/depth/OI/news from candles.

S02 acceptance stays 7 PARTIAL/2 UNVERIFIED/0 SOURCE_ACCEPTED. Reuse its exact
G/H source interfaces and proposed clock only after appropriate approval; C02v1
unchanged. Source-backed R1 needs dated instrument lifecycle/units/filters,
fresh turnover/BBO, distinct accepted spread samples, sequence/quantity-correct
depth, genuine OI measurement/mark, events/publication coverage and actual
availability. Price-only screens assert zero strict eligible historical trades.

Research only single100% frozen target/stop, no elective trail/breakeven/scale-in.
Owner must approve this exact new management policy before later implementation.
Sizing remains q<=min(.0025 equity, remaining .005 risk)/(d+c_loss), rounded down
and independently capped by isolated2x margin/filters; two slots/one per symbol,
1% daily entry halt. One immutable owner nonce, one exchange writer, bounded IOC
within original trigger+10s, adverse cap=min(2 dated ticks,.10ATR5,.05 originalR)
AND U, approval request<=90s, no expired setup rescue. First actual fill starts
11h55 flatten/12h emergency clocks. No widening, averaging down or timer reset.
No research result grants approval, writer access or production registration.

Later R1/R2 inherit S01 minimum100 legitimate intended signals/30UTC days/
30 nonoverlapping shared-market12h components/4symbols including2altcoins and
two point-in-time liquidity cohorts, >=50% exact source-aware controls. Preserve
October1–14 validation,15–31 untouched evaluation and12h purge/embargo; length
does not waive adequacy. Source-backed R1 joint24h-block97.5% lower bound>0 for
primary4h contrast and conservative target-first>=35%; R2 full scanner/selector,
approvals/nonfills/partials/portfolio/exits/funding and genuine fee/fill evidence,
positive mean modeled initial-monetary net_R with joint-block97.5% lower>0 and
stress lower>=0. Independent review and exact owner version approval are needed.
No new purchase or persistent collection is authorized by this experiment.
