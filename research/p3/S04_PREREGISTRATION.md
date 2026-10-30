# S04 VT4 — compression breakout, protocol v0.1

PROPOSED / RESEARCH_ONLY. Baseline 32c528866003f97ef76be1c510564b4d7156c051.
Commit this protocol and S04_CANDIDATES.json before running any new outcomes.
One serious hypothesis; no replacement candidate or threshold search this session.

## Mechanism and data

VT4 tests whether a directional exit from a compact six-hour auction, followed
by a distinct acceptance close, predicts continuation within twelve hours.
It replaces VWAP pullbacks and failed auctions. Broad structural invalidation
tests whether ordinary auction noise defeated the previous short stops.
Reuse C03 TA-Lib context, S03 causal unvisited swings, C05 costs/paths and exact
controls. A Donchian range is a statistic, not an upstream profitable strategy.
No new technical indicator or dependency is needed.

Only the 84 pinned July–September Binance public archives in the original C04
manifest (SHA256 6a34aae6b37ec9b48aa166dda52cd578a86776ef8b36be05aaaa5bf42f51058a).
Restore exact originals if absent, outside Git, retaining current retrieval audit.
July is warmup. August is additional development, September is extensively
selected development and the source-identical benchmark interval. August was
previously used as indicator history; neither month is an untouched test.
Run both without changing the candidate. October files must be excluded before
opening. Purge each month's crossing horizons. Never pool months to rescue a
failed September gate. Fixed seven symbols are not a point-in-time C02 universe.
Original exchange close+1ms is an availability PROXY, not provider/owner arrival.

## Exact causal schedule and rule

At each new closed 15m q, freeze H/L from the preceding 24 contiguous closed
15m bars, excluding q. A raw formation is q.close > H (long) or < L (short),
with the previous 15m close inside [L,H]. Each raw formation consumes a six-hour
symbol-wide cooldown, including rejected formations. No future outcome changes
rearming. Record every scanned 5m window, all raw formations and all vetoes.
Require complete histories. Compute A=ATR14 on hourly bars available no later
than q.open_time, not the breakout-containing hour. W=H-L.

Main formation masks: READY/nonextreme C03 context, 4h bias not opposite side,
W/A <= 4, q directional body, 0.05A <= signed(q.close-edge) <= 0.50A,
and C03 15m relative volume >=1.20. Freeze structural stop at the adverse
extreme of the preceding twelve 15m bars INCLUDING q, minus/plus 0.25A.
Freeze the measured auction objective at edge +/- 2W. This objective is a
predeclared price-range projection, NOT observed liquidity. Choose a closer
active opposing S03 confirmed/unvisited hourly swing when present. No farther
target substitution. This proposed target/management version requires explicit
owner approval before qualification/registry integration; it changes no T1/B1.

Exactly the next distinct 5m bar must close >=0.05A beyond edge. Touch of the
original stop wins; missing bar invalidates; failed acceptance expires. No
extension/retry. Shadow all raw formations with available ATR through this same
transition, even if a main mask vetoed, to expose rejected outcomes. Confirmation
price must remain within edge +/-0.50A, have positive frozen stop distance <=2%
of entry, positive target, gross target R in [1.8,4], and no NEW nearer unvisited
opposition. Freeze levels; never widen stop or move target. A target touched on
the formation or confirmation candle is a rejection, not a retroactive success.

## Controls and outcome seal

Every diagnostic confirmation gets an original control selected without returns:
same symbol, side, C03 regime, 4h bias, ATR quartile and four-hour UTC session;
past 12h..7d, within the same month, complete future12h within that month.
No raw formation, cooldown, active or terminal setup at control cutoff; READY
nonextreme and side permitted. No future-trigger exclusion. Replacement allowed,
fixed seed20261030. Save all pool IDs, covariates, exclusions, pool hashes and
unmatched cases. Copy case stop/target FRACTIONS only for control normalization.
Seal complete chronological census and matches before any forward-path call.

## Costs, timing and falsification

