"""Fail-closed data rights audit gate. Never infers official ex-right dates or adjusts OHLCV."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from scripts.ds1_prebreakout_v2 import ACTIVE,WATCH_RISK

SYMBOLS=set(ACTIVE+WATCH_RISK)
def assess(ledger):
    rows=[];issues=[]
    got={x["symbol"] for x in ledger["symbols"]}
    if got!=SYMBOLS:issues.append("UNIVERSE_MISMATCH")
    for item in ledger["symbols"]:
        events=item.get("events",[])
        for e in events:
            missing=[k for k in ("ex_date","source_url") if not e.get(k)]
            if not e.get("record_date") and not e.get("ex_date"):missing.append("event_date")
            if e.get("adjustment_status")!="VERIFIED":missing.append("adjustment_status")
            if e.get("data_application")!="NEVER_AUTO_APPLY":issues.append("UNSAFE_AUTO_ADJUSTMENT:"+item["symbol"])
            rows.append({"symbol":item["symbol"],"date":e.get("record_date") or e.get("ex_date"),
                         "ex_date":e.get("ex_date"),"event_type":e.get("event_type"),
                         "missing":missing,"verified":not missing})
    no_events=sorted(x["symbol"] for x in ledger["symbols"] if not x.get("events"))
    missing_ex=sum(not x["ex_date"] for x in rows)
    verified=sum(x["verified"] for x in rows)
    blocked=bool(issues or no_events or verified!=len(rows) or not ledger.get("adjustment_basis",{}).get("verified"))
    return {"status":"BLOCKED" if blocked else "READY_FOR_MANUAL_REVIEW","eligible_for_official_backtest":False,
            "symbols":len(got),"events":len(rows),"events_without_ex_date":missing_ex,
            "fully_verified_events":verified,"symbols_without_events_documented":no_events,
            "issues":issues,"event_audit":rows,
            "reason":"Historical events completeness and DNSE adjustment basis still require independent evidence"}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",default="data/ds1_v2/corporate_action_ledger.json")
    p.add_argument("--output",default="data/ds1_v2/corporate_action_gate.json")
    args=p.parse_args()
    result=assess(json.loads(Path(args.ledger).read_text()))
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!="event_audit"}))
    return 0
if __name__=="__main__":raise SystemExit(main())
