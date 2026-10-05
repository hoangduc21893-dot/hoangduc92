#!/usr/bin/env python3
"""Conservative DS1 multi-stock watcher.

FALSE POSITIVE = zero tolerance.
Monitors every DS1 symbol for confirmed S3 breakout and S4 pullback setups.
It intentionally accepts false negatives and sends Telegram only after
multiple independent confirmations.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

DS1 = [
    "PVT", "PVS", "MSB", "HAH", "BSR", "VGC",
    "DHC", "VTP", "VPB", "MWG", "HDB", "PET",
]

BREAKOUT_LOOKBACK = 20
MIN_CLOSED_1M_BARS = 3
VOLUME_RATIO_MIN = 1.50
RETEST_TOLERANCE = 0.25
MAX_BREAKOUT_CHASE_PCT = 1.10
S4_NEAR_MA_PCT = 1.50
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
BASE_URL = "https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"
STATE_PATH = Path("data/ds1_watch_state.json")

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://www.dnse.com.vn",
    "referer": "https://www.dnse.com.vn/",
    "user-agent": "Mozilla/5.0",
}


def in_session(now: datetime) -> bool:
    t = now.time()
    return dtime(9, 15) <= t <= dtime(11, 30) or dtime(13, 0) <= t <= dtime(14, 45)


def fetch(symbol: str, resolution: str, seconds: int) -> dict:
    now = int(time.time())
    params = {
        "from": now - seconds,
        "to": now,
        "symbol": symbol,
        "resolution": resolution,
    }
    r = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"{symbol}: invalid DNSE response")
    return data


def bars(data: dict) -> list[dict]:
    ts = data.get("t") or data.get("time") or []
    opens = data.get("o") or data.get("open") or []
    highs = data.get("h") or data.get("high") or []
    lows = data.get("l") or data.get("low") or []
    closes = data.get("c") or data.get("close") or []
    vols = data.get("v") or data.get("volume") or []
    n = min(len(ts), len(opens), len(highs), len(lows), len(closes), len(vols))
    out = []
    for i in range(n):
        try:
            out.append({
                "t": float(ts[i]), "o": float(opens[i]), "h": float(highs[i]),
                "l": float(lows[i]), "c": float(closes[i]), "v": float(vols[i]),
            })
        except (TypeError, ValueError):
            continue
    return out


def sma(values: list[float], n: int) -> float:
    return sum(values[-n:]) / n if len(values) >= n else 0.0


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def session_progress(now: datetime) -> float:
    if now.time() <= dtime(11, 30):
        elapsed = (now.hour * 60 + now.minute) - (9 * 60 + 15)
    elif now.time() < dtime(13, 0):
        elapsed = 135
    else:
        elapsed = 135 + ((now.hour * 60 + now.minute) - (13 * 60))
    return max(0.05, min(1.0, elapsed / 240.0))


def volume_ratio(intraday: list[dict], daily: list[dict], now: datetime) -> float:
    completed_daily = daily[:-1] if len(daily) > 1 else daily
    vols = [b["v"] for b in completed_daily[-20:] if b["v"] > 0]
    if not vols:
        return 0.0
    adv20 = sum(vols) / len(vols)
    today = now.date()
    day_bars = [
        b for b in intraday
        if datetime.fromtimestamp(b["t"], VN_TZ).date() == today
    ]
    cumulative = sum(b["v"] for b in day_bars)
    expected = adv20 * session_progress(now)
    return cumulative / expected if expected > 0 else 0.0


def check_s3(symbol: str, intraday: list[dict], daily: list[dict], vr: float):
    # Never use the newest 1m bar: it may still be forming.
    closed = intraday[:-1]
    if len(closed) < MIN_CLOSED_1M_BARS + 1 or len(daily) < BREAKOUT_LOOKBACK + 5:
        return None

    completed_daily = daily[:-1]
    prior = completed_daily[-BREAKOUT_LOOKBACK:]
    breakout = max(b["h"] for b in prior)
    recent = closed[-MIN_CLOSED_1M_BARS:]
    closes = [b["c"] for b in recent]
    price = closes[-1]

    confirmed = all(c > breakout for c in closes)
    trade_through = recent[0]["h"] > breakout
    retest = any(
        b["l"] <= breakout + RETEST_TOLERANCE and b["c"] > breakout
        for b in recent[1:]
    )
    chase = price > breakout * (1 + MAX_BREAKOUT_CHASE_PCT / 100)
    volume_ok = vr >= VOLUME_RATIO_MIN

    if confirmed and trade_through and retest and volume_ok and not chase:
        return {
            "strategy": "S3 Breakout Momentum",
            "trigger": f"3x 1M closed > {breakout:.2f} + retest/hold + volume {vr:.2f}x",
            "price": price, "level": breakout, "volume_ratio": vr,
        }
    return None


def check_s4(symbol: str, intraday: list[dict], daily: list[dict]):
    # Use only completed daily candles for trend state.
    completed = daily[:-1]
    if len(completed) < 55:
        return None

    closes = [b["c"] for b in completed]
    ma20 = sma(closes, 20)
    ma50 = sma(closes, 50)
    if not ma20 or not ma50 or ma20 <= ma50:
        return None

    last = completed[-1]
    prev = completed[-2]
    near_ma20 = abs(last["c"] - ma20) / ma20 * 100 <= S4_NEAR_MA_PCT
    bullish_reversal = last["c"] > last["o"] and last["c"] > prev["c"]
    avg20v = sma([b["v"] for b in completed], 20)
    volume_contract = avg20v > 0 and last["v"] <= avg20v * 1.10

    if near_ma20 and bullish_reversal and volume_contract:
        # Require intraday price to remain above the completed daily close.
        closed = intraday[:-1]
        if not closed:
            return None
        price = closed[-1]["c"]
        if price >= last["c"]:
            return {
                "strategy": "S4 Pullback Trend Following",
                "trigger": f"MA20 {ma20:.2f} > MA50 {ma50:.2f}; pullback/reversal confirmed",
                "price": price, "level": ma20, "volume_ratio": 0.0,
            }
    return None


def telegram(message: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message},
        timeout=15,
    )
    r.raise_for_status()


def main() -> int:
    now = datetime.now(VN_TZ)
    if now.weekday() >= 5 or not in_session(now):
        print("Outside DS1 trading session.")
        return 0

    state = load_state()
    alerts = 0

    for symbol in DS1:
        try:
            intraday = bars(fetch(symbol, "1", 24 * 60 * 60))
            daily = bars(fetch(symbol, "1D", 90 * 24 * 60 * 60))
            if len(intraday) < 5 or len(daily) < 55:
                print(f"{symbol}: insufficient data")
                continue

            vr = volume_ratio(intraday, daily, now)
            signal = check_s3(symbol, intraday, daily, vr)
            if signal is None:
                signal = check_s4(symbol, intraday, daily)

            if signal is None:
                print(f"{symbol}: no confirmed setup")
                continue

            key = f"{now:%Y-%m-%d}|{symbol}|{signal['strategy']}"
            if state.get("last_alert_key") == key:
                print(f"{symbol}: alert already sent")
                continue

            message = (
                f"🚨 DS1 CONFIRMED SETUP — {symbol}\n\n"
                f"Strategy: {signal['strategy']}\n"
                f"Giá: {signal['price']:.2f}\n"
                f"Trigger: {signal['trigger']}\n"
                "Action: WAIT/BUY only after manual risk check\n"
                "Safety: FALSE POSITIVE = NGHIÊM CẤM. "
                "Thiếu bất kỳ xác nhận nào = KHÔNG ALERT."
            )
            telegram(message)
            state["last_alert_key"] = key
            state["last_alert_at"] = now.isoformat()
            save_state(state)
            alerts += 1
            print(f"{symbol}: Telegram alert sent")
        except Exception as exc:
            print(f"{symbol}: ERROR {exc}")

    print(f"DS1 scan complete. Alerts={alerts}/{len(DS1)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
