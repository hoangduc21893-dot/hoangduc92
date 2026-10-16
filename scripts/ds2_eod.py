"""Read-only DS2 valuation. DNSE chart stock 1D only; no broker/order imports."""
import argparse
from datetime import date, datetime, time as dt_time, timedelta
from decimal import Decimal
import json
from pathlib import Path
import time
from zoneinfo import ZoneInfo

import requests

ICT = ZoneInfo('Asia/Ho_Chi_Minh')
URL = 'https://services.entrade.com.vn/chart-api/v2/ohlcs/stock'
HOLDINGS = {'PVT': (1000, 23230), 'DGW': (700, 45750), 'DCM': (500, 34400)}
# Published exchange calendar; unknown years fail closed until reviewed.
# https://www.hsx.vn/vi/tin-tuc/hose-thong-bao-lich-nghi-giao-dich-nam-2026/2437411
HOLIDAYS = {'2026-01-01', '2026-01-02', '2026-02-16', '2026-02-17',
            '2026-02-18', '2026-02-19', '2026-02-20', '2026-04-27',
            '2026-04-30', '2026-05-01', '2026-08-31', '2026-09-01', '2026-09-02'}


def trading_day(day):
    if day.year != 2026:
        raise ValueError('calendar coverage expired: review exchange calendar')
    return day.weekday() < 5 and day.isoformat() not in HOLIDAYS


def get_payload(symbol, day, session, sleep=time.sleep):
    start = datetime.combine(day, dt_time(), ICT)
    params = {'symbol': symbol, 'resolution': '1D',
              'from': int(start.timestamp()),
              'to': int((start + timedelta(days=1)).timestamp()) - 1}
    for attempt in range(3):
        try:
            response = session.get(URL, params=params, timeout=(5, 20), headers={
                'User-Agent': 'Mozilla/5.0', 'Origin': 'https://www.dnse.com.vn',
                'Referer': 'https://www.dnse.com.vn/'})
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.ConnectionError('retryable DNSE response')
            response.raise_for_status()
            return response.json()
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 2:
                raise RuntimeError(f'{symbol}: DNSE transport/retry exhausted') from None
            sleep(2 ** attempt)
        except (requests.RequestException, ValueError):
            raise RuntimeError(f'{symbol}: DNSE HTTP/JSON failure') from None


def closed_bar(payload, day):
    if not isinstance(payload, dict) or payload.get('s') not in (None, 'ok'):
        raise ValueError('DNSE error envelope')
    arrays = [payload.get(k) for k in 'tohlcv']
    if any(not isinstance(a, list) for a in arrays) or len({len(a) for a in arrays}) != 1:
        raise ValueError('missing/unequal OHLCV arrays')
    selected = []
    previous = None
    for row in zip(*arrays):
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in row):
            raise ValueError('OHLCV must be numeric')
        values = [Decimal(str(v)) for v in row]
        if not all(v.is_finite() for v in values):
            raise ValueError('nonfinite OHLCV')
        stamp, o, h, l, c, volume = values
        if not 946684800 <= stamp <= 4102444800 or stamp != int(stamp) or (previous is not None and stamp <= previous):
            raise ValueError('duplicate/unordered timestamps')
        previous = stamp
        if not 0 < l <= min(o, c) <= max(o, c) <= h or volume <= 0 or volume != int(volume):
            raise ValueError('invalid OHLCV bounds/volume')
        # Chart endpoint contract is thousand VND, never infer units by magnitude.
        prices = [v * 1000 for v in (o, h, l, c)]
        if any(v != int(v) or v < 1000 or v > 1000000 for v in prices):
            raise ValueError('unexpected stock price scale')
        bar_day = datetime.fromtimestamp(int(stamp), ICT).date()
        if bar_day > day:
            raise ValueError('future bar')
        if bar_day == day:
            selected.append({'timestamp': int(stamp), 'close_vnd': int(prices[-1]),
                             'volume': int(volume)})
    if len(selected) != 1:
        raise ValueError('missing/stale/duplicate target daily bar')
    return selected[0]


def collect(day, now, session):
    if now.tzinfo is None:
        raise ValueError('timezone-aware clock required')
    now = now.astimezone(ICT)
    if day > now.date() or (day == now.date() and now.time() < dt_time(16, 10)):
        raise ValueError('EOD not closed: require 16:10 ICT or later')
    if not trading_day(day):
        return {'status': 'NON_TRADING_DAY', 'date': str(day)}
    rows = []
    for symbol, (quantity, cost) in HOLDINGS.items():
        bar = closed_bar(get_payload(symbol, day, session), day)
        value = quantity * bar['close_vnd']
        basis = quantity * cost
        rows.append({'symbol': symbol, 'quantity': quantity, 'cost_vnd': cost,
                     **bar, 'market_value_vnd': value, 'cost_basis_vnd': basis,
                     'pnl_vnd': value - basis,
                     'pnl_pct': round((value - basis) / basis * 100, 6)})
    nav = sum(r['market_value_vnd'] for r in rows)
    basis = sum(r['cost_basis_vnd'] for r in rows)
    return {'status': 'VERIFIED_EOD', 'date': str(day), 'source': URL,
            'resolution': '1D', 'currency': 'VND', 'price_multiplier': 1000,
            'collected_at': now.isoformat(), 'positions': rows,
            'nav_vnd': nav, 'cost_basis_vnd': basis, 'pnl_vnd': nav - basis,
            'pnl_pct': round((nav - basis) / basis * 100, 6),
            'nav_scope': 'holdings only; cash, fees, taxes and dividends excluded'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', type=date.fromisoformat)
    parser.add_argument('--output', type=Path, default=Path('data/ds2'))
    args = parser.parse_args()
    now = datetime.now(ICT)
    day = args.date or now.date()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / f'{day}.json'
    # A failed rerun must never leave an old success at the expected output path.
    target.unlink(missing_ok=True)
    try:
        with requests.Session() as session:
            report = collect(day, now, session)
    except Exception as exc:
        report = {'status': 'ERROR', 'date': str(day), 'error': str(exc)}
        target.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report))
        raise SystemExit(1) from None
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(report, indent=2), encoding='utf-8')
    temp.replace(target)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
