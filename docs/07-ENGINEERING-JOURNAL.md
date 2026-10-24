# 07 — AstraBot Engineering Journal, ADR Index and Delivery Ledger

**Type:** append-only factual handoff ledger, not a substitute for tests or code.  
**Last editorial checkpoint:** 2026-10-24 · preimplementation docs bootstrap.  
**Current phase:** `P0 — contracts and single-owner feasibility`  
**NEXT_GATE:** `C01 — Engine-owner ADR and frozen lifecycle/economics interfaces`  
**Next assigned Codex profile:** `Sol / complex` (if the named model is available).  
**Live funds enabled:** **NO**. **Any strategy economically qualified:** **NO**.

## Rules for updating this file

- Append **one short structured entry per meaningful Codex session**, PR and material architecture decision. Reference exact PR URL, commit SHA, test command/log artifact and evidence. Do not paste megabytes of raw output.
- Update the top `Current phase`, `NEXT_GATE`, and `Next assigned profile` **only after a reviewed gate/decision**, not because a minor issue was found.
- Keep decisions in an ADR table with statuses `PROPOSED`, `ACCEPTED`, `REJECTED`, `SUPERSEDED`; an ADR cannot alter owner-controlled shape or risk limits without explicit owner approval noted here.
- Preserve former entries; make corrections via new entries or a linked erratum. Journal summaries are **secondary to tests/code and external exchange truth**.
- Distinguish **implemented** / **tested** / **observed** / **inferred** / **untested** / **deferred**. No statement of profitability without results.
- Include enough context that a smaller-model bulk session can be reviewed independently by a higher-reasoning lead without rereading the full codebase. Summarize what matters, don't narrate every edit.

## Progress and persistent memory policy

Measure progress toward the **research-qualified and demo-safe v1 development definition of done**, **not** proven profitability or authorized live trading. Report after each reviewed Codex PR: `Estimated verified completion X% / remaining 100-X%`; breakdown and uncertainty, with basis. Use *rough phase-gate weights* P0 **10%**, P1 **15%**, P2 **20%**, P3 **25%**, P4 **10%**, P5 **15%**, P6 **5%**. Only award a phase's full weight when its evidence-based gate passes; optional provisional subphase credit must list objective completed artifacts and cannot imply promotion. The initial implementation estimate is **0%** as of this documentation review; original design consultation is complete but no gate has been implemented. If evidence invalidates a gate, revise the estimate openly. This rubric estimates product capabilities, not calendar time or Codex quota remaining.

After each reviewed session, add a **short durable memory capsule**: what changed in code, exact commits/PRs, verified tests and datasets, nontrivial implementation decisions and why, reproducible important defects and fixes, affected architecture/feature versions, next gate and owner questions. Preserve knowledge via source-linked ADRs rather than long conversational recollections. Distinguish research observations from production facts. Keep prompts/agent memories summarized with bounded retention; do not commit credentials, raw sensitive account data or large raw market streams into Git. Market-data storage and authoritative event truth follow `02`.

## Milestone / phase status

| Gate | Status | Actual evidence | Next |
|---|---|---|---|
| P0 architecture and consulted v1.5 | DESIGN BASELINE | preserved in `docs/reference/AGENTIC_SPEC_v1.5.md` | C01 owner-selection feasibility |
| P1 data / coin discovery / feature readiness | NOT STARTED | none | C02 after C01 |
| P2 T1/R1/B1 deterministic policies | NOT STARTED | none | C03 |
| P3 friction and full-policy research | NOT STARTED | none | C04–C05 |
| P4 OpenBot approval and agent tools | NOT STARTED | none | C06 after research gate |
| P5 Binance demo protected execution | NOT STARTED | none | C07 |
| P6 full demo and independent review | NOT STARTED | none | C08–C09 |
| Live pilot | BLOCKED BY DESIGN | no owner authorization; not a Codex task by default | separate owner decision |

## Decisions and ADRs

| ADR | Decision | Status | Evidence/owner authority |
|---|---|---|---|
| ADR-000 | OpenBot coordinator mandatory for new entries; three live roles; deterministic tools; 10 analytical families preserved | DESIGN BASELINE | Owner conversation / v1.5 |
| ADR-001 | Binance USD-M USDT perpetual, dynamic altcoins, 12h first-fill age, v1 risk ceilings, one-use human approval | DESIGN BASELINE | Owner conversation / v1.5 |
| ADR-002 | REUSE-FIRST, no separate OpenCode infrastructure, journal and phase-gated Codex cloud delivery | DESIGN BASELINE | Owner conversation / this bootstrap |
| ADR-EXEC-001 | Select one live order owner from SDK gateway, Freqtrade or NautilusTrader | **OPEN / C01** | must contain pinned test evidence and comparison |
| ADR-ENTRY-001 | Armed approvals vs post-trigger baseline | **RESEARCH CANDIDATE** | must include approval delay, fill and economics study |
| ADR-B1-001 | Original B1 TP ladder 40%@1R + 60%@2R remains research-only | ACCEPTED RESTRICTION | v1.5 arithmetic; no strategy performance claims |

