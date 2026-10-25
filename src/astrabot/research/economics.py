"""Conservative price/quantity mapper; successful ladder scenario, not expectancy."""
from decimal import Decimal as D, ROUND_CEILING, ROUND_FLOOR
from fractions import Fraction
from math import lcm

from astrabot.contracts import FixedGeometry, scenario_net_rr
from astrabot.data.models import InstrumentMetadata, config_hash
from astrabot.research.models import CostProfile, ResearchAccount, ScenarioEconomics


def rounded(price: D, tick: D, *, up: bool) -> D:
    return (price / tick).to_integral_value(rounding=ROUND_CEILING if up else ROUND_FLOOR) * tick


def profile_hash(profile: CostProfile) -> str:
    return config_hash(profile.model_dump(mode="json"))


def evaluate_economics(*, side: str, entry: D, geometry: FixedGeometry,
                       profile: CostProfile, metadata: InstrumentMetadata,
                       account: ResearchAccount, requested_quantity: D,
                       midpoint_screen: bool = False,
                       notional_price: D | None = None) -> tuple[ScenarioEconomics | None, tuple[str, ...]]:
    """Cap only downward. Entry already includes spread and permitted slippage.

    Fees use each route's actual assumed price. Funding is a conservative debit
    for the permitted hold, never an assumed credit. No fill or P&L is invented.
    """
    sign = D(1) if side == "LONG" else D(-1)
    # SHORT has its worst stop loss at the lower bound, but its largest
    # admitted notional at the upper bound. Keep these two stresses separate.
    notional_price = notional_price if notional_price is not None else entry
    if notional_price < entry:
        return None, ("NOTIONAL_PRICE_BOUND_INVALID",)
    stop = geometry.original_stop
    d = sign * (entry - stop)
    if d <= 0:
        return None, ("STOP_WRONG_SIDE",)
    if any(sign * (t.price - entry) <= 0 for t in geometry.targets):
        return None, ("TARGET_WRONG_SIDE",)
    if any(sign * (b.price - a.price) <= 0 for a, b in zip(geometry.targets, geometry.targets[1:])):
        return None, ("TARGET_ORDER_INVALID",)
    if (not metadata.price_tick or not metadata.quantity_step or metadata.contract_size != 1
            or requested_quantity <= 0):
        return None, ("FILTER_OR_QUANTITY_UNAVAILABLE",)
    prices = (entry, stop, *(t.price for t in geometry.targets))
    if any(p % metadata.price_tick for p in prices):
        return None, ("PRICE_TICK_INVALID",)
    for f in metadata.filters:
        if f.filter_type == "PRICE_FILTER" and any(
            (f.min_value is not None and p < f.min_value)
            or (f.max_value and p > f.max_value)
            or (f.step_size and p % f.step_size) for p in prices
        ):
            return None, ("PRICE_FILTER_BOUND",)

    gross_reward = sum((t.fraction * sign * (t.price-entry) for t in geometry.targets), D(0))
    entry_fee = entry * profile.entry_fee_rate
    win_cost = (entry_fee + sum((t.fraction*t.price*profile.ordinary_exit_fee_rate
                                for t in geometry.targets), D(0))
                + profile.ordinary_exit_spread_per_unit + profile.ordinary_exit_slippage_per_unit
                + profile.funding_per_unit)
    loss_cost = (entry_fee + stop*profile.stop_exit_fee_rate + profile.stop_spread_per_unit
                 + profile.stop_slippage_per_unit + profile.funding_per_unit)
    gross_r = gross_reward / d
    rr = scenario_net_rr(gross_r, d, win_cost, loss_cost)
    mid_rr = None
    reasons = []
    if midpoint_screen:
        first = geometry.targets[0]
        mid_cost = (entry_fee + first.price*profile.ordinary_exit_fee_rate
                    + profile.ordinary_exit_spread_per_unit + profile.ordinary_exit_slippage_per_unit
                    + profile.funding_per_unit)
        mid_rr = scenario_net_rr(sign*(first.price-entry)/d, d, mid_cost, loss_cost)
        if mid_rr < D("1.5"):
            reasons.append("MIDPOINT_SCREEN_NET_RR_BELOW_MINIMUM")
    if rr < D("1.5"):
        reasons.append("SCENARIO_NET_RR_BELOW_MINIMUM")

    ceiling = max(D(0), min(account.equity_usdt*D(".0025"),
                            account.equity_usdt*D(".005")-account.pending_open_risk_usdt))
    notional_capacity = max(D(0), account.equity_usdt*2-account.pending_open_notional_usdt)
    raw = min(requested_quantity, ceiling/(d+loss_cost), notional_capacity/notional_price,
              account.isolated_margin_available_usdt*2/notional_price)
    for f in metadata.filters:
        if f.filter_type in ("LOT_SIZE", "MARKET_LOT_SIZE") and f.max_value:
            raw = min(raw, f.max_value)
    # Reduce to a total size whose exact policy fractions are all venue steps.
    denominator = lcm(*(Fraction(t.fraction).denominator for t in geometry.targets))
    steps = (metadata.quantity_step, *(f.step_size for f in metadata.filters
        if f.filter_type in ("LOT_SIZE", "MARKET_LOT_SIZE") and f.step_size))
    scale = D(10) ** max(max(0, -s.as_tuple().exponent) for s in steps)
    common_step = D(lcm(*(int(s*scale) for s in steps))) / scale
    quantum = common_step * denominator
    quantity = rounded(raw, quantum, up=False)
    target_quantities = tuple(quantity*t.fraction for t in geometry.targets)
    minimum_qty = max((metadata.minimum_quantity or D(0), *(f.min_value for f in metadata.filters
        if f.filter_type in ("LOT_SIZE", "MARKET_LOT_SIZE") and f.min_value is not None)))
    minimum_notional = max((metadata.minimum_notional or D(0), *(f.min_value for f in metadata.filters
        if f.filter_type == "MIN_NOTIONAL" and f.min_value is not None)))
    if (quantity <= 0 or quantity < minimum_qty or quantity*entry < minimum_notional
            or any(q < minimum_qty or q*t.price < minimum_notional
                   for q, t in zip(target_quantities, geometry.targets))):
        reasons.append("QUANTITY_OR_TARGET_FRACTION_INFEASIBLE")
    if not account.reconciled:
        reasons.append("ACCOUNT_UNRECONCILED")
    if account.daily_entry_halt:
        reasons.append("DAILY_ENTRY_HALT")
    if account.occupied_slots >= 2 or metadata.symbol in account.occupied_symbols:
        reasons.append("POSITION_CAPACITY_UNAVAILABLE")
    result = ScenarioEconomics(gross_price_r=gross_r, cost_r=loss_cost/d, scenario_net_rr=rr,
        midpoint_screen_net_rr=mid_rr, win_cost_per_unit=win_cost, loss_cost_per_unit=loss_cost,
        proposed_quantity=quantity, target_quantities=target_quantities,
        proposed_modeled_loss_usdt=quantity*(d+loss_cost), account_risk_ceiling_usdt=ceiling)
    return result, tuple(reasons)
