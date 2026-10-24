#!/usr/bin/env python3
"""Offline probe: exact pinned vendor AST functions, fake exchange boundary.

Not a full Freqtrade package test. No vendor modules imported, no network.
Run: python probe_freqtrade_vendor_hooks.py /path/to/freqtrade
"""
from __future__ import annotations

import ast
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from functools import wraps
from types import SimpleNamespace
from typing import Any, Callable, TypeVar, cast

PIN = "1f394eaebc2f46a83d26971388628707802f8602"
HASHES = {
    "freqtrade/freqtradebot.py": "6fb6c7bcc00c14412c65978de80480e1d8a5c3dd8161f1d6f33d60bea364c5e4",
    "freqtrade/rpc/rpc.py": "663ef3d187fae9d7a9fcf63bf5b991bba6d7126071c4b8863b2f5a185a6dd10a",
    "freqtrade/strategy/strategy_wrapper.py": "791ac142aff61fe8d8f1cbbbf43e8b9b626eaa39b158c7f73fbd706b4516f464",
}


class ExchangeBoundary(Exception):
    pass


class RPCDenied(Exception):
    pass


class Field:
    def __eq__(self, other):
        return True

    def is_(self, other):
        return True


class FakeTrade:
    is_open = pair = Field()
    found = None

    @classmethod
    def get_trades(cls, *args):
        return SimpleNamespace(first=lambda: cls.found)

    @staticmethod
    def get_open_trade_count():
        return 0


def main(root: Path):
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip() == PIN
    for rel, expected in HASHES.items():
        assert hashlib.sha256((root / rel).read_bytes()).hexdigest() == expected, rel
    logger = logging.getLogger("vendor-probe")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    scope = dict(Any=Any, Callable=Callable, TypeVar=TypeVar, cast=cast, deepcopy=deepcopy,
                 wraps=wraps, F=TypeVar("F", bound=Callable[..., Any]), logger=logger,
                 datetime=datetime, UTC=UTC, StrategyError=RuntimeError, Trade=FakeTrade,
                 RPCException=RPCDenied,
                 SignalDirection=SimpleNamespace(LONG="long", SHORT="short"))

    def extract(rel, names):
        tree = ast.parse((root / rel).read_text())
        nodes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in names]
        assert {n.name for n in nodes} == set(names)
        for n in nodes:
            # Only annotation evaluation changes; complete original function bodies retained.
            n.decorator_list = []
        future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
        module = ast.fix_missing_locations(ast.Module(body=[future] + nodes, type_ignores=[]))
        exec(compile(module, str(root / rel), "exec"), scope)

    extract("freqtrade/strategy/strategy_wrapper.py", ["__format_traceback", "strategy_safe_wrapper"])
    extract("freqtrade/freqtradebot.py", ["execute_entry"])
    extract("freqtrade/rpc/rpc.py", ["_rpc_force_entry"])
    cases = []

    def run(mode, outcome, force=False, existing=False):
        seen = {"callback_calls": 0, "create_order_calls": 0}

        def confirm(**kwargs):
            seen["callback_calls"] += 1
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        def create_order(**kwargs):
            seen["create_order_calls"] += 1
            raise ExchangeBoundary  # Stop exactly before external side effect.

        bot = SimpleNamespace(
            strategy=SimpleNamespace(order_time_in_force={"entry": "IOC"},
                                     order_types={"entry": "limit"}, confirm_trade_entry=confirm,
                                     position_adjustment_enable=True),
            get_valid_enter_price_and_stake=lambda *a: (100, 10, 1),
            handle_similar_open_order=lambda *a: False,
            exchange=SimpleNamespace(create_order=create_order),
        )
        bot.execute_entry = lambda *a, **kw: scope["execute_entry"](bot, *a, **kw)
        try:
            if force:
                from contextlib import nullcontext
                FakeTrade.found = SimpleNamespace(is_short=False, has_open_orders=False) if existing else None
                rpc = SimpleNamespace(_freqtrade=bot, _config={"max_open_trades": 5},
                                      _force_entry_validations=lambda *a: None)
                bot._exit_lock = nullcontext()
                scope["_rpc_force_entry"](rpc, "BTC/USDT:USDT", 100, stake_amount=10)
            else:
                bot.execute_entry("BTC/USDT:USDT", 10, mode=mode)
        except ExchangeBoundary:
            pass
        except RPCDenied:
            assert force and outcome is False and not existing
        expected_call = 1 if mode == "initial" else 0
        assert seen["callback_calls"] == expected_call, seen
        expected_create = 0 if mode == "initial" and outcome is False else 1
        assert seen["create_order_calls"] == expected_create, seen
        cases.append(dict(mode=mode, outcome=type(outcome).__name__ if isinstance(outcome, Exception) else outcome,
                          force=force, existing=existing, **seen))

    for outcome in (False, True, ValueError("approval failed"), RuntimeError("approval failed")):
        run("initial", outcome)
    run("pos_adjust", False)
    run("replace", False)
    run("initial", False, force=True)
    run("initial", ValueError("approval failed"), force=True)
    run("pos_adjust", False, force=True, existing=True)
    print(json.dumps({"classification": "FAKE_TESTED", "vendor_source_verified": True,
                      "method": "AST-extracted complete exact pinned function bodies; fake exchange boundary; RPC validations stubbed",
                      "full_vendor_suite_run": False, "commit": PIN, "python": sys.version.split()[0],
                      "source_sha256": HASHES, "passed": len(cases), "cases": cases}, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
