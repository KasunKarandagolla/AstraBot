# 02 — Architecture, Runtime Boundaries and Ground-Level Contracts

**Status:** targeted implementation blueprint. Follow binding v1.5 for expanded details; interfaces here are proposed shape and subject to integration qualification.

## Runtime model (minimal deployment)

```text
Binance public feeds / verified calendar  ──>  ingestion + normalized cache + readiness
                                                    |
       OpenBot Coordinator (LLM required for NEW plans; no trading keys)
        ├─ News/Events role ─────> structured sources + deterministic blackout policy
        ├─ decision tool call ───> universe -> regimes -> setup registry -> policy evaluation
        └─ Journal role <──────── append-only machine events (read only)
                                                    |
                                   decision/risk + qualified registry
                                                    |
                      bounded proposal/armed-plan -> owner HTTPS approval
                                                    |
                     SINGLE WRITER execution + protection service (24/7)
                                                    |
                                      Binance futures SDK and user streams
                                                    |
                               event ledger + position supervisor + watchdog
```

**One deployable Python application with logical modules** plus an isolated 24/7 execution/supervision service is preferable to premature microservices. PostgreSQL stores approvals, durable intents, reservations, positions, trade events, setups, readiness and audit records; files/object storage holds immutable market captures. Use optional queue/broker only when load measurements justify it. Strict separate credentials/network permissions between agent/read-only plane and exchange writer.

## Existing technology interfaces

- **OpenBot**: main agent coordinator plus two small role subagents: News/Events and Journal. The LLM issues only six or fewer domain-level typed calls; no arbitrary shell access to trading credentials. Agent cannot perform time-critical protection.
- **Binance Skills Hub/CLI**: isolated, strictly read-only query/reference surface. Do not expose authenticated trading commands from the agent environment. Probe actual OpenBot compatibility.
- **Binance modular USD-M Python SDK**: default *transport candidate*, not proven OMS. Freqtrade or NautilusTrader may replace it **as sole live writer** if bake-off establishes materially better lifetime integration.
- **Existing analytics**: wrap qualified prebuilt packages behind typed feature-provider contracts; preserve exact upstream version/semantics, data fidelity and available-at time.
- **Backtesting**: start one reusable engine, then add finer event replay only if needed for entry/stop assumptions. Keep pure strategy and management functions identical across research and runtime.

## Logical modules and minimum Python package layout

```text
src/astrabot/
  config/               # versioned configs, schema validation; no real secrets
  data/                 # Binance adapters, normalized candles/trades/depth, readiness
  universe/             # exchange-eligibility + inexpensive opportunity shortlisting
  features/             # typed wrappers: all A01–A10 (plugin registry)
  regime/               # fixed point-in-time context, volatility and vetoes
  setups/               # persistent T1/R1/B1 objects; duplicate and expiry controls
  decision/             # policy evaluation, qualified registry, candidate selection
  research/             # replay, friction reports, matched controls, cohorts
  approval/             # authenticated one-use armed/post-trigger authorization
  execution/            # exactly one exchange writer, intent ledger, reconciliation
  supervision/          # immutable thesis, stop/TP/time/early-exit logic, watchdog
  agent_tools/          # six bounded read-only or proposal-request operations
  news/                 # verified event sources, symbol mapping, deterministic policies
  journal/              # append-only factual machine events + derived summaries
  api/                  # authenticated approval/status API; optional UI
  common/               # typed schemas, timestamps, enums, IDs, errors

tests/{contracts,unit,fixtures,integration,replay,fault}/
research/{configs,reports,manifests}/  # no private account data
```

Create this structure **gradually**, in milestone-sized increments; it is a target taxonomy, not permission to scaffold unused complexity in the first session.

## Data contracts (Python/Pydantic or JSON Schema; define before writing consumers)

Every relevant observation or feature has:
`symbol`, `instrument_id`, `venue`, `as_of`, `event_time`, `available_at`, `ingested_at`, `data_source`, `source_version`, `feature_version`, `units`, `fidelity`, `readiness`, `observation_id`, `config_hash`, `value`/`payload`. Times use UTC with timezone. Preserve exchange event and processing times separately; do not treat historical bar close as universally available earlier.

`fidelity` examples: `TRADE_DERIVED`, `BOOK_L2`, `BAR_DERIVED_APPROX`, `VENUE_ESTIMATE`. `readiness`: `COLD`, `WARMING`, `READY`, `DEGRADED`, `UNAVAILABLE`. Required unavailable features veto dependent *entries*, not existing protective operations.

