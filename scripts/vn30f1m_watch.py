#!/usr/bin/env python3
"""VN30F1M Futures Engine v2 - dedicated F1-F4 system.

DNSE -> F1-F4 -> VN30 confirmation -> Basis -> OI -> Futures Risk Engine
-> Signal History -> Telegram.

F1 Trend Following
F2 Breakout + Retest
F3 Range Reversal
F4 VWAP Reclaim / Breakdown

Paper/alert only. No order placement.
FALSE POSITIVE = zero tolerance. FALSE NEGATIVE = acceptable.
"""
from __future__ import annotations
import json, math, os, time
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

# KBS is the authoritative live OI source. DNSE derivative chart payload does not expose OI.
try:
    from scripts.kbs_oi_adapter_v1 import get_snapshot as get_kbs_oi_snapshot
except ImportError:
    from kbs_oi_adapter_v1 import get_snapshot as get_kbs_oi_snapshot

SYMBOL="VN30F1M"; SPOT="VN30"
ENDPOINTS = {
    "VN30F1M": [
        "https://services.entrade.com.vn/chart-api/v2/ohlcs/derivative",
        "https://api.dnse.com.vn/chart-api/v2/ohlcs/derivative",
    ],
    "VN30": [
        "https://services.entrade.com.vn/chart-api/v2/ohlcs/index",
        "https://api.dnse.com.vn/chart-api/v2/ohlcs/index",
    ],
}
RISK_PER_TRADE_VND=400_000; POINT_VALUE_VND=100_000; MAX_CONTRACTS=1
MIN_SCORE=75; MIN_RR=2.0; MIN_VOL_RATIO=1.30
OI_MIN_CHANGE_PCT=0.0; BASIS_SOFT_LIMIT=12.0; MAX_CHASE_POINTS=2.5; KBS_PRICE_TOLERANCE=5.0
VN_TZ=ZoneInfo("Asia/Ho_Chi_Minh")
STATE_PATH=Path("data/vn30f1m_watch_state.json")
HISTORY_PATH=Path("data/vn30f1m_signal_history.jsonl")
HEADERS={"accept":"application/json, text/plain, */*","origin":"https://www.dnse.com.vn","referer":"https://www.dnse.com.vn/","user-agent":"Mozilla/5.0"}

def in_session(now):
    t=now.time()
    return dtime(8,45)<=t<=dtime(11,30) or dtime(13,0)<=t<=dtime(14,45)

def fetch(symbol,resolution,seconds):
    n=int(time.time())
    params={"from":n-seconds,"to":n,"symbol":symbol,"resolution":resolution}
    attempts=[]
    for endpoint in ENDPOINTS[symbol]:
        try:
            r=requests.get(endpoint,params=params,headers=HEADERS,timeout=15)
            attempts.append({"endpoint":endpoint,"status_code":r.status_code,"url":r.url})
            if not r.ok:
                continue
            d=r.json()
            if not isinstance(d,dict):
                raise RuntimeError(f"{symbol}: invalid DNSE response")
            return d, endpoint, attempts
        except Exception as e:
            attempts.append({"endpoint":endpoint,"error":f"{type(e).__name__}: {e}"})
    raise RuntimeError(f"{symbol}: all DNSE endpoints failed: {attempts}")

def _series(d, keys):
    for key in keys:
        value=d.get(key)
        if isinstance(value,list):
            return value
    return []

def bars(d):
    vals=[_series(d,("t","time")), _series(d,("o","open")),
          _series(d,("h","high")), _series(d,("l","low")),
          _series(d,("c","close")), _series(d,("v","volume"))]
    oi=_series(d,("oi","openInterest","open_interest","openinterest"))
    n=min(map(len,vals)); out=[]
    for i in range(n):
        try:
            x={"t":float(vals[0][i]),"o":float(vals[1][i]),"h":float(vals[2][i]),"l":float(vals[3][i]),"c":float(vals[4][i]),"v":float(vals[5][i])}
            if i<len(oi) and oi[i] not in (None,""): x["oi"]=float(oi[i])
            out.append(x)
        except (TypeError,ValueError): pass
    return out

def ema(v,n):
    if len(v)<n:return 0.0
    e=sum(v[:n])/n;k=2/(n+1)
    for x in v[n:]:e=x*k+e*(1-k)
    return e

def atr(b,n=14):
    if len(b)<n+1:return 0.0
    tr=[max(b[i]["h"]-b[i]["l"],abs(b[i]["h"]-b[i-1]["c"]),abs(b[i]["l"]-b[i-1]["c"])) for i in range(1,len(b))]
    return sum(tr[-n:])/n

def vwap(b):
    if not b:return 0.0
    day=datetime.fromtimestamp(b[-1]["t"],VN_TZ).date()
    x=[z for z in b if datetime.fromtimestamp(z["t"],VN_TZ).date()==day]
    vol=sum(z["v"] for z in x)
    return sum(((z["h"]+z["l"]+z["c"])/3)*z["v"] for z in x)/vol if vol else 0.0

