#!/usr/bin/env python3
"""VN30F data and Telegram diagnostic. Fail closed; never places trades."""
import json
import os
import sys
import time
from datetime import datetime, time as dtime
from urllib import request, parse, error
from zoneinfo import ZoneInfo

TZ=ZoneInfo("Asia/Ho_Chi_Minh")
URLS={
    "VN30F1M":"https://services.entrade.com.vn/chart-api/v2/ohlcs/derivative",
    "VN30":"https://services.entrade.com.vn/chart-api/v2/ohlcs/index",
}

def in_session(now):
    t=now.time()
    return now.weekday()<5 and (dtime(8,45)<=t<=dtime(11,30) or dtime(13,0)<=t<=dtime(14,45))

def inspect(payload, now_epoch, resolution_seconds, max_lag_seconds=180):
    if not isinstance(payload,dict):return {"status":"ERROR","reason":"INVALID_PAYLOAD"}
    ts=payload.get("t",payload.get("time",[]))
    closes=payload.get("c",payload.get("close",[]))
    if not isinstance(ts,list) or not isinstance(closes,list) or not ts or len(ts)!=len(closes):
        return {"status":"ERROR","reason":"INVALID_SERIES"}
    try:
        stamps=[int(float(v)) for v in ts]
        values=[float(v) for v in closes]
    except (TypeError,ValueError,OverflowError):
        return {"status":"ERROR","reason":"NON_NUMERIC_DATA"}
    if any(v<=0 for v in values) or any(b<=a for a,b in zip(stamps,stamps[1:])):
        return {"status":"ERROR","reason":"BAD_PRICE_OR_TIME_ORDER"}
    latest=stamps[-1]
    lag=now_epoch-latest
    # Without knowing whether timestamps denote candle START or END,
    # both possibilities must be tested and ambiguity must remain explicit.
    possible_end_lags={"END":lag,"START":lag-resolution_seconds}
    plausible=[k for k,v in possible_end_lags.items() if -10<=v<=max_lag_seconds]
    if lag < -10:return {"status":"ERROR","reason":"FUTURE_TIMESTAMP","lag_seconds":lag}
    if not plausible:return {"status":"STALE","reason":"NO_RECENT_CLOSED_CANDLE","lag_seconds":lag}
    return {"status":"UNVERIFIED","reason":"CANDLE_TIMESTAMP_SEMANTICS_UNVERIFIED",
            "lag_seconds":lag,"last_timestamp":latest,"last_close":values[-1],
            "plausible_conventions":plausible,"bars":len(stamps)}

def get_chart(symbol,resolution,window):
    end=int(time.time())
    params=parse.urlencode({"from":end-window,"to":end,"symbol":symbol,"resolution":resolution})
    req=request.Request(URLS[symbol]+"?"+params,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
    with request.urlopen(req,timeout=20) as resp:return json.load(resp)

def telegram(message):
    token=os.environ.get("TELEGRAM_BOT_TOKEN")
    chat=os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:raise RuntimeError("TELEGRAM_SECRETS_MISSING")
    payload=json.dumps({"chat_id":chat,"text":message}).encode()
    req=request.Request("https://api.telegram.org/bot"+token+"/sendMessage",
                        data=payload,headers={"Content-Type":"application/json"},method="POST")
    with request.urlopen(req,timeout=20) as resp:
        data=json.load(resp)
    if data.get("ok") is not True:raise RuntimeError("TELEGRAM_NOT_ACKNOWLEDGED")

def run():
    now=datetime.now(TZ)
    if not in_session(now):
        print("SKIP: outside VN30F session; no live freshness claim")
        return 0
    findings={}
    for symbol,resolution,window,seconds in (("VN30F1M","1",86400,60),("VN30","5",432000,300)):
        try:
            findings[symbol]=inspect(get_chart(symbol,resolution,window),int(time.time()),seconds)
        except Exception as exc:
            findings[symbol]={"status":"ERROR","reason":type(exc).__name__}
    status="DATA_ERROR" if any(x["status"] in ("ERROR","STALE") for x in findings.values()) else "DATA_UNVERIFIED"
    msg="VN30F DATA DIAGNOSTIC | "+now.strftime("%Y-%m-%d %H:%M")+" VN\nStatus: "+status
    for symbol,item in findings.items():
        msg+="\n"+symbol+": "+item["status"]+" / "+item["reason"]+" / lag="+str(item.get("lag_seconds","N/A"))+"s"
    msg+="\nSignals: DISABLED IN DIAGNOSTIC. No order placement."
    print(msg)
    os.makedirs("data",exist_ok=True)
    with open("data/vn30f_data_diagnostic.json","w",encoding="utf-8") as f:
        json.dump({"time":now.isoformat(),"status":status,"findings":findings},f,indent=2)
    try:
        telegram(msg)
    except Exception as exc:
        print("TELEGRAM_ERROR: "+type(exc).__name__,file=sys.stderr)
        return 2
    print("TELEGRAM_ACK: OK")
    return 1 if status=="DATA_ERROR" else 0

if __name__=="__main__":raise SystemExit(run())
