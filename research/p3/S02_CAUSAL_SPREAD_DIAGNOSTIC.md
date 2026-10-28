# S02 — Causal spread diagnostic and reproduction

**SOURCE_CONTRACT_PARTIAL_BUT_IMPLEMENTABLE. Original SOLUSDT one-day empirical
acceptance: PENDING_OWNER_RUN.** Proposed v2 diagnostics confer no production
C02 eligibility, strategy qualification or trading authority. See the
[source-clock ADR](../../docs/adr/ADR-P3-SOURCE-CLOCK-AND-ACCEPTANCE-S02.md) for
the frozen mathematics, routes and four owner decisions; the
[acceptance matrix](S02_SOURCE_ACCEPTANCE.json) is the authoritative nine-feed
and A01–A10 handoff.

## What was actually available

On 2026-10-28 the workspace repository, attachments, shared/downloads and library
locations contained no owner-original three-feed files. A filename inventory
found only `tests/fixtures/c05g/` copies with identical-looking filenames; their
manifest explicitly says `synthetic:true`, and **all three hashes differ** from
the original pins. No authentic one-day counts/medians/age/coverage result was
manufactured and no vendor download was attempted.

| Original file for SOLUSDT 2024-10-01 | SHA-256 of compressed bytes | Prior reported rows |
|---|---|---:|
| quotes | `ce31562cbfa20312aeda0246caf2d83754ce90835ce7579aeca40988b50f68cc` | 1,064,711 |
| derivative_ticker | `8c7301a2b3aa22de1430af3844afac9bb05de061dfc28a65a7bdc4920c1357d7` | 119,927 |
| book_snapshot_25 | `19655523821b384f741715a2d4bf5db2fe1f825fddbed66ecaf9ef1796a6e3ba` | 1,522,898 |

These pins originate in retained C05-D/E/H preflights and issue #18. Quotes and
derivatives had prior independent uploaded-byte inspection; the book summary
was owner-agent reported. The detailed owner-side C05-I/M reports are absent.
A matching checksum reestablishes identity to those bytes, **not** a publisher
signature, lawful acquisition, full source continuity or historical owner receipt.
Quotes are L2-reconstructed BBO, top-25 is reconstructed depth, and derivative
ticker is a changing normalized record; none becomes a native depth sequence or
native bookTicker merely because its format is valid.

Independent retained genuine sample checks succeeded for the **existing C02 smoke
panel only**, using manifest digest and row count:

- BTCUSDT 1h CSV: 24 rows, SHA-256
  `73930ee78240d99a8184e5dedf808dbd998799c22fcc632732ffdc12dd465c1b`.
- APEUSDT aggregate-trade CSV: 100 rows, SHA-256
  `52ff319bf0526d02d757b21939ea33f73a125d057469e775e2f119aaaf5fd778`.

Neither contains BBO/provider/owner arrivals, so neither can empirically test
this spread sampler. Existing panel regressions were run, with no strategy
outcome analysis added. Original October 15–31 monthly evaluation archives were
not opened; no October strategy outcomes or policy thresholds were inspected
or tuned for S02.

## Executed synthetic mechanics (not market evidence)

The existing C05-G fixture contains 63 raw quote rows, four derivative rows and
two book rows. Source hashes, full input audit counts, per-slot identities,
original clocks/prices, ages, rejected rows and deterministic uncompressed
payload hashes are committed in [`s02-synthetic/`](s02-synthetic/S02_DIAGNOSTIC.json).
Every file is labeled SYNTHETIC_ONLY. The original four cutoffs are frozen;
01:00 is an additional **synthetic-only** positive-mechanics cutoff.

| UTC cutoff | Raw window rows | Selected | Unselected | Invalid unselected | Missing slots | Exact v1 intervals | Proposed v2 provider pass |
|---|---:|---:|---:|---:|---:|---:|---|
| 00:30 | 30 | 30 | 0 | 0 | 30 | 0 | false |
| 01:00 synthetic only | 62 | 60 | 2 | 1 | 0 | 0 | true |
| 01:05 | 58 | 56 | 2 | 1 | 4 | 0 | false |
| 08:05 | 0 | 0 | 0 | 0 | 60 | 0 | false |
| 16:05 | 0 | 0 | 0 | 0 | 60 | 0 | false |

At 01:00, median spread fraction is
`0.0001993918553381824420070463518` (~0.0199391855%), below the unchanged 0.10%
threshold. The same selected original fixture rows fail strict-v1 cadence;
all five strict-v1 spread diagnostics are false. All **owner-receipt** runs
select zero because no owner arrivals are recorded. Unknown owner receipt is
not called an invalid market price or replaced by provider arrival.

At 01:00 and 01:05 the two unselected rows include a duplicate and a temporally
late row. Invalid counts and reason membership counts are different: one row
can have DUPLICATE_SOURCE_ROW and DUPLICATE_EVENT_IDENTITY. Unselected does not
mean invalid: newer eligible alternatives can displace valid observations.
Missing 08:05/16:05 fixture coverage remains missing. The report never calls a
v2 pass real C02 eligibility. Selected source classes remain reconstructed quotes.

The pure test oracle independently creates 60 irregular synthetic events and
checks each expected endpoint/row identity, exact Decimal statistic and strict
v1 failure. Adversarial tests cover missing/stale/late/unknown/future clocks,
inverted chronology, raw and native identity duplicates/conflicts, numeric
formatting, source order, repeated offered rows, inclusive boundaries, cutoff
rounding/freshness, tampered evidence, cross-source/symbol/scope contamination,
late-discovered contradictions and scanner/replay serialization parity. The
production scanner still rejects irregular event spacing even with sampled_at.

