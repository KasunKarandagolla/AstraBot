"""Small snapshot -> context -> persistent policy -> research decision facade."""
from datetime import timedelta
from decimal import Decimal as D

from astrabot.data.models import FeatureObservation, config_hash, stable_id
from astrabot.research.context import evaluate_context
from astrabot.research.decision import build_decision, no_trade
from astrabot.research.models import (
    CostProfile, Dependency, Evaluation, ResearchAccount, ResearchSetup, ResearchState,
)
from astrabot.research.policies import TERMINAL, advance_setup, form_setup
from astrabot.universe.eligibility import SymbolData, scan_universe


def point_in_time(data: SymbolData, as_of) -> SymbolData:
    """Exclude future observations before hashing or touching their status."""
    fields = {}
    for name in ("metadata", "ticker", "depth", "open_interest"):
        item = getattr(data, name)
        fields[name] = item if item and item.available_at <= as_of and item.event_time <= as_of else None
    for name in ("candles_5m", "candles_15m", "candles_1h", "candles_4h"):
        fields[name] = tuple(c for c in getattr(data, name) if c.confirmed_at(as_of))
    fields["spread_samples"] = tuple(s for s in data.spread_samples
        if s.available_at <= as_of and s.event_time <= as_of)
    fields["event_clearance"] = data.event_clearance if (
        data.event_clearance and data.event_clearance.as_of <= as_of) else None
    # Every selected value is copied from an already validated immutable
    # SymbolData instance. Re-validating hundreds or thousands of historical
    # candles through JSON on every replay timestamp changes no evidence and
    # dominates bounded multi-month archive runs.
    return data.model_copy(update=fields)


