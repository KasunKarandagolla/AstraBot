"""C03 S03–S21: meaningful synthetic chronology and economic counterexamples."""
import ast
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest
from pydantic import ValidationError

from astrabot.contracts import FixedGeometry, Target, TradeAuthorizationV15, scenario_net_rr
from astrabot.research.context import evaluate_context
from astrabot.research.demo import START, IID, SYMBOL, account, candle, costs, market, reflect, roll_market
from astrabot.research.economics import evaluate_economics
from astrabot.research.engine import evaluate
from astrabot.research.models import CostProfile, ResearchState
from astrabot.research.policies import advance_setup, form_setup
from scripts.c03_research import c02_no_trade


def context(data, at):
    return evaluate_context(data, symbol=SYMBOL, instrument_id=IID, as_of=at)


def evaluate_one(data, at, *, strategy="T1", side="LONG", state=ResearchState(), profile=None, **kwargs):
    return evaluate(data, symbol=SYMBOL, instrument_id=IID, as_of=at, account=account(at),
        profile=profile or costs(), requested_quantity=D("10"), strategies=(strategy,), sides=(side,),
        state=state, **kwargs)


def flat_cost(c=".001"):
    return CostProfile(version="SYNTHETIC_EQUAL_ROUTE_COST_V1", evidence_ids=("SYNTHETIC_ONLY",),
        entry_fee_rate="0", ordinary_exit_fee_rate="0", stop_exit_fee_rate="0",
        ordinary_exit_spread_per_unit="0", ordinary_exit_slippage_per_unit=c,
        stop_spread_per_unit="0", stop_slippage_per_unit=c, funding_per_unit="0")


def t1_case(side="LONG", *, bad=False):
    at = START+timedelta(seconds=5)
    data = market(at, side=side)
    formed = evaluate_one(data, at, side=side)
    bar = candle(START, open="99.9", high="100.5", low="99.8", close="100.4")
    at2 = START+timedelta(minutes=5, seconds=5)
    later = roll_market(data, at2, extra=(bar,), side=side)
    return data, formed, later, at2, evaluate_one(later, at2, side=side,
        state=formed.state, profile=costs(expensive=bad))


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_s14_s21_t1_complete_snapshot_to_candidate(side):
    data, armed, later, at, result = t1_case(side)
    assert armed.emitted[0].rejection_reason_codes == ("SETUP_ARMED_AWAITING_FUTURE_BAR",)
    before, after = armed.state.setups[0], result.state.setups[0]
    decision = result.emitted[0]
    assert decision.decision == "RESEARCH_CANDIDATE", decision.rejection_reason_codes
    assert after.snapshot.state == "CONSUMED" and after.snapshot.consumed_by == decision.decision_id
    assert before.snapshot.anchors == after.snapshot.anchors
    assert before.snapshot.frozen_atr == after.snapshot.frozen_atr
    assert decision.adverse_bound == ("BUY_MAX" if side == "LONG" else "SELL_MIN")
    worst = decision.entry_max if side == "LONG" else decision.entry_min
    sign = 1 if side == "LONG" else -1
    assert sign*(worst-decision.original_stop) > 0
    assert all(sign*(t.price-worst) > 0 for t in decision.targets)
    assert decision.earliest_hypothetical_entry_at > at > after.confirmation_bar.close_time
    assert decision.trigger_submit_deadline == after.confirmation_bar.close_time+timedelta(seconds=10)
    assert decision.expires_at <= at+timedelta(seconds=90)
    assert decision.scenario_net_rr >= D("1.5")
    assert decision.economics.actual_filled_initial_modeled_risk_usdt is None
    assert decision.economics.execution_economics is None
    assert decision.economics.proposed_quantity <= 10


def test_s03_future_append_preserves_full_decision_bytes():
    _, armed, data, at, old = t1_case()
    future = candle(START+timedelta(minutes=5), open="100.4", high="150", low="99", close="140")
    extended = data.model_copy(update={"candles_5m": (*data.candles_5m, future)})
    replay = evaluate_one(extended, at, state=armed.state)
    assert old.model_dump_json() == replay.model_dump_json()


