# C05-J / P3-M2 — Integrated causal economic research

**NEXT_GATE:** independent engineering-lead review of this implementation and
decision packet, together with the owner's C05-I source-evidence packet. P3
remains `INSUFFICIENT_EVIDENCE`; T1/R1/B1 remain `RESEARCH_ONLY`; phase credit
remains **45% credited / 55% unqualified**. C06-F owner-hosted acceptance is
owner-reported PASS and closed; it was not rerun as a project milestone here.

Date: 2026-10-26 (Asia/Colombo). Tracking issue:
<https://github.com/KasunKarandagolla/AstraBot/issues/18>.
Original fetched merged-main base:
`20600d12c66c253d968857a4af909084b4b9e5d0`.
Branch: `codex/p3-integrated-economic-research`.
Implementation head, PR and final-head CI are recorded in the delivery addendum.

## Capability delivered and reuse decision

The existing C04 replay already supplies a chronological C02 universe, persistent
C03 states, E0/E1/E2 execution assumptions, portfolio reservations and block-aware
statistics. C05-G supplies checksummed original-feed readers and causal sampled
observations; C05-H supplies scoped metadata/unit/measurement verification.
They did not previously share a runnable research decision path. C03's mandatory
vetoes also stop setup formation, so its previous all-NO_TRADE diagnostics could
not answer whether authentic prices contained a frozen policy pattern.

This change adds one research integration module and one offline command. It
joins G/H outputs to C04 **only at the exact validation cutoff**, retains original
instrument IDs, source hashes, event/arrival times and degraded readiness, then
uses the existing strict scanner and policy engine. It also invokes the actual
frozen `form_setup` / `advance_setup` functions in a separate price diagnostic
ledger. A price confirmation never enters the strict decision or execution
denominator. E0/E1/E2 and all risk, cost, fill, exit and portfolio calculations
continue to use the existing C04 components.

No strategy threshold, C02 production spread interpretation, dependency,
exchange-order interface or runtime architecture was changed. B1 retains
`B1.original-ladder.v1`, 40% at 1R and 60% at 2R. The original risk ceilings,
one-use approval, one writer, isolated 2x, two positions and first-fill 11h55m/12h
boundaries remain intact.

## Reproduce the authentic decision packet

Install the repository's pinned `requirements-test.txt` in Python 3.12. Keep the
existing C04 raw archive tree outside Git. From the repository root, run:

```sh
ASTRABOT_DATA_ROOT=/path/to/c04-data python scripts/c05_integrated_research.py
```

This command defaults to all seven symbols, 5-minute candle availability cutoffs,
`2024-10-01T00:00:00Z <= decision < 2024-10-02T00:00:00Z`. It retains earlier
source history for warm-up and does not evaluate policy outcomes in the untouched
October 15–31 window.
An explicit `--start`, `--end`, `--interval`, `--manifest` and `--data-root` can
bound another declared replay. Outcome candles are clipped at `--end`; late
opportunities can remain unresolved rather than borrowing a later split.

Outputs are `C05_J_DECISION_PACKET.json`, its lossless `.json.gz` copy, and
`C05_J_DECISION_PACKET.md` in
`research/c05` (or `--output-dir`). JSON contains the complete chronological
funnel, source partitions, diagnostic setup lifecycles, sensitivity assumptions,
per-policy scenario costs and uncertainty. The packet hashes its deterministic
content; wall-clock runtime measurements are excluded. Historical bar
`available_at` is explicitly the existing close-time-plus-1ms proxy, not observed
archive publication or ingestion latency.

## Source bytes actually available in this executor

The fresh executor initially lacked the external C04 archives. The exact
**112 pinned files / 15,417,887 compressed bytes** were restored once, with every
size and SHA-256 matched against the unchanged C04 manifest. The existing loader
then independently checked ZIP members, CSV schemas, member hashes, coverage,
row counts and cross-month continuity, and normalized **356,454 rows**:

| Interval | Normalized bars |
|---|---:|
| 5m | 247,968 |
| 15m | 82,656 |
| 1h | 20,664 |
| 4h | 5,166 |

The cohort is BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, ADAUSDT and DOGEUSDT;
coverage is July–October 2024. It is a fixed cohort, not proof of a historical
dynamic universe. Source manifest:
[`research/c04/historical_manifest.json`](../c04/historical_manifest.json), SHA-256
`6a34aae6b37ec9b48aa166dda52cd578a86776ef8b36be05aaaa5bf42f51058a`.
Actual raw tree for this run: `/workspace/work/c04-data`, outside the repository.
No new source cohort or archive plan was acquired, and no original-data downloader
was added to the product.

