"""C01 deterministic FAKE ONLY. No SDK, URL, key, credential or network support.

SQLite/JSON is a tiny fault-test ledger, not a production persistence proposal.
Single-row transactions deliberately serialize account claims with CAS; no
transaction spans fake venue I/O. Venue truth uses a separate durable database.
"""
from __future__ import annotations
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal as D
import json
import sqlite3
from pathlib import Path

from astrabot.contracts import (AccountReservationV15, BoundedGeometry, EconomicsV15,
    FixedGeometry, OrderIntentV15, OrderParameters, SetupSnapshotV15, TradeAuthorizationV15,
    scenario_net_rr)

TERMINAL = {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}


def iso(t):
    return t.isoformat()


def dt(t):
    return datetime.fromisoformat(t)


class FakeClock:
    def __init__(self, now):
        self.now = now

    def advance(self, **delta):
        self.now += timedelta(**delta)
        return self.now


class State:
    def __init__(self, path, initial):
        self.path = str(path)
        with closing(self.connection()) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO state VALUES(1, ?)", (json.dumps(initial),))

    def connection(self):
        return sqlite3.connect(self.path, timeout=10)

    def read(self):
        with closing(self.connection()) as db:
            return json.loads(db.execute("SELECT payload FROM state WHERE id=1").fetchone()[0])

    def change(self, action):
        with closing(self.connection()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            state = json.loads(db.execute("SELECT payload FROM state WHERE id=1").fetchone()[0])
            result = action(state)
            db.execute("UPDATE state SET payload=? WHERE id=1", (json.dumps(state),))
            return result

    def assert_no_transaction(self):
        # Called from venue I/O hook; a leaked writer lock fails immediately.
        with closing(sqlite3.connect(self.path, timeout=0)) as db:
            db.execute("BEGIN IMMEDIATE")
            db.rollback()


class FakeVenue:
    """Whole-position stops and reduce-only are assumptions under test, not Binance proof."""
    def __init__(self, path, clock):
        self.clock = clock
        self.state = State(path, {"orders": {}, "fills": {}, "positions": {}, "writes": []})
        self.connected = True
        self.io_hook = lambda: None
        self.stop_ack_delay_ms = 0

    def _io(self):
        self.io_hook()
        if not self.connected:
            raise ConnectionError("fake disconnected")

    def submit(self, client_id, params: OrderParameters, *, result="ACKNOWLEDGED", lifecycle_id):
        self._io()
        if params.kind == "STOP_MARKET":
            self.clock.advance(milliseconds=self.stop_ack_delay_ms)
        def action(s):
            if client_id in s["orders"]:
                raise AssertionError("fake rejects duplicate client IDs")
            s["writes"].append({"client_id": client_id, "params": params.model_dump(mode="json")})
            status = "REJECTED" if result == "REJECTED" else "ACKNOWLEDGED"
            prefix = "algo-" if params.kind == "STOP_MARKET" else "ordinary-"
            s["orders"][client_id] = {"params": params.model_dump(mode="json"), "status": status,
                "id": prefix + client_id, "lifecycle_id": lifecycle_id, "filled": "0", "visible": result != "ABSENT"}
            return s["orders"][client_id]["id"]
        oid = self.state.change(action)
        if result == "UNKNOWN":
            raise TimeoutError("fake lost acknowledgement")
        return oid

    def snapshot(self):
        self._io()
        return self.state.read()

    def cancel(self, client_id, *, unknown=False):
        self._io()
        def action(s):
            order = s["orders"][client_id]
            if order["status"] not in TERMINAL:
                order["status"] = "UNKNOWN_CANCEL" if unknown else "CANCELLED"
        self.state.change(action)
        if unknown:
            raise TimeoutError("fake cancel unknown")

    def fill(self, client_id, fill_id, quantity, price, *, at=None, late=False):
        """Inject venue-confirmed execution; distinct from local detection time."""
        def action(s):
            if fill_id in s["fills"]:
                return D(s["fills"][fill_id]["quantity"])
            order = s["orders"][client_id]
            p = order["params"]
            if order["status"] in TERMINAL and not late:
                return D(0)
            q, px = D(quantity), D(price)
            if q <= 0 or px <= 0:
                raise ValueError("positive fill required")
            key = order["lifecycle_id"]
            position = D(s["positions"].get(key, "0"))
            if p["reduce_only"] or p["close_position"]:
                # Reduce-side must match actual position; never reverse.
                reducing = (position > 0 and p["side"] == "SELL") or (position < 0 and p["side"] == "BUY")
                q = min(q, abs(position)) if reducing else D(0)
                if not p["close_position"]:
                    q = min(q, max(D(0), D(p["quantity"]) - D(order["filled"])))
            else:
                q = min(q, D(p["quantity"]) - D(order["filled"]))
            if p["kind"] == "LIMIT" and ((p["side"] == "BUY" and px > D(p["price"]))
                or (p["side"] == "SELL" and px < D(p["price"]))):
                raise ValueError("fill violates adverse limit price")
            signed = q if p["side"] == "BUY" else -q
            s["positions"][key] = str(position + signed)
            order["filled"] = str(D(order["filled"]) + q)
            order["status"] = "FILLED" if p["close_position"] or D(order["filled"]) >= D(p["quantity"]) else "PARTIAL"
            s["fills"][fill_id] = {"client_id": client_id, "lifecycle_id": key, "quantity": str(q),
                "price": str(px), "at": iso(at or self.clock.now), "entry": not (p["reduce_only"] or p["close_position"])}
            return q
        return self.state.change(action)

    def price_touch(self, _price):
        # Deliberately no fill: a price touch is not execution evidence.
        return None


class FakeOwner:
    def __init__(self, path, venue, clock, *, equity=D("10000")):
        self.clock, self.venue = clock, venue
        self.ledger = State(path, {"version": 0, "equity": str(equity), "baseline": str(equity),
            "utc_day": clock.now.date().isoformat(), "daily_halt": False, "fault_halt": False,
            "reconciled": False, "approvals": {}, "setups": {}, "consumed": [], "nonces": [],
            "used_setups": [], "intents": {}, "reservations": {}, "positions": {},
            "exit_requests": {}, "faults": [], "latencies": {}})
        self.ready = False  # process-local restart barrier, always starts closed
        self.venue.io_hook = self.ledger.assert_no_transaction

    def register_approval(self, auth, setup):
        """FAKE authenticated boundary: fixture owner only; no real auth implementation."""
        if (auth.owner.owner_ref, auth.owner.authentication_evidence_ref, auth.owner.mfa_evidence_ref) != ("fake-owner", "fake-auth", "fake-mfa"):
            raise ValueError("fake owner verification failed")
        if auth.immutable_hash() != auth.approved_immutable_hash:
            raise ValueError("approval payload mismatch")
        if auth.setup_id != setup.setup_id or auth.setup_expires_at > setup.expires_at:
            raise ValueError("authorization must bind original setup identity/expiry")
        def action(s):
            if auth.plan_id in s["approvals"] or setup.setup_id in s["used_setups"]:
                raise ValueError("approval/setup already registered or used")
            s["approvals"][auth.plan_id] = auth.model_dump(mode="json")
            if setup.setup_id in s["setups"] and s["setups"][setup.setup_id] != setup.model_dump(mode="json"):
                raise ValueError("frozen setup altered")
            s["setups"][setup.setup_id] = setup.model_dump(mode="json")
        self.ledger.change(action)

    def claim(self, auth, *, quantity, quote, trigger_at, expected_version=None, callback=lambda: True,
              readiness=True, event_ok=True, risk_ok=True, geometry=None):
        """Consume approval, reserve capacity, persist intent atomically; ZERO venue I/O."""
        try:
            if callback() is not True or not all((self.ready, readiness, event_ok, risk_ok)):
                return None
            # Revalidate even objects produced with Pydantic's unchecked model_copy.
            auth = TradeAuthorizationV15.model_validate_json(auth.model_dump_json())
            auth.check_submission(now=self.clock.now, trigger_at=trigger_at, quote=quote, quantity=quantity)
            g = auth.geometry
            if isinstance(g, BoundedGeometry):
                # Resolve exact approved formula from supplied anchor evidence, never caller geometry.
                if geometry is None:
                    return None
                g = g.resolve(entry=quote, side=auth.side, now=self.clock.now, **geometry)
            worst = auth.entry_max if auth.side == "LONG" else auth.entry_min
            distance = abs(worst - g.original_stop)
            modeled_loss = quantity * (distance + auth.stop_cost_per_unit)
            gross = sum(t.fraction * abs(t.price - worst) for t in g.targets) / distance
            minimum = auth.geometry.minimum_scenario_net_rr if isinstance(auth.geometry, BoundedGeometry) else D("1.5")
            if (quantity * worst > auth.notional_max
                or isinstance(auth.geometry, BoundedGeometry) and distance > auth.geometry.max_stop_distance):
                return None
            if modeled_loss > auth.approved_max_risk_usdt or scenario_net_rr(gross, distance, auth.target_cost_per_unit, auth.stop_cost_per_unit) < minimum:
                return None
            def action(s):
                if not s["reconciled"] or s["daily_halt"] or s["fault_halt"]:
                    return None
                if expected_version is not None and s["version"] != expected_version:
                    return None
                stored = s["approvals"].get(auth.plan_id)
                if stored != auth.model_dump(mode="json") or auth.plan_id in s["consumed"] or auth.one_use_nonce in s["nonces"] or auth.setup_id in s["used_setups"]:
                    return None
                setup = SetupSnapshotV15.model_validate_json(json.dumps(s["setups"][auth.setup_id]))
                if (setup.state not in ("ARMED", "CONFIRMED") or setup.expires_at <= self.clock.now
                    or auth.setup_expires_at > setup.expires_at
                    or setup.symbol != auth.symbol or setup.side != auth.side
                    or setup.strategy_version != auth.strategy_version or setup.strategy_policy_hash != auth.strategy_policy_hash
                    or tuple(a.anchor_id for a in setup.anchors) != auth.frozen_anchor_ids):
                    return None
                active = [r for r in s["reservations"].values() if r["status"] != "RELEASED"]
                equity = D(s["equity"])
                before_risk = sum((D(r["risk"]) for r in active), D(0))
                before_notional = sum((D(r["notional"]) for r in active), D(0))
                notional = quantity * worst
                if (auth.approved_max_risk_usdt > equity * D(".0025") or len(active) >= 2
                    or any(r["symbol"] == auth.symbol for r in active)
                    or before_risk + auth.approved_max_risk_usdt > equity * D(".005")
                    or before_notional + notional > equity * min(D(2), auth.leverage_max)):
                    return None
                reservation_id, intent_id = "res-" + auth.plan_id, "intent-" + auth.plan_id
                reservation = AccountReservationV15(reservation_id=reservation_id, plan_id=auth.plan_id,
                    equity_snapshot_id="fake-equity-" + str(s["version"]), equity_basis=equity,
                    risk_before=before_risk, risk_after=before_risk + auth.approved_max_risk_usdt,
                    notional_before=before_notional, notional_after=before_notional + notional,
                    effective_leverage=(before_notional + notional) / equity,
                    occupied_slots=len(active) + 1, available_slots=1 - len(active), status="PENDING",
                    version_before=s["version"], version=s["version"] + 1)
                request = OrderParameters(symbol=auth.symbol, side="BUY" if auth.side == "LONG" else "SELL",
                    kind="LIMIT", quantity=quantity, price=worst, time_in_force="IOC")
                intent = OrderIntentV15(intent_id=intent_id, lifecycle_id=auth.lifecycle_id, approval_id=auth.plan_id,
                    reservation_id=reservation_id, approved_hash=auth.approved_immutable_hash, request=request,
                    client_order_id="entry-" + auth.plan_id, persisted_at=self.clock.now, state="PERSISTED", action_version=0)
                s["consumed"].append(auth.plan_id)
                s["nonces"].append(auth.one_use_nonce)
                s["used_setups"].append(auth.setup_id)
                s["version"] += 1
                s["reservations"][reservation_id] = {"contract": reservation.model_dump(mode="json"),
                    "symbol": auth.symbol, "risk": str(auth.approved_max_risk_usdt), "notional": str(notional), "status": "PENDING"}
                s["intents"][intent_id] = intent.model_dump(mode="json")
                s["positions"][auth.lifecycle_id] = {"plan_id": auth.plan_id, "entry_id": intent.client_order_id,
                    "first_fill_at": None, "quantity": "0", "entry_quantity": "0", "fills": [],
                    "stop_ids": [], "tp_ids": [], "latch": None, "state": "SUPERVISED", "entry_terminal": False,
                    "risk_final": None, "d0": None, "geometry": g.model_dump(mode="json"), "version": 0,
                    "trigger_at": iso(trigger_at), "authorized_quantity": str(quantity)}
                return intent_id
            return self.ledger.change(action)
        except (ValueError, TypeError, KeyError):
            return None
        except Exception:
            # Callback/tool exceptions fail closed before claim, not vendor behavior.
            return None

    def submit(self, intent_id, *, result="ACKNOWLEDGED", quote=D("100"),
               readiness=True, event_ok=True, risk_ok=True):
        def before(s):
            i = OrderIntentV15.model_validate_json(json.dumps(s["intents"][intent_id]))
            p = s["positions"][i.lifecycle_id]
            if i.state != "PERSISTED" or p["latch"] or not self.ready:
                return None
            auth = TradeAuthorizationV15.model_validate_json(json.dumps(s["approvals"][p["plan_id"]]))
            try:
                auth.check_submission(now=self.clock.now, trigger_at=dt(p["trigger_at"]),
                    quote=quote, quantity=D(p["authorized_quantity"]))
                setup = s["setups"][auth.setup_id]
                active = [r for r in s["reservations"].values() if r["status"] != "RELEASED"]
                equity = D(s["equity"])
                if (not all((readiness, event_ok, risk_ok, s["reconciled"]))
                    or s["daily_halt"] or s["fault_halt"] or setup["state"] not in {"ARMED", "CONFIRMED"}
                    or self.clock.now >= dt(setup["expires_at"])
                    or sum(D(r["risk"]) for r in active) > equity * D(".005")
                    or auth.approved_max_risk_usdt > equity * D(".0025")
                    or sum(D(r["notional"]) for r in active) > equity * 2):
                    raise ValueError("fresh execution veto")
            except ValueError:
                s["intents"][intent_id] = i.advance("REJECTED").model_dump(mode="json")
                # No network attempt occurred: retain consumption but release capacity.
                s["reservations"][i.reservation_id]["status"] = "RELEASED"
                return None
            i = i.advance("SUBMITTED", submitted_at=self.clock.now)
            s["intents"][intent_id] = i.model_dump(mode="json")
            return i
        intent = self.ledger.change(before)
        if intent is None:
            return
        try:
            oid = self.venue.submit(intent.client_order_id, intent.request, result=result, lifecycle_id=intent.lifecycle_id)
            state = "REJECTED" if result == "REJECTED" else "ACKNOWLEDGED"
        except (TimeoutError, ConnectionError):
            oid, state = None, "UNKNOWN_SUBMISSION"
        def after(s):
            s["intents"][intent_id] = intent.advance(state, exchange_order_id=oid).model_dump(mode="json")
            if state == "UNKNOWN_SUBMISSION":
                s["reservations"][intent.reservation_id]["status"] = "UNKNOWN"
        self.ledger.change(after)

    def proves_unsubmitted_intent(self, intent_id, *, snapshot=None):
        """Prove a PERSISTED intent has not crossed the fake venue boundary.

        The proof combines C01's atomic pre-submit state with the authoritative
        fake venue write/order/fill/position store. Any missing or contradictory
        evidence fails closed. It is deliberately narrower than general retry.
        """
        state = self.ledger.read()
        raw = state.get("intents", {}).get(intent_id)
        if raw is None:
            return False
        try:
            intent = OrderIntentV15.model_validate_json(json.dumps(raw))
            auth_raw = state["approvals"][intent.approval_id]
            auth = TradeAuthorizationV15.model_validate_json(json.dumps(auth_raw))
            reservation_raw = state["reservations"][intent.reservation_id]
            reservation = AccountReservationV15.model_validate_json(
                json.dumps(reservation_raw["contract"]))
            position = state["positions"][intent.lifecycle_id]
            snapshot = snapshot if snapshot is not None else self.venue.snapshot()
        except (ConnectionError, KeyError, TypeError, ValueError):
            return False

        expected_side = "BUY" if auth.side == "LONG" else "SELL"
        expected_price = auth.entry_max if auth.side == "LONG" else auth.entry_min
        expected_client_id = "entry-" + auth.plan_id
        lifecycle_intents = [
            item for item in state["intents"].values()
            if item["lifecycle_id"] == intent.lifecycle_id
        ]
        lifecycle_orders = [
            order for order in snapshot["orders"].values()
            if order["lifecycle_id"] == intent.lifecycle_id
        ]
        lifecycle_fills = [
            fill for fill in snapshot["fills"].values()
            if fill["lifecycle_id"] == intent.lifecycle_id
        ]
        exact_unsubmitted_record = (
            intent.intent_id == intent_id == "intent-" + auth.plan_id
            and intent.state == "PERSISTED" and intent.submitted_at is None
            and intent.client_order_id == expected_client_id
            and intent.client_algo_id is None
            and intent.lifecycle_id == auth.lifecycle_id
            and intent.approval_id == auth.plan_id
            and intent.reservation_id == "res-" + auth.plan_id
            and intent.approved_hash == auth.approved_immutable_hash == auth.immutable_hash()
            and auth.plan_id in state["consumed"]
            and state["consumed"].count(auth.plan_id) == 1
            and state["nonces"].count(auth.one_use_nonce) == 1
            and state["used_setups"].count(auth.setup_id) == 1
            and reservation.reservation_id == intent.reservation_id
            and reservation.plan_id == auth.plan_id
            and reservation.status == "PENDING"
            and reservation_raw["status"] == "PENDING"
            and intent.request.symbol == auth.symbol
            and intent.request.side == expected_side
            and intent.request.kind == "LIMIT"
            and intent.request.time_in_force == "IOC"
            and intent.request.price == expected_price
            and intent.request.quantity == D(position["authorized_quantity"])
            and D(position["authorized_quantity"]) <= auth.quantity_max
            and position["plan_id"] == auth.plan_id
            and position["entry_id"] == expected_client_id
            and position["first_fill_at"] is None
            and D(position["quantity"]) == 0
            and len(lifecycle_intents) == 1
            and not lifecycle_orders and not lifecycle_fills
            and D(snapshot["positions"].get(intent.lifecycle_id, "0")) == 0
            and not any(write.get("client_id") == expected_client_id
                        for write in snapshot["writes"])
        )
        return bool(exact_unsubmitted_record)

    def reconnect(self, *, disagree=False):
        self.ready = False
        self.ledger.change(lambda s: s.update(reconciled=False))
        try:
            snapshot = self.venue.snapshot()
        except ConnectionError:
            return False
        if disagree:
            self.ledger.change(lambda s: s["faults"].append("SNAPSHOT_DISAGREEMENT"))
            return False
        self._apply_snapshot(snapshot)
        # Recover real exposure/protection before the entry barrier may reopen.
        recovered = self.ledger.read()
        pending_exits = recovered.get("exit_requests", {})
        for life, p in recovered["positions"].items():
            if D(p["quantity"]) > 0:
                request = pending_exits.get(life)
                if p["latch"] or (request and request.get("status") != "FLAT_RECONCILED"):
                    self.reduce(life, reason=(p["latch"] or {}).get("reason", "RECOVER_PENDING_EXIT"))
                elif not p["stop_ids"]:
                    self.protect(life)
        snapshot = self.venue.snapshot()
        proven_unsubmitted = {
            intent_id for intent_id, intent in self.ledger.read()["intents"].items()
            if intent["state"] == "PERSISTED"
            and self.proves_unsubmitted_intent(intent_id, snapshot=snapshot)
        }
        def consistent(s):
            absent_intent = any(
                intent["state"] in {"SUBMITTED", "UNKNOWN_SUBMISSION"}
                or (intent["state"] == "PERSISTED" and intent_id not in proven_unsubmitted)
                for intent_id, intent in s["intents"].items())
            unresolved_management = any(
                item.get("status") in {"PERSISTED", "SUBMITTED", "UNKNOWN_SUBMISSION"}
                and client_id not in snapshot["orders"]
                for client_id, item in s.get("management", {}).items())
            unowned = any(D(q) != 0 and life not in s["positions"] for life, q in snapshot["positions"].items())
            missing_protection = any(D(p["quantity"]) > 0 and not p["stop_ids"]
                for p in s["positions"].values())
            breach = any(reason in s["faults"] for reason in (
                "LATE_FILL_AFTER_FINALIZATION", "APPROVED_RISK_EXCEEDED",
                "MANAGEMENT_ORDER_CORRELATION_MISMATCH"))
            s["reconciled"] = not (absent_intent or unresolved_management
                or unowned or missing_protection or breach)
            if unowned:
                s["faults"].append("UNOWNED_POSITION")
                s["fault_halt"] = True
            return s["reconciled"]
        self.ready = self.ledger.change(consistent)
        self.timers()
        return self.ready

    def _apply_snapshot(self, snapshot):
        def action(s):
            for iid, i in s["intents"].items():
                order = snapshot["orders"].get(i["client_order_id"])
                if order and i["state"] in ("SUBMITTED", "UNKNOWN_SUBMISSION", "PERSISTED"):
                    i["state"] = "RECONCILED"
                    i["exchange_order_id"] = order["id"]
                    i["reconciliation_evidence"] = ["fake-correlated-boundary"]
            for client_id, intent in s.get("management", {}).items():
                order = snapshot["orders"].get(client_id)
                if not order:
                    continue
                if (order["lifecycle_id"] != intent["lifecycle_id"]
                    or order["params"] != intent["params"]):
                    s["faults"].append("MANAGEMENT_ORDER_CORRELATION_MISMATCH")
                    s["fault_halt"], s["reconciled"] = True, False
                    continue
                if intent.get("status") in {"PERSISTED", "SUBMITTED", "UNKNOWN_SUBMISSION"}:
                    intent["status"] = "RECONCILED"
                    intent["exchange_order_id"] = order["id"]
            for life, p in s["positions"].items():
                entries = [(fid, f) for fid, f in snapshot["fills"].items() if f["lifecycle_id"] == life and f["entry"]]
                new_fills = [fid for fid, _ in entries if fid not in p["fills"]]
                if entries:
                    earliest = min(dt(f["at"]) for _, f in entries)
                    p["first_fill_at"] = iso(min(earliest, dt(p["first_fill_at"]))) if p["first_fill_at"] else iso(earliest)
                p["quantity"] = str(abs(D(snapshot["positions"].get(life, "0"))))
                p["entry_quantity"] = str(sum((D(f["quantity"]) for _, f in entries), D(0)))
                if p["risk_final"] is not None and new_fills:
                    # Finalization proof was wrong or late discovery; preserve frozen
                    # denominator and halt. Production correction is not simulated.
                    s["faults"].append("LATE_FILL_AFTER_FINALIZATION")
                    s["fault_halt"], s["reconciled"] = True, False
                    p["state"] = "RECONCILING"
                p["fills"] = [fid for fid, _ in entries]
                valid_stops = [cid for cid in p["stop_ids"] if cid in snapshot["orders"]
                    and snapshot["orders"][cid]["visible"] and snapshot["orders"][cid]["status"] in {"ACKNOWLEDGED", "PARTIAL"}]
                if len(valid_stops) != len(p["stop_ids"]):
                    p["stop_ids"] = valid_stops
                order = snapshot["orders"].get(p["entry_id"])
                p["entry_terminal"] = bool(order and order["status"] in TERMINAL)
                if new_fills:
                    s["latencies"][life] = {"detected_at": iso(self.clock.now),
                        "exchange_first_fill_at": p["first_fill_at"], "stop_ack_at": None}
                if p["entry_terminal"] and p["risk_final"] is None and entries:
                    auth = TradeAuthorizationV15.model_validate_json(json.dumps(s["approvals"][p["plan_id"]]))
                    q = D(p["entry_quantity"])
                    weighted = sum(D(f["quantity"]) * D(f["price"]) for _, f in entries) / q
                    distance = abs(weighted - D(p["geometry"]["original_stop"]))
                    risk = q * (distance + auth.stop_cost_per_unit)
                    if risk > auth.approved_max_risk_usdt:
                        s["faults"].append("APPROVED_RISK_EXCEEDED")
                        s["fault_halt"] = True
                    p["risk_final"], p["d0"] = str(risk), str(distance)
        self.ledger.change(action)

    def detect_fills(self, *, stop_result="ACKNOWLEDGED"):
        snapshot = self.venue.snapshot()
        self._apply_snapshot(snapshot)
        for life, p in self.ledger.read()["positions"].items():
            stop_triggered = any(f["lifecycle_id"] == life and not f["entry"] and D(f["quantity"]) > 0
                and snapshot["orders"][f["client_id"]]["params"]["kind"] == "STOP_MARKET"
                for f in snapshot["fills"].values())
            if stop_triggered and not p["latch"]:
                self.latch(life, "STOP_TRIGGERED")
                p = self.ledger.read()["positions"][life]
            if D(p["quantity"]) > 0:
                if p["latch"]:
                    self.reduce(life)
                elif not p["stop_ids"]:
                    self.protect(life, result=stop_result)

    def protect(self, life, *, result="ACKNOWLEDGED"):
        s = self.ledger.read()
        p = s["positions"][life]
        auth = TradeAuthorizationV15.model_validate_json(json.dumps(s["approvals"][p["plan_id"]]))
        cid = "stop-" + life + "-" + str(p["version"])
        params = OrderParameters(symbol=auth.symbol, side="SELL" if auth.side == "LONG" else "BUY",
            kind="STOP_MARKET", stop_price=D(p["geometry"]["original_stop"]), close_position=True, working_type="MARK_PRICE")
        detected = dt(s["latencies"][life]["detected_at"])
        order, outcome = self._submit_management_order(life, cid, params, result=result)
        verified = bool(order and order["visible"] and order["status"] == "ACKNOWLEDGED"
            and outcome in {"ACKNOWLEDGED", "RECONCILED"})
        elapsed = self.clock.now - detected
        if verified and elapsed <= timedelta(seconds=2):
            def confirm_stop(s):
                s["positions"][life]["stop_ids"].append(cid)
                s["latencies"][life].update(stop_ack_at=iso(self.clock.now))
                s["management"][cid].update(status=outcome,
                    exchange_order_id=order["id"])
            self.ledger.change(confirm_stop)
        else:
            self.fault(life, "PROTECTION_DEADLINE" if elapsed > timedelta(seconds=2) else "MISSING_PROTECTION")

    def _management_intent(self, life, cid, params):
        def action(s):
            management = s.setdefault("management", {})
            existing = management.get(cid)
            expected_params = params.model_dump(mode="json")
            if existing:
                return (existing["lifecycle_id"] == life
                    and existing["params"] == expected_params)
            management[cid] = {"lifecycle_id": life,
                "params": expected_params, "status": "PERSISTED"}
            s["positions"][life]["version"] += 1
            return True
        return self.ledger.change(action)

    def _submit_management_order(self, life, cid, params, *, result="ACKNOWLEDGED"):
        """Persist, atomically claim and reconcile one existing client ID."""
        if not self._management_intent(life, cid, params):
            return None, "INCONSISTENT"
        try:
            snapshot = self.venue.snapshot()
        except ConnectionError:
            self.ledger.change(lambda state: state.update(reconciled=False))
            return None, "UNAVAILABLE"

        def correlated(order):
            return bool(order and order["lifecycle_id"] == life
                and order["params"] == params.model_dump(mode="json"))

        existing = snapshot["orders"].get(cid)
        if existing:
            if not correlated(existing):
                self.ledger.change(lambda state: (state.update(reconciled=False, fault_halt=True),
                    state["faults"].append("MANAGEMENT_ORDER_CORRELATION_MISMATCH")))
                return None, "INCONSISTENT"
            outcome = "REJECTED" if existing["status"] == "REJECTED" else "RECONCILED"
            self.ledger.change(lambda state: state["management"][cid].update(
                status=outcome, exchange_order_id=existing["id"]))
            return existing, outcome

        if any(write.get("client_id") == cid for write in snapshot["writes"]):
            self.ledger.change(lambda state: (state.update(reconciled=False),
                state["management"][cid].update(status="UNKNOWN_SUBMISSION")))
            return None, "UNKNOWN_SUBMISSION"

        def claim(state):
            intent = state["management"][cid]
            if intent["status"] != "PERSISTED":
                return False
            intent["status"] = "SUBMITTED"
            return True
        if not self.ledger.change(claim):
            return None, "UNRESOLVED"
        try:
            oid = self.venue.submit(cid, params, result=result, lifecycle_id=life)
        except (TimeoutError, ConnectionError):
            self.ledger.change(lambda state: (state.update(reconciled=False),
                state["management"][cid].update(status="UNKNOWN_SUBMISSION")))
            return None, "UNKNOWN_SUBMISSION"
        try:
            snapshot = self.venue.snapshot()
        except ConnectionError:
            self.ledger.change(lambda state: (state.update(reconciled=False),
                state["management"][cid].update(status="UNKNOWN_SUBMISSION")))
            return None, "UNKNOWN_SUBMISSION"
        order = snapshot["orders"].get(cid)
        if not correlated(order):
            self.ledger.change(lambda state: (state.update(reconciled=False, fault_halt=True),
                state["management"][cid].update(status="UNKNOWN_SUBMISSION"),
                state["faults"].append("MANAGEMENT_ORDER_CORRELATION_MISMATCH")))
            return None, "INCONSISTENT"
        outcome = "REJECTED" if order["status"] == "REJECTED" else "ACKNOWLEDGED"
        if order["status"] != "REJECTED" and not order["visible"]:
            outcome = "UNKNOWN_SUBMISSION"
        self.ledger.change(lambda state: state["management"][cid].update(
            status=outcome, exchange_order_id=oid))
        if outcome == "UNKNOWN_SUBMISSION":
            self.ledger.change(lambda state: state.update(reconciled=False))
        return order, outcome

    def fault(self, life, reason):
        self.ledger.change(lambda s: (s["faults"].append(reason), s.update(fault_halt=True)))
        self.latch(life, reason)

    def latch(self, life, reason, *, cancel_unknown=False):
        def action(s):
            p = s["positions"][life]
            if not p["latch"]:
                p["latch"] = {"reason": reason, "at": iso(self.clock.now)}
            p["state"] = "EXIT_REQUESTED"
            return p["entry_id"]
        entry = self.ledger.change(action)  # persisted BEFORE cancel/reduce
        try:
            self.venue.cancel(entry, unknown=cancel_unknown)
        except (TimeoutError, ConnectionError):
            pass
        self.reduce(life, reason=reason)  # cancellation uncertainty never stalls urgent reduction

    def reduce(self, life, *, reason="REDUCE_ONLY"):
        # Record the requested reduction before reading or writing the fake
        # venue. A disconnect therefore cannot erase the supervisor's intent.
        def persist_request(s):
            requests = s.setdefault("exit_requests", {})
            existing = requests.get(life)
            if existing:
                return existing
            position = s["positions"][life]
            prior_market = [
                cid for cid, item in s.get("management", {}).items()
                if item["lifecycle_id"] == life and item["params"]["kind"] == "MARKET"
            ]
            client_id = prior_market[-1] if prior_market else f"exit-{life}-{position['version']}"
            request = {"lifecycle_id": life, "client_order_id": client_id,
                "reason": reason, "requested_at": iso(self.clock.now),
                "status": "PENDING_RECONCILIATION", "attempt": 0, "prior_requests": []}
            requests[life] = request
            return request

        request = self.ledger.change(persist_request)
        cid = request["client_order_id"]
        try:
            snap = self.venue.snapshot()
        except ConnectionError:
            self.ledger.change(lambda s: s.update(reconciled=False))
            return cid
        q_signed = D(snap["positions"].get(life, "0"))
        if not q_signed:
            self.ledger.change(lambda s: s.setdefault("exit_requests", {}).get(life, {}).update(
                status="FLAT_RECONCILED", resolved_at=iso(self.clock.now),
                reconciliation_evidence="fake-authoritative-flat-position"))
            return None
        s = self.ledger.read()
        p = s["positions"][life]
        auth = s["approvals"][p["plan_id"]]
        existing = snap["orders"].get(cid)
        if (q_signed and existing and existing["lifecycle_id"] == life
            and existing["params"]["kind"] == "MARKET"
            and existing["params"]["reduce_only"]
            and existing["status"] in {"FILLED", "CANCELLED", "EXPIRED"}
            and request.get("status") != "FLAT_RECONCILED"):
            # A correlated terminal reduce-only order plus authoritative
            # non-flat venue truth permits a new reduction identity. This is
            # specifically how C01 handles a late entry fill after a prior
            # reduce filled; unknown/absent acknowledgements never take this
            # branch because they are not terminal correlated orders.
            def advance_exit_request(state):
                current = state.setdefault("exit_requests", {}).get(life)
                if (not current or current.get("client_order_id") != cid
                    or current.get("status") == "FLAT_RECONCILED"):
                    return None
                prior = {key: current.get(key) for key in (
                    "client_order_id", "status", "exchange_order_id", "requested_at", "reason")}
                history = list(current.get("prior_requests", []))
                history.append(prior)
                attempt = int(current.get("attempt", 0)) + 1
                new_id = f"exit-{life}-{state['positions'][life]['version']}-{attempt}"
                current.update(client_order_id=new_id, reason=reason,
                    requested_at=iso(self.clock.now), status="PENDING_RECONCILIATION",
                    exchange_order_id=None, attempt=attempt, prior_requests=history)
                return current
            request = self.ledger.change(advance_exit_request)
            if request is None:
                self.ledger.change(lambda state: state.update(reconciled=False))
                return cid
            cid = request["client_order_id"]
            existing = None
        if existing:
            valid = (existing["lifecycle_id"] == life
                and existing["params"]["kind"] == "MARKET"
                and existing["params"]["reduce_only"]
                and existing["params"]["side"] == ("SELL" if q_signed > 0 else "BUY"))
            if not valid:
                self.ledger.change(lambda state: state.update(reconciled=False))
                return cid
            status = "ORDER_OBSERVED" if existing["status"] not in TERMINAL else "ORDER_TERMINAL"
            def reconcile_existing(state):
                state.setdefault("exit_requests", {}).get(life, {}).update(
                    status=status, exchange_order_id=existing["id"])
                management = state.get("management", {}).get(cid)
                if management and management.get("status") in {
                    "PERSISTED", "SUBMITTED", "UNKNOWN_SUBMISSION"}:
                    management.update(status="RECONCILED", exchange_order_id=existing["id"])
            self.ledger.change(reconcile_existing)
            return cid

        # A write record without its correlated order is ambiguous. Do not
        # create another client ID or repeat the external action.
        if any(write.get("client_id") == cid for write in snap["writes"]):
            self.ledger.change(lambda state: state.update(reconciled=False))
            return cid

        params = OrderParameters(symbol=auth["symbol"], side="SELL" if q_signed > 0 else "BUY",
            kind="MARKET", quantity=abs(q_signed), reduce_only=True)
        def persist_order_intent(state):
            management = state.setdefault("management", {})
            existing_intent = management.get(cid)
            if existing_intent:
                if (existing_intent["lifecycle_id"] != life
                    or existing_intent["params"] != params.model_dump(mode="json")
                    or existing_intent["status"] != "PERSISTED"):
                    return False
            else:
                management[cid] = {"lifecycle_id": life,
                    "params": params.model_dump(mode="json"), "status": "PERSISTED"}
                state["positions"][life]["version"] += 1
            state.setdefault("exit_requests", {})[life].update(status="ORDER_INTENT_PERSISTED")
            return True
        if not self.ledger.change(persist_order_intent):
            return cid
        def claim_submission(state):
            intent = state.get("management", {}).get(cid)
            exit_request = state.setdefault("exit_requests", {}).get(life)
            if (not intent or intent["status"] != "PERSISTED" or not exit_request
                or exit_request["client_order_id"] != cid
                or exit_request["status"] != "ORDER_INTENT_PERSISTED"):
                return False
            intent["status"] = "SUBMITTED"
            exit_request["status"] = "SUBMITTED"
            return True
        if not self.ledger.change(claim_submission):
            return cid
        try:
            oid = self.venue.submit(cid, params, lifecycle_id=life)
        except (TimeoutError, ConnectionError):
            def unknown(state):
                if state["management"].get(cid, {}).get("status") == "SUBMITTED":
                    state["management"][cid]["status"] = "UNKNOWN_SUBMISSION"
                    state.setdefault("exit_requests", {})[life].update(status="UNKNOWN_SUBMISSION")
                state["reconciled"] = False
            self.ledger.change(unknown)
            return cid
        def acknowledged(state):
            if state["management"].get(cid, {}).get("status") == "SUBMITTED":
                state["management"][cid]["status"] = "ACKNOWLEDGED"
                state.setdefault("exit_requests", {})[life].update(
                    status="ACKNOWLEDGED", exchange_order_id=oid)
        self.ledger.change(acknowledged)
        return cid

    def add_targets(self, life):
        s = self.ledger.read()
        p = s["positions"][life]
        if p["latch"]:
            return []
        auth = s["approvals"][p["plan_id"]]
        q = D(p["entry_quantity"])
        ids = []
        for index, target in enumerate(p["geometry"]["targets"]):
            cid = f"tp-{life}-{index}"
            params = OrderParameters(symbol=auth["symbol"], side="SELL" if auth["side"] == "LONG" else "BUY",
                kind="LIMIT", quantity=q * D(target["fraction"]), price=D(target["price"]), time_in_force="GTC", reduce_only=True)
            order, outcome = self._submit_management_order(life, cid, params)
            if not order or outcome not in {"ACKNOWLEDGED", "RECONCILED"}:
                raise RuntimeError("target order submission is unresolved")
            ids.append(cid)
        self.ledger.change(lambda s: s["positions"][life].update(tp_ids=ids))
        return ids

    def tighten(self, life, price, *, overlap_safe=False, result="ACKNOWLEDGED"):
        s = self.ledger.read()
        p = s["positions"][life]
        snap = self.venue.snapshot()
        old = p["stop_ids"][-1]
        old_order = snap["orders"][old]
        auth = s["approvals"][p["plan_id"]]
        prior = D(old_order["params"]["stop_price"])
        if (not overlap_safe or old_order["status"] not in {"ACKNOWLEDGED", "PARTIAL"}
            or (auth["side"] == "LONG" and price <= prior) or (auth["side"] == "SHORT" and price >= prior)):
            return False
        cid = "replacement-" + life + "-" + str(p["version"])
        params = OrderParameters.model_validate_json(json.dumps({**old_order["params"], "stop_price": str(price)}))
        replacement, outcome = self._submit_management_order(life, cid, params, result=result)
        if (not replacement or outcome not in {"ACKNOWLEDGED", "RECONCILED"}
            or replacement["status"] != "ACKNOWLEDGED" or not replacement["visible"]):
            return False
        self.ledger.change(lambda s: s["positions"][life]["stop_ids"].append(cid))
        self.venue.cancel(old)
        return True

    def timers(self):
        state = self.ledger.read()
        for intent in state["intents"].values():
            if intent["submitted_at"] and self.clock.now - dt(intent["submitted_at"]) >= timedelta(seconds=10):
                try:
                    snapshot = self.venue.snapshot()
                    order = snapshot["orders"].get(intent["client_order_id"])
                    if order and order["status"] not in TERMINAL:
                        self.venue.cancel(intent["client_order_id"])
                except (TimeoutError, ConnectionError):
                    self.ledger.change(lambda s: s.update(reconciled=False))
        for life, p in self.ledger.read()["positions"].items():
            if p["first_fill_at"] and D(p["quantity"]) > 0:
                age = self.clock.now - dt(p["first_fill_at"])
                if age >= timedelta(hours=12):
                    self.fault(life, "TIME_EXIT_BREACH")
                elif age >= timedelta(hours=11, minutes=55):
                    self.latch(life, "TIME_LIMIT")

    def mark_equity(self, equity, *, net_external_transfer=D(0)):
        def action(s):
            day = self.clock.now.date().isoformat()
            if day != s["utc_day"] and s["reconciled"] and self.ready:
                s.update(utc_day=day, baseline=str(equity - net_external_transfer), daily_halt=False)
            s["baseline"] = str(D(s["baseline"]) + net_external_transfer)
            s["equity"] = str(equity)
            if equity <= D(s["baseline"]) * D(".99"):
                s["daily_halt"] = True
        self.ledger.change(action)

    def terminal(self, life, *, correlated=True):
        snapshot = self.venue.snapshot()
        self._apply_snapshot(snapshot)
        orders = [o for o in snapshot["orders"].values() if o["lifecycle_id"] == life]
        s = self.ledger.read()
        # Every original entry identity needs correlated terminal evidence.
        # Missing ACK/RECONCILED orders are uncertain, never proof of cancellation.
        pending = []
        for i in s["intents"].values():
            if i["lifecycle_id"] != life:
                continue
            never_sent = i["state"] == "REJECTED" and i["submitted_at"] is None
            original = snapshot["orders"].get(i["client_order_id"])
            proven_terminal = original and original["status"] in TERMINAL
            if not never_sent and not proven_terminal:
                pending.append(i)
        management_missing = [cid for cid, i in s.get("management", {}).items()
            if i["lifecycle_id"] == life and cid not in snapshot["orders"]]
        exit_request = s.get("exit_requests", {}).get(life)
        if (exit_request and D(snapshot["positions"].get(life, "0")) == 0
            and not management_missing and all(o["status"] in TERMINAL for o in orders)):
            self.ledger.change(lambda state: state.setdefault("exit_requests", {}).get(life, {}).update(
                status="FLAT_RECONCILED", resolved_at=iso(self.clock.now),
                reconciliation_evidence="fake-correlated-flat-and-orders-terminal"))
            s = self.ledger.read()
            exit_request = s.get("exit_requests", {}).get(life)
        exit_request_unresolved = bool(exit_request and exit_request.get("status") != "FLAT_RECONCILED")
        complete = (correlated and s["positions"][life]["state"] != "RECONCILING"
            and D(snapshot["positions"].get(life, "0")) == 0 and not pending
            and not management_missing and not exit_request_unresolved
            and orders and all(o["status"] in TERMINAL for o in orders))
        if complete:
            def action(s):
                p = s["positions"][life]
                p["state"] = "FLAT_RECONCILED"
                p["terminal_proof"] = "fake-correlated-flat-and-orders-terminal"
                s["reservations"]["res-" + p["plan_id"]]["status"] = "RELEASED"
            self.ledger.change(action)
        return bool(complete)