def test_s04_above_vwap_without_real_prior_cross_is_not_reclaim():
    at = START+timedelta(seconds=5)
    data = market(at)
    bars = list(data.candles_5m)
    bars[-3:] = [candle(b.open_time, open="100.1", high="100.4", low="99.9", close="100.3") for b in bars[-3:]]
    result = evaluate_one(data.model_copy(update={"candles_5m": tuple(bars)}), at)
    assert result.emitted[0].decision == "NO_TRADE"
    assert "T1_PRIOR_VWAP_CROSS_MISSING" in result.emitted[0].rejection_reason_codes


def test_s05_lower_later_extreme_never_moves_original_t1_stop():
    at = START+timedelta(seconds=5)
    data = market(at)
    setup, _ = form_setup("T1", data, context(data, at), "LONG", "snapshot")
    original = setup.snapshot.model_dump_json()
    bar = candle(START, open="99.9", high="100.5", low="99.4", close="100.4")
    later = roll_market(data, START+timedelta(minutes=5, seconds=5), extra=(bar,))
    new = advance_setup(setup, later, context(later, START+timedelta(minutes=5, seconds=5)))
    assert new.snapshot.anchors == setup.snapshot.anchors
    assert new.levels[0].price == D("99.6")
    assert setup.snapshot.model_dump_json() == original


def test_s06_midnight_reset_suspends_reclaim_without_invented_thesis_failure():
    at = START.replace(hour=23, minute=55, second=5)
    data = market(at)
    setup, reasons = form_setup("T1", data, context(data, at), "LONG", "snapshot")
    assert setup, reasons
    bar1 = candle(at.replace(second=0), open="99.9", high="100.3", low="99.8", close="99.9")
    bar2 = candle(at.replace(second=0)+timedelta(minutes=5), open="100", high="100.8", low="99.8", close="100.7")
    next_at = at+timedelta(minutes=10)
    later = roll_market(data, next_at, extra=(bar1, bar2))
    result = advance_setup(setup, later, context(later, next_at))
    assert result.snapshot.state == "ARMED"
    assert "T1_ROLLOVER_CONFIRMATION_SUSPENDED" in result.notes
    assert result.snapshot.anchors == setup.snapshot.anchors
    fresh, reasons = form_setup("T1", later, context(later, next_at), "LONG", "new")
    assert fresh is None and "T1_SESSION_ROLLOVER_UNQUALIFIED" in reasons


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_s20_t1_cost_stress_rejects_unchanged_geometry(side):
    _, _, _, _, result = t1_case(side, bad=True)
    decision = result.emitted[0]
    assert decision.decision == "NO_TRADE"
    assert "SCENARIO_NET_RR_BELOW_MINIMUM" in decision.rejection_reason_codes
    assert decision.geometry and decision.economics


def r1_case(side="LONG", *, confirm=True):
    at = START+timedelta(seconds=5)
    data = market(at, family="R1", side=side)
    formation = evaluate_one(data, at, strategy="R1", side=side)
    sweep = candle(START, open="96.4", high="96.5", low="95.8", close="96.2")
    at2 = at+timedelta(minutes=5)
    later = roll_market(data, at2, family="R1", side=side, extra=(sweep,))
    swept = evaluate_one(later, at2, strategy="R1", side=side, state=formation.state)
    confirmation = candle(START+timedelta(minutes=5), open="96.2", high="96.8", low="96.1",
                          close="96.6" if confirm else "96.3")
    at3 = at+timedelta(minutes=10)
    final = roll_market(later, at3, family="R1", side=side, extra=(confirmation,))
    result = evaluate_one(final, at3, strategy="R1", side=side, state=swept.state)
    return data, formation, later, swept, final, at3, result


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_s07_s08_r1_frozen_range_and_distinct_confirmation(side):
    data, armed, later, swept, final, at, result = r1_case(side)
    assert armed.state.setups and swept.state.setups[0].snapshot.state == "ARMED"
    setup = swept.state.setups[0]
    assert setup.selected_bar.source_record_id != result.emitted[0].trigger_event_id
    assert setup.levels == result.state.setups[0].levels == armed.state.setups[0].levels
    decision = result.emitted[0]
    assert decision.decision == "RESEARCH_CANDIDATE", decision.rejection_reason_codes
    assert decision.economics.midpoint_screen_net_rr >= D("1.5")
    assert tuple(t.fraction for t in decision.targets) == (D(".5"), D(".5"))
    duplicate = evaluate_one(later, at-timedelta(minutes=5), strategy="R1", side=side, state=swept.state)
    assert duplicate.state.setups[0].snapshot.state == "ARMED"
    assert not any(d.decision == "RESEARCH_CANDIDATE" for d in duplicate.emitted)


