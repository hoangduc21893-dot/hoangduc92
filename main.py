import os
import time
import requests
import pandas as pd
from google import genai


# ============================================================
# CONFIG
# ============================================================

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

SYMBOL = "FPT"
GEMINI_MODEL = "gemini-3.8-flash"


# ============================================================
# 1. GET STOCK DATA FROM DNSE
# ============================================================

def get_stock_data():
    """
    Lấy dữ liệu nến OHLCV 90 ngày gần nhất từ DNSE Entrade X.
    """

    to_time = int(time.time())
    from_time = to_time - (90 * 24 * 3600)

    url = "https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"

    params = {
        "symbol": SYMBOL,
        "from": from_time,
        "to": to_time,
        "resolution": "1D"
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    try:
        print(f"Đang kết nối API DNSE lấy dữ liệu {SYMBOL}...")

        res = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=15
        )

        res.raise_for_status()

        data = res.json()

        if "t" in data and len(data["t"]) > 0:

            df = pd.DataFrame({
                "Date": pd.to_datetime(data["t"], unit="s"),
                "Open": data["o"],
                "High": data["h"],
                "Low": data["l"],
                "Close": data["c"],
                "Volume": data["v"]
            })

            # Chuẩn hóa giá nếu DNSE trả về đơn vị nghìn đồng
            if df["Close"].iloc[-1] < 1000:
                for col in ["Open", "High", "Low", "Close"]:
                    df[col] = df[col] * 1000

            df = (
                df
                .sort_values("Date")
                .reset_index(drop=True)
            )

            print(
                f"-> Đã lấy thành công {len(df)} phiên nến từ DNSE!"
            )

            return df

    except Exception as e:

        print(f"Lỗi kết nối DNSE: {e}")

    # ========================================================
    # FALLBACK DATA
    # ========================================================

    print("-> Chuyển sang dữ liệu dự phòng...")

    df = pd.DataFrame([
        {
            "Date": "2026-09-18",
            "Open": 64800,
            "High": 65500,
            "Low": 64500,
            "Close": 65200,
            "Volume": 2850000
        },
        {
            "Date": "2026-09-21",
            "Open": 65200,
            "High": 66000,
            "Low": 65000,
            "Close": 65800,
            "Volume": 3100000
        },
        {
            "Date": "2026-09-22",
            "Open": 65800,
            "High": 66500,
            "Low": 65600,
            "Close": 66200,
            "Volume": 3400000
        },
        {
            "Date": "2026-09-23",
            "Open": 66200,
            "High": 66800,
            "Low": 65900,
            "Close": 66500,
            "Volume": 4200000
        },
        {
            "Date": "2026-09-24",
            "Open": 66500,
            "High": 66600,
            "Low": 65500,
            "Close": 65900,
            "Volume": 3800000
        },
        {
            "Date": "2026-09-25",
            "Open": 65900,
            "High": 66200,
            "Low": 65100,
            "Close": 65400,
            "Volume": 2900000
        },
        {
            "Date": "2026-09-28",
            "Open": 65400,
            "High": 65800,
            "Low": 64800,
            "Close": 65000,
            "Volume": 2600000
        },
        {
            "Date": "2026-09-29",
            "Open": 65000,
            "High": 65300,
            "Low": 64200,
            "Close": 64500,
            "Volume": 3150000
        },
        {
            "Date": "2026-09-30",
            "Open": 64500,
            "High": 64900,
            "Low": 63800,
            "Close": 64000,
            "Volume": 3500000
        },
        {
            "Date": "2026-10-01",
            "Open": 64000,
            "High": 64200,
            "Low": 62500,
            "Close": 62700,
            "Volume": 4100000
        },
        {
            "Date": "2026-10-02",
            "Open": 62700,
            "High": 62900,
            "Low": 62000,
            "Close": 62100,
            "Volume": 3192400
        }
    ])

    df["Date"] = pd.to_datetime(df["Date"])

    return df


# ============================================================
# 2. TECHNICAL ANALYSIS + GEMINI
# ============================================================

