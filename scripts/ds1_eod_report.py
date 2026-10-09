#!/usr/bin/env python3
"""Fail-closed DNSE daily EOD price exporter for DS1. Separate from 1m trading signals."""
import argparse
import csv
import json
from datetime import date, datetime, timedelta, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.ds1_market_wide import Client, atomic_json

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
CORE = ("PVT","PVS","MSB","HAH","BSR","VGC","DHC","VPB","MWG","HDB","PET","HPG","DCM","GMD")
PENDING = ("PLX","ANV","VHC","GVR")
OUTPUT = Path("data/ds1_eod")

def extract_daily_close(bars, target):
    """Only the uniquely dated DNSE 1D bar counts; never a 1m bar or prior-day fallback."""
    if not isinstance(target, date):
        raise ValueError("target must be date")
    matching = [b for b in bars if datetime.fromtimestamp(b["t"], TZ).date() == target]
    if len(matching) != 1:
        raise ValueError("EOD_MISSING_OR_DUPLICATE")
    b = matching[0]
    if b["c"] <= 0 or not b["l"] <= b["c"] <= b["h"]:
        raise ValueError("EOD_INVALID_PRICE")
    if b["v"] < 0:
        raise ValueError("EOD_INVALID_VOLUME")
    return {"close_vnd": b["c"], "bar_time": datetime.fromtimestamp(b["t"], TZ).isoformat(),
            "volume": b["v"], "source": "DNSE chart-api/v2/ohlcs/stock",
            "resolution": "1D", "unit": "VND", "date": target.isoformat()}

def export_for_day(target, client, output=OUTPUT):
    now = datetime.now(TZ)
    # No same-day EOD before a conservative post-close buffer at 15:15 ICT.
    if target > now.date() or (target == now.date() and now.time() < dtime(15,15)):
        raise ValueError("EOD_NOT_READY")
    if target.weekday() >= 5:
        raise ValueError("NON_TRADING_WEEKDAY")
    symbols = CORE + PENDING
    data = {"schema_version": 1, "asof":target.isoformat(), "generated_at":now.isoformat(),
            "status":"PARTIAL", "quotes":{}, "unverified":[], "source":"DNSE", "price_unit":"VND",
            "note":"Price is 1D OHLCV bar close, not auction tick; verify exchange final settlement when necessary."}
    with_errors=0
    # Query historical time range ending AFTER target date but before future bars; do not
    # borrow an adjacent day's close under any circumstance.
    asof = datetime.combine(target + timedelta(days=1), dtime(2,0), TZ)
    for sym in symbols:
        try:
            bars=client.ohlcv(sym,"1D",asof)
            data["quotes"][sym]=extract_daily_close(bars,target)
        except Exception:
            with_errors+=1
            data["unverified"].append(sym)
    data["status"]="COMPLETE" if not with_errors else "PARTIAL"
    output.mkdir(parents=True,exist_ok=True)
    atomic_json(output / ("ds1_eod_"+str(target)+".json"),data)
    with (output / ("ds1_eod_"+str(target)+".csv")).open("w",newline="",encoding="utf-8-sig") as stream:
        writer=csv.writer(stream)
        writer.writerow(["symbol","date","close_vnd","dnse_bar_time","volume","status","source"])
        for sym in symbols:
            q=data["quotes"].get(sym)
            writer.writerow([sym,target,q["close_vnd"] if q else "",
                             q["bar_time"] if q else "",q["volume"] if q else "",
                             "VERIFIED_1D" if q else "MISSING","DNSE 1D"])
    print(json.dumps({"date":str(target),"status":data["status"],"confirmed":len(data["quotes"]),
                      "missing":data["unverified"]},ensure_ascii=False))
    return 0 if data["status"]=="COMPLETE" else 2

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",help="YYYY-MM-DD, defaults to current Vietnam date")
    a=p.parse_args()
    target=date.fromisoformat(a.date) if a.date else datetime.now(TZ).date()
    return export_for_day(target, Client(interval=1.0))

if __name__ == "__main__":
    raise SystemExit(main())
