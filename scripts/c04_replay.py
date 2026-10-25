"""Run the bounded C04 replay and write a deterministic evidence package."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from astrabot.data.models import config_hash
from astrabot.research.engine import evaluate
from astrabot.research.replay import (
    load_c02_panel, replay_panel, run_c02_panel, synthetic_account, synthetic_cost_profile,
)
from astrabot.research.simulation import ExecutionScenario, simulate_decision
from astrabot.research.demo import START, account, candle, costs, market, roll_market


def synthetic_execution_trace() -> dict[str, object]:
    """Exercise the simulator on a labeled synthetic C03 candidate and bars."""
    from astrabot.research.engine import evaluate as c03_evaluate
    from astrabot.research.demo import SYMBOL, account as demo_account, costs as demo_costs

    formed_at = START + timedelta(seconds=5)
    original = market(formed_at)
    kwargs = {"symbol": SYMBOL, "instrument_id": original.metadata.instrument_id,
        "requested_quantity": 10, "strategies": ("T1",), "sides": ("LONG",)}
    formation = c03_evaluate(original, as_of=formed_at, account=demo_account(formed_at),
        profile=demo_costs(), **kwargs)
    confirmation_at = START + timedelta(minutes=5, seconds=5)
    confirmation_bar = candle(START, open="99.9", high="100.5", low="99.8", close="100.4")
    snapshot = roll_market(original, confirmation_at, extra=(confirmation_bar,))
    confirmed = c03_evaluate(snapshot, as_of=confirmation_at, account=demo_account(confirmation_at),
        profile=demo_costs(), state=formation.state, **kwargs)
    decision = next(d for d in confirmed.emitted if d.decision == "RESEARCH_CANDIDATE")
    arrival = decision.earliest_hypothetical_entry_at
    if arrival is None:
        raise ValueError("C03 synthetic golden candidate has no entry time")
    entry_bar = candle(arrival, open="100.2", high="100.5", low="100.1", close="100.3")
    tp1_bar = candle(arrival + timedelta(minutes=5), open="100.3", high="101.5", low="100.2", close="101.3")
    tp2_bar = candle(arrival + timedelta(minutes=10), open="101.3", high="108.2", low="101.1", close="108.1")
    exec_data = snapshot.model_copy(update={
        "candles_5m": tuple(sorted((*snapshot.candles_5m, entry_bar, tp1_bar, tp2_bar), key=lambda b: b.open_time))
    })
    sample_end = tp2_bar.available_at
    no_execution = simulate_decision(decision, exec_data, scenario=ExecutionScenario.no_execution(),
        profile=demo_costs(), evidence_class="SYNTHETIC_MODELLED_EXECUTION")
    conservative = simulate_decision(decision, exec_data,
        scenario=ExecutionScenario.conservative(sample_end=sample_end), profile=demo_costs(),
        evidence_class="SYNTHETIC_MODELLED_EXECUTION")
    stress = simulate_decision(decision, exec_data,
        scenario=ExecutionScenario.stress(sample_end=sample_end), profile=demo_costs(),
        evidence_class="SYNTHETIC_MODELLED_EXECUTION")
    delayed = simulate_decision(decision, exec_data,
        scenario=ExecutionScenario.delayed_stress(sample_end=sample_end), profile=demo_costs(),
        evidence_class="SYNTHETIC_MODELLED_EXECUTION")
    ambiguous_tp1 = tp1_bar.model_copy(update={"low": decision.geometry.original_stop - D("0.1")})
    ambiguous_data = snapshot.model_copy(update={"candles_5m": tuple(sorted(
        (*snapshot.candles_5m, entry_bar, ambiguous_tp1, tp2_bar), key=lambda b: b.open_time))})
    ambiguous = simulate_decision(decision, ambiguous_data,
        scenario=ExecutionScenario.conservative(sample_end=sample_end), profile=demo_costs(),
        evidence_class="SYNTHETIC_MODELLED_EXECUTION", adverse_first=True)
    gap_bar = candle(arrival + timedelta(minutes=5), open=str(decision.geometry.original_stop - D("0.2")),
        high=str(decision.entry_max), low=str(decision.geometry.original_stop - D("0.5")),
        close=str(decision.geometry.original_stop - D("0.3")))
    gap_data = snapshot.model_copy(update={"candles_5m": tuple(sorted(
        (*snapshot.candles_5m, entry_bar, gap_bar), key=lambda b: b.open_time))})
    gap = simulate_decision(decision, gap_data,
        scenario=ExecutionScenario.conservative(sample_end=gap_bar.available_at), profile=demo_costs(),
        evidence_class="SYNTHETIC_MODELLED_EXECUTION")
    timer_bar = candle(arrival + timedelta(hours=11, minutes=55), open="100.3", high="100.5",
        low="100.1", close="100.3")
    timer_data = snapshot.model_copy(update={"candles_5m": tuple(sorted(
        (*snapshot.candles_5m, entry_bar, timer_bar), key=lambda b: b.open_time))})
    timer = simulate_decision(decision, timer_data,
        scenario=ExecutionScenario.conservative(sample_end=timer_bar.available_at), profile=demo_costs(),
        evidence_class="SYNTHETIC_MODELLED_EXECUTION")
    hard_bar = candle(arrival + timedelta(hours=12), open="100.3", high="100.5", low="100.1", close="100.3")
    hard_data = snapshot.model_copy(update={"candles_5m": tuple(sorted(
        (*snapshot.candles_5m, entry_bar, hard_bar), key=lambda b: b.open_time))})
    hard_limit = simulate_decision(decision, hard_data,
        scenario=ExecutionScenario.conservative(sample_end=hard_bar.available_at), profile=demo_costs(),
        evidence_class="SYNTHETIC_MODELLED_EXECUTION")
    return {"evidence_class": "SYNTHETIC_TEST_FIXTURE", "decision_id": decision.decision_id,
        "scenario_net_rr": str(decision.scenario_net_rr), "scenario_outcomes": {
            "E0": no_execution.model_dump(mode="json"),
            "E1": conservative.model_dump(mode="json"), "E2_PARTIAL_STRESS": stress.model_dump(mode="json"),
            "E2_DELAYED": delayed.model_dump(mode="json"), "E2_SAME_BAR_AMBIGUITY": ambiguous.model_dump(mode="json"),
            "E2_GAP_STOP": gap.model_dump(mode="json"), "E2_11H55_FLATTEN": timer.model_dump(mode="json"),
            "E2_12H_HARD_LIMIT": hard_limit.model_dump(mode="json")},
        "fixture_events": {"confirmation_available_at": confirmation_bar.available_at.isoformat(),
            "assumed_order_arrival": arrival.isoformat(), "entry_bar_open": entry_bar.open_time.isoformat(),
            "sample_end": sample_end.isoformat()},
        "caveat": "Generated prices/account/costs are synthetic mechanics evidence, never historical performance."}


def report_markdown(run: dict[str, object], synthetic: dict[str, object]) -> str:
    strict = run["modes"]["STRICT_POLICY_REPLAY"]
    exploratory = run["modes"]["EXPLORATORY_SIGNAL_DIAGNOSTICS"]
    funnel = run["funnel"]
    parts = run["partitions"]
    lines = [
        "# C04 historical replay and execution economics — research handoff",
        "",
        f"**Run:** `{run['run_id']}`",
        f"**Configuration hash:** `{run['config_hash']}`",
        f"**Verdict:** `BLOCKED_BY_DATA`",
        "**C05 recommendation:** `INSUFFICIENT_EVIDENCE`",
        "",
        "This result is an engineering and source-coverage report. It does not claim an edge, owner approval, or observed exchange fills.",
        "",
        "## Scope and provenance",
        "",
        "The bounded retained panel contains the source partitions below. It is a parser and causal replay smoke sample; the retained symbol choice was not a strategy-performance selection and does not represent the historical tradeable universe.",
        "",
        "| Feed | Symbol | Coverage | Rows | Fidelity | Retained SHA256 | Availability |",
        "|---|---|---|---:|---|---|---|"]
    for p in parts:
        lines.append(f"| {p['feed']} | {p['symbol']} | {p['coverage_start']}–{p['coverage_end']} | {p['actual_row_count']} | {p['fidelity']} | `{p['retained_input_sha256']}` | {p['availability_status']} |")
    lines.extend([
        "",
        "The source archive host `data.binance.vision` is outside the selected executor's restricted egress allowlist. The earlier C02 attempt received a CONNECT 403; this task reuses its verified GitHub mirror fixtures and does not repeat blocked download attempts. The historical archive does not prove original publication or transport latency. BTC hourly bars use `close_time + 1 ms` as an availability proxy; APE aggregate trades use exchange transaction time as a proxy. Neither is observed live ingestion time.",
        "",
        "No point-in-time exchangeInfo snapshots were retained. Historical listing status, tick/step/min-notional filters, delisting state, and a reliable inactive-symbol panel are therefore unavailable. The current symbol universe was not substituted for historical metadata.",
        "",
        "## Opportunity funnel",
        "",
        "| Stage | Result |",
        "|---|---:|",
        f"| Symbols present in retained panel | {funnel['symbols_discovered']} |",
        f"| Symbols with source coverage | {funnel['symbols_with_source_coverage']} |",
        f"| Symbols eligible at latest snapshot | {funnel['symbols_eligible_latest']} |",
        f"| Latest C02 eligibility states | `{funnel['eligibility_state_counts_latest']}` |",
        f"| Symbols shortlisted at latest snapshot | {funnel['symbols_shortlisted_latest']} |",
        f"| Shortlist entries across replay windows | {strict['shortlisted_symbol_windows']} |",
        f"| STRICT C03 policy evaluations | {strict['strict_decision_count']} |",
        f"| Separate C03 diagnostic context evaluations | {funnel['diagnostic_context_evaluations']} |",
        f"| STRICT research candidates | {strict['candidate_count']} |",
        f"| Armed/confirmed diagnostic setups | {funnel['setups_armed']}/{funnel['setups_confirmed']} |",
        f"| Diagnostic C03 NO_TRADE records | {exploratory['decision_count']} |",
        "| Approval, order, fill, protected-position, TP/stop events | 0 |",
        "",
        "The strict scanner uses C02's actual eligibility and deterministic shortlist gates, capped at 15. Because no symbol passes, no symbol enters the strict policy shortlist. The separate diagnostic stream calls the actual C03 engine on panel symbols with an empty bypass list; it does not promote those records into eligible trades. The panel symbol count is source coverage, not a reconstructed historical tradeable universe. Funnel and decision details are in `run.json`.",
        "",
        "Top missing-input vetoes include absent metadata, ticker, 5M/15M/4H history, 60 spread samples, depth, validated OI notional, and verified event clearance. The 24 BTC 1H rows also fall short of the C03 735-bar ATR percentile warm-up. APE has only 100 aggregate trades and no candle context.",
        "",
        "## Historical examples",
        "",
        "| Case | Source chronology | Result |",
        "|---|---|---|",
        "| BTCUSDT 1H | Binance public archive; 2024-10-28 00:00 through 23:59:59.999 UTC; 24 rows; replay availability through 2024-10-29 00:00 UTC | C02 ineligible; C03 diagnostic NO_TRADE. No eligible setup or execution outcome. |",
        "| APEUSDT aggregate trades | Binance public archive; 2024-10-18 00:00:03.958 through 00:01:24.156 UTC; first 100 contiguous rows retained from a 45,342-row day | Trade-side parser evidence only; no candle context or eligible setup. |",
        "",
        "The positive/negative C03 golden trace remains synthetic and is reported in the separate synthetic section below. No historical target/stop result can be reconstructed from these retained rows.",
        "",
        "## Execution cases and economics",
        "",
        "E0 records no approval and no observed fill. E1 applies an adverse-side bounded entry, fixed C03 geometry, exchange quantity filters, fees, partial exits, stop/target ambiguity, a 11h55m flatten objective and 12-hour cap as a bar-model counterfactual. E2 applies a preapproved bounded-plan variant with partial size and higher fees/friction; a separate E2 delayed case assumes 15 seconds after trigger. A delay beyond C03's ten-second trigger submission deadline becomes a missed entry. Every OHLC result remains `BAR_APPROX` and is not an IOC fill observation.",
        "",
        "Where no observed funding settlements exist, synthetic execution scenarios charge the declared max-hold proxy against modeled remaining quantity-time; partial exits reduce later proxy exposure. This is a labeled sensitivity assumption, not historical funding data.",
        "",
        "Historical E0/E1/E2 outcomes: no historical candidate reached this stage; there are zero modeled historical execution outcomes.",
        "",
        "Synthetic test fixture outcomes are isolated and cannot enter historical performance summaries:",
        "",
        "| Scenario | Status | Filled quantity | Realized net R | Classification |",
        "|---|---|---:|---:|---|"])
    for scenario_id, outcome in synthetic["scenario_outcomes"].items():
        lines.append(f"| {scenario_id} | {outcome['status']} | {outcome['filled_quantity']} | {outcome['realized_net_r']} | {outcome['evidence_class']} |")
    lines.extend([
        "",
        "Synthetic outcomes verify accounting paths only. C03's scenario net RR is a conditional successful-ladder benchmark, not expectancy. B1 retains the original 40% at +1R and 60% at +2R ladder, 1.6 gross price-R, and equal-cost threshold `c/d <= 0.04`; the empirical share meeting that threshold is not testable here.",
        "",
        "## R0–R3 and uncertainty",
        "",
        "| Stage | Result |",
        "|---|---|",
        "| R0 data/friction feasibility | `INSUFFICIENT_DATA`; no fee, funding, quote/depth or qualified opportunity distribution |",
        "| R1 setup diagnostics | `NOT_TESTABLE`; zero causally complete setups and no matched controls |",
        "| R2 complete policy replay | `BLOCKED_BY_DATA`; zero C02-eligible symbols and zero strict C03 candidates |",
        "| R3 ablations | `NOT_TESTABLE`; no qualified sample for A01, funding/OI vetoes, obstacles or management comparisons |",
        "| Cluster-aware interval | Undefined; no qualified fills or market-time outcome blocks |",
        "",
        "A chronological split is predeclared for a future bounded pilot: dataset window 2024-08-01 through 2024-11-01 UTC; warm-up 2024-08-01–2024-08-31; development 2024-09-01–2024-09-30; validation 2024-10-01–2024-10-14; untouched evaluation 2024-10-15–2024-10-31; 12-hour purge/embargo at boundaries. This supplies more than the 735-hour C03 warm-up while leaving two months for evaluation. Retained coverage does not satisfy any split. No holdout outcome was used to choose a strategy or cohort.",
        "",
        "## Performance and reproducibility",
        "",
        f"Measured on this executor: {run['measurements']['runtime_seconds']:.6f}s, peak traced Python allocation {run['measurements']['peak_traced_memory_bytes']} bytes, {run['time_range']['evaluation_windows']} availability snapshots, {len(run['funnel_events'])} funnel events. These are measurements of the bounded in-memory replay, not archive extraction or broad-universe capacity.",
        "",
        f"Decision ledger SHA256: `{run['output_manifest']['decision_ledger_sha256']}`",
        f"Funnel ledger SHA256: `{run['output_manifest']['funnel_ledger_sha256']}`",
        "",
        "## Data blocker and next experiment",
        "",
        "The workspace's restricted egress policy permits Binance documentation hosts but not the archive host; archive retrieval therefore remains blocked here. The existing retained GitHub mirror fixtures provide genuine Binance-origin observations but not a usable multi-symbol policy panel. Missing OI units, historical event/news coverage, quote/depth, funding, metadata changes and executable fill records remain unresolved and fail closed.",
        "",
        "Next research task: on an executor whose approved egress permits Binance public historical archives, retrieve the fixed 2024-08-01 through 2024-11-01 pilot range using Binance UM archives for BTC/ETH context and a predeclared altcoin selection based only on point-in-time contract validity, prior 30-day turnover, and realized-volatility/liquidity cohorts. Do not use strategy outcomes for symbol selection. Preserve symbols that become inactive when historical archive and metadata evidence exist; otherwise log the gap. Store raw partitions outside Git, retain checksums and gaps, then populate 1H/4H/15M/5M and funding. Keep verified event, OI-unit, quote/depth, and contract filter status unavailable until authentic point-in-time sources are qualified.",
        "",
        "## C05 decision boundary",
        "",
        "This report recommends `INSUFFICIENT_EVIDENCE`. It is not the C05 economic decision. Do not advance an empirical policy GO or claim profitable, production-ready, demo-qualified or owner-approved performance from the modeled fixture.",
        "",
        "**C04 engineering gate:** the replay, funnel, simulation adapter, statistics, deterministic artifact generation, provenance checks and offline tests are ready for independent review.",
        "**Empirical economic evidence:** insufficient for C05.",
        "**C06:** only a research-only paper MVP may be considered after independent C04 review; no real exposure authority is implied.",
        ""])
    return "\n".join(lines)


def build_artifacts(data_dir: Path) -> tuple[dict[str, object], dict[str, object], str]:
    panel = load_c02_panel(data_dir)
    run = replay_panel(panel)
    synthetic = synthetic_execution_trace()
    run["scenario_outcomes"]["SYNTHETIC_TEST_FIXTURE"] = synthetic["scenario_outcomes"]
    run["synthetic_test_fixture"] = synthetic
    run["empirical_qualification"] = {"status": "BLOCKED_BY_DATA",
        "c05_recommendation": "INSUFFICIENT_EVIDENCE", "policy_profitability_claim": False,
        "synthetic_results_in_empirical_summary": False}
    return run, synthetic, report_markdown(run, synthetic)


def source_inventory(panel) -> dict[str, object]:
    return {
        "schema_version": "c04.source-inventory.v1",
        "classification": "OBSERVED_WITH_EXPLICIT_AVAILABILITY_PROXY",
        "pilot_window_proposed_utc": {"start": "2024-08-01T00:00:00Z", "end_exclusive": "2024-11-01T00:00:00Z"},
        "retained_manifest": "../c02_panel/manifest.json",
        "retained_manifest_sha256": hashlib.sha256(
            (ROOT / "research/c02_panel/manifest.json").read_bytes()).hexdigest(),
        "partitions": list(panel.partitions),
        "source_attempts": [
            {"source": "Binance public archives", "host": "data.binance.vision",
             "result": "BLOCKED_BY_RESTRICTED_EGRESS", "attempted_in_c04": False,
             "evidence": "C02 journal records CONNECT 403; this task did not repeat the blocked request."},
            {"source": "Freqtrade pinned public fixture mirror", "host": "github.com",
             "result": "REUSED_EXISTING_CHECKSUMMED_FIXTURES", "attempted_in_c04": False,
             "version": "1f394eaebc2f46a83d26971388628707802f8602"},
            {"source": "Other mirrors/providers", "result": "NOT_ATTEMPTED",
             "reason": "No qualifying alternative source was retained; bounded data retrieval plan documented in README."}
        ],
        "historical_contract_metadata": "UNAVAILABLE; current exchangeInfo was not substituted",
        "historical_delisted_symbols": "UNAVAILABLE unless future archive and dated metadata evidence are supplied",
        "archive_publication_latency": "UNVERIFIED",
        "ingestion_timestamp": "UNOBSERVED",
        "retrieval_reproduction": "See research/c04/README.md; external downloads remain opt-in/manual on an executor with approved egress.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "research/c02_panel")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research/c04")
    parser.add_argument("--check", action="store_true", help="verify run reproducibility invariants")
    args = parser.parse_args()
    run, synthetic, report = build_artifacts(args.data_dir)
    inventory = source_inventory(load_c02_panel(args.data_dir))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "run.json"
    report_path = args.output_dir / "REPORT.md"
    inventory_path = args.output_dir / "source_inventory.json"
    json_path.write_text(json.dumps(run, sort_keys=True, indent=2, default=str) + "\n")
    report_path.write_text(report)
    inventory_path.write_text(json.dumps(inventory, sort_keys=True, indent=2, default=str) + "\n")
    if args.check:
        if run["modes"]["STRICT_POLICY_REPLAY"]["status"] != "BLOCKED_BY_DATA":
            raise SystemExit("C04 actual retained panel unexpectedly left the data-blocked state")
        if run["funnel"]["strict_candidate_decisions"] != 0:
            raise SystemExit("C04 retained panel unexpectedly produced a strict historical candidate")
        if run["empirical_qualification"]["c05_recommendation"] != "INSUFFICIENT_EVIDENCE":
            raise SystemExit("C04 replay must not make a C05 economic qualification decision")
        repeated, repeated_synthetic, repeated_report = build_artifacts(args.data_dir)
        for key in ("run_id", "config_hash", "output_manifest", "funnel", "strict_decisions", "diagnostic_decisions"):
            if run[key] != repeated[key]:
                raise SystemExit(f"C04 deterministic replay check failed: {key}")
        if synthetic != repeated_synthetic:
            raise SystemExit("C04 synthetic replay reproduction check failed")
    print(json.dumps({"run_id": run["run_id"], "report": str(report_path),
        "run_json": str(json_path), "verdict": "BLOCKED_BY_DATA",
        "measurements": run["measurements"], "strict_candidates": run["funnel"]["strict_candidate_decisions"],
        "diagnostic_no_trade": run["funnel"]["diagnostic_no_trade_decisions"]}, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
