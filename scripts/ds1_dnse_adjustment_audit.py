"""DNSE-first historical adjustment audit: compare ex-right boundaries WITHOUT price rewrites."""
import argparse,csv,hashlib,json,math
from pathlib import Path
from datetime import date
FIELDS=["symbol","event_date","ex_date","previous_trading_date","previous_close_dnse","ex_date_reference_dnse","ex_date_open_dnse","ex_date_close_dnse","theoretical_stock_factor","previous_close_if_unadjusted","evidence_status","volume_adjustment_status","event_source"]
def audit(ledger,warehouse):
    report=[]
    for stock in ledger["symbols"]:
        symbol=stock["symbol"];path=Path(warehouse)/(symbol+".csv")
        bars={}
        if path.exists():
            with path.open(encoding="utf-8",newline="") as f:
                for row in csv.DictReader(f):bars[row["date"]]=row
        ordered=sorted(bars)
        for e in stock["events"]:
            ex=e.get("ex_date")
            previous=next((d for d in reversed(ordered) if ex and d<ex),None)
            before=bars.get(previous) if previous else None
            after=bars.get(ex) if ex else None
            ratio=e.get("stock_ratio_new_per_old")
            factor=1/(1+ratio) if isinstance(ratio,(int,float)) and ratio>=0 and not e.get("cash_dividend_vnd") else None
            # Do NOT infer adjustment basis from a single before/after close.
            report.append({"symbol":symbol,"event_date":e.get("record_date") or ex,"ex_date":ex,
              "previous_trading_date":previous,"previous_close_dnse":float(before["close"]) if before else None,
              "ex_date_reference_dnse":None,"ex_date_open_dnse":float(after["open"]) if after else None,
              "ex_date_close_dnse":float(after["close"]) if after else None,
              "theoretical_stock_factor":factor,"previous_close_if_unadjusted":None,
              "evidence_status":"BLOCKED_RAW_REFERENCE_AND_ADJUSTMENT_UNVERIFIED",
              "volume_adjustment_status":"UNVERIFIED","event_source":e.get("source_url")})
    return report
def run(ledger_path,warehouse,outdir):
    ledger_bytes=Path(ledger_path).read_bytes();ledger=json.loads(ledger_bytes)
    rows=audit(ledger,warehouse)
    out=Path(outdir);out.mkdir(parents=True,exist_ok=True)
    target=out/"dnse_rights_audit.csv"
    with target.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    manifest={"mode":"DNSE_FIRST_RESEARCH_ONLY","events":len(rows),"dnse_both_side_available":sum(r["previous_close_dnse"] is not None and r["ex_date_close_dnse"] is not None for r in rows),
      "adjustment_basis_verified":False,"volume_basis_verified":False,"full_backtest_approved":False,
      "ledger_sha256":hashlib.sha256(ledger_bytes).hexdigest(),
      "audit_sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
      "vendor_price_basis":"UNKNOWN: not safe to double-adjust",
      "required_next_evidence":"Official ex-day reference plus provider raw/adjusted definition and volume basis"}
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps(manifest));return manifest
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",default="data/ds1_v2/corporate_action_ledger.json")
    p.add_argument("--warehouse",default="data/ds1_v2/historical_warehouse")
    p.add_argument("--output-dir",default="data/ds1_v2/dnse_rights_audit")
    a=p.parse_args();run(a.ledger,a.warehouse,a.output_dir)