## Session entry template — copy only when completing work

```md
### YYYY-MM-DD — Cxx — <short deliverable>
- **Phase / model / branch / PR / SHA:** Pn | Sol/Luna | `branch` | URL | `sha`
- **Intended gate and bounded scope:** one sentence each.
- **Actual implemented:** 2–5 bullets naming modules, interfaces and versioned component choices.
- **Observed tests / datasets / outputs:** exact command and summary; clear PASS/FAIL/NOT-RUN.
- **Important discoveries:** max 3, why they matter to project or economics.
- **Decisions made / ADR:** identifier, current status, whether owner sign-off obtained.
- **Open P0/P1 (if any):** reproduction + effect + minimal correction; no vague blocker.
- **P2/P3 deferred:** short note and reason it doesn't prevent NEXT_GATE.
- **Doc updates:** links/paths to sources updated in this PR.
- **Reviewer verdict:** PASS / PASS WITH DEFERRED NONBLOCKERS / BLOCKED; reviewer and date.
- **Estimated completion and remaining:** X% / Y% demo-qualified scope; gate credits and uncertainty, session/quota usage if measurable.
- **Expert strategy standard (where relevant):** upstream solutions examined; positive/failed practitioner cases; causal replay and discrepancies.
- **NEXT_GATE / next Codex task:** explicit phase-oriented action and why it follows.
```

## Initialization entry

### 2026-10-24 — DOC-BOOTSTRAP — Living documentation baseline
- **Intended gate:** establish reusable, synchronized project sources before Codex cloud code tasks.
- **Repository state before bootstrap:** GitHub metadata reported repository `KasunKarandagolla/AstraBot`, default branch `main`, size 0; GitHub contents endpoint confirmed empty. No prior code to migrate.
- **Prepared documentation:** root README, eight live `docs/` operational sources, one preserved v1.5 reference file; exact ten Markdown files including README.
- **Preserved vision:** OpenBot-only coordinator/free models, three roles, Binance USD-M dynamic altcoins, all ten families, sniper/target rules, approved one-use trades, twelve-hour age, active supervision, single execution owner, reuse-first and research-before-platform build.
- **Open implementation facts:** neither research nor exchange/tool integration has run. Model availability/permissions must be verified in the first actual Codex task.
- **GitHub publication VERIFIED:** initial bootstrap committed directly to the empty `main` branch (documentation initialization exception, not Codex implementation). GitHub recursively returned exactly ten Markdown blobs. The preserved v1.5 reference was uploaded at commit `7a6bc96e19c67d6216103312fc6c971130a67320`; each living file has a distinct initial commit, and project instructions are present. No PR was used because this initialized a blank repository.
- **GitHub content verification:** compared file-blob SHA-1 for all ten documents against local output; nine GitHub copies omit only the final newline, while the v1.5 reference is byte-identical. Package copies will match GitHub.
- **ChatGPT Project source sync:** **PENDING USER ACTION** — create a project, paste `docs/08-CHATGPT-PROJECT-INSTRUCTIONS.md` into Instructions, upload the same ten Markdown files from the provided ZIP. No tool here can create/modify the user's ChatGPT Project directly.
- **Bootstrap review:** doc count and instruction length verified, and agreement with fixed v1.5 vision inspected. There are **no implementation tests yet**. Next milestone unchanged: C01. No Codex session used for this bootstrap.
- **NEXT_GATE:** C01 / ADR-EXEC-001 and minimal lifecycle contracts. No signed Binance trading.

