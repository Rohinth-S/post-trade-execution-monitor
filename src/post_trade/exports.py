"""Tabular reporting for command-line and dashboard users."""
import csv
from io import StringIO

ORDER_FIELDS = (
    "venue", "order_id", "route", "symbol", "side", "sent_at", "state", "age_ms",
    "expected_qty", "filled_qty", "quote_usd", "first_response_ms", "first_fill_ms",
    "last_fill_at", "completion_ms", "vwap_usd", "slippage_bps", "expected_notional_usd",
    "executed_notional_usd", "filled_reference_notional_usd", "latency_ms", "gas_usd",
    "fee_usd", "price_improvement_usd", "execution_pnl_usd", "signed_inventory",
    "net_cash_usd", "failed_receipts",
)


def orders_csv(rows: list[dict]) -> str:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=ORDER_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
