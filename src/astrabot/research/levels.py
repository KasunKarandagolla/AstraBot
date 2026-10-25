"""Narrow v1.5 causal levels; this is not a qualified general SMC provider.

The strict 3-left/3-right rule is the explicit C03 BUILD exception. Lean's
streaming strict-pivot source confirms the comparison semantics; a small Python
implementation avoids importing a second C# trading engine. Availability is
stamped at confirmation, never at the retrospectively identified pivot.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Sequence

from pydantic import Field, model_validator

from astrabot.contracts import Contract, ID, Positive, UTC
from astrabot.data.models import Candle, Fidelity, stable_id
from astrabot.research.evidence import history

VERSION = "c03.levels.v1"


class StructuralLevel(Contract):
    level_id: ID
    symbol: ID
    instrument_id: ID
    kind: ID
    relevance: Literal["RESISTANCE", "SUPPORT", "BOTH"]
    source_ids: tuple[ID, ...] = Field(min_length=1)
    timeframe: Literal["5m", "15m", "1h", "4h"]
    event_time: UTC
    available_at: UTC
    price: Positive
    version: ID = VERSION
    fidelity: Fidelity
    invalidated: bool = False
    invalidation_policy: ID

    @model_validator(mode="after")
    def causal_level(self):
        if self.available_at < self.event_time:
            raise ValueError("level cannot be available before its event")
        return self


def confirmed_swings(
    candles: Sequence[Candle], *, symbol: str, instrument_id: str,
    as_of: datetime,
) -> tuple[StructuralLevel, ...]:
    """Return all finite, confirmed 1H extrema in source order.

    The caller selects the nearest opposing price from this inventory. Old
    broken levels remain eligible only on the correct side of a future entry,
    as expressly permitted by v1.5. Equal highs/lows never qualify.
    """
    rows = history(candles, interval="1h", symbol=symbol,
                   instrument_id=instrument_id, as_of=as_of, minimum=0)
    result = []
    for index in range(3, len(rows) - 3):
        window = rows[index - 3:index + 4]
        pivot = rows[index]
        others = (*window[:3], *window[4:])
        available = max(c.available_at for c in window)
        sources = tuple(c.source_record_id for c in window)
        for kind, relevance, price, qualifies in (
            ("SWING_HIGH", "RESISTANCE", pivot.high,
             all(pivot.high > c.high for c in others)),
            ("SWING_LOW", "SUPPORT", pivot.low,
             all(pivot.low < c.low for c in others)),
        ):
            if qualifies:
                result.append(StructuralLevel(
                    level_id=stable_id(VERSION, instrument_id, kind, *sources),
                    symbol=symbol, instrument_id=instrument_id, kind=kind,
                    relevance=relevance, source_ids=sources, timeframe="1h",
                    event_time=pivot.close_time, available_at=available,
                    price=price, fidelity=("SYNTHETIC_FIXTURE" if any(
                        c.fidelity == "SYNTHETIC_FIXTURE" for c in window
                    ) else "BAR_DERIVED_APPROX"),
                    invalidation_policy="V15_CORRECT_SIDE_AT_SELECTION_NO_AUTOMATIC_BREAK_REMOVAL",
                ))
    return tuple(result)
