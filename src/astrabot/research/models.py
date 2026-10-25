"""Frozen C03 artifacts. A research decision is never a bearer authorization."""
from __future__ import annotations

from datetime import timedelta
from typing import Literal

from pydantic import Field, model_validator

from astrabot.contracts import (
    Contract, EconomicsV15, FixedGeometry, ID, Money, Positive, Side,
    Signed, SetupSnapshotV15, Target, UTC,
)
from astrabot.data.models import Candle, Readiness, stable_id
from astrabot.research.context import BalanceEvidence
from astrabot.research.levels import StructuralLevel

VERSIONS = {"T1": "T1.reclaim.v1", "R1": "R1.sweep.v1", "B1": "B1.original-ladder.v1"}


class Dependency(Contract):
    name: ID
    role: Literal["MANDATORY", "VETO", "RECORD_ONLY"]
    readiness: str
    source_ids: tuple[str, ...] = ()


class ResearchSetup(Contract):
    """Policy terms around the accepted C01 lifecycle, not a second FSM.

    Selecting a sweep/retest records a later event; it never edits formation
    anchors. C01's advance method exclusively changes lifecycle states.
    """
    snapshot: SetupSnapshotV15
    strategy_id: Literal["T1", "R1", "B1"]
    instrument_id: ID
    levels: tuple[StructuralLevel, ...]
    opposing_at_formation: tuple[StructuralLevel, ...] = ()
    feature_refs: tuple[str, ...]
    atr_15m: Positive
    balance_at_formation: BalanceEvidence | None = None
    session_id: str | None = None
    prior_vwap_event_id: str | None = None
    selected_bar: Candle | None = None
    selected_extreme: StructuralLevel | None = None
    confirmation_bar: Candle | None = None
    processed_event_ids: tuple[str, ...] = ()
    last_bar_open: UTC
    next_bar_open: UTC
    retest_last_open: UTC | None = None
    confirmation_due_open: UTC | None = None
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def coherent(self):
        if self.snapshot.strategy_version != VERSIONS[self.strategy_id]:
            raise ValueError("policy version mismatch")
        if any(x.symbol != self.snapshot.symbol or x.instrument_id != self.instrument_id
               or x.available_at > self.snapshot.available_at for x in self.levels):
            raise ValueError("formation levels must be available at formation")
        expected = tuple((x.level_id, stable_id(*x.source_ids), x.price, x.available_at) for x in self.levels)
        actual = tuple((x.anchor_id, x.source_event_id, x.price, x.available_at) for x in self.snapshot.anchors)
        if not expected or actual != expected:
            raise ValueError("formation levels must match original lifecycle anchors")
        if self.strategy_id == "R1" and (self.balance_at_formation is None
                or not self.balance_at_formation.qualified
                or self.balance_at_formation.available_at > self.snapshot.available_at):
            raise ValueError("R1 requires saved available balance qualification")
        if self.selected_bar and self.selected_bar.source_record_id not in self.processed_event_ids:
            raise ValueError("selected interaction must be processed evidence")
        if bool(self.selected_bar) != bool(self.selected_extreme):
            raise ValueError("selected interaction and structural extreme must be paired")
        if self.selected_bar:
            b, x = self.selected_bar, self.selected_extreme
            price = b.low if self.snapshot.side == "LONG" else b.high
            if (b.symbol != self.snapshot.symbol or b.instrument_id != self.instrument_id
                    or b.available_at <= self.snapshot.available_at or b.interval != "5m"
                    or x.price != price or x.source_ids != (b.source_record_id,)
                    or x.event_time != b.close_time or x.available_at != b.available_at
                    or x.kind != ("SWEEP_EXTREME" if self.strategy_id == "R1" else "RETEST_EXTREME")):
                raise ValueError("selected extreme must match its distinct source candle")
        if self.confirmation_bar:
            b = self.confirmation_bar
            if (b.source_record_id != self.snapshot.confirmed_event_id
                    or b.available_at != self.snapshot.confirmed_at
                    or b.source_record_id not in self.processed_event_ids
                    or b.available_at <= self.snapshot.available_at):
                raise ValueError("confirmation must match lifecycle evidence")
        return self


class ResearchAccount(Contract):
    """Explicit synthetic/reconciled input; not read from an account API."""
    source_id: ID
    as_of: UTC
    equity_usdt: Positive
    pending_open_risk_usdt: Money
    pending_open_notional_usdt: Money
    isolated_margin_available_usdt: Money
    occupied_slots: int = Field(ge=0)
    occupied_symbols: tuple[str, ...] = ()
    reconciled: bool
    daily_entry_halt: bool
    mode: Literal["ISOLATED_ONE_WAY_USDT_PERPETUAL"] = "ISOLATED_ONE_WAY_USDT_PERPETUAL"