def test_s07_s09_r1_survives_hour_roll_and_ordinary_context_change():
    data, armed, _, _, _, _, _ = r1_case()
    setup = armed.state.setups[0]
    at = START+timedelta(minutes=5, seconds=5)
    sweep = candle(START, open="96.4", high="96.5", low="95.8", close="96.2")
    later = roll_market(data, at, family="R1", extra=(sweep,))
    ctx = context(later, at).model_copy(update={"classification": "TREND_DOWN", "balance": None})
    new = advance_setup(setup, later, ctx)
    assert new.selected_bar and new.levels == setup.levels
    # The price source's rolling hourly window can change without rewriting anchors.
    shifted = later.model_copy(update={"candles_1h": later.candles_1h[1:]})
    confirm = candle(START+timedelta(minutes=5), open="96.2", high="96.8", low="96.1", close="96.6")
    shifted = roll_market(shifted, at+timedelta(minutes=5), family="R1", extra=(confirm,))
    final = advance_setup(new, shifted, ctx.model_copy(update={"as_of": at+timedelta(minutes=5)}))
    assert final.snapshot.state == "CONFIRMED" and final.levels == setup.levels


def test_s09_r1_volume_breakout_is_not_balance_merely_because_bias_is_neutral():
    at = START+timedelta(seconds=5)
    data = market(at, family="R1")
    assert context(data, at).classification == "RANGE"
    four = tuple(candle(b.open_time, interval="4h", high="101", low="99", close="100")
                 for b in data.candles_4h)
    fifteen = list(data.candles_15m)
    fifteen[-1] = candle(fifteen[-1].open_time, interval="15m", high="111", low="99", close="110", volume="150")
    data = data.model_copy(update={"candles_4h": four, "candles_15m": tuple(fifteen)})
    ctx = context(data, at)
    assert ctx.bias == "NEUTRAL" and ctx.breakout is None
    assert "BALANCE_DISQUALIFYING_VOLUME_BREAKOUT" in ctx.balance.reason_codes
    result = evaluate_one(data, at, strategy="R1")
    assert result.emitted[0].decision == "NO_TRADE"
    assert "R1_STABLE_BALANCE_UNQUALIFIED" in result.emitted[0].rejection_reason_codes


def test_s07_actual_hourly_roll_changes_new_range_but_keeps_original_targets():
    at = START.replace(minute=55, second=5)
    data = market(at, family="R1")
    hourly = list(data.candles_1h)
    # The latest closed hour is excluded at formation, then enters the next
    # rolling prior-20 window. It must not move this setup's original high.
    hourly[-1] = hourly[-1].model_copy(update={"high": D("106")})
    data = data.model_copy(update={"candles_1h": tuple(hourly)})
    armed = evaluate_one(data, at, strategy="R1")
    sweep = candle(at.replace(second=0), open="96.4", high="96.5", low="95.8", close="96.2")
    later = roll_market(data, at+timedelta(minutes=5), family="R1", extra=(sweep,))
    assert context(later, at+timedelta(minutes=5)).balance.high == D("106")
    swept = evaluate_one(later, at+timedelta(minutes=5), strategy="R1", state=armed.state)
    confirmation = candle(at.replace(second=0)+timedelta(minutes=5), open="96.2", high="96.8", low="96.1", close="96.6")
    final = roll_market(later, at+timedelta(minutes=10), family="R1", extra=(confirmation,))
    result = evaluate_one(final, at+timedelta(minutes=10), strategy="R1", state=swept.state)
    decision = result.emitted[0]
    assert decision.decision == "RESEARCH_CANDIDATE", decision.rejection_reason_codes
    assert decision.targets[-1].price == D("104")
    assert result.state.setups[0].levels == armed.state.setups[0].levels


