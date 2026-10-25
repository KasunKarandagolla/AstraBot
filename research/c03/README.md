# C03 reproducible policy evidence

These are **research policies**, with synthetic positive/negative cases and an
actual incomplete-data NO_TRADE. None authorizes orders or establishes an edge.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/c03_research.py --check --summary
.venv/bin/python scripts/c03_research.py --c02-panel --check
```

The first demonstration reproduces [golden_trace.json](golden_trace.json):
closed observations → TREND_UP/bullish bias → frozen three-bar pullback → later
own-session VWAP reclaim → future IOC research bounds → stop/targets/costs.
Its candidate has entry validity window `100.38–100.42`, enforceable BUY maximum
`100.42`, original stop `99.56`, 40% at `101.28` and 60% at the preconfirmed
`108` swing. Net ladder scenario is approximately `5.50106`. A deliberately
severe fee stress rejects the **same geometry**, approximately `−0.02417` net
scenario RR. These favorable synthetic prices and synthetic fees were chosen
to exercise acceptance and rejection; they are not fitted historical evidence.
The full output (omit `--summary`) includes restorable setup/decision state.

The second demonstration checksum-verifies C02's 24 actual BTCUSDT hourly bars
from 2024-10-28, normalizes them with the existing C02 adapter, and returns
NO_TRADE for T1/R1/B1. Missing metadata, complete warm-up, 5M/15M/4H inputs,
OI, quotes and event clearance remain missing. The account/cost overlay is
explicitly synthetic. Archive close-time availability remains C02's declared
proxy, not recovered original feed latency. No live request occurs.

## Acceptance evidence map

| Gate | Executed local coverage |
|---|---|
| S01–S02 | `test_c03_context_levels.py`: unavailable/forming HTF, strict/tied/delayed 3/3 swings |
| S03 | Full context and full decision/state bytes invariant to future unavailable bars |
| S04–S06 | Real prior VWAP crossing, frozen pullback, midnight suspension and no false thesis failure |
| S07–S09 | Frozen range, actual hourly roll changing the new range, distinct confirmation, stable-balance negative width/drift/tests and context persistence |
| S10–S12 | First B1 retest, no better-later replacement, bar-six next-close edge, hard penetration and disappearing breakout label |
| S13–S16 | Exact 1.6 ladder and 0.04 equal-cost boundary; long/short IOC bounds, no retroactive entry, missing/wrong-side/forged/obstructed targets, whole-ladder costs and fractional sizing |
| S17 | Immutable anchors/ATR, consumed/expired state, duplicate events/scans and one-symbol candidate arbitration |
| S18–S19 | Mandatory OI/events/history fail closed; optional A01/A03 remain unavailable; output rejected as authorization; no signed writer imports |
| S20 | T1 cost-stress rejection; R1 touch/breach/failed confirmation; B1 first-retest/failure/economics rejection |
| S21 | Synthetic golden candidate plus fixed-geometry rejection, and checksum-backed actual C02 incomplete-data NO_TRADE |
| S22 | All existing C01/C02 tests remain in the full offline suite |

Main implementation lives in `src/astrabot/research/`. Versions, exact raw
fixture generators and checksums are in the golden trace. C01 contracts and
the v1.5 reference are unchanged. C01's frozen lifecycle is reused; its
`EconomicsV15` filled-execution compatibility slot is intentionally empty.

[Expert evidence](EXPERT_EVIDENCE.md) and [source lock](sources.lock.json) record
the implementation/practitioner research and exactly which external tests ran.
Practitioner inputs were not recovered; those cases are qualitative analogies.
The C02 panel is not a multi-market backtest. All thresholds, R1 balance terms,
cost profiles, entry latency/chase and original B1 exits need empirical C04/C05
qualification. C04's precise data requirements are in that evidence report.
