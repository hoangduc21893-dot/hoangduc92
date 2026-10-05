#!/usr/bin/env python3
"""KBS OI Delta Engine v1 for VN30F1M.

Classifies price/OI changes into:
- LONG_BUILDUP
- SHORT_BUILDUP
- SHORT_COVERING
- LONG_UNWINDING

Data-analysis only. No signals and no orders.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

OUT=Path("data/kbs_oi_delta_snapshot.json")

def classify(price_prev: float, price_curr: float, oi_prev: float, oi_curr: float) -> str:
    """Classify the four price/OI regimes using sign of both deltas."""
    pp=float(price_prev); pc=float(price_curr)
    op=float(oi_prev); oc=float(oi_curr)
    if op <= 0:
        raise ValueError("oi_prev must be > 0")
    if pp <= 0 or pc <= 0:
        raise ValueError("prices must be > 0")
    dp=pc-pp
    doi=oc-op
    if dp > 0 and doi > 0:
        return "LONG_BUILDUP"
    if dp < 0 and doi > 0:
        return "SHORT_BUILDUP"
    if dp > 0 and doi < 0:
        return "SHORT_COVERING"
    if dp < 0 and doi < 0:
        return "LONG_UNWINDING"
    return "NEUTRAL"

def compute_delta(previous: dict, current: dict) -> dict:
    """Build a normalized delta record from two KBS adapter snapshots."""
    if previous.get("contract_code") != current.get("contract_code"):
        raise ValueError("contract_code mismatch")
    pp=float(previous["price"]); pc=float(current["price"])
    op=float(previous["open_interest"]); oc=float(current["open_interest"])
    price_delta=pc-pp
    oi_delta=oc-op
    result={
        "engine_version":"v1",
        "captured_at":datetime.now(timezone.utc).isoformat(),
        "source":"KBS",
        "symbol_alias":current.get("symbol_alias","VN30F1M"),
        "contract_code":current["contract_code"],
        "previous_timestamp":previous.get("timestamp"),
        "current_timestamp":current.get("timestamp"),
        "previous_price":pp,
        "current_price":pc,
        "price_delta":price_delta,
        "price_delta_pct":(price_delta/pp)*100 if pp else 0.0,
        "previous_open_interest":op,
        "current_open_interest":oc,
        "oi_delta":oi_delta,
        "oi_delta_pct":(oi_delta/op)*100 if op else 0.0,
        "classification":classify(pp,pc,op,oc),
    }
    return result

def save_delta(previous: dict, current: dict) -> dict:
    result=compute_delta(previous,current)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    return result

def main() -> int:
    print("KBS OI Delta Engine v1 is a library/classifier; no live pair supplied.")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
