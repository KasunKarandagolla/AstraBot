# AstraBot — Living Project Sources

**Project:** reuse-first, OpenBot-coordinated, multi-strategy Binance USDⓈ-M crypto-perpetual research and trading system, requiring explicit human approval before every new exposure.  
**Baseline:** architecture v1.5 (24 Oct 2026). **Current status: DESIGN / PRE-IMPLEMENTATION.** No exchange integration, backtest, economic edge or live safety qualification has yet been established.  
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

## Current focus and next action

**Phase 0: pre-code contract and economic feasibility.** Run the scoped engine-owner feasibility spike and the data/cost audit **before** constructing a full autonomous platform. The first Codex task is `C01` in `docs/06-CODEX-DELIVERY-PLAN.md`; do not jump to execution or live infrastructure. After every Codex task: push commits, open a PR, update the engineering journal and relevant live docs, and submit the PR for independent ChatGPT Project review before merge.

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