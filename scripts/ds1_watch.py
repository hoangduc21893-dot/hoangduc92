#!/usr/bin/env python3
"""DS1 conservative scanner + Market Regime + Risk Engine + signal history.

FALSE POSITIVE = zero tolerance. FALSE NEGATIVE = acceptable.
Only confirmed S3/S4 setups can become Telegram alerts.
"""
from __future__ import annotations
import json, math, os, time
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

DS1 = ["PVT","PVS","MSB","HAH","BSR","VGC","DHC","VTP","VPB","MWG","HDB","PET"]
NAV_VND=100_000_000
RISK_PER_TRADE_VND=400_000
MAX_POSITION_PCT=0.20
BREAKOUT_LOOKBACK=20
MIN_CLOSED_1M_BARS=3
VOLUME_RATIO_MIN=1.50
RETEST_TOLERANCE_PCT=0.35
MAX_BREAKOUT_CHASE_PCT=1.10
S4_NEAR_MA_PCT=1.50
MIN_SCORE=75
MIN_RR=2.0
VN_TZ=ZoneInfo("Asia/Ho_Chi_Minh")
BASE_URL="https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"
STATE_PATH=Path("data/ds1_watch_state.json")
HISTORY_PATH=Path("data/signal_history.jsonl")
HEADERS={"accept":"application/json, text/plain, */*","origin":"https://www.dnse.com.vn","referer":"https://www.dnse.com.vn/","user-agent":"Mozilla/5.0"}

def in_session(now):
    t=now.time()
    return dtime(9,15)<=t<=dtime(11,30) or dtime(13,0)<=t<=dtime(14,45)

def fetch(symbol,resolution,seconds):
    now=int(time.time())
    r=requests.get(BASE_URL,params={"from":now-seconds,"to":now,"symbol":symbol,"resolution":resolution},headers=HEADERS,timeout=15)
    r.raise_for_status()
    data=r.json()
    if not isinstance(data,dict): raise RuntimeError(f"{symbol}: invalid DNSE response")
    return data

def bars(data):
    ts=data.get("t") or data.get("time") or []
    opens=data.get("o") or data.get("open") or []
    highs=data.get("h") or data.get("high") or []
    lows=data.get("l") or data.get("low") or []
    closes=data.get("c") or data.get("close") or []
    vols=data.get("v") or data.get("volume") or []
    n=min(len(ts),len(opens),len(highs),len(lows),len(closes),len(vols))
    out=[]
    for i in range(n):
        try: out.append({"t":float(ts[i]),"o":float(opens[i]),"h":float(highs[i]),"l":float(lows[i]),"c":float(closes[i]),"v":float(vols[i])})
        except (TypeError,ValueError): pass
    return out

def sma(values,n): return sum(values[-n:])/n if len(values)>=n else 0.0

def atr(values,n=14):
    if len(values)<n+1: return 0.0
    trs=[]
    for i in range(1,len(values)):
        b,p=values[i],values[i-1]
        trs.append(max(b["h"]-b["l"],abs(b["h"]-p["c"]),abs(b["l"]-p["c"])))
    return sum(trs[-n:])/n

def load_state():
    try: return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception: return {}

def save_state(state):
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True)
    STATE_PATH.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")

def append_history(record):
    HISTORY_PATH.parent.mkdir(parents=True,exist_ok=True)
    with HISTORY_PATH.open("a",encoding="utf-8") as f: f.write(json.dumps(record,ensure_ascii=False)+"\n")

def session_progress(now):
    if now.time()<=dtime(11,30): elapsed=(now.hour*60+now.minute)-555
    elif now.time()<dtime(13,0): elapsed=135
    else: elapsed=135+(now.hour*60+now.minute-780)
    return max(0.05,min(1.0,elapsed/240.0))

def volume_ratio(intraday,daily,now):
    completed=daily[:-1] if len(daily)>1 else daily
    vols=[b["v"] for b in completed[-20:] if b["v"]>0]
    if not vols: return 0.0
    adv20=sum(vols)/len(vols)
    cumulative=sum(b["v"] for b in intraday if datetime.fromtimestamp(b["t"],VN_TZ).date()==now.date())
    expected=adv20*session_progress(now)
    return cumulative/expected if expected>0 else 0.0

