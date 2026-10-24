# 06 — Completion-First Roadmap and Codex Cloud Session Plan

**Objective:** ship the shortest credible path from empty GitHub repo to a research-qualified, demo-safe agentic trading system. **Minimize Codex sessions, not correctness.** The schedule below is a **planning sequence**, not a requirement to start every session. Each session produces one logical PR/hand-off. Stop if a phase gate fails; do not build the full platform based on unqualified strategies.

## Operating rules for ALL Codex sessions

1. Start from the latest merged `main` and read `README.md`, `01`, `06`, `07` plus the specifically relevant contract (`02`–`05`). Read only the needed sections of full v1.5; do not re-derive settled architecture.
2. Session has **one complexity class**, assigned by cognitive difficulty, not alternating model labels. **Sol (GPT-6.1 Sol if available)** for unresolved hard architecture, market-model semantics, trading-policy and exchange-safety decisions; **Luna (GPT-6 Luna if available)** for bulk integration, existing-rule implementation, fixtures, CI, adapters and reports. Prefer the lower-cost model when an implementation contract is settled. An independent ChatGPT Project lead review may replace a separate Codex audit session; escalate to Sol only for a material unresolved issue. Confirm model access and actual quotas.
3. **One primary deliverable and one phase gate**, with bounded related changes. No unrelated refactor, polish, dependency sprawl or large redesign. Prefer small adapters to new frameworks.
4. Test the targeted behavior, pin adopted package versions, summarize evidence and limitations. CI screenshots are not proof of quantitative edge.
5. **Commit + push branch + create PR**; append a concise `07-ENGINEERING-JOURNAL.md` entry in the *same PR*, update impacted live docs and phase checklist. Link hashes/test outputs, exact remaining blocker and next action.
6. Do not merge automatically. Project lead independently checks actual diff, runs/checks available tests, gives `PASS`, `PASS WITH DEFERRED NONBLOCKERS` or `BLOCKED`. Critical repairs may use one focused follow-up; nonblocking findings go to journal backlog, not a new session.
7. A session that hits a genuine P0/P1 blocker stops at a **safe partial output**, records precise reproduction and proposed cheapest fix, and does not quietly deviate to another phase.
8. Never use production Binance credentials; no live capital. Keep test/dry-run flags and gateways disabled until separate owner authorization.

## Session portfolio — planned maximum core path (conditional)

| Task | Phase | Use | Complexity | Bounded output / why grouped | Gate |
|---|---|---|---|---|---|
| **C01** | P0 | **Sol** | Complex only | Engine-owner bake-off + explicit binding setup/approval/economics/lifecycle contracts + ADR, golden fakes. No bulk scaffolding. | Choose one documented writer candidate and frozen first research rules |
| **C02** | P1 | **Luna** | Bulk integration only | Repo/package/CI minimal skeleton, official Binance **read-only** market data + symbol universe + readiness/archives and prebuilt feature wrapper examples. No strategy creativity. | Reproducible causal market panel; scanner and A01/A02/A03 adapter smoke checks |
| **C03** | P2 | **Sol** | Complex quant only | Implement/review **pure T1/R1/B1 setup chronologies**, target/cost formulas, research qualification criteria and hand-checked fixtures; preserve B1 research-only. No UI/exchange orders. | Prefix-causal events, fixed anchors, exact worst-fill scenario economics |
| **C04** | P3 | **Luna** | Bulk research only | Implement replay adapters/reports from C03 rules; dataset manifest, fees/funding, approval delay, portfolio funnel, bootstrap tests; generate reproducible R0–R2 results. | Full frozen policy replay runs with declared uncertainty and no future registry |
| **C05** | P3 decision | **Lead review by default; optional Sol** | Independent complex review, no bulk coding | Inspect actual reproducible research evidence, practitioner-case parity, cost/fill assumptions and select STOP/REVISE/GO variants. Invoke Codex Sol only for a real unresolved statistical or strategy-design problem. | Written economic go/no-go and qualified policy version(s) or explicit research hold |
| **C06** | P4 | **Luna** | Bulk orchestration only | OpenBot (three roles), read-only Binance Skill/typed tool facade, news source adapter, journal summaries, proposal/approval dashboard and **fake-owner** integration. No signed order writes. | New-trade workflow calls tools; unauthenticated prompts cannot authorize trades |
| **C07** | P5 | **Sol** | Complex lifecycle only | Implement **selected single live owner** on demo/fake venue: atomic one-use approval + reservations, durable order intents, initial protection, partial TP, stop replacement, APSS state/thesis rules, time cap and recovery. Scope is one coherent high-risk order lifecycle. No UI redesign. | Critical fault matrix, no unauthorized exposure/stop gap, positions supervised until flat |
| **C08** | P6 | **Luna** | Bulk end-to-end only | Wire bounded components and run demo/shadow integration, report funnel/costs, docs, health dashboards, journal/alert paths, tiered tests and handover scripts. No new strategies. | Repeatable demo session + 12h/time warp + restart/fail simulations |
| **C09** | P6 review | **Lead review by default; optional Sol** | Independent critical audit; no bulk coding | Independently inspect **actual merged code and reports**, P0/P1 failures and economic conformance. Invoke a focused Sol Codex task only when evidence exposes an unresolved hard defect. | Explicit `RESEARCH_ONLY`, `DEMO_QUALIFIED` or owner-facing live-pilot recommendation |

