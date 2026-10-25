# AstraBot — Living Project Sources

**Project:** reuse-first, OpenBot-coordinated, multi-strategy Binance USDⓈ-M crypto-perpetual research and trading system, requiring explicit human approval before every new exposure.  
**Baseline:** architecture v1.5 (24 Oct 2026). **Current status: PRs through #16 merged; P0–P2 credited, P3 economic evidence on hold; real OpenBot/Codex read-only C06-D negative and positive multi-tool synthetic workflows owner-reported PASS.** Authentic seven-symbol OHLCV price diagnostics are available; strict policy replay remains `BLOCKED_BY_DATA`, and economic qualification remains `INSUFFICIENT_EVIDENCE`. P3 empirical and P4–P6 operational gates are not complete. No edge, demo safety or live readiness has been established.
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

**P3 evidence hold — original-byte quote sample now available.** Reviewed implementation and corrective PRs through #15 are merged; the authentic C04 price panel and offline observer do **not** qualify economic policy results. Binance public API returned HTTP 451 in the tested environment; Tardis docs GET was blocked by Codex CONNECT 403. Neither access error proves global data absence. C05 economic status is `INSUFFICIENT_EVIDENCE`, and original approval/risk controls remain unchanged.

**Phase credit remains 45% / 55% unqualified.** C06-B tested six typed tools plus synthetic fake approval/protection/exit. C06-C added real SDK-based MCP stdio protocol; a Windows 11 OpenBot agent using the Codex provider subsequently **reported actual attached `evaluate_symbol` tool invocation** returning `NO_TRADE`, `executable=false`, `readiness=UNAVAILABLE` (owner-provided runtime evidence, not independent journal/video replay). PR #15 merged the Windows test fixes: 221 GitHub CI tests passed. The real model-to-tool read-only path is evidenced; **actual agent-driven paper execution/approval, production authenticated human approval/MFA, durable journal and legitimate economic qualification are NOT verified**. P3/C05 remains `INSUFFICIENT_EVIDENCE`, all T1/R1/B1 `RESEARCH_ONLY`; C07/demo/live blocked. **NEXT_GATE:** C06-D existing-fixture multi-tool conformance was owner-reported PASS; stop extra C06 development and return to **P3 read-only data/economic evidence feasibility**. Obtain owner approval before launching any prospective collection, paying for feeds, choosing retention/storage/hosting, or changing operational topology. No new Codex coding task assigned.

**New C05-D original data evidence (2026-10-25):** Owner-uploaded Tardis-format SOLUSDT 2024-10-01 quote gzip passed integrity/schema audit: 1,064,711 records, all 1,440 one-minute buckets present, 1,381 consecutive 60-minute median-spread windows within the research threshold. See [original-byte preflight](research/c05/ORIGINAL_BYTES_PREFLIGHT.md). Status **`SAMPLE_ONLY / QUOTES_SCHEMA_COMPATIBLE`**, not a continuous dataset or economically qualified policy. Missing deeper depth, OI, funding, venue metadata, verified events and realistic fills. **NEXT_GATE:** acquire separate, date-matched original `derivative_ticker` and `book_snapshot_25` samples with documented rights, or explicitly approve a longer-term data route; no new Codex network probes, C07 or trading authorization.

**C05-D companion derivative-ticker sample (2026-10-25):** Owner supplied genuine gzip/CSV-format SOLUSDT derivative ticks for 2024-10-01: **119,927** rows, OI populated in **119,913**, mark/index prices in all records, published next-funding rate/time, and all **1,440** collector-time minute buckets overlapping with the quote file. [Derivative-ticker original-byte preflight](research/c05/DERIVATIVE_TICKER_PREFLIGHT.md). Status **`SAMPLE_ONLY / DERIVATIVE_TICKER_SCHEMA_COMPATIBLE`**. Raw OI **units and USDT-notional conversion not validated**, funding is not a verified settlement, deeper depth/events/metadata/fills remain missing. **NEXT_GATE:** date-matched `book_snapshot_25` original bytes plus OI units and a rights-checked representative data route.

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
