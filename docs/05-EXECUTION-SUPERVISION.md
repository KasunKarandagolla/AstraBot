# 05 — Approval, Single-Writer Execution and Active Trade Supervision

**Scope:** deterministic order-lifecycle and risk-reducing behavior for Binance USDⓈ-M perpetuals. **Only test/demo capability is planned until a separate owner live-promotion decision.** Vendor semantics must be verified against the pinned account mode and official API; no README claim alone certifies a stop.

## 1. Separate authority from transport

- OpenBot: coordinates a new-trade evaluation and reports typed evidence. No live credentials, order endpoints, arbitrary signing capability, direct approvals or override of risk gates.
- Owner portal: authenticated with MFA; approve/reject **one immutable plan hash + nonce**. A Telegram/chat message can notify but not act as trade approval.
- Decision engine: *proposes* only qualified exact setups; research policy cannot become live because its output looks plausible.
- Independent risk service: validates equity, adverse-fill-bound loss, cost profile, stop/target geometry, slot limits, news/data/instrument conditions and account-wide reserved capacity.
- Exactly one owner of ordinary and algo orders. Preferred transport candidate official Binance USD-M Python SDK, or a **replacement** selected in C01. No parallel Freqtrade and SDK writers.
- Position supervisor/watchdog: always-on independent of model, owner workstation or journal; executes approved reductions, stops and flat-by-policy attempts.

## 2. Trade authorization options

**Preferred research variant: bounded pre-approved armed plan** so owner/LLM latency is outside the last seconds of entry. Alternative: immediate post-trigger proposal and manual approval. Compare both as separate policies; do not call the armed version automatically better.

Approval payload binds `plan_id, nonce, immutable_hash, owner, symbol, side, instrument mode, setup_id+anchor_ids, strategy/policy version, trigger version, precise entry range and adverse bound, stop/targets or bounded formulas, max quantity/notional/leverage/loss, approved management version, expiration clocks, data/event/liquidity vetoes`.

**Clocks are distinct:** approval-request expiry (initial research default 90 sec), armed expiry (candidate 30–60 min but earlier if setup/event expires), trigger-to-submission max delay, and the open-position clock from *earliest fill*. Approval cannot auto-extend. Submitted orders must claim **one atomic authorization and account reservation** before network sends. Unknown acknowledgement is `UNKNOWN_SUBMISSION`, not permission to retry a second order.

## 3. State machines (implement explicitly; never infer from UI labels)

```text
SETUP: FORMING -> ARMED -> CONFIRMED -> CONSUMED
                     \-> INVALIDATED / EXPIRED
AUTH:  PENDING -> APPROVED_ARMED -> TRIGGER_CONFIRMED -> EXECUTION_STARTED
                    \-> CANCELLED / REJECTED / EXPIRED
ORDER INTENT: PLANNED -> PERSISTED -> SENT -> ACK/UNKNOWN -> PART_FILL/FILL/CANCEL/REJECT
POSITION: NONE -> PARTIALLY_OPEN/OPEN -> EXIT_REQUESTED -> REDUCING -> FLAT_RECONCILED
OPERATION: HEALTHY / DEGRADED_DATA / HALTED_ENTRIES / EMERGENCY_EXIT / RECONCILING
```

Any order/workflow can fail while position remains open; `FAILED` is **never** allowed to mark un-reconciled exposure terminal. Only `FLAT_RECONCILED` after entry intents and protective instructions have been resolved ends supervision for the lifecycle. Reserve risk for pending, unknown and partially filled exposures until reconciled. Block a new trade on that symbol while prior exposure or orphaned instruction exists.

## 4. Minimal exact execution algorithm