**Original Windows C05 gzip files are absent here.** Their earlier counts and
hashes in C05-G are prior-session evidence, not a replay performed in this task.
The historical H manifest
[`C05_H_EVIDENCE_SOLUSDT_2024-10-01.json`](C05_H_EVIDENCE_SOLUSDT_2024-10-01.json)
has zero evidence records and closes zero historical checks. Synthetic G/H
fixtures are used only in mechanics regressions and cannot be attached to this
authentic panel.

## Authentic research result

The complete CLI run evaluated **288 chronological cutoffs × 7 symbols = 2,016
symbol-windows**, from 00:00 through 23:55 UTC on 2024-10-01. All source-history
lookbacks were warm; all **12,096** C03 policy/side diagnostics had `READY`
context. Missing historical market evidence, rather than a missing candle
warm-up, prevented strict admissions.

| Funnel stage | Count |
|---|---:|
| Verified source bars, full archive panel | 356,454 |
| Strict C02 symbol-windows considered | 2,016 |
| Eligible / shortlisted symbol-windows | 0 / 0 |
| Strict C03 candidate decisions | 0 |
| C03 diagnostic NO_TRADE records | 12,096 |
| Price-only frozen formations | 30 |
| Price-only confirmations | 6 |
| E0 / E1 / E2 historical outcomes | 0 / 0 / 0 |
| Historical executable trades / qualified net-R sample | 0 / 0 |

Each of these six C02 vetoes applies to **2,016/2,016 windows**:
`METADATA_MISSING`, `TICKER_24H_MISSING`,
`SPREAD_WARMUP_LT_60_VALID_SAMPLES`, `DEPTH_MISSING`,
`OPEN_INTEREST_MISSING`, `EVENT_CLEARANCE_MISSING_OR_FUTURE`.
These counts overlap; summing them does not create additional rejected windows.
Separately, **576/2,016** price contexts were `EXTREME_VOLATILITY`, resulting in
**3,456** additional policy/side veto memberships. Strict approvals, entry
attempts, fills, partials, portfolio reservations and exits are all zero because
their candidate ledger is empty, not because successful free execution was
assumed.

| Frozen policy | Diagnostic formations | Diagnostic confirmations | Strict candidates | Economic decision |
|---|---:|---:|---:|---|
| T1.reclaim.v1 | 13 | 5 | 0 | INSUFFICIENT_EVIDENCE |
| R1.sweep.v1 | 0 | 0 | 0 | INSUFFICIENT_EVIDENCE |
| B1.original-ladder.v1 | 17 | 1 | 0 | INSUFFICIENT_EVIDENCE |

R1's stable-balance requirement rejected all **4,032** policy/side attempts.
T1/B1 formations demonstrate observable price patterns; they do not establish
admissible entries, feasible target quantities, positive returns or an edge.
R0 now exposes formation frequency, veto coverage and diagnostic friction
feasibility. R1 event/control and MAE/MFE outputs remain `NOT_TESTABLE` with zero
strict events. R2 has zero candidate outcomes; mean net-R and confidence
intervals are **null**, not zero. The E0/E1/E2 mechanics are exercised separately
by labelled synthetic regressions. No empirical bootstrap or matched-control
result is fabricated from the diagnostic patterns.

The owner's one-symbol SOLUSDT packet can affect at most **288/2,016** windows in
this same-day cohort. The other **1,728** windows require their own instrument
and feed evidence. Even SOLUSDT needs the remaining C02 readiness, ticker/event
and cadence requirements; successful H arithmetic does not unlock all 288.

Packet content hash:
`5d1c6c6c1d4a6e38f642c7d3f6e264d9dd5f9247f4a50fd31efda5b5d4d91c20`.
C04 run ID:
`f731e56d0321be28d81ea553416100437a744ba26c9a1e9e93244a798d293c53`.
Decision/funnel ledger hashes are preserved in `replay.output_manifest`.
See [the human packet](C05_J_DECISION_PACKET.md) and
[the full compressed JSON packet](C05_J_DECISION_PACKET.json.gz). The complete
source-ID/chronology ledger is retained in the compressed artifact; decompression
produces the exact JSON generated by the command. Gzip metadata uses a fixed
timestamp and no embedded local filename. The uncompressed default output is
ignored by Git to keep the PR readable; no research records are removed.

## Chronological market and no-trade cases

The case selection rule is fixed: first chronological formation that reaches
price confirmation, otherwise first formation; and first chronological
rejection. No return-based selection or threshold tuning is used.