## Windows / OpenBot owner-original command

Use the reviewed branch/PR checkout with Python 3.12 and the **existing** original
files in Downloads. OpenBot can run this exact PowerShell block from the existing
owner repository; it installs only repository test dependencies into a local
venv, makes no market/account request, and creates no collector or trade plan.
No hash override or alternate original filename is accepted. If dependencies
are already installed, use that environment and run only the final command.

```powershell
Set-Location 'C:\Users\User\AstraBot'
py -3.12 -m venv 'work\s02-venv'
& '.\work\s02-venv\Scripts\python.exe' -m pip install --disable-pip-version-check -r requirements-test.txt
& '.\work\s02-venv\Scripts\python.exe' 'scripts\s02_source_diagnostic.py' --original-root 'C:\Users\User\Downloads' --output-dir 'work\s02-original'
if ($LASTEXITCODE -ne 0) { throw 'S02 original-file acceptance failed; do not classify the source as accepted.' }
```

The final command verifies all three compressed SHA-256 pins **before parsing**,
fully consumes each gzip for CRC/schema validation, enforces symbol/day and
original row counts, checks source hashes again after reading, and emits:

- `work\s02-original\S02_DIAGNOSTIC.json`: four fixed cutoffs 00:30, 01:05, 08:05,
  16:05 UTC; exact raw window/selected/unselected/invalid counts; full-day feed
  diagnostics (including full-day quote duplicate/regression/inversion/minute-coverage/gap/delay counts); slot states/ages/reason counts; v1/v2 comparison; source and version
  hashes. Missing data never yields a fabricated median or pass.
- `provider-HHMM.json.gz`: all offered quote rows for the declared window, raw
  cells/clocks and exact selected identity for all 60 endpoints, including missing
  slots and machine exclusions. These detailed records stay owner-local.

Raw window is `[cutoff-60m,cutoff]` by exchange clock, without provider-arrival
prefilter, so late rows remain auditable; the summary reports all other day rows
as outside this declared window. Each sampler invocation is bounded to 100,000
rows and aborts above it. Derivative/book audits reuse C05-G; those utilities
exclude duplicate/inverted observations but retain raw counters. The **quote**
path deliberately retains duplicates/inverted clocks for S02 rejection evidence.
Malformed/truncated feeds, wrong hashes/counts or mixed symbol/day abort the run;
partial output is never a source acceptance result. Avoid reusing output from a
failed command; only a fresh successful run is reviewable. A directory containing
a prior summary is rejected, so a failed rerun cannot be mistaken for its old result.

Original-mode status is HASH_PINNED_DIAGNOSTIC_ONLY_REQUIRES_REVIEW, never automatic
SOURCE_ACCEPTED. Owner arrival remains null. Compare uncompressed evidence SHA-256
across hosts; code/contract version hashes normalize UTF-8 text newlines to LF,
while original feed hashes always bind exact compressed bytes. Gzip output fixes
mtime/filename/OS header; runtime compression-library differences need not change
uncompressed evidence identity. No detailed real sampled rows are uploaded to Git
without independently established redistribution rights.

## Offline reproduction and technical acceptance

From repository root (Python 3.12; pinned requirements):

```sh
python -m pip install --disable-pip-version-check -r requirements-test.txt
python -m pytest -q tests/test_s02_source_clock.py tests/test_c02_data.py tests/test_c02_universe.py tests/test_c02_panel.py tests/test_c05g_historical_pipeline.py tests/test_c05h_historical_evidence.py
python scripts/s02_source_diagnostic.py --synthetic-fixture --output-dir work/s02-verify
python -m compileall -q src/astrabot tests scripts
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q
python scripts/c03_research.py --check --summary
python scripts/c03_research.py --c02-panel --check
python scripts/c04_replay.py --check --output-dir work/s02-c04-check
python -m pip check
git diff --check
```

The CLI test reruns into two fresh directories and compares both with committed
machine evidence. Contract schemas must match generated Pydantic JSON schemas;
all nine matrix rows require native fields, units, time/provenance/coverage,
validation, evidence and missingness. Existing C05-H tests cover the supported
quantity conversions and reject future-known/cross-dataset unit claims.
`python scripts/s02_source_diagnostic.py --write-contract` regenerates the wire
schema only when the proposed contract intentionally changes.

Final local suite count, delivery head and GitHub Actions result are recorded in
the engineering journal/PR delivery metadata. The committed synthetic summary
records exact normalized code/contract/requirements hashes and all input pins;
no self-referential hash is inserted into its own payload. The PR is not self-merged.

## Acceptance still pending

The owner run resolves only hash-pinned one-day mechanics/temporal reliability
within the recorded provider clocks. Acceptance still requires native BBO/depth
identity/reset evidence, complete dated metadata/filters/multipliers, OI-specific
measurement and mark timing, historical ticker/universe, verified news coverage,
settlements/position alignment and real execution costs/latency/fills. Each field,
reason, acceptance test and cheapest next artifact is explicit in the matrix.
New strategy-specific spending stays HOLD because PC2/FR2 v0.1 also failed their
economic advancement criteria. Session 03 can implement safe missingness and
reuse these contracts without changing policies or production eligibility.
