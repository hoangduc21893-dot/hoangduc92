#!/usr/bin/env python3
"""Intraday MWG breakout watcher for GitHub Actions.

Uses DNSE's public chart endpoint for 1-minute and daily OHLCV.
It alerts Telegram only after a confirmed breakout and suppresses
duplicate alerts for the same trading day.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

SYMBOL = "MWG"
BREAKOUT = 74.0
MAX_CHASE = 74.8
SL = 72.8
TP1 = 76.5
TP2 = 79.0
MIN_CLOSES = 2
VOLUME_RATIO = 1.30
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
STATE_PATH = Path("data/mwg_breakout_state.json")
BASE_URL = "https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"

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
        raise RuntimeError("DNSE response is not an object")
    return data


def bars(data: dict) -> list[dict]:
    # DNSE chart responses normally expose parallel arrays:
    # t/o/h/l/c/v. Keep the parser tolerant to common variants.
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
                "t": float(ts[i]),
                "o": float(opens[i]),
                "h": float(highs[i]),
                "l": float(lows[i]),
                "c": float(closes[i]),
                "v": float(vols[i]),
            })
        except (TypeError, ValueError):
            continue
    return out


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def avg_daily_volume(daily: list[dict]) -> float:
    # Exclude the latest bar because it can be today's incomplete session.
    completed = daily[:-1] if len(daily) > 1 else daily
    vols = [b["v"] for b in completed[-20:] if b["v"] > 0]
    return sum(vols) / len(vols) if vols else 0.0


def session_progress(now: datetime) -> float:
    # Approximate elapsed fraction of the 09:15-11:30 + 13:00-14:45 session.
    if now.time() <= dtime(11, 30):
        elapsed = (now.hour * 60 + now.minute) - (9 * 60 + 15)
    elif now.time() < dtime(13, 0):
        elapsed = 135
    else:
        elapsed = 135 + ((now.hour * 60 + now.minute) - (13 * 60))
    total = 135 + 105
    return max(0.05, min(1.0, elapsed / total))


def main() -> int:
    now = datetime.now(VN_TZ)
    if now.weekday() >= 5 or not in_session(now):
        print("Outside MWG trading session; nothing to do.")
        return 0

    intraday = bars(fetch(SYMBOL, "1", 24 * 60 * 60))
    daily = bars(fetch(SYMBOL, "1D", 45 * 24 * 60 * 60))
    if len(intraday) < MIN_CLOSES or len(daily) < 10:
        raise RuntimeError("Insufficient DNSE data for MWG breakout check")

    # Use the last two closed/available 1m bars. GitHub polling is periodic,
    # so the newest bar may still be forming; requiring two consecutive closes
    # materially reduces single-tick false breakouts.
    recent = intraday[-MIN_CLOSES:]
    closes = [b["c"] for b in recent]
    price = closes[-1]
    confirmed = all(c >= BREAKOUT for c in closes)

    # Compare cumulative session volume with the expected share of 20-day ADV.
    today = now.date()
    day_bars = [
        b for b in intraday
        if datetime.fromtimestamp(b["t"], VN_TZ).date() == today
    ]
    cumulative_volume = sum(b["v"] for b in day_bars)
    adv20 = avg_daily_volume(daily)
    expected = adv20 * session_progress(now)
    volume_ratio = cumulative_volume / expected if expected > 0 else 0.0
    volume_ok = volume_ratio >= VOLUME_RATIO

    print(
        f"MWG price={price:.2f} closes={closes} "
        f"breakout={confirmed} cum_volume={cumulative_volume:.0f} "
        f"volume_ratio={volume_ratio:.2f} volume_ok={volume_ok}"
    )

    if not (confirmed and volume_ok):
        return 0

    state = load_state()
    today_key = now.strftime("%Y-%m-%d")
    if state.get("last_alert_date") == today_key:
        print("MWG breakout alert already sent today.")
        return 0

    chase = price > MAX_CHASE
    action = "WAIT — KHÔNG CHASE" if chase else "BUY BREAKOUT"
    entry_low = BREAKOUT
    entry_high = MAX_CHASE

    risk = max(0.01, ((entry_low + entry_high) / 2) - SL)
    rr1 = (TP1 - ((entry_low + entry_high) / 2)) / risk
    rr2 = (TP2 - ((entry_low + entry_high) / 2)) / risk

    message = (
        "🚨 MWG BREAKOUT ALERT\n\n"
        f"Giá: {price:.2f}\n"
        f"Breakout: > {BREAKOUT:.2f}\n"
        f"Volume ratio: {volume_ratio:.2f}x kỳ vọng\n"
        "Strategy: S3 Breakout + S4 Pullback\n"
        f"Entry: {entry_low:.1f}–{entry_high:.1f}\n"
        f"SL: {SL:.1f}\n"
        f"TP1: {TP1:.1f} (R:R ~1:{rr1:.1f})\n"
        f"TP2: {TP2:.1f} (R:R ~1:{rr2:.1f})\n"
        f"Action: {action}\n"
        "Rule: 2 nến 1M liên tiếp trên breakout + volume xác nhận."
    )

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message},
        timeout=15,
    )
    response.raise_for_status()

    state.update({
        "last_alert_date": today_key,
        "last_alert_price": price,
        "last_alert_volume_ratio": volume_ratio,
        "alerted_at": now.isoformat(),
    })
    save_state(state)
    print("MWG breakout Telegram alert sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
