"""Reproducible event-level rights reconciliation. Research only, no price changes."""
import argparse,csv,hashlib,json,math
from pathlib import Path

FIELDS=["event_id","symbol","event_type","record_date","ex_date","official_reference_vnd","official_reference_source","raw_ohlcv_source","raw_open","raw_high","raw_low","raw_close","raw_volume","adjusted_ohlcv_source","adjusted_open","adjusted_high","adjusted_low","adjusted_close","adjusted_volume","theoretical_price_factor","observed_price_factor","observed_volume_factor","adjustment_basis","event_source","status","missing_evidence"]

def finite_positive(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>0

def build(ledger, evidence=None):
    evidence=evidence or {}
    rows=[]
    for entry in ledger["symbols"]:
        for index,event in enumerate(entry["events"]):
            key=f'{entry["symbol"]}:{event.get("ex_date") or event.get("record_date") or "UNKNOWN"}:{index}'
            proof=evidence.get(key,{})
            raw=proof.get("raw_ohlcv") or {}
            adj=proof.get("adjusted_ohlcv") or {}
            ratio=event.get("stock_ratio_new_per_old")
            theoretical=1/(1+ratio) if isinstance(ratio,(float,int)) and ratio>=0 and not event.get("cash_dividend_vnd") else None
            price_factor=(adj["close"]/raw["close"]) if finite_positive(raw.get("close")) and finite_positive(adj.get("close")) else None
            volume_factor=(adj["volume"]/raw["volume"]) if finite_positive(raw.get("volume")) and finite_positive(adj.get("volume")) else None
            needed=[]
            if not event.get("ex_date"):needed.append("ex_date")
            if not event.get("source_url"):needed.append("event_source")
            if not finite_positive(proof.get("official_reference_vnd")):needed.append("official_reference_vnd")
            if not proof.get("official_reference_source"):needed.append("official_reference_source")
            for kind,bar in (("raw",raw),("adjusted",adj)):
                if not proof.get(kind+"_ohlcv_source"):needed.append(kind+"_ohlcv_source")
                if not all(finite_positive(bar.get(k)) for k in ("open","high","low","close","volume")):
                    needed.append(kind+"_ohlcv")
            if not proof.get("vendor_adjustment_documentation"):needed.append("vendor_adjustment_documentation")
            if not proof.get("reviewed_against_official_source"):needed.append("independent_review")
            row={"event_id":key,"symbol":entry["symbol"],"event_type":event.get("event_type"),"record_date":event.get("record_date"),"ex_date":event.get("ex_date"),
                 "official_reference_vnd":proof.get("official_reference_vnd"),"official_reference_source":proof.get("official_reference_source"),
                 "raw_ohlcv_source":proof.get("raw_ohlcv_source"),"adjusted_ohlcv_source":proof.get("adjusted_ohlcv_source"),
                 "theoretical_price_factor":theoretical,"observed_price_factor":price_factor,"observed_volume_factor":volume_factor,
                 "adjustment_basis":proof.get("vendor_adjustment_documentation"),"event_source":event.get("source_url"),
                 "status":"VERIFIED" if not needed else "BLOCKED_UNVERIFIED","missing_evidence":";".join(needed)}
            for kind,bar in (("raw",raw),("adjusted",adj)):
                for field in ("open","high","low","close","volume"):row[kind+"_"+field]=bar.get(field)
            rows.append(row)
    return rows

def export(ledger_path,proof_path,output_dir):
    ledger_bytes=Path(ledger_path).read_bytes()
    proof_bytes=Path(proof_path).read_bytes() if Path(proof_path).exists() else b"{}"
    evidence=json.loads(proof_bytes)
    rows=build(json.loads(ledger_bytes),evidence)
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    with (out/"rights_reconciliation.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    report={"mode":"RESEARCH_ONLY","status":"BLOCKED" if any(r["status"]!="VERIFIED" for r in rows) else "EVENT_ROWS_VERIFIED_HISTORY_COMPLETENESS_STILL_REQUIRED",
            "events":len(rows),"verified":sum(r["status"]=="VERIFIED" for r in rows),
            "ledger_sha256":hashlib.sha256(ledger_bytes).hexdigest(),"evidence_sha256":hashlib.sha256(proof_bytes).hexdigest(),
            "comparison_csv_sha256":hashlib.sha256((out/"rights_reconciliation.csv").read_bytes()).hexdigest(),
            "full_backtest_approved":False,"no_price_adjustments_applied":True}
    (out/"reconciliation_manifest.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report))
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",default="data/ds1_v2/corporate_action_ledger.json")
    p.add_argument("--evidence",default="data/ds1_v2/rights_price_evidence.json")
    p.add_argument("--output-dir",default="data/ds1_v2/rights_reconciliation")
    a=p.parse_args();export(a.ledger,a.evidence,a.output_dir)
if __name__=="__main__":main()