### 2026-10-24 — DOC-QUALITY-001 — Owner's expert-level and quota-aware refinement
- **Owner clarified:** prebuilt **best-working trading logic**, not superficial basic indicators; actual trader-level market interpretation; deep strategy research using implementation code, historical examples, charts and trading-community evidence, tempered by causal and economic testing. Maintain creative solutions without pointless defensive boilerplate or scope creep.
- **Delivery refinement:** choose Sol only for real unresolved complexity; use Luna on settled bulk implementation; default C05/C09 to independent project-lead reviews, optional Sol escalation. Use separable subagents where beneficial. The conditional critical path is now ~7 Codex sessions, not 9 automatic charges.
- **Continuity:** phase-weighted verified progress percentages after reviews; bounded market/agent memory and durable code/test/ADR journaling; owner asked on genuinely material unknowns. This changes **working methods and research rigor**, not the agreed trading vision or risk ceilings.
- **Tests/research:** DOCUMENTATION ONLY. No new implementation, validated strategy, historical replay or Codex session claimed. Phase and NEXT_GATE remain P0/C01.


## Deferred issues / parking lot (P2/P3 only)

No code-derived deferred issues yet. Add only with reason, affected phase, inexpensive next action, and a trigger for revisiting. Never create a new Codex session solely because an issue appears in this table.

| ID | Severity | Finding / evidence | Why deferred | Revisit condition |
|---|---|---|---|---|
| — | — | — | — | — |

## Post-PR review checklist (lead fills from evidence)

1. Which exact commit and files were reviewed? What contract or ADR changed?
2. Which test assertions were run? Are any PASS claims only narrative?
3. Can LLM/skill bypass owner approval or access exchange-write secrets? Are futures protection and first-fill time safe?
4. Is indicator data causal? Are fill/economics assumptions documented and conservative where needed?
5. Are there new dependencies or custom computations that violate reuse-first without justification?
6. Does this satisfy the CURRENT_GATE? Categorize findings, and do not turn a P2/P3 into a blocker.
7. Does a major architecture/trading/risk shift require owner sign-off? If so, halt that change only.
8. Update phase status, NEXT_GATE and ChatGPT Project sources if milestone docs were modified.

### 2026-10-24 — C01 — Execution-owner feasibility and v1.5 core contracts

