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

def test_old_ledgers_migrate_and_compare_timezone_equivalent_instants(tmp_path):
    import sqlite3
    from datetime import timedelta
    from post_trade.storage import LedgerStore

    path = tmp_path / "ledger.sqlite3"
    store = LedgerStore(path)
    batch = demo_batch()
    store.ingest(batch)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version = 0")
    reopened = LedgerStore(path)
    assert reopened.statistics()["schema_version"] == 1
    cutoff = batch.fills[0].filled_at
    assert len(reopened.snapshot(cutoff).fills) == 1
    assert len(reopened.snapshot(cutoff - timedelta(microseconds=1)).fills) == 0
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version = 9")
    with pytest.raises(ValueError, match="unsupported ledger schema"):
        LedgerStore(path)
