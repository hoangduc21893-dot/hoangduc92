"""Conservative DS1 pre-breakout scoring. Confirmation logic remains in ds1_watch."""
from __future__ import annotations

import math
from statistics import mean
from typing import Iterable

SECTORS = {
    "ENERGY": ("PVT", "PVS", "BSR"),
    "BANKS": ("MSB", "VPB", "HDB"),
    "CONSUMER": ("MWG", "PET"),
    "MATERIALS": ("HPG", "DHC", "VGC"),
    "INDUSTRIALS": ("HAH", "VTP"),
}
WEIGHTS = {
    "near_breakout": 15,
    "base_quality": 20,
    "volume_dry_up": 15,
    "higher_low": 10,
    "relative_strength": 15,
    "volume_up_down": 10,
    "sector_strength": 5,
    "catalyst": 5,
    "market_regime": 5,
}
MIN_HISTORY = 61


def _valid_bar(bar):
    try:
        values = [float(bar[k]) for k in ("o", "h", "l", "c", "v")]
    except (KeyError, TypeError, ValueError):
        return False
    return all(math.isfinite(v) for v in values) and values[1] >= values[2] and values[3] > 0 and values[4] >= 0


def _closed(data):
    """Match ds1_watch's convention: the final API bar may still be forming."""
    if not isinstance(data, list) or len(data) < MIN_HISTORY:
        return []
    result = [b for b in data[:-1] if _valid_bar(b)]
    return result


def _return_20(data):
    if len(data) < 21 or data[-21]["c"] <= 0:
        return None
    return data[-1]["c"] / data[-21]["c"] - 1.0


def _atr(data, period=14):
    if len(data) < period + 1:
        return None
    tr = []
    for previous, current in zip(data[-period - 1:-1], data[-period:]):
        tr.append(max(current["h"] - current["l"],
                      abs(current["h"] - previous["c"]),
                      abs(current["l"] - previous["c"])))
    value = mean(tr)
    return value if math.isfinite(value) and value > 0 else None


def _sector_returns(daily_by_symbol):
    returns = {}
    for sector, symbols in SECTORS.items():
        values = [_return_20(_closed(daily_by_symbol.get(symbol, [])))
                  for symbol in symbols if symbol in daily_by_symbol]
        values = [v for v in values if v is not None]
        if len(values) >= 2:
            returns[sector] = mean(values)
    return returns


def _sector_for(symbol):
    return next((name for name, members in SECTORS.items() if symbol in members), None)