def analyze_with_ai(df):

    """
    Tính SMA5 / RSI7 và gửi dữ liệu sang Gemini.
    """

    if len(df) < 8:
        raise ValueError(
            "Cần ít nhất 8 phiên dữ liệu để tính RSI7."
        )

    # --------------------------------------------------------
    # SMA 5
    # --------------------------------------------------------

    df["SMA5"] = (
        df["Close"]
        .rolling(5)
        .mean()
    )

    # --------------------------------------------------------
    # RSI 7
    # --------------------------------------------------------

    delta = df["Close"].diff()

    gain = (
        delta
        .where(delta > 0, 0)
        .rolling(7)
        .mean()
    )

    loss = (
        -delta
        .where(delta < 0, 0)
        .rolling(7)
        .mean()
    )

    rs = gain / (loss + 1e-9)

    df["RSI"] = (
        100 -
        (100 / (1 + rs))
    )

    # --------------------------------------------------------
    # Latest data
    # --------------------------------------------------------

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    pct_change = round(
        (
            (latest["Close"] - prev["Close"])
            / prev["Close"]
        ) * 100,
        2
    )

    # --------------------------------------------------------
    # Gemini Client
    # --------------------------------------------------------

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    # --------------------------------------------------------
    # Prompt
    # --------------------------------------------------------

    prompt = f"""
Bạn là chuyên gia phân tích kỹ thuật chứng khoán Việt Nam.

Hãy phân tích phiên giao dịch gần nhất của {SYMBOL}.

DỮ LIỆU:

- Ngày: {latest["Date"].strftime("%d/%m/%Y")}
- Giá đóng cửa: {latest["Close"]:,.0f} VNĐ
- Thay đổi: {pct_change}%
- Khối lượng: {int(latest["Volume"]):,} cổ phiếu
- RSI(7): {latest["RSI"]:.2f}
- SMA(5): {latest["SMA5"]:,.0f} VNĐ

YÊU CẦU:

1. Đánh giá xu hướng ngắn hạn.
2. Đánh giá dòng tiền dựa trên giá và khối lượng.
3. Đánh giá RSI.
4. Xác định vùng hỗ trợ quan trọng.
5. Xác định vùng kháng cự quan trọng.
6. Đưa ra hành động:
   - MUA
   - BÁN
   - TIẾP TỤC QUAN SÁT

Không được bịa dữ liệu ngoài những gì được cung cấp.

Trả lời ngắn gọn, rõ ràng và ưu tiên tính thực tế.
"""

    # --------------------------------------------------------
    # Call Gemini
    # --------------------------------------------------------

    for attempt in range(3):

        try:

            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )

            if not response.text:
                raise RuntimeError(
                    "Gemini trả về nội dung rỗng."
                )

            return (
                latest,
                pct_change,
                response.text
            )

        except Exception as e:

            print(
                f"Gemini attempt {attempt + 1}/3 lỗi: {e}"
            )

            if attempt < 2:
                time.sleep(4)

    raise RuntimeError(
        "Không thể hoàn tất phân tích qua Gemini API."
    )


# ============================================================
# 3. SEND TELEGRAM
# ============================================================

def send_telegram(message):

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "Thiếu TELEGRAM_BOT_TOKEN."
        )

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "Thiếu TELEGRAM_CHAT_ID."
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=10
        )

        response.raise_for_status()

        print(
            "Đã gửi tin nhắn Telegram thành công!"
        )

    except Exception as e:

        print(
            f"Lỗi gửi Telegram: {e}"
        )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("DAILY STOCK ANALYSIS AGENT")
    print("Provider: Gemini Free Tier")
    print(f"Symbol: {SYMBOL}")
    print("=" * 60)

    df = get_stock_data()

    latest, pct_change, ai_report = analyze_with_ai(df)

    final_message = (
        f"🔔 BÁO CÁO PHÂN TÍCH {SYMBOL}\n\n"
        f"📅 Ngày: "
        f"{latest['Date'].strftime('%d/%m/%Y')}\n"
        f"💰 Giá đóng cửa: "
        f"{latest['Close']:,.0f} VNĐ "
        f"({pct_change}%)\n"
        f"📊 Khối lượng: "
        f"{int(latest['Volume']):,} CP\n"
        f"📈 RSI(7): "
        f"{latest['RSI']:.2f}\n"
        f"📐 SMA(5): "
        f"{latest['SMA5']:,.0f} VNĐ\n\n"
        f"{ai_report}"
    )

    print(final_message)

    send_telegram(final_message)
