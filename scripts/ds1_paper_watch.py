"""DS1 V2 offline-only paper watch snapshot, no orders or Telegram."""
import argparse,json
from datetime import date,datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.ds1_prebreakout_paper import ACTIVE,WATCH_RISK,compare
from scripts.ds1_paper_dnse import Client
from scripts.ds1_universe import symbols
TZ=ZoneInfo("Asia/Ho_Chi_Minh")
def present(result):
    rows=[]
    for item in result["symbols"]:
        v=item["v2"];score=v.get("score");gates=v.get("gates",[])
        is_risk=item["symbol"] in result.get("watch_risk",WATCH_RISK) or "WATCH_RISK" in gates
        watch=not is_risk and score is not None and score>=70 and not any(g in gates for g in ("TREND_GATE","PIVOT_GATE","LIQUIDITY_GATE"))
        rows.append({"symbol":item["symbol"],"v1_score":item["v1"].get("score") if item["v1"] else None,"v2_score":score,
          "candidate":watch,"paper_status":"PAPER_WATCH" if watch else "WATCH_RISK" if is_risk else "DATA_ERROR" if score is None else "MONITOR",
          "validation_status":v.get("status"),"gates":gates,"metrics":v.get("metrics",{})})
    return sorted(rows,key=lambda r:(not r["candidate"],-(r["v2_score"] if r["v2_score"] is not None else -1),r["symbol"]))
def run(asof,client,output):
    expected=symbols(asof)
    result=compare(expected,asof,client)
    rows=present(result)
    if len(rows)!=len(expected) or {r["symbol"] for r in rows}!=set(expected) or any(r["paper_status"]=="DATA_ERROR" for r in rows):
        raise ValueError("INCOMPLETE_OR_STALE_DATA: no paper snapshot published")
    payload={"asof":asof,"mode":"PAPER_WATCH_RESEARCH_ONLY","validated_buy_signals":False,"telegram_enabled":False,
      "watchlist_version":result.get("watchlist_version"),"expected_count":len(expected),"market_sector_status":"UNVERIFIED","candidate_count":sum(r["candidate"] for r in rows),"rows":rows}
    p=Path(output);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"asof":asof,"candidates":[r["symbol"] for r in rows if r["candidate"]],"count":len(rows)}))
    return payload
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",default=datetime.now(TZ).date().isoformat())
    p.add_argument("--output",default=None)
    a=p.parse_args()
    # A complete daily bar must be available; compare() enforces exact requested trading date.
    target=a.output or "data/ds1_v2/paper_watch/"+a.date+".json"
    run(a.date,Client(interval=.5),target)
if __name__=="__main__":main()