```text
on_approved_trigger(plan_id, event):
  atomically confirm one-use approval, plan state, trigger freshness, risk and capacity
  persist order intent and reserved capacity before first Binance write
  submit side-correct adverse-bounded IOC limit / specifically qualified variant
  if transport outcome unknown: query original client_order_id and reconcile; no blind resend
  on first partial fill: mark earliest fill time, place/verify exchange-native protection urgently
  continuously reconcile trade fills, remaining entry, reduce-only targets, full-position stop
  if protective placement fails or cannot be confirmed by policy deadline: execute emergency exit policy
  on entry terminal: finalize filled quantity and immutable initial modeled risk; do not reset first-fill timer
```

Do not claim atomic fill-and-stop if exchange only permits separate calls. Measure `exchange_fill→protection_ACK` and `local_detect→protection_ACK`, including failures/tails. Guarantee only **best effort** flatten when an exchange outage prevents orders. Use Binance official account/user-data and independent reconciliation snapshots, recognizing separate REST calls aren't necessarily atomic.

**Binance parameter checks:** fixed v1 one-way/isolated account mode; differentiate ordinary orders from conditional algo orders; check `STOP_MARKET`, `TAKE_PROFIT_MARKET`, `closePosition=true`, `reduceOnly`, quantity, trigger basis `MARK_PRICE/CONTRACT_PRICE`, `priceProtect`, step/tick, position-side and algorithm IDs against actual current SDK/test environment. Test whether whole-position stop can coexist with partial resting TP legs under selected mode; do not assume undocumented overlap safety.

## 5. Stop replacement and partial TP (highest-risk operational area)

An optional stop tightening request follows:

1. Read **reconciled** remaining position, stop, TP and in-flight order state.
2. Validate **new stop is no looser** than original/last verified stop and obeys market/tick/venue rules.
3. Attempt overlap: submit new protective conditional order **only if** exact Binance/account behavior has passed a safe-overlap test; independently verify its presence/trigger configuration.
4. Only then cancel or retire the old stop, reconciling simultaneous triggers, cancel acknowledgements, positions and algo-spawned ordinary orders.
5. If overlap is not supported safely or result is unknown, **retain the existing verified stop**, or execute preauthorized reduce-only emergency exit; never remove the only known protection just to pursue a tighter stop.

Partial TP quantities derive from **actual finalized initial filled quantity**, rounded safely. A TP line touching the chart doesn't count: reduce exposure only after Binance-confirmed fills. On fills cancel/resize stale targets as needed, preserve stop, avoid reversing position, and manage dust/min-lot constraints via a documented branch. A target update may bring profit closer according to an approved policy but may never widen stop/increase risk. Reconcile every target after reconnect.

## 6. Live thesis supervision (not LLM free-form reasoning)

Each position stores original immutable thesis: setup ID/version, context, structural anchors/levels, VWAP anchor/roll policy, stop, target-ladder, risk assumption, entry first-fill time, allowed management policy and source evidence. A market event or configured heartbeat calls the same **pure `evaluate_management(position_state, feature_snapshot)`** used in replay. Repeated watches of the same candle count as **one observation**.

| Thesis/risk state | Trigger type | Allowed response |
|---|---|---|
| `VALID` | Setup still inside frozen tolerances | HOLD, qualified TP, qualified later structure-tighten |
| `WEAKENING` | Named soft deterioration confirmed, no hard break | Preapproved partial reduction / nearer target / hold, policy-specific |
| `BROKEN` | Exact strategy hard invalidation confirmed | Reduce-only EXIT immediately under original approval |
| `UNKNOWN_DATA` | Required analysis stream stale/incomplete | Maintain venue protection, pause elective modifications, halt new exposure |
| `RISK_EMERGENCY` | Stop missing, margin/capacity breach, time expiry, severe operational fault | Highest priority: emergency reduce-only reconcile/flatten policy |

**Do not use universal 'three bad ticks → stop to breakeven' rules.** Test management variants independently: no-BE baseline, fee-aware break-even after real TP1 fill plus approved confirmation, later confirmed structure trailing, nearer opposition levels and failure-to-progress/time decay. Management version cannot silently mutate mid-position. Do not treat a new VWAP day or regime label alone as a broken thesis. Never widen stop, average down or add exposure.

