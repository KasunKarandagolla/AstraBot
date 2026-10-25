# AstraBot — Living Project Sources

**Project:** reuse-first, OpenBot-coordinated, multi-strategy Binance USDⓈ-M crypto-perpetual research and trading system, requiring explicit human approval before every new exposure.  
**Baseline:** architecture v1.5 (24 Oct 2026). **Current status: C01/C02 merged; C03 causal research policies prepared for independent review.** The public adapter has not been verified against a live Binance endpoint. No trading operations, strategy backtest, economic edge or live safety qualification has been established.
**Repository:** https://github.com/KasunKarandagolla/AstraBot

## Read in this order

| Source | Purpose | Owner of updates |
|---|---|---|
| `README.md` | One-page entry point and current phase | Project lead |
| `docs/01-PROJECT-CHARTER.md` | Scope, guardrails, authority and change control | Project lead + owner |
| `docs/02-SYSTEM-ARCHITECTURE.md` | Boundaries, runtime layout, interfaces and event semantics | Architecture sessions |
| `docs/03-COMPONENT-REUSE-REGISTER.md` | Prebuilt candidate assessment, replacement gates and decisions | Integration sessions |
| `docs/04-TRADING-DECISION-RESEARCH.md` | Data, all ten analytical families, testable strategies, economics, validation | Quant/research sessions |
| `docs/05-EXECUTION-SUPERVISION.md` | Approval, risk, single-writer OMS, active management and recovery | Execution sessions |
| `docs/06-CODEX-DELIVERY-PLAN.md` | Phase gates, scoped Codex tasks, routing between models, definition of done | Project lead |
| `docs/07-ENGINEERING-JOURNAL.md` | Append-only milestone and decision log, blockers, PR/review handoffs | Every implementation session |
| `docs/08-CHATGPT-PROJECT-INSTRUCTIONS.md` | Paste into ChatGPT Project instructions (under 8,000 characters) | Project lead |
| `docs/reference/AGENTIC_SPEC_v1.5.md` | Preserved full consulted architecture and detailed original contracts | Version-controlled historical baseline |

**Exactly ten Markdown files** are included. Upload these same ten files as ChatGPT Project sources; the repository is the **source of truth**, and after approved changes the Project files should be refreshed from the repository. The ChatGPT Project instructions field uses file `08` (paste its contents), which is also stored in Git for traceability.

## Quality bar and completion focus (2026-10-24 clarification)

Assembly is **not** a basic-indicator bot. Choose the most suitable **working, mature, context-aware prebuilt logic and trading projects** first; verify their actual behavior and upgrade/switch candidates when stronger evidence appears. Each promoted strategy requires a focused expert-level deep dive: market context, chronology, liquidity/flow interpretation, failed setups, target/stop and thesis management, practitioner cases plus historical causal replay. Annotated professional/trader charts are useful *qualitative case studies*, not causal data or proof of positive expectancy; validate against contemporaneous data and negative examples. See `03` and `04`.

Codex model selection is **complexity-triggered, not a Sol/Luna alternating pattern**; independent lead reviews can replace some paid Sol tasks. Use subagents for separable research/coding/review under one accountable task without multiplying sessions or tool costs blindly. Report estimated **demo-qualification completion % and remaining %** after each reviewed PR using the weighted gate ledger in `07`; identify what the estimate does/doesn't measure. Persist concise verified findings, storage decisions, code and test references across sessions; distinguish development memory from runtime market-data retention and durable trading events. Ask the owner when missing facts affect material or irreversible decisions. No generic repeated disclaimers; no dilution of real exchange/order-safety controls.

## MVP-first delivery rule (2026-10-25)

**Build an evidence-led MVP before completing the platform.** The MVP is a narrow, integrated *vertical slice*, not ten shallow indicators or a UI demo.

