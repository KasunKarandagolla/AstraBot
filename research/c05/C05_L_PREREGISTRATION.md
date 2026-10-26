# C05-L exploratory September price-outcome preregistration

Registered before loading forward candles or computing outcomes. Base:
`0d5b45c4ccdadd782f9b4f42f290f35faf445a60`. This document and its initial Git
commit fix the design; subsequent findings do not change membership or matching.
This is an R1 investment/falsification diagnostic, not strict R1 qualification.

- **Sources/population:** original C04 manifest and C05-K census, with all 434 T1
  confirmations and 624 formation histories. Original 149 screenable geometries
  and 24 base cost/route/context survivors are immutable. Preserve original IDs,
  stops, structural targets, 40%/60% fractions and scenarios. July–August is
  context warm-up only; September decisions only; October archives/outcomes
  must not be opened. Authentic absent files may be restored once from their
  original public URLs and must match already-committed sizes and hashes.
- **Reference/horizons:** confirmation close is hypothetical. Subsequent bars
  start at confirmation availability (exclusive of the confirmation candle),
  using native close+1ms availability. Fixed 15m, 1h, 4h, 12h paths; endpoints at
  or before October 1 00:00 UTC. Incomplete horizons are censored, never extended
  into October. Final-12h decisions are excluded from full-12h comparisons.
  No validation/evaluation training or cross-split control is permitted; preserve
  the existing 12h purge/embargo. The already-formed original events remain in
  the event ledger even when a horizon cannot be completed.
- **Outcomes:** signed close move, favorable/adverse extremes in percentage and
  original price-R; MFE >=0, MAE <=0; first stop, 1R and original structural target
  touches at candle resolution; target-vs-stop LOWER (strict earlier candle) and
  UPPER (same candle allowed) counts. Full ladder means ordered geometry and
  second target touched before stop, not two fictitious fills. Same-bar ordering
  is unresolved. Fixed-stop 40%/60% marks at touches/expiry may be reported only
  as NON_EXECUTABLE_DIAGNOSTIC_BOUNDS. No expectancy, win rate, realized-R or
  profit factor. Original post-entry thesis logic is used only where implemented;
  do not apply armed-setup invalidation as an invented position exit.
- **Controls, selected before any outcome calculation:** one non-trigger per
  event, with replacement, deterministic existing `statistics.matched_controls`
  seed 20261026. Exact symbol, side, frozen confirmation regime, ATR-percentile
  quartile [0,25), [25,50), [50,75), [75,100], UTC four-hour session. Controls
  must be in September, in the preceding seven days, at least 12h before the
  event, and have a full 12h September outcome. Exclude timestamps with a T1
  setup armed/confirming on either side using only formation/state facts already
  available at that timestamp. Do not exclude a control because a future setup
  or future favorable/adverse return later appears. No relaxed matching fallback.
  Retain candidate metadata, causal exclusion reasons and exact match links.
  Controls use own close and the matched event's original stop fraction solely
  for comparable R scaling; they do not inherit a tradable setup. Percentage
  moves are also reported. The observed pool is the fixed seven-symbol panel,
  not a point-in-time eligible universe. Source-calendar month is fixed and
  preceding-seven-day matching is the market-time restriction.
- **Dependence/uncertainty:** retain overlaps across symbols and dates; report
  UTC market-day counts, counts of shared/overlapping case/control windows and
  Kish concentration across days using existing statistics. Day-cluster results
  are descriptive. Suppress bootstrap confidence intervals with <30 distinct
  market days or <30 nonoverlapping shared-market outcome components; this
  September-only investment sample cannot establish a reliable advantage.
  Report equal-day-weighted paired differences, leave-one-day-out ranges and
  per-symbol/per-day results, with no p-values or independent-trade inference.
- **Sensitivity:** retain optimistic/base/stress 2/5/10bps per-side fees,
  0/2/5bps round-trip friction and 0/1/3bps funding debit hypotheses. Report
  model drag versus actual price excursion, not trade net results. Ex-post
  funding only if original records are available; prior aggregate funding audit
  is not event-level cash flow. Hypothetical 0/.025/.05 original-R adverse entry
  uses fixed levels; 15/60s delays exceed the frozen 10s entry deadline. Bars
  cannot resolve 0/5/10s fills; next-bar open/close is diagnostic only.
- **Decision rule (research judgment, not a significance test):** WEAK_REVISE if
  conservative paths materially fail the full original ladder (at most 25% of
  survivors reach target 2 strictly before stop within 12h) AND the 12h matched
  equal-day signed-move difference is nonpositive, with no reversal under
  same-bar upper bounds. Conditional justification requires both favorable
  target-path evidence and consistent positive matched differences at 1/4/12h,
  robust to day deletion and ordering, while expressly withholding economic GO.
  Otherwise INDETERMINATE. SOURCE_BLOCKED only if indispensable authentic paths
  cannot be accessed/restored or legitimately reconstructed from existing
  authenticated artifacts. Sparse sample alone does not reject T1. No retuning.

No production C02/source-clock, strategy, risk, execution or coordination changes.
One next programme action follows the evidence, with separate owner/source
acceptance required before any prospective collection or expenditure.
