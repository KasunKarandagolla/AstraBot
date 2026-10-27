# Integrated offline research MVP — RC1

2026-10-27 (Asia/Colombo). Initial independent base:
`0d5b45c4ccdadd782f9b4f42f290f35faf445a60`; subsequently reconciled with merged
main `2f2ea0bc87d4004dee71f4b71f4143ba9e5585b1` after PR #28 was independently
accepted during this task. **NEXT_GATE: independent review of RC1; then an owner
HOLD / separately preregistered hypothesis-revision decision.** No economic,
Demo or live phase promotion. Formal qualification remains **45%**.

## Working capability

The existing C05 command now joins verified local research, all-ten-family
readiness reporting, frozen policy decisions, the existing six C06 tools,
source identities and an event-derived owner explanation. A sealed historical
snapshot can be reopened by the same MCP server used by OpenBot. Its historical
mode rejects every proposal request: all original policies remain unqualified.
The same operator command has a physically separate synthetic mode which drives
the existing MCP, C01 fake owner and independent C06 fake supervisor through a
complete protected lifecycle. No second simulator, writer, database, service or
dependency was introduced. This is new operator integration, not another C06-F
host acceptance claim; C06-F's `_run` acceptance routine is not invoked.

## Launch

From the repository root, with Python 3.12 and the existing pinned environment:

```sh
python -m pip install -r requirements-test.txt
python scripts/c05_integrated_research.py --mode authentic --output-dir work/rc1
python scripts/c05_integrated_research.py --mode synthetic --output-dir work/rc1
```

The first command uses the checked-in **authentic, incomplete C02 sample**. It
performs no network requests and needs no exchange credentials. The second uses
only synthetic observations, fake owner identity/MFA and a fake exchange. It
isolates child environments with the existing C06 allowlist and instruments
outbound networking to fail. Existing synthetic state is never reset: choose a
fresh output root for another demonstration. Authentic files can be reproduced
at the same path without creating plans or owner/venue stores.

Outputs are under `authentic/` and `synthetic/`: `OPERATOR_PACKET.json` (also
deterministic gzip), `EVENTS.jsonl`, and `OWNER_SUMMARY.md`. The authentic directory
also contains the existing complete C05 packet and one MCP snapshot per symbol.
The synthetic directory retains the marked scenario directories and the existing
C06, owner and fake-venue SQLite files for restart inspection. JSON packet hashes
exclude their own digest; gzip timestamps and filenames are fixed. Run IDs and
events depend on source/configuration/fixture evidence, not wall-clock time or
output paths. These are reproducibility checksums, not external signatures.

To connect OpenBot to a generated genuine snapshot, configure its existing MCP
stdio connection to run:

```sh
python scripts/c06_mcp_server.py --research-snapshot work/rc1/authentic/BTCUSDT_MCP_SNAPSHOT.json
```

Exactly six tools remain: scan, symbol evaluation, candidate evaluation, proposal,
plan status and operations summary. Historical `scan_opportunities` explicitly
returns `OBSERVED_HISTORICAL_RESEARCH`; proposal requests are rejected, unknown
plan status stays unknown, and journal events survive process restart through
the sealed snapshot. The server validates the digest and reproduces the frozen
evaluation and event IDs. The existing positive synthetic MCP startup still
works unchanged. Neither mode adds approval/order/shell/credential tools. This
release verifies actual SDK stdio subprocess calls; it does not claim a new
owner-hosted OpenBot runtime acceptance.

To inspect the retained fake state without rerunning the scenario:

```sh
python scripts/c06_fixture_owner.py --fake-only --state-dir work/rc1/synthetic/state/positive list
python scripts/c06_fake_supervisor.py --fake-only --state-dir work/rc1/synthetic/state/positive status
```

The **original seven-symbol C04 archive interface is retained**:

```sh
python scripts/c05_integrated_research.py --mode authentic --data-root /path/to/c04-data --start 2024-09-01T00:00:00Z --end 2024-09-02T00:00:00Z --interval 1h --output-dir work/seven-symbol-rc1
```