### Persistent setup object

`setup_id, symbol, side, strategy_id, policy_version, formation_snapshot_id, anchor_ids, context_at_formation, frozen_levels, ATR/tick tolerances, created_at, confirmed_at?, expires_at, invalidation_reason?, confirmation_event_id?, consumed_at?, state`. State: `FORMING → ARMED → CONFIRMED → CONSUMED` or `INVALIDATED/EXPIRED`. A regime label flip does not retrospectively erase a setup; strategy-specific invalidation applies. Each setup may produce at most one approved trade lifecycle.

### Trade candidate and decision

`candidate_id, setup_id, strategy_version, symbol, side, trigger_spec, entry_bounds, stop, target_ladder, risk_profile_id, worst_fill_economics, used_feature_ids, rejected_level_alternatives, reason_codes, snapshot_hash, expires_at, qualification_status`. Results: `RESEARCH_ONLY`, `NO_TRADE`, `PROPOSE_APPROVAL`, with explicit reason codes. Never pass free-text numerical suggestions into execution.

### Approval and durable exchange intent

`plan_id, immutable_hash, approver_id, one_use_nonce, symbol/side, exact trigger_version, setup anchors, management_version, max_quantity/notional/leverage/loss, absolute entry bounds, stop/targets or bounded formula, approval_deadline, armed_deadline, submission_deadline, invalidation criteria, accepted_at?, consumed_at?`. On submission persist `intent_id, client_order_id, account_reservation_id, plan_hash, order_params, state` **before** any network request. Unknown submission means reconcile, never blind retry.

### Machine journal event

`event_id, occurred_at, received_at, symbol, lifecycle_id, setup_id?, actor, event_type, prior_state, new_state, snapshot_ids, policy_version, reason_code, relevant numbers, exchange_refs, correlation_id`. Append-only; redact account identifiers, keys and personally identifying data. Derived OpenBot summary links `event_ids`, never replaces source events.

## High-level OpenBot tool surface (examples; no raw exchange calls)

| Tool | Input | Output | Allowed side effect |
|---|---|---|---|
| `scan_opportunities` | universe policy/version, as_of | shortlisted symbol+reason IDs, freshness | read-only |
| `evaluate_symbol` | symbol, as_of, required families | regime/setup/feature IDs and readiness | read-only |
| `evaluate_candidates` | snapshot IDs | ranked qualifying candidates or NO_TRADE | read-only |
| `prepare_plan` | candidate ID, bounded policy | immutable candidate proposal ID for human review | persist **non-executable** proposal only |
| `get_plan_status` | plan ID | approved/armed/triggered/expired/rejected | read-only |
| `get_operations_summary` | time or lifecycle ID | positions, alarms, journal event IDs | read-only |

Human approval is through authenticated owner-facing API, not the LLM. Even for planned agent tools, external service authentication/permissions and schema validation must be enforced by code, not prompts. The execution gateway will honor a verified one-use authorization from the owner API; it does not accept model-authored order payloads.

## Timing and data dependencies

Context 4H → regime 1H → setup 15M → trigger closed 5M; lower-frequency trade-derived windows where qualified. The supervisor is **event-driven** (fills, price and data status, closed bars) plus configurable timer check; do not equate repeated polling of one closed candle with multiple confirmations. The 12-hour clock begins at earliest first fill and never resets. Protect and supervise positions even if coordinator, journal or an agent channel goes down.

## Storage, memory and continuity contract (pre-implementation design)

Separate **three classes of memory** rather than treating agent conversational state as authoritative:

1. **Trading truth (durable):** append-only exchange/intents/approvals/fills/protection/position/supervision events, immutable setup snapshots and earliest-fill clocks in transactional storage; idempotent IDs, versioned schemas, encrypted credentials, backup/restore and replay/reconciliation tests. Never depend on LLM memory for risk or order state.
2. **Market research and feature data (size-governed):** immutable source provenance/manifests, partitions by symbol/date/feed, cold archives for ticks/aggTrades where justified, bounded hot caches and summarized flow/profile aggregations with gap/readiness labels. Select and measure retention/partition/compaction based on observed feed volume; **do not** default to storing full-depth tick data for every altcoin indefinitely. Preserve enough original observations for causal replay of qualified policies.
3. **Agent/development memory:** small journal, ADRs, tested component registry, pointers to commits/datasets/results and compact tool outputs. Agents read scoped summaries instead of unbounded histories; document summary provenance, retention, permission and deletion. Journal and LLM-generated narratives are derived explanations, never sources of trading truth.

