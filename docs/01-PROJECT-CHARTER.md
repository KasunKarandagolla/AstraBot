# 01 — Product Charter, Authority and Change Control

**Status:** approved design intent; engineering and profitability **not** verified. Last baseline: 2026-10-24 v1.5.

## Mission and commercial intent

Build **AstraBot**, a Binance USDⓈ-M USDT-settled perpetual-futures system which scans eligible futures pairs including altcoins, identifies opportunities, selects a qualified regime-specific trading policy, obtains owner authorization, executes and actively manages positions. Use an OpenBot-hosted *free-model* LLM as mandatory **new-trade workflow coordinator**, not as a numeric or discretionary trading oracle. Minimize custom code and Codex sessions through qualified prebuilt components. The aim is economically useful, reproducible decisions and operational reliability—not flashy agent demos, backtest overfitting or guaranteed profits.

## Hard product constraints (only owner may change)

| Dimension | Binding requirement |
|---|---|
| Venue | Binance USDⓈ-M **USDT-settled perpetuals**, one-way mode, isolated margin, after account/adapter qualification |
| Markets | Dynamic eligible altcoins, optionally BTC/ETH; BTC/ETH may provide market context, not BTC-only trading |
| Holding | Intended maximum **12 hours from first exchange-confirmed entry fill**; initiate flatten at 11h55m; enforce reconciliation during outages |
| Analysis | All **A01–A10** analytics remain in full-product scope; they are tools, **not** ten simultaneously live strategies |
| V1 executable setups | T1 VWAP continuation, R1 range-edge sweep/reclaim, B1 breakout/retest — all **RESEARCH_ONLY** until qualified; original B1 TP ladder has known economics issue |
| Agent runtime | **OpenBot only**; internal free models, no separate OpenCode integration; three operational roles: Coordinator, News/Events, Journal |
| Human authority | One explicit, authenticated owner approval for **every new entry or exposure increase**. An approved, one-use bounded conditional plan may execute its exact trigger without a second approval; no blanket authorizations |
| Model limits | LLM coordinates typed calls and explanations; cannot invent indicators, select unqualified strategies, set numeric risk, alter stops or place signed orders |
| Open-position management | Independent deterministic service; may tighten risk, partially exit, take TP, close thesis-invalidated/time-expired positions; cannot average down, scale in, widen stop or reset holding clock |
| Live order authority | Exactly **one** authenticated writer: SDK/gateway is **candidate default** pending recorded Freqtrade/Nautilus bake-off |
| Data validity | Point-in-time/casual availability, coverage/readiness and source semantics required; no fake order-flow from candle proxies |
| Deployment | Historical → shadow/paper → Binance-supported demo/test → owner-authorized small live pilot. No live activation by a casual flag |
| Reuse rule | Adopt → Configure → Wrap → Small Patch → Build only when necessary |

**Provisional v1 hard ceilings, from v1.5**: per-trade modeled stop risk ≤0.25% reconciled equity; aggregate pending+open modeled stop risk ≤0.50%; entry halt after 1% daily UTC equity-baseline decline; ≤2 concurrent positions; one independent position per symbol; isolated margin; effective leverage ≤2×. Model risk is not a worst-case loss guarantee. These ceilings may be tightened within a research configuration; loosening or changing their meaning requires owner sign-off.

## Expert-trader quality requirement (owner clarification, 2026-10-24)

AstraBot must aim for **experienced retail-trader-level market interpretation**, not superficial use of A01–A10 as independent indicator checkboxes. Strategy selection and real trade management must account for regimes, contextual anchors, order-flow/price-response interaction, liquidity conditions, confluence/dependency, failed setups and changing thesis. An elegant basic implementation is insufficient if it cannot interpret meaningful historical cases. This standard **does not require** a huge custom AI, copying a guru's discretionary intuition, or activating all families at once. Investigate qualified prebuilt expert-grade logic before writing bespoke rules; verify it with rigorous case review and causal economic testing.

