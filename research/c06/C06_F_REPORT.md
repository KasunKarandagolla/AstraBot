# C06-E Repair + C06-F Offline Paper Workflow Report

**Status:** prepared on PR #23, branch codex/c06-e-integrated-durable-paper-runtime.
**Boundary:** synthetic fixture only. This report does not qualify P3 economics, P4 production operations, real human MFA, Binance Demo, strategy profitability or live trading.

## Delivered implementation

- Restart after a persisted C01 entry intent is permitted only when the original immutable authorization, one-use nonce, reservation, client order ID and C01/venue absence records jointly prove that the entry did not cross the fake venue boundary. SUBMITTED, UNKNOWN_SUBMISSION, missing or contradictory evidence stays halted.
- EventJournal writes now enforce the same plan/lifecycle correlation rule as restore. Durable status and journal reads refresh and verify SQLite state from a consistent read snapshot.
- The MCP server retains the same six tools and typed input/output schemas. --state-dir is an opt-in at process startup; it is not an MCP argument. A marked synthetic directory holds the C06 plan/event database and the existing C01 owner and venue databases.
- scripts/c06_fixture_owner.py provides separate local list, show, approve, reject, expire and consume commands. show reads without initializing or reconnecting the owner/venue stores. The identity is always FIXTURE_OWNER_NOT_REAL_MFA.
- scripts/c06_fake_supervisor.py reopens and reconciles existing C01 state, simulates entry/fills/protection/partial take-profit and the 11h55m/12h boundary, and persists an exit request before a disconnected venue call. Ambiguous writes are never blindly repeated. A later reduce-only identity is permitted only after a correlated terminal reduce and authoritative remaining position establish a late-fill remainder.
- src/astrabot/c06/role_summaries.py provides typed, read-only summaries. News/Events fixtures distinguish verified synthetic evidence, synthetic veto and unknown/unavailable; authentic_clearance always remains UNKNOWN. Journal output is derived from a verified C06 event chain and read-only C01 state, retains IDs/correlations and reports unavailable/inconsistent records explicitly.
- scripts/c06_acceptance_demo.py exercises the official MCP SDK, owner CLI and supervisor through fresh processes against shared SQLite stores. scripts/c06_fixture_reset.py removes only known SQLite files from a marked synthetic directory and refuses unrelated contents.

## Reproduction

Install the repository's pinned dependencies, then run:

~~~text
python -m pip install -e . -r requirements-test.txt
python scripts/c06_acceptance_demo.py --fake-only
~~~

To preserve the positive fixture stores for inspection:

~~~text
python scripts/c06_acceptance_demo.py --fake-only --state-dir C:\AstraBot-fixtures\c06-f-positive
~~~

The chosen path must be outside the repository and original market-data directories, empty on first use, and reserved for this synthetic fixture. A second run rejects existing stores unless reset explicitly:

~~~text
python scripts/c06_acceptance_demo.py --fake-only --state-dir C:\AstraBot-fixtures\c06-f-positive --reset
~~~

Or reset only the marked C06 fixture stores without rerunning the demonstration:

~~~text
python scripts/c06_fixture_reset.py --fake-only --state-dir C:\AstraBot-fixtures\c06-f-positive
~~~

The reset command retains .astrabot-c06-synthetic, removes only the known c06_state.sqlite, owner.sqlite, venue.sqlite and their SQLite journal/WAL/SHM files, and refuses the directory if any unrelated file is present. Do not point either command at market data, a general application-data folder or a real account database.

## Windows OpenBot operator handoff

Use the installed Python environment containing this checkout and the pinned packages.

1. In OpenBot's local MCP server settings, add a stdio server:
   - **Command:** C:\path\to\AstraBot\.venv\Scripts\python.exe
   - **Arguments:** C:\path\to\AstraBot\scripts\c06_mcp_server.py --fixture positive --state-dir C:\AstraBot-fixtures\c06-f-openbot
   - **Working directory:** C:\path\to\AstraBot
2. Keep C:\AstraBot-fixtures\c06-f-openbot dedicated to this marked synthetic fixture. Restarting OpenBot/MCP reopens the same verified proposal and event stores.
3. Through OpenBot, call scan_opportunities, evaluate_symbol, evaluate_candidates, then prepare_plan. Record the returned plan_id and immutable_hash; the plan remains RESEARCH_ONLY and executable: false.
4. In a separate PowerShell window, inspect and make only a fake fixture decision:

~~~powershell
$py = 'C:\path\to\AstraBot\.venv\Scripts\python.exe'
$root = 'C:\path\to\AstraBot'
$state = 'C:\AstraBot-fixtures\c06-f-openbot'
& $py "$root\scripts\c06_fixture_owner.py" --fake-only --state-dir $state list
& $py "$root\scripts\c06_fixture_owner.py" --fake-only --state-dir $state show <plan_id>
& $py "$root\scripts\c06_fixture_owner.py" --fake-only --state-dir $state approve <plan_id>
& $py "$root\scripts\c06_fixture_owner.py" --fake-only --state-dir $state consume <plan_id>
~~~

   Approval and consumption happen outside MCP. They use a deterministic fake identity, not a real owner, MFA or authentication service.
5. Independently step the fake supervisor. Each command is a new process over the same stores:

~~~powershell
& $py "$root\scripts\c06_fake_supervisor.py" --fake-only --state-dir $state status
& $py "$root\scripts\c06_fake_supervisor.py" --fake-only --state-dir $state submit-entry
& $py "$root\scripts\c06_fake_supervisor.py" --fake-only --state-dir $state fill-entry
& $py "$root\scripts\c06_fake_supervisor.py" --fake-only --state-dir $state partial-tp1
& $py "$root\scripts\c06_fake_supervisor.py" --fake-only --state-dir $state time-exit
& $py "$root\scripts\c06_fake_supervisor.py" --fake-only --state-dir $state fill-exit
~~~

   These commands only operate the deterministic fake venue. They do not wait 11h55m of real time and do not send exchange requests.
6. Restart the MCP server process in OpenBot, then call get_plan_status with the recorded plan_id and get_operations_summary with the lifecycle_id from supervisor status. The expected synthetic terminal state is CLOSED_RECONCILED with the Journal role reporting FLAT_RECONCILED.
7. To reset only this synthetic directory after review, close OpenBot and run c06_fixture_reset.py above. Reset refuses unmarked folders and any folder containing unrelated files.

**Owner-run OpenBot acceptance:** OWNER_OPENBOT_ACCEPTANCE_PENDING. Cloud-side MCP SDK tests prove protocol and process behavior, not that the owner's OpenBot build launched the server or performed this sequence.

## Verification record

The full repository run completed with **244 passed in 181.26s**:

~~~text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 work/c06-f-venv/bin/python -m pytest -q
244 passed in 181.26s
~~~

The focused C01/C06 regression command completed with **95 passed in 31.73s**. The dedicated official-MCP-SDK, fresh-process acceptance test completed with **1 passed in 112.10s**. It verifies exactly six MCP tools, two concurrent consume processes with one winning one-use claim, network attempts blocked at zero, disconnected exit with zero venue-write delta, unknown entry halted without resubmission, unknown exit management intent reconciled to its exact correlated fake venue order, a concurrent read-only Journal summary during supervisor recovery, final MCP reopen at CLOSED_RECONCILED, and final fake venue state FLAT_RECONCILED. Separate NO_TRADE, rejected and expired proposals all retain zero fake venue writes. Missing/rejected protection and late-fill fault cases remain fail-closed or use the already correlated reduce-only emergency close.

Compilation, pinned-environment dependency checks and whitespace validation also passed: compileall, pip check reported no broken requirements, and git diff --check was clean. The acceptance harness instruments its parent and subprocesses to reject outbound non-loopback networking and reports zero attempts. Its persistent stores are disposable synthetic fixtures only.

The final implementation commit and final-head GitHub Actions result are recorded in the delivery addendum below and in PR #23. Local checks do not prove owner-run OpenBot acceptance; that remains OWNER_OPENBOT_ACCEPTANCE_PENDING.

## Remaining limits

- Three SQLite files do not share one atomic transaction. A crash between C01 owner state and the C06 status mirror is recovered from each verified store where evidence permits; contradictions halt progress.
- SQLite transaction locks serialize local file operations only. There is no multi-host fencing, distributed lock, encrypted backup, restore certification, or 24/7 service monitor.
- The supervisor and owner CLI run only deterministic fake C01 classes. Test fills, stop visibility, reduce-only behavior, conditional-order interaction, latencies and outage recovery are not evidence of Binance behavior.
- --journal-unavailable models omission of supervisor step events while the reporting role is unavailable; C01 protection/reconciliation continues and the plan mirror catches up after journal recovery.
- Real OpenBot-hosted agent flow, real MFA, production owner service, Binance Demo, empirical P3 qualification and all strategy-economic conclusions remain unresolved. P3 stays INSUFFICIENT_EVIDENCE; policies remain RESEARCH_ONLY; phase accounting remains 45% credited / 55% unqualified.