def volume_ratio(b):
    x=b[:-1]
    if len(x)<25:return 0.0
    base=sum(z["v"] for z in x[-21:-1])/20
    return x[-1]["v"]/base if base>0 else 0.0

def market_regime(b):
    c=[z["c"] for z in b[:-1]]
    if len(c)<60:return "UNKNOWN"
    e20,e50=ema(c,20),ema(c,50); r20=c[-1]/c[-21]-1
    if c[-1]>e20>e50 and r20>0.001:return "TREND_UP"
    if c[-1]<e20<e50 and r20<-0.001:return "TREND_DOWN"
    hi=max(z["h"] for z in b[-60:-1]);lo=min(z["l"] for z in b[-60:-1])
    return "RANGE" if (hi-lo)/c[-1]<0.012 else "CHOPPY"

def vn30_confirmation(v,side):
    c=[z["c"] for z in v[:-1]]
    if len(c)<30:return False
    e10,e30=ema(c,10),ema(c,30)
    return (side=="LONG" and c[-1]>e10>e30) or (side=="SHORT" and c[-1]<e10<e30)

def oi_snapshot(kbs_snapshot, futures_price):
    """Normalize the live KBS OI snapshot for the futures engine.

    KBS /derivative/iss provides current OI, but not an intraday OI time series.
    Therefore v1 uses OI availability + contract/price validation as the hard
    data-quality gate. Directional OI delta is deliberately left unavailable
    until a persistent intraday OI history source is added.
    """
    if not isinstance(kbs_snapshot, dict):
        return None
    oi=kbs_snapshot.get("open_interest")
    price=kbs_snapshot.get("price")
    try:
        oi=float(oi)
        price=float(price)
    except (TypeError,ValueError):
        return None
    if oi<=0 or price<=0:
        return None
    if kbs_snapshot.get("source")!="KBS" or kbs_snapshot.get("underlying")!="VN30":
        return None
    price_gap=abs(float(futures_price)-price)
    return {
        "current":oi,
        "previous":None,
        "delta":None,
        "delta_pct":None,
        "vs_avg_pct":None,
        "source":"KBS",
        "contract_code":kbs_snapshot.get("contract_code"),
        "contract_name":kbs_snapshot.get("contract_name"),
        "timestamp":kbs_snapshot.get("timestamp"),
        "expiry":kbs_snapshot.get("expiry"),
        "market_status":kbs_snapshot.get("market_status"),
        "price":price,
        "price_gap":price_gap,
        "price_valid":price_gap<=KBS_PRICE_TOLERANCE,
    }

def basis_snapshot(fut,spot):
    if not fut or not spot:return None
    f=fut[-1]["c"]; s=spot[-1]["c"]
    return {"futures":f,"vn30":s,"basis":f-s,"basis_pct":((f/s)-1)*100 if s else 0.0}

def bullish(b,p):return b["c"]>b["o"] and b["c"]>p["c"] and b["c"]>=b["l"]+(b["h"]-b["l"])*0.55
def bearish(b,p):return b["c"]<b["o"] and b["c"]<p["c"] and b["c"]<=b["h"]-(b["h"]-b["l"])*0.55

def f1(b,reg,vw):
    c=b[-1]["c"]; e=ema([z["c"] for z in b[:-1]],20)
    if reg=="TREND_UP" and c>e and b[-2]["c"]<=e and c>=vw-.5:return {"strategy":"F1 Trend Following","side":"LONG","entry":c,"level":e,"trigger":"EMA20 reclaim + VWAP support"}
    if reg=="TREND_DOWN" and c<e and b[-2]["c"]>=e and c<=vw+.5:return {"strategy":"F1 Trend Following","side":"SHORT","entry":c,"level":e,"trigger":"EMA20 breakdown + VWAP resistance"}
    return None

def f2(b,vr,vw):
    c=b[-1]["c"]; p=b[-21:-1]
    if len(p)<20 or vr<MIN_VOL_RATIO:return None
    hi=max(z["h"] for z in p);lo=min(z["l"] for z in p);x=b[-4:]
    if c>hi and any(z["l"]<=hi+0.5 for z in x[1:]) and c-hi<=MAX_CHASE_POINTS and c>=vw-1:return {"strategy":"F2 Breakout + Retest","side":"LONG","entry":c,"level":hi,"trigger":f"Breakout/retest {hi:.2f} + volume {vr:.2f}x"}
    if c<lo and any(z["h"]>=lo-0.5 for z in x[1:]) and lo-c<=MAX_CHASE_POINTS and c<=vw+1:return {"strategy":"F2 Breakout + Retest","side":"SHORT","entry":c,"level":lo,"trigger":f"Breakdown/retest {lo:.2f} + volume {vr:.2f}x"}
    return None