Practical project leadership: minimize total Codex resource consumption while maintaining this quality bar, delegate genuinely independent subagent tasks when available, keep stateful engineering memory and runtime market-data storage bounded, and estimate demo-qualification progress after every PR review. Avoid repetitive generic warnings; explain material constraints once, then solve the task. Ask the owner if a genuinely decision-changing fact is unknown; proceed on reversible small implementation details under recorded assumptions.

## What is NOT proven

No currently chosen software candidate has been installed, pinned and exercised end-to-end for this system. No backtest has proven profit. No live order flows or Binance testnet capabilities have passed acceptance tests. Labels in documentation are **hypotheses**, not certifications.

## Project-lead decision authority

The ChatGPT project lead may autonomously decide day-to-day implementation priorities, minor library adapters, repository organization, tests, issue triage and phase-specific scope **inside the charter**. The lead should challenge weak ideas constructively as a disciplined crypto-futures systems designer; it must never claim a verified profitable track record or substitute unvalidated trading intuition for evidence.

**Notify owner and await decision** before: adding/removing a major subagent or runtime; changing Binance venue/margin mode; reducing A01–A10 final scope; changing human approval; allowing unapproved exposure; loosening leverage/risk or adding scale-ins; live deployment; changing core strategy approval/qualification or material cost definitions; authorizing a rewrite; choosing a materially new operational topology; merging a major breaking design change.

If a potential improvement is substantial, write a **two-option mini-ADR**: observed problem, proposed change, simpler alternative, impacts to evidence/tests/deadlines, and recommendation. Mark `PROPOSED` pending owner approval. Do **not** silently enact a project-shaping decision.

## Protect project momentum: severity and scope rubric

| Level | Meaning | Next action |
|---|---|---|
| P0 / blocker | Potential unauthorized exposure, loss of stop/protection, wrong risk authorization, look-ahead in research conclusions, unreconciled position, credential leak | Pause promotion/affected work; fix within current phase or raise immediate owner decision |
| P1 / gate blocker | Prevents *current* milestone proving its acceptance gate, materially invalidates research/economics/data, or creates unbounded maintenance | Fix this phase with tight scope; document trade-off |
| P2 / backlog | Real problem but not blocking current next gate, isolated edge case with safe fallback, or later optimization | Record concisely in journal/backlog, **advance milestone** |
| P3 / polish | Naming, UI aesthetics, redundant framework abstraction, speculative enhancements | Defer or omit |

**Stop rule:** two rounds of minor fixes on the same issue trigger a lead decision: accept known limitation, scope a concise correction, or escalate only if P0/P1. Never convert one minor observation into a chain of unlimited Codex sessions. Prefer explicit safe fallback over speculative generality.

## Model/session spending principles

Use **GPT-6.1 Sol** (only if available in Codex cloud) for genuinely difficult coupled decisions: financial-rule semantics, exchange order races/authorization, trading research interpretation, architectural bake-off, fault review. Use **GPT-6 Luna** for large-volume mechanical integration: scaffolds, SDK adapters, fixtures, docs, CI, ingestion, deterministic module wiring and report generation. These are planned labels supplied by the owner; verify actual Codex access/menu at task launch. Do not combine deep design research and bulk implementation in one task merely to save an invocation; instead make the deep decisions first, then batch bounded related implementation. Reuse existing outcomes rather than rethinking settled issues.

## Completion definition

Project is **feature complete** only when contract-driven coin discovery, A01–A10 plugin capability/readiness, at least one independently qualified executable policy, scoped OpenBot coordination, secure owner approval, single-owner demo execution, continuous protection/reconciliation, active management and truthful monitoring/reporting pass the corresponding tests. **Live readiness** additionally requires owner authorization and real operational checks. It is acceptable that some analytical families remain dormant if not economically qualified; none are silently removed.