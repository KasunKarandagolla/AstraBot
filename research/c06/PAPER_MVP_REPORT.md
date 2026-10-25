# C06-B Offline OpenBot-Facing Paper MVP Report

**Date:** 2026-10-25
**Branch:** `codex/c06-b-offline-openbot-paper-mvp`
**Verified base:** `4a16e96f1229974af8cbc8b28e0e57acccb4ec2e`
**Scope:** Owner-authorized Option B: one offline-only C06 paper demonstration while P3 economics remain on hold.

## Compatibility status

- `OFFLINE_ORCHESTRATION_TESTED`: **YES**. The deterministic offline driver called the six typed tools and ran the fake-owner/fake-venue lifecycle below.
- `REAL_OPENBOT_INTEGRATION_VERIFIED`: **NOT_VERIFIED**. No `openbot` executable or reusable runtime was found on `PATH`, in the repository source, or in the targeted Cloud `/opt` and `/usr/local` search. No OpenBot package was installed and no external OpenBot site was probed. This report does not claim an OpenBot LLM, runtime, or OS permission boundary.

The exposed tool names are `scan_opportunities`, `evaluate_symbol`, `evaluate_candidates`, `prepare_plan`, `get_plan_status`, and `get_operations_summary`. Input models reject extra fields. The coordinator wrapper has only a tool-call method and has no approval, claim, or submission method. `prepare_plan` emits a frozen, non-executable proposal from an existing C03 `RESEARCH_ONLY` decision.

## Reused and new code

Reused without changes to C01–C04 strategy or lifecycle behavior:

- C02 `scan_universe` and its typed eligibility observations.
- C03 `evaluate`, `ResearchDecision`, `ResearchSetup`, and the existing synthetic market fixture.
- C04 `synthetic_eligible_panel()` from `astrabot.research.replay`.
- C01 `FakeOwner`, `FakeVenue`, `FakeClock`, `TradeAuthorizationV15`, and the existing one-use, risk, protection, timer, and flat-reconciliation checks in `tests/c01_fake.py`.

New files:

- `src/astrabot/c06/paper_mvp.py`: six-tool input/output models, immutable proposal, harness-side plan status, and append-only per-run machine event journal.
- `scripts/c06_paper_demo.py`: deterministic offline driver and reproducible positive/negative demonstrations.
- `tests/test_c06_offline_openbot.py`: focused contract, boundary, negative-case, no-network, timer, and journal tests.
- `research/c06/PAPER_MVP_REPORT.md`: this evidence report.

The machine journal is an immutable, append-only in-memory event stream for each run. Its summary digest reproduces across identical runs. It is not a durable production journal. C01's fake owner ledger uses temporary SQLite files during the demo.

## Positive trace

The C04/C03 fixture produced a synthetic `ALTUSDT` T1 candidate with `RESEARCH_ONLY` status. Proposal terms were copied from that candidate: entry bounds `100.38–100.42`, quantity `10`, stop `99.56`, targets `101.28` (40%) and `108` (60%), modeled loss `8.849980 USDT`, and notional bound `1004.20 USDT`. These are test values, not observed market values or profitability evidence.

The fake owner approval was bound through C01's immutable authorization hash to the plan hash, nonce, risk terms, and expiry:

- Plan ID: `f313dfa5896e97b25600f5d1f7f64e28fde8797ee4f3dbb5060fc63868d448a4`
- Proposal hash: `228440732d9b5916b5928917710f5ced849cd3a600b7ac1a7ef33ca634e324ce`
- C01 authorization hash: `bb01ceacc3ca3a857278bd635bbb30fc7c838426cbf5b00ddf557a15cdcfff82`
- One-use nonce: `e6fcea71dbad0055c945bc53c2c9843c430e03355dd085fe86c00e0796434f06`
- Approval expiry: `2025-02-01T08:06:35Z`

The fake authentication evidence values are fixtures, not production owner authentication or MFA. The fake owner consumed the authorization once. A second claim with the same authorization and nonce was rejected before another venue write. The fake venue recorded a full entry fill of `10 @ 100.42`, then an immediate simulated stop at `99.56`. TP1 reduced `4` at the fixture target `101.28`, leaving `6`; the first-fill time remained unchanged.

After the position opened, both coordinator and journal roles were made unavailable. C01's independent fake supervisor initiated the reduce-only time exit exactly `11h55m` after first fill, at `2025-02-01T20:00:05.150001Z`. The fake venue used the already-bound entry bound `100.42` as the synthetic closing fill input, then C01 confirmed `FLAT_RECONCILED` with quantity zero after dormant instructions were cancelled. No return or profitability statistic was calculated. The per-run journal contained 8 events; summary digest: `37d12394f4f1830b54ad01ffa07978e2b51e95935345aaf01034528da76523b7`.

## Negative cases

Every case ended with zero unauthorized new exposure:

