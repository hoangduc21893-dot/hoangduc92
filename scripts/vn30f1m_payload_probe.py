#!/usr/bin/env python3
"""
VN30F1M Payload Probe
- DATA COLLECTION ONLY: no signals, no orders, no Telegram.
- Captures raw DNSE/Entrade chart payloads plus normalized OHLCV fields.
- Best effort discovery for OI/basis keys; never invents missing values.
"""
import json, os, time
from datetime import datetime, timezone
from pathlib import Path
import requests

BASES = [
    "https://services.entrade.com.vn/chart-api/v2/ohlcs/derivative",
    "https://api.dnse.com.vn/chart-api/v2/ohlcs/derivative",
]
SYMBOLS = {"VN30F1M": "VN30F1M", "VN30": "VN30"}
RESOLUTION = "1"
INTERVAL_SEC = int(os.getenv("PROBE_INTERVAL_SEC", "10"))
DURATION_SEC = int(os.getenv("PROBE_DURATION_SEC", "1200"))
OUT = Path(os.getenv("PROBE_OUT", "data/vn30f1m_payload_probe.jsonl"))
OUT.parent.mkdir(parents=True, exist_ok=True)

def epoch_now():
    return int(time.time())

def request_symbol(symbol, start, end):
    params = {"from": start, "to": end, "symbol": symbol, "resolution": RESOLUTION}
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://banggia.dnse.com.vn",
        "Referer": "https://banggia.dnse.com.vn/",
        "User-Agent": "Mozilla/5.0",
    }
    last_error = None
    for base in BASES:
        try:
            r = requests.get(base, params=params, headers=headers, timeout=15)
            r.raise_for_status()
            return r.json(), r.url
        except Exception as e:
            last_error = e
    raise last_error

def key_candidates(obj, needles=("oi", "openinterest", "open_interest", "basis", "volume", "timestamp", "time")):
    hits = {}
    def walk(x, path=""):
        if isinstance(x, dict):
            for k,v in x.items():
                p = f"{path}.{k}" if path else k
                kl = str(k).lower().replace("-", "").replace(" ", "")
                if any(n in kl for n in needles):
                    hits[p] = v
                walk(v,p)
        elif isinstance(x, list):
            for i,v in enumerate(x[:20]):
                walk(v, f"{path}[{i}]")
    walk(obj)
    return hits

def normalize_ohlc(payload):
    # Supports common array/object OHLC responses without assuming a schema.
    if isinstance(payload, dict):
        for k in ("data","result","candles","items"):
            if k in payload:
                return normalize_ohlc(payload[k])
        if all(k in payload for k in ("t","o","h","l","c")):
            return payload
        if all(k in payload for k in ("time","open","high","low","close")):
            return payload
    if isinstance(payload, list) and payload:
        last = payload[-1]
        if isinstance(last, dict):
            return last
        if isinstance(last, (list,tuple)) and len(last) >= 5:
            return {"raw_candle": last}
    return None

def main():
    started = time.time()
    end = epoch_now()
    total = 0
    print(f"[probe] start={datetime.now().astimezone().isoformat()} duration={DURATION_SEC}s interval={INTERVAL_SEC}s")
    while time.time() - started < DURATION_SEC:
        now = epoch_now()
        row = {"captured_at": datetime.now(timezone.utc).isoformat(), "request_to": now, "symbols": {}}
        for name, symbol in SYMBOLS.items():
            try:
                payload, url = request_symbol(symbol, now-180, now+5)
                row["symbols"][name] = {
                    "url": url,
                    "normalized": normalize_ohlc(payload),
                    "candidate_fields": key_candidates(payload),
                    "raw": payload,
                }
            except Exception as e:
                row["symbols"][name] = {"error": f"{type(e).__name__}: {e}"}
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        total += 1
        print(f"[probe] sample={total} utc={row['captured_at']}")
        time.sleep(INTERVAL_SEC)
    print(f"[probe] finished samples={total} file={OUT}")

if __name__ == "__main__":
    main()
