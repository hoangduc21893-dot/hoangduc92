"""DS1 Pre-Breakout V2 research only. No orders, alerts, or production score changes."""
from __future__ import annotations
import json, argparse
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.ds1_market_wide import Client, pre_breakout_rank

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
WEIGHTS = {"trend":15,"base":15,"pivot":10,"dryup":10,"contraction":10,
           "relative_strength":15,"accumulation":10,"liquidity":10,"market_sector":5}
ACTIVE = ("PVT","PVS","MSB","HAH","BSR","VGC","DHC","VPB","MWG","HDB","PET",
          "HPG","DCM","GMD","PLX","ANV","VHC","PHR","TCB")
WATCH_RISK = ("GVR",)

def mean(values):
    return sum(values)/len(values) if values else 0.0

def score_v2(daily, benchmark, *, sector_strength=None, market_regime=None):
    """Every score uses completed 1D bars only; unavailable benchmark blocks readiness."""
    if len(daily)<60 or len(benchmark)<60:
        return {"score":None,"status":"INSUFFICIENT_DATA","reasons":["need 60 complete daily bars"]}
    if any(not all(k in b and isinstance(b[k],(float,int)) for k in ("o","h","l","c","v")) for b in daily[-60:]+benchmark[-60:]):
        return {"score":None,"status":"INVALID_DATA","reasons":["bad OHLCV"]}
    if any(b["c"]<=0 or b["v"]<0 or b["h"]<max(b["o"],b["c"]) or b["l"]>min(b["o"],b["c"]) for b in daily[-60:]+benchmark[-60:]):
        return {"score":None,"status":"INVALID_DATA","reasons":["invalid prices or volume"]}
    c=[b["c"] for b in daily]; bc=[b["c"] for b in benchmark]
    ma20=mean(c[-20:]); ma50=mean(c[-50:]); close=c[-1]
    pivot=max(b["h"] for b in daily[-21:-1])
    distance=100*(pivot-close)/pivot
    recent=daily[-20:]; first=recent[:10]; last=recent[10:]
    avg_range=lambda bars:mean([(b["h"]-b["l"])/b["c"] for b in bars])
    range_contract=avg_range(last)<=0.85*avg_range(first) if avg_range(first)>0 else False
    vol_dry=mean([b["v"] for b in last])<=0.85*mean([b["v"] for b in first]) if mean([b["v"] for b in first])>0 else False
    rs20=100*((close/c[-21]-1)-(bc[-1]/bc[-21]-1))
    # Proxy metrics, not evidence of institutional accumulation.
    clv=[((2*b["c"]-b["h"]-b["l"])/(b["h"]-b["l"]) if b["h"]>b["l"] else 0) for b in recent]
    pressure=mean(clv)
    liquidity_vnd=mean([b["c"]*b["v"] for b in recent])
    base_depth=100*(max(b["h"] for b in recent)-min(b["l"] for b in recent))/max(b["h"] for b in recent)
    pts={
       "trend":15 if close>=ma20>ma50 else 0,
       "base":15 if base_depth<=12 and close>=min(b["l"] for b in recent)*1.03 else 0,
       "pivot":10 if 0<=distance<=5 else 0,
       "dryup":10 if vol_dry else 0,
       "contraction":10 if range_contract else 0,
       "relative_strength":15 if rs20>=3 else (8 if rs20>=0 else 0),
       "accumulation":10 if pressure>=0.15 else (5 if pressure>=0 else 0),
       "liquidity":10 if liquidity_vnd>=20_000_000_000 else 0,
       "market_sector":5 if market_regime=="TREND_UP" and sector_strength is not None and sector_strength>0 else 0
    }
    gates=[]
    if not (close>=ma20>ma50): gates.append("TREND_GATE")
    if not (0<=distance<=5): gates.append("PIVOT_GATE")
    if liquidity_vnd<20_000_000_000: gates.append("LIQUIDITY_GATE")
    if market_regime is None or sector_strength is None: gates.append("UNVERIFIED_MARKET_SECTOR")
    total=sum(pts.values())
    status=("PRIORITY_WATCH" if total>=85 else "WATCH" if total>=70 else "MONITOR" if total>=50 else "LOW_PRIORITY")
    if gates: status="RESEARCH_BLOCKED"
    return {"score":total,"status":status,"components":pts,"gates":gates,"metrics":{
        "close_vnd":round(close,2),"ma20":round(ma20,2),"ma50":round(ma50,2),
        "pivot20_vnd":round(pivot,2),"distance_pct":round(distance,2),
        "rs20_pct_points":round(rs20,2),"base_depth_pct":round(base_depth,2),
        "liquidity20_vnd":round(liquidity_vnd),"volume_dryup":vol_dry,
        "range_contraction":range_contract,"close_location_avg":round(pressure,3)}}

def compare(symbols, asof, client):
    now=datetime.fromisoformat(asof+"T23:00:00").replace(tzinfo=TZ)
    end=date.fromisoformat(asof)
    benchmark=[b for b in client.ohlcv("VN30","1D",now) if datetime.fromtimestamp(b["t"],TZ).date()<=end]
    results=[]
    for symbol in symbols:
        try:
            daily=[b for b in client.ohlcv(symbol,"1D",now) if datetime.fromtimestamp(b["t"],TZ).date()<=end]
            if not daily or datetime.fromtimestamp(daily[-1]["t"],TZ).date()!=end:
                raise ValueError("TARGET_DATE_MISSING")
            v1=pre_breakout_rank(daily)
            v2=score_v2(daily,benchmark)
            if symbol in WATCH_RISK:
                v2["status"]="WATCH_RISK"
                v2.setdefault("gates",[]).append("WATCH_RISK")
            results.append({"symbol":symbol,"v1":v1,"v2":v2})
        except Exception as exc:
            results.append({"symbol":symbol,"v1":None,"v2":{"score":None,"status":"DATA_ERROR","reason":str(exc)}})
    return {"asof":asof,"mode":"RESEARCH_ONLY","framework":"Pre-Breakout V2.0 experimental, thresholds NOT backtested",
            "market_sector_data":"UNAVAILABLE","symbols":results}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--date",required=True)
    parser.add_argument("--output",default="data/ds1_v2/pre_breakout_v2_research.json")
    args=parser.parse_args()
    result=compare(ACTIVE+WATCH_RISK,args.date,Client(interval=0.5))
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"asof":args.date,"mode":"RESEARCH_ONLY","count":len(result["symbols"]),
      "scores":[{"symbol":r["symbol"],"v1":r["v1"]["score"] if r["v1"] else None,
      "v2":r["v2"]["score"],"status":r["v2"]["status"]} for r in result["symbols"]]}))
    return 0 if all(x["v2"]["status"]!="DATA_ERROR" for x in result["symbols"]) else 2

if __name__=="__main__":raise SystemExit(main())
