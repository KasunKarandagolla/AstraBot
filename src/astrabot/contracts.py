"""Binding minimal v1.5 data contracts, not executable owner authentication.

Wire financial values are decimal strings, timestamps are explicit UTC and all
containers immutable. Schema validation cannot qualify a policy or grant owner
permission. Methods return new snapshots; durable compare-and-swap is the future
writer's responsibility. Only the focused tests implement a fake atomic ledger.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from typing import Annotated, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, AfterValidator, WithJsonSchema, model_validator


def _decimal(value):
    if not isinstance(value, (str, Decimal)):
        raise ValueError("financial values require decimal strings (or internal Decimal)")
    try:
        result = Decimal(value)
    except Exception as exc:
        raise ValueError("invalid decimal") from exc
    if not result.is_finite():
        raise ValueError("nonfinite financial value")
    return result


def _utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("explicit UTC timestamp required")
    return value


DecimalWire = WithJsonSchema({"type": "string", "pattern": r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$",
                              "description": "Finite exact decimal string; financial bounds validated by contract."})
Money = Annotated[Decimal, BeforeValidator(_decimal), Field(ge=0), DecimalWire]
Positive = Annotated[Decimal, BeforeValidator(_decimal), Field(gt=0), DecimalWire]
Signed = Annotated[Decimal, BeforeValidator(_decimal), DecimalWire]
UTC = Annotated[datetime, AfterValidator(_utc)]
ID = Annotated[str, Field(min_length=1)]
Side = Literal["LONG", "SHORT"]


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", validate_default=True)


class Anchor(Contract):
    anchor_id: ID
    source_event_id: ID
    price: Positive
    available_at: UTC


class SetupSnapshotV15(Contract):
    schema_version: Literal["setup_snapshot.v1.5"] = "setup_snapshot.v1.5"
    setup_id: ID
    strategy_version: ID
    strategy_policy_hash: ID
    symbol: ID
    side: Side
    venue: Literal["BINANCE_USDM_USDT_PERPETUAL"] = "BINANCE_USDM_USDT_PERPETUAL"
    source_snapshot_id: ID
    formed_event_id: ID
    anchors: tuple[Anchor, ...] = Field(min_length=1)
    frozen_atr: Positive
    tolerance: Money
    original_risk_parameters_hash: ID
    context_at_formation: ID
    formed_at: UTC
    confirmed_at: UTC | None = None
    available_at: UTC
    expires_at: UTC
    state: Literal["FORMING", "ARMED", "CONFIRMED", "CONSUMED", "INVALIDATED", "EXPIRED"]
    confirmed_event_id: ID | None = None
    consumed_by: ID | None = None
    invalidation_reason: ID | None = None

    @model_validator(mode="after")
    def chronology(self) -> Self:
        if not self.formed_at <= self.available_at < self.expires_at:
            raise ValueError("invalid setup chronology")
        if any(a.available_at > self.available_at for a in self.anchors):
            raise ValueError("anchor not available at formation snapshot")
        if self.state in ("CONFIRMED", "CONSUMED") and (not self.confirmed_event_id or not self.confirmed_at):
            raise ValueError("confirmation evidence required")
        if self.confirmed_at and not self.available_at <= self.confirmed_at < self.expires_at:
            raise ValueError("invalid confirmation chronology")
        if self.state == "CONSUMED" and not self.consumed_by:
            raise ValueError("consumption evidence required")
        if self.state == "INVALIDATED" and not self.invalidation_reason:
            raise ValueError("invalidation evidence required")
        return self

    def advance(self, state: str, **evidence) -> Self:
        allowed = {"FORMING": {"ARMED", "INVALIDATED", "EXPIRED"},
                   "ARMED": {"CONFIRMED", "INVALIDATED", "EXPIRED"},
                   "CONFIRMED": {"CONSUMED", "INVALIDATED", "EXPIRED"}}
        if state not in allowed.get(self.state, set()):
            raise ValueError("setup transition must be monotonic")
        if set(evidence) - {"confirmed_at", "confirmed_event_id", "consumed_by", "invalidation_reason"}:
            raise ValueError("frozen formation terms cannot change")
        return self.model_validate_json(self.model_copy(update={"state": state, **evidence}).model_dump_json())


class Target(Contract):
    price: Positive
    fraction: Annotated[Decimal, BeforeValidator(_decimal), Field(gt=0, le=1), DecimalWire]


class FixedGeometry(Contract):
    kind: Literal["FIXED"] = "FIXED"
    original_stop: Positive
    targets: tuple[Target, ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def complete(self) -> Self:
        if sum(t.fraction for t in self.targets) != 1:
            raise ValueError("target fractions must total one")
        return self


class BoundedGeometry(Contract):
    """Only one finite formula; arbitrary strings/code or unknown anchors fail.

    The future anchor must be of the exact approved source/type, published by the
    deadline and inside its closed interval. Stop = anchor + signed offset.
    Targets = actual entry + direction * target multiples * original distance.
    Final quantity-rounded economics must be rechecked before claiming an intent.
    """
    kind: Literal["BOUNDED_ANCHOR_OFFSET"] = "BOUNDED_ANCHOR_OFFSET"
    formula_version: Literal["anchor_offset_targets.v1"] = "anchor_offset_targets.v1"
    source_id: ID
    permitted_anchor_type: Literal["CONFIRMED_SWING", "CLOSED_RETEST_EXTREME"]
    anchor_min: Positive
    anchor_max: Positive
    stop_offset: Signed
    max_stop_distance: Positive
    target_multiples: tuple[Positive, Positive]
    target_fractions: tuple[Positive, Positive]
    minimum_scenario_net_rr: Annotated[Decimal, BeforeValidator(_decimal), Field(ge=Decimal("1.5")), DecimalWire]
    anchor_deadline: UTC

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if self.anchor_min > self.anchor_max or sum(self.target_fractions) != 1:
            raise ValueError("invalid bounded geometry")
        return self

    def resolve(self, *, entry: Decimal, side: Side, anchor: Anchor,
                anchor_type: str, now: datetime) -> FixedGeometry:
        if (anchor.source_event_id != self.source_id or anchor_type != self.permitted_anchor_type
                or not self.anchor_min <= anchor.price <= self.anchor_max
                or anchor.available_at > now or now > self.anchor_deadline):
            raise ValueError("unapproved future anchor")
        stop = anchor.price + self.stop_offset
        distance = abs(entry - stop)
        if not 0 < distance <= self.max_stop_distance or (side == "LONG") != (stop < entry):
            raise ValueError("unbounded or wrong-side stop")
        sign = 1 if side == "LONG" else -1
        return FixedGeometry(original_stop=stop, targets=tuple(
            Target(price=entry + sign * m * distance, fraction=f)
            for m, f in zip(self.target_multiples, self.target_fractions)))


class OwnerIdentity(Contract):
    """Reference to separately verified owner/MFA evidence, never a bearer grant."""
    owner_ref: ID
    authentication_evidence_ref: ID
    mfa_evidence_ref: ID


class TradeAuthorizationV15(Contract):
    schema_version: Literal["trade_authorization.v1.5"] = "trade_authorization.v1.5"
    plan_id: ID
    setup_id: ID
    lifecycle_id: ID
    one_use_nonce: ID
    approved_immutable_hash: ID
    owner: OwnerIdentity
    mode: Literal["POST_TRIGGER_APPROVAL", "PREAPPROVED_ARMED_PLAN"]
    symbol: ID
    side: Side
    venue: Literal["BINANCE_USDM_USDT_PERPETUAL"] = "BINANCE_USDM_USDT_PERPETUAL"
    position_mode: Literal["ONE_WAY"] = "ONE_WAY"
    margin_mode: Literal["ISOLATED"] = "ISOLATED"
    strategy_version: ID
    strategy_policy_hash: ID
    trigger_policy_hash: ID
    management_policy_hash: ID
    frozen_anchor_ids: tuple[ID, ...] = Field(min_length=1)
    entry_min: Positive
    entry_max: Positive
    quantity_max: Positive
    notional_max: Positive
    leverage_max: Annotated[Decimal, BeforeValidator(_decimal), Field(gt=0, le=2), DecimalWire]
    approved_max_risk_usdt: Positive
    cost_profile_hash: ID
    stop_cost_per_unit: Money
    target_cost_per_unit: Money
    geometry: Annotated[FixedGeometry | BoundedGeometry, Field(discriminator="kind")]
    readiness_ref: ID
    event_veto_ref: ID
    risk_veto_ref: ID
    approved_at: UTC
    approval_request_expires_at: UTC
    armed_expires_at: UTC
    setup_expires_at: UTC
    data_event_expires_at: UTC
    trigger_submit_deadline_ms: Annotated[int, Field(gt=0)]
    state: Literal["APPROVED_ARMED", "TRIGGER_CONFIRMED", "EXECUTION_STARTED", "DISARMED", "EXPIRED"]

    @model_validator(mode="after")
    def terms(self) -> Self:
        if self.entry_min > self.entry_max:
            raise ValueError("entry bounds inverted")
        if self.approved_at >= self.approval_request_expires_at:
            raise ValueError("owner approved after request expired")
        if self.approved_at >= min(self.armed_expires_at, self.setup_expires_at, self.data_event_expires_at):
            raise ValueError("approval after effective expiry")
        if isinstance(self.geometry, FixedGeometry):
            g = self.geometry
            if self.side == "LONG":
                valid = g.original_stop < self.entry_min and all(t.price > self.entry_max for t in g.targets)
            else:
                valid = g.original_stop > self.entry_max and all(t.price < self.entry_min for t in g.targets)
            if not valid:
                raise ValueError("stop/target geometry wrong side of approved entry range")
        return self

    def immutable_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"approved_immutable_hash", "state"})
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def check_submission(self, *, now: datetime, trigger_at: datetime,
                         quote: Decimal, quantity: Decimal) -> None:
        if self.immutable_hash() != self.approved_immutable_hash:
            raise ValueError("approved hash mismatch")
        if self.state not in ("APPROVED_ARMED", "TRIGGER_CONFIRMED"):
            raise ValueError("authorization not executable")
        chronology = (trigger_at <= self.approved_at <= now if self.mode == "POST_TRIGGER_APPROVAL"
                      else self.approved_at <= trigger_at <= now)
        if not chronology:
            raise ValueError("trigger chronology invalid")
        if now >= min(self.armed_expires_at, self.setup_expires_at, self.data_event_expires_at):
            raise ValueError("authorization expired")
        if now - trigger_at > timedelta(milliseconds=self.trigger_submit_deadline_ms):
            raise ValueError("trigger submission deadline exceeded")
        if not self.entry_min <= quote <= self.entry_max or not 0 < quantity <= self.quantity_max:
            raise ValueError("approved quantity/quote bound exceeded")
        if quote * quantity > self.notional_max:
            raise ValueError("notional cap exceeded")


class AccountReservationV15(Contract):
    schema_version: Literal["account_reservation.v1.5"] = "account_reservation.v1.5"
    reservation_id: ID
    plan_id: ID
    equity_snapshot_id: ID
    equity_basis: Positive
    risk_before: Money
    risk_after: Money
    notional_before: Money
    notional_after: Money
    effective_leverage: Money
    occupied_slots: Annotated[int, Field(ge=0, le=2)]
    available_slots: Annotated[int, Field(ge=0, le=2)]
    status: Literal["PENDING", "OPEN", "UNKNOWN", "RELEASED"]
    version_before: Annotated[int, Field(ge=0)]
    version: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def ceilings(self) -> Self:
        if self.version != self.version_before + 1:
            raise ValueError("reservation requires exact compare-and-swap successor")
        if (self.risk_after > self.equity_basis * Decimal(".005")
                or self.notional_after > self.equity_basis * 2
                or self.effective_leverage != self.notional_after / self.equity_basis
                or self.occupied_slots + self.available_slots != 2):
            raise ValueError("account reservation ceiling")
        return self


class OrderParameters(Contract):
    symbol: ID
    side: Literal["BUY", "SELL"]
    kind: Literal["LIMIT", "STOP_MARKET", "MARKET"]
    quantity: Positive | None = None
    price: Positive | None = None
    stop_price: Positive | None = None
    time_in_force: Literal["IOC", "GTC"] | None = None
    reduce_only: bool = False
    close_position: bool = False
    working_type: Literal["MARK_PRICE", "CONTRACT_PRICE"] | None = None
    price_protect: bool = False

    @model_validator(mode="after")
    def combinations(self) -> Self:
        if self.close_position and (self.quantity is not None or self.reduce_only or self.kind != "STOP_MARKET"):
            raise ValueError("closePosition cannot combine with quantity/reduceOnly")
        if not self.close_position and self.quantity is None:
            raise ValueError("sized order needs quantity")
        if self.kind == "LIMIT" and (self.price is None or self.time_in_force is None):
            raise ValueError("limit requires price and time in force")
        if self.kind == "STOP_MARKET" and (self.stop_price is None or self.working_type is None):
            raise ValueError("conditional stop requires trigger terms")
        return self


class OrderIntentV15(Contract):
    schema_version: Literal["order_intent.v1.5"] = "order_intent.v1.5"
    intent_id: ID
    lifecycle_id: ID
    approval_id: ID
    reservation_id: ID
    approved_hash: ID
    request: OrderParameters
    client_order_id: ID | None = None
    client_algo_id: ID | None = None
    exchange_order_id: ID | None = None
    exchange_algo_id: ID | None = None
    persisted_at: UTC
    submitted_at: UTC | None = None
    state: Literal["PERSISTED", "SUBMITTED", "UNKNOWN_SUBMISSION", "ACKNOWLEDGED", "PARTIAL", "FILLED", "CANCELLED", "REJECTED", "RECONCILED"]
    reconciliation_evidence: tuple[ID, ...] = ()
    action_version: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def identifiers(self) -> Self:
        if bool(self.client_order_id) == bool(self.client_algo_id):
            raise ValueError("exactly one ordinary/algo client identifier required")
        if (self.request.kind == "STOP_MARKET") != bool(self.client_algo_id):
            raise ValueError("conditional orders require distinct algo namespace")
        if self.submitted_at and self.submitted_at < self.persisted_at:
            raise ValueError("intent persisted after submit")
        return self

    def advance(self, state: str, **evidence) -> Self:
        allowed = {
            "PERSISTED": {"SUBMITTED", "REJECTED", "CANCELLED"}, "SUBMITTED": {"ACKNOWLEDGED", "UNKNOWN_SUBMISSION", "REJECTED"},
            "UNKNOWN_SUBMISSION": {"RECONCILED"}, "ACKNOWLEDGED": {"PARTIAL", "FILLED", "CANCELLED", "REJECTED", "RECONCILED"},
            "PARTIAL": {"FILLED", "CANCELLED", "RECONCILED"},
            "RECONCILED": {"PARTIAL", "FILLED", "CANCELLED", "REJECTED"}}
        if state not in allowed.get(self.state, set()):
            raise ValueError("illegal intent transition; unknown must reconcile original ID")
        if set(evidence) - {"submitted_at", "exchange_order_id", "exchange_algo_id", "reconciliation_evidence"}:
            raise ValueError("order parameters are immutable")
        if self.state == "UNKNOWN_SUBMISSION" and not evidence.get("reconciliation_evidence"):
            raise ValueError("unknown transition requires reconciliation evidence")
        for key in ("exchange_order_id", "exchange_algo_id", "submitted_at"):
            if getattr(self, key) is not None and key in evidence and evidence[key] != getattr(self, key):
                raise ValueError("recorded exchange identity/submission time cannot change")
        return self.model_validate_json(self.model_copy(update={"state": state,
            "action_version": self.action_version + 1, **evidence}).model_dump_json())


class TerminalProof(Contract):
    correlated_boundary_id: ID
    confirmed_at: UTC
    venue_quantity: Money
    all_entry_intents_terminal: bool
    all_exit_orders_terminal: bool
    all_algo_orders_terminal: bool

    @property
    def complete(self) -> bool:
        return self.venue_quantity == 0 and self.all_entry_intents_terminal and self.all_exit_orders_terminal and self.all_algo_orders_terminal


class ExitLatchV15(Contract):
    schema_version: Literal["exit_latch.v1.5"] = "exit_latch.v1.5"
    lifecycle_id: ID
    exit_reason: ID
    latched_at: UTC
    position_version: Annotated[int, Field(ge=0)]
    current_order_ids: tuple[ID, ...]
    unresolved_entry_ids: tuple[ID, ...]
    terminal_proofs: tuple[TerminalProof, ...] = ()


class PositionLifecycleV15(Contract):
    schema_version: Literal["position_lifecycle.v1.5"] = "position_lifecycle.v1.5"
    lifecycle_id: ID
    management_policy_hash: ID
    first_fill_at: UTC | None
    initial_filled_quantity: Money
    remaining_quantity: Money
    verified_stop_ids: tuple[ID, ...]
    verified_tp_ids: tuple[ID, ...]
    exit_latch: ExitLatchV15 | None
    outstanding_entry_ids: tuple[ID, ...]
    outstanding_exit_ids: tuple[ID, ...]
    outstanding_algo_ids: tuple[ID, ...]
    reconciliation: Literal["REQUIRED", "CONSISTENT", "DISAGREEMENT"]
    approved_max_risk_usdt: Positive
    initial_modeled_risk_usdt: Money | None
    d0_price: Money | None
    initial_entry_terminal: bool
    initial_entry_reconciliation_ref: ID | None = None
    state: Literal["NO_POSITION", "SUPERVISED", "EXIT_REQUESTED", "RECONCILING", "FLAT_RECONCILED"]
    terminal_proof: TerminalProof | None = None
    action_version: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def supervised(self) -> Self:
        if self.initial_filled_quantity > 0 and self.first_fill_at is None:
            raise ValueError("real exposure requires earliest first-fill timestamp")
        if self.initial_modeled_risk_usdt is not None and (not self.initial_entry_terminal or not self.initial_entry_reconciliation_ref):
            raise ValueError("initial risk needs terminal entry and reconciled actual fill set")
        if self.remaining_quantity > self.initial_filled_quantity:
            raise ValueError("remaining quantity exceeds observed cumulative entry fills")
        # Observed adverse fills remain recordable in a supervised fault state.
        if (self.initial_modeled_risk_usdt is not None
            and self.initial_modeled_risk_usdt > self.approved_max_risk_usdt
            and self.state not in ("RECONCILING", "EXIT_REQUESTED", "FLAT_RECONCILED")):
            raise ValueError("observed risk breach requires supervised fault state")
        if self.state == "FLAT_RECONCILED" and (not self.terminal_proof or not self.terminal_proof.complete
                or self.remaining_quantity != 0 or self.outstanding_entry_ids or self.outstanding_exit_ids
                or self.outstanding_algo_ids or self.reconciliation != "CONSISTENT"):
            raise ValueError("terminal lifecycle requires flatness and cleared instructions")
        return self

    def revise(self, **changes) -> Self:
        if self.state == "FLAT_RECONCILED":
            raise ValueError("terminal proof cannot revive; late evidence requires fault reconciliation")
        if changes.get("initial_filled_quantity", self.initial_filled_quantity) < self.initial_filled_quantity:
            raise ValueError("observed cumulative entry quantity cannot decrease")
        immutable = {"schema_version", "lifecycle_id", "management_policy_hash"}
        if any(k in changes and changes[k] != getattr(self, k) for k in immutable):
            raise ValueError("lifecycle identity and management policy are immutable")
        if self.initial_entry_terminal and changes.get("initial_filled_quantity", self.initial_filled_quantity) != self.initial_filled_quantity:
            raise ValueError("late discovery requires fault reconciliation; finalized initial quantity frozen")
        if self.initial_entry_terminal and changes.get("initial_entry_terminal", True) is not True:
            raise ValueError("initial entry finalization cannot reverse")
        if "action_version" in changes and changes["action_version"] != self.action_version + 1:
            raise ValueError("position update requires action-version successor")
        changes["action_version"] = self.action_version + 1
        if "first_fill_at" in changes and self.first_fill_at is not None:
            if changes["first_fill_at"] is None or changes["first_fill_at"] > self.first_fill_at:
                raise ValueError("first fill can only move earlier with exchange evidence")
        for key in ("approved_max_risk_usdt", "initial_modeled_risk_usdt", "d0_price"):
            if key in changes and getattr(self, key) is not None and changes[key] != getattr(self, key):
                raise ValueError("original risk denominator and approval ceiling are immutable")
        if self.exit_latch and changes.get("exit_latch", self.exit_latch) != self.exit_latch:
            raise ValueError("exit latch cannot clear or change")
        return self.model_validate_json(self.model_copy(update=changes).model_dump_json())


class EconomicsV15(Contract):
    schema_version: Literal["economics.v1.5"] = "economics.v1.5"
    approved_max_risk_usdt: Positive
    actual_entry_quantity: Money
    weighted_initial_entry: Positive | None
    original_stop: Positive
    modeled_stop_cost_per_unit: Money
    initial_entry_terminal: bool
    realized_net_pnl_usdt: Signed
    # Realized P&L already includes fills, fees and funding; do not subtract twice.
    realized_fees_usdt: Money
    realized_funding_usdt: Signed
    cost_profile_hash: ID

    @model_validator(mode="after")
    def filled_geometry(self) -> Self:
        if self.actual_entry_quantity and self.weighted_initial_entry is None:
            raise ValueError("filled quantity requires entry price")
        if self.actual_entry_quantity and self.d0_price == 0:
            raise ValueError("zero original stop distance")
        # Preserve observed truth above the approved cap for fault investigation.
        return self

    @property
    def d0_price(self) -> Decimal | None:
        return abs(self.weighted_initial_entry - self.original_stop) if self.weighted_initial_entry else None

    @property
    def initial_modeled_risk_usdt(self) -> Decimal | None:
        if not self.initial_entry_terminal:
            return None
        if not self.actual_entry_quantity:
            return Decimal(0)
        return self.actual_entry_quantity * (self.d0_price + self.modeled_stop_cost_per_unit)

    @property
    def cost_r(self) -> Decimal | None:
        return self.modeled_stop_cost_per_unit / self.d0_price if self.d0_price else None

    @property
    def net_r(self) -> Decimal | None:
        denominator = self.initial_modeled_risk_usdt
        return self.realized_net_pnl_usdt / denominator if denominator else None


def scenario_net_rr(gross_price_r: Decimal, d0_price: Decimal,
                    win_cost_per_unit: Decimal, loss_cost_per_unit: Decimal) -> Decimal:
    if d0_price <= 0 or min(win_cost_per_unit, loss_cost_per_unit) < 0:
        raise ValueError("invalid price distance/costs")
    return (gross_price_r * d0_price - win_cost_per_unit) / (d0_price + loss_cost_per_unit)


class CompletePolicyExpectancyV15(Contract):
    """Definition only; no research qualification or expectancy is calculated here.

    Full selector attempts include authorization attrition and missed/no fills.
    Policy net USDT outcomes include every stop/TP/thesis/time/funding path.
    No-fill net_R is undefined, never divide by zero. Report both attempt/fill
    counts and a separately declared normalization for monetary policy expectancy.
    A successful ladder scenario alone supplies no statistical expectancy.
    """
    schema_version: Literal["complete_policy_expectancy.v1.5"] = "complete_policy_expectancy.v1.5"
    management_policy_hash: ID
    selector_policy_hash: ID
    untouched_dataset_ref: ID
    attempts: Annotated[int, Field(ge=0)]
    approvals: Annotated[int, Field(ge=0)]
    fills: Annotated[int, Field(ge=0)]
    no_fill_attempts: Annotated[int, Field(ge=0)]
    normalization_definition_ref: ID
    all_path_net_usdt_outcomes_ref: ID

    @model_validator(mode="after")
    def attrition(self) -> Self:
        if not self.fills <= self.approvals <= self.attempts or self.no_fill_attempts + self.fills != self.attempts:
            raise ValueError("attempt/fill attrition counts inconsistent")
        return self