def market_regime(vn30):
    d=vn30[:-1]
    if len(d)<60: return "UNKNOWN"
    c=[b["c"] for b in d]; ma20,ma50=sma(c,20),sma(c,50)
    r20=c[-1]/c[-21]-1; r5=c[-1]/c[-6]-1
    spread=abs(ma20-ma50)/ma50 if ma50 else 1
    if c[-1]>ma20>ma50 and r20>0.015 and r5>-0.02: return "TREND_UP"
    if c[-1]<ma20<ma50 and r20<-0.015: return "TREND_DOWN"
    if spread<0.012 and abs(r20)<0.03: return "RANGE"
    return "CHOPPY"

def relative_strength(symbol_daily,vn30):
    a,b=symbol_daily[:-1],vn30[:-1]
    if len(a)<21 or len(b)<21: return 0.0
    return (a[-1]["c"]/a[-21]["c"]-1)-(b[-1]["c"]/b[-21]["c"]-1)

def score_signal(daily,vr,rs,strategy):
    d=daily[:-1]; c=[b["c"] for b in d]; last,prev=d[-1],d[-2]
    ma20,ma50=sma(c,20),sma(c,50)
    pa=(10 if last["c"]>last["o"] else 0)+(10 if last["c"]>prev["c"] else 0)
    structure=25 if strategy=="S3 Breakout Momentum" else (22 if abs(last["c"]-ma20)/ma20<=0.015 else 15)
    volume=20 if vr>=1.80 else 17 if vr>=1.50 else 10
    momentum=15 if last["c"]>ma20>ma50 else 8 if last["c"]>ma50 else 3
    rs_score=15 if rs>=0.05 else 12 if rs>=0.02 else 8 if rs>=0 else 4
    base=min(95,structure+pa+volume+momentum+rs_score)
    return base,{"structure":structure,"price_action":pa,"volume":volume,"momentum":momentum,"relative_strength":rs_score,"base_score":base}

def detect_s3(daily,intraday,vr):
    closed=intraday[:-1]; d=daily[:-1]
    if len(closed)<MIN_CLOSED_1M_BARS+1 or len(d)<BREAKOUT_LOOKBACK+5: return None
    breakout=max(b["h"] for b in d[-BREAKOUT_LOOKBACK:])
    recent=closed[-MIN_CLOSED_1M_BARS:]; price=recent[-1]["c"]
    confirmed=all(b["c"]>breakout for b in recent)
    trade_through=recent[0]["h"]>breakout
    retest=any(b["l"]<=breakout*(1+RETEST_TOLERANCE_PCT/100) and b["c"]>breakout for b in recent[1:])
    chase=price>breakout*(1+MAX_BREAKOUT_CHASE_PCT/100)
    if confirmed and trade_through and retest and vr>=VOLUME_RATIO_MIN and not chase:
        return {"strategy":"S3 Breakout Momentum","price":price,"level":breakout,"trigger":f"3x 1M closed > {breakout:.2f} + retest/hold + volume {vr:.2f}x"}
    return None

def detect_s4(daily,intraday):
    d=daily[:-1]; closed=intraday[:-1]
    if len(d)<55 or not closed: return None
    c=[b["c"] for b in d]; ma20,ma50=sma(c,20),sma(c,50)
    if ma20<=ma50: return None
    last,prev=d[-1],d[-2]
    near=abs(last["c"]-ma20)/ma20*100<=S4_NEAR_MA_PCT
    reversal=last["c"]>last["o"] and last["c"]>prev["c"]
    avg20v=sma([b["v"] for b in d],20)
    contraction=avg20v>0 and last["v"]<=avg20v*1.10
    price=closed[-1]["c"]
    if near and reversal and contraction and price>=last["c"]:
        return {"strategy":"S4 Pullback Trend Following","price":price,"level":ma20,"trigger":f"MA20 {ma20:.2f} > MA50 {ma50:.2f} + pullback/reversal + volume contraction"}
    return None