These are **scoped planning packets**, not promises that nine calls always suffice. If prebuilt Freqtrade/NautilusTrader drastically reduces C07, merge only **compatible tasks of the same complexity and same gate**. If C04/C05 shows no edge, halt execution development and iterate *only* the weakest research hypothesis. Separate production pilot planning follows a **new owner decision**, not an automatic tenth task.

## Quota-conscious delegation and task routing

The default critical path now has **seven planned implementation Codex sessions** (`C01–C04`, `C06–C08`), including **three Sol** (`C01/C03/C07`) and **four Luna** (`C02/C04/C06/C08`); `C05/C09` are independent ChatGPT Project lead review gates by default, with *optional* Sol escalation. This is a **conditional estimate**, not a hard cap or automatic session count. Avoid paying for a fresh Sol task simply to repeat a review already possible from a PR, dataset and logged evidence.

Before opening any Codex task, lead records **why this model**, **why this session is needed**, expected token/tool cost relative to remaining quota if known, and whether the task can be resolved by inspecting existing artifacts. Bundle *related work with the same complexity class and phase gate*, but never bury an unresolved trading/authorization decision in a bulk integration prompt. Where supported, use parallel subagents for genuinely separable work (e.g. upstream verification, dataset checks, fixture/test audit), with one accountable integration/review owner, bounded context/tool permissions and no concurrent exchange writers. Do not force subagents into trivial tasks; parallelism must reduce wall time or reasoning burden rather than multiply redundant outputs.

Market expertise is a **phase deliverable**, not optional polish: the C03 research/implementation handoff and C05 review must include case studies and failures showing the policy's market understanding, against historical practitioner examples where applicable, plus causal replay and cost evidence. Do not treat screenshots or reputation as statistical proof. The next phase begins only after its actual gate clears, not after endless optional issue fixing.

## Delivery phases and artifacts

| Phase | Outcome, not work-for-work's-sake | Promotion constraint |
|---|---|---|
| P0 Contracts and owner selection | `ADR-EXEC-001`; fake venue cases; cost/authorization/fill contracts | unambiguous versioned interfaces and one engine candidate |
| P1 Read-only discovery | causal Binance dataset/manifest; dynamic eligible altcoins; news/readiness; prebuilt features | no signed orders and no fake CVD |
| P2 Entries and geometry | 3 setup policies & realistic cost/target profiles, B1 defect preserved | prefix tests and formula assertions pass |
| P3 Research evidence | matched controls, full-policy replay, cluster-aware uncertainty | strategy/policy GO or STOP recorded before platform build |
| P4 Coordination/approval | OpenBot free-model tool calls, scoped skills, human approval, machine journal | model cannot reach exchange write credentials |
| P5 Protected demo execution | single writer, one-use plan, partial exits, 12h, recovery | all activated lifecycle safety cases pass |
| P6 Integrated demonstration/review | trace from scan to closed trade and owner-facing report, lessons recorded | independent final review and owner-controlled promotion |

## Ready-to-run C01 Codex cloud brief (copy/paste as first task)

> Repository: `KasunKarandagolla/AstraBot`. Read `README.md`, `docs/01-PROJECT-CHARTER.md`, `docs/03-COMPONENT-REUSE-REGISTER.md`, `docs/05-EXECUTION-SUPERVISION.md`, `docs/06-CODEX-DELIVERY-PLAN.md`, `docs/07-ENGINEERING-JOURNAL.md` and relevant sections of `docs/reference/AGENTIC_SPEC_v1.5.md`. This is **C01 / Sol / complex feasibility only**. Do not scaffold the whole product. Evaluate pinned official Binance USD-M SDK+small gateway, Freqtrade sole-owner, and NautilusTrader sole-owner against exact approval failure-closed behavior, IOC unknown result, stop/TP coexistence, partial fill protection, safe stop replacement, restart reconciliation and 12h timer. Use fake-venue fixtures and no real credentials. Provide a concise measured matrix, choose a **provisional** single-writer approach via `ADR-EXEC-001` and state remaining unknowns. Define minimal typed lifecycle, approval and economics contracts to unblock subsequent bulk work. Record the decision, versions, tests, blockers and next task in `docs/07-ENGINEERING-JOURNAL.md`. Update only impacted docs. Commit/push to one feature branch and open a PR. **Avoid unrelated changes, auto-merge and live deployment.**

## Review contract after each PR

After every PR review publish a **rough percentage complete / remaining toward demo-qualified scope**, using phase weights and rules in `07`; explicitly say what is measured and that the estimate is not time-to-live or verified profitability. Also state model/session quota spent when known (otherwise `unavailable`), and one next priority.


The project lead must examine actual changed paths, API/contract changes, test evidence and Codex journal entry; compare with current phase gate and preceding decisions. Report **what is verified in code** vs claimed. Classify all findings P0/P1/P2/P3, insist fixes only for current blockers, and give the next task ID. If a new idea genuinely improves outcome with less code, propose a concise owner-review ADR. Use PR/commit hashes rather than relying on summaries alone. No next task begins on an unmerged dependent state unless explicitly branched and documented.

## Preventing tunnel vision

Keep a visible `NEXT_GATE` at the top of every session handoff. An observation is not automatically a task. Ask: *Does this materially prevent the next milestone or violate a binding invariant?* If not, log under deferred issues with impact and proceed. Count major milestones completed, not number of issues fixed. Change this roadmap deliberately when evidence supports it, rather than treating it as permanent doctrine.