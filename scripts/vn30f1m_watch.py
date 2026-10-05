#!/usr/bin/env python3
"""VN30F1M S1-S5 conservative signal watcher.

LONG/SHORT/WAIT only. Paper-trading / alerting: never places orders.
FALSE POSITIVE = zero tolerance. FALSE NEGATIVE = acceptable.
Risk: 1 contract maximum, 400k VND/trade.
"""
from __future__ import annotations
import json, math, os, time
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

SYMBOL="VN30F1M"
SPOT="VN30"
BASE_URL="https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"
RISK_PER_TRADE_VND=400_000
POINT_VALUE_VND=100_000
MAX_CONTRACTS=1
MIN_SCORE=75
MIN_RR=2.0
MIN_VOL_RATIO=1.50
CHASE_PCT=0.25
RETEST_PCT=0.15
VN_TZ=ZoneInfo("Asia/Ho_Chi_Minh")
STATE_PATH=Path("data/vn30f1m_watch_state.json")
HISTORY_PATH=Path("data/signal_history.jsonl")
HEADERS={"accept":"application/json, text/plain, */*","origin":"https://www.dnse.com.vn","referer":"https://www.dnse.com.vn/","user-agent":"Mozilla/5.0"}

def in_session(now):
    t=now.time()
    return dtime(8,45)<=t<=dtime(11,30) or dtime(13,0)<=t<=dtime(14,45)

def fetch(symbol,resolution,seconds):
    now=int(time.time())
    r=requests.get(BASE_URL,params={"from":now-seconds,"to":now,"symbol":symbol,"resolution":resolution},
                   headers=HEADERS,timeout=15)
    r.raise_for_status()
    data=r.json()
    if not isinstance(data,dict): raise RuntimeError(f"{symbol}: invalid response")
    return data

def bars(data):
    keys=("t","o","h","l","c","v")
    vals=[data.get(k) or [] for k in keys]
    n=min(map(len,vals))
    out=[]
    for i in range(n):
        try: out.append({"t":float(vals[0][i]),"o":float(vals[1][i]),"h":float(vals[2][i]),
                         "l":float(vals[3][i]),"c":float(vals[4][i]),"v":float(vals[5][i])})
        except (TypeError,ValueError): pass
    return out

def sma(v,n): return sum(v[-n:])/n if len(v)>=n else 0.0
def ema(v,n):
    if len(v)<n: return 0.0
    e=sum(v[:n])/n; k=2/(n+1)
    for x in v[n:]: e=x*k+e*(1-k)
    return e

def rsi(v,n=14):
    if len(v)<n+1: return 50.0
    gains=[]; losses=[]
    for i in range(len(v)-n,len(v)):
        d=v[i]-v[i-1]; gains.append(max(d,0)); losses.append(max(-d,0))
    ag=sum(gains)/n; al=sum(losses)/n
    if al==0: return 100.0 if ag else 50.0
    rs=ag/al; return 100-(100/(1+rs))

def atr(bs,n=14):
    if len(bs)<n+1: return 0.0
    tr=[]
    for i in range(1,len(bs)):
        b,p=bs[i],bs[i-1]
        tr.append(max(b["h"]-b["l"],abs(b["h"]-p["c"]),abs(b["l"]-p["c"])))
    return sum(tr[-n:])/n

def bullish(b,p): return b["c"]>b["o"] and b["c"]>p["c"] and b["c"]>=b["l"]+(b["h"]-b["l"])*0.55
def bearish(b,p): return b["c"]<b["o"] and b["c"]<p["c"] and b["c"]<=b["h"]-(b["h"]-b["l"])*0.55

def volume_ratio(bs):
    c=bs[:-1]
    if len(c)<25: return 0.0
    return c[-1]["v"]/sma([b["v"] for b in c[-21:-1]],20) if sma([b["v"] for b in c[-21:-1]],20)>0 else 0.0

def regime(bs):
    c=[b["c"] for b in bs[:-1]]
    if len(c)<60: return "UNKNOWN"
    e20,e50=ema(c,20),ema(c,50)
    r20=c[-1]/c[-21]-1
    if c[-1]>e20>e50 and r20>0.001: return "TREND_UP"
    if c[-1]<e20<e50 and r20<-0.001: return "TREND_DOWN"
    if abs(e20-e50)/e50<0.0015: return "RANGE"
    return "CHOPPY"

def vn30_confirmation(vn30_5m, direction):
    c=[b["c"] for b in vn30_5m[:-1]]
    if len(c)<30: return False
    e10,e30=ema(c,10),ema(c,30)
    return (direction=="LONG" and c[-1]>e10>e30) or (direction=="SHORT" and c[-1]<e10<e30)

def detect_s3(b, direction):
    c=b[:-1]
    if len(c)<30: return None
    pivot=max(x["h"] for x in c[-20:]) if direction=="LONG" else min(x["l"] for x in c[-20:])
    recent=c[-3:]
    ok=all(x["c"]>pivot for x in recent) if direction=="LONG" else all(x["c"]<pivot for x in recent)
    trade=(recent[0]["h"]>pivot if direction=="LONG" else recent[0]["l"]<pivot)
    retest=any((x["l"]<=pivot*(1+RETEST_PCT/100) and x["c"]>pivot) if direction=="LONG"
               else (x["h"]>=pivot*(1-RETEST_PCT/100) and x["c"]<pivot) for x in recent[1:])
    price=recent[-1]["c"]
    chase=(price>pivot*(1+CHASE_PCT/100)) if direction=="LONG" else (price<pivot*(1-CHASE_PCT/100))
    if ok and trade and retest and volume_ratio(b)>=MIN_VOL_RATIO and not chase:
        return {"strategy":"S3 Breakout Momentum","direction":direction,"entry":price,"level":pivot,
                "trigger":f"3x 1M close {'>' if direction=='LONG' else '<'} {pivot:.2f} + retest + volume {volume_ratio(b):.2f}x"}
    return None

def detect_s4(b, direction):
    c=b[:-1]
    if len(c)<55: return None
    closes=[x["c"] for x in c]; e20,e50=ema(closes,20),ema(closes,50)
    last,prev=c[-1],c[-2]
    trend=(e20>e50 and last["c"]>=e20*0.998 and direction=="LONG") or (e20<e50 and last["c"]<=e20*1.002 and direction=="SHORT")
    reversal=bullish(last,prev) if direction=="LONG" else bearish(last,prev)
    contraction=last["v"]<=sma([x["v"] for x in c[-21:-1]],20)*1.10
    if trend and reversal and contraction:
        return {"strategy":"S4 Pullback Trend Following","direction":direction,"entry":last["c"],"level":e20,
                "trigger":f"EMA20/EMA50 trend + pullback/reversal + volume controlled"}
    return None

def detect_s1(b, direction):
    c=b[:-1]
    if len(c)<55: return None
    closes=[x["c"] for x in c]; e20,e50=ema(closes,20),ema(closes,50)
    last,prev=c[-1],c[-2]
    trend=(e20>e50 and last["c"]>e50 and direction=="LONG") or (e20<e50 and last["c"]<e50 and direction=="SHORT")
    reversal=bullish(last,prev) if direction=="LONG" else bearish(last,prev)
    if trend and reversal:
        return {"strategy":"S1 Stock Swing Trading","direction":direction,"entry":last["c"],"level":e20,
                "trigger":"EMA trend + confirmed price-action reversal"}
    return None

def detect_s2(b, direction):
    c=b[:-1]
    if len(c)<30: return None
    closes=[x["c"] for x in c]; e20=ema(closes,20); rr=rsi(closes)
    lo=min(x["l"] for x in c[-20:]); hi=max(x["h"] for x in c[-20:])
    last,prev=c[-1],c[-2]
    if direction=="LONG":
        ok=last["c"]<=e20*0.996 and rr<=35 and last["c"]<=lo*1.002 and bullish(last,prev)
        level=lo
    else:
        ok=last["c"]>=e20*1.004 and rr>=65 and last["c"]>=hi*0.998 and bearish(last,prev)
        level=hi
    if ok:
        return {"strategy":"S2 Mean Reversion","direction":direction,"entry":last["c"],"level":level,
                "trigger":f"mean deviation + RSI {rr:.1f} + boundary + reversal"}
    return None

def detect_s5(b, direction):
    c=b[:-1]
    if len(c)<50: return None
    seg=[c[-15:-10],c[-10:-5],c[-5:]]
    ranges=[sma([(x["h"]-x["l"])/x["c"] for x in s],len(s)) for s in seg]
    vols=[sma([x["v"] for x in s],len(s)) for s in seg]
    contracting=ranges[1]<=ranges[0]*0.8 and ranges[2]<=ranges[1]*0.8 and vols[1]<=vols[0]*0.85 and vols[2]<=vols[1]*0.85
    return detect_s3(b,direction) if contracting else None

def candidates(b):
    out=[]
    for d in ("LONG","SHORT"):
        for fn in (detect_s5,detect_s3,detect_s4,detect_s1,detect_s2):
            x=fn(b,d)
            if x: out.append(x)
    return out

def risk_engine(signal,b):
    c=b[:-1]; a=atr(c,14)
    if a<=0: return None
    entry=signal["entry"]; d=signal["direction"]
    if d=="LONG":
        sl=min(entry-0.8*a, min(x["l"] for x in c[-5:]))
        risk_pts=entry-sl; tp1=entry+2*risk_pts; tp2=entry+3*risk_pts
    else:
        sl=max(entry+0.8*a, max(x["h"] for x in c[-5:]))
        risk_pts=sl-entry; tp1=entry-2*risk_pts; tp2=entry-3*risk_pts
    risk_vnd=risk_pts*POINT_VALUE_VND
    if risk_pts<=0 or risk_vnd>RISK_PER_TRADE_VND or risk_vnd<=0: return None
    return {"entry":entry,"sl":sl,"tp1":tp1,"tp2":tp2,"rr":2.0,"contracts":1,
            "risk_points":risk_pts,"risk_vnd":risk_vnd,"atr14":a}

def score(signal,b,vr,confirmed,risk):
    c=b[:-1]; last,prev=c[-1],c[-2]
    pa=(10 if (last["c"]>last["o"])==(signal["direction"]=="LONG") else 0)+(10 if (last["c"]>prev["c"])==(signal["direction"]=="LONG") else 0)
    vol=20 if vr>=1.8 else 17 if vr>=1.5 else 10
    e20,e50=ema([x["c"] for x in c],20),ema([x["c"] for x in c],50)
    momentum=15 if ((e20>e50)==(signal["direction"]=="LONG")) else 3
    structure=25 if signal["strategy"] in ("S3 Breakout Momentum","S5 VCP Breakout") else 22
    confirmation=15 if confirmed else 0
    rr=5 if risk and risk["rr"]>=MIN_RR else 0
    total=min(100,structure+pa+vol+momentum+confirmation+rr)
    return total,{"structure":structure,"price_action":pa,"volume":vol,"momentum":momentum,"vn30_confirmation":confirmation,"rr":rr}

def load_state():
    try: return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception: return {}

def save_state(x):
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True)
    STATE_PATH.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")

def append_history(x):
    HISTORY_PATH.parent.mkdir(parents=True,exist_ok=True)
    with HISTORY_PATH.open("a",encoding="utf-8") as f: f.write(json.dumps(x,ensure_ascii=False)+"\n")