def risk_engine(price,level,daily,strategy):
    d=daily[:-1]; a=atr(d,14)
    if a<=0 or price<=0: return None
    recent_low=min(b["l"] for b in d[-3:] if strategy=="S3 Breakout Momentum") if strategy=="S3 Breakout Momentum" else min(b["l"] for b in d[-5:])
    sl=max(0.01,min(level-0.8*a,recent_low))
    risk_per_share=price-sl
    if risk_per_share<=0: return None
    entry=price; tp1=entry+2*risk_per_share; tp2=entry+3*risk_per_share
    shares_by_risk=math.floor(RISK_PER_TRADE_VND/(risk_per_share*100))*100
    max_shares=math.floor((NAV_VND*MAX_POSITION_PCT)/(entry*100))*100
    shares=max(0,min(shares_by_risk,max_shares))
    if shares<100: return None
    return {"entry":entry,"sl":sl,"tp1":tp1,"tp2":tp2,"rr":2.0,"risk_per_share":risk_per_share,"atr14":a,"shares":shares,"position_value":entry*shares,"risk_vnd":risk_per_share*shares}

def telegram(message):
    token=os.environ["TELEGRAM_BOT_TOKEN"]; chat_id=os.environ["TELEGRAM_CHAT_ID"]
    r=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":chat_id,"text":message},timeout=15)
    r.raise_for_status()

def main():
    now=datetime.now(VN_TZ)
    if now.weekday()>=5 or not in_session(now): return 0
    vn30=bars(fetch("VN30","1D",120*24*60*60)); regime=market_regime(vn30)
    print(f"MARKET REGIME={regime}")
    state=load_state(); alerts=0
    for symbol in DS1:
        try:
            intraday=bars(fetch(symbol,"1",24*60*60)); daily=bars(fetch(symbol,"1D",120*24*60*60))
            if len(intraday)<10 or len(daily)<60: print(f"{symbol}: insufficient data"); continue
            vr=volume_ratio(intraday,daily,now); rs=relative_strength(daily,vn30)
            signal=detect_s3(daily,intraday,vr) or detect_s4(daily,intraday)
            if signal is None: print(f"{symbol}: no confirmed setup"); continue
            score,parts=score_signal(daily,vr,rs,signal["strategy"]); risk=risk_engine(signal["price"],signal["level"],daily,signal["strategy"])
            blocked=[]
            if regime!="TREND_UP": blocked.append(f"regime={regime}")
            if score<MIN_SCORE: blocked.append(f"score={score}<{MIN_SCORE}")
            if risk is None: blocked.append("risk_engine_failed")
            elif risk["rr"]<MIN_RR: blocked.append(f"rr={risk['rr']:.2f}<2.0")
            record={"timestamp":now.isoformat(),"symbol":symbol,"strategy":signal["strategy"],"market_regime":regime,"score":score,"score_parts":parts,"price":signal["price"],"trigger":signal["trigger"],"volume_ratio":vr,"relative_strength_20d_vs_vn30":rs,"risk":risk,"status":"BLOCKED" if blocked else "ALERTED","block_reasons":blocked}
            append_history(record)
            if blocked: print(f"{symbol}: BLOCKED {blocked}"); continue
            key=f"{now:%Y-%m-%d}|{symbol}|{signal['strategy']}"
            if state.get("alert_keys",{}).get(key): print(f"{symbol}: alert already sent"); continue
            r=risk
            message=(f"🚨 DS1 CONFIRMED — {symbol}\n\n"
                     f"Strategy: {signal['strategy']}\nMarket Regime: {regime}\nScore: {score}/100\n"
                     f"Entry: {r['entry']:.2f}\nSL: {r['sl']:.2f}\nTP1: {r['tp1']:.2f}\nTP2: {r['tp2']:.2f}\n"
                     f"R:R: 1:{r['rr']:.2f}\nSize: {r['shares']:,} cp | Position: {r['position_value']:,.0f} VND\n"
                     f"Risk: {r['risk_vnd']:,.0f} VND\nVolume: {vr:.2f}x | RS20D: {rs*100:.1f}pp vs VN30\n"
                     f"Trigger: {signal['trigger']}\n\nAction: BUY only after final manual check.\nSafety: FALSE POSITIVE = NGHIÊM CẤM.")
            telegram(message); state.setdefault("alert_keys",{})[key]=now.isoformat(); save_state(state); alerts+=1
        except Exception as exc: print(f"{symbol}: ERROR {exc}")
    print(f"DS1 scan complete. Alerts={alerts}/{len(DS1)}")
    return 0

if __name__=="__main__": raise SystemExit(main())