That command now reuses the **independently merged** monthly source-bound loader
from PR #28 (main `2f2ea0b`). The complete frozen 112-file manifest is validated,
but only the 84 July–September source files are opened for this September scope;
28 October archives stay unopened. The source cutoff is the first month boundary
covering the explicit evaluation end. The new boundary tests include an exclusive
October 1 end (still no October source bytes) and an explicitly selected October
2 end (October source files then required). No data is downloaded by the operator.

RC1 was originally built independently at `0d5b45c` without PR #28 code. When the
lead independently accepted and merged PR #28 at 02:18:31 UTC during this task,
main advanced to `2f2ea0b`; RC1 merged that actual main, resolved only documentation
conflicts and then adopted its reviewed loader API. There is no unmerged dependency
or secret cherry-pick. The above seven-symbol run was executed **twice**, with
byte-identical JSON/gzip packets and events, reusing the same retained cache.
The historical BTC snapshot from that run also passed actual six-tool MCP stdio
reopening in two fresh processes. October remains unopened.

RC1 operator evaluation is capped at one day's cutoffs (24 hourly / 288 five-minute
cutoffs); the original C05 CLI remains available for longer research by omitting
`--mode`. History limits and the original fixed archive plan are reused. This is
bounded offline operation, not a broad-universe or indefinite collector benchmark.

The owner SOLUSDT case remains consumable through the **existing G/H interface**:
add `--feed-data-root`, `--symbol SOLUSDT`, `--date 2024-10-01`, the original
`--source-manifest` if needed and `--evidence-manifest`, with matching local
candle scope. G validates all three original gzip hashes and consumes each feed
to EOF; H validates supplied historical artifacts. No Windows private paths are
assumed. Synthetic G/H inputs are refused in authentic mode. This Cloud session
did **not** replay the unavailable original owner feeds or accept any new source
assertion. Existing G/H joins and unit/causality tests remain the acceptance evidence
for that interface, not a new authentic host run.

## Actual outputs

The committed packets in `rc1/authentic/` (seven symbols) and `rc1/synthetic/`
are compressed copies of the actual command outputs, with separate owner summaries.
The tiny default C02 smoke run is tested separately and needs no external cache.

**Committed authentic seven-symbol result:** 266,616 normalized original bars
from 84 verified July–September archives; 168 hourly symbol-windows on September
1; **1,008 NO_TRADE policy-side decisions**, zero eligible windows, zero strict
candidates/trades and no outcome rows. Price-only diagnostics retain **17
formations / three confirmations**, outside admission. Each window is vetoed by
missing dated metadata, ticker, 60-sample spread history, depth, validated OI and
verified events. Existing C03 context is actually exercised (90 TREND_DOWN, 66
UNCLASSIFIED and 12 BREAKOUT_EVENT contexts); session VWAP is ready at the last
operator snapshot. The seven operator records at September 1 23:00 UTC (September
2 04:30 Colombo) retain **8,708 unique symbol/interval/native-ID bars**. Every one
was independently matched to exact original OHLC in 56 pinned archive CSV members.

**Default bundled smoke command:** the pinned C02 files contain 24 BTCUSDT hourly candles for
2024-10-28 and 100 APEUSDT aggregate trades for 2024-10-18. All 124 source rows
are checksum verified. C05 evaluates **48 symbol-windows**, **288 policy-side
NO_TRADE diagnostics**, zero eligible windows, zero strict candidates, zero
historical trades and no outcome rows. The operator presents both symbols at the
last candle cutoff, 2024-10-29 00:00 UTC (05:30 Colombo). Its BTC packet retains
all 24 original native IDs/OHLC/availability observations, scoped by symbol and
interval. Missing metadata, ticker, 5m/15m/1h/4h warm-up, spread history, depth,
validated OI and verified events are enumerated. APE has no policy candle history;
the trade smoke file is not promoted to CVD or a candidate. No profitable or
eligible historical trade is claimed. C04's explicit synthetic account/cost
overlay remains labeled as a hypothesis; the operator has **no reconciled account
evidence** and cannot generate an authentic approval.