@pytest.mark.parametrize("negative", ["edge_touch", "breach", "failed_confirmation"])
def test_s20_r1_false_positive_rejections(negative):
    if negative == "failed_confirmation":
        result = r1_case(confirm=False)[-1]
        assert result.emitted[0].rejection_reason_codes == ("R1_CONFIRMATION_FAILED",)
        return
    at = START+timedelta(seconds=5)
    data = market(at, family="R1")
    armed = evaluate_one(data, at, strategy="R1")
    bar = candle(START, open="96.4", high="96.5", low="96" if negative == "edge_touch" else "95.8",
                 close="96.2" if negative == "edge_touch" else "95.9")
    later = roll_market(data, at+timedelta(minutes=5), family="R1", extra=(bar,))
    result = evaluate_one(later, at+timedelta(minutes=5), strategy="R1", state=armed.state)
    assert result.emitted[0].decision == "NO_TRADE"
    expected = "AWAITING_ORDERED_CONFIRMATION" if negative == "edge_touch" else "R1_RANGE_BREACH_WITHOUT_RECLAIM"
    assert expected in result.emitted[0].rejection_reason_codes


def b1_formation(side="LONG"):
    at = START+timedelta(seconds=5)
    raw = market(at)
    fifteen = list(raw.candles_15m)
    fifteen[-1] = candle(fifteen[-1].open_time, interval="15m", open="100.5", high="101.3",
                         low="100.4", close="101.2", volume="150")
    five = list(raw.candles_5m)
    five[-1] = candle(five[-1].open_time, open="101", high="101.3", low="100.9", close="101.2")
    data = raw.model_copy(update={"candles_15m": tuple(fifteen), "candles_5m": tuple(five)})
    if side == "SHORT":
        data = reflect(data)
    formed = evaluate_one(data, at, strategy="B1", side=side, profile=flat_cost())
    assert formed.state.setups, formed.emitted[0].rejection_reason_codes
    return data, formed


def b1_complete(side="LONG", *, retest_index=1, failure=False):
    data, formed = b1_formation(side)
    bars = []
    for i in range(1, retest_index):
        bars.append(candle(START+timedelta(minutes=5*(i-1)), open="101.4", high="101.6", low="101.3", close="101.5"))
    bars.append(candle(START+timedelta(minutes=5*(retest_index-1)), open="101.2", high="101.3", low="101.02", close="101.15"))
    at = START+timedelta(minutes=5*retest_index, seconds=5)
    later = roll_market(data, at, extra=bars, side=side)
    selected = evaluate_one(later, at, strategy="B1", side=side, profile=flat_cost(), state=formed.state)
    confirmation = candle(START+timedelta(minutes=5*retest_index), open="101.15", high="101.5",
                         low="100.7" if failure else "101.1", close="101.4")
    final_at = at+timedelta(minutes=5)
    final = roll_market(later, final_at, extra=(confirmation,), side=side)
    result = evaluate_one(final, final_at, strategy="B1", side=side, profile=flat_cost(), state=selected.state)
    return formed, selected, final, final_at, result


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
@pytest.mark.parametrize("retest_index", [1, 6])
def test_s10_s11_s12_b1_first_or_bar_six_retest_gets_exact_next_confirmation(side, retest_index):
    formed, selected, data, at, result = b1_complete(side, retest_index=retest_index)
    setup = selected.state.setups[0]
    assert setup.selected_bar.open_time == START+timedelta(minutes=5*(retest_index-1))
    assert setup.snapshot.state == "ARMED"
    assert setup.levels == formed.state.setups[0].levels
    assert result.emitted[0].decision == "RESEARCH_CANDIDATE", result.emitted[0].rejection_reason_codes
    assert result.emitted[0].economics.gross_price_r == D("1.6")
    assert result.emitted[0].research_status == "RESEARCH_ONLY"
    if retest_index == 6:
        assert context(data, at).classification != "BREAKOUT_EVENT"


def test_s11_no_retest_search_after_bar_six_and_no_revival():
    data, formed = b1_formation()
    bars = tuple(candle(START+timedelta(minutes=5*i), open="101.4", high="101.6", low="101.3", close="101.5") for i in range(6))
    at = START+timedelta(minutes=30, seconds=5)
    later = roll_market(data, at, extra=bars)
    expired = evaluate_one(later, at, strategy="B1", state=formed.state)
    assert expired.state.setups[0].snapshot.state == "EXPIRED"
    bar7 = candle(START+timedelta(minutes=30), open="101.2", high="101.3", low="101.02", close="101.15")
    later = roll_market(later, at+timedelta(minutes=5), extra=(bar7,))
    again = evaluate_one(later, at+timedelta(minutes=5), strategy="B1", state=expired.state)
    assert again.state.setups[0].snapshot.state == "EXPIRED"
    assert not any(d.decision == "RESEARCH_CANDIDATE" for d in again.emitted)


