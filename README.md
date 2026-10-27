# AstraBot — Living Project Sources

**Project:** reuse-first, OpenBot-coordinated, multi-strategy Binance USDⓈ-M crypto-perpetual research and trading system, requiring explicit human approval before every new exposure.  
**Baseline:** architecture v1.5 (24 Oct 2026); merged code through independently reviewed PR #26 at `153d4d31c473e1f55c4ca62eaf5ad877629ea415`. **Current status: P0–P2 credited; P3 economic evidence on hold. PR #23 C06-E/F is merged, and the owner reports Windows/OpenBot C06-F acceptance PASS; that scope is closed.** Authentic seven-symbol OHLCV price diagnostics and one-day source samples exist; strict policy replay remains `BLOCKED_BY_DATA`, and economic qualification remains `INSUFFICIENT_EVIDENCE`. P3 empirical and P4–P6 operational gates are not complete. No edge, demo safety or live readiness has been established.
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

**Integrated offline research MVP RC1 — ready for independent review.** The existing C05 command now presents authentic source-backed NO_TRADE decisions through the existing six OpenBot-compatible tools and produces a separate protected fake lifecycle, durable fake approval/restart evidence and owner summaries derived from machine events. See [launch, evidence and limits](research/acceptance/INTEGRATED_RESEARCH_MVP_RC1.md) and the [software readiness matrix](research/acceptance/RELEASE_READINESS_RC1.json).

```sh
python scripts/c05_integrated_research.py --mode authentic --output-dir work/rc1
python scripts/c05_integrated_research.py --mode synthetic --output-dir work/rc1
```

The default authentic run verifies the retained 124-row C02 sample: 48 symbol-windows, zero eligible windows/candidates, NO_TRADE / BLOCKED_BY_DATA. Synthetic mode separately demonstrates partial entry/protection/TP/restart/11h55/12h/emergency closure and rejected, expired, stale-trigger and protection-failure cases. No qualified historical trade or new owner-host OpenBot acceptance is claimed. Existing complete C04 and owner G/H input interfaces are retained; original Windows feeds are not assumed accessible.

**Programme truth:** P3 `INSUFFICIENT_EVIDENCE`; T1/R1/B1 `RESEARCH_ONLY`; formal credit **45% / 55% unqualified**. PR #28 was independently accepted (review `5661492640`) and merged by the lead at `2f2ea0b`; repaired head `510165f3ad2f35142da927b7cf4ee601dc24ba10` ([green CI](https://github.com/KasunKarandagolla/AstraBot/actions/runs/40436282335)). Its `T1_INDETERMINATE` finding preserves 24 original stop touches and zero original second targets before stop. External C05-M source/host assessment: `HOLD_REVISE`, zero of nine source requirements fully accepted, 210-day study **DEFERRED** (see issue #18; attachments are not in Git). RC1 began independently at `0d5b45c`, then reconciled actual merged main `2f2ea0b`. Its real seven-symbol run verifies 266,616 bars and produces 1,008 NO_TRADE decisions across 168 windows, zero candidates; all 28 October archives remain unopened. No unmerged changes were copied. The current owner assignment authorizes this offline integration only; completed C06-F host acceptance is not repeated.

**NEXT_GATE:** independent review of RC1, then owner HOLD or a separately preregistered economic-hypothesis revision. C07, Demo/live, credentials, collector and paid procurement remain unauthorized. Software integration adds no formal phase credit.

The following sample notes preserve earlier evidence and its limitations; their original next actions are historical context, not separate current work orders. Earlier Binance HTTP 451 and Tardis CONNECT 403 observations do not establish global data absence.

**C05-D original data evidence (2026-10-25):** Owner-uploaded Tardis-format SOLUSDT 2024-10-01 quote gzip passed integrity/schema audit: 1,064,711 records, all 1,440 one-minute buckets present, 1,381 consecutive 60-minute median-spread windows within the research threshold. See [original-byte preflight](research/c05/ORIGINAL_BYTES_PREFLIGHT.md). Status **`SAMPLE_ONLY / QUOTES_SCHEMA_COMPATIBLE`**, not a continuous dataset or economically qualified policy. Missing deeper depth, OI, funding, venue metadata, verified events and realistic fills. **Original next action:** acquire separate, date-matched original `derivative_ticker` and `book_snapshot_25` samples with documented rights, or explicitly approve a longer-term data route; no new Codex network probes, C07 or trading authorization.

**C05-D companion derivative-ticker sample (2026-10-25):** Owner supplied genuine gzip/CSV-format SOLUSDT derivative ticks for 2024-10-01: **119,927** rows, OI populated in **119,913**, mark/index prices in all records, published next-funding rate/time, and all **1,440** collector-time minute buckets overlapping with the quote file. [Derivative-ticker original-byte preflight](research/c05/DERIVATIVE_TICKER_PREFLIGHT.md). Status **`SAMPLE_ONLY / DERIVATIVE_TICKER_SCHEMA_COMPATIBLE`**. Raw OI **units and USDT-notional conversion not validated**, funding is not a verified settlement, deeper depth/events/metadata/fills remain missing. **Original next action:** date-matched `book_snapshot_25` original bytes plus OI units and a rights-checked representative data route.

**C05-E top-25 reconstructed book sample (owner report, 2026-10-25):** Local OpenBot reported validating 94,944,824 compressed bytes, 1,522,898 `binance-futures/SOLUSDT` order-book snapshots (104 columns), UTC 2024-10-01 and within-0.20%-of-mid raw depth. **Independent source bytes and the detailed local Markdown file were not attached for reinspection**; contract quantity/USDT-notional units remain unverified and Tardis reconstructs/remove crossed levels. [Sample preflight](research/c05/BOOK_SNAPSHOT_25_PREFLIGHT.md). **Original next action:** validate historical SOLUSDT quantity units/filters, then a bounded causal quotes+derivatives+L2 alignment diagnostic, not economic GO. P3 `INSUFFICIENT_EVIDENCE` and overall 45% phase credit unchanged.

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
