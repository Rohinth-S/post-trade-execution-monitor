"""Reconstruct execution state, inventory, attribution, and operational alerts."""

from collections import Counter, defaultdict
from datetime import UTC, datetime
from math import isclose

import numpy as np

from .events import AlertLimits, ExecutionBatch, Order, Receipt

def _unique(records, field):
    by_key = {}
    for record in records:
        key = (record.venue, getattr(record, field))
        before = by_key.setdefault(key, record)
        if before != record:
            raise ValueError(f"conflicting {field} identity at {record.venue}/{key[1]}")
    return list(by_key.values())


def _order_row(order: Order, receipts: list[Receipt], cutoff: datetime, limits: AlertLimits) -> dict:
    successful = [receipt for receipt in receipts if receipt.status == "filled"]
    quantity = sum(receipt.quantity for receipt in successful)
    value = sum(receipt.quantity * receipt.executed_price_usd for receipt in successful)
    vwap = value / quantity if quantity else None
    direction = 1 if order.side == "buy" else -1
    reference = order.quoted_price_usd * quantity
    improvement = direction * (reference - value)
    gas = sum(receipt.gas_usd for receipt in receipts)
    fees = sum(receipt.fee_usd for receipt in receipts)
    age_ms = (cutoff - order.sent_at).total_seconds() * 1_000
    def elapsed(receipt: Receipt) -> float:
        return (receipt.filled_at - order.sent_at).total_seconds() * 1_000

    response_ms = min(map(elapsed, receipts), default=None)
    first_fill_ms = min(map(elapsed, successful), default=None)
    latency_ms = max(
        map(elapsed, receipts),
        default=None,
    )
    if quantity and isclose(order.quantity, quantity, rel_tol=1e-9, abs_tol=1e-12):
        status = "filled"
    elif quantity > order.quantity:
        status = "overfilled"
    elif quantity:
        status = "partial"
    elif receipts:
        status = "failed"
    else:
        status = "missing" if age_ms >= limits.missing_after_ms else "pending"
    return {
        "venue": order.venue, "order_id": order.order_id, "route": order.route, "symbol": order.symbol,
        "side": order.side, "sent_at": order.sent_at.isoformat(), "state": status, "age_ms": age_ms,
        "expected_qty": order.quantity, "filled_qty": quantity, "quote_usd": order.quoted_price_usd,
        "first_response_ms": response_ms, "first_fill_ms": first_fill_ms,
        "vwap_usd": vwap, "slippage_bps": -improvement / reference * 10_000 if reference else None,
        "latency_ms": latency_ms, "gas_usd": gas, "fee_usd": fees, "price_improvement_usd": improvement,
        "execution_pnl_usd": improvement - gas - fees, "signed_inventory": direction * quantity,
        "net_cash_usd": -direction * value - gas - fees, "failed_receipts": len(receipts) - len(successful),
    }


def _statistics(orders: list[dict]) -> dict:
    latencies = [row["latency_ms"] for row in orders if row["latency_ms"] is not None]
    realized = [row for row in orders if row["slippage_bps"] is not None]
    reference = sum(row["filled_qty"] * row["quote_usd"] for row in realized)
    return {
        "orders": len(orders), "states": dict(Counter(row["state"] for row in orders)),
        "p95_latency_ms": float(np.percentile(latencies, 95)) if latencies else None,
        "weighted_slippage_bps": -sum(row["price_improvement_usd"] for row in realized) / reference * 10_000
        if reference else None,
        **{name: sum(row[name] for row in orders) for name in (
            "gas_usd", "fee_usd", "price_improvement_usd", "execution_pnl_usd", "failed_receipts",
        )},
    }


def build_execution_report(
    batch: ExecutionBatch, *, as_of: datetime | None = None, limits: AlertLimits = AlertLimits(),
) -> dict:
    if as_of and (as_of.tzinfo is None or as_of.utcoffset() is None):
        raise ValueError("replay cutoff must include a timezone")
    cutoff = as_of or max(
        [order.sent_at for order in batch.orders] + [fill.filled_at for fill in batch.fills],
        default=datetime(1970, 1, 1, tzinfo=UTC),
    )
    orders = {
        (order.venue, order.order_id): order
        for order in _unique([item for item in batch.orders if item.sent_at <= cutoff], "order_id")
    }
    visible_fills = _unique([item for item in batch.fills if item.filled_at <= cutoff], "fill_id")
    receipts: dict[tuple[str, str], list[Receipt]] = defaultdict(list)
    exceptions = []
    for fill in sorted(visible_fills, key=lambda item: (item.filled_at, item.venue, item.fill_id)):
        key = (fill.venue, fill.order_id)
        state = "orphan" if key not in orders else "pre_order" if fill.filled_at < orders[key].sent_at else None
        if state:
            exceptions.append({
                "venue": fill.venue, "order_id": fill.order_id, "fill_id": fill.fill_id,
                "state": state, "cost_usd": fill.fee_usd + fill.gas_usd,
            })
        else:
            receipts[key].append(fill)
    rows = [
        _order_row(order, receipts[key], cutoff, limits)
        for key, order in sorted(orders.items(), key=lambda item: (item[1].sent_at, item[0]))
    ]
    alerts = []
    groups = {"venue": defaultdict(list), "route": defaultdict(list)}
    inventory: dict[str, dict] = defaultdict(lambda: {"position_qty": 0.0, "net_cash_usd": 0.0})
    for row in rows:
        key = {"venue": row["venue"], "order_id": row["order_id"]}
        state = row["state"]
        if state in {"failed", "missing", "overfilled"}:
            alerts.append({**key, "type": state, "severity": "critical"})
        if state == "partial" and row["age_ms"] >= limits.missing_after_ms:
            alerts.append({**key, "type": "stale_partial", "severity": "warning"})
        if row["failed_receipts"] and state != "failed":
            alerts.append({**key, "type": "failed_attempt", "severity": "warning"})
        if (row["slippage_bps"] or 0) > limits.slippage_bps:
            alerts.append({**key, "type": "adverse_slippage", "severity": "warning"})
        if (row["latency_ms"] or 0) > limits.latency_ms:
            alerts.append({**key, "type": "latency", "severity": "warning"})
        for dimension, values in groups.items():
            values[row[dimension]].append(row)
        exposure = inventory[row["symbol"]]
        exposure["position_qty"] += row["signed_inventory"]
        exposure["net_cash_usd"] += row["net_cash_usd"]
    alerts.extend({**item, "type": item["state"], "severity": "critical"} for item in exceptions)
    return {
        "as_of": cutoff.astimezone(UTC).isoformat(), "limits": limits.model_dump(), "summary": _statistics(rows),
        "by_venue": {k: _statistics(v) for k, v in sorted(groups["venue"].items())},
        "by_route": {k: _statistics(v) for k, v in sorted(groups["route"].items())},
        "by_symbol": dict(sorted(inventory.items())), "orders": rows, "alerts": alerts,
        "unlinked_cost_usd": sum(item["cost_usd"] for item in exceptions),
    }
