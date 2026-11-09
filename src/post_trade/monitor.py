from dataclasses import dataclass
from datetime import datetime
import numpy as np
@dataclass
class Fill:
    order_id:str; venue:str; quoted:float; executed:float; quantity:float; gas_usd:float; sent_at:datetime; filled_at:datetime; status:str="filled"
    def slippage_bps(self): return (self.executed-self.quoted)/self.quoted*1e4
    def latency_ms(self): return (self.filled_at-self.sent_at).total_seconds()*1000

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
