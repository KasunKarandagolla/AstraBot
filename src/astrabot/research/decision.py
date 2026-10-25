"""Frozen post-trigger geometry and cost admission. No trading authorization."""
from datetime import timedelta
from decimal import Decimal as D

from astrabot.contracts import Anchor, BoundedGeometry, FixedGeometry, Target
from astrabot.data.models import config_hash, stable_id
from astrabot.research.economics import evaluate_economics, profile_hash, rounded
from astrabot.research.levels import confirmed_swings
from astrabot.research.models import ResearchDecision, VERSIONS
from astrabot.research.policies import verify_setup_sources

MANAGEMENT = config_hash({"version": "c03.fixed-research.v1", "stops": "NEVER_WIDEN",
    "scale_ins": False, "flatten_after": "11h55m", "hold_limit": "12h",
    "optional_management": "UNQUALIFIED_DISABLED"})


def no_trade(*, strategy, side, context, source_snapshot_id, profile, dependencies,
             reasons, setup=None, **details):
    states = [context.readiness, *(d.readiness for d in dependencies if d.role != "RECORD_ONLY")]
    readiness = next((s for s in ("UNAVAILABLE", "DEGRADED", "COLD") if s in states),
                     "WARMING" if any(s != "READY" for s in states) else "READY")
    return ResearchDecision(decision_id=stable_id("c03.decision.v1", source_snapshot_id,
        strategy, side, setup.snapshot.setup_id if setup else None, reasons,
        profile_hash(profile), tuple(d.model_dump(mode="json") for d in dependencies), details),
        setup_id=setup.snapshot.setup_id if setup else None, strategy_id=strategy,
        strategy_version=VERSIONS[strategy], symbol=context.symbol, instrument_id=context.instrument_id,
        side=side, as_of=context.as_of, source_snapshot_id=source_snapshot_id,
        context_id=context.context_id, feature_refs=setup.feature_refs if setup else (context.context_id,),
        adverse_bound="BUY_MAX" if side == "LONG" else "SELL_MIN",
        management_policy_hash=MANAGEMENT, cost_profile_hash=profile_hash(profile),
        expires_at=context.as_of, readiness=readiness,
        dependencies=dependencies, rejection_reason_codes=tuple(dict.fromkeys(reasons)),
        decision="NO_TRADE", **details)


