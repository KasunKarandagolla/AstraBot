# ADR-EXEC-001 — One execution owner and C01 v1.5 contracts

Date: 2026-10-24. Status: **PROPOSED — independent project-lead review required**.
Base: `e333818da488ea27788624dbc4937327faa52701` (`main`).
Scope: P0/C01 feasibility; no live gateway, account connection, strategy qualification,
or change to the approved operational topology.

## Decision and evidence boundary

Provisionally retain the **official Binance modular USD-M SDK with a bounded durable
gateway** as the single future execution owner. The comparison does not establish
Binance demo qualification. Keep Freqtrade available for a separately qualified
research baseline; defer NautilusTrader unless event-level research or operational
requirements demonstrate enough benefit to offset its additional integration surface.

The SDK reuses current endpoint transport, response models, ordinary/algo identifiers,
user streams and connection machinery without importing an independent trading policy
or a second OMS. It leaves substantial, explicit safety glue: authenticated one-use
approval, account reservations, durable intent/outbox, unknown-result reconciliation,
first-fill protection, an exit latch, and independent deterministic supervision. None
of these is supplied by a generic SDK. C01 implements only their typed boundary and
a credential-free fake fault harness.

No candidate natively supplies AstraBot's entire authorization/risk contract.
Freqtrade needs a write-boundary authorization integration, changes to unsafe
callback/replacement behavior, and Binance demo support enabled and qualified.
Nautilus supplies more lifecycle infrastructure but
still needs AstraBot approval/reservations and Binance-specific protective choreography.
The recommendation minimizes the number of overlapping lifecycle/policy authorities;
it does not claim that less initial code necessarily means less operational risk.

Evidence vocabulary: `SOURCE_VERIFIED` means inspected pinned source or vendor tests;
`FAKE_TESTED` means an executed test with synthetic inputs/transport;
`DEMO_VERIFIED` requires an actual supported demo observation;
`UNVERIFIED` means not exercised; `UNSUPPORTED` means an inspected interface rejects
the required operation. Source inspection and fake tests are separate evidence levels.
**No behavior in this ADR is DEMO_VERIFIED.**

## Pinned comparison