def test_s10_b1_first_retest_cannot_be_replaced_by_better_later_bar():
    data, formed = b1_formation()
    retest = candle(START, open="101.2", high="101.3", low="101.02", close="101.15")
    second = candle(START+timedelta(minutes=5), open="101.15", high="101.25", low="101", close="101.2")
    third = candle(START+timedelta(minutes=10), open="101.2", high="101.7", low="101.1", close="101.6")
    at = START+timedelta(minutes=15, seconds=5)
    later = roll_market(data, at, extra=(retest, second, third))
    result = evaluate_one(later, at, strategy="B1", state=formed.state)
    assert result.state.setups[0].selected_bar.source_record_id == retest.source_record_id
    assert result.state.setups[0].snapshot.state == "EXPIRED"
    assert "B1_CONFIRMATION_FAILED" in result.emitted[0].rejection_reason_codes


def test_s12_s20_b1_hard_penetration_survives_no_context_exception():
    *_, result = b1_complete(retest_index=6, failure=True)
    assert result.emitted[0].decision == "NO_TRADE"
    assert "B1_SAVED_PENETRATION_FAILURE" in result.emitted[0].rejection_reason_codes


@pytest.mark.parametrize("ratio,passes", [(".039999", True), (".04", True), (".040001", False)])
def test_s13_s16_exact_b1_equal_cost_boundary(ratio, passes):
    geometry = FixedGeometry(original_stop="90", targets=(Target(price="110", fraction=".4"), Target(price="120", fraction=".6")))
    data = market()
    econ, reasons = evaluate_economics(side="LONG", entry=D(100), geometry=geometry,
        profile=flat_cost(str(D(ratio)*10)), metadata=data.metadata, account=account(START), requested_quantity=D(10))
    assert econ.gross_price_r == D("1.6")
    assert (econ.scenario_net_rr >= D("1.5")) == passes
    assert ("SCENARIO_NET_RR_BELOW_MINIMUM" not in reasons) == passes


def test_s16_rounded_fractions_risk_and_leverage_only_reduce_quantity():
    data = market()
    geometry = FixedGeometry(original_stop="99", targets=(Target(price="102", fraction=".4"), Target(price="104", fraction=".6")))
    limited = account(START).model_copy(update={"pending_open_risk_usdt": D("49.1"),
        "pending_open_notional_usdt": D("19900"), "isolated_margin_available_usdt": D("40")})
    econ, reasons = evaluate_economics(side="LONG", entry=D(100), geometry=geometry, profile=flat_cost(".1"),
        metadata=data.metadata, account=limited, requested_quantity=D("9.997"))
    assert not reasons
    assert econ.proposed_quantity <= D(".8")
    assert econ.proposed_modeled_loss_usdt <= D(".9")
    assert all(q % data.metadata.quantity_step == 0 for q in econ.target_quantities)
    assert sum(econ.target_quantities) == econ.proposed_quantity
    assert econ.win_cost_per_unit == econ.loss_cost_per_unit == D(".1")
    assert econ.scenario_net_rr == scenario_net_rr(D("3.2"), D(1), D(".1"), D(".1"))


def test_s16_short_notional_uses_upper_bound_separately_from_adverse_lower_entry():
    _, armed, data, at, _ = t1_case("SHORT")
    limited = account(at).model_copy(update={"pending_open_notional_usdt": D("19900.40")})
    result = evaluate(data, symbol=SYMBOL, instrument_id=IID, as_of=at, account=limited,
        profile=costs(), requested_quantity=D(10), strategies=("T1",), sides=("SHORT",), state=armed.state)
    decision = result.emitted[0]
    assert decision.decision == "RESEARCH_CANDIDATE"
    assert decision.economics.proposed_quantity < D(1)
    assert limited.pending_open_notional_usdt+decision.entry_max*decision.economics.proposed_quantity <= limited.equity_usdt*2


def test_s15_no_fabricated_or_unconfirmed_inventory():
    _, armed, data, at, _ = t1_case()
    setup = armed.state.setups[0]
    fake = setup.opposing_at_formation[0].model_copy(update={"price": D("110")})
    tampered = setup.model_copy(update={"opposing_at_formation": (fake,)})
    result = evaluate_one(data, at, state=ResearchState(setups=(tampered,)))
    assert result.emitted[0].rejection_reason_codes == ("STRUCTURAL_INVENTORY_SOURCE_MISMATCH",)


