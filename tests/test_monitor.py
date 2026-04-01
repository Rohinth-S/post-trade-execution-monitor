from datetime import datetime,timedelta
from post_trade.monitor import Fill,reconcile,anomalies,pnl_attribution
def test_reconciliation_and_alerts():
 t=datetime(2026,1,1); rows=reconcile([Fill("a","dex",100,101,1,2,t,t+timedelta(seconds=2))]); assert rows[0]["latency_ms"]==2000; assert len(anomalies(rows))==1
def test_empty_summary(): assert pnl_attribution([])["count"]==0