**Time rule:** Begin flatten at earliest fill +11h55m. At +12h all residual exposure is in emergency exit workflow. Persist this absolute deadline, including partial fills, restarts and supervisor handoffs. Poll a watchdog timer independently (v1.5 at least every 5 sec) in addition to event-driven supervision; a configured analytical heartbeat such as ~10sec is **not** a timing guarantee or proof that the last 5M candle changed. During Binance outage keep exit-intent durable and retry/reconcile as available, halt new entries and alert.

## 7. Race conditions and fail-closed recovery scenarios

- **Entry fills after exit intent:** persist `exit_requested` latch before cancellations/exits; cancel remaining entry, keep protection, reconcile any late fill, flatten/re-protect it; never send a new speculative entry under the same approval.
- **IOC result lost:** query original client ID, Binance fills and position; don't retry with a new ID until resolved.
- **A stop and TP race:** latest remaining venue quantity is authoritative after reconciliation; ensure reduce-only/close position behavior cannot flip the net position; clean orphaned orders.
- **Two approvals at once:** account-wide durable reservation transaction guards aggregate 0.50% risk, slots and notional including pending unknown intents; per-symbol lock alone is insufficient.
- **Restart/stream gap:** halt entries; restore durable intents, open/partial positions, algo and ordinary orders, consumed approvals and first-fill timers; rebuild correlated event boundary and compare exchange truth; only resume when consistent.
- **Unowned/manual position:** safe mode, do not adopt into a strategy or turn off emergency monitoring silently; require owner decision.
- **Data/LLM/Journal outage:** stop new plan authorization as appropriate, but continue exchange-native protection, deterministic supervisor, forced exits and reconciliation.
- **Scanner rate-limit saturation:** reserve Binance API budget for position protection/emergency; deprioritize discretionary symbol scans.
- **Daily loss threshold:** latched **entry halt** for the UTC day using reconciled equity baseline adjusted for external transfers; no automatic flatten merely because this entry cutoff tripped unless a separately authorized emergency policy says so.

### Mandatory invariants to assert in code/tests

`no_new_exposure_without_one_use_owner_approval`, `exactly_one_writer`, `never_remove_sole_verified_protection_for_optional_adjustment`, `no_stop_widen`, `no_scale_in_v1`, `partial_exit_reduce_only`, `position_always_supervised_until_flat_reconciled`, `first_fill_timer_never_resets`, `late_fill_does_not_reopen_orphan`, `no_automatic_retry_of_unknown_submit`, `no_entry_while_account_unreconciled`.

## 8. Definition of done for operational layer

Fake exchange deterministic fault tests pass for approval exceptions, duplicate submissions, lost acknowledgements, missing stop, two target races, order replacement, restarts, 12h timer and entry/exit races. The exact selected Binance demo adapter passes the same **applicable** scenarios using redacted logs. A demo test proves wiring only, not market liquidity, historical edge or live safety in every market. Live access remains off pending documented owner promotion.

## 9. C06-E offline fake runtime boundary

C06-E persists the C06 proposal/status/event record in one SQLite file and reuses the C01 fake owner and fake venue in their existing, separate SQLite files. The fixture owner decision (approve, reject, expire, consume once) is a local harness interface, is clearly labeled as simulated identity, and is absent from the six-tool MCP server. C01 remains the only risk validator and fake order owner.

The three files do not share a transaction. On restart, the fake venue snapshot and C01 owner ledger decide whether an approval was consumed, an order exists, a fill occurred, protection is visible, and flat reconciliation is proven. C06 status is a recoverable mirror. If an order acknowledgment or terminal instruction cannot be correlated, the harness keeps the lifecycle unresolved and does not submit a replacement blindly. This test milestone does not demonstrate authenticated owner MFA, production uptime or Binance Demo behavior.
