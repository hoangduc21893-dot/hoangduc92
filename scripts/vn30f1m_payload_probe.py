#!/usr/bin/env python3
"""
VN30F1M Payload Probe v2
- DATA COLLECTION ONLY: no signals, no orders, no Telegram.
- Probes the correct DNSE/Entrade history endpoints separately:
    * VN30F1M -> derivative endpoint
    * VN30    -> stock endpoint
- Captures status, URL, raw payload and candidate OI/basis/volume/timestamp fields.
- Never invents missing values.
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ENDPOINTS = {
    "VN30F1M": [
        "https://services.entrade.com.vn/chart-api/v2/ohlcs/derivative",
        "https://api.dnse.com.vn/chart-api/v2/ohlcs/derivative",
    ],
    "VN30": [
        "https://services.entrade.com.vn/chart-api/v2/ohlcs/stock",
        "https://api.dnse.com.vn/chart-api/v2/ohlcs/stock",
    ],
}

RESOLUTION = os.getenv("PROBE_RESOLUTION", "1")
INTERVAL_SEC = int(os.getenv("PROBE_INTERVAL_SEC", "10"))
DURATION_SEC = int(os.getenv("PROBE_DURATION_SEC", "1200"))
LOOKBACK_SEC = int(os.getenv("PROBE_LOOKBACK_SEC", "300"))
OUT = Path(os.getenv("PROBE_OUT", "data/vn30f1m_payload_probe.jsonl"))
OUT.parent.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
    "DNT": "1",
    "Origin": "https://banggia.dnse.com.vn",
    "Referer": "https://banggia.dnse.com.vn/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    ),
}

def epoch_now():
    return int(time.time())

def request_symbol(symbol, start, end):
    params = {
        "resolution": RESOLUTION,
        "symbol": symbol,
        "from": start,
        "to": end,
    }

    attempts = []
    for base in ENDPOINTS[symbol]:
        try:
            r = requests.get(
                base,
                params=params,
                headers=HEADERS,
                timeout=15,
            )
            attempts.append({
                "endpoint": base,
                "url": r.url,
                "status_code": r.status_code,
                "response_preview": r.text[:1000],
            })
            if r.ok:
                try:
                    payload = r.json()
                except ValueError as e:
                    return {
                        "ok": False,
                        "endpoint": base,
                        "url": r.url,
                        "status_code": r.status_code,
                        "error": f"JSONDecodeError: {e}",
                        "response_text": r.text[:5000],
                        "attempts": attempts,
                    }
                return {
                    "ok": True,
                    "endpoint": base,
                    "url": r.url,
                    "status_code": r.status_code,
                    "payload": payload,
                    "attempts": attempts,
                }
        except Exception as e:
            attempts.append({
                "endpoint": base,
                "error": f"{type(e).__name__}: {e}",
            })

    return {
        "ok": False,
        "error": "All configured endpoints failed",
        "attempts": attempts,
    }

def key_candidates(obj, needles=(
    "oi", "openinterest", "open_interest",
    "basis", "volume", "timestamp", "time",
    "receivedat", "received_at"
)):
    hits = {}

    def walk(x, path=""):
        if isinstance(x, dict):
            for k, v in x.items():
                p = f"{path}.{k}" if path else str(k)
                kl = str(k).lower().replace("-", "").replace(" ", "")
                if any(n in kl for n in needles):
                    hits[p] = v
                walk(v, p)
        elif isinstance(x, list):
            for i, v in enumerate(x[:20]):
                walk(v, f"{path}[{i}]")

    walk(obj)
    return hits

def normalize_ohlc(payload):
    if isinstance(payload, dict):
        for k in ("data", "result", "candles", "items"):
            if k in payload:
                normalized = normalize_ohlc(payload[k])
                if normalized is not None:
                    return normalized

        if all(k in payload for k in ("t", "o", "h", "l", "c")):
            return payload

        if all(k in payload for k in ("time", "open", "high", "low", "close")):
            return payload

    if isinstance(payload, list) and payload:
        last = payload[-1]
        if isinstance(last, dict):
            return last
        if isinstance(last, (list, tuple)) and len(last) >= 5:
            return {"raw_candle": last}

    return None

def summarize_payload(payload):
    return {
        "normalized": normalize_ohlc(payload),
        "candidate_fields": key_candidates(payload),
        "payload_type": type(payload).__name__,
        "top_level_keys": list(payload.keys())[:50] if isinstance(payload, dict) else None,
    }

def main():
    started = time.time()
    total = 0

    print(
        f"[probe-v2] start={datetime.now().astimezone().isoformat()} "
        f"duration={DURATION_SEC}s interval={INTERVAL_SEC}s "
        f"resolution={RESOLUTION}"
    )

    # Start fresh for each workflow run so the artifact is self-contained.
    if OUT.exists():
        OUT.unlink()

    while time.time() - started < DURATION_SEC:
        now = epoch_now()
        row = {
            "probe_version": "v2",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "request_from": now - LOOKBACK_SEC,
            "request_to": now,
            "resolution": RESOLUTION,
            "symbols": {},
        }

        for symbol in ("VN30F1M", "VN30"):
            result = request_symbol(symbol, now - LOOKBACK_SEC, now)
            if result["ok"]:
                payload = result["payload"]
                row["symbols"][symbol] = {
                    "endpoint": result["endpoint"],
                    "url": result["url"],
                    "status_code": result["status_code"],
                    **summarize_payload(payload),
                    "raw": payload,
                    "attempts": result["attempts"],
                }
            else:
                row["symbols"][symbol] = {
                    "error": result.get("error"),
                    "attempts": result.get("attempts", []),
                }

        with OUT.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ) + "\n"
            )

        total += 1
        print(
            f"[probe-v2] sample={total} "
            f"utc={row['captured_at']} "
            f"VN30F1M_ok={row['symbols']['VN30F1M'].get('status_code')} "
            f"VN30_ok={row['symbols']['VN30'].get('status_code')}"
        )

        remaining = DURATION_SEC - (time.time() - started)
        if remaining > 0:
            time.sleep(min(INTERVAL_SEC, remaining))

    print(f"[probe-v2] finished samples={total} file={OUT}")

if __name__ == "__main__":
    main()
