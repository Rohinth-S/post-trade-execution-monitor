from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
import csv
import json
from pathlib import Path
import numpy as np


class ExecutionState(StrEnum):
    FILLED = "filled"
    PARTIAL = "partial"
    FAILED = "failed"
    MISSING = "missing"
    DUPLICATE = "duplicate"
    OVERFILLED = "overfilled"
    ORPHAN = "orphan"


@dataclass(frozen=True)
class ExpectedOrder:
    order_id: str
    venue: str
    quantity: float

    def __post_init__(self) -> None:
        if not self.order_id or not self.venue or self.quantity <= 0:
            raise ValueError("expected order id/venue are required and quantity must be positive")
@dataclass
class Fill:
    order_id:str; venue:str; quoted:float; executed:float; quantity:float; gas_usd:float; sent_at:datetime; filled_at:datetime; status:str="filled"
    def slippage_bps(self): return (self.executed-self.quoted)/self.quoted*1e4
    def latency_ms(self): return (self.filled_at-self.sent_at).total_seconds()*1000


def reconcile_orders(
    expected: list[ExpectedOrder],
    fills: list[Fill],
    *,
    quantity_tolerance: float = 1e-9,
) -> list[dict]:
    """Reconcile broker expectations against execution events.

    The output is an auditable state transition for every expected order and
    an ``orphan`` row for fills that have no corresponding order. Duplicate
    events remain visible instead of being silently deduplicated.
    """
    if quantity_tolerance < 0:
        raise ValueError("quantity_tolerance cannot be negative")
    by_order: dict[str, list[Fill]] = {}
    for fill in fills:
        by_order.setdefault(fill.order_id, []).append(fill)
    rows: list[dict] = []
    seen: set[str] = set()
    for order in expected:
        matches = by_order.get(order.order_id, [])
        seen.add(order.order_id)
        if not matches:
            state = ExecutionState.MISSING
            filled_qty = 0.0
            slippage = latency = gas = 0.0
        elif len(matches) > 1:
            state = ExecutionState.DUPLICATE
            filled_qty = float(sum(fill.quantity for fill in matches))
            slippage = float(np.mean([fill.slippage_bps() for fill in matches]))
            latency = float(max(fill.latency_ms() for fill in matches))
            gas = float(sum(fill.gas_usd for fill in matches))
        else:
            fill = matches[0]
            filled_qty = float(fill.quantity)
            slippage, latency, gas = fill.slippage_bps(), fill.latency_ms(), fill.gas_usd
            if fill.status != "filled":
                state = ExecutionState.FAILED
            elif filled_qty > order.quantity + quantity_tolerance:
                state = ExecutionState.OVERFILLED
            elif filled_qty < order.quantity - quantity_tolerance:
                state = ExecutionState.PARTIAL
            else:
                state = ExecutionState.FILLED
        rows.append({"order_id": order.order_id, "venue": order.venue,
                     "expected_quantity": order.quantity, "filled_quantity": filled_qty,
                     "state": state.value, "duplicate_count": len(matches),
                     "slippage_bps": float(slippage), "latency_ms": float(latency), "gas_usd": float(gas)})
    for fill in fills:
        if fill.order_id not in seen:
            rows.append({"order_id": fill.order_id, "venue": fill.venue,
                         "expected_quantity": 0.0, "filled_quantity": fill.quantity,
                         "state": ExecutionState.ORPHAN.value, "duplicate_count": 1,
                         "slippage_bps": float(fill.slippage_bps()), "latency_ms": float(fill.latency_ms()),
                         "gas_usd": float(fill.gas_usd)})
    return rows


@dataclass
class ReconciliationStateMachine:
    """Incremental reconciler for a stream of fill events."""

    expected: list[ExpectedOrder]
    _fills: list[Fill] = field(default_factory=list, init=False, repr=False)

    def ingest(self, fill: Fill) -> dict:
        self._fills.append(fill)
        rows = reconcile_orders(self.expected, self._fills)
        return next(row for row in rows if row["order_id"] == fill.order_id)

    def snapshot(self) -> list[dict]:
        return reconcile_orders(self.expected, self._fills)


def write_report(rows: list[dict], destination: str | Path, format: str | None = None) -> Path:
    """Persist reconciliation rows as JSON or CSV with stable field order."""
    path = Path(destination)
    kind = (format or path.suffix.lstrip(".") or "json").lower()
    if kind not in {"json", "csv"}:
        raise ValueError("format must be json or csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "json":
        path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    else:
        fields = list(dict.fromkeys(key for row in rows for key in row))
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    return path

def reconcile(fills):
    rows=[]
    for f in fills:
      rows.append({"order_id":f.order_id,"venue":f.venue,"slippage_bps":f.slippage_bps(),"latency_ms":f.latency_ms(),"gas_usd":f.gas_usd,"status":f.status})
    return rows

def anomalies(rows, slip_limit=40, latency_limit=1000):
    return [r for r in rows if abs(r["slippage_bps"])>slip_limit or r["latency_ms"]>latency_limit or r["status"]!="filled"]

def pnl_attribution(rows):
    if not rows:return {"count":0,"mean_slippage_bps":0.0,"gas_usd":0.0,"failed":0}
    return {"count":len(rows),"mean_slippage_bps":float(np.mean([r["slippage_bps"] for r in rows])),"gas_usd":float(sum(r["gas_usd"] for r in rows)),"failed":sum(r["status"]!="filled" for r in rows)}
