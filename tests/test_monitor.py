from datetime import datetime,timedelta
import json
from post_trade.monitor import (
    ExecutionState,
    ExpectedOrder,
    Fill,
    ReconciliationStateMachine,
    anomalies,
    pnl_attribution,
    reconcile,
    reconcile_orders,
    write_report,
)
def test_reconciliation_and_alerts():
 t=datetime(2026,1,1); rows=reconcile([Fill("a","dex",100,101,1,2,t,t+timedelta(seconds=2))]); assert rows[0]["latency_ms"]==2000; assert len(anomalies(rows))==1
def test_empty_summary(): assert pnl_attribution([])["count"]==0

def test_state_machine_detects_partial_duplicate_missing_and_orphan():
 t=datetime(2026,1,1)
 expected=[ExpectedOrder("a","dex",2), ExpectedOrder("b","cex",1), ExpectedOrder("c","dex",1)]
 fills=[Fill("a","dex",100,100.1,1,1,t,t+timedelta(milliseconds=10)),
        Fill("a","dex",100,100.2,1,1,t,t+timedelta(milliseconds=20)),
        Fill("z","cex",10,10,1,0,t,t)]
 rows=reconcile_orders(expected,fills)
 states={row["order_id"]: row["state"] for row in rows}
 assert states == {"a":ExecutionState.DUPLICATE.value,"b":ExecutionState.MISSING.value,"c":ExecutionState.MISSING.value,"z":ExecutionState.ORPHAN.value}

def test_incremental_reconciliation_and_json_csv_reports(tmp_path):
 t=datetime(2026,1,1)
 machine=ReconciliationStateMachine([ExpectedOrder("a","dex",1)])
 first=machine.ingest(Fill("a","dex",100,100,1,0,t,t))
 assert first["state"] == ExecutionState.FILLED.value
 rows=machine.snapshot()
 json_path=write_report(rows,tmp_path/"report.json")
 csv_path=write_report(rows,tmp_path/"report.csv")
 assert json.loads(json_path.read_text())[0]["state"] == "filled"
 assert "order_id" in csv_path.read_text().splitlines()[0]
