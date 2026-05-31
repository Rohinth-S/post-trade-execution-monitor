"""Operational PnL, latency, and alert aggregation for execution reports."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
import numpy as np

from .monitor import anomalies


def _percentile(values: list[float], percentile: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), percentile)) if values else 0.0


def aggregate_by_venue(rows: Sequence[dict], *, slip_limit: float = 40, latency_limit: float = 1_000) -> dict[str, dict]:
    """Aggregate fill economics and tail latency by execution venue."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if "venue" not in row:
            raise ValueError("rows must include venue")
        groups[str(row["venue"])].append(row)
    result: dict[str, dict] = {}
    for venue, items in sorted(groups.items()):
        alerts = anomalies(items, slip_limit, latency_limit)
        p95_latency = _percentile([float(item["latency_ms"]) for item in items], 95)
        result[venue] = {"count": len(items), "failed": sum(item.get("status") != "filled" for item in items),
                         "pnl_usd": float(sum(item.get("pnl_usd", 0.0) for item in items)),
                         "gas_usd": float(sum(item.get("gas_usd", 0.0) for item in items)),
                         "mean_slippage_bps": float(np.mean([item["slippage_bps"] for item in items])),
                         "p95_latency_ms": p95_latency, "alert_count": len(alerts)}
    return result


def alert_summary(rows: Sequence[dict], *, slip_limit: float = 40, latency_limit: float = 1_000) -> dict:
    """Classify anomalies into failure, latency, and slippage alerts."""
    alerts = anomalies(rows, slip_limit, latency_limit)
    counts = {"failure": 0, "latency": 0, "slippage": 0}
    for row in alerts:
        if row.get("status") != "filled":
            counts["failure"] += 1
        if float(row.get("latency_ms", 0)) > latency_limit:
            counts["latency"] += 1
        if abs(float(row.get("slippage_bps", 0))) > slip_limit:
            counts["slippage"] += 1
    return {"total": len(alerts), "by_type": counts,
            "critical": counts["failure"], "warning": len(alerts) - counts["failure"]}
