"""Independent historical OHLCV collector with explicit raw/adjusted provenance.

Accept exports from independent providers (e.g., SSI and VCI/KBS), but never
assert a price-basis label without provider documentation or reviewer evidence.
No network credentials, trading, or automatic adjustment.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from pathlib import Path
from datetime import date
from scripts.ds1_prebreakout_v2 import ACTIVE,WATCH_RISK

REQUIRED=("date","open","high","low","close","volume")
BASIS=("RAW","ADJUSTED","UNKNOWN")
def load_csv(path, symbol, provider, declared_basis, documentation_url=None):
    if declared_basis not in BASIS:raise ValueError("invalid basis")
    if declared_basis!="UNKNOWN" and not documentation_url:
        raise ValueError("source documentation required for asserted price basis")
    raw=Path(path).read_bytes()
    rows=[];dates=set()
    with Path(path).open(newline="",encoding="utf-8-sig") as f:
        reader=csv.DictReader(f)
        if not set(REQUIRED).issubset(reader.fieldnames or []):raise ValueError("missing OHLCV columns")
        for line in reader:
            d=date.fromisoformat(line["date"]).isoformat()
            if d in dates:raise ValueError("duplicate trading date")
            dates.add(d)
            vals={k:float(line[k]) for k in REQUIRED if k!="date"}
            if not all(math.isfinite(v) for v in vals.values()):raise ValueError("non-finite OHLCV")
            if any(vals[k]<=0 for k in ("open","high","low","close")) or vals["volume"]<0:raise ValueError("invalid OHLCV")
            if vals["high"]<max(vals["open"],vals["close"]) or vals["low"]>min(vals["open"],vals["close"]):raise ValueError("invalid OHLC range")
            rows.append({"date":d,**vals})
    rows.sort(key=lambda r:r["date"])
    return {"symbol":symbol,"provider":provider,"declared_basis":declared_basis,
            "basis_documentation_url":documentation_url,"source_path":str(path),
            "source_sha256":hashlib.sha256(raw).hexdigest(),"count":len(rows),
            "first":rows[0]["date"] if rows else None,"last":rows[-1]["date"] if rows else None,
            "rows":rows}

def compare(raw,adjusted):
    if raw["symbol"]!=adjusted["symbol"]:raise ValueError("symbol mismatch")
    if raw["provider"]==adjusted["provider"]:raise ValueError("not independent providers")
    r={x["date"]:x for x in raw["rows"]}
    a={x["date"]:x for x in adjusted["rows"]}
    out=[]
    for d in sorted(r.keys()&a.keys()):
        x,y=r[d],a[d]
        out.append({"symbol":raw["symbol"],"date":d,"raw_provider":raw["provider"],
            "adjusted_provider":adjusted["provider"],
            "raw_close":x["close"],"adjusted_close":y["close"],
            "price_factor":y["close"]/x["close"],
            "volume_factor":y["volume"]/x["volume"] if x["volume"] else None,
            "raw_source_sha256":raw["source_sha256"],"adjusted_source_sha256":adjusted["source_sha256"],
            "status":"CROSS_SOURCE_ONLY_NOT_OFFICIALLY_VERIFIED"})
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--raw-csv",required=True)
    p.add_argument("--adjusted-csv",required=True)
    p.add_argument("--symbol",required=True,choices=ACTIVE+WATCH_RISK)
    p.add_argument("--raw-provider",default="SSI")
    p.add_argument("--adjusted-provider",default="VCI")
    p.add_argument("--raw-basis",default="UNKNOWN",choices=BASIS)
    p.add_argument("--adjusted-basis",default="UNKNOWN",choices=BASIS)
    p.add_argument("--raw-documentation-url")
    p.add_argument("--adjusted-documentation-url")
    p.add_argument("--output-dir",default="data/ds1_v2/independent_history")
    args=p.parse_args()
    raw=load_csv(args.raw_csv,args.symbol,args.raw_provider,args.raw_basis,args.raw_documentation_url)
    adj=load_csv(args.adjusted_csv,args.symbol,args.adjusted_provider,args.adjusted_basis,args.adjusted_documentation_url)
    rows=compare(raw,adj)
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0]) if rows else ["symbol","date","raw_close","adjusted_close","price_factor","volume_factor","status"]
    with (out/(args.symbol+"_comparison.csv")).open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    manifest={"symbol":args.symbol,"raw":{k:v for k,v in raw.items() if k!="rows"},
              "adjusted":{k:v for k,v in adj.items() if k!="rows"},
              "matched_sessions":len(rows),"only_raw":len(raw["rows"])-len(rows),
              "only_adjusted":len(adj["rows"])-len(rows),
              "price_basis_verified":False,"volume_basis_verified":False,
              "full_backtest_approved":False,
              "comparison_sha256":hashlib.sha256((out/(args.symbol+"_comparison.csv")).read_bytes()).hexdigest()}
    (out/(args.symbol+"_manifest.json")).write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps({"symbol":args.symbol,"matched_sessions":len(rows),"status":"REQUIRES_INDEPENDENT_BASIS_VERIFICATION"}))
if __name__=="__main__":main()