class CostProfile(Contract):
    version: ID
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    # Entry spread/slippage are embedded once in the worst IOC entry price.
    entry_fee_rate: Money
    ordinary_exit_fee_rate: Money
    stop_exit_fee_rate: Money
    ordinary_exit_spread_per_unit: Money
    ordinary_exit_slippage_per_unit: Money
    stop_spread_per_unit: Money
    stop_slippage_per_unit: Money
    funding_per_unit: Money
    status: Literal["RESEARCH_ONLY"] = "RESEARCH_ONLY"


class ScenarioEconomics(Contract):
    gross_price_r: Signed
    cost_r: Money
    scenario_net_rr: Signed
    midpoint_screen_net_rr: Signed | None = None
    win_cost_per_unit: Money
    loss_cost_per_unit: Money
    proposed_quantity: Money
    target_quantities: tuple[Money, ...]
    proposed_modeled_loss_usdt: Money
    account_risk_ceiling_usdt: Money
    approved_max_risk_usdt: None = None
    actual_filled_initial_modeled_risk_usdt: None = None
    realized_net_r: None = None
    full_policy_expectancy: None = None
    # C01 execution economics is intentionally absent before approval/fills.
    execution_economics: EconomicsV15 | None = None
    status: Literal["RESEARCH_ONLY"] = "RESEARCH_ONLY"


class ResearchDecision(Contract):
    schema_version: Literal["research_decision.c03.v1"] = "research_decision.c03.v1"
    decision_id: ID
    setup_id: str | None
    strategy_id: Literal["T1", "R1", "B1"]
    strategy_version: ID
    symbol: ID
    instrument_id: ID
    side: Side
    as_of: UTC
    source_snapshot_id: ID
    context_id: ID
    feature_refs: tuple[str, ...]
    entry_method: Literal["MARKETABLE_IOC_LIMIT_RESEARCH"] = "MARKETABLE_IOC_LIMIT_RESEARCH"
    trigger_event_id: str | None = None
    earliest_hypothetical_entry_at: UTC | None = None
    entry_min: Positive | None = None
    entry_max: Positive | None = None
    adverse_bound: Literal["BUY_MAX", "SELL_MIN"]
    trigger_submit_deadline: UTC | None = None
    geometry: FixedGeometry | None = None
    original_stop: Positive | None = None
    targets: tuple[Target, ...] = ()
    original_anchor_ids: tuple[str, ...] = ()
    target_level_ids: tuple[str, ...] = ()
    rejected_level_ids: tuple[str, ...] = ()
    management_policy_hash: ID
    cost_profile_hash: ID
    scenario_net_rr: Signed | None = None
    economics: ScenarioEconomics | None = None
    expires_at: UTC
    readiness: Readiness
    dependencies: tuple[Dependency, ...]
    rejection_reason_codes: tuple[str, ...]
    decision: Literal["RESEARCH_CANDIDATE", "NO_TRADE"]
    research_status: Literal["RESEARCH_ONLY"] = "RESEARCH_ONLY"
    executable: Literal[False] = False
    holding_limit: timedelta = timedelta(hours=12)
    flatten_objective: timedelta = timedelta(hours=11, minutes=55)

    @model_validator(mode="after")
    def complete_candidate(self):
        if self.targets != (self.geometry.targets if self.geometry else ()):
            raise ValueError("decision targets must match frozen geometry")
        if self.decision == "RESEARCH_CANDIDATE":
            if (not self.setup_id or not self.trigger_event_id or not self.geometry
                    or self.original_stop != self.geometry.original_stop
                    or self.entry_min is None or self.entry_max is None
                    or self.entry_min > self.entry_max or not self.economics
                    or self.scenario_net_rr is None or self.scenario_net_rr < 1.5
                    or self.rejection_reason_codes or self.readiness != "READY"
                    or self.trigger_submit_deadline is None
                    or self.trigger_submit_deadline <= self.as_of
                    or self.expires_at <= self.as_of
                    or self.earliest_hypothetical_entry_at is None):
                raise ValueError("incomplete research candidate")
        elif not self.rejection_reason_codes:
            raise ValueError("NO_TRADE requires machine-readable reasons")
        return self

class ResearchState(Contract):
    setups: tuple[ResearchSetup, ...] = ()
    decisions: tuple[ResearchDecision, ...] = ()


class Evaluation(Contract):
    state: ResearchState
    emitted: tuple[ResearchDecision, ...]
