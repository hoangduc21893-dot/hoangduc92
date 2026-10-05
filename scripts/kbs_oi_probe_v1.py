#!/usr/bin/env python3
"""KBS OI Probe v1 - data collection only, no signals/orders."""
from __future__ import annotations
import json
import re
import time
from datetime import datetime, date
from pathlib import Path
import requests

BASE="https://kbbuddywts.kbsec.com.vn/iis-server/investment"
DERIVATIVE_ISS=f"{BASE}/derivative/iss"
DERIVATIVE_GROUP=f"{BASE}/index/DER/stocks"
OUT=Path("data/kbs_oi_probe_v1.jsonl")
OUT.parent.mkdir(parents=True,exist_ok=True)
HEADERS={
    "Accept":"application/json, text/plain, */*",
    "Accept-Language":"en-US,en;q=0.9,vi;q=0.8",
    "Content-Type":"application/json",
    "Origin":"https://www.kbsec.com.vn",
    "Referer":"https://www.kbsec.com.vn/",
    "User-Agent":"Mozilla/5.0",
    "x-lang":"vi",
}

def third_thursday(y,m):
    d=date(y,m,1)
    return d.replace(day=1)

def expand_f1m(today=None):
    today=today or date.today()
    # F1M is the nearest monthly contract. If today's expiry has passed,
    # roll to next month.
    import calendar
    def expiry(y,m):
        first=date(y,m,1)
        offset=(3-first.weekday())%7
        return first.fromordinal(first.toordinal()+offset+14)
    y,m=today.year,today.month
    if today>expiry(y,m):
        m+=1
        if m==13: y,m=y+1,1
    return f"VN30F{y%100:02d}{m:02d}"

def krx_code_from_legacy(full):
    m=re.fullmatch(r"VN30F(\d{2})(\d{2})",full)
    if not m: return None
    yy,mm=int(m.group(1)),int(m.group(2))
    year=2000+yy
    idx=(year-2010)%30
    alphabet="ABCDEFGHJKLMNPQRSTVW"
    year_code=str(idx) if idx<=9 else alphabet[idx-10]
    month_code=str(mm) if mm<=9 else {10:"A",11:"B",12:"C"}[mm]
    return f"41I1{year_code}{month_code}000"

def get_json(method,url,**kwargs):
    r=requests.request(method,url,headers=HEADERS,timeout=20,**kwargs)
    info={"status_code":r.status_code,"url":r.url}
    try: payload=r.json()
    except Exception:
        payload=None
    info["payload"]=payload
    return info

def resolve_contract():
    legacy=expand_f1m()
    krx=krx_code_from_legacy(legacy)
    result={"legacy_f1m":legacy,"krx_candidate":krx,"group_candidates":[]}
    try:
        g=get_json("GET",DERIVATIVE_GROUP)
        result["group_status"]=g["status_code"]
        p=g["payload"]
        result["group_payload_preview"]=p if isinstance(p,(dict,list)) else str(p)[:2000]
        items=p.get("data",[]) if isinstance(p,dict) else p if isinstance(p,list) else []
        result["group_candidates"]=[x for x in items if isinstance(x,str) and ("I1" in x or x.startswith("VN30F"))][:100]
    except Exception as e:
        result["group_error"]=f"{type(e).__name__}: {e}"
    return result

def probe_code(code):
    try:
        r=get_json("POST",DERIVATIVE_ISS,json={"code":code})
        p=r["payload"]
        rows=p.get("data",[]) if isinstance(p,dict) else p if isinstance(p,list) else []
        oi_keys=set()
        flat=[]
        for row in rows if isinstance(rows,list) else []:
            if isinstance(row,dict):
                oi_keys.update(k for k in row if "oi" in str(k).lower() or "openinterest" in str(k).lower() or "open_interest" in str(k).lower())
                flat.append({k:row[k] for k in row if k in {"SB","symbol","OI","CP","OP","HI","LO","TT","EX","t"}})
        return {
            "code":code,"status_code":r["status_code"],"url":r["url"],
            "row_count":len(rows) if isinstance(rows,list) else 0,
            "oi_keys":sorted(oi_keys),
            "oi_values":[row.get("OI") for row in rows if isinstance(row,dict) and "OI" in row][:10],
            "rows_preview":flat[:5],
            "raw_payload":p,
        }
    except Exception as e:
        return {"code":code,"error":f"{type(e).__name__}: {e}"}

def main():
    if OUT.exists(): OUT.unlink()
    started=datetime.now().astimezone().isoformat()
    resolution=resolve_contract()
    codes=[]
    for c in resolution.get("group_candidates",[]):
        if c not in codes: codes.append(c)
    for c in [resolution.get("krx_candidate"),resolution.get("legacy_f1m")]:
        if c and c not in codes: codes.append(c)
    samples=[probe_code(c) for c in codes[:8]]
    best=next((s for s in samples if s.get("status_code") in (200,201) and s.get("oi_keys")),None)
    row={
        "probe_version":"v1",
        "captured_at":started,
        "resolver":resolution,
        "samples":samples,
        "oi_verified":bool(best),
        "verified_code":best.get("code") if best else None,
        "verified_oi_keys":best.get("oi_keys") if best else [],
    }
    OUT.write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
        "probe_version":"v1","oi_verified":row["oi_verified"],
        "verified_code":row["verified_code"],
        "verified_oi_keys":row["verified_oi_keys"],
        "tested_codes":[s.get("code") for s in samples],
        "statuses":[{"code":s.get("code"),"status":s.get("status_code"),"oi_keys":s.get("oi_keys",[]),"rows":s.get("row_count",0)} for s in samples]
    },ensure_ascii=False))
if __name__=="__main__":
    main()
