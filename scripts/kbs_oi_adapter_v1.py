#!/usr/bin/env python3
"""KBS Open Interest Adapter v1 for VN30F1M.
Normalizes KBS derivative/iss into a small, validated snapshot.
No signals, no orders.
"""
from __future__ import annotations
import json, re
from datetime import date, datetime, timezone
from pathlib import Path
import requests

KBS_BASE="https://kbbuddywts.kbsec.com.vn/iis-server/investment"
DERIVATIVE_ISS=f"{KBS_BASE}/derivative/iss"
DERIVATIVE_GROUP=f"{KBS_BASE}/index/DER/stocks"
OUT=Path("data/kbs_oi_snapshot.json")
HEADERS={
    "Accept":"application/json, text/plain, */*",
    "Accept-Language":"en-US,en;q=0.9,vi;q=0.8",
    "Content-Type":"application/json",
    "Origin":"https://www.kbsec.com.vn",
    "Referer":"https://www.kbsec.com.vn/",
    "User-Agent":"Mozilla/5.0",
    "x-lang":"vi",
}

def f1m_alias(today: date | None = None) -> str:
    today=today or date.today()
    def expiry(y,m):
        first=date(y,m,1)
        offset=(3-first.weekday())%7
        return first.fromordinal(first.toordinal()+offset+14)
    y,m=today.year,today.month
    if today>expiry(y,m):
        m += 1
        if m==13: y,m=y+1,1
    return f"VN30F{y%100:02d}{m:02d}"

def krx_code_from_alias(alias: str) -> str | None:
    m=re.fullmatch(r"VN30F(\d{2})(\d{2})",alias)
    if not m: return None
    year=2000+int(m.group(1)); month=int(m.group(2))
    idx=(year-2010)%30
    alphabet="ABCDEFGHJKLMNPQRSTVW"
    ycode=str(idx) if idx<=9 else alphabet[idx-10]
    mcode=str(month) if month<=9 else {10:"A",11:"B",12:"C"}[month]
    return f"41I1{ycode}{mcode}000"

def _request(method,url,**kwargs):
    r=requests.request(method,url,headers=HEADERS,timeout=20,**kwargs)
    try: payload=r.json()
    except Exception as e: raise RuntimeError(f"KBS non-JSON response HTTP {r.status_code}: {e}") from e
    return r.status_code,payload

def resolve_contract() -> dict:
    alias=f1m_alias()
    candidate=krx_code_from_alias(alias)
    status,payload=_request("GET",DERIVATIVE_GROUP)
    items=payload.get("data",[]) if isinstance(payload,dict) else payload if isinstance(payload,list) else []
    candidates=[x for x in items if isinstance(x,str) and ("I1" in x or x.startswith("VN30F"))]
    return {"symbol_alias":alias,"krx_candidate":candidate,"group_status":status,"group_candidates":candidates[:100]}

def _rows(payload):
    rows=payload.get("data",[]) if isinstance(payload,dict) else payload if isinstance(payload,list) else []
    return [x for x in rows if isinstance(x,dict)]

def _to_float(row,*keys):
    for k in keys:
        if k in row and row[k] not in (None,""):
            try: return float(row[k])
            except (TypeError,ValueError): pass
    return None

def _parse_ts(value):
    if value in (None,""): return None
    if isinstance(value,(int,float)):
        v=float(value)
        if v>1e12: v/=1000
        return datetime.fromtimestamp(v,timezone.utc).isoformat()
    s=str(value).strip()
    for fmt in ("%d/%m/%Y %H:%M:%S","%d/%m/%Y","%Y-%m-%d %H:%M:%S"):
        try: return datetime.strptime(s,fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError: pass
    return s

def _select_row(rows, contract_code):
    for row in rows:
        if str(row.get("SB","")).strip()==contract_code: return row
    for row in rows:
        name=str(row.get("FN","")).upper()
        if "VN30 INDEX FUTURES" in name: return row
    return rows[0] if rows else None

def fetch_snapshot() -> dict:
    resolution=resolve_contract()
    codes=[]
    for c in resolution["group_candidates"]:
        if c not in codes: codes.append(c)
    for c in (resolution["krx_candidate"],):
        if c and c not in codes: codes.append(c)

    attempts=[]
    for code in codes[:8]:
        try:
            status,payload=_request("POST",DERIVATIVE_ISS,json={"code":code})
            rows=_rows(payload)
            attempts.append({"code":code,"status_code":status,"rows":len(rows)})
            row=_select_row(rows,code)
            if status not in (200,201) or not row:
                continue
            oi=_to_float(row,"OI","openInterest","open_interest")
            price=_to_float(row,"CP","price","close")
            volume=_to_float(row,"TT","volume")
            if oi is None:
                continue
            snapshot={
                "adapter_version":"v1",
                "captured_at":datetime.now(timezone.utc).isoformat(),
                "source":"KBS",
                "endpoint":DERIVATIVE_ISS,
                "symbol_alias":resolution["symbol_alias"],
                "contract_code":str(row.get("SB") or code),
                "contract_name":row.get("FN"),
                "underlying":row.get("ULS","VN30"),
                "open_interest":oi,
                "price":price,
                "open":_to_float(row,"OP","open"),
                "high":_to_float(row,"HI","high"),
                "low":_to_float(row,"LO","low"),
                "volume":volume,
                "timestamp":_parse_ts(row.get("TST") or row.get("TS") or row.get("TTM") or row.get("TIME")),
                "expiry":row.get("LTD"),
                "market_status":row.get("TSI"),
                "raw_keys":sorted(row.keys()),
                "validation":{"http_status":status,"oi_numeric":True,"contract_match":str(row.get("SB") or code)==code},
                "attempts":attempts,
            }
            OUT.parent.mkdir(parents=True,exist_ok=True)
            OUT.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding="utf-8")
            return snapshot
        except Exception as e:
            attempts.append({"code":code,"error":f"{type(e).__name__}: {e}"})
    raise RuntimeError(f"KBS OI unavailable; attempts={attempts}")

if __name__=="__main__":
    print(json.dumps(fetch_snapshot(),ensure_ascii=False,indent=2))