Reuse C05 fees2/5/10bps per side, roundtrip friction0/2/5bps, funding0/1/3bps.
Recompute actual entry/stop/target notionals and gross geometry after adverse
entry shifts0/.025/.05 originalR. Separately test funding5/10bps and extra
stop-slippage .10R. No favorable funding credits. These are conditional cost
scenarios, not measured fees/fills. Require successful-target net RR>=1.5.
Observe full contiguous12h excluding confirmation candle, conservative stop-first
same-bar ordering and 11h55 exit. Report modeled fixed-stop/single-target
cashflows normalized by initial monetary risk, including time exits and gap-open
stop degradation. These are OHLC assumptions, NOT realized net_R.

Timing cases: confirmation close as an idealized reference, next5m open as an
OHLC entry diagnostic, and 90s/300s delay observability. A 5m bar cannot certify
10-second IOC, 90-second actual approval, partials, depth, dated ticks or fills.
All actual executable/strict eligible counts remain zero without those sources.
One-use approval<=90s; original trigger+10s submission; cap=min(2 dated ticks,
.10ATR5,.05originalR); all must pass later. No entry can be backfilled.

Descriptive ablations on the SAME raw schedule: remove compression, volume,
or 4h-bias mask individually, and remove all three. All other geometry/cost/
timing rules remain. Report included versus excluded paths and equal-day
differences; filters are not validated by fewer losing cases alone. Side-reversed
signed close paths are a negative control, not a second candidate. Never promote
an ablation after outcomes. Report per-day/symbol/side/volatility/session, matched
1h/4h/12h contrasts, control reuse, market-time components, equal-day deletion
ranges and joint-day resampling sensitivity (descriptive, no selection-valid CI).
Save chronological first winner, loser, rejection, timeout and ambiguity examples.

## Frozen decision

Apply the existing S03 eleven conjunctive gates to September separately: >=20
complete base cases, >=8 UTC days, >=4 symbols, >=10% primary confirmations
survive, >=35% conservative target-first, >=50% exact controls across>=8 event
days, positive1h/4h and nonnegative12h equal-day contrasts, and4h day-deletion
lower>0. Additional August development must not contradict the mechanism:
if August has>=20 complete base cases, target-first upper<=20% OR negative
matched4h AND12h defeats cross-month support. No pooling or threshold changes.
ADVANCE only if September passes all gates and August does not contradict.
REJECT if>=20 primary confirmations and zero base survivors, or>=20 complete
base cases and optimistic target-first<=20% in either month. Otherwise REVISE
only if target-first exceeds PC3's1/9 and population exceeds9 with>=4symbols;
otherwise REJECT. SOURCE BLOCKED describes strict economics separately and
cannot erase a measured adverse price verdict. Benchmark beaten YES only when
all September advancement gates pass, not because one count looks better.

## Qualification and safety contract

Preserve S01/S03 source-backed R1/R2 requirements: >=100 legitimate intended
signals, >=30UTC days and30 nonoverlapping shared-market12h components,
>=4symbols including2alts/two dated liquidity cohorts, >=50% source-aware exact
controls, joint24h-block97.5% lower>0 for primary4h contrast; full-policy R2
initial-monetary net_R lower>0 and stress lower>=0, plus untouched independent
review. Preserve October1–14 validation/15–31 evaluation and12h purges, without
assuming short October supplies sufficient sample. No after-outcome gate waiver.

S02 issue22: original host quote/ticker/book hashes and reported clock evidence
remain distinct from Cloud inspection; 7PARTIAL/2UNVERIFIED/0SOURCE_ACCEPTED.
Reconstructed L2 quote is not native BBO; provider receipt is not owner receipt.
C02v1 unchanged. Missing dated metadata/units/OI measurement/mark/depth sequence/
news/fee/fill/availability continues to veto admission. A01/A05/A08 record-only
when absent; A02 optional record-only here (no VWAP claim); A03 price structure,
A07 closed-price action, A09/A10 context mandatory; A04 depth and A06 OI/funding
required for later qualification. No invented order flow or missing-as-zero.

Keep <=.25% per-trade/.50%aggregate modeled stop risk,2slots/one per symbol,
isolated2x,1%daily entry halt, one-use authenticated owner approval, one writer,
no widening/averaging/timer reset,11h55flatten/12hemergency from first fill.
Portfolio diagnostic uses .25%risk,2slots,2xnotional, chronological ordering and
fixed12h reservations; no hypothetical result permits trading. No orders, Demo,
production activation, procurement, new subscription or persistent collector.
