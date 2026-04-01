from datetime import datetime,timedelta
from .monitor import Fill,reconcile,anomalies,pnl_attribution
def main():
 t=datetime(2026,1,1); fs=[Fill("o1","dex",100,100.2,1,3,t,t+timedelta(milliseconds=120)),Fill("o2","dex",100,102,1,3,t,t+timedelta(seconds=2))]; rows=reconcile(fs); print(pnl_attribution(rows)); print({"alerts":anomalies(rows)})
if __name__=="__main__":main()
