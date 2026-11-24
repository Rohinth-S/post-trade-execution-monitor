"""Repeatable order and execution fixtures."""

from datetime import UTC, datetime, timedelta

from .events import ExecutionBatch, Order, Receipt


def demo_batch() -> ExecutionBatch:
    start = datetime(2026, 4, 24, 12, tzinfo=UTC)
    orders = [
        Order(
            venue=venue, order_id=str(index), symbol="ETH", route=route, side=side,
            quoted_price_usd=2_000, quantity=1, sent_at=start + timedelta(seconds=index),
        )
        for index, (venue, route, side) in enumerate((
            ("dex", "eth-usdc", "buy"), ("cex", "eth-usdc", "sell"), ("cex", "eth-usdc", "sell"),
            ("dex", "eth-usdc", "buy"), ("dex", "eth-usdc", "sell"), ("cex", "eth-usdc", "buy"),
        ))
    ]

    def fill(index, suffix, qty, price, millis, *, status="filled", gas=0):
        order = orders[index]
        return Receipt(
            venue=order.venue, order_id=order.order_id, fill_id=f"{index}-{suffix}",
            quantity=qty, executed_price_usd=price, gas_usd=gas, fee_usd=0.2,
            filled_at=order.sent_at + timedelta(milliseconds=millis), status=status,
        )

    fills = [
        fill(0, "a", 0.4, 2_002, 280, gas=1.25),
        fill(0, "b", 0.6, 2_005, 1_040, gas=1.05),
        fill(1, "a", 1, 2_003, 85),
        fill(2, "a", 0.5, 1_975, 220),
        fill(3, "a", 0, None, 1_500, status="failed", gas=8.5),
        fill(5, "a", 1.1, 2_010, 8_000),
    ]
    return ExecutionBatch(orders=orders, fills=fills)
