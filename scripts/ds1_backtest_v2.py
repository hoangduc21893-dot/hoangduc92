"""Point-in-time DS1 V1/V2 daily WATCH research. NOT an intraday BUY strategy."""
from __future__ import annotations
import argparse,csv,json,math
from datetime import date,datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.ds1_market_wide import Client,pre_breakout_rank
from scripts.ds1_prebreakout_v2 import score_v2,validate_series,ACTIVE,WATCH_RISK

TZ=ZoneInfo("Asia/Ho_Chi_Minh")
HORIZONS=(5,10,20)
MIN_HISTORY=60

def walk_forward(data,benchmark, *, fee_bps=25.0, train_end="2025-12-31", test_start="2026-01-01", test_end="2026-10-14"):
    """No parameter fitting: fixed-rule chronological holdout, separate train/test."""
    if fee_bps<0: raise ValueError("negative fees")
    daily={s:sorted(bs,key=lambda b:b["t"]) for s,bs in data.items()}
    bench=sorted(benchmark,key=lambda b:b["t"])
    bmap={datetime.fromtimestamp(b["t"],TZ).date():i for i,b in enumerate(bench)}
    records=[]
    for symbol, bars in daily.items():
        dates=[datetime.fromtimestamp(b["t"],TZ).date() for b in bars]
        if len(dates)!=len(set(dates)):raise ValueError(f"{symbol}: duplicate trading dates")
        for i in range(MIN_HISTORY-1,len(bars)-max(HORIZONS)):
            day=dates[i]
            if not (date.fromisoformat(train_end)>=day or date.fromisoformat(test_start)<=day<=date.fromisoformat(test_end)):continue
            if day not in bmap or bmap[day]<MIN_HISTORY-1:continue
            bi=bmap[day]; hist=bars[:i+1]; bh=bench[:bi+1]
            if len(hist)<MIN_HISTORY or len(bh)<MIN_HISTORY:continue
            v1=pre_breakout_rank(hist)
            v2=score_v2(hist,bh)
            # V2 context unavailable: retain numeric scores for exploratory study;
            # NEVER promote RESEARCH_BLOCKED to trade/BUY.
            if symbol in WATCH_RISK:continue
            group="train" if day<=date.fromisoformat(train_end) else "test"
            future={}
            for h in HORIZONS:
                exit_close=bars[i+h]["c"]
                # Entry next bar OPEN to avoid buying on the signal close.
                entry=bars[i+1]["o"]
                ret=100*(exit_close/entry-1)-2*fee_bps/100
                future[f"net_return_{h}d_pct"]=round(ret,4)
            records.append({"symbol":symbol,"date":day.isoformat(),"split":group,
                            "v1_score":v1.get("score"),"v1_watch":v1.get("status")=="WATCH",
                            "v2_score":v2.get("score"),"v2_status":v2.get("status"),
                            "v2_candidate":v2.get("score") is not None and v2["score"]>=70,
                            **future})
    return records

def metrics(rows,flag):
    selected=[r for r in rows if r[flag]]
    if not selected:return {"signals":0,"mean_5d_net_pct":None,"mean_10d_net_pct":None,"mean_20d_net_pct":None,"win_rate_10d_pct":None}
    return {"signals":len(selected),
            **{f"mean_{h}d_net_pct":round(sum(r[f"net_return_{h}d_pct"] for r in selected)/len(selected),3) for h in HORIZONS},
            "win_rate_10d_pct":round(100*sum(r["net_return_10d_pct"]>0 for r in selected)/len(selected),2)}

def summarize(rows):
    return {split:{"v1":metrics([r for r in rows if r["split"]==split],"v1_watch"),
                   "v2_exploratory":metrics([r for r in rows if r["split"]==split],"v2_candidate")}
            for split in ("train","test")}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--end",default="2026-10-14")
    p.add_argument("--train-end",default="2025-12-31")
    p.add_argument("--test-start",default="2026-01-01")
    p.add_argument("--fee-bps",type=float,default=25)
    p.add_argument("--output-dir",default="data/ds1_v2/backtest")
    args=p.parse_args()
    if args.train_end>=args.test_start:raise ValueError("train/test intervals overlap")
    client=Client(interval=0.3)
    asof=datetime.fromisoformat(args.end+"T23:00:00").replace(tzinfo=TZ)
    benchmark=client.ohlcv("VN30","1D",asof)
    universe={}
    errors={}
    for symbol in ACTIVE:
        try:
            bs=client.ohlcv(symbol,"1D",asof)
            validate_series(bs,date.fromisoformat(args.end),symbol)
            universe[symbol]=bs
        except Exception as exc:
            errors[symbol]=str(exc)
    records=walk_forward(universe,benchmark,fee_bps=args.fee_bps,
                         train_end=args.train_end,test_start=args.test_start,test_end=args.end)
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    fields=["symbol","date","split","v1_score","v1_watch","v2_score","v2_status","v2_candidate"]+[f"net_return_{h}d_pct" for h in HORIZONS]
    with (out/"events.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(records)
    report={"status":"EXPLORATORY_NOT_VALIDATED","data_limit":"DNSE client fetches up to 220 calendar days, so 2023-2025 history is unavailable from this endpoint as configured","end":args.end,"fee_bps_each_side":args.fee_bps,"symbols":len(universe),"errors":errors,"events":len(records),"results":summarize(records),"methodology":"Signal at completed close, next-open entry, close after 5/10/20 bars, two-way fees, overlapping event returns; no capacity/slippage/corporate-action audit; V2 ignores blocked status ONLY for offline research"}
    (out/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"status":report["status"],"symbols":report["symbols"],"events":report["events"],"errors":report["errors"],"results":report["results"]}))
    return 0 if not errors else 2
if __name__=="__main__":raise SystemExit(main())