- **Research MVP (MVP-R, C02–C04; economic review C05):** real read-only Binance USD-M data → dynamic eligible altcoin shortlist → prebuilt, causal market-analysis providers → one precisely defined candidate setup with real structural levels and costs → TRADE_CANDIDATE or NO_TRADE → saved reproducible replay/report. Start this vertical slice as early as C02; no live orders.
- **Agentic paper MVP (MVP-A, C06):** OpenBot coordinates the deterministic workflow; explicit owner approval of a bounded one-use proposal; **fake/paper** order execution, position management and decision journal on a reproducible scenario. A research-only policy can only run in simulation, never gain live authority through a demo. No full Binance order-management platform is needed for this milestone.
- **Demo-qualified v1 (C07–C09):** independently proven single order owner, Binance demo exchange integration, protective order reconciliation, partial exits, restart recovery and 12-hour timer. This comes later and is gated separately.

**MVP acceptance:** reproduce a real historical candidate and a justified no-trade case, report input provenance and economic assumptions, show a working end-to-end paper trace including approval/hold-or-exit/journal, and run relevant tests. If no policy survives economic review, **report research MVP achieved but policy unqualified**; do not fake a profitable trade or advance to funded execution. Preserve all A01–A10 in final scope; activate only validated dependencies in the MVP. No extra Codex session is automatic: deliver these slices inside C02–C06 and existing gates.

## Current focus and next action

**C03 / P2: causal setups and frozen geometry, pending independent review.** C02 PR #2 and the reviewed head are verified merged on the resolved latest `main`. The C03 branch adds pure context/strict-swing providers, T1/R1/B1 long/short chronologies and conservative research decisions. Run `python scripts/c03_research.py --check --summary` or see [C03 evidence](research/c03/README.md). The actual incomplete C02 archive also produces explicit NO_TRADE. Independent review of the actual diff/evidence remains the next action; no empirical strategy or live qualification is claimed.

## Source authority and drift prevention

1. Approved owner decisions and merged ADRs in `docs/07-ENGINEERING-JOURNAL.md` override older provisional proposals.
2. The current charter and focused contracts (`01`–`06`) govern **implementation details**, within the unchanged product vision.
3. `docs/reference/AGENTIC_SPEC_v1.5.md` preserves full original requirements and historic rationale. Consult it for omitted detail. If newer docs disagree on product shape or hard risk constraints, **pause and request owner approval**, not silent reinterpretation.
4. Upstream vendor documentation and executable tests decide external API behavior; treat all unverified capabilities as candidates.
5. A journal entry describes what happened but does not supersede a contract or approve live deployment by itself.

## Development philosophy

**ADOPT → CONFIGURE → WRAP → SMALL PATCH → BUILD ONLY IF NECESSARY.** Reuse prebuilt libraries, SDKs and research engines. Do not rebuild market indicators, exchange transports or backtest infrastructure without a short recorded decision. Keep one authenticated live order owner. Keep LLM coordination mandatory for new-trade workflow, but protective operation independent of model availability. Keep all ten analysis families in final scope while qualifying only a small number of executable strategies at once.

## Delivery discipline

- Work toward the **next phase gate**, not an ever-growing issue queue. Record unrelated findings, classify their actual impact, and defer the nonblocking ones.
- Do not represent a planned feature as implemented or an implemented feature as tested.
- No live capital or production API secrets in development tasks. Testnet/demo and research only until a separately approved promotion.
- Avoid two live execution owners, independent custom indicators without cause, sprawling microservices, more LLM subagents than necessary, or redesign without evidence.
- Do not commit secrets, credentials, real user/account data, or unredacted trading logs. Set CI to protect against accidental commits of secrets.

## Repo workflow

`Codex cloud task → feature branch → commit/push → PR + journal entry → project-lead review → correction only for blocking issues → merge → update ChatGPT Project sources at milestone`.

A review is not complete until it states: **PASS**, **PASS WITH DEFERRED NONBLOCKERS**, or **BLOCKED**, and provides the next phase action.
