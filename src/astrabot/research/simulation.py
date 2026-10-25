"""Research-only counterfactual execution and portfolio accounting.

Nothing in this module imports a Binance order client or can create exchange
exposure. OHLCV-triggered fills are explicitly labeled as bar-model estimates.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal as D, ROUND_FLOOR
from typing import Literal

from pydantic import ConfigDict, Field

from astrabot.contracts import Contract
from astrabot.data.models import Candle, FundingObservation
from astrabot.research.economics import rounded
from astrabot.research.models import CostProfile, ResearchDecision
from astrabot.universe.eligibility import SymbolData


class ExecutionScenario(Contract):
    scenario_id: Literal["E0", "E1", "E2"]
    label: str
    approval_mode: Literal["NONE", "PREAPPROVED_ARMED", "POST_TRIGGER_IMMEDIATE", "HUMAN_DELAY", "REJECTED", "NO_RESPONSE"]
    approval_delay: timedelta = timedelta(0)
    ioc_ttl: timedelta = timedelta(seconds=1)
    fill_model: Literal["NONE", "OHLC_TOUCH", "OHLC_CLOSE_CROSS"] = "OHLC_TOUCH"
    approval_outcome: Literal["APPROVED", "REJECTED", "NO_RESPONSE"] = "APPROVED"
    fee_multiplier: D = D(1)
    spread_slippage_multiplier: D = D(1)
    fill_fraction: D = D(1)
    funding_mode: Literal["OBSERVED_ONLY", "DECLARED_MAX_HOLD_PROXY"] = "DECLARED_MAX_HOLD_PROXY"
    sample_end: datetime | None = None

    @classmethod
    def no_execution(cls) -> "ExecutionScenario":
        return cls(scenario_id="E0", label="No execution policy truth",
            approval_mode="NONE", fill_model="NONE", approval_outcome="NO_RESPONSE",
            funding_mode="OBSERVED_ONLY")

    @classmethod
    def conservative(cls, *, sample_end: datetime | None = None) -> "ExecutionScenario":
        return cls(scenario_id="E1", label="Conservative hypothetical bar-model execution",
            approval_mode="POST_TRIGGER_IMMEDIATE", approval_delay=timedelta(0),
            fill_model="OHLC_TOUCH", approval_outcome="APPROVED", sample_end=sample_end)

    @classmethod
    def stress(cls, *, sample_end: datetime | None = None) -> "ExecutionScenario":
        return cls(scenario_id="E2", label="Stress: preapproved bounded plan, partial size and higher costs",
            approval_mode="PREAPPROVED_ARMED", approval_delay=timedelta(0),
            fill_model="OHLC_TOUCH", approval_outcome="APPROVED",
            fee_multiplier=D(2), spread_slippage_multiplier=D(3), fill_fraction=D("0.5"),
            sample_end=sample_end)

    @classmethod
    def delayed_stress(cls, *, sample_end: datetime | None = None) -> "ExecutionScenario":
        return cls(scenario_id="E2", label="Stress: 15-second human delay after trigger",
            approval_mode="HUMAN_DELAY", approval_delay=timedelta(seconds=15),
            fill_model="OHLC_TOUCH", approval_outcome="APPROVED", fee_multiplier=D(2),
            spread_slippage_multiplier=D(3), fill_fraction=D("0.5"), sample_end=sample_end)


class SimulatedEvent(Contract):
    event_id: str
    event_type: str
    at: datetime
    symbol: str
    details: dict[str, object] = Field(default_factory=dict)


class ScenarioOutcome(Contract):
    schema_version: Literal["c04.scenario-outcome.v1"] = "c04.scenario-outcome.v1"
    evidence_class: Literal["NO_EXECUTION_POLICY_TRUTH", "MODELLED_EXECUTION", "SYNTHETIC_MODELLED_EXECUTION"]
    scenario_id: Literal["E0", "E1", "E2"]
    decision_id: str
    symbol: str
    status: Literal["NO_TRADE", "REJECTED", "EXPIRED", "MISSED_ENTRY", "UNFILLED", "TARGET_LEG_INFEASIBLE", "FLAT", "UNRESOLVED_AT_SAMPLE_END"]
    fill_fidelity: Literal["NONE", "BAR_APPROX"]
    filled_quantity: D = D(0)
    first_fill_at: datetime | None = None
    initial_modeled_risk_usdt: D | None = None
    realized_pnl_usdt: D = D(0)
    unrealized_pnl_usdt: D = D(0)
    realized_net_r: D | None = None
    mark_to_market_net_r: D | None = None
    fees_usdt: D = D(0)
    spread_slippage_usdt: D = D(0)
    funding_usdt: D = D(0)
    exit_events: tuple[SimulatedEvent, ...] = ()
    optimistic_bound_net_r: D | None = None
    reasons: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()


def _floor_step(quantity: D, step: D) -> D:
    if step <= 0:
        return D(0)
    return (quantity / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _event(decision: ResearchDecision, kind: str, at: datetime, **details) -> SimulatedEvent:
    from astrabot.data.models import stable_id
    return SimulatedEvent(event_id=stable_id("c04.sim-event.v1", decision.decision_id, kind, at, details),
        event_type=kind, at=at, symbol=decision.symbol, details=details)


def _pnl(side: str, entry: D, exit_price: D, quantity: D) -> D:
    return (exit_price-entry)*quantity if side == "LONG" else (entry-exit_price)*quantity


def simulate_decision(
    decision: ResearchDecision,
    data: SymbolData,
    *,
    scenario: ExecutionScenario,
    profile: CostProfile,
    funding: tuple[FundingObservation, ...] = (),
    evidence_class: Literal["MODELLED_EXECUTION", "SYNTHETIC_MODELLED_EXECUTION"] = "MODELLED_EXECUTION",
    adverse_first: bool = True,
) -> ScenarioOutcome:
    """Apply a named counterfactual to one admitted C03 candidate.

    A bar must begin after the assumed arrival time; a bar touch is only a
    modeled fill and never venue evidence. Stop/target collisions use adverse
    ordering for the reported outcome. An optimistic bound is calculated
    separately when the same bar is ambiguous.
    """
    from astrabot.data.models import stable_id

    if decision.decision != "RESEARCH_CANDIDATE" or decision.economics is None or decision.geometry is None:
        return ScenarioOutcome(evidence_class="NO_EXECUTION_POLICY_TRUTH", scenario_id=scenario.scenario_id,
            decision_id=decision.decision_id, symbol=decision.symbol, status="NO_TRADE",
            fill_fidelity="NONE", reasons=decision.rejection_reason_codes or ("NOT_A_RESEARCH_CANDIDATE",),
            caveats=("A C03 candidate is not an approval or observed fill.",))
    if scenario.scenario_id == "E0" or scenario.fill_model == "NONE":
        return ScenarioOutcome(evidence_class="NO_EXECUTION_POLICY_TRUTH", scenario_id="E0",
            decision_id=decision.decision_id, symbol=decision.symbol, status="UNFILLED",
            fill_fidelity="NONE", reasons=("NO_OWNER_APPROVAL_OR_OBSERVED_FILL",),
            caveats=("E0 claims no owner approval and no exchange execution.",))
    if scenario.approval_outcome == "REJECTED":
        return ScenarioOutcome(evidence_class="MODELLED_EXECUTION", scenario_id=scenario.scenario_id,
            decision_id=decision.decision_id, symbol=decision.symbol, status="REJECTED",
            fill_fidelity="NONE", reasons=("HYPOTHETICAL_APPROVAL_REJECTED",))
    if scenario.approval_outcome == "NO_RESPONSE":
        return ScenarioOutcome(evidence_class="MODELLED_EXECUTION", scenario_id=scenario.scenario_id,
            decision_id=decision.decision_id, symbol=decision.symbol, status="EXPIRED",
            fill_fidelity="NONE", reasons=("HYPOTHETICAL_APPROVAL_NO_RESPONSE",))
    if data.metadata is None or data.metadata.quantity_step is None or data.metadata.price_tick is None:
        return ScenarioOutcome(evidence_class="MODELLED_EXECUTION", scenario_id=scenario.scenario_id,
            decision_id=decision.decision_id, symbol=decision.symbol, status="UNFILLED",
            fill_fidelity="NONE", reasons=("EXCHANGE_FILTERS_UNAVAILABLE",))
    deadline = decision.trigger_submit_deadline
    if deadline is None:
        return ScenarioOutcome(evidence_class="MODELLED_EXECUTION", scenario_id=scenario.scenario_id,
            decision_id=decision.decision_id, symbol=decision.symbol, status="EXPIRED",
            fill_fidelity="NONE", reasons=("TRIGGER_SUBMIT_DEADLINE_MISSING",))
    arrival = max(decision.as_of + timedelta(microseconds=1),
                  decision.earliest_hypothetical_entry_at or decision.as_of) + scenario.approval_delay
    if arrival > deadline:
        return ScenarioOutcome(evidence_class="MODELLED_EXECUTION", scenario_id=scenario.scenario_id,
            decision_id=decision.decision_id, symbol=decision.symbol, status="MISSED_ENTRY",
            fill_fidelity="NONE", reasons=("APPROVAL_DELAY_EXCEEDS_10S_TRIGGER_DEADLINE",),
            caveats=("The deadline was not relaxed to manufacture a fill.",))
    if arrival > decision.expires_at:
        return ScenarioOutcome(evidence_class="MODELLED_EXECUTION", scenario_id=scenario.scenario_id,
            decision_id=decision.decision_id, symbol=decision.symbol, status="EXPIRED",
            fill_fidelity="NONE", reasons=("APPROVAL_DELAY_EXCEEDS_PROPOSAL_EXPIRY",))
    reporting_cutoff = scenario.sample_end or max(
        (b.available_at for b in data.candles_5m), default=deadline)
    bars = sorted((b for b in data.candles_5m if b.symbol == decision.symbol
        and b.instrument_id == decision.instrument_id and b.available_at <= reporting_cutoff
        and b.open_time >= arrival and b.open_time <= min(decision.expires_at, arrival + scenario.ioc_ttl)
        and b.confirmed_at(max(reporting_cutoff, b.available_at))),
        key=lambda b: (b.open_time, b.source_record_id))
    bound = decision.entry_max if decision.side == "LONG" else decision.entry_min
    if bound is None or bound <= 0:
        return ScenarioOutcome(evidence_class="MODELLED_EXECUTION", scenario_id=scenario.scenario_id,
            decision_id=decision.decision_id, symbol=decision.symbol, status="UNFILLED",
            fill_fidelity="NONE", reasons=("FROZEN_ADVERSE_ENTRY_BOUND_MISSING",))
    entry_bar = None
    for bar in bars:
        if scenario.fill_model == "OHLC_TOUCH":
            touched = bar.low <= bound if decision.side == "LONG" else bar.high >= bound
        else:
            touched = bar.close <= bound if decision.side == "LONG" else bar.close >= bound
        if touched:
            entry_bar = bar
            break
    if entry_bar is None:
        return ScenarioOutcome(evidence_class="MODELLED_EXECUTION", scenario_id=scenario.scenario_id,
            decision_id=decision.decision_id, symbol=decision.symbol, status="UNFILLED",
            fill_fidelity="BAR_APPROX", reasons=("NO_POST_ARRIVAL_BAR_SUPPORTS_FILL",),
            caveats=("OHLC bars cannot establish a genuine IOC queue fill.",))

    entry = bound  # worst permitted adverse price; entry spread is already inside this bound
    step = data.metadata.quantity_step
    proposed = decision.economics.proposed_quantity
    quantity = _floor_step(proposed * scenario.fill_fraction, step)
    min_qty = data.metadata.minimum_quantity or D(0)
    min_notional = data.metadata.minimum_notional or D(0)
    if quantity <= 0 or quantity < min_qty or quantity * entry < min_notional:
        return ScenarioOutcome(evidence_class="MODELLED_EXECUTION", scenario_id=scenario.scenario_id,
            decision_id=decision.decision_id, symbol=decision.symbol, status="UNFILLED",
            fill_fidelity="BAR_APPROX", reasons=("SIMULATED_FILL_BELOW_EXCHANGE_MINIMUMS",))
    targets = decision.geometry.targets
    first_leg = _floor_step(quantity * targets[0].fraction, step)
    legs = [first_leg, quantity-first_leg]
    for q, target in zip(legs, targets):
        if q <= 0 or q < min_qty or q * target.price < min_notional:
            return ScenarioOutcome(evidence_class="MODELLED_EXECUTION", scenario_id=scenario.scenario_id,
                decision_id=decision.decision_id, symbol=decision.symbol, status="TARGET_LEG_INFEASIBLE",
                fill_fidelity="BAR_APPROX", filled_quantity=quantity, first_fill_at=entry_bar.open_time,
                reasons=("ROUNDED_PARTIAL_TARGET_BELOW_MINIMUM",),
                caveats=("The actual simulated filled quantity, not proposed quantity, was rounded.",))

    sign = D(1) if decision.side == "LONG" else D(-1)
    stop = decision.geometry.original_stop
    distance = sign * (entry-stop)
    if distance <= 0:
        return ScenarioOutcome(evidence_class="MODELLED_EXECUTION", scenario_id=scenario.scenario_id,
            decision_id=decision.decision_id, symbol=decision.symbol, status="UNFILLED",
            fill_fidelity="BAR_APPROX", reasons=("STOP_WRONG_SIDE_OF_ADVERSE_FILL",))
    loss_cost = decision.economics.loss_cost_per_unit
    initial_risk = quantity * (distance + loss_cost)
    entry_fee = entry * quantity * profile.entry_fee_rate * scenario.fee_multiplier
    realized = -entry_fee
    fees = entry_fee
    friction = D(0)
    funding_total = D(0)
    remaining = quantity
    events: list[SimulatedEvent] = []
    first_fill = entry_bar.open_time  # earliest possible point in the OHLC interval; conservative timer
    flatten_at = first_fill + timedelta(hours=11, minutes=55)
    hard_at = first_fill + timedelta(hours=12)
    proxy_exposure_quantity_seconds = D(0)
    proxy_exposure_cursor = first_fill

    def accrue_proxy_exposure(at: datetime) -> None:
        nonlocal proxy_exposure_quantity_seconds, proxy_exposure_cursor
        if at <= proxy_exposure_cursor:
            return
        elapsed = D(str((at-proxy_exposure_cursor).total_seconds()))
        proxy_exposure_quantity_seconds += remaining * elapsed
        proxy_exposure_cursor = at

    sample_end = reporting_cutoff
    exit_bars = [b for b in sorted(data.candles_5m, key=lambda b: b.open_time)
        if b.open_time > entry_bar.open_time and b.available_at <= (sample_end or datetime.max.replace(tzinfo=timezone.utc))
        and b.open_time >= first_fill]
    exit_events: list[tuple[Candle, int, D]] = []
    ambiguous = False
    settled_funding = sorted((f for f in funding if f.is_settled
        and first_fill < f.funding_time and f.available_at <= f.funding_time),
        key=lambda f: (f.funding_time, f.observation_id))
    funding_index = 0
    for bar in exit_bars:
        accrue_proxy_exposure(bar.open_time)
        timer_due = bar.open_time >= hard_at or bar.open_time >= flatten_at
        # Timer exits are modeled at bar open; other OHLC exits are only
        # resolved by bar availability, so a settlement inside that bar is
        # conservatively charged before the modeled exit.
        funding_cutoff = bar.open_time if timer_due else bar.available_at
        while funding_index < len(settled_funding) and settled_funding[funding_index].funding_time <= funding_cutoff:
            observation = settled_funding[funding_index]
            charge = sign * observation.funding_rate * entry * remaining
            funding_total += charge
            realized -= charge
            events.append(_event(decision, "FUNDING_SETTLEMENT", observation.funding_time,
                rate=str(observation.funding_rate), remaining_quantity=str(remaining),
                signed_debit_usdt=str(charge), source_id=observation.observation_id))
            funding_index += 1
        if timer_due:
            accrue_proxy_exposure(bar.open_time)
            px = bar.open
            q = remaining
            realized += _pnl(decision.side, entry, px, q)
            fee = px*q*profile.ordinary_exit_fee_rate*scenario.fee_multiplier
            fees += fee
            realized -= fee
            flatten_kind = "FORCED_FLATTEN_12H_HARD_LIMIT" if bar.open_time >= hard_at else "FORCED_FLATTEN_11H55"
            events.append(_event(decision, flatten_kind, bar.open_time,
                                 quantity=str(q), price=str(px), hard_limit=bar.open_time >= hard_at))
            remaining = D(0)
            break
        stop_hit = bar.low <= stop if decision.side == "LONG" else bar.high >= stop
        hit_targets = [i for i, target in enumerate(targets)
                       if (bar.high >= target.price if decision.side == "LONG" else bar.low <= target.price)
                       and legs[i] > 0]
        if stop_hit and hit_targets:
            ambiguous = True
            if adverse_first:
                hit_targets = []
        if stop_hit and not hit_targets:
            accrue_proxy_exposure(bar.available_at)
            trigger = min(stop, bar.open) if decision.side == "LONG" else max(stop, bar.open)
            stop_cost = (profile.stop_spread_per_unit + profile.stop_slippage_per_unit) * scenario.spread_slippage_multiplier
            px = trigger - stop_cost if decision.side == "LONG" else trigger + stop_cost
            q = remaining
            realized += _pnl(decision.side, entry, px, q)
            fee = px*q*profile.stop_exit_fee_rate*scenario.fee_multiplier
            fees += fee
            friction += stop_cost*q
            realized -= fee
            realized -= stop_cost*q
            events.append(_event(decision, "STOP", bar.available_at, quantity=str(q), price=str(px),
                                 same_bar_ambiguity=ambiguous, adverse_first=adverse_first))
            remaining = D(0)
            break
        for index in hit_targets:
            accrue_proxy_exposure(bar.available_at)
            q = legs[index] if index < len(legs)-1 else remaining
            q = min(q, remaining)
            target = targets[index]
            px = target.price
            exit_cost = (profile.ordinary_exit_spread_per_unit + profile.ordinary_exit_slippage_per_unit) * scenario.spread_slippage_multiplier
            effective_px = px-exit_cost if decision.side == "LONG" else px+exit_cost
            realized += _pnl(decision.side, entry, effective_px, q)
            fee = effective_px*q*profile.ordinary_exit_fee_rate*scenario.fee_multiplier
            fees += fee
            friction += exit_cost*q
            realized -= fee
            events.append(_event(decision, "TP1" if index == 0 else "TP2", bar.available_at,
                                 quantity=str(q), price=str(effective_px), same_bar_ambiguity=ambiguous))
            remaining -= q
            legs[index] = D(0)
            if remaining <= 0:
                remaining = D(0)
                break
        if remaining <= 0:
            break
    if remaining > 0:
        eligible_marks = [b for b in sorted(data.candles_5m, key=lambda b: b.open_time)
            if b.open_time > entry_bar.open_time and b.available_at <= (sample_end or datetime.max.replace(tzinfo=timezone.utc))]
        if eligible_marks:
            mark = eligible_marks[-1].close
            unrealized = _pnl(decision.side, entry, mark, remaining)
        else:
            unrealized = D(0)
    else:
        unrealized = D(0)
    # Funding observations are used only at a known settlement instant. When
    # absent, the explicitly declared max-hold proxy is prorated by time held.
    terminal_at = (events[-1].at if remaining == 0 and events else
        (exit_bars[-1].available_at if exit_bars else first_fill))
    if remaining > 0:
        accrue_proxy_exposure(terminal_at)
    while funding_index < len(settled_funding) and settled_funding[funding_index].funding_time <= terminal_at:
        observation = settled_funding[funding_index]
        charge = sign * observation.funding_rate * entry * remaining
        funding_total += charge
        realized -= charge
        events.append(_event(decision, "FUNDING_SETTLEMENT", observation.funding_time,
            rate=str(observation.funding_rate), remaining_quantity=str(remaining),
            signed_debit_usdt=str(charge), source_id=observation.observation_id))
        funding_index += 1
    if not settled_funding and scenario.funding_mode == "DECLARED_MAX_HOLD_PROXY":
        exposure = min(quantity, proxy_exposure_quantity_seconds / D(43200))
        funding_total = profile.funding_per_unit * exposure
        realized -= funding_total
        events.append(_event(decision, "DECLARED_MAX_HOLD_FUNDING_PROXY", terminal_at,
            quantity_seconds=str(proxy_exposure_quantity_seconds),
            equivalent_12h_quantity=str(exposure), signed_debit_usdt=str(funding_total)))
    mark_net = realized + unrealized
    flat = remaining == 0
    if flat:
        realized_net_r = realized / initial_risk if initial_risk else None
        mark_net_r = realized_net_r
        status = "FLAT"
    else:
        realized_net_r = None
        mark_net_r = mark_net / initial_risk if initial_risk else None
        status = "UNRESOLVED_AT_SAMPLE_END"
        events.append(_event(decision, "SAMPLE_END_MARK", terminal_at,
                             remaining_quantity=str(remaining), unrealized_pnl_usdt=str(unrealized)))
    optimistic_bound = None
    if ambiguous and adverse_first:
        optimistic = simulate_decision(decision, data, scenario=scenario, profile=profile,
            funding=funding, evidence_class=evidence_class, adverse_first=False)
        optimistic_bound = optimistic.realized_net_r or optimistic.mark_to_market_net_r
    return ScenarioOutcome(evidence_class=evidence_class, scenario_id=scenario.scenario_id,
        decision_id=decision.decision_id, symbol=decision.symbol, status=status,
        fill_fidelity="BAR_APPROX", filled_quantity=quantity, first_fill_at=first_fill,
        initial_modeled_risk_usdt=initial_risk, realized_pnl_usdt=realized,
        unrealized_pnl_usdt=unrealized, realized_net_r=realized_net_r,
        mark_to_market_net_r=mark_net_r, fees_usdt=fees, spread_slippage_usdt=friction,
        funding_usdt=funding_total, exit_events=tuple(events), optimistic_bound_net_r=optimistic_bound,
        caveats=("OHLC bar touch/close is a model assumption, not an observed IOC fill.",
                 "Entry spread/adverse movement is embedded once at the frozen adverse limit.",
                 "The first-fill clock uses the earliest point in the fill bar.",
                 "The profile funding fallback is a declared quantity-time proxy, not historical funding.",
                 "A funding settlement within an OHLC exit bar is charged before that modeled bar exit."))


class PortfolioLedger(Contract):
    """Synthetic account reservations enforcing the v1.5 portfolio ceilings."""
    model_config = ConfigDict(frozen=False)
    equity_usdt: D
    daily_start_equity_usdt: D
    current_day: str | None = None
    realized_pnl_today_usdt: D = D(0)
    halted: bool = False
    reservations: dict[str, dict[str, str]] = Field(default_factory=dict)
    closed_symbols: tuple[str, ...] = ()

    def admit(self, decision: ResearchDecision, *, as_of: datetime) -> tuple[bool, str | None]:
        if decision.decision != "RESEARCH_CANDIDATE" or decision.economics is None:
            return False, "NOT_A_RESEARCH_CANDIDATE"
        day = as_of.astimezone(timezone.utc).date().isoformat()
        if self.current_day != day:
            self.current_day = day
            self.daily_start_equity_usdt = self.equity_usdt
            self.realized_pnl_today_usdt = D(0)
            self.halted = False
        if self.halted:
            return False, "DAILY_UTC_ENTRY_HALT"
        active = self.reservations
        if len(active) >= 2:
            return False, "MAX_SIMULTANEOUS_POSITIONS"
        if any(row["symbol"] == decision.symbol for row in active.values()):
            return False, "SYMBOL_ALREADY_RESERVED"
        risk = decision.economics.proposed_modeled_loss_usdt
        risk_cap = self.equity_usdt * D("0.0025")
        aggregate = sum(D(row["risk_usdt"]) for row in active.values())
        if risk > risk_cap:
            return False, "PER_TRADE_RISK_CAP"
        if aggregate + risk > self.equity_usdt * D("0.005"):
            return False, "AGGREGATE_RISK_CAP"
        quantity = decision.economics.proposed_quantity
        price = decision.entry_max if decision.side == "LONG" else decision.entry_min
        notional = quantity * (price or D(0))
        aggregate_notional = sum(D(row["notional_usdt"]) for row in active.values()) + notional
        if aggregate_notional > self.equity_usdt * 2 or aggregate_notional / 2 > self.equity_usdt:
            return False, "LEVERAGE_CAP"
        self.reservations[decision.decision_id] = {"symbol": decision.symbol,
            "risk_usdt": str(risk), "notional_usdt": str(notional), "side": decision.side}
        return True, None

    def release(self, decision_id: str, *, realized_pnl_usdt: D, at: datetime) -> None:
        row = self.reservations.pop(decision_id, None)
        if row is None:
            return
        self.equity_usdt += realized_pnl_usdt
        day = at.astimezone(timezone.utc).date().isoformat()
        if self.current_day != day:
            self.current_day = day
            self.daily_start_equity_usdt = self.equity_usdt-realized_pnl_usdt
            self.realized_pnl_today_usdt = D(0)
            self.halted = False
        self.realized_pnl_today_usdt += realized_pnl_usdt
        if self.realized_pnl_today_usdt <= -self.daily_start_equity_usdt*D("0.01"):
            self.halted = True

    def mark_to_market(self, *, unrealized_pnl_usdt: D, at: datetime) -> None:
        day = at.astimezone(timezone.utc).date().isoformat()
        if self.current_day != day:
            self.current_day = day
            self.daily_start_equity_usdt = self.equity_usdt
            self.realized_pnl_today_usdt = D(0)
            self.halted = False
        if self.realized_pnl_today_usdt + unrealized_pnl_usdt <= -self.daily_start_equity_usdt*D("0.01"):
            self.halted = True