| Candidate | Exact inspected source | Runtime and important dependencies | Evidence |
|---|---|---|---|
| A: official SDK | `binance-sdk-derivatives-trading-usds-futures==18.1.0`, `binance-common==4.7.0`; [commit 6b3ba001274406372d376e218c8b9d04bd9c1720](https://github.com/binance/binance-connector-python/tree/6b3ba001274406372d376e218c8b9d04bd9c1720/clients/derivatives_trading_usds_futures), released 2026-10-23 | Python >=3.10,<3.15; requests, urllib3, aiohttp, pycryptodome, Pydantic >=2.14.1. Executed Python 3.12.14. | SOURCE_VERIFIED; actual full-package mocked transport probe: 8 checks; 20 selected upstream mocked tests passed. |
| B: Freqtrade sole writer | Stable `2026.9`, [commit 1f394eaebc2f46a83d26971388628707802f8602](https://github.com/freqtrade/freqtrade/tree/1f394eaebc2f46a83d26971388628707802f8602), dated 2026-09-29 | Python >=3.11; release requirements pin CCXT 4.5.84 and SQLAlchemy 2.0.54, plus TA-Lib/numpy/pandas. Full environment not installed. | SOURCE_VERIFIED; 9 AST-extracted actual vendor-hook scenarios passed. Full framework and upstream suite UNVERIFIED. |
| C: NautilusTrader sole writer | Stable `v1.231.0`, [commit 27a8e54e7ac3c57d6cbf8891f0283dfbaee97317](https://github.com/nautechsystems/nautilus_trader/tree/27a8e54e7ac3c57d6cbf8891f0283dfbaee97317), dated 2026-08-02 | Python >=3.12,<3.15; Rust 1.97.1/edition 2024, Cython 3.2.9, msgspec, pyarrow, pandas, uvloop; native modules. | SOURCE_VERIFIED only; runtime and upstream suite not executed. |

Nautilus's annotated tag object is `d3e1685e979925d7b0ffacd1b3f442547686e18f`;
the commit above is its peeled commit, not that tag object. Release selection used
stable tags, excluding Nautilus 2.x release candidates. The CCXT 4.5.84 wheel's actual
Binance source was inspected without installing/executing CCXT.
[`candidates.lock.json`](../../tests/vendor/candidates.lock.json) records source,
artifact and fetched-document hashes; [`sdk-requirements.lock`](../../tests/vendor/sdk-requirements.lock)
records the resolved SDK test environment. Framework dependency ranges are inspected
requirements, not a claim of a resolved/installed framework runtime.

## Mandatory feasibility matrix

All rows refer to the exact pins above. A described wrapper is future work, not an
implemented or vendor-qualified feature. Binance account behavior remains unverified
for all three candidates. Source reference keys are expanded below.

| Required area | A — SDK + bounded gateway | B — Freqtrade sole owner | C — NautilusTrader sole owner |
|---|---|---|---|
| Entry authorization | A1 direct methods have no human gate. Custom atomic approval/intent boundary; C01 fake only. | B1 initial-entry callback exists, but lacks one-use/identity/reservation semantics. Needs gate below every writer path. | C1 native numeric risk checks, no owner authorization. Guard all execution delegation with custom approval. |
| Exception handling | A2 timeout/503 behavior FAKE_TESTED; custom gate must fail closed. Protective actions remain independent. | B1 FAKE_TESTED: callback ValueError/Exception permits entry because default=True. Unsafe as authorization boundary. | C1 queue error handling is not owner authorization. Fail-closed custom boundary UNVERIFIED. |
| Bypass prevention | A1 REST and WS write APIs both exposed. Isolate credentials and deny direct callers. | B1 FAKE_TESTED: pos_adjust/replace skip callback; new force entry calls it, existing force entry uses pos_adjust. Patch/guard all increases. | C1 risk engine `is_bypassed` directly forwards commands. Disable bypass and guard direct clients, actors and lists. |
| Durable intent before send | A1 is stateless transport; custom committed approval+reservation+client IDs before network. | B1 exchange call precedes Trade creation/commit; no durable application client ID there. Core persistence integration required. | C2 stable IDs, OrderSubmitted event and optional persistent cache help, but atomic approved outbox commit before send UNVERIFIED. |
| Unknown IOC response | A1/A2 FAKE_TESTED IOC encoding; POST timeout/unknown503 do not retry. Query original ordinary ID; retain reservation. | B2 CCXT generates ID internally; Freqtrade does not durably persist it before send. Unknown-send recovery needs integration. | C2 inflight reconciliation/client-ID query exists. Retry/rejection after actual venue acceptance remains UNVERIFIED; preserve unknown risk. |
| Partial entry fills | A3 fill events expose last/cumulative quantity and trade time. First-fill protection/reducer custom. | B1 adopts filled quantity on expired IOC; later stop-management loop does not prove 2s protection. Deadline integration needed. | C2 native partial-fill/position events; upstream partial/reconstruction tests inspected. Immediate protected quantity policy still custom. |
| Protective whole stop | A1 algo closePosition encoding FAKE_TESTED; read-back/coverage and 2s deadline custom; venue acceptance UNVERIFIED. | B3 creates reduceOnly stop later; CCXT current algo routes inspected. Exact whole-position stop coverage/account behavior UNVERIFIED. | C3 modern STOP_MARKET algo, quantity/reduceOnly or closePosition route. Fill-to-stop gap/read-back UNVERIFIED. |
| Two TP legs | A1 ordinary reduceOnly LIMIT primitives; custom actual-filled/rounded fractions and sibling cleanup. Venue coexistence UNVERIFIED. | B2 negative position adjustments support sequential partial reductions, not established two resting TP legs. Needs custom persistent leg state. | C3 independent reduceOnly orders available; Binance linked/OCO brackets explicitly UNSUPPORTED. Custom leg coordinator required. |
| Stop tightening | A1 only LIMIT amend established; no atomic algo amend. Keep old stop until overlap qualification and verified replacement. | B3 cancels old stop then creates replacement. Unmodified flow violates no-gap requirement; patch or disable elective changes. | C3 non-triggered stop modification rejected; limit/triggered limit child only. Custom safe replacement choreography required. |
| Late fills / exit latch | A3 events/query primitives; durable latch, cancel-unknown handling and compensation custom. | B2 cancel races handled partly, but irreversible lifecycle latch not established. Implement original-lifecycle protection/reduction. | C2 upstream tests explicitly reopen cancelled orders on late fills: useful accounting, not an exit latch. Add durable policy. |
| Account reservations | Balance endpoints, no pending/open/unknown reservation manager. Custom account CAS/transaction. | B2 wallet subtracts open-trade stakes; pre-send unknown-intent risk/slot reservation not established. Custom ledger needed. | C1 account/balance/list checks help; no durable cross-command approval+unknown-risk reservation proof. Custom transaction needed. |
| Restart / reconnect | A3 transport reconnect has selected upstream fake tests. Restore journal, renew user stream and reconcile positions + ordinary + algo + unknowns before entry. | B2 persistent Trade/Order startup fetches known DB order IDs; never-persisted submissions absent. Custom approval/unknown/stop barrier. | C2 cache DB/load and venue reconciliation are meaningful reuse. Configure persistence/actor save-load explicitly; correlate approval journal and both order namespaces. |
| First-fill holding limit | No native AstraBot clock; persist earliest exchange fill, 11h55m exit and +12h emergency custom. | B4 poll/candle callback timing differs live/backtest. Add durable first-fill watchdog independent of strategy cadence. | C4 TestClock/LiveClock and timers reusable; first-fill immutable deadline/exit policy custom. |
| Exactly one writer | SDK library supplies no process fence. Isolated credentialed owner and fenced recovery required. | B2 bot lock is in-process, not account exclusivity. Guard RPC/other processes and isolate keys. | C4 serialized command/event queues do not fence concurrent transport tasks/processes. One account owner still required. |
| API priority | A2 rate-limit/error/backoff primitives, no protection budget scheduler. Reserve capacity and throttle scans. | B4 exits precede entries in loop, but public refresh precedes management; no protected HTTP lane established. | C4 quotas/FIFO queues do not establish emergency priority. Custom protected budget/admission control. |
| Total maintenance | Maintained small transport surface; substantial but explicit finite safety glue, no framework policy fork. Preferred provisional baseline. | Core authorization/persistence/stop patches plus framework policy and CCXT drift. Highest conflict with exact contract. Research use remains plausible. | Strongest reusable event/cache lifecycle, but native build, risk/cache/async adapter and custom approval/legs must agree. Defer pending measured net benefit. |

## Actual source and vendor-hook evidence

Pinned source keys (file/symbols and tests actually inspected):

- **A1:** [`TradeApi`](https://github.com/binance/binance-connector-python/blob/6b3ba001274406372d376e218c8b9d04bd9c1720/clients/derivatives_trading_usds_futures/src/binance_sdk_derivatives_trading_usds_futures/rest_api/api/trade_api.py#L1335): `new_algo_order:1335`, `new_order:1488`, `modify_order:1231`, `query_algo_order:1805`, `query_order:1997`, `current_all_algo_open_orders:811`, `current_all_open_orders:869`, `position_information_v3:1757`; mode primitives `change_margin_type:644`, `change_position_mode:757`. Ordinary enum includes stop values but ordinary method lacks trigger fields: enum membership does not prove support.
- **A2:** [`common/utils.py`](https://github.com/binance/binance-connector-python/blob/6b3ba001274406372d376e218c8b9d04bd9c1720/common/src/binance_common/utils.py#L350) retry/send/sign/error paths `:350,551,614,690`. POST is not retried; timeout wraps `NetworkError` with Timeout cause; unknown 503 becomes generic `ServerError`, losing Binance's message. Treat uncertain writes conservatively as UNKNOWN_SUBMISSION. The actual SDK serializes forbidden closePosition+quantity+reduceOnly together; local validation is not exchange validation.
- **A3:** [`common/websocket.py`](https://github.com/binance/binance-connector-python/blob/6b3ba001274406372d376e218c8b9d04bd9c1720/common/src/binance_common/websocket.py#L805) reconnect/subscription replay `:805–1048`; client `websocket_streams/models/user_data_stream_events_response.py:85,198` routes ALGO_UPDATE, ORDER_TRADE_UPDATE, ACCOUNT_UPDATE, listenKeyExpired; `order_trade_update_o.py:29–67` includes fill quantities/IDs/time. Reconnection is not account reconciliation or listen-key renewal.
- **SDK upstream tests executed:** `clients/derivatives_trading_usds_futures/tests/unit/rest_api/test_trade_api.py` selected new ordinary/algo success/required-field, algo query/list and V3 positions; `common/tests/unit/test_websocket.py` three retry/reconnect cases. **20 passed**, 326 deselected, 12 collection warnings. All use fake transport; real sockets/HTTP/signing blocked/mocked. Full vendor suite not run. The upstream optional algo fixture sends mutually invalid fields: a mock passing cannot prove exchange acceptance.
- **B1:** [`FreqtradeBot.execute_entry`](https://github.com/freqtrade/freqtrade/blob/1f394eaebc2f46a83d26971388628707802f8602/freqtrade/freqtradebot.py#L1113) callback `:1113`, exchange `:1133`, IOC fill handling `:1156–1194`, Trade creation/commit `:1201,1244`; [`strategy_safe_wrapper`](https://github.com/freqtrade/freqtrade/blob/1f394eaebc2f46a83d26971388628707802f8602/freqtrade/strategy/strategy_wrapper.py#L31); [`RPC._rpc_force_entry`](https://github.com/freqtrade/freqtrade/blob/1f394eaebc2f46a83d26971388628707802f8602/freqtrade/rpc/rpc.py#L1157). Tests read: `tests/strategy/test_strategy_safe_wrapper.py:20–37`, `tests/freqtradebot/test_freqtradebot.py:1151–1209`; the latter explicitly expects exception entry success.
- **B2:** `freqtrade/exchange/exchange.py:create_order:1498–1573`, `freqtradebot.py:handle_cancel_enter:2044`, `startup_update_open_orders:570`, `update_trade_state:2506`, position adjustment `:982–1041`; `wallets.py:336–346`. CCXT 4.5.84 wheel `ccxt/binance.py:6738–6803,6913,7179,7228,8018,8069` has current ordinary/conditional algo and clientAlgoId routing; this source was read, not executed.
- **B3:** [`exchange stop creation`](https://github.com/freqtrade/freqtrade/blob/1f394eaebc2f46a83d26971388628707802f8602/freqtrade/exchange/exchange.py#L1673) uses reduceOnly; `freqtradebot.py:create_stoploss_order:1598`, `handle_stoploss_on_exchange:1634`, `handle_trailing_stoploss_on_exchange:1731–1766` cancels before creating replacement. `exchange/binance.py:81–86,121–146` supports cross and isolated, rejects hedge; isolated rejects multi-asset. **Binance `supports_demo_trading=False` at `binance.py:49–53`; `exchange.py:930–936` rejects demo configuration.** Modern CCXT algo support does not remove this explicit demo blocker. AstraBot must assert its narrower isolated/one-way scope.
- **B4:** `freqtradebot.py:process:305–362`, `worker.py:58,145,197`; `optimize/backtesting.py:726,1192,1669` and `docs/strategy-callbacks.md:61,910` distinguish repeated live adjustments from candle-based backtests.
- **C1:** [`risk/engine.pyx`](https://github.com/nautechsystems/nautilus_trader/blob/27a8e54e7ac3c57d6cbf8891f0283dfbaee97317/nautilus_trader/risk/engine.pyx#L414) submit/list/bypass/risk paths `:414,458,666,1000`. No human approval boundary established.
- **C2:** `adapters/binance/execution.py:410,823,830–861,1020,1179` status/submitted/client-ID/retry paths; `live/config.py:85–120` inflight reconciliation; `cache/config.py:61`, `execution/engine.pyx:774`, `system/config.py:122`, `common/actor.pyx:208,226` persistence defaults/hooks. Tests **read, not run**: `tests/unit_tests/execution/test_engine.py:813–899,1259–1331` late/partial fills; `tests/unit_tests/live/test_execution_recon.py:448–498` partial reconstruction.
- **C3:** [`Binance execution adapter`](https://github.com/nautechsystems/nautilus_trader/blob/27a8e54e7ac3c57d6cbf8891f0283dfbaee97317/nautilus_trader/adapters/binance/execution.py#L1112) linked/OCO deny `:1112–1128`, stop algo `:1130–1227`, modify `:1287–1304`, parent/child cancellation `:1516–1541`; `futures/http/account.py:529–556,1119` modern algo endpoints; `futures/execution.py:163,330,385,447–455,750` ALGO_UPDATE and parent/child reports. Tests **read, not run**: `tests/integration_tests/adapters/binance/test_execution_futures.py:619–651,1335–1378,1539–1635,1678–1726`. The bracket test expects all three linked orders denied before HTTP.
- **C4:** `common/component.pyx:419,485,623,839` timers/clocks, `backtest/engine.pyx:2708,3924` simulated matching, `live/execution_engine.py:147,486,511` async queues, `adapters/binance/factories.py:113–141` quotas. These are source observations, not live/replay equivalence proof. `futures/execution.py:124,234,265` account type/margin/mode setup must be configured; startup can change margin/leverage, which C01 did not perform.

[`probe_freqtrade.py`](../../tests/vendor/probe_freqtrade.py) executes complete AST-extracted
actual pinned wrapper/entry/force-entry function bodies with fake collaborators;
RPC validation is explicitly stubbed and real source inspected separately. Its 9 cases
are not a full Freqtrade installation or integration test. [`probe_sdk.py`](../../tests/vendor/probe_sdk.py)
imports the complete actual SDK checkout, verifies hashes/import origin and mocks
transport/signature. Nautilus received source/test inspection only. All other
unexercised framework/runtime claims remain **UNVERIFIED**.

## Binance restrictions and remaining qualification

Current official pages retrieved 2026-10-24 UTC (HTML SHA256 and unusable legacy
responses recorded in the candidate lock):

- [USD-M trade API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade): ordinary `/fapi/v1/order`; conditional `/fapi/v1/algoOrder`; distinct clientOrderId/clientAlgoId and triggered child ordinary IDs. IDs unique among open orders are not indefinite idempotency keys. Query retention is finite; keep the local journal.
- [Exchange information](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#exchange-information): tickSize/stepSize and current filters, not pricePrecision/quantityPrecision, govern rounding and eligibility.
- [User-data streams](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/user-data-streams): listen-key lifetime/keepalive; stream reconnect does not establish complete account truth. Legacy per-event URLs returned content shells; SDK event models supplied source evidence, not those pages.
- [General API information](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info): unknown execution after some 503 responses requires query/stream reconciliation. Documented risk-reduction overload exemptions are not a universal protective-algo priority guarantee.

In one-way mode use positionSide BOTH; assert isolated and supported single-asset
account configuration. `closePosition=true` whole-position STOP_MARKET must omit
quantity and reduceOnly. Quantity-defined exits can use reduceOnly in one-way mode;
that parameter is forbidden in hedge mode. Trigger basis MARK_PRICE/CONTRACT_PRICE
and priceProtect are approved terms; priceProtect=true can delay triggering under
excess mark/contract divergence, so it cannot be presumed safer. There is no proven
atomic fill-and-stop or in-place conditional-stop amendment.

All candidates still require **UNVERIFIED** demo tests of: account-mode assertions and
endpoint guard; marketable IOC full/partial/nonfill and lost acknowledgement; actual
ordinary/algo/triggered-child query/event correlation; filled-quantity stop read-back
within measured local deadline; whole-position stop + two partial reduceOnly TPs;
stop/TP races and sibling cleanup; overlap replacement acceptance/rejection/unknown;
reconnect/listen-key expiry and restart with unknown orders; venue limits/rounding and
priority under load. SDK specifically needs the full guarded adapter; Freqtrade also
needs its approval/persistence/stop changes; Nautilus needs installed native runtime,
guarded delegation and independent leg coordination. No account mode was read or changed.

Nautilus `adapters/binance/common/urls.py:50–56,144–150` explicitly maps USDT DEMO to
`demo-fapi.binance.com` and `demo-fstream.binance.com`; factories resolve an unspecified
environment to LIVE (`factories.py:51–54`). This is source support, not a tested demo
connection. Freqtrade's pinned Binance adapter explicitly rejects demo configuration,
so configuration override/patch and qualification would be required even before its
order-safety gaps could be exercised on these demo hosts.

SDK constructors default to production endpoints. Future demo writer construction must
require explicit allowlisted REST **and** stream endpoints and a qualified demo account;
an environment label alone cannot authorize it. C01 fixtures expose no network transport.

## Minimal binding contracts and transaction boundaries

[`src/astrabot/contracts.py`](../../src/astrabot/contracts.py) uses strict frozen
Pydantic 2.14.1 models, decimal strings on the wire, finite Decimal arithmetic and
explicit UTC timestamps. Nested containers are tuples; unknown fields and nonfinite
financial values are rejected. JSON Schema is available through `model_json_schema()`;
schema-version literals identify each v1.5 record without a duplicate generated schema.

| Contract | Frozen boundary / essential behavior |
|---|---|
| `SetupSnapshotV15` | Strategy/source versions, original anchors, ATR/tolerance, causal formation/confirmation/availability, expiry, invalidation/consumption. `advance` permits monotonic states without rewriting formation. No T1/R1/B1 algorithms. |
| `TradeAuthorizationV15` | Exact hash/nonce, verified-identity evidence reference, setup/lifecycle, both approval variants, strategy/trigger/management versions, side bounds, quantity/notional/leverage/modeled loss, stop/target geometry, veto references and separate request/armed/setup/data-event/trigger clocks. |
| `FixedGeometry`, `BoundedGeometry` | Fixed original stop and at most two fractional targets, or a single versioned finite anchor-offset formula with permitted source/type, anchor range/deadline, maximum distance and minimum scenario economics. No arbitrary executable formula. Final economics rechecked at the approved adverse entry. |
| `AccountReservationV15` | Equity basis, before/after risk/notional/leverage/slots, pending/open/unknown/released state, exact version successor/CAS. The fake reserves the approved ceiling conservatively and includes pending/unknown reservations. |
| `OrderParameters`, `OrderIntentV15` | Immutable request, intent/lifecycle/approval/reservation IDs, distinct ordinary/algo namespaces, persisted/submitted time, acknowledgement and reconciliation evidence. Unknown can only advance through reconciliation of the original ID. Cross-field stop parameter validation fills the observed SDK gap. |
| `ExitLatchV15`, `PositionLifecycleV15`, `TerminalProof` | Earliest fill, actual initial/remaining quantities, verified stop/TP IDs, outstanding entry/exit/algo IDs, management version and immutable original risk denominator. Latch cannot be cleared; terminal requires correlated flatness plus resolved instructions. Failed operations do not end supervision. |
| `EconomicsV15`, `CompletePolicyExpectancyV15`, `scenario_net_rr` | Separate approved ceiling, terminal actual-filled stop/cost risk, cost-R, realized net-R and target-success scenario. Complete-policy attempt/approval/fill counts explicitly preserve attrition. Observed risk breaches remain representable rather than losing exposure because a validator rejects exchange truth. |

Frozen Pydantic models are not a security boundary: callers can construct unchecked
objects with `model_copy`/`model_construct`. The fake authorization boundary revalidates
the wire payload and compares it to the trusted registered immutable approval. Future
production consumers must do the same at their authenticated boundary.

These records are data contracts, not evidence of authenticated owner identity.
Production must verify the owner/MFA assertion in a trusted approval service and
keep credentials out of every agent/research process. Both post-trigger approval and
bounded armed approval remain research variants. No strategy is promoted by this ADR.

For a production transaction: lock/CAS the account version; revalidate the approved
hash, unused nonce, unconsumed setup, current vetoes, all independent deadlines and
side-specific price bounds; reserve pending/open/unknown risk, notional and slots;
persist the one-use claim plus immutable intent and client IDs; commit. Perform
exchange I/O after commit, then persist acknowledgement or UNKNOWN_SUBMISSION in a
new short transaction. Recovery reconciles the original IDs, fills, positions and both
order namespaces. Never release unknown reservations or invent a new speculative ID.
No database lock spans exchange network I/O. The fake ledger is a test fixture, not
the project's future PostgreSQL execution implementation.

Financial definitions preserve `approved_max_risk_USDT` separately from the initial
actual-filled denominator. `d0_price` is the absolute initial weighted entry to
original stop distance. Finalize `initial_modeled_risk_USDT` only after the initial
entry group and actual fills are reconciled terminal; freeze it thereafter.
`cost_R = round_trip_cost_per_unit / d0_price`; `scenario_net_RR` is net successful
ladder proceeds / modeled initial stop loss; `net_R` is actual net USDT P&L / frozen
initial modeled risk. Fees, funding and route costs must not double-count spread or
slippage embedded in fills. Complete-policy expectancy must include rejected,
expired, unfilled, partial, stopped, time-exited and approval-attrition outcomes;
zero-fill attempts have no realized filled-position denominator. A successful target
scenario is not historical expectancy.

The B1 baseline remains RESEARCH_ONLY: `0.4*1 + 0.6*2 = 1.6` gross price-R;
`(1.6*d-c)/(d+c) >= 1.5` exactly when `c/d <= 0.04` for equal modeled costs.
With separate route costs the equivalent condition is
`c_win + 1.5*c_loss <= 0.10*d`. No threshold or target has been changed.

## Reproduction and focused acceptance evidence

From repository root, Python 3.12.14 (setup installation uses approved package access;
the actual test process has an empty environment except the variables shown):

```sh
python3.12 -m venv work/c01-venv
work/c01-venv/bin/python -m pip install -r requirements-test.txt
env -i PATH=/usr/bin:/bin PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 work/c01-venv/bin/python -m pytest -q
work/c01-venv/bin/python -m pip check
```

Observed final output: **`68 passed in 0.33s`**, 0 failed, 0 skipped;
`No broken requirements found.` Python 3.12.14, Pydantic 2.14.1/core 2.50.1,
pytest 8.4.2. Exact normal-suite dependencies are in `requirements-test.txt`.
All normal tests deny sockets and remove credential-related environment variables;
the reported command additionally scrubs the process environment before Python starts.
There is no SDK, HTTP client, endpoint or credential capability in the fake fixture.

[`tests/c01_fake.py`](../../tests/c01_fake.py) implements a bounded synthetic venue,
clock and two independent SQLite/JSON stores (owner ledger and venue truth).
[`tests/test_c01_acceptance.py`](../../tests/test_c01_acceptance.py) executes the
following matrix; its AT mapping identifies related original obligations, **not**
full completion of each production acceptance test.

| C01 case | Actual fake assertion | Related v1.5 IDs |
|---|---|---|
| F01 | Missing/invalid/expired/disarmed/mismatched/replayed authorization or readiness/event/risk veto causes zero entry writes. | AT08, AT84, AT105, AT107 |
| F02 | Callback exception/rejection fails closed; fake alternate route cannot submit missing intent. Actual Freqtrade exception permissiveness separately reproduced. | AT122 |
| F03 | Eight concurrent claims of one approval yield one durable intent and at most one write. | AT08, AT106 |
| F04 | Account CAS contention, pending/unknown reservations, 0.25% per trade/0.50% aggregate, two slots, per-symbol exclusion and 2x notional ceiling. | AT108 |
| F05 | Lost IOC acknowledgement retains UNKNOWN_SUBMISSION/reservation and resolves original ID/fills without duplicate. | AT11, AT109 |
| F06 | First partial fill protects actual quantity; duplicate and earlier out-of-order fills preserve earliest time. Exchange/local detection timestamps separate. | AT12, AT27, AT56, AT121 |
| F07 | Rejected/unknown/absent stop or 2001ms local acknowledgement triggers durable halt/latch/reduceOnly exit; exactly 2000ms succeeds. API submission never counts as flatness. | AT13, AT87 |
| F08 | Two sized reduceOnly TP legs update only on actual fills, respect order remainder and cannot reverse in long/short stop races. Price touch has no effect. | AT49–AT50, AT55–AT57, AT114 (related management obligations) |
| F09 | Unsafe/widening/rejected/unknown/absent elective replacement retains verified original stop; success verifies new before cancelling old. | AT43, AT51–AT54, AT113 |
| F10 | Durable exit latch, uncertain entry cancel and late remainder fill stay attached to original lifecycle and issue reduction without fresh entry. | AT110–AT111 |
| F11 | New owner/venue objects recover disk state; reconnect disagreement, absent unknown IDs, unowned exposure and missing protection preserve entry barrier until reconciled/protected. | AT14, AT88, AT112, AT115, AT121 |
| F12 | Earliest-fill +11h55m begins flatten, +12h residual exposure faults; restart/later fills/outage do not reset time. Ten-second entry cancellation also tested. | AT27–AT29, AT121 |
| F13 | Long buy IOC upper cap / short sell lower cap; final submission rechecks quote, vetoes, original setup expiry and original trigger deadline. | AT84, AT106 |
| F14 | Exact Decimal B1 gross 1.6 and equal-cost 0.04 boundary; 0.25 cost-R fails admission. | AT100 |
| F15 | Partial actual quantity/original costs finalize risk only on terminal initial group; TP/stop change cannot reset denominator; scenario, realized R and approval cap distinct. | §8.5, AT100 |
| F16 | Flat snapshot/failed operation cannot release with unknown or missing ACK/RECONCILED original entry, working ordinary/algo/TP or unresolved exit. Proven flat plus cleared orders can terminate. | AT112, AT115 |

Extra regressions cover real post-trigger approval delay, bounded formula evidence,
monotonic frozen setup, strict financial wire schema/UTC, daily UTC 1% entry halt
without flatten (AT120), actual-fill risk breach/frozen history, and late discovery
after denominator finalization. That late-discovery branch records actual exposure,
preserves the original denominator, latches a durable reconciliation fault and halts
entries; production correction/accounting policy remains unverified.

The fake's atomic snapshot, immediate scheduled fills and reduceOnly/closePosition
semantics are stronger assumptions than separate live REST snapshots. It has no real
owner/MFA verification, exchange filters/margin validator, production DB/fencing, or
API priority scheduler. AT37/AT85/AT86/AT89 require operational/account qualification;
fake ownership records do not establish those controls. AT43/AT55 and other mapped
venue behavior remain unverified beyond the exact synthetic scenarios above.

Offline vendor reproduction (install into a **separate** interpreter):

```sh
git clone https://github.com/binance/binance-connector-python work/candidates/sdk/binance-connector-python
git -C work/candidates/sdk/binance-connector-python checkout --detach 6b3ba001274406372d376e218c8b9d04bd9c1720
python3.12 -m venv work/candidates/sdk/venv
work/candidates/sdk/venv/bin/python -m pip install -r tests/vendor/sdk-requirements.lock
env -i PATH=/usr/bin:/bin work/candidates/sdk/venv/bin/python tests/vendor/probe_sdk.py work/candidates/sdk/binance-connector-python
env -i PATH=/usr/bin:/bin work/candidates/sdk/venv/bin/python tests/vendor/run_sdk_tests.py work/candidates/sdk/binance-connector-python
git clone https://github.com/freqtrade/freqtrade work/candidates/freqtrade
git -C work/candidates/freqtrade checkout --detach 1f394eaebc2f46a83d26971388628707802f8602
env -i PATH=/usr/bin:/bin work/c01-venv/bin/python tests/vendor/probe_freqtrade.py work/candidates/freqtrade
```

The session installed SDK/common from the exact checkout; the lock also allows their
same-version public distributions. Both runners import the complete pinned checkout
and assert source hashes and installed metadata. No dependency installation occurs
inside either runner. Observed: SDK probe **8 checks passed**; SDK selected upstream
tests **20 passed, 326 deselected, 12 collection warnings**; Freqtrade AST probe **9
cases passed**. [`observed-results.json`](../../tests/vendor/observed-results.json)
records outputs/evidence classes. These are separate totals, not 105 full-engine tests.

Nautilus source reproduction: clone
`https://github.com/nautechsystems/nautilus_trader` and detach
`27a8e54e7ac3c57d6cbf8891f0283dfbaee97317`; verify inspected-file hashes in the
candidate lock. **Nautilus runtime and full Freqtrade suite: NOT RUN. Binance public,
signed demo and live requests: zero.** Demo qualifications were not collected as fake
passing/skipped pytest cases.

## Minimum future integration, maintenance and rollback

SDK: isolate one signed writer; implement the small transaction boundary above using
the project's transactional store; reconcile normal/algo/child orders and user fills;
use the approved management policy for whole-position protection, two TP legs,
late-fill exits and the persisted first-fill timer; reserve API capacity for
protection/exits/reconciliation ahead of scans. Independently qualify exchange filters,
one-way isolated mode, daily UTC entry halt, owner identity and process/network fencing.
This is C07 work after the research gates, not permission to build a general OMS now.

Freqtrade: enforce approval below every order-producing callback/force/adjust/replace
path; remove fail-open authorization behavior; establish durable pre-send claims and
unknown reservations; qualify or patch protection replacement and multi-leg quantities;
implement first-fill supervision outside coarse strategy scheduling. This cuts across
framework policy and persistence and imposes release-by-release patch requalification.
Rollback is disabling live Freqtrade operation; research-only use remains independent.

Nautilus: integrate approvals/reservations at the execution command boundary and audit
direct commands, emulation and strategy actors; configure/persist cache and reconciliation;
map native identifiers/events to ordinary/algo/child orders; implement Binance-safe
stop/TP relationships and the holding/exit latch policy. Its event engine is meaningful
reuse, but its Python/native build, adapter, cache, risk engine and order-state model
expand the integration that must remain consistent. Revisit if measured benefits
remove more custom lifecycle risk than this interface costs. Do not co-run it as writer.

Keep vendor pins immutable. A failed upgrade retains the prior tested transport and
existing verified protection, halts entries, and triggers qualification of the changed
surface. Removing a candidate must not remove the durable ledger or supervision of
existing positions. Changing owners requires reconciliation to flat/cleared instructions
and explicit single-writer handoff, never two credentialed engines competing.

## Gate, owner authority and reconsideration

C01 implementation/evidence is **READY FOR INDEPENDENT REVIEW**, not independently
accepted. The bounded Sol code audit reproduced and corrected premature terminal
release on absent acknowledged entry and actual setup-expiry bypass before send;
the final main-agent scrubbed regression run passed 68 tests. No known unresolved
P0/P1 remains in this scoped fake/contract gate. This is not an audit of a production
gateway or certification of a real engine/account. The top journal phase/NEXT_GATE
and verified progress credit remain unchanged pending project-lead review.

Deferred P2: production fencing/transaction durability, real authenticated approval,
ordered non-atomic venue snapshots, filters/rounding/dust, API-budget load behavior,
late-fill final-accounting correction and actual stop/TP/overlap qualification belong
to C07/C08; keeping them explicitly unverified does not obstruct C02's read-only data
work **after** this ADR/contracts pass review. Strategies and B1 economics remain
research-only; C03/C05 own their expert study and economic qualification.

No project-shaping change is accepted here. Project-lead review must accept or reject
this provisional ADR before C02 begins. A different operational topology, relaxed risk
or authorization meaning, or any live promotion requires owner approval. Selection
alone authorizes none of those changes.

Reconsider the SDK recommendation if its current algo/stream interfaces cannot be
qualified, if safe whole-stop/TP coexistence is unavailable for the approved account
mode, or if a pinned framework demonstrates the same fault matrix with materially
less custom safety code and no permissive path. The cheapest next qualification is
an isolated demo adapter probe of bounded IOC lost acknowledgement and a partial fill
with independently queried whole-position stop plus two reduce-only TPs; keep elective
stop replacement disabled until overlap is demonstrated. Account qualifications block
demo/live promotion, not the creation of these source-based C01 research interfaces.
