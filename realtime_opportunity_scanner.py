import argparse, json, os, time
import pandas as pd
import requests

DS1 = ["PVT","PVS","MSB","TVS","PET","HAH","BSR","VPI","VGC","DHC","VTP","VPB","MWG"]
URL = "https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"
THRESHOLD = float(os.getenv("SCANNER_CANDIDATE_THRESHOLD","55"))
COOLDOWN = int(os.getenv("SCANNER_COOLDOWN_SECONDS","900"))
STATE = os.getenv("SCANNER_STATE_FILE","data/realtime_scanner_state.json")

def fetch_1m(symbol, bars=120):
    now=int(time.time())
    r=requests.get(URL,params={"symbol":symbol,"from":now-bars*60,"to":now,"resolution":"1"},
                   headers={"User-Agent":"Mozilla/5.0"},timeout=10)
    r.raise_for_status()
    d=r.json()
    if not d.get("t"): return pd.DataFrame()
    df=pd.DataFrame({"ts":pd.to_datetime(d["t"],unit="s",utc=True),"open":d["o"],"high":d["h"],
                     "low":d["l"],"close":d["c"],"volume":d["v"]})
    for c in ["open","high","low","close","volume"]: df[c]=pd.to_numeric(df[c],errors="coerce")
    if len(df) and df["close"].iloc[-1] < 1000:
        df[["open","high","low","close"]]=df[["open","high","low","close"]]*1000
    return df.dropna().sort_values("ts").drop_duplicates("ts").reset_index(drop=True)

def rsi(s,p=7):
    d=s.diff(); g=d.clip(lower=0).rolling(p).mean(); l=(-d.clip(upper=0)).rolling(p).mean()
    return float((100-100/(1+g/(l+1e-9))).iloc[-1])

def atr(df,p=14):
    prev=df.close.shift(1)
    tr=pd.concat([df.high-df.low,(df.high-prev).abs(),(df.low-prev).abs()],axis=1).max(axis=1)
    return float(tr.rolling(p).mean().iloc[-1])

def score_symbol(symbol,df):
    if len(df)<60: return None
    close=float(df.close.iloc[-1]); a=atr(df)
    if not a or a<=0: return None
    hh=float(df.high.iloc[-21:-1].max()); ll=float(df.low.iloc[-21:-1].min())
    ema=float(df.close.ewm(span=20,adjust=False).mean().iloc[-1]); sma=float(df.close.rolling(50).mean().iloc[-1])
    av=float(df.volume.iloc[-21:-1].mean()); vr=float(df.volume.iloc[-1]/av) if av>0 else 0
    rv=rsi(df.close)
    bg=max(0,(hh-close)/a); sg=max(0,(close-ll)/a); eg=abs(close-ema)/a
    candidates=[]
    s3=max(0,100-min(bg/1.5,1)*65)+(min(max(vr-1,0)*20,20))
    if close>=hh: s3=max(s3,80)
    candidates.append(("S3/S5",min(s3,100),f"breakout gap {bg:.2f} ATR; volume {vr:.2f}x"))
    s1=max(0,100-min(sg/2,1)*65)+(25 if 35<=rv<=55 else 10 if 30<=rv<=60 else 0)
    candidates.append(("S1",min(s1,100),f"support gap {sg:.2f} ATR; RSI {rv:.1f}"))
    s2=max(0,100-min(eg/2,1)*70)+(25 if rv<=40 else 0)
    candidates.append(("S2",min(s2,100),f"EMA20 gap {eg:.2f} ATR; RSI {rv:.1f}"))
    trend=close>=ema>=sma
    s4=max(0,100-min(eg/1.5,1)*70)+(20 if trend else 0)
    candidates.append(("S4",min(s4,100),f"EMA20 gap {eg:.2f} ATR; trend={'PASS' if trend else 'FAIL'}"))
    best=max(candidates,key=lambda x:x[1])
    if best[1]<THRESHOLD: return None
    return {"symbol":symbol,"candidate_score":round(best[1],1),"candidate_strategy":best[0],
            "reason":best[2],"price":round(close,2),"rsi7":round(rv,1),"volume_ratio":round(vr,2),
            "breakout_gap_atr":round(bg,2),"support_gap_atr":round(sg,2),"ema20_gap_atr":round(eg,2),
            "timestamp":df.ts.iloc[-1].isoformat()}

def load_state():
    try:
        with open(STATE,encoding="utf-8") as f: return json.load(f)
    except Exception: return {}

def save_state(s):
    os.makedirs(os.path.dirname(STATE) or ".",exist_ok=True)
    with open(STATE,"w",encoding="utf-8") as f: json.dump(s,f,ensure_ascii=False,indent=2)

def scan_once():
    out=[]
    for symbol in DS1:
        try:
            x=score_symbol(symbol,fetch_1m(symbol))
            if x: out.append(x)
        except Exception as e: print(f"[WARN] {symbol}: {type(e).__name__}: {e}")
    return sorted(out,key=lambda x:x["candidate_score"],reverse=True)

def main():
    candidates=scan_once()
    state=load_state(); now=time.time(); eligible=[]
    for x in candidates:
        if now-float(state.get(x["symbol"],0))>=COOLDOWN: eligible.append(x)
        print(f"[CANDIDATE] {x['symbol']} {x['candidate_strategy']} {x['candidate_score']:.0f}/100 | {x['reason']} | price={x['price']}")
    if not eligible:
        print("[SCAN] No candidate handed to exact engine.")
        return 1
    for x in eligible: state[x["symbol"]]=now
    save_state(state)
    print("[SCAN] REALTIME_CANDIDATE=YES")
    print(json.dumps(eligible,ensure_ascii=False))
    return 0

if __name__=="__main__": raise SystemExit(main())