- **Phase / branch / base:** P0; `codex/c01-engine-owner-feasibility`; latest fetched merged `main` at start: `e333818da488ea27788624dbc4937327faa52701`. Repository contained only the ten design sources, no prior implementation/ADR. All required living docs and focused v1.5 sections read. Implementation SHA/PR are recorded in the delivery addendum after GitHub creation; no self-referential commit hash is claimed.
- **Actual model / resources:** main session is GPT-6-based Codex (more specific backend identifier unavailable); four bounded subagents explicitly selected `gpt-6.1-sol` for SDK research, framework research, contracts/fault implementation and independent scoped audit. GPT-6.1 Sol was available through delegation. Token/quota/cost usage unavailable; no estimate invented.
- **Intended gate / scope:** compare three pinned single-owner candidates, freeze minimal v1.5 interfaces and execute F01–F16 fake-contract faults. No gateway/service, strategy, analytics, authenticated UI, agent deployment, production DB or live/demo order integration built.
- **Implemented:** strict immutable Decimal/UTC records in `src/astrabot/contracts.py`: `SetupSnapshotV15`, `TradeAuthorizationV15`, bounded/fixed geometry, `AccountReservationV15`, `OrderIntentV15`, `ExitLatchV15`, `PositionLifecycleV15`, `TerminalProof`, `EconomicsV15`, `CompletePolicyExpectancyV15`. Initial actual-filled denominator remains distinct from approved ceiling; real adverse-fill breaches remain recordable and cannot hide exposure. B1 remains RESEARCH_ONLY.
- **Fixtures/tests:** `tests/c01_fake.py` has separate durable fake venue/ledger stores, deterministic clock, short account CAS/claim transactions and fake-only management. Every venue I/O checks no ledger write lock remains held. `tests/test_c01_acceptance.py` maps F01–F16 to related AT obligations, with 68 parameterized cases covering authorization, reservation contention, unknown IOC, partial protection/deadlines, two TP races, safe replacement, latch/late fills, restart/holding timer, direction/economics and unresolved instructions. Technical real single-writer/account-mode controls remain unverified.
- **Candidate pins:** official USD-M SDK 18.1.0/common 4.7.0 at `6b3ba001274406372d376e218c8b9d04bd9c1720`; Freqtrade 2026.9 at `1f394eaebc2f46a83d26971388628707802f8602` (CCXT 4.5.84 source); NautilusTrader 1.231.0 peeled commit `27a8e54e7ac3c57d6cbf8891f0283dfbaee97317`. Exact source/artifact/doc hashes in `tests/vendor/candidates.lock.json`; exercised SDK dependencies in `tests/vendor/sdk-requirements.lock`. Normal contract dependencies in `requirements-test.txt` align SDK's Pydantic >=2.14.1 minimum without importing SDK into the fake suite.
- **Observed verification (PASS):** `env -i PATH=/usr/bin:/bin PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 work/c01-venv/bin/python -m pytest -q` → **68 passed in 0.33s**, 0 failed/skipped; `work/c01-venv/bin/python -m pip check` → `No broken requirements found.` Python 3.12.14/Pydantic 2.14.1/pytest 8.4.2. Autouse socket denial plus scrubbed process environment; no credentials read. Final staged whitespace/reference checks recorded with delivery.
- **Actual vendor execution (PASS, synthetic):** `env -i PATH=/usr/bin:/bin work/candidates/sdk/venv/bin/python tests/vendor/probe_sdk.py work/candidates/sdk/binance-connector-python` → 8 checks; same interpreter `tests/vendor/run_sdk_tests.py work/candidates/sdk/binance-connector-python` → 20 selected upstream tests passed, 326 deselected, 12 collection warnings. Complete actual SDK checkout, HTTP/sockets blocked and signing mocked. `env -i PATH=/usr/bin:/bin work/c01-venv/bin/python tests/vendor/probe_freqtrade.py work/candidates/freqtrade` → 9 actual AST-extracted vendor-hook cases passed; RPC validation collaborator explicitly stubbed. Full Freqtrade/Nautilus runtimes and full vendor suites **NOT RUN**; Nautilus source/tests were read only. Commands/setup/source symbols and outputs are in ADR and `tests/vendor/observed-results.json`.
- **Important findings:** (1) Freqtrade's inspected release permits approval-callback exceptions, bypasses the callback for adjustment/replacement, sends before Trade commit and cancels old stop before replacement; its Binance adapter also explicitly disables demo configuration. (2) SDK current ordinary/algo IDs and transports work in mocks, but cross-field trading validation is missing and generic 503 errors lose message detail. (3) Nautilus has modern algo/child/event/recovery reuse and demo hosts, but Binance rejects native linked brackets; application approval/reservations/leg coordination remain. These facts favor retaining the existing SDK topology provisionally, not claiming a qualified live engine.
- **Bounded correction evidence:** review found and fixed original-trigger deadline reset, missing final submission veto/expiry checks, nonrepresentable observed risk, stale recovery/protection barriers and oversized fake TP fills. Independent Sol audit reproduced absent acknowledged-entry premature terminal release and actual setup-expiry bypass; both regressions now pass (focused audit: 9 passed/59 deselected). An initial two-case Decimal zero-format assertion failure after quantity correction was fixed by numerical equality, not relaxed economic assertions. Final full suite passed; no known unresolved P0/P1 remains in this scoped fake/contract gate.
- **ADR / authority:** [ADR-EXEC-001](adr/ADR-EXEC-001.md) **PROPOSED**, recommends the official SDK + bounded gateway as the single future writer. No materially different topology/risk/authorization accepted. Owner production/live approval is absent and unnecessary for these authorized C01 artifacts; remains mandatory for later live promotion or owner-controlled changes. No account was queried or changed; **zero demo/live exchange requests**.
- **Remaining UNVERIFIED / P2 deferrals:** real owner/MFA trust, PostgreSQL transaction durability and operational fencing, non-atomic REST/WS ordering, account mode/filters/dust, protected API budgets, actual IOC uncertainty, whole-stop/two-TP coexistence, overlapping replacement and actual latency. Fake snapshots/reduceOnly assumptions do not qualify Binance. Late fills discovered after initial denominator finalization preserve quantity/denominator and halt for reconciliation; production accounting correction remains future work. These belong to existing C07/C08 gates, not a new feature backlog.
- **Documentation:** full 16-row source-evidenced comparison/reproduction in ADR; `03-COMPONENT-REUSE-REGISTER.md` updated with provisional/rejected/deferred pins; this journal appended. `02`/`05` and preserved `docs/reference/AGENTIC_SPEC_v1.5.md` unchanged. Expert strategy deep dives remain C03/C05.
- **Reviewer verdict / progress:** **PENDING independent project-lead PR review**; scoped subagent audit does not substitute for that review. Verified demo-qualification ledger remains **0% / 100% remaining** until the lead awards reviewed P0 gate credit; artifacts ready for review do not establish demo or profitability evidence. Existing top phase/NEXT_GATE unchanged.
- **Suggested NEXT_GATE:** independently inspect actual C01 PR diff/tests and accept/reject ADR-EXEC-001/contracts. Only after that review passes, start **C02 read-only market data, dynamic eligibility and causal feature integration**. No owner-controlled change is proposed for acceptance in this implementation.