**BTCUSDT T1 SHORT — an ineligible price confirmation.** At 02:10 UTC the actual
frozen T1 function formed an armed short in `TREND_DOWN` / `BEARISH` context
(1h ADX 44.1524). The three-bar pullback high **63,460.00** was frozen from source
IDs `1727747700000`, `1727748000000`, `1727748300000`; frozen 5m ATR was
**115.81841600914574**. The policy's historical VWAP tests passed on their own
causal prefixes; they did not use the session's later final VWAP.

| Available UTC | Source 5m open UTC | OHLC (USDT) | Diagnostic transition |
|---|---|---|---|
| 02:10 | 02:05 | 63336.90 / 63380.20 / 63264.80 / 63321.60 | ARMED, original high and ATR frozen |
| 02:15 | 02:10 | 63321.70 / 63331.60 / 63183.20 / 63214.80 | CONFIRMED by distinct next closed event |

The confirmation source ID is `1727748600000`; the original expiry remained
02:40. Setup ID:
`9653aa15cda4297c9c700ee15fb98e0d2c642af06276fe29d53351b09d50d130`.
The archive is `BTCUSDT-5m-2024-10.zip`, pinned by the C04 manifest. All six
missing-evidence vetoes still applied. The strict engine therefore emitted no
candidate, entry, stop/target execution or P&L for this pattern.

**ADAUSDT T1 LONG — rejected before formation.** At 00:00 UTC the newest known
bar was 2024-09-30 23:55–23:59:59.999, source ID `1727740500000`, OHLC
**0.37280 / 0.37360 / 0.37270 / 0.37320**. Its availability proxy was exactly
00:00; no later October bar entered this context. Context was `TREND_DOWN` /
`BEARISH` (1h ADX 47.0136), so a long failed `T1_CONTEXT_NOT_ALIGNED`; the same
six independent C02 data vetoes also blocked admission. This is a separate
reasoned NO_TRADE case, not a retrospectively labelled losing trade. Its source
bar is in `ADAUSDT-5m-2024-09.zip`, also manifest-pinned.

## Source-backed B1 friction sensitivity

One B1 price pattern confirmed: **BNBUSDT SHORT at 15:10 UTC**, confirmation
source ID `1727795100000`, setup
`3753d791bdd31d6fb45f94dca5f24edc595220f1aedd378c023276200ed7b041`.
Using its authentic confirmation close **550.390** as a *hypothetical* entry and
the original retest extreme plus 0.10 frozen ATR gives an unrounded diagnostic
stop **562.703278148911452780**, distance **12.313278148911452780** or **2.23719%**.
These numbers do not establish a historical bounded fill or exchange rounding.

The original 40%/60% ladder yields 1.6 gross price-R. Under the openly simplified
symmetric winning/losing round-trip cost hypothesis,
`(1.6*d - c)/(d+c) >= 1.5` requires **cost_R = c/d <= 0.04**.

| Assumed fee per side | Other round-trip friction | Cost_R | Successful-ladder net RR | 1.5 screen |
|---:|---:|---:|---:|---|
| 2 bps | 0 bps | 0.017880 | 1.554330 | passes model |
| 5 bps | 2 bps | 0.053639 | 1.467639 | fails model |
| 10 bps | 5 bps | 0.111747 | 1.338661 | fails model |

Thus this source-backed geometry can accommodate the lowest declared friction
scenario but not the middle or stress assumptions. **This is conditional ladder
arithmetic, not expectancy or a profitable trade.** Fees/friction are modelling
assumptions; no funding settlement, spread, impact, fill probability, venue
filter/quantity feasibility or target-before-stop outcome is certified. With
one diagnostic observation, its min/median/p90/max stop fraction coincide; no
distributional inference follows. The appropriate next economic question for B1
is realistic cost feasibility before spending effort on a full outcome study.
No ladder revision or policy promotion is performed.

## Owner Windows / C05-I handoff

Keep the original C04 archive tree, three original gzip feeds and H supporting
artifacts local. Preserve the existing G manifest filenames/digests, and the H
`c05h.historical-evidence.v1` schema, relative artifact paths, checksums, source
locators, availability/effective periods, instrument and exact dataset bindings.
The independent source review required by C05-H still applies; a hash does not
authenticate an arbitrary assertion.

Use this same integrated command in PowerShell after activating Python 3.12:

```powershell
$env:ASTRABOT_DATA_ROOT = 'D:\AstraBotData\c04'
python scripts/c05_integrated_research.py `
  --feed-data-root 'C:\Users\User\Downloads' `
  --symbol SOLUSDT --date 2024-10-01 `
  --evidence-manifest 'D:\AstraBotEvidence\manifest.json' `
  --output-dir 'D:\AstraBotEvidence\integrated'
```

