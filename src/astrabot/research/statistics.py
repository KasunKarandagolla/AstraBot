"""Small, deterministic statistics for sparse, correlated research samples."""
from __future__ import annotations

from collections import defaultdict
from math import isfinite
from random import Random
from statistics import mean, median
from typing import Iterable, Mapping, Sequence


def effective_sample_size(values: Sequence[float]) -> float:
    """Kish effective n for non-negative observation weights."""
    weights = [float(x) for x in values if isfinite(float(x)) and float(x) >= 0]
    total = sum(weights)
    squares = sum(x * x for x in weights)
    return total * total / squares if squares else 0.0


def drawdown(values: Sequence[float]) -> float:
    """Maximum peak-to-trough loss in a unit-starting cumulative net-R path."""
    equity = peak = 0.0
    worst = 0.0
    for value in values:
        equity += float(value)
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return worst


def profit_factor(values: Sequence[float]) -> float | None:
    gains = sum(float(x) for x in values if float(x) > 0)
    losses = -sum(float(x) for x in values if float(x) < 0)
    if losses == 0:
        return None if gains == 0 else float("inf")
    return gains / losses


def cluster_bootstrap(
    observations: Iterable[Mapping[str, object]],
    *,
    block_key: str = "market_time_block",
    value_key: str = "net_r",
    replicates: int = 2000,
    seed: int = 20261025,
) -> dict[str, object]:
    """Resample shared market-time blocks, keeping simultaneous symbols together.

    Each sampled block contributes its mean return. All rows for the same block
    are kept together, so altcoins exposed to the same market move are not
    treated as independent bootstrap draws.
    """
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in observations:
        block = str(row[block_key])
        value = float(row[value_key])
        if isfinite(value):
            grouped[block].append(value)
    blocks = sorted(grouped)
    n = len(blocks)
    trade_count = sum(len(grouped[b]) for b in blocks)
    if n == 0:
        return {"method": "JOINT_MARKET_TIME_BLOCK", "seed": seed,
                "replicates": replicates, "trade_count": 0, "block_count": 0,
                "effective_sample_size": 0, "mean_net_r": None,
                "ci95": None, "warning": "NO_QUALIFIED_OUTCOMES"}
    block_means = [mean(grouped[b]) for b in blocks]
    point = mean(block_means)
    if n < 2 or replicates < 1:
        return {"method": "JOINT_MARKET_TIME_BLOCK", "seed": seed,
                "replicates": replicates, "trade_count": trade_count,
                "block_count": n, "effective_sample_size": n,
                "mean_net_r": point, "ci95": None,
                "warning": "FEWER_THAN_TWO_MARKET_TIME_BLOCKS" if n < 2 else "NO_BOOTSTRAP_REPLICATES"}
    rng = Random(seed)
    samples = []
    for _ in range(replicates):
        samples.append(mean(block_means[rng.randrange(n)] for _ in range(n)))
    samples.sort()
    low = samples[int(0.025 * (replicates - 1))]
    high = samples[int(0.975 * (replicates - 1))]
    return {"method": "JOINT_MARKET_TIME_BLOCK", "seed": seed,
            "replicates": replicates, "trade_count": trade_count,
            "block_count": n, "effective_sample_size": n,
            "mean_net_r": point, "ci95": [low, high], "warning": None}


def summarize(values: Sequence[float], *, time_blocks: Sequence[str] = ()) -> dict[str, object]:
    finite = [float(x) for x in values if isfinite(float(x))]
    block_count = len(set(time_blocks)) if time_blocks else 0
    positive = sum(x > 0 for x in finite)
    negative = sum(x < 0 for x in finite)
    flat = len(finite) - positive - negative
    pf = profit_factor(finite)
    return {
        "n": len(finite),
        "market_time_blocks": block_count,
        "effective_sample_size": block_count if block_count else len(finite),
        "mean_net_r": mean(finite) if finite else None,
        "median_net_r": median(finite) if finite else None,
        "wins": positive,
        "losses": negative,
        "breakeven": flat,
        "max_drawdown_r": drawdown(finite) if finite else None,
        "profit_factor": pf if pf is None or isfinite(pf) else "UNDEFINED_NO_LOSSES",
        "low_sample_warning": "FEWER_THAN_30_MARKET_TIME_BLOCKS" if block_count < 30 else None,
    }


def matched_controls(
    opportunities: Sequence[Mapping[str, object]],
    *,
    seed: int = 20261025,
    embargo_hours: int = 12,
) -> dict[str, str]:
    """Choose non-trigger controls from contemporaneous metadata only.

    Required fields are symbol, regime, cohort, event_time, is_trigger and
    window_id. Outcome fields are deliberately ignored. Each opportunity gets
    at most one stable control outside its overlapping-outcome embargo.
    """
    from datetime import datetime, timedelta
    from astrabot.data.models import stable_id

    rows = list(opportunities)
    chosen: dict[str, str] = {}
    for trigger in sorted((r for r in rows if bool(r["is_trigger"])),
                          key=lambda r: (str(r["event_time"]), str(r["window_id"]))):
        t = datetime.fromisoformat(str(trigger["event_time"]).replace("Z", "+00:00"))
        candidates = []
        for row in rows:
            if bool(row["is_trigger"]):
                continue
            if any(row.get(k) != trigger.get(k) for k in ("symbol", "regime", "cohort")):
                continue
            at = datetime.fromisoformat(str(row["event_time"]).replace("Z", "+00:00"))
            if at > t or abs((at - t).total_seconds()) < embargo_hours * 3600:
                continue
            candidates.append(row)
        if candidates:
            candidates.sort(key=lambda r: stable_id(seed, trigger["window_id"], r["window_id"]))
            chosen[str(trigger["window_id"])] = str(candidates[0]["window_id"])
    return chosen
