"""Daily Pre-Breakout V2 Paper Watch; NEVER places orders or sends BUY alerts."""
from __future__ import annotations
import argparse,csv,json
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.ds1_prebreakout_v2 import compare,ACTIVE,WATCH_RISK
from scripts.ds1_market_wide import Client
TZ=ZoneInfo("Asia/Ho_Chi_Minh")
def classify(result):
    output=[]
    for item in result["symbols"]:
        s=item["symbol"];v=item["v2"];score=v.get("score")
        gates=v.get("gates",[])
        watch=(s in ACTIVE and isinstance(score,(int,float)) and score>=70 and
               not any(k in gates for k in ("TREND_GATE","PIVOT_GATE","LIQUIDITY_GATE")) and
               v["status"]=="RESEARCH_BLOCKED")
        output.append({"symbol":s,"date":result["asof"],"score":score,
          "watch_category":"PAPER_WATCH_CANDIDATE" if watch else "WATCH_RISK" if s in WATCH_RISK else "NO_WATCH",
          "model_status":v["status"],"blocking_gates":gates,
          "close_vnd":v.get("metrics",{}).get("close_vnd"),
          "mode":"PAPER_ONLY_NO_BUY"})
    return sorted(output,key=lambda r:(r["watch_category"]!="PAPER_WATCH_CANDIDATE",-(r["score"] or -1),r["symbol"]))
def write_report(result,out):
    records=classify(result)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    day=result["asof"]
    (out/f"paper_watch_{day}.json").write_text(json.dumps({"date":day,"mode":"PAPER_ONLY","note":"not a trading signal; market/sector context unverified","symbols":records},ensure_ascii=False,indent=2))
    with (out/f"paper_watch_{day}.csv").open("w",newline="",encoding="utf-8") as f:
        fields=list(records[0]) if records else ["symbol","date","score","watch_category"]
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for row in records:w.writerow({**row,"blocking_gates":";".join(row["blocking_gates"])})
    return records
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",default=None,help="YYYY-MM-DD; default latest completed DNSE VN30 trading day")
    p.add_argument("--output-dir",default="data/ds1_v2/paper_watch")
    a=p.parse_args()
    now=datetime.now(TZ)
    client=Client(interval=0.5)
    if a.date:day=a.date
    else:
        cutoff=(now-timedelta(days=1)).date() if now.hour<16 else now.date()
        bars=client.ohlcv("VN30","1D",now)
        dates=[datetime.fromtimestamp(b["t"],TZ).date() for b in bars if datetime.fromtimestamp(b["t"],TZ).date()<=cutoff]
        if not dates:raise ValueError("No completed DNSE benchmark day")
        day=max(dates).isoformat()
    result=compare(ACTIVE+WATCH_RISK,day,client)
    rows=write_report(result,a.output_dir)
    errors=[r for r in rows if r["model_status"] in ("DATA_ERROR","INVALID_DATA","INSUFFICIENT_DATA")]
    print(json.dumps({"date":day,"count":len(rows),"paper_watch_candidates":[r["symbol"] for r in rows if r["watch_category"]=="PAPER_WATCH_CANDIDATE"],"errors":errors,"production_changes":False}))
    return 2 if errors or len(rows)!=20 else 0
if __name__=="__main__":raise SystemExit(main())
