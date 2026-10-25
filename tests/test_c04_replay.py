"""Offline acceptance checks for C04's causal replay and counterfactual layer."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

from astrabot.data.models import binance_usdm_instrument_id
from astrabot.data.models import FundingObservation
from astrabot.research.engine import evaluate
from astrabot.research.replay import (
    derive_4h_from_1h, load_c02_panel, replay_panel,
)
from astrabot.research.simulation import ExecutionScenario, PortfolioLedger, simulate_decision
from astrabot.research.statistics import cluster_bootstrap, matched_controls, summarize
from astrabot.universe.eligibility import scan_universe
from astrabot.research.demo import START, account as demo_account, candle, costs as demo_costs, market, roll_market
from scripts.c04_replay import synthetic_execution_trace


ROOT = Path(__file__).resolve().parents[1]


def _synthetic_candidate():
    formed_at = START + timedelta(seconds=5)
    original = market(formed_at)
    kwargs = {"symbol": "ALTUSDT", "instrument_id": binance_usdm_instrument_id("ALTUSDT"),
        "requested_quantity": D("10"), "strategies": ("T1",), "sides": ("LONG",)}
    formation = evaluate(original, as_of=formed_at, account=demo_account(formed_at),
        profile=demo_costs(), **kwargs)
    confirmed_at = START + timedelta(minutes=5, seconds=5)
    confirmation = candle(START, open="99.9", high="100.5", low="99.8", close="100.4")
    data = roll_market(original, confirmed_at, extra=(confirmation,))
    result = evaluate(data, as_of=confirmed_at, account=demo_account(confirmed_at),
        profile=demo_costs(), state=formation.state, **kwargs)
    decision = next(d for d in result.emitted if d.decision == "RESEARCH_CANDIDATE")
    return decision, data


def test_c04_retained_manifest_checksums_and_source_limits():
    panel = load_c02_panel(ROOT / "research/c02_panel")
    assert set(panel.symbols) == {"BTCUSDT", "APEUSDT"}
    assert len(panel.symbols["BTCUSDT"].candles_1h) == 24
    assert panel.symbols["APEUSDT"].candles_1h == ()
    assert all(len(p["retained_input_sha256"]) == 64 for p in panel.partitions)
    assert all(p["availability_status"] == "OBSERVED_WITH_EXPLICIT_AVAILABILITY_PROXY"
               for p in panel.partitions)
    assert all(p["historical_listing_metadata"].startswith("UNAVAILABLE") for p in panel.partitions)
    assert all(p["could_be_known_at_replay_time"] == "UNVERIFIED" for p in panel.partitions)


def test_c04_full_funnel_is_capped_reproducible_and_fail_closed():
    panel = load_c02_panel(ROOT / "research/c02_panel")
    first = replay_panel(panel)
    second = replay_panel(panel)
    assert first["run_id"] == second["run_id"]
    assert first["output_manifest"] == second["output_manifest"]
    assert first["strict_decisions"] == second["strict_decisions"]
    assert first["funnel_events"] == second["funnel_events"]
    assert first["config"]["shortlist_limit"] <= 15
    assert first["funnel"]["symbols_discovered"] == 2
    assert first["funnel"]["symbols_with_source_coverage"] == 2
    assert first["funnel"]["symbols_eligible_latest"] == 0
    assert first["funnel"]["symbols_shortlisted_latest"] == 0
    assert first["funnel"]["strict_candidate_decisions"] == 0
    assert first["funnel"]["symbol_evaluation_windows"] == 48
    assert first["funnel"]["diagnostic_context_evaluations"] == 48
    assert first["modes"]["STRICT_POLICY_REPLAY"]["status"] == "BLOCKED_BY_DATA"
    assert first["modes"]["EXPLORATORY_SIGNAL_DIAGNOSTICS"]["mandatory_gates_bypassed"] == []
    assert first["statistics"]["market_time_block_bootstrap"]["ci95"] is None


def test_c04_dynamic_universe_rejects_a_not_yet_listed_symbol():
    as_of = START + timedelta(seconds=5)
    data = market(as_of)
    data = data.model_copy(update={"metadata": data.metadata.model_copy(update={
        "onboard_time": as_of + timedelta(days=1)})})
    universe = scan_universe({"ALTUSDT": data}, as_of, D("100"))
    row = universe.considered[0]
    assert not row.eligible
    assert "CONTRACT_NOT_YET_ONBOARDED_OR_ALREADY_DELIVERED" in row.reasons


def test_c04_4h_derivation_requires_complete_contiguous_utc_groups():
    data = market(START + timedelta(seconds=5))
    hourly = data.candles_1h
    group = next(tuple(hourly[i:i+4]) for i in range(len(hourly)-3)
        if hourly[i].open_time.hour % 4 == 0
        and len(hourly[i:i+4]) == 4
        and all(hourly[i+j].open_time - hourly[i+j-1].open_time == timedelta(hours=1)
                for j in range(1, 4)))
    derived = derive_4h_from_1h(group)
    assert len(derived) == 1
    bar = derived[0]
    assert bar.interval == "4h" and bar.fidelity == "BAR_DERIVED_APPROX"
    assert bar.open_time == group[0].open_time
    assert bar.open == group[0].open and bar.close == group[-1].close
    assert bar.high == max(x.high for x in group) and bar.low == min(x.low for x in group)
    assert bar.base_volume == sum((x.base_volume for x in group), D(0))
    assert bar.available_at == max(x.available_at for x in group)
    assert derive_4h_from_1h((group[0], group[2], group[3])) == ()


def test_c04_causal_prefix_and_source_state_survive_future_append():
    as_of = START + timedelta(seconds=5)
    data = market(as_of)
    future = candle(START + timedelta(minutes=5), open="100", high="110", low="90", close="109")
    extended = data.model_copy(update={"candles_5m": (*data.candles_5m, future)})
    account = demo_account(as_of)
    first = evaluate(data, symbol="ALTUSDT", instrument_id=binance_usdm_instrument_id("ALTUSDT"),
        as_of=as_of, account=account, profile=demo_costs(), requested_quantity=D("10"),
        strategies=("T1",), sides=("LONG",))
    extended_result = evaluate(extended, symbol="ALTUSDT", instrument_id=binance_usdm_instrument_id("ALTUSDT"),
        as_of=as_of, account=account, profile=demo_costs(), requested_quantity=D("10"),
        strategies=("T1",), sides=("LONG",))
    assert first.model_dump(mode="json") == extended_result.model_dump(mode="json")
    assert len(first.state.setups) == len(extended_result.state.setups)


def test_c04_execution_accounts_actual_partial_fill_and_separates_evidence():
    decision, snapshot = _synthetic_candidate()
    arrival = decision.earliest_hypothetical_entry_at
    assert arrival is not None
    entry_bar = candle(arrival, open="100.2", high="100.5", low="100.1", close="100.3")
    tp1_bar = candle(arrival + timedelta(minutes=5), open="100.3", high="101.5", low="100.2", close="101.3")
    tp2_bar = candle(arrival + timedelta(minutes=10), open="101.3", high="108.2", low="101.1", close="108.1")
    data = snapshot.model_copy(update={"candles_5m": tuple(sorted(
        (*snapshot.candles_5m, entry_bar, tp1_bar, tp2_bar), key=lambda b: b.open_time))})
    profile = demo_costs()
    e0 = simulate_decision(decision, data, scenario=ExecutionScenario.no_execution(), profile=profile)
    e1 = simulate_decision(decision, data,
        scenario=ExecutionScenario.conservative(sample_end=tp2_bar.available_at), profile=profile,
        evidence_class="SYNTHETIC_MODELLED_EXECUTION")
    e2 = simulate_decision(decision, data,
        scenario=ExecutionScenario.stress(sample_end=tp2_bar.available_at), profile=profile,
        evidence_class="SYNTHETIC_MODELLED_EXECUTION")
    late = simulate_decision(decision, data,
        scenario=ExecutionScenario.delayed_stress(sample_end=tp2_bar.available_at), profile=profile)
    assert e0.evidence_class == "NO_EXECUTION_POLICY_TRUTH" and e0.filled_quantity == 0
    assert e1.status == "FLAT" and e1.filled_quantity == D("10") and e1.fill_fidelity == "BAR_APPROX"
    exits = [e for e in e1.exit_events if e.event_type in {"TP1", "TP2"}]
    assert [e.event_type for e in exits] == ["TP1", "TP2"]
    funding_proxy = next(e for e in e1.exit_events
        if e.event_type == "DECLARED_MAX_HOLD_FUNDING_PROXY")
    assert D(funding_proxy.details["quantity_seconds"]) == D("7800")
    # Hand calculation: 48.92 gross, 0.02 modeled exit friction, 0.20573 fees,
    # and 0.000180555... proxy after the 4-unit partial exit.
    expected_pnl = D("48.92") - D("0.02") - D("0.20573") - D("0.0001805555555555555555555555556")
    assert abs(e1.realized_pnl_usdt - expected_pnl) < D("0.000000000000001")
    assert e1.initial_modeled_risk_usdt == D("8.849980")
    assert e1.realized_net_r == e1.realized_pnl_usdt / e1.initial_modeled_risk_usdt
    assert e2.filled_quantity == D("5.0")
    assert sum(D(e.details["quantity"]) for e in e2.exit_events
        if "quantity" in e.details) == D("5.0")
    assert late.status == "MISSED_ENTRY"
    assert "APPROVAL_DELAY_EXCEEDS_10S_TRIGGER_DEADLINE" in late.reasons
    assert e1.evidence_class == "SYNTHETIC_MODELLED_EXECUTION"


def test_c04_same_bar_is_adverse_first_and_reports_optimistic_bound():
    decision, snapshot = _synthetic_candidate()
    arrival = decision.earliest_hypothetical_entry_at
    entry_bar = candle(arrival, open="100.2", high="100.5", low="100.1", close="100.3")
    collision = candle(arrival + timedelta(minutes=5), open="100.3", high="101.5",
        low=str(decision.geometry.original_stop - D("0.1")), close="101.3")
    later = candle(arrival + timedelta(minutes=10), open="101.3", high="108.2", low="101.1", close="108.1")
    data = snapshot.model_copy(update={"candles_5m": tuple(sorted(
        (*snapshot.candles_5m, entry_bar, collision, later), key=lambda b: b.open_time))})
    result = simulate_decision(decision, data,
        scenario=ExecutionScenario.conservative(sample_end=later.available_at),
        profile=demo_costs(), evidence_class="SYNTHETIC_MODELLED_EXECUTION")
    assert result.status == "FLAT"
    assert result.exit_events[0].event_type == "STOP"
    assert result.exit_events[0].details["same_bar_ambiguity"] is True
    assert result.realized_net_r < 0
    assert result.optimistic_bound_net_r is not None
    assert result.optimistic_bound_net_r > result.realized_net_r


def test_c04_settled_funding_inside_exit_bar_charges_remaining_quantity():
    decision, snapshot = _synthetic_candidate()
    arrival = decision.earliest_hypothetical_entry_at
    assert arrival is not None
    entry_bar = candle(arrival, open="100.2", high="100.5", low="100.1", close="100.3")
    tp1_bar = candle(arrival + timedelta(minutes=5), open="100.3", high="101.5", low="100.2", close="101.3")
    tp2_bar = candle(arrival + timedelta(minutes=10), open="101.3", high="108.2", low="101.1", close="108.1")
    settlement_time = arrival + timedelta(minutes=12)
    funding = FundingObservation(symbol=decision.symbol, instrument_id=decision.instrument_id,
        event_time=settlement_time, available_at=settlement_time, ingested_at=settlement_time,
        as_of=settlement_time, data_source="SYNTHETIC_SETTLEMENT", source_version="test.v1",
        units="RATE", fidelity="SYNTHETIC_FIXTURE", readiness="READY",
        observation_id="settled-between-partial-and-final-exit", config_hash="c04.test.v1",
        funding_rate="0.00001", funding_time=settlement_time, is_settled=True)
    data = snapshot.model_copy(update={"candles_5m": tuple(sorted(
        (*snapshot.candles_5m, entry_bar, tp1_bar, tp2_bar), key=lambda b: b.open_time))})
    outcome = simulate_decision(decision, data,
        scenario=ExecutionScenario.conservative(sample_end=tp2_bar.available_at),
        profile=demo_costs(), funding=(funding,))
    event = next(e for e in outcome.exit_events if e.event_type == "FUNDING_SETTLEMENT")
    assert D(event.details["remaining_quantity"]) == D("6.0")
    expected_debit = D("0.00001") * decision.entry_max * D("6.0")
    assert D(event.details["signed_debit_usdt"]) == expected_debit
    assert outcome.funding_usdt == expected_debit
    assert not any(e.event_type == "DECLARED_MAX_HOLD_FUNDING_PROXY" for e in outcome.exit_events)


def test_c04_synthetic_stress_matrix_covers_gap_ambiguity_partial_and_both_timers():
    matrix = synthetic_execution_trace()["scenario_outcomes"]
    partial = matrix["E2_PARTIAL_STRESS"]
    assert partial["filled_quantity"] == "5.0"
    assert sum(D(e["details"]["quantity"]) for e in partial["exit_events"]
        if "quantity" in e["details"]) == D("5")
    delayed = matrix["E2_DELAYED"]
    assert delayed["status"] == "MISSED_ENTRY"
    ambiguous = matrix["E2_SAME_BAR_AMBIGUITY"]
    assert ambiguous["exit_events"][0]["event_type"] == "STOP"
    assert ambiguous["optimistic_bound_net_r"] is not None
    gap = matrix["E2_GAP_STOP"]
    assert gap["exit_events"][0]["event_type"] == "STOP"
    assert D(gap["exit_events"][0]["details"]["price"]) < D("99.56")
    for key, event_type, hours, minutes in (
        ("E2_11H55_FLATTEN", "FORCED_FLATTEN_11H55", 11, 55),
        ("E2_12H_HARD_LIMIT", "FORCED_FLATTEN_12H_HARD_LIMIT", 12, 0),
    ):
        outcome = matrix[key]
        assert outcome["status"] == "FLAT"
        event = outcome["exit_events"][0]
        assert event["event_type"] == event_type
        first_fill = datetime.fromisoformat(outcome["first_fill_at"].replace("Z", "+00:00"))
        exit_at = datetime.fromisoformat(event["at"].replace("Z", "+00:00"))
        assert exit_at == first_fill + timedelta(hours=hours, minutes=minutes)


def test_c04_flatten_timer_survives_utc_midnight():
    decision, snapshot = _synthetic_candidate()
    shift = timedelta(hours=10)
    shifted = decision.model_copy(update={
        "as_of": decision.as_of + shift,
        "expires_at": decision.expires_at + shift,
        "earliest_hypothetical_entry_at": decision.earliest_hypothetical_entry_at + shift,
        "trigger_submit_deadline": decision.trigger_submit_deadline + shift,
    })
    arrival = shifted.earliest_hypothetical_entry_at
    entry = candle(arrival, open="100.2", high="100.5", low="100.1", close="100.3")
    flatten = candle(arrival + timedelta(hours=11, minutes=55), open="100.3", high="100.5",
        low="100.1", close="100.3")
    data = snapshot.model_copy(update={"candles_5m": (entry, flatten)})
    outcome = simulate_decision(shifted, data,
        scenario=ExecutionScenario.conservative(sample_end=flatten.available_at),
        profile=demo_costs(), evidence_class="SYNTHETIC_MODELLED_EXECUTION")
    exit_at = outcome.exit_events[0].at
    assert outcome.first_fill_at.date() != exit_at.date()
    assert outcome.exit_events[0].event_type == "FORCED_FLATTEN_11H55"
    assert exit_at == outcome.first_fill_at + timedelta(hours=11, minutes=55)


def test_c04_portfolio_reservations_limits_and_utc_daily_halt():
    decision, _ = _synthetic_candidate()
    too_risky = decision.model_copy(update={"economics": decision.economics.model_copy(
        update={"proposed_modeled_loss_usdt": D("25.01")})})
    risk_ledger = PortfolioLedger(equity_usdt=D("10000"), daily_start_equity_usdt=D("10000"))
    assert risk_ledger.admit(too_risky, as_of=decision.as_of) == (False, "PER_TRADE_RISK_CAP")
    too_leveraged = decision.model_copy(update={"economics": decision.economics.model_copy(
        update={"proposed_quantity": D("300")})})
    assert risk_ledger.admit(too_leveraged, as_of=decision.as_of) == (False, "LEVERAGE_CAP")
    boundary = PortfolioLedger(equity_usdt=D("10000"), daily_start_equity_usdt=D("10000"))
    at_cap = decision.model_copy(update={"economics": decision.economics.model_copy(
        update={"proposed_modeled_loss_usdt": D("25")})})
    assert boundary.admit(at_cap, as_of=decision.as_of) == (True, None)
    second_at_cap = at_cap.model_copy(update={"decision_id": "second-at-cap", "symbol": "OTHERUSDT",
        "instrument_id": binance_usdm_instrument_id("OTHERUSDT")})
    assert boundary.admit(second_at_cap, as_of=decision.as_of) == (True, None)
    assert sum(D(row["risk_usdt"]) for row in boundary.reservations.values()) == D("50")

    ledger = PortfolioLedger(equity_usdt=D("10000"), daily_start_equity_usdt=D("10000"))
    accepted, reason = ledger.admit(decision, as_of=decision.as_of)
    assert accepted and reason is None
    same_symbol = decision.model_copy(update={"decision_id": "second", "setup_id": "other-setup"})
    assert ledger.admit(same_symbol, as_of=decision.as_of) == (False, "SYMBOL_ALREADY_RESERVED")
    other = decision.model_copy(update={"decision_id": "other-symbol", "symbol": "OTHERUSDT",
        "instrument_id": binance_usdm_instrument_id("OTHERUSDT")})
    accepted, reason = ledger.admit(other, as_of=decision.as_of)
    assert accepted and reason is None
    third = decision.model_copy(update={"decision_id": "third", "symbol": "THIRDUSDT",
        "instrument_id": binance_usdm_instrument_id("THIRDUSDT")})
    assert ledger.admit(third, as_of=decision.as_of) == (False, "MAX_SIMULTANEOUS_POSITIONS")
    ledger.release(decision.decision_id, realized_pnl_usdt=D("-101"), at=decision.as_of)
    assert ledger.halted
    assert ledger.admit(third, as_of=decision.as_of) == (False, "DAILY_UTC_ENTRY_HALT")
    ledger.mark_to_market(unrealized_pnl_usdt=D("-100"), at=decision.as_of + timedelta(minutes=1))
    assert ledger.halted


def test_c04_joint_time_block_bootstrap_and_preoutcome_controls_are_reproducible():
    rows = [
        {"market_time_block": "t1", "symbol": "ALT1", "net_r": 1.0},
        {"market_time_block": "t1", "symbol": "ALT2", "net_r": -1.0},
        {"market_time_block": "t2", "symbol": "ALT1", "net_r": 0.5},
        {"market_time_block": "t3", "symbol": "ALT2", "net_r": -0.25},
    ]
    first = cluster_bootstrap(rows, replicates=200, seed=17)
    second = cluster_bootstrap(rows, replicates=200, seed=17)
    assert first == second
    assert first["block_count"] == 3 and first["trade_count"] == 4
    assert first["effective_sample_size"] == 3
    one_block = cluster_bootstrap(rows[:2], replicates=200, seed=17)
    assert one_block["ci95"] is None
    assert one_block["warning"] == "FEWER_THAN_TWO_MARKET_TIME_BLOCKS"
    assert summarize([])["low_sample_warning"] == "FEWER_THAN_30_MARKET_TIME_BLOCKS"
    summary = summarize([1.0, -2.0, 0.0], time_blocks=["t1", "t2", "t3"])
    assert summary["mean_net_r"] == -1.0/3.0
    assert summary["median_net_r"] == 0.0
    assert summary["wins"] == 1 and summary["losses"] == 1 and summary["breakeven"] == 1
    assert summary["max_drawdown_r"] == 2.0 and summary["profit_factor"] == 0.5
    controls = [
        {"window_id": "trigger", "symbol": "ALT1", "regime": "TREND", "cohort": "LARGE",
         "event_time": "2024-01-10T00:00:00Z", "is_trigger": True, "outcome": 99},
        {"window_id": "near", "symbol": "ALT1", "regime": "TREND", "cohort": "LARGE",
         "event_time": "2024-01-09T20:00:00Z", "is_trigger": False, "outcome": -99},
        {"window_id": "prior", "symbol": "ALT1", "regime": "TREND", "cohort": "LARGE",
         "event_time": "2024-01-08T00:00:00Z", "is_trigger": False, "outcome": 123},
        {"window_id": "future", "symbol": "ALT1", "regime": "TREND", "cohort": "LARGE",
         "event_time": "2024-01-12T00:00:00Z", "is_trigger": False, "outcome": -123},
    ]
    picked = matched_controls(controls, seed=3)
    assert picked == {"trigger": "prior"}
    changed_outcomes = [{**row, "outcome": 1000} for row in controls]
    assert matched_controls(changed_outcomes, seed=3) == picked


def test_c04_report_evidence_classes_and_no_writer_boundary():
    panel = load_c02_panel(ROOT / "research/c02_panel")
    run = replay_panel(panel)
    assert run["modes"]["STRICT_POLICY_REPLAY"]["evidence_class"] == "OBSERVED_HISTORICAL_INPUTS_INCOMPLETE"
    assert run["modes"]["EXPLORATORY_SIGNAL_DIAGNOSTICS"]["evidence_class"] == "OBSERVED_HISTORICAL_DIAGNOSTICS"
    assert run["config"]["account"].startswith("synthetic")
    source = (ROOT / "src/astrabot/research/simulation.py").read_text()
    assert "BinancePublic" not in source
    assert "TradeAuthorizationV15" not in source
    assert "create_order" not in source