Before choosing a database/queue/retention period, measure ingestion and query load; document recoverability, backup/checksum procedures, growth limits, secrets protection and a restore drill. Start with existing database and filesystem/object-store facilities rather than a new vector DB, message broker or distributed event platform without demonstrated need.

## Repo/CI conventions

Python pinned dependency lock, formatting/typecheck, unit/contract fixtures, causal-prefix replay, component golden tests, integration fakes, fault harness, and optionally public demo adapter tests. Real API keys never enter CI or LLM runtime. Tests are tiered so basic commits stay fast. All nontrivial behavior and adopted versions need references in `03` register and `07` journal.

## C02 read-only implementation boundary

The C02 branch adds `data/models.py`, a typed observation layer using the C01
Decimal and UTC conventions; `data/binance.py`, an unauthenticated GET-only
allowlist for public USD-M metadata, candles, aggregate trades, book snapshots,
24h ticker, OI, mark/index and funding data; and `data/replay.py` for stable
raw normalization, gap checks and manifests. Live REST observations use the
capture time as their availability boundary when Binance supplies no publish
time. Archive replay uses the explicit exchange-close or trade-time proxy in
its manifest. Forming candles are omitted.

`universe/eligibility.py` applies the provisional v1.5 thresholds to the
point-in-time metadata snapshot and required feeds. Every input symbol keeps a
record with state and exclusion/selection reasons. The maximum 15-symbol output
is explicitly `RESEARCH_WATCHLIST`, with `executable=false`; range-edge
proximity, median spread and turnover are deterministic context/tie-breaks,
not strategy or profitability scores. Missing verified event clearance stays
warming.

`features/providers.py` exposes A01 aggregate-trade signed volume with
continuity/readiness, A02 UTC-session candle VWAP labeled
`BAR_DERIVED_APPROX`, and A03 as `UNAVAILABLE` until one inspected SMC
implementation passes expanding-prefix availability checks. No A03 hindsight
labels are copied into features. C02 adds offline synthetic and actual archive
fixtures plus CI; it does not change C01 execution contracts or expose private
account/order methods. The historical sample is a normalization smoke panel,
not eligible-universe or strategy evidence.

## Acceptance for architecture phase

A fake data snapshot can produce deterministic feature IDs and a NO_TRADE/proposal decision, without signed Binance access. A toy OpenBot coordinator can call the typed tools and cannot access trading keys. Services restart without losing recorded setup or approval state. Version pinning/fixture tests catch changed units or timestamps in adopted packages. No order-writing endpoint is accessible from the agent network.

## C05-G offline historical research pipeline

`data/historical_sources.py` streams strict Tardis-format USD-M `quotes`,
`derivative_ticker` and `book_snapshot_25` gzip CSV schemas. It checks compressed
SHA-256 before parsing, validates the full ordered header and each record,
preserves exchange `timestamp` and provider `local_timestamp` independently,
assigns stable source-row IDs, and detects duplicate rows, timestamp ties,
regressions, inverted arrival times and incomplete/invalid books. Exact duplicate
detection is disk-backed so a multi-million-row feed does not require an
in-memory observation set. Gzip streams are consumed to EOF for CRC/trailer
validation.

`data/historical_replay.py` selects source observations only when both their
exchange event and provider arrival proxy are no later than the decision time.
The research-only `c05g.periodic-spread.v1` sampler keeps `sampled_at` separate
from raw `event_time`, uses one distinct UTC-minute-aligned 60-second endpoint
window per sample,
requires 60 distinct occupied endpoints, preserves the 0.10% median threshold,
and applies a strict source-event age below 60 seconds. It never fills a missing
endpoint or rounds an exchange timestamp. C02's existing raw-event-time scanner
is unchanged; promotion of periodic sampling requires engineering-lead and
owner review. This isolates the proposed sampling interpretation from
production-facing eligibility.

Raw OI, book amounts, provider-arrival semantics and funding fields remain
explicitly uncertain. No C02 OI/depth pass, funding settlement, historical
metadata, event clearance or economic result can be inferred from these three
feeds. `scripts/c05_historical_research.py` performs an offline, checksummed
replay and writes deterministic JSON and Markdown reports; synthetic gzip
fixtures live under `tests/fixtures/c05g/`.

The replay's latest-quote, depth and OI freshness defaults derive from the
existing C02 `FreshnessPolicy`; the report configuration hash includes the
resolved thresholds. This keeps the research diagnostics aligned with existing
gate limits without changing eligibility behavior.
