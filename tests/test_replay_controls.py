import pytest

from post_trade.execution import build_execution_report
from post_trade.fixtures import demo_batch
from post_trade.monitor import ExpectedOrder, Fill, reconcile_orders
from post_trade.scope import ReportScope


def test_replay_scope_and_retry_do_not_mix_venues():
    batch = demo_batch()
    batch.fills.append(batch.fills[0])
    result = build_execution_report(batch, scope=ReportScope(venue="dex"))
    assert result["summary"]["orders"] == 3
    first = result["orders"][0]
    assert first["filled_qty"] == 1
    assert first["first_response_ms"] == 280
    assert first["completion_ms"] == 1040
    assert result["scope"] == {"venue": "dex"}

    t = batch.orders[0].sent_at
    events = [Fill("same", "cex", 100, 100, 1, 0, t, t)]
    expected = [ExpectedOrder("same", "dex", 1), ExpectedOrder("same", "cex", 1)]
    assert [row["state"] for row in reconcile_orders(expected, events)] == ["missing", "filled"]
