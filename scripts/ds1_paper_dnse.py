"""Isolated DNSE-only read client, paper research, no trading or alerts."""
import math,time,requests
from scripts import ds1_watch as v1

class Client:
    """Sequential requests; configurable pacing is not a provider quota claim."""
    def __init__(self, interval=1.0, attempts=3, session=None):
        if interval < 0.2 or not 1 <= attempts <= 5:
            raise ValueError("invalid request limits")
        self.interval, self.attempts = interval, attempts
        self.session = session or requests.Session()
        self.last = 0.0
        self.metrics = {"requests": 0, "retries": 0, "errors": 0}

    def get(self, url, params=None):
        for attempt in range(self.attempts):
            time.sleep(max(0, self.interval - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            self.metrics["requests"] += 1
            try:
                response = self.session.get(url, params=params, headers=v1.HEADERS, timeout=(5, 20))
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt + 1 < self.attempts:
                        self.metrics["retries"] += 1
                        retry = response.headers.get("Retry-After", "")
                        delay = float(retry) if retry.isdigit() else 2 ** attempt
                        time.sleep(min(60, max(1, delay)))
                        continue
                response.raise_for_status()
                return response.json()
            except (requests.Timeout, requests.ConnectionError):
                if attempt + 1 < self.attempts:
                    self.metrics["retries"] += 1
                    time.sleep(2 ** attempt)
                    continue
                self.metrics["errors"] += 1
                raise RuntimeError("market API transport failure") from None
            except (requests.RequestException, ValueError):
                self.metrics["errors"] += 1
                raise RuntimeError("market API HTTP or JSON failure") from None
        raise RuntimeError("request attempts exhausted")

    def ohlcv(self, symbol, resolution, now):
        seconds = 220 * 86400 if resolution == "1D" else 86400
        endpoint = v1.INDEX_URL if symbol == "VN30" else v1.BASE_URL
        payload = self.get(endpoint, {"symbol": symbol, "resolution": resolution,
                                      "from": int(now.timestamp()) - seconds, "to": int(now.timestamp())})
        result = validate_bars(payload)
        # Live PVT payload verified 2026-10-08: 25.55 means 25,550 VND.
        if symbol != "VN30":
            for bar in result:
                for key in "ohlc":
                    bar[key] *= 1000
        return result


def validate_bars(payload):
    if not isinstance(payload, dict):
        raise ValueError("OHLCV must be an object")
    arrays = [payload.get(k, payload.get(alias)) for k, alias in
              zip("tohlcv", ("time", "open", "high", "low", "close", "volume"))]
    if any(not isinstance(a, list) for a in arrays) or len({len(a) for a in arrays}) != 1:
        raise ValueError("OHLCV arrays missing or unequal")
    result = []
    for values in zip(*arrays):
        bar = dict(zip("tohlcv", map(float, values)))
        if not all(math.isfinite(x) for x in bar.values()):
            raise ValueError("nonfinite OHLCV")
        if min(bar[k] for k in "ohlc") <= 0 or bar["v"] < 0:
            raise ValueError("invalid price or volume")
        if not bar["l"] <= min(bar["o"], bar["c"]) <= max(bar["o"], bar["c"]) <= bar["h"]:
            raise ValueError("invalid OHLC bounds")
        if result and bar["t"] <= result[-1]["t"]:
            raise ValueError("unordered or duplicate timestamps")
        result.append(bar)
    return result


def pre_breakout_rank(daily):
    """Daily-only WATCH priority, not a BUY signal or a new S1-S5 gate."""
    if len(daily) < 60:
        return {"score": 0, "status": "INSUFFICIENT_DATA"}
    closes = [b["c"] for b in daily]
    ma20 = v1.sma(closes, 20)
    ma50 = v1.sma(closes, 50)
    last = closes[-1]
    highs = [b["h"] for b in daily[-21:-1]]
    resistance = max(highs)
    if resistance <= 0 or ma20 <= 0 or ma50 <= 0:
        return {"score": 0, "status": "INVALID"}
    distance_pct = 100 * (resistance - last) / resistance
    ranges = [(b["h"] - b["l"]) / b["c"] for b in daily[-20:] if b["c"] > 0]
    if len(ranges) != 20:
        return {"score": 0, "status": "INVALID"}
    older_range = sum(ranges[:10]) / 10
    newer_range = sum(ranges[10:]) / 10
    older_vol = sum(b["v"] for b in daily[-20:-10]) / 10
    newer_vol = sum(b["v"] for b in daily[-10:]) / 10
    trend = ma20 > ma50 and last >= ma20
    near_pivot = 0 <= distance_pct <= 5
    contracting = older_range > 0 and newer_range <= older_range * 0.85
    volume_dryup = older_vol > 0 and newer_vol <= older_vol * 0.85
    score = (30 if trend else 0) + (30 if near_pivot else 0) + (20 if contracting else 0) + (20 if volume_dryup else 0)
    return {"score": score, "status": "WATCH" if trend and near_pivot and (contracting or volume_dryup) else "NOT_READY",
            "pivot_vnd": resistance, "distance_to_pivot_pct": round(distance_pct, 2),
            "trend": trend, "range_contraction": contracting, "volume_dryup": volume_dryup}


