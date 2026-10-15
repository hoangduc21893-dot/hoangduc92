"""SSI FastConnect Data official historical connector; research only.

Reference: https://guide.ssi.com.vn/ssi-products/fastconnect-data/api-specs
Credentials: SSI_CONSUMER_ID and SSI_CONSUMER_SECRET environment variables.
DailyStockPrice has ClosePriceAdjusted, NOT verified full adjusted OHLCV.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,time
from datetime import datetime
from pathlib import Path
import requests
BASE="https://fc-data.ssi.com.vn/api/v2/Market"
FIELDS=["date","symbol","market","raw_open","raw_high","raw_low","raw_close","raw_volume",
        "reference_price","adjusted_close","price_close_factor","source_endpoint","basis_status"]
def get_token(session,consumer_id,secret):
    if not consumer_id or not secret:raise ValueError("Missing SSI API credentials")
    r=session.post(BASE+"/AccessToken",json={"consumerID":consumer_id,"consumerSecret":secret},timeout=30)
    r.raise_for_status()
    obj=r.json()
    token=(obj.get("data") or {}).get("accessToken")
    if not token:raise ValueError("SSI did not return token")
    return token
def fetch(session,token,endpoint,symbol,start,end,market=None):
    output=[];page=1
    while page<=100:
        params={"symbol":symbol,"fromDate":start,"toDate":end,"pageIndex":page,"pageSize":1000,"ascending":True}
        if market:params["market"]=market
        r=session.get(BASE+"/"+endpoint,params=params,headers={"Authorization":"Bearer "+token},timeout=30)
        r.raise_for_status();obj=r.json()
        if not isinstance(obj.get("data"),list):raise ValueError("SSI unexpected response")
        part=obj["data"];output.extend(part)
        total=int(obj.get("totalRecord") or 0)
        if not part or len(output)>=total or len(part)<1000:break
        page+=1;time.sleep(.15)
    if page>100:raise ValueError("SSI pagination cap")
    return output
def normalize(ohlc,quotes,symbol):
    def datekey(x):
        raw=x.get("TradingDate") or x.get("Tradingdate")
        return datetime.strptime(raw,"%d/%m/%Y").date().isoformat()
    def numeric(v):
        if v is None or str(v).strip()=="":return None
        return float(v)
    qmap={datekey(q):q for q in quotes}
    rows=[];seen=set()
    for p in ohlc:
        d=datekey(p)
        if d in seen:raise ValueError("SSI duplicate date "+d)
        seen.add(d);q=qmap.get(d,{})
        close=numeric(p.get("Close"));adj=numeric(q.get("ClosePriceAdjusted"))
        raw_close=numeric(q.get("ClosePrice")) or close
        rows.append({"date":d,"symbol":symbol,"market":p.get("Market"),
                     "raw_open":numeric(p.get("Open")),"raw_high":numeric(p.get("High")),
                     "raw_low":numeric(p.get("Low")),"raw_close":raw_close,
                     "raw_volume":numeric(p.get("Volume")),
                     "reference_price":numeric(q.get("RefPrice")),
                     "adjusted_close":adj,
                     "price_close_factor":adj/raw_close if adj is not None and raw_close and raw_close>0 else None,
                     "source_endpoint":"SSI:DailyOhlc+DailyStockPrice",
                     "basis_status":"ADJUSTED_CLOSE_FIELD_ONLY_FULL_OHLCV_UNVERIFIED"})
    return sorted(rows,key=lambda x:x["date"])
def run(args,session=None):
    session=session or requests.Session()
    token=get_token(session,os.getenv("SSI_CONSUMER_ID"),os.getenv("SSI_CONSUMER_SECRET"))
    from_date=datetime.strptime(args.start,"%Y-%m-%d").strftime("%d/%m/%Y")
    to_date=datetime.strptime(args.end,"%Y-%m-%d").strftime("%d/%m/%Y")
    ohlc=fetch(session,token,"DailyOhlc",args.symbol,from_date,to_date,args.market)
    prices=fetch(session,token,"DailyStockPrice",args.symbol,from_date,to_date,args.market)
    rows=normalize(ohlc,prices,args.symbol)
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    csvpath=out/(args.symbol+"_ssi_history.csv")
    with csvpath.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    report={"source":"SSI FastConnect Data","symbol":args.symbol,"start":args.start,"end":args.end,
        "count":len(rows),"missing_adjusted_close":sum(x["adjusted_close"] is None for x in rows),
        "price_basis_status":"CLOSE_ADJUSTMENT_REQUIRES_VENDOR_RECONCILIATION",
        "adjusted_ohlcv_available":False,"full_backtest_approved":False,
        "file_sha256":hashlib.sha256(csvpath.read_bytes()).hexdigest()}
    (out/(args.symbol+"_ssi_manifest.json")).write_text(json.dumps(report,indent=2))
    print(json.dumps(report));return 0 if rows else 2
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--symbol",required=True)
    p.add_argument("--start",default="2023-01-01")
    p.add_argument("--end",default="2026-10-14")
    p.add_argument("--market",default=None)
    p.add_argument("--output-dir",default="data/ds1_v2/ssi_history")
    a=p.parse_args();raise SystemExit(run(a))
if __name__=="__main__":main()