@pytest.mark.parametrize("target_case", ["missing", "wrong_side", "obstructed"])
def test_s15_source_inventory_missing_wrong_side_or_nearer_obstacle(target_case):
    at = START+timedelta(seconds=5)
    data = market(at)
    rows = list(data.candles_1h)
    if target_case == "missing":
        pivot = rows[720]
        rows[720] = pivot.model_copy(update={"high": pivot.close+D("1.4")})
    elif target_case == "wrong_side":
        rows[720] = rows[720].model_copy(update={"high": D("100")})
    else:
        rows[740] = rows[740].model_copy(update={"high": D("101")})
    data = data.model_copy(update={"candles_1h": tuple(rows)})
    armed = evaluate_one(data, at)
    assert armed.state.setups, armed.emitted[0].rejection_reason_codes
    confirmation = candle(START, open="99.9", high="100.5", low="99.8", close="100.4")
    later = roll_market(data, at+timedelta(minutes=5), extra=(confirmation,))
    result = evaluate_one(later, at+timedelta(minutes=5), state=armed.state)
    expected = "PRECONFIRMED_OBSTACLE_BLOCKS_TARGET_ROUTE" if target_case == "obstructed" else "PRECONFIRMED_OPPOSING_TARGET_MISSING"
    assert result.emitted[0].decision == "NO_TRADE"
    assert expected in result.emitted[0].rejection_reason_codes


def test_s15_frozen_range_cannot_be_forged_with_matching_lifecycle_anchor():
    data, armed, _, _, final, at, _ = r1_case()
    setup = armed.state.setups[0]
    levels = tuple(x.model_copy(update={"price": D("110")}) if x.kind == "RANGE_HIGH" else x for x in setup.levels)
    anchors = tuple(x.model_copy(update={"price": levels[i].price}) for i, x in enumerate(setup.snapshot.anchors))
    tampered = setup.model_copy(update={"levels": levels, "snapshot": setup.snapshot.model_copy(update={"anchors": anchors})})
    result = evaluate_one(final, at, strategy="R1", state=ResearchState(setups=(tampered,)))
    assert result.emitted[0].rejection_reason_codes == ("FROZEN_RANGE_SOURCE_MISMATCH",)


def test_s14_late_detection_or_chase_cannot_retroactively_enter():
    _, armed, data, at, _ = t1_case()
    # Trigger's inclusive-close clock expires 1ms before the C02 availability
    # freshness window; this exercises the separate trigger deadline itself.
    late_at = at+timedelta(seconds=4, milliseconds=999)
    late = roll_market(data, late_at)
    result = evaluate_one(late, late_at, state=armed.state)
    assert result.emitted[0].rejection_reason_codes == ("TRIGGER_SUBMIT_DEADLINE_EXPIRED",)
    moved = data.model_copy(update={"depth": data.depth.model_copy(update={
        "bids": (data.depth.bids[0].model_copy(update={"price": D("100.49")}),),
        "asks": (data.depth.asks[0].model_copy(update={"price": D("100.51")}),)})})
    result = evaluate_one(moved, at, state=armed.state)
    assert result.emitted[0].rejection_reason_codes == ("ENTRY_OUTSIDE_FROZEN_CHASE_BOUND",)


