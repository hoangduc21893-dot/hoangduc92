import os
import time
from datetime import datetime, timezone, timedelta

import pandas as pd
import requests

SYMBOL = "MWG"
BREAKOUT = 74_000
LOOKBACK_MINUTES = 90
VOLUME_MULTIPLIER = 1.5

DNSE_URL = "https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"
TELEGRAM_URL = "https://api.telegram.org/bot{}/sendMessage"


def fetch_1m():
    now = int(time.time())
    start = now - LOOKBACK_MINUTES * 60

    params = {
        "symbol": SYMBOL,
        "from": start,
        "to": now,
        "resolution": "1",
    }
    r = requests.get(
        DNSE_URL,
        params=params,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()

    if not data.get("t"):
        raise RuntimeError("DNSE không trả dữ liệu 1m cho MWG.")

    df = pd.DataFrame({
        "ts": pd.to_datetime(data["t"], unit="s", utc=True),
        "open": data["o"],
        "high": data["h"],
        "low": data["l"],
        "close": data["c"],
        "volume": data["v"],
    }).sort_values("ts").reset_index(drop=True)

    # DNSE có thể trả giá theo nghìn đồng.
    if df["close"].iloc[-1] < 1000:
        for col in ["open", "high", "low", "close"]:
            df[col] *= 1000

    return df


def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID.")

    r = requests.post(
        TELEGRAM_URL.format(token),
        json={"chat_id": chat_id, "text": message},
        timeout=10,
    )
    r.raise_for_status()


def main():
    # Chỉ chạy trong giờ giao dịch Việt Nam.
    now_vn = datetime.now(timezone.utc) + timedelta(hours=7)
    if now_vn.weekday() >= 5:
        print("Weekend -> skip.")
        return

    # GitHub Actions schedule có thể lệch vài phút; dùng cửa sổ rộng.
    market_time = (
        (9 * 60 <= now_vn.hour * 60 + now_vn.minute <= 11 * 60 + 45)
        or
        (13 * 60 <= now_vn.hour * 60 + now_vn.minute <= 14 * 60 + 45)
    )
    if not market_time:
        print(f"Outside market window: {now_vn.isoformat()}")
        return

    df = fetch_1m()
    if len(df) < 25:
        raise RuntimeError("Không đủ nến 1m để xác nhận volume breakout.")

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    price = float(latest["close"])
    previous_price = float(previous["close"])
    vol = float(latest["volume"])
    avg_vol = float(df.iloc[-21:-1]["volume"].mean())

    crossed = previous_price < BREAKOUT <= price
    volume_confirmed = avg_vol > 0 and vol >= avg_vol * VOLUME_MULTIPLIER

    print(
        f"MWG price={price:.0f}, prev={previous_price:.0f}, "
        f"1m_volume={vol:.0f}, avg20={avg_vol:.0f}, "
        f"crossed={crossed}, volume_confirmed={volume_confirmed}"
    )

    if not (crossed and volume_confirmed):
        return

    vn_time = latest["ts"].tz_convert("Asia/Ho_Chi_Minh").strftime("%H:%M")
    message = (
        "🚨 MWG BREAKOUT ALERT\n\n"
        f"⏰ {vn_time} VN\n"
        f"💰 Giá: {price:,.0f} VNĐ\n"
        f"📈 Breakout: > {BREAKOUT:,.0f}\n"
        f"📊 Volume 1m: {vol:,.0f} "
        f"(~{vol / avg_vol:.1f}x TB20 1m)\n\n"
        "Strategy: S3 Breakout Momentum + S4 Pullback Trend Following\n"
        "⚠️ Đây là cảnh báo breakout; chưa tự động đặt lệnh. "
        "Kiểm tra retest/R:R trước khi vào."
    )
    send_telegram(message)
    print("Telegram breakout alert sent.")


if __name__ == "__main__":
    main()