**Synthetic positive:** T1 fixture proposal → immutable fake approval → one-use
claim, duplicate refused → unknown entry acknowledgement reconciled after restart
without a duplicate write → **5 units** partially filled and verified stop →
unfilled IOC remainder canceled by the existing timer → original TP1 reduces to
**3 units**, protection and first-fill time unchanged → fresh supervisor process
observes the same quantity → **11h55** reduce-only flatten attempt (unknown exit
acknowledgement handled by C01) → deliberately unfilled remainder reaches **12h**,
which records `TIME_EXIT_BREACH` and emergency handling → fake exit fill →
`FLAT_RECONCILED`, zero owner/venue quantity, no unresolved intents → C06
`CLOSED_RECONCILED` and verified Journal role. This scenario intentionally tests
the hard-deadline failure branch; it does not claim the simulated venue was flat
before 12h. Orders, fills, original stop/TP parameters, risk reservation and
every operator observation are retained in the machine packet.

**Negatives:** rejected and expired proposals cannot consume approval or write
to the fake venue. A separately approved but **stale original trigger, before
proposal expiry**, cannot be consumed (zero writes). A rejected protective stop
produces `MISSING_PROTECTION` and uses the existing emergency reduce-only path
until verified flat. Each scenario has its own marked directory and journal.

## Acceptance and limits

`tests/test_research_mvp_rc1.py` executes both CLI modes, checks native source
identities and A01–A10 readiness, prevents historical proposals, inspects actual
durable fake-owner/venue state, checks one-use approval, partial quantities,
unchanged first fill, both deadlines and critical protection handling, reopens
authentic MCP in two subprocesses, rejects an extra risk field and tampered or
synthetic snapshots, and reproduces byte-identical packets/events in fresh paths.
The full post-merge suite passed **339 tests in 127.45 seconds**, including nine
RC1 operator checks, repaired C05-L tests, source-month boundary regressions and
reproduction of all seven committed operator decisions from their exact bars.
The final MCP description update also passed all four protocol checks. Compilation, dependency integrity, deterministic C03 golden
and incomplete-panel checks, C04 blocker replay and whitespace checks passed.
Exact final-head GitHub CI is recorded in the PR handoff after publication.

The machine [readiness matrix](RELEASE_READINESS_RC1.json) separates software
implementation from formal phase qualification. Full A04/A05/A08 analytics,
qualified expectancy registry, real owner MFA/approval service, production
fencing/watchdog/backup and genuine Binance adapter remain incomplete code or
unqualified integrations. Dated metadata, accepted spread clock (#22), OI/depth
semantics, ticker/events, execution costs/fills and representative causal economic
evidence are **external/economic blockers**, not bugs that another wrapper fixes.
Nine historical source requirements remain unaccepted per the external C05-M
owner handoff summarized in issue #18; no C05-M artifact is invented in Git.

PR #28's repaired evidence head is `510165f3ad2f35142da927b7cf4ee601dc24ba10`;
its [exact-head CI](https://github.com/KasunKarandagolla/AstraBot/actions/runs/40436282335)
passed. Independent review `5661492640` accepted that repaired research evidence;
PR #28 was merged externally at `2f2ea0b`. Its verdict is T1_INDETERMINATE,
24 original stop touches and zero original second targets before stop. C05-M HOLD_REVISE and the 210-day study DEFER remain current.
Code integration does not establish P3 edge, P5 Demo acceptance or live readiness.

Shortest legitimate next step: independently inspect RC1 and its machine
evidence, run the existing historical snapshot through the actual owner OpenBot
host when available, then have the owner choose HOLD or an explicitly preregistered research
pivot without changing original T1/R1/B1. Source-clock/source/host procurement
decisions become consequential only for a justified, separately authorized
empirical route. No collector, purchase, credential use, exchange account contact,
C07, Demo deployment or live order is authorized or implemented here.