def telegram(msg):
    token=os.environ["TELEGRAM_BOT_TOKEN"]; chat=os.environ["TELEGRAM_CHAT_ID"]
    r=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":chat,"text":msg},timeout=15)
    r.raise_for_status()

def main():
    now=datetime.now(VN_TZ)
    if now.weekday()>=5 or not in_session(now): return 0
    f1=bars(fetch(SYMBOL,"1",24*60*60))
    v30=bars(fetch(SPOT,"5",5*24*60*60))
    if len(f1)<60 or len(v30)<30: print("VN30F1M: insufficient data"); return 0
    reg=regime(f1); vr=volume_ratio(f1)
    cands=candidates(f1)
    if not cands:
        print(f"VN30F1M: WAIT | regime={reg} | no confirmed S1-S5 setup"); return 0
    state=load_state()
    priority={"S5 VCP Breakout":5,"S3 Breakout Momentum":4,"S4 Pullback Trend Following":3,"S1 Stock Swing Trading":2,"S2 Mean Reversion":1}
    cands.sort(key=lambda x:priority.get(x["strategy"],0),reverse=True)
    for sig in cands:
        confirmed=vn30_confirmation(v30,sig["direction"])
        risk=risk_engine(sig,f1)
        score_v,parts=score(sig,f1,vr,confirmed,risk)
        allowed=(reg=="TREND_UP" and sig["direction"]=="LONG") or (reg=="TREND_DOWN" and sig["direction"]=="SHORT") or (reg=="RANGE" and sig["strategy"]=="S2 Mean Reversion")
        blocked=[]
        if not allowed: blocked.append(f"regime={reg} incompatible")
        if not confirmed: blocked.append("VN30 5M confirmation failed")
        if score_v<MIN_SCORE: blocked.append(f"score={score_v}<{MIN_SCORE}")
        if risk is None: blocked.append("risk_engine_failed_or_risk>400k")
        rec={"timestamp":now.isoformat(),"symbol":SYMBOL,"strategy":sig["strategy"],"direction":sig["direction"],
             "market_regime":reg,"score":score_v,"score_parts":parts,"price":sig["entry"],"trigger":sig["trigger"],
             "volume_ratio":vr,"vn30_confirmation":confirmed,"risk":risk,
             "basis":"not_available_in_this_v1","open_interest":"not_available_in_this_v1",
             "status":"BLOCKED" if blocked else "ALERTED","block_reasons":blocked}
        append_history(rec)
        if blocked:
            print(f"VN30F1M {sig['strategy']} {sig['direction']}: BLOCKED {blocked}")
            continue
        key=f"{now:%Y-%m-%d}|{sig['strategy']}|{sig['direction']}"
        if state.get("alert_keys",{}).get(key):
            print("VN30F1M: alert already sent"); return 0
        r=risk
        msg=(f"🚨 VN30F1M CONFIRMED — {sig['direction']}\n\n"
             f"Strategy: {sig['strategy']}\nMarket Regime: {reg}\nScore: {score_v}/100\n"
             f"Entry: {r['entry']:.2f}\nSL: {r['sl']:.2f}\nTP1: {r['tp1']:.2f}\nTP2: {r['tp2']:.2f}\n"
             f"R:R: 1:{r['rr']:.2f}\nSize: 1 HĐ\nRisk: {r['risk_vnd']:,.0f} VND\n"
             f"Volume: {vr:.2f}x\nTrigger: {sig['trigger']}\n"
             f"VN30 5M: CONFIRMED\nBasis/OI: chưa có trong v1\n\n"
             f"Action: PAPER TRADE / manual check only.\nSafety: FALSE POSITIVE = NGHIÊM CẤM.")
        telegram(msg); state.setdefault("alert_keys",{})[key]=now.isoformat(); save_state(state)
        print("VN30F1M: ALERTED",sig["strategy"],sig["direction"])
        return 0
    print("VN30F1M: no tradeable signal")
    return 0

if __name__=="__main__": raise SystemExit(main())