def test_s17_overlapping_t1_b1_selects_one_symbol_candidate_by_spec_fallback():
    def step(data, at, state=ResearchState()):
        return evaluate(data, symbol=SYMBOL, instrument_id=IID, as_of=at, account=account(at),
            profile=flat_cost(), requested_quantity=D(10), strategies=("T1", "B1"),
            sides=("LONG",), state=state)
    at = START-timedelta(minutes=5)+timedelta(seconds=5)
    original = market(at)
    armed_t1 = step(original, at)
    assert any(s.strategy_id == "T1" for s in armed_t1.state.setups)
    breakout_bar = candle(START-timedelta(minutes=5), open="101.3", high="101.4", low="100.9", close="101.2")
    data = roll_market(original, START+timedelta(seconds=5), extra=(breakout_bar,))
    fifteen = list(data.candles_15m)
    fifteen[-1] = candle(START-timedelta(minutes=15), interval="15m", open="100.5", high="101.4",
                         low="100.4", close="101.2", volume="150")
    data = data.model_copy(update={"candles_15m": tuple(fifteen)})
    both_armed = step(data, START+timedelta(seconds=5), armed_t1.state)
    assert {s.strategy_id for s in both_armed.state.setups if s.snapshot.state == "ARMED"} == {"T1", "B1"}
    retest = candle(START, open="101.2", high="101.3", low="101.02", close="101.15")
    data = roll_market(data, START+timedelta(minutes=5, seconds=5), extra=(retest,))
    selected = step(data, START+timedelta(minutes=5, seconds=5), both_armed.state)
    confirm = candle(START+timedelta(minutes=5), open="101.15", high="101.5", low="101.1", close="101.4")
    data = roll_market(data, START+timedelta(minutes=10, seconds=5), extra=(confirm,))
    result = step(data, START+timedelta(minutes=10, seconds=5), selected.state)
    candidates = [d for d in result.emitted if d.decision == "RESEARCH_CANDIDATE"]
    assert len(candidates) == 1 and candidates[0].strategy_id == "B1"
    other = next(d for d in result.emitted if d.strategy_id == "T1")
    assert other.rejection_reason_codes == ("SYMBOL_CANDIDATE_NOT_SELECTED",)


def test_s17_consumed_setup_and_duplicate_scan_cannot_emit_second_candidate():
    _, armed, data, at, first = t1_case()
    restored = ResearchState.model_validate_json(first.state.model_dump_json())
    second = evaluate_one(data, at, state=restored)
    assert not any(x.decision == "RESEARCH_CANDIDATE" for x in second.emitted)
    assert second.state.setups[0].snapshot == first.state.setups[0].snapshot
    third = evaluate_one(data, at, state=second.state)
    assert not third.emitted
    with pytest.raises(ValidationError):
        first.emitted[0].original_stop = D(1)


@pytest.mark.parametrize("missing", ["oi", "events", "history"])
def test_s18_mandatory_missing_data_fails_closed(missing):
    at = START+timedelta(seconds=5)
    data = market(at)
    changes = {"open_interest": data.open_interest.model_copy(update={"unit_validated": False, "open_interest_notional_usdt": None})} if missing == "oi" else (
        {"event_clearance": None} if missing == "events" else {"candles_1h": data.candles_1h[-720:]})
    result = evaluate_one(data.model_copy(update=changes), at)
    assert result.emitted[0].decision == "NO_TRADE"
    assert result.emitted[0].rejection_reason_codes
    assert result.emitted[0].readiness != "READY"
    assert not result.state.setups


def test_s18_optional_unavailable_a03_and_cvd_stay_unavailable_without_blocking_t1():
    *_, result = t1_case()
    decision = result.emitted[0]
    assert decision.decision == "RESEARCH_CANDIDATE"
    for name in ("A01", "A03"):
        dependency = next(x for x in decision.dependencies if x.name == name)
        assert dependency.role == "RECORD_ONLY" and dependency.readiness == "UNAVAILABLE"


def test_s19_research_artifacts_have_no_approval_or_signed_writer_capability():
    *_, result = t1_case()
    decision = result.emitted[0]
    assert decision.executable is False
    with pytest.raises(ValidationError):
        TradeAuthorizationV15.model_validate_json(decision.model_dump_json())
    paths = Path("src/astrabot/research").glob("*.py")
    for path in paths:
        tree = ast.parse(path.read_text())
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any(x and (x.startswith("astrabot.execution") or "binance" in x or "requests" in x) for x in imports)
        assert not any(isinstance(n, ast.Name) and n.id == "TradeAuthorizationV15" for n in ast.walk(tree))


def test_s21_actual_c02_archive_reaches_no_trade_with_honest_missing_evidence():
    result = c02_no_trade()
    assert result["candle_count"] == 24
    assert result["retained_file_sha256"] == "73930ee78240d99a8184e5dedf808dbd998799c22fcc632732ffdc12dd465c1b"
    assert len(result["decisions"]) == 3
    assert all(d["decision"] == "NO_TRADE" and not d["executable"] for d in result["decisions"])
    assert all("METADATA_MISSING" in d["rejection_reason_codes"] for d in result["decisions"])