def score_prebreakout(symbol, daily, vn30, regime, sector_return=None,
                      catalyst=False):
    """Return a reviewable score card; missing mandatory inputs always block."""
    bars = _closed(daily)
    market = _closed(vn30)
    if len(bars) < 55 or len(market) < 21:
        return {"symbol": symbol, "score": 0, "classification": "NO TRADE",
                "blocked": ["insufficient_closed_daily_history"], "scores": {}}

    close = bars[-1]["c"]
    resistance = max(b["h"] for b in bars[-21:-1])
    support = min(b["l"] for b in bars[-20:])
    a = _atr(bars)
    stock_return = _return_20(bars)
    market_return = _return_20(market)
    if (close <= 0 or resistance <= 0 or support <= 0 or a is None
            or stock_return is None or market_return is None
            or sector_return is None):
        return {"symbol": symbol, "score": 0, "classification": "NO TRADE",
                "blocked": ["missing_price_volume_rs_atr_or_sector_data"], "scores": {}}

    gap_pct = (resistance - close) / resistance * 100.0
    # An already-broken pivot belongs to the separate confirmation engine.
    near = (15 if 0 <= gap_pct <= 1.5 else 12 if gap_pct <= 3.0
            else 7 if gap_pct <= 5.0 else 0)

    base = bars[-20:]
    base_width = (max(b["h"] for b in base) - min(b["l"] for b in base)) / close * 100.0
    base_quality = 20 if base_width <= 10 else 16 if base_width <= 14 else 10 if base_width <= 18 else 0

    recent_vol = mean(b["v"] for b in bars[-5:])
    prior_vol = mean(b["v"] for b in bars[-20:-5])
    if prior_vol <= 0:
        return {"symbol": symbol, "score": 0, "classification": "NO TRADE",
                "blocked": ["invalid_volume_baseline"], "scores": {}}
    dry_ratio = recent_vol / prior_vol
    dry = 15 if dry_ratio <= 0.60 else 11 if dry_ratio <= 0.80 else 6 if dry_ratio <= 0.95 else 0

    recent_lows = min(b["l"] for b in bars[-5:])
    prior_lows = min(b["l"] for b in bars[-10:-5])
    higher = 10 if recent_lows >= prior_lows else 0

    rs = stock_return - market_return
    rs_score = 15 if rs >= 0.05 else 11 if rs >= 0.02 else 6 if rs >= 0 else 0

    up_volume = sum(b["v"] for b in bars[-20:] if b["c"] >= b["o"])
    down_volume = sum(b["v"] for b in bars[-20:] if b["c"] < b["o"])
    if up_volume + down_volume <= 0 or down_volume <= 0:
        return {"symbol": symbol, "score": 0, "classification": "NO TRADE",
                "blocked": ["invalid_up_down_volume"], "scores": {}}
    ud_ratio = up_volume / down_volume
    ud_score = 10 if ud_ratio >= 1.5 else 7 if ud_ratio >= 1.1 else 4 if ud_ratio >= 0.9 else 0

    sector_score = 5 if sector_return - market_return >= 0.05 else 3 if sector_return >= market_return else 0
    catalyst_score = 5 if catalyst else 0
    regime_score = 5 if regime == "TREND_UP" else 3 if regime == "RANGE" else 0

    scores = {
        "near_breakout": near, "base_quality": base_quality,
        "volume_dry_up": dry, "higher_low": higher,
        "relative_strength": rs_score, "volume_up_down": ud_score,
        "sector_strength": sector_score, "catalyst": catalyst_score,
        "market_regime": regime_score,
    }
    score = sum(scores.values())
    if score >= 80:
        classification = "PRE-BREAKOUT BUY"
    elif score >= 70:
        classification = "WATCH/BUY SMALL"
    elif score >= 60:
        classification = "WAIT"
    else:
        classification = "NO TRADE"

    ma20 = mean(b["c"] for b in bars[-20:])
    ma50 = mean(b["c"] for b in bars[-50:])
    s3 = gap_pct <= 5.0 and close < resistance
    s5 = base_width <= 18 and dry_ratio <= 0.95 and higher
    s4 = ma20 > ma50 and close >= ma20 - 0.5 * a and close < resistance
    strategies = [name for name, passed in (
        ("S3", s3), ("S5", s5), ("S4", s4)) if passed]

    blocked = []
    if close >= resistance:
        blocked.append("breakout_already_occurred_use_confirmation_engine")
    if gap_pct < 0 or gap_pct > 5:
        blocked.append("price_not_within_prebreakout_zone")
    if regime not in {"TREND_UP", "RANGE"}:
        blocked.append("market_regime_not_tradeable")
    if not strategies:
        blocked.append("no_S3_S5_S4_prebreakout_structure")
    if classification in {"WAIT", "NO TRADE"}:
        blocked.append("score_below_70")
    entry = close
    invalidation_level = min(support - 0.25 * a, entry - a)
    if invalidation_level <= 0 or invalidation_level >= entry:
        blocked.append("invalid_dynamic_invalidation")
    return {
        "symbol": symbol, "score": score, "classification": classification,
        "scores": scores, "blocked": blocked, "strategies": strategies,
        "price": close, "resistance": resistance, "support": support,
        "gap_pct": gap_pct, "atr14": a, "entry": entry,
        "sl": invalidation_level, "trigger": (
            f"Buy only on a limit entry at/under {entry:.2f}; base holds below "
            f"rolling resistance {resistance:.2f}, pullback volume stays dry, "
            "and price closes above the prior day's high"
        ),
        "invalidation": (
            f"Daily close below dynamic support {invalidation_level:.2f}, "
            "or a confirmed breakout failure"
        ),
        "relative_strength_20d": rs, "volume_dry_ratio": dry_ratio,
        "up_down_volume_ratio": ud_ratio, "sector_return": sector_return,
        "base_width_pct": base_width,
    }


def scan_prebreakout(daily_by_symbol, vn30, regime,
                     catalyst_symbols: Iterable[str] = ()):
    """Score the DS1 universe. No candidate can pass with missing sector data."""
    sector_returns = _sector_returns(daily_by_symbol)
    catalysts = {str(s).upper() for s in catalyst_symbols}
    results = []
    for symbol, daily in daily_by_symbol.items():
        sector = _sector_for(symbol)
        sector_return = sector_returns.get(sector) if sector else None
        results.append(score_prebreakout(
            symbol, daily, vn30, regime, sector_return,
            catalyst=symbol in catalysts))
    return sorted(results, key=lambda row: row["score"], reverse=True)