def build_decision(*, setup, data, context, source_snapshot_id, profile, account,
                   requested_quantity, dependencies):
    """One future IOC experiment with saved stop/targets and finite chase bounds."""
    base = dict(strategy=setup.strategy_id, side=setup.snapshot.side, context=context,
        source_snapshot_id=source_snapshot_id, profile=profile, dependencies=dependencies, setup=setup)
    bar = setup.confirmation_bar
    if setup.snapshot.state != "CONFIRMED" or bar is None:
        return no_trade(**base, reasons=("SETUP_NOT_CONFIRMED",))
    source_reasons = verify_setup_sources(setup, data, context.as_of)
    if source_reasons:
        return no_trade(**base, reasons=source_reasons)
    # Event clock, not scanner receipt time, limits post-trigger submission.
    deadline = min(bar.close_time+timedelta(seconds=10), setup.snapshot.expires_at)
    if context.as_of >= deadline:
        return no_trade(**base, reasons=("TRIGGER_SUBMIT_DEADLINE_EXPIRED",),
                        trigger_event_id=bar.source_record_id, trigger_submit_deadline=deadline)
    metadata, depth = data.metadata, data.depth
    if not metadata or not metadata.price_tick or not depth or depth.event_time <= bar.close_time:
        return no_trade(**base, reasons=("POST_CONFIRMATION_QUOTE_UNAVAILABLE",))
    side = setup.snapshot.side
    sign = D(1) if side == "LONG" else D(-1)
    tick = metadata.price_tick
    extreme = setup.levels[0] if setup.strategy_id == "T1" else setup.selected_extreme
    if extreme is None:
        return no_trade(**base, reasons=("FROZEN_STOP_ANCHOR_MISSING",))
    raw_stop = extreme.price-sign*D(".10")*setup.snapshot.frozen_atr
    if raw_stop <= 0:
        return no_trade(**base, reasons=("STOP_PRICE_INVALID",))
    stop = rounded(raw_stop, tick, up=side == "SHORT")
    reference_distance = sign*(bar.close-stop)
    if reference_distance <= 0:
        return no_trade(**base, reasons=("STOP_WRONG_SIDE",))
    chase = min(tick*2, D(".10")*setup.snapshot.frozen_atr, D(".05")*reference_distance)
    entry_min = rounded(bar.close-chase, tick, up=True)
    entry_max = rounded(bar.close+chase, tick, up=False)
    if entry_min <= 0 or entry_max < entry_min:
        return no_trade(**base, reasons=("ENTRY_TICK_WINDOW_INFEASIBLE",))
    quote = depth.asks[0].price if side == "LONG" else depth.bids[0].price
    if not entry_min <= quote <= entry_max:
        return no_trade(**base, reasons=("ENTRY_OUTSIDE_FROZEN_CHASE_BOUND",),
                        entry_min=entry_min, entry_max=entry_max, original_stop=stop)
    entry = entry_max if side == "LONG" else entry_min
    distance = sign*(entry-stop)
    if distance <= 0:
        return no_trade(**base, reasons=("STOP_WRONG_SIDE",))

    # Re-derive the inventory from source candles at the original formation
    # time. A caller cannot insert a claimed/unconfirmed price into a setup.
    causal_inventory = confirmed_swings(data.candles_1h, symbol=context.symbol,
        instrument_id=context.instrument_id, as_of=setup.snapshot.available_at)
    if setup.opposing_at_formation != causal_inventory:
        return no_trade(**base, reasons=("STRUCTURAL_INVENTORY_SOURCE_MISMATCH",))
    kind = "SWING_HIGH" if side == "LONG" else "SWING_LOW"
    opposing = sorted((x for x in causal_inventory if x.kind == kind and not x.invalidated
        and x.available_at <= setup.snapshot.available_at and sign*(x.price-entry) > 0),
        key=lambda x: (sign*(x.price-entry), x.available_at, x.level_id))
    target_ids = ()
    if setup.strategy_id == "T1":
        if not opposing:
            return no_trade(**base, reasons=("PRECONFIRMED_OPPOSING_TARGET_MISSING",))
        tp1 = rounded(entry+sign*distance, tick, up=side == "SHORT")
        tp2 = rounded(opposing[0].price, tick, up=side == "SHORT")
        targets = (Target(price=tp1, fraction=".4"), Target(price=tp2, fraction=".6"))
        target_ids = (opposing[0].level_id,)
    elif setup.strategy_id == "R1":
        midpoint = next(x for x in setup.levels if x.kind == "RANGE_MIDPOINT")
        far = next(x for x in setup.levels if x.kind == ("RANGE_HIGH" if side == "LONG" else "RANGE_LOW"))
        targets = tuple(Target(price=rounded(x.price, tick, up=side == "SHORT"), fraction=".5")
                        for x in (midpoint, far))
        target_ids = (midpoint.level_id, far.level_id)
    else:
        # The original 1/2R, 40/60 ladder is a bounded, predeclared formula.
        # No target extension is permitted to rescue its 1.6 gross payout.
        offset = stop-extreme.price
        bounded = BoundedGeometry(source_id=stable_id(*extreme.source_ids),
            permitted_anchor_type="CLOSED_RETEST_EXTREME", anchor_min=extreme.price,
            anchor_max=extreme.price, stop_offset=offset, max_stop_distance=distance,
            target_multiples=(D(1), D(2)), target_fractions=(D(".4"), D(".6")),
            minimum_scenario_net_rr="1.5", anchor_deadline=deadline)
        resolved = bounded.resolve(entry=entry, side=side,
            anchor=Anchor(anchor_id=extreme.level_id, source_event_id=stable_id(*extreme.source_ids),
                          price=extreme.price, available_at=extreme.available_at),
            anchor_type="CLOSED_RETEST_EXTREME", now=context.as_of)
        targets = resolved.targets
        target_ids = (stable_id("B1.original-ladder.v1", extreme.level_id, entry, stop),)
    geometry = FixedGeometry(original_stop=stop, targets=targets)
    details = dict(trigger_event_id=bar.source_record_id,
        earliest_hypothetical_entry_at=context.as_of+timedelta(microseconds=1),
        entry_min=entry_min, entry_max=entry_max, trigger_submit_deadline=deadline,
        geometry=geometry, original_stop=stop, targets=targets,
        original_anchor_ids=tuple(dict.fromkeys((*[a.anchor_id for a in setup.snapshot.anchors], extreme.level_id))),
        target_level_ids=target_ids)
    # Every leg must have a feasible route, even if an earlier target fills.
    route_inventory = confirmed_swings(data.candles_1h, symbol=context.symbol,
        instrument_id=context.instrument_id, as_of=context.as_of)
    obstacles = tuple(x.level_id for x in route_inventory if x.kind == kind and not x.invalidated
        if any(D(0) < sign*(x.price-entry) < sign*(t.price-entry) for t in targets))
    if obstacles:
        return no_trade(**base, reasons=("PRECONFIRMED_OBSTACLE_BLOCKS_TARGET_ROUTE",),
                        rejected_level_ids=obstacles, **details)
    econ, reasons = evaluate_economics(side=side, entry=entry, geometry=geometry,
        profile=profile, metadata=metadata, account=account, requested_quantity=requested_quantity,
        midpoint_screen=setup.strategy_id == "R1", notional_price=entry_max)
    details.update(economics=econ, scenario_net_rr=econ.scenario_net_rr if econ else None)
    if reasons:
        return no_trade(**base, reasons=reasons, **details)
    return ResearchDecision(decision_id=stable_id("c03.candidate.v1", setup.snapshot.setup_id,
        bar.source_record_id, source_snapshot_id, profile_hash(profile), geometry.model_dump_json(),
        account.model_dump_json(), str(requested_quantity)), setup_id=setup.snapshot.setup_id,
        strategy_id=setup.strategy_id, strategy_version=setup.snapshot.strategy_version,
        symbol=context.symbol, instrument_id=context.instrument_id, side=side,
        as_of=context.as_of, source_snapshot_id=source_snapshot_id, context_id=context.context_id,
        feature_refs=setup.feature_refs, adverse_bound="BUY_MAX" if side == "LONG" else "SELL_MIN",
        management_policy_hash=MANAGEMENT, cost_profile_hash=profile_hash(profile),
        expires_at=min(context.as_of+timedelta(seconds=90), setup.snapshot.expires_at),
        readiness="READY", dependencies=dependencies, rejection_reason_codes=(),
        decision="RESEARCH_CANDIDATE", **details)
