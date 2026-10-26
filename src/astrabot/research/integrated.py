"""C05 economic research packet over the existing C02/C03/C04/G/H pipeline.

Price-only setup traces answer a separate diagnostic question. They never enter
C04's candidate ledger, portfolio simulator or uncertainty sample.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from decimal import Decimal as D
from statistics import median
from typing import Any, Sequence

from astrabot.contracts import scenario_net_rr
from astrabot.data.historical_replay import ResearchSnapshot
from astrabot.data.models import binance_usdm_instrument_id, config_hash, stable_id
from astrabot.research.context import evaluate_context
from astrabot.research.models import VERSIONS
from astrabot.research.policies import TERMINAL, advance_setup, form_setup
from astrabot.research.replay import HistoricalPanel, _panel_point_in_time, _panel_availability_times, replay_panel
from astrabot.research.statistics import cluster_bootstrap, summarize
from astrabot.universe.eligibility import SymbolData, scan_universe

HISTORY_LIMITS = {"5m": 288, "15m": 21, "1h": 735, "4h": 200}


def safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, D):
        return str(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dataclass_fields__"):
        return safe(asdict(value))
    if isinstance(value, dict):
        return {str(k): safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(v) for v in value]
    return value


def attach_snapshots(panel: HistoricalPanel, snapshots: Sequence[ResearchSnapshot], *,
                     feed_provenance: dict[str, Any]) -> HistoricalPanel:
    """Join verified G/H output only at the cutoff where it was validated.

    Preserve source event/arrival times, readiness and quality. Periodic samples
    retain their raw event timestamps; sampled_at never replaces C02's clock.
    No ticker, event clearance, funding settlement or fill is inferred.
    """
    panel_synthetic = panel.source_manifest.get("evidence_class", "").startswith("SYNTHETIC_")
    if bool(feed_provenance.get("synthetic")) != panel_synthetic:
        raise ValueError("synthetic feed/panel scope mismatch")
    hashes = feed_provenance["source_sha256"]
    joined = {at: dict(values) for at, values in panel.research_snapshots.items()}
    seen = set()
    for snapshot in snapshots:
        key = (snapshot.symbol, snapshot.decision_time)
        if key in seen or snapshot.symbol not in panel.symbols or snapshot.symbol in joined.get(snapshot.decision_time, {}):
            raise ValueError("duplicate cutoff or feed symbol absent from historical panel")
        seen.add(key)
        for name, dataset in (("latest_quote", "quotes"), ("latest_depth", "book_snapshot_25"),
                              ("latest_open_interest", "derivative_ticker")):
            row = getattr(snapshot, name)
            if row is not None and (row.symbol != snapshot.symbol
                    or row.instrument_id != binance_usdm_instrument_id(snapshot.symbol)
                    or row.source_sha256 != hashes[dataset]):
                raise ValueError("snapshot feed identity/hash mismatch")
        if any(row.symbol != snapshot.symbol
               or row.instrument_id != binance_usdm_instrument_id(snapshot.symbol)
               or row.source_sha256 != hashes["quotes"]
               for row in snapshot.periodic_spread_samples):
            raise ValueError("snapshot periodic quote identity/hash mismatch")
        # These are exact research snapshots, never a forward-filled history.
        data = SymbolData(metadata=snapshot.evidence_validation.metadata,
            spread_samples=snapshot.periodic_spread_samples,
            depth=snapshot.latest_depth, open_interest=snapshot.latest_open_interest)
        joined.setdefault(snapshot.decision_time, {})[snapshot.symbol] = data
    provenance = safe(feed_provenance)
    manifest = {**panel.source_manifest, "c05_original_feed_inputs": provenance,
                "c05_exact_snapshot_sha256": config_hash(safe(snapshots))}
    # Include all provenance in C04 run identity without pretending it is a
    # retained market-data partition with invented rows or coverage.
    return replace(panel, source_manifest=manifest, research_snapshots=joined)


def evaluation_times(panel: HistoricalPanel, *, start: datetime | None,
                     end: datetime | None, interval: str | None) -> list[datetime]:
    if interval is not None and interval not in ("5m", "15m", "1h", "4h"):
        raise ValueError("unsupported evaluation interval")
    times = (_panel_availability_times(panel) if interval is None else
        {c.available_at for data in panel.symbols.values()
             for c in getattr(data, f"candles_{interval}")})
    return sorted(at for at in times if (start is None or at >= start)
                  and (end is None or at < end))


def price_diagnostics(panel: HistoricalPanel, times: Sequence[datetime]) -> dict[str, Any]:
    """Run frozen formation/advancement on prices, outside admission.

    Every attempted policy/side retains a reason. Timeline state and original
    anchors are inspectable; CONFIRMED here is a price pattern, never a trade.
    """
    active = {}
    seen = set()
    timelines = defaultdict(list)
    formations = {}
    reasons = Counter()
    context_counts = Counter()
    rejection_samples = []
    for at in times:
        for symbol in sorted(panel.symbols):
            data = _panel_point_in_time(panel, symbol, at, HISTORY_LIMITS)
            context = evaluate_context(data, symbol=symbol,
                instrument_id=binance_usdm_instrument_id(symbol), as_of=at)
            context_counts[context.classification] += 1
            source = stable_id("c05j.price-only.v1", symbol, at, context.context_id)
            last = data.candles_5m[-1] if data.candles_5m else None
            c02 = scan_universe({symbol: data}, at, D("100")).considered[0]
            for strategy in VERSIONS:
                for side in ("LONG", "SHORT"):
                    key = (symbol, strategy, side)
                    setup = active.get(key)
                    if setup is not None:
                        previous = setup
                        setup = advance_setup(setup, data, context)
                        active[key] = setup
                        changed = setup != previous
                        row_reasons = (("PRICE_ONLY_CONFIRMATION",) if setup.snapshot.state == "CONFIRMED"
                            else setup.notes[-1:] or ("AWAITING_ORDERED_CONFIRMATION",))
                        if changed:
                            timelines[setup.snapshot.setup_id].append({"as_of": at.isoformat(),
                                "state": setup.snapshot.state, "notes": list(row_reasons),
                                "last_bar_open": setup.last_bar_open.isoformat(),
                                "selected_bar": safe(setup.selected_bar),
                                "confirmation_bar": safe(setup.confirmation_bar)})
                        if setup.snapshot.state in TERMINAL or setup.snapshot.state == "CONFIRMED":
                            active.pop(key, None)
                        reasons.update(row_reasons)
                        continue
                    setup, rejected = form_setup(strategy, data, context, side, source)
                    if setup is not None and setup.snapshot.setup_id not in seen:
                        seen.add(setup.snapshot.setup_id)
                        active[key] = setup
                        formations[setup.snapshot.setup_id] = setup
                        timelines[setup.snapshot.setup_id].append({"as_of": at.isoformat(),
                            "state": setup.snapshot.state, "notes": ["PRICE_ONLY_FORMATION"],
                            "c02_reasons": list(c02.reasons), "source_bar": safe(last),
                            "context": safe(context)})
                        reasons["PRICE_ONLY_FORMATION"] += 1
                    else:
                        rejected = rejected or ("SETUP_EVENT_ALREADY_RECORDED",)
                        reasons.update(rejected)
                        # Stable first chronological sample per policy/side/symbol.
                        sample_key = (symbol, strategy, side)
                        if sample_key not in {tuple(r["key"]) for r in rejection_samples}:
                            rejection_samples.append({"key": list(sample_key), "as_of": at.isoformat(),
                                "symbol": symbol, "strategy": strategy, "side": side,
                                "reasons": list(rejected), "c02_reasons": list(c02.reasons),
                                "source_bar": safe(last), "context": safe(context)})
    records = [{"setup_id": identifier, "strategy": setup.strategy_id,
        "side": setup.snapshot.side, "symbol": setup.snapshot.symbol,
        "frozen_setup": safe(setup), "timeline": timelines[identifier],
        "eligible_trade": False} for identifier, setup in formations.items()]
    return {"evidence_class": "PRICE_ONLY_FROZEN_POLICY_DIAGNOSTIC",
        "admitted_to_execution": False, "candidate_count": 0,
        "formation_count": len(records), "formations_by_policy": dict(Counter(r["strategy"] for r in records)),
        "confirmed_pattern_count": sum(any(t["state"] == "CONFIRMED" for t in r["timeline"]) for r in records),
        "reason_counts": dict(sorted(reasons.items())), "context_counts": dict(sorted(context_counts.items())),
        "setups": records, "rejection_samples": rejection_samples,
        "limitation": "Price patterns exclude mandatory admission and geometry/economic gates; hourly formation can miss transient events. No diagnostic is a policy-eligible trade."}


def sensitivity(diagnostics: dict[str, Any]) -> dict[str, Any]:
    """B1's frozen ladder cost capacity with real diagnostic stop widths.

    Reuses the contract's net-RR function. Symmetric round-trip costs are
    deliberately simplified hypotheses, never historical fees/funding/fills.
    """
    examples = []
    for record in diagnostics["setups"]:
        if record["strategy"] != "B1":
            continue
        confirmation = next((t.get("confirmation_bar") for t in record["timeline"]
                             if t.get("confirmation_bar")), None)
        selected = next((t.get("selected_bar") for t in record["timeline"]
                         if t.get("selected_bar")), None)
        if not confirmation or not selected:
            continue
        sign = D(1) if record["side"] == "LONG" else D(-1)
        extreme = D(selected["low"] if sign == 1 else selected["high"])
        atr = D(record["frozen_setup"]["snapshot"]["frozen_atr"])
        stop = extreme-sign*D(".10")*atr
        entry = D(confirmation["close"])
        distance = sign*(entry-stop)
        if distance <= 0:
            continue
        rows = []
        for fee_bps, friction_bps in ((D(2), D(0)), (D(5), D(2)), (D(10), D(5))):
            cost = entry*(2*fee_bps+friction_bps)/D(10000)
            rr = scenario_net_rr(D("1.6"), distance, cost, cost)
            rows.append({"fee_per_side_bps": str(fee_bps), "other_round_trip_friction_bps": str(friction_bps),
                "cost_per_unit": str(cost), "cost_r": str(cost/distance),
                "ladder_success_net_rr": str(rr), "passes_1_5_rr_hypothesis": rr >= D("1.5")})
        examples.append({"setup_id": record["setup_id"], "symbol": record["symbol"],
            "as_of": confirmation["available_at"], "side": record["side"],
            "source_bar_id": confirmation["source_record_id"], "assumed_entry_at_confirmation_close": str(entry),
            "unrounded_diagnostic_stop": str(stop), "stop_distance": str(distance),
            "stop_fraction": str(distance/entry), "symmetric_cost_budget_r_for_1_5_rr": "0.04",
            "scenarios": rows})
    return {"status": "MODELLED_FRICTION_DIAGNOSTIC" if examples else "NOT_TESTABLE",
        "frozen_ladder": "B1 40% at 1R, 60% at 2R; 1.6 gross price R",
        "formula": "(1.6*d - c)/(d+c) >= 1.5 requires symmetric cost c/d <= 0.04",
        "assumptions": ["Confirmation close as hypothetical entry, unrounded original retest/ATR stop.",
            "Symmetric round-trip cost: two assumed per-side fees plus stated friction; no observed fills or funding.",
            "No target/stop outcome, tick/minimum quantity, route or C02 admission is certified."],
        "examples": examples}


def policy_assessments(run: dict[str, Any]) -> dict[str, Any]:
    decisions = {d["decision_id"]: d for d in run["strict_decisions"]}
    synthetic = run["config"]["panel_evidence_class"].startswith("SYNTHETIC_")
    assessments = {}
    for strategy, version in VERSIONS.items():
        candidates = [d for d in decisions.values() if d["strategy_id"] == strategy
                      and d["decision"] == "RESEARCH_CANDIDATE"]
        scenarios = {}
        for scenario, outcomes in run["scenario_outcomes"].items():
            rows = [r for r in outcomes if r["decision_id"] in decisions
                    and decisions[r["decision_id"]]["strategy_id"] == strategy]
            complete = [r for r in rows if r["status"] == "FLAT" and r["realized_net_r"] is not None]
            values = [float(r["realized_net_r"]) for r in complete]
            blocks = [str(r["first_fill_at"])[:10] for r in complete]
            scenarios[scenario] = {"evidence_class": "NO_EXECUTION_POLICY_TRUTH" if scenario == "E0" else
                ("SYNTHETIC_MODELLED_BAR_COUNTERFACTUALS" if synthetic else "MODELLED_BAR_COUNTERFACTUALS"),
                "outcome_count": len(rows), "status_counts": dict(Counter(r["status"] for r in rows)),
                "complete_modelled_outcomes": len(complete),
                "costs_usdt": {name: str(sum((D(str(r.get(name) or 0)) for r in rows), D(0)))
                    for name in ("fees_usdt", "spread_slippage_usdt", "funding_usdt")},
                "summary": summarize(values, time_blocks=blocks),
                "uncertainty": cluster_bootstrap([{"market_time_block": b, "net_r": v}
                    for b, v in zip(blocks, values)])}
        assessments[strategy] = {"version": version, "status": "RESEARCH_ONLY",
            "evidence_class": "SYNTHETIC_PIPELINE_TEST_ONLY" if synthetic else "OBSERVED_HISTORICAL_RESEARCH",
            "decision": "INSUFFICIENT_EVIDENCE", "strict_candidates": len(candidates),
            "historical_executable_trades": 0, "scenarios": scenarios,
            "reason": "No observed executable-fill evidence or qualified later-window economic gate; modelled outcomes cannot certify a policy."}
    return assessments


def build_packet(panel: HistoricalPanel, *, replay_start: datetime | None = None,
                 replay_end: datetime | None = None, evaluation_interval: str | None = "1h",
                 snapshots: Sequence[ResearchSnapshot] = (),
                 feed_provenance: dict[str, Any] | None = None) -> dict[str, Any]:
    """Complete one deterministic research decision packet, with causal ledgers."""
    if snapshots:
        if feed_provenance is None:
            raise ValueError("feed provenance required with original-feed snapshots")
        panel = attach_snapshots(panel, snapshots, feed_provenance=feed_provenance)
    if replay_end is not None:
        # Outcome bars cannot silently cross the declared research scope into
        # a later validation/holdout period. Preserve full input provenance.
        panel = replace(panel, symbols={symbol: data.model_copy(update={
            f"candles_{interval}": tuple(c for c in getattr(data, f"candles_{interval}")
                if c.available_at < replay_end)
            for interval in ("5m", "15m", "1h", "4h")})
            for symbol, data in panel.symbols.items()})
    times = evaluation_times(panel, start=replay_start, end=replay_end, interval=evaluation_interval)
    if not times:
        raise ValueError("research scope contains no candle evaluation windows")
    run = replay_panel(panel, replay_start=replay_start, replay_end=replay_end,
        evaluation_interval=evaluation_interval, history_limits=HISTORY_LIMITS, compact_diagnostics=True,
        diagnostic_sample_times=(times[0], times[-1]))
    # Timings are measured operationally by C04 but excluded from reproducible packet.
    run.pop("measurements", None)
    eligibility = [e for e in run["funnel_events"] if e["event_type"] == "ELIGIBILITY_WINDOW"]
    vetoes = Counter(reason for e in eligibility for reason in e["details"]["reasons"])
    by_symbol = {}
    for symbol in sorted(panel.symbols):
        rows = [e for e in eligibility if e["symbol"] == symbol]
        by_symbol[symbol] = {"windows": len(rows), "eligible": sum(e["details"]["eligible"] for e in rows),
            "vetoes": dict(sorted(Counter(r for e in rows for r in e["details"]["reasons"]).items()))}
    diagnostics = price_diagnostics(panel, times)
    sensitivity_report = sensitivity(diagnostics)
    widths = sorted(D(row["stop_fraction"]) for row in sensitivity_report["examples"])
    stop_widths = {"count": len(widths), "minimum": str(widths[0]) if widths else None,
        "median": str(median(widths)) if widths else None,
        "p90": str(widths[int((len(widths)-1)*.90)]) if widths else None,
        "maximum": str(widths[-1]) if widths else None,
        "population": "Confirmed price-only B1 patterns with positive unrounded original stop distance; not eligible trades."}
    spreads = sorted(s.spread_median_fraction for s in snapshots if s.spread_median_fraction is not None)
    assessments = policy_assessments(run)
    synthetic = run["config"]["panel_evidence_class"].startswith("SYNTHETIC_")
    selected_case = next((r for r in diagnostics["setups"] if any(
        t["state"] == "CONFIRMED" for t in r["timeline"])), next(iter(diagnostics["setups"]), None))
    packet = {"schema_version": "c05j.integrated-economic-research.v1",
        "evidence_class": "SYNTHETIC_PIPELINE_TEST_ONLY" if synthetic else "OBSERVED_HISTORICAL_RESEARCH",
        "decision": "INSUFFICIENT_EVIDENCE", "policy_status": "RESEARCH_ONLY",
        "policy_versions": VERSIONS, "phase_gate_credit_percent": 45,
        "provenance": {"historical_manifest": panel.source_manifest,
            "original_feeds": safe(feed_provenance), "normalized_historical_rows": sum(
                p["normalized_row_count"] for p in panel.partitions),
            "original_feed_snapshot_count": len(snapshots)},
        "funnel": {**run["funnel"], "eligibility_vetoes_by_symbol_window": dict(sorted(vetoes.items())),
            "per_symbol": by_symbol, "policy_side_evaluations": run["diagnostic_summary"]["decision_counts"],
            "price_only_formations": diagnostics["formation_count"], "historical_executable_trades": 0},
        "stages": {"R0": {"status": "INSUFFICIENT_EVIDENCE", "strict_admissions": run["funnel"]["strict_candidate_decisions"],
            "friction_sensitivity": sensitivity_report,
            "diagnostic_b1_stop_fraction_distribution": stop_widths,
            "periodic_spread_fraction_distribution": {"count": len(spreads),
                "minimum": str(spreads[0]) if spreads else None,
                "median": str(median(spreads)) if spreads else None,
                "maximum": str(spreads[-1]) if spreads else None,
                "strict_c02_spread_admission_implied": False},
            "price_formation_frequency": {"formations": diagnostics["formation_count"],
                "symbol_windows": len(times)*len(panel.symbols),
                "by_policy": diagnostics["formations_by_policy"]},
            "reason": "Actual price patterns and veto distribution are observable; complete historical liquidity/cohort and cost feasibility are not established."},
            "R1": {"status": "NOT_TESTABLE", "strict_event_denominator": run["funnel"]["strict_candidate_decisions"],
                "matched_controls": None, "forward_move_mae_mfe": None,
                "reason": "No authentic strictly eligible event/control population with declared horizons and complete mandatory evidence is certified."},
            "R2": {"status": "MODELLED_COUNTERFACTUALS_ONLY" if run["funnel"]["strict_candidate_decisions"] else "NOT_TESTABLE",
                "outcome_end_exclusive": replay_end.isoformat() if replay_end else None,
                "split_purge_status": "UNQUALIFIED_NO_CROSS_SPLIT_ECONOMIC_PROMOTION",
                "policy_assessments": assessments, "qualified_net_r": None,
                "reason": "E0 retains no-execution truth; E1/E2 reuse C04 costs, approval/entry delay, partial fills, exits and portfolio constraints as explicit bar models."}},
        "cases": {"selection_rule": "First chronological price-only formation reaching confirmation, else first formation; first chronological rejection. No return-based selection.",
            "market_case": selected_case, "no_trade_case": next(iter(diagnostics["rejection_samples"]), None)},
        "price_diagnostics": diagnostics, "original_feed_snapshots": safe(snapshots),
        "policy_assessments": assessments, "replay": run,
        "remaining_evidence": ["Contemporaneous instrument metadata/filters, venue ticker, validated OI measurement/units, complete fresh depth and verified event clearance for the same instrument and cutoff.",
            "Strict spread observations retain raw event-time cadence; C05 periodic endpoints are research diagnostics and do not change C02.",
            "Date-matched historical funding/fees and higher-frequency observed execution or defensible calibrated fill evidence.",
            "Representative historical selector/cohorts, independent later-window R1 controls/horizons and R2 uncertainty with purged overlapping outcomes."],
        "next_gate": "Owner supplies original G feeds and H artifacts for a bounded matched historical interval; independently review strict admissions and R0 friction feasibility before R1/R2 qualification."}
    packet["packet_sha256"] = config_hash(packet)
    return packet


def _case_excerpt(case):
    """Keep the human report readable; full source inventories stay in JSON."""
    if case is None:
        return None
    result = {key: case[key] for key in ("symbol", "strategy", "side", "setup_id", "as_of",
        "reasons", "c02_reasons", "eligible_trade") if key in case}
    def context(value):
        return {key: value[key] for key in ("context_id", "classification", "bias", "readiness",
            "adx_1h", "atr_5m", "atr_15m", "threshold_status") if key in value}
    def bar(value):
        if value is None:
            return None
        return {key: value[key] for key in ("source_record_id", "open_time", "event_time", "available_at",
            "open", "high", "low", "close", "fidelity") if key in value}
    if "frozen_setup" in case:
        setup = case["frozen_setup"]
        result["frozen_snapshot"] = setup["snapshot"]
        result["frozen_levels"] = setup["levels"]
        result["timeline"] = []
        for row in case["timeline"]:
            excerpt = {key: row[key] for key in ("as_of", "state", "notes", "c02_reasons", "last_bar_open") if key in row}
            if "context" in row:
                excerpt["context"] = context(row["context"])
            for name in ("source_bar", "selected_bar", "confirmation_bar"):
                if row.get(name):
                    excerpt[name] = bar(row[name])
            result["timeline"].append(excerpt)
    else:
        result["context"] = context(case["context"])
        result["source_bar"] = bar(case["source_bar"])
    return result


def render_packet(packet: dict[str, Any]) -> str:
    f = packet["funnel"]
    lines = ["# C05-J integrated economic research decision packet", "",
        f"Decision: **{packet['decision']}**. T1/R1/B1 remain **RESEARCH_ONLY**; phase credit 45%.", "",
        f"Packet SHA-256: `{packet['packet_sha256']}`", "",
        f"Verified normalized historical rows: {packet['provenance']['normalized_historical_rows']:,}. "
        f"Symbol windows: {f['symbol_evaluation_windows']:,}; eligible: {f['eligible_symbol_windows']:,}; "
        f"strict candidates: {f['strict_candidate_decisions']}; executable historical trades: 0.", "",
        f"Price-only frozen formations: {f['price_only_formations']}; these never enter the trade denominator.", "",
        "| C02 reason | Symbol windows vetoed |", "|---|---:|"]
    lines += [f"| {reason} | {count:,} |" for reason, count in sorted(f["eligibility_vetoes_by_symbol_window"].items())]
    lines += ["", "| Policy | Strict candidates | Assessment |", "|---|---:|---|"]
    lines += [f"| {key} | {row['strict_candidates']} | {row['decision']} |" for key, row in sorted(packet["policy_assessments"].items())]
    for stage, report in packet["stages"].items():
        lines += ["", f"{stage}: **{report['status']}**. {report['reason']}"]
    for label in ("market_case", "no_trade_case"):
        case = packet["cases"][label]
        lines += ["", f"## {label.replace('_', ' ')}", "", "```json", __import__('json').dumps(_case_excerpt(case), indent=2, sort_keys=True), "```"]
    lines += ["", "## B1 friction sensitivity", "", packet["stages"]["R0"]["friction_sensitivity"]["formula"], "",
              "All fee/friction scenarios are declared models. Source-backed price geometry is diagnostic; no fill, return or profitability is certified.", "",
              "## Remaining evidence", ""]
    lines += [f"- {reason}" for reason in packet["remaining_evidence"]]
    lines += ["", packet["next_gate"], "", "Full chronology, source IDs/hashes, original-feed evidence checks, sensitivity rows, E0/E1/E2 outcomes and uncertainty are in the accompanying JSON packet.", ""]
    return "\n".join(lines)
