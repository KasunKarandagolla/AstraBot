# C06-E — Integrated Durable Offline Paper Runtime

**Status:** implemented for review on `codex/c06-e-integrated-durable-paper-runtime`. This is a synthetic/fake-only engineering milestone. It does not qualify P3 economics, OpenBot execution, production owner authentication or Binance Demo.

## Reproduce

From the repository root, install the pinned test dependencies in a local environment and run the offline lifecycle:

```bash
python -m venv .venv
.venv/bin/pip install -e . -r requirements-test.txt
.venv/bin/python scripts/c06_paper_demo.py --fake-only --data-dir /tmp/astrabot-c06-e
.venv/bin/python scripts/c06_paper_demo.py --fake-only --data-dir /tmp/astrabot-c06-e --resume
```

`--data-dir` is optional for a temporary in-process fixture. A persistent directory is never silently reset: the fresh-run command rejects existing C06/owner/venue databases, while `--resume` reopens them and reconciles the saved lifecycle.

To inspect the separate owner boundary before the one-use claim:

```bash
.venv/bin/python scripts/c06_paper_demo.py --fake-only --data-dir /tmp/astrabot-c06-staged --prepare-only
.venv/bin/python scripts/c06_paper_demo.py --fake-only --data-dir /tmp/astrabot-c06-staged --resume --owner-decision approve --approve-only
.venv/bin/python scripts/c06_paper_demo.py --fake-only --data-dir /tmp/astrabot-c06-staged --resume
```

The second command persists an explicitly simulated owner approval and stops before claim. A later resume uses C01 to atomically claim the one-use nonce/reservation, then continues from persisted venue truth. `--owner-decision` accepts `approve`, `reject` or `expire`. The fixture identity is explicitly **not real MFA**. `--clock "2025-02-01T20:00:05.150001+00:00"` is available with `--resume` for deterministic supervision-time tests. The harness contains no Binance order client, API credentials or signed-request code.

## Persisted state and recovery

`c06_state.sqlite` holds:

- Immutable serialized research-plan payload, exact hash, stable lifecycle ID, expiry and status.
- Append-only plan-transition history, checked against the current status on restore.
- Append-only correlated machine events with deterministic IDs, `occurred_at`, `received_at`, lifecycle/plan/correlation IDs, details and a verifiable hash chain. Duplicate event IDs are idempotent; event updates/deletes are blocked by SQLite triggers.
- Operations summaries derived from the persisted machine events.

`owner.sqlite` and `venue.sqlite` remain the existing C01 fake owner's separate databases. Claim, nonce consumption, capacity reservation and entry intent are atomic only inside the C01 owner ledger. No transaction spans that ledger, the C06 state database and fake venue I/O. On reopen, the runtime reconciles the C06 plan mirror with C01 approvals/nonce consumption, then C01 reconciles its intents, fills, protection and position against fake venue state. A missing order for an unresolved entry/exit remains unresolved; the runtime does not blindly resubmit. Active exposure without verified protection fails closed. The C01 fake supervisor and 11h55m timer do not depend on the coordinator or reporting-journal availability in the demonstration.

The six MCP tools stay `scan_opportunities`, `evaluate_symbol`, `evaluate_candidates`, `prepare_plan`, `get_plan_status`, and `get_operations_summary`. Approval, claim, submission, owner decisions and account controls are not MCP methods.

## Verified fault scenarios

The durable restart integration suite simulates fresh objects opening the same files after:

1. Proposal persisted before owner approval.
2. Fake owner approval committed before the C06 status mirror updates.
3. Entry intent submitted with an unknown acknowledgment and correlated venue order.
4. Partial entry fill before local fill detection/protection recovery.
5. Stop protection acknowledged before restart.
6. Partial take-profit fill.
7. First-fill +11h54m, then a restart crossing the 11h55m flatten threshold.
8. Unknown exit acknowledgment with a correlated reduce-only order.
9. Exit fill before terminal flat reconciliation.
10. Unknown entry acknowledgment with no venue-correlated order, which stays halted with reservation retained and no second write.

Other tests verify immutable plan/hash restoration, status/transition consistency, persistent expiry/reject/consumed reuse rejection, deterministic event IDs, idempotent append and reopen, journal summaries, plan/event corruption rejection, default in-memory behavior, fake-owner rejection, risk tampering, missing event/market data and exact 11h55m time exit.

## Test evidence

Verified commands and results:

```bash
.venv/bin/python -m pytest -q
# 237 passed in 30.20s
.venv/bin/python -m pytest -q tests/test_c06_offline_openbot.py tests/test_c06_durable_runtime.py
# 21 passed
```

The offline runtime command and `--resume` path were also run against a persistent directory; the positive summary ended `FLAT_RECONCILED`, reopening preserved the same five fake venue writes and derived the event summary from SQLite. The persistent runtime test denies sockets, `create_connection` and URL opens. The full suite includes the existing MCP stdio discovery and Windows process compatibility tests. No CI run is claimed here; the local full-regression result is the evidence available before publication.

## Limitations and remaining safety work

- C01 fake owner/venue semantics are assumptions for tests, not a production OMS or proof of Binance conditional-order behavior.
- The C06 plan store, fake owner ledger and fake venue do not share a database transaction. A crash between owner decision/claim and mirror/report updates is handled through reconciliation, but unresolved or contradictory truth halts progress.
- SQLite files have integrity/hash checks, not backup, encryption, multi-host consensus or operational restore certification.
- Fixture approval uses synthetic identity/evidence. An authenticated human approval service and its threat model, key handling, audit trail and MFA verification remain unimplemented.
- No actual OpenBot-hosted model approved or executed this lifecycle. The six-tool read-only/proposal MCP surface remains separate from the fixture owner interface.
- P3 remains `INSUFFICIENT_EVIDENCE`; T1/R1/B1 remain `RESEARCH_ONLY`. This milestone does not qualify a strategy or establish expected economics.
- Before any Binance Demo phase, separately qualify the one selected writer, conditional order/partial-reduction semantics, protection and outage behavior, account mode, durable storage/backup and recovery operations, monitoring/alerting, authenticated owner authorization and all applicable fault cases against the actual adapter.

Keep official phase accounting at **45% credited / 55% unqualified**. Do not start C07, connect Binance order endpoints, or claim demo/live readiness from this fake-only result.
