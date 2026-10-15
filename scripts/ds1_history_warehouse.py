"""Research-only point-in-time DNSE 1D warehouse backfill with QA and provenance.
Backfill is NOT an assertion that vendor supplies 2023 data or adjusted prices.
"""
from __future__ import annotations
import argparse,csv,json,math,hashlib
from datetime import date,datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.ds1_market_wide import Client,validate_bars
from scripts import ds1_watch as v1
from scripts.ds1_prebreakout_v2 import ACTIVE,WATCH_RISK
TZ=ZoneInfo("Asia/Ho_Chi_Minh")

def windows(start,end,span=150):
    if end<start:raise ValueError("reversed dates")
    d=start
    while d<=end:
        stop=min(end,d+timedelta(days=span-1))
        yield d,stop
        d=stop+timedelta(days=1)

def audit_series(bars,benchmark_days=None):
    seen=set();bad=[];dates=[]
    for bar in bars:
        try:
            dt=datetime.fromtimestamp(bar["t"],TZ).date()
            vals=[bar[x] for x in ("o","h","l","c","v")]
            if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in vals):raise ValueError("NONFINITE")
            if min(vals[:4])<=0 or vals[4]<0 or bar["h"]<max(bar["o"],bar["c"]) or bar["l"]>min(bar["o"],bar["c"]):raise ValueError("INVALID_OHLCV")
            if dt in seen:raise ValueError("DUPLICATE_DATE")
            seen.add(dt);dates.append(dt)
        except Exception as exc:bad.append(str(exc))
    missing=sorted(set(benchmark_days or [])-set(dates)) if benchmark_days is not None else []
    return {"count":len(bars),"first":str(min(dates)) if dates else None,
            "last":str(max(dates)) if dates else None,"missing_benchmark_sessions":[str(d) for d in missing],
            "missing_count":len(missing),"errors":bad}

def backfill(client,symbol,start,end):
    collected={}
    for a,b in windows(start,end):
        endpoint=v1.INDEX_URL if symbol=="VN30" else v1.BASE_URL
        start_time=int(datetime.combine(a,datetime.min.time(),TZ).timestamp())
        end_time=int(datetime.combine(b+timedelta(days=1),datetime.min.time(),TZ).timestamp())
        payload=client.get(endpoint,{"symbol":symbol,"resolution":"1D","from":start_time,"to":end_time})
        items=validate_bars(payload)
        for bar in items:
            d=datetime.fromtimestamp(bar["t"],TZ).date()
            if not a<=d<=b:continue
            if symbol!="VN30":
                for k in "ohlc":bar[k]*=1000
            if d in collected and collected[d]!=bar:
                raise ValueError(f"{symbol}: conflicting duplicate date {d}")
            collected[d]=bar
    return [collected[k] for k in sorted(collected)]

def corporate_action_flags(bars, threshold_pct=18):
    """Flag raw overnight discontinuities; NEVER infer or perform adjustments."""
    out=[]
    for prev,cur in zip(bars,bars[1:]):
        gap=100*(cur["o"]/prev["c"]-1)
        if abs(gap)>=threshold_pct:
            out.append({"date":datetime.fromtimestamp(cur["t"],TZ).date().isoformat(),
                        "raw_overnight_gap_pct":round(gap,3),"status":"UNVERIFIED_POSSIBLE_ACTION_OR_EVENT"})
    return out

def run(args,client=None):
    client=client or Client(interval=0.5)
    start,end=date.fromisoformat(args.start),date.fromisoformat(args.end)
    if end>=datetime.now(TZ).date():raise ValueError("Warehouse accepts historical completed dates only")
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    symbols=("VN30",)+ACTIVE+WATCH_RISK
    store={};errors={}
    for symbol in symbols:
        try:store[symbol]=backfill(client,symbol,start,end)
        except Exception as exc:errors[symbol]=str(exc)
    calendar={datetime.fromtimestamp(b["t"],TZ).date() for b in store.get("VN30",[])}
    results={}
    for symbol,bars in store.items():
        check=audit_series(bars,calendar if symbol!="VN30" else None)
        flags=corporate_action_flags(bars) if symbol!="VN30" else []
        check["corporate_action_candidates"]=flags
        check["price_adjustment_verified"]=False
        check["source"]="DNSE chart-api/v2/ohlcs; resolution=1D"
        check["source_units"]="VND" if symbol!="VN30" else "index_points"
        results[symbol]=check
        if bars:
            p=out/(symbol+".csv")
            with p.open("w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["date","timestamp","open","high","low","close","volume"])
                w.writeheader()
                for x in bars:w.writerow({"date":datetime.fromtimestamp(x["t"],TZ).date().isoformat(),"timestamp":int(x["t"]),
                    "open":x["o"],"high":x["h"],"low":x["l"],"close":x["c"],"volume":x["v"]})
            check["sha256"]=hashlib.sha256(p.read_bytes()).hexdigest()
    complete=not errors and calendar and all(results[s]["missing_count"]==0 and not results[s]["errors"] for s in ACTIVE)
    validated_actions=False
    report={"status":"READY_FOR_ACTION_RECONCILIATION" if complete else "DATA_INCOMPLETE",
      "research_only":True,"start":str(start),"end":str(end),"all_corporate_actions_verified":validated_actions,
      "full_backtest_approved":False,"symbols_attempted":len(symbols),"symbols_returned":len(store),
      "reference_calendar":"VN30 returned daily bars; not an official exchange holiday calendar",
      "errors":errors,"audits":results}
    (out/"manifest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"status":report["status"],"symbols_returned":len(store),"errors":errors,
      "sessions_reference":len(calendar),"total_missing":sum(v["missing_count"] for v in results.values()),
      "corporate_action_flags":sum(len(v["corporate_action_candidates"]) for v in results.values())}))
    return 0 if complete else 2

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--start",default="2023-01-01")
    p.add_argument("--end",default="2026-10-14")
    p.add_argument("--output-dir",default="data/ds1_v2/historical_warehouse")
    args=p.parse_args()
    return run(args)
if __name__=="__main__":raise SystemExit(main())