- Fake owner rejection: `OWNER_REJECTED`; venue writes `0`.
- Approval expiry: claim rejected after expiry; venue writes `0`.
- Duplicate approval/nonce: second claim rejected with no second entry.
- Missing event clearance: C03 returned `NO_TRADE` (`C02_UNIVERSE_NOT_READY`, `EVENT_CLEARANCE_MISSING_OR_FUTURE`); plan preparation rejected.
- Missing market evidence (metadata and depth): C03 returned `NO_TRADE` (`C02_UNIVERSE_NOT_READY`, `METADATA_MISSING`, `DEPTH_MISSING`); plan preparation rejected.
- Coordinator risk override: an extra numerical risk field failed typed input validation before plan creation.
- Tampered C01 risk value: the modified value failed the original immutable authorization hash check before any fake venue write.
- Coordinator and journal outage after entry: coordinator tool access and journal summary failed while unavailable; independent first-fill supervision still exited and reconciled the existing position. No additional entry was submitted.

The demo's exit fill and all market values are explicitly fixture-driven. It makes no Binance, Tardis, account, signing, order, or other runtime network request. A focused test also patches socket creation and `urllib` URL access to fail; the offline demo passes under those guards.

## Reproduction and test evidence

Portable repository command, with the pinned test requirements available in the Python environment:

```bash
python scripts/c06_paper_demo.py
```

Cloud invoked it with `/workspace/work/c06-venv/bin/python scripts/c06_paper_demo.py`:

```text
C06-B offline OpenBot-facing paper MVP (fixture-driven)
OpenBot compatibility: NOT_VERIFIED
Fixture: C04_SYNTHETIC_FULLY_ELIGIBLE_TEST_FIXTURE; demo exchange/account/network calls: none
tool scan_opportunities -> ALTUSDT / READY / SYNTHETIC_FIXTURE
tool evaluate_symbol -> RESEARCH_CANDIDATE / READY
tool evaluate_candidates -> RESEARCH_ONLY
tool prepare_plan -> executable=false / plan=f313dfa5896e97b25600f5d1f7f64e28fde8797ee4f3dbb5060fc63868d448a4
tool get_plan_status -> CLOSED_RECONCILED
tool get_operations_summary -> 8 events / digest=37d12394f4f1830b54ad01ffa07978e2b51e95935345aaf01034528da76523b7
fake owner -> one-use consumed; replay rejected; entry=10 @ 100.42 (fixture)
supervisor -> protected; partial exit=4; remaining=6
coordinator+journal unavailable -> first-fill timer initiates reduce-only exit at 2025-02-01T20:00:05.150001Z
fake venue -> final FLAT_RECONCILED quantity=0
negative owner_rejected -> venue_writes=0 / new_exposure=false
negative approval_expired -> rejected / venue_writes=0 / new_exposure=false
negative missing_event_evidence -> NO_TRADE / prepare_plan=REJECTED
negative missing_market_evidence -> NO_TRADE / prepare_plan=REJECTED
negative checks -> risk_override=REJECTED_BY_TYPED_SCHEMA; tampered_hash=REJECTED_BY_C01_FAKE_OWNER; nonce_reuse=REJECTED_WITH_NO_SECOND_ENTRY
```

Commands and results in the pinned disposable Cloud environment:

| Command | Result |
|---|---|
| `/workspace/work/c06-venv/bin/python scripts/c06_paper_demo.py` | Exit 0; positive trace and all negative demonstrations completed |
| `/workspace/work/c06-venv/bin/python -m pytest -q tests/test_c06_offline_openbot.py` | **5 passed** |
| `/workspace/work/c06-venv/bin/python -m pytest -q` | **217 passed** (full repository suite, including existing C01–C04 regressions) |
| `git diff --check` | Passed |

The test environment was an isolated venv populated from the repository's pinned `requirements-test.txt`. No OpenBot or speculative agent framework was installed.

## Limits and remaining blockers

- Real OpenBot runtime/version, tool registration compatibility, model tool-call behavior, and process/OS isolation are **not verified**. Minimum remedy: make a genuine OpenBot runtime/version available, wire these six schemas through its supported adapter, and run permission and tool-call conformance checks there.
- The owner/MFA identity is a C01 fixture. This does not verify real authentication, approval UX, or security.
- Fake venue behavior and the final time-exit fill are software fixtures; they do not establish Binance behavior, demo safety, execution quality, or profitability.
- The event journal is per-run memory only. A durable runtime would need an append-only persisted event store and restore/replay tests.
- P3 remains `INSUFFICIENT_EVIDENCE`; T1/R1/B1 remain `RESEARCH_ONLY`. This work awards no P3 economic credit, no P4 phase credit, and no C07 authorization. Verified project accounting remains **45% credited / 55% unqualified** pending independent project-lead review.

## Resource use

One Codex Cloud session; no subagents; one disposable pinned-dependency venv. The repository base was fetched from GitHub and test packages from the configured package index. No Binance/Tardis/API/account/signing/order calls or market-data downloads were made. The full suite took `13.75s`; the focused C06 suite took `1.95s`; model quota, CPU/memory totals, and end-to-end session accounting were not exposed.

`C06_B_OFFLINE_PAPER_MVP_READY_FOR_INDEPENDENT_REVIEW`
