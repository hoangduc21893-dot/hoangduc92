#!/usr/bin/env python3
"""KBS OI Live Collector v1 for VN30F1M.

Collects timestamped KBS OI/price snapshots and computes OI delta
classifications between consecutive samples. Data collection only:
no trading signals and no orders.
"""
from __future__ import annotations
import json, os, time
from datetime import datetime, timezone
from pathlib import Path

from scripts.kbs_oi_adapter_v1 import fetch_snapshot
from scripts.kbs_oi_delta_engine_v1 import compute_delta

OUT=Path("data/kbs_oi_live_v1.jsonl")
SUMMARY=Path("data/kbs_oi_live_v1_summary.json")
INTERVAL_SEC=float(os.getenv("KBS_OI_INTERVAL_SEC","10"))
DURATION_SEC=float(os.getenv("KBS_OI_DURATION_SEC","600"))

def append(row: dict) -> None:
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open("a",encoding="utf-8") as f:
        f.write(json.dumps(row,ensure_ascii=False)+"\n")

def run(duration_sec=DURATION_SEC, interval_sec=INTERVAL_SEC, fetcher=fetch_snapshot):
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.unlink(missing_ok=True)
    start=datetime.now(timezone.utc)
    previous=None
    count=0
    errors=0
    classifications={}
    end_time=time.monotonic()+duration_sec
    while time.monotonic() < end_time:
        captured=datetime.now(timezone.utc).isoformat()
        try:
            current=fetcher()
            delta=None
            if previous is not None:
                delta=compute_delta(previous,current)
                classifications[delta["classification"]]=classifications.get(delta["classification"],0)+1
            row={
                "collector_version":"v1",
                "captured_at":captured,
                "snapshot":current,
                "delta":delta,
            }
            append(row)
            previous=current
            count+=1
        except Exception as exc:
            errors+=1
            append({
                "collector_version":"v1",
                "captured_at":captured,
                "error":f"{type(exc).__name__}: {exc}",
            })
        remaining=end_time-time.monotonic()
        if remaining<=0: break
        time.sleep(min(interval_sec,remaining))
    finish=datetime.now(timezone.utc)
    summary={
        "collector_version":"v1",
        "started_at":start.isoformat(),
        "finished_at":finish.isoformat(),
        "duration_sec":(finish-start).total_seconds(),
        "interval_sec":interval_sec,
        "requested_duration_sec":duration_sec,
        "samples":count,
        "errors":errors,
        "delta_classifications":classifications,
        "data_file":str(OUT),
        "status":"OK" if count>0 and errors==0 else "PARTIAL" if count>0 else "FAILED",
        "paper_only":True,
    }
    SUMMARY.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    return summary

if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