def f3(b,reg):
    if reg!="RANGE":return None
    x=b[-31:-1];hi=max(z["h"] for z in x);lo=min(z["l"] for z in x);c=b[-1]
    if hi==lo:return None
    if c["c"]-lo<=(hi-lo)*.12 and bullish(c,b[-2]):return {"strategy":"F3 Range Reversal","side":"LONG","entry":c["c"],"level":lo,"trigger":f"Range low rejection {lo:.2f} + bullish reversal"}
    if hi-c["c"]<=(hi-lo)*.12 and bearish(c,b[-2]):return {"strategy":"F3 Range Reversal","side":"SHORT","entry":c["c"],"level":hi,"trigger":f"Range high rejection {hi:.2f} + bearish reversal"}
    return None

def f4(b,vw):
    x=b[-4:-1];c=b[-1]["c"]
    if x[0]["c"]<=vw and x[-1]["c"]>vw and c>vw:return {"strategy":"F4 VWAP Reclaim","side":"LONG","entry":c,"level":vw,"trigger":f"VWAP reclaim {vw:.2f} + hold"}
    if x[0]["c"]>=vw and x[-1]["c"]<vw and c<vw:return {"strategy":"F4 VWAP Breakdown","side":"SHORT","entry":c,"level":vw,"trigger":f"VWAP breakdown {vw:.2f} + hold"}
    return None

def risk_engine(sig,b):
    a=atr(b[:-1]);e=sig["entry"];side=sig["side"]
    if not a:return None
    lo=min(z["l"] for z in b[-6:-1]);hi=max(z["h"] for z in b[-6:-1])
    sl=min(sig["level"]-0.25*a,lo) if side=="LONG" else max(sig["level"]+0.25*a,hi)
    pts=e-sl if side=="LONG" else sl-e
    rv=pts*POINT_VALUE_VND
    if pts<=0 or rv>RISK_PER_TRADE_VND:return None
    return {"entry":e,"sl":sl,"tp1":e+(2*pts if side=="LONG" else -2*pts),"tp2":e+(3*pts if side=="LONG" else -3*pts),
            "rr":2.0,"risk_points":pts,"risk_vnd":rv,"contracts":1,"atr14":a}

def score(sig,b,vr,vn30_ok,basis,oi,risk):
    c=b[:-1];last,prev=c[-1],c[-2]
    pa=(10 if (last["c"]>last["o"])==(sig["side"]=="LONG") else 0)+(10 if (last["c"]>prev["c"])==(sig["side"]=="LONG") else 0)
    structure=25 if sig["strategy"]=="F2 Breakout + Retest" else 22
    volume=20 if vr>=1.8 else 17 if vr>=1.5 else 10
    e20,e50=ema([z["c"] for z in c],20),ema([z["c"] for z in c],50)
    momentum=15 if ((e20>e50)==(sig["side"]=="LONG")) else 3
    confirm=15 if vn30_ok else 0
    rr=5 if risk and risk["rr"]>=MIN_RR else 0
    return min(100,structure+pa+volume+momentum+confirm+rr),{"structure":structure,"price_action":pa,"volume":volume,"momentum":momentum,"vn30_confirmation":confirm,"rr":rr}

def load_state():
    try:return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:return {}

def save_state(x):
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True);STATE_PATH.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")

def history(x):
    HISTORY_PATH.parent.mkdir(parents=True,exist_ok=True)
    with HISTORY_PATH.open("a",encoding="utf-8") as f:f.write(json.dumps(x,ensure_ascii=False)+"\n")

def telegram(msg):
    r=requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",json={"chat_id":os.environ["TELEGRAM_CHAT_ID"],"text":msg},timeout=15);r.raise_for_status()