def evaluate(data: SymbolData, *, symbol: str, instrument_id: str, as_of,
             account: ResearchAccount, profile: CostProfile, requested_quantity: D,
             state: ResearchState = ResearchState(),
             optional_features: tuple[FeatureObservation, ...] = (),
             strategies: tuple[str, ...] = ("T1", "R1", "B1"),
             sides: tuple[str, ...] = ("LONG", "SHORT")) -> Evaluation:
    """Pure deterministic step; callers persist returned JSON between scans.

    CONSUMED means a single research candidate was emitted, never an order or
    approval was consumed. Replays must carry the saved state instead of
    repeatedly creating a new empty registry. No database or network is used.
    """
    data = point_in_time(data, as_of)
    state = ResearchState.model_validate_json(state.model_dump_json())
    account = ResearchAccount.model_validate_json(account.model_dump_json())
    profile = CostProfile.model_validate_json(profile.model_dump_json())
    optional = tuple(f for f in optional_features if f.available_at <= as_of and f.event_time <= as_of
        and f.symbol == symbol and f.instrument_id == instrument_id)
    source_id = stable_id("c03.snapshot.v1", symbol, instrument_id, as_of,
        config_hash(data.model_dump(mode="json")), tuple(f.observation_id for f in optional))
    context = evaluate_context(data, symbol=symbol, instrument_id=instrument_id, as_of=as_of)
    reference = data.depth.asks[0].price if data.depth else D(0)
    # C02 requires a positive diagnostic test notional even for an empty feed.
    # This floor enables missing-data reporting; it never supplies an entry
    # price or makes absent depth eligible.
    diagnostic_notional = max(D(1), requested_quantity*reference)
    universe = scan_universe({symbol: data}, as_of, diagnostic_notional).considered[0]
    dependencies = (
        Dependency(name="RESEARCH_ACCOUNT", role="MANDATORY", readiness="READY" if (
            account.reconciled and account.as_of <= as_of <= account.as_of+timedelta(seconds=60)) else "UNAVAILABLE",
            source_ids=(account.source_id,)),
        Dependency(name="C02_UNIVERSE", role="MANDATORY", readiness=universe.state,
                   source_ids=universe.reasons),
        Dependency(name="CONTEXT", role="MANDATORY", readiness=context.readiness,
                   source_ids=(context.context_id,)),
        Dependency(name="OI_VALIDATED_NOTIONAL", role="MANDATORY",
                   readiness=data.open_interest.readiness if data.open_interest and data.open_interest.unit_validated else "UNAVAILABLE",
                   source_ids=(data.open_interest.observation_id,) if data.open_interest else ()),
        Dependency(name="VERIFIED_EVENT_CLEARANCE", role="VETO",
                   readiness="READY" if data.event_clearance and data.event_clearance.state == "CLEAR" else "UNAVAILABLE",
                   source_ids=data.event_clearance.source_ids if data.event_clearance else ()),
        *(Dependency(name=family, role="RECORD_ONLY",
                      readiness=next((f.readiness for f in optional if f.feature_family == family), "UNAVAILABLE"),
                      source_ids=tuple(f.observation_id for f in optional if f.feature_family == family))
          for family in ("A01", "A03", "A04", "A05", "A06", "A08")),
    )
    safety = []
    if not universe.eligible:
        safety.extend(("C02_UNIVERSE_NOT_READY", *universe.reasons))
    if context.readiness != "READY":
        safety.extend(("MANDATORY_CONTEXT_UNAVAILABLE", *context.reason_codes))
    if context.classification == "EXTREME_VOLATILITY":
        safety.append("EXTREME_VOLATILITY_OR_LIQUIDITY_VETO")
    if not account.as_of <= as_of <= account.as_of+timedelta(seconds=60):
        safety.append("ACCOUNT_SNAPSHOT_STALE_OR_FUTURE")
    if requested_quantity <= 0:
        safety.append("REQUESTED_QUANTITY_INVALID")
    setups = list(state.setups)
    records = list(state.decisions)
    emitted = []
    pending_candidates = []

    def emit(decision):
        if all(x.decision_id != decision.decision_id for x in records):
            records.append(decision)
            emitted.append(decision)

    for strategy in strategies:
        if strategy not in ("T1", "R1", "B1"):
            raise ValueError("unknown research strategy")
        for side in sides:
            if side not in ("LONG", "SHORT"):
                raise ValueError("unknown side")
            base = dict(strategy=strategy, side=side, context=context, source_snapshot_id=source_id,
                        profile=profile, dependencies=dependencies)
            indices = [i for i, s in enumerate(setups) if s.strategy_id == strategy
                and s.snapshot.side == side and s.snapshot.symbol == symbol and s.instrument_id == instrument_id
                and s.snapshot.state not in TERMINAL]
            if len(indices) > 1:
                raise ValueError("multiple active setups for one strategy/side")
            index = indices[0] if indices else None
            setup = setups[index] if index is not None else None
            if setup and any(d.source_snapshot_id == source_id and d.setup_id == setup.snapshot.setup_id
                             for d in records):
                continue
            if safety:
                if setup and setup.snapshot.state in ("FORMING", "ARMED", "CONFIRMED"):
                    setup = setup.model_copy(update={"snapshot": setup.snapshot.advance(
                        "INVALIDATED", invalidation_reason=safety[0])})
                    setups[index] = setup
                emit(no_trade(**base, setup=setup, reasons=tuple(safety)))
                continue
            if setup:
                setup = advance_setup(setup, data, context)
                setups[index] = setup
                if setup.snapshot.state == "CONFIRMED":
                    decision = build_decision(setup=setup, data=data, context=context,
                        source_snapshot_id=source_id, profile=profile, account=account,
                        requested_quantity=requested_quantity, dependencies=dependencies)
                    if decision.decision == "RESEARCH_CANDIDATE":
                        pending_candidates.append((index, setup, decision))
                    else:
                        snapshot = setup.snapshot.advance("INVALIDATED",
                            invalidation_reason=decision.rejection_reason_codes[0])
                        setups[index] = ResearchSetup.model_validate_json(setup.model_copy(
                            update={"snapshot": snapshot}).model_dump_json())
                        emit(decision)
                else:
                    reasons = (setup.notes[-1],) if setup.snapshot.state in TERMINAL else (
                        "T1_ROLLOVER_CONFIRMATION_SUSPENDED" if "T1_ROLLOVER_CONFIRMATION_SUSPENDED" in setup.notes
                        else "AWAITING_ORDERED_CONFIRMATION",)
                    emit(no_trade(**base, setup=setup, reasons=reasons))
                continue
            setup, reasons = form_setup(strategy, data, context, side, source_id)
            if setup:
                if any(s.snapshot.setup_id == setup.snapshot.setup_id
                       or (s.snapshot.symbol == symbol and s.strategy_id == strategy
                           and s.snapshot.side == side
                           and setup.snapshot.formed_event_id in (
                               s.snapshot.formed_event_id, s.snapshot.confirmed_event_id)) for s in setups):
                    emit(no_trade(**base, setup=setup, reasons=("SETUP_EVENT_ALREADY_RECORDED",)))
                else:
                    setups.append(setup)
                    emit(no_trade(**base, setup=setup, reasons=("SETUP_ARMED_AWAITING_FUTURE_BAR",)))
            else:
                emit(no_trade(**base, reasons=reasons))
    # No qualified expectancy registry exists at C03. The specified fallback
    # selects the alphabetical strategy, then a stable side/setup tie-break.
    # A symbol can emit at most one research candidate per snapshot.
    for rank, (index, setup, decision) in enumerate(sorted(pending_candidates,
            key=lambda item: (item[2].strategy_id, item[2].side, item[2].setup_id))):
        if rank == 0:
            snapshot = setup.snapshot.advance("CONSUMED", consumed_by=decision.decision_id)
        else:
            decision = decision.model_copy(update={"decision": "NO_TRADE",
                "decision_id": stable_id("c03.not-selected.v1", decision.decision_id),
                "rejection_reason_codes": ("SYMBOL_CANDIDATE_NOT_SELECTED",)})
            snapshot = setup.snapshot.advance("INVALIDATED", invalidation_reason="SYMBOL_CANDIDATE_NOT_SELECTED")
        setups[index] = ResearchSetup.model_validate_json(setup.model_copy(update={"snapshot": snapshot}).model_dump_json())
        emit(decision)
    return Evaluation(state=ResearchState(setups=tuple(setups), decisions=tuple(records)), emitted=tuple(emitted))