The reference SOLUSDT day uses the existing pinned G manifest by default. For
another approved dataset, also supply `--source-manifest path\source.json` using
the existing G schema. The command verifies each original gzip, reads it through
EOF once through the existing adapters, evaluates evidence at every selected
candle cutoff and joins that result into the strict replay. It does not download
the originals or require their transfer to Codex Cloud. A supplied H manifest
without original feeds is rejected; the stored G report cannot stand in for raw
input bytes.

Return sanitized JSON/Markdown, exact command, code SHA, source/evidence manifest
hashes and reviewed artifact citations. Do not include credentials, private
account records or redistribute data without rights. The packet explicitly
reports which checks and vetoes remain; H validation alone does not supply a
historical ticker, event clearance, executable depth, settled funding or fills.

## Execution assumptions retained from C04

The existing C04 economic profile is explicitly
`c04.synthetic-research-cost.v1`: 5 bps per-side fees; ordinary-exit spread /
slippage 0.01 / 0.02 USDT per base unit; stop spread / slippage 0.02 / 0.05;
max-hold funding proxy 0.05 per unit. The research account is a modelled 10,000
USDT account. These are uncalibrated assumptions, not the owner's account or a
historical fee/funding schedule. E1 assumes immediate post-trigger approval and
OHLC-touch execution; E2 assumes a bounded preapproved plan, half size, doubled
fees and tripled friction. The existing simulator handles partial exits,
stop/target ambiguity, holding clocks and per-scenario portfolio limits. Its
`BAR_APPROX` fills cannot establish one-second IOC execution. No nonzero
historical P&L may be inferred from empty scenario ledgers.

## Acceptance evidence

- Focused integrated regressions: **7 passed**. They cover authentic zero-event
  denominators, future-candle prefix stability, exact-cutoff H validation,
  instrument/feed hash and synthetic scope, and real E0/E1/E2 machinery exercised
  with synthetic observations. The positive case is repeated with metadata on
  the base data, only in causal history, and only in exact snapshots. This caught
  and protects the material execution-filter propagation defect fixed here.
- Complete relevant CI suite locally:
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q` — **314 passed in
  238.38s**, no failures or skips. Full regression includes existing automated
  safety tests; no owner-hosted C06 acceptance scenario was rerun.
- Compilation, `pip check`, frozen C03 golden trace, incomplete authentic C03
  panel check, existing C04 replay `--check`, and `git diff --check` passed.
  The C04 check wrote only to a scratch output directory.
- Two separate integrated CLI runs on the retained authentic C02 sample produced
  byte-identical JSON and Markdown: 48 symbol-windows, 288 diagnostic NO_TRADE
  records and zero strict candidates. These are a small deterministic command
  regression, not substitutes for the seven-symbol research run.
- Frozen policy, context, economics, simulator, production C02, risk contracts
  and C06 source paths were compared with the original base and are unchanged.
  The C04 replay adapter pins selected decision-time metadata for simulation,
  preserving full outcome candles; this changes integration, not policy rules.

Exact commands use the isolated `/workspace/work/c05-venv` interpreter in this
executor. No dependency was added. Remote final-head CI is observed separately
in the delivery addendum; local success is not a remote CI claim. Internal
implementation/research/test review does not replace the required independent
engineering-lead acceptance. The PR remains unmerged.

## Remaining economic qualification boundary

All three policies retain an explicit `INSUFFICIENT_EVIDENCE` decision. No GO,
REVISE or STOP verdict about empirical edge can be inferred from a day with no
strictly eligible opportunity. No trade is different from a loss, and diagnostic
patterns are different from admitted policy observations.

The next P3 gate is a substantive evidence/feasibility decision: review the actual
C05-I source packet against this runnable same-day pipeline, determine which
strict gates it closes, and decide whether a representative causal event study
is now feasible. In particular, C05's periodic minute endpoints do not replace
C02's raw source-event cadence, and reconstructed book arithmetic does not prove
executable liquidity. The cadence/source-time mismatch is already tracked in
[issue #22](https://github.com/KasunKarandagolla/AstraBot/issues/22). Earlier
C05-F/G reports found only 0–2 of 59 adjacent raw-event intervals exactly one
minute apart at the fully populated sample cutoffs; those are prior-session
observations, not fresh original-byte measurements here. This PR does not close
that issue or promote the opt-in sampler. If those gates remain unsupported, the lead must record the
specific source or policy-interpretation decision needed; another generic
validator or synthetic-only demonstration will not close P3. No C06/C07, demo,
live, procurement or persistent collection follows automatically.
