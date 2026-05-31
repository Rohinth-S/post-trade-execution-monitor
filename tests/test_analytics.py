from datetime import datetime, timedelta

from post_trade.analytics import aggregate_by_venue, alert_summary
from post_trade.monitor import Fill, reconcile


def test_venue_aggregation_and_alert_summary():
    t = datetime(2026, 1, 1)
    rows = reconcile([
        Fill("a", "dex", 100, 101, 1, 2, t, t + timedelta(milliseconds=100)),
        Fill("b", "dex", 100, 99, 2, 1, t, t + timedelta(seconds=2), status="rejected"),
        Fill("c", "cex", 10, 10, 1, 0, t, t + timedelta(milliseconds=10)),
    ])
    by_venue = aggregate_by_venue(rows, slip_limit=40, latency_limit=1_000)
    assert by_venue["dex"]["count"] == 2
    assert by_venue["dex"]["failed"] == 1
    assert by_venue["dex"]["p95_latency_ms"] > 1_000
    summary = alert_summary(rows)
    assert summary["total"] == 2 and summary["critical"] == 1