def main():
    now=datetime.now(VN_TZ)
    if now.weekday()>=5 or not in_session(now):return 0
    fut_payload,fut_endpoint,fut_attempts=fetch(SYMBOL,"1",86400)
    v30_payload,v30_endpoint,v30_attempts=fetch(SPOT,"5",5*86400)
    fut=bars(fut_payload);v30=bars(v30_payload)
    if len(fut)<70 or len(v30)<30:
        raise RuntimeError(
            f"Insufficient DNSE data | VN30F1M endpoint={fut_endpoint} bars={len(fut)} | "
            f"VN30 endpoint={v30_endpoint} bars={len(v30)}"
        )
    reg=market_regime(fut);vw=vwap(fut);vr=volume_ratio(fut);bs=basis_snapshot(fut[:-1],v30[:-1])
    try:
        kbs_oi=get_kbs_oi_snapshot()
    except Exception as e:
        history({"timestamp":now.isoformat(),"symbol":SYMBOL,"status":"WAIT","market_regime":reg,"futures_endpoint":fut_endpoint,"vn30_endpoint":v30_endpoint,"basis":bs,
                 "oi_status":"UNAVAILABLE","oi_source":"KBS","reason":f"KBS OI adapter failed: {type(e).__name__}: {e}"})
        return 0
    oi=oi_snapshot(kbs_oi,fut[-1]["c"])
    oi_status="AVAILABLE" if oi is not None else "INVALID"
    oi_source="KBS /derivative/iss"
    candidates=[f1(fut[:-1],reg,vw),f2(fut[:-1],vr,vw),f3(fut[:-1],reg),f4(fut[:-1],vw)]
    candidates=[x for x in candidates if x]
    if not candidates:
        history({"timestamp":now.isoformat(),"symbol":SYMBOL,"status":"WAIT","market_regime":reg,"futures_endpoint":fut_endpoint,"vn30_endpoint":v30_endpoint,"basis":bs,"oi":oi,"oi_status":oi_status,"oi_source":oi_source,"reason":"no confirmed F1-F4 setup"});return 0
    priority={"F2 Breakout + Retest":4,"F1 Trend Following":3,"F4 VWAP Reclaim":2,"F4 VWAP Breakdown":2,"F3 Range Reversal":1}
    candidates.sort(key=lambda x:priority[x["strategy"]],reverse=True)
    for sig in candidates:
        vn_ok=vn30_confirmation(v30,sig["side"]);risk=risk_engine(sig,fut[:-1]);sc,parts=score(sig,fut,vr,vn_ok,bs,oi,risk)
        blocked=[]
        if reg=="CHOPPY" or reg=="UNKNOWN":blocked.append(f"regime={reg}")
        if reg=="TREND_UP" and sig["side"]=="SHORT" and sig["strategy"]!="F3 Range Reversal":blocked.append("counter-trend SHORT")
        if reg=="TREND_DOWN" and sig["side"]=="LONG" and sig["strategy"]!="F3 Range Reversal":blocked.append("counter-trend LONG")
        if reg=="RANGE" and sig["strategy"] not in ("F3 Range Reversal","F4 VWAP Reclaim","F4 VWAP Breakdown"):blocked.append("range strategy mismatch")
        if not vn_ok:blocked.append("VN30 5M confirmation failed")
        if bs is None:blocked.append("basis unavailable")
        elif abs(bs["basis"])>BASIS_SOFT_LIMIT:blocked.append(f"basis extreme={bs['basis']:.2f}")
        if oi is None:blocked.append("KBS OI unavailable/invalid")
        elif not oi["price_valid"]:blocked.append(f"KBS/DNSE price mismatch={oi['price_gap']:.2f} pts")
        if sc<MIN_SCORE:blocked.append(f"score={sc}<75")
        if risk is None:blocked.append("risk_engine_failed_or_risk>400k")
        rec={"timestamp":now.isoformat(),"symbol":SYMBOL,"strategy":sig["strategy"],"side":sig["side"],"market_regime":reg,"score":sc,"score_parts":parts,
             "entry":sig["entry"],"trigger":sig["trigger"],"volume_ratio":vr,"futures_endpoint":fut_endpoint,"vn30_endpoint":v30_endpoint,"basis":bs,"oi":oi,"oi_status":oi_status,"oi_source":oi_source,"kbs_oi_snapshot":kbs_oi,"vn30_confirmation":vn_ok,"risk":risk,
             "status":"BLOCKED" if blocked else "ALERTED","block_reasons":blocked}
        history(rec)
        if blocked:continue
        state=load_state();key=f"{now:%Y-%m-%d}|{sig['strategy']}|{sig['side']}"
        if state.get("alert_keys",{}).get(key):return 0
        r=risk;msg=(f"🚨 VN30F1M {sig['side']}\n\nStrategy: {sig['strategy']}\nRegime: {reg}\nScore: {sc}/100\n"
                    f"Entry: {r['entry']:.1f}\nSL: {r['sl']:.1f}\nTP1: {r['tp1']:.1f}\nTP2: {r['tp2']:.1f}\n"
                    f"R:R: 1:{r['rr']:.1f}\nSize: 1 HĐ\nRisk: {r['risk_vnd']:,.0f} VND\n"
                    f"Volume: {vr:.2f}x\nBasis: {bs['basis']:.2f}\nOI: {oi['current']:,.0f} (KBS, live)\nContract: {oi['contract_code']}\n"
                    f"VN30 5M: CONFIRMED\nTrigger: {sig['trigger']}\n\nPAPER TRADE / manual check only.\nSafety: FALSE POSITIVE = NGHIÊM CẤM.")
        telegram(msg);state.setdefault("alert_keys",{})[key]=now.isoformat();save_state(state);return 0
    return 0

if __name__=="__main__":raise SystemExit(main())
