#!/usr/bin/env python3
"""Independent DS1 v2 paper-first pipeline. Never places orders."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from scripts import ds1_watch as v1

ROOT = Path("data/ds1_v2")
ALLOWED = {
    "S1 Stock Swing Trading": {"TREND_UP", "RANGE"},
    "S2 Mean Reversion": {"RANGE"},
    "S3 Breakout Momentum": {"TREND_UP"},
    "S4 Pullback Trend Following": {"TREND_UP"},
    "S5 VCP Breakout": {"TREND_UP"},
}


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temp.replace(path)


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


def parse_manifest(payload, now):
    """Normalized discovery contract; do not guess undocumented DNSE schemas."""
    created = datetime.fromisoformat(payload["generated_at"])
    if created.tzinfo is None or not 0 <= (now - created).total_seconds() <= 86400:
        raise ValueError("universe manifest stale or future")
    sessions = sorted({date.fromisoformat(d) for d in payload["trading_dates"]})
    if now.date() not in sessions:
        raise ValueError("today is not a verified trading date")
    previous = [d for d in sessions if d < now.date()]
    if not previous:
        raise ValueError("previous trading date missing")
    symbols = {}
    excluded = []
    for row in payload["instruments"]:
        symbol, exchange = row.get("symbol", ""), row.get("exchange")
        if (re.fullmatch(r"[A-Z][A-Z0-9]{2}", symbol) and symbol != "VTP"
                and exchange in {"HOSE", "HNX", "UPCOM"}
                and row.get("type") == "STOCK" and row.get("active") is True):
            if symbol in symbols and symbols[symbol] != exchange:
                raise ValueError("conflicting symbol exchange")
            symbols[symbol] = exchange
        else:
            excluded.append(symbol)
    if not symbols or set(symbols.values()) != {"HOSE", "HNX", "UPCOM"}:
        raise ValueError("universe must cover all three exchanges")
    if payload.get("complete") is not True or not payload.get("source"):
        raise ValueError("universe completeness/source not declared")
    return symbols, previous[-1], excluded


def discover(client, now):
    """Public board discovery, verified response shape on 2026-10-08.

    Three-character tickers are provisional equity candidates; OHLCV validation
    follows. Independent security-type and holiday-calendar checks remain a
    live gate, so this source is paper-only.
    """
    rows = []
    counts = {}
    for exchange in ("HOSE", "HNX", "UPCOM"):
        data = client.get("https://services.entrade.com.vn/chart-api/symbols", {"type": exchange})
        symbols = data.get("symbols") if isinstance(data, dict) else None
        if not isinstance(symbols, list) or not symbols or any(not isinstance(s, str) for s in symbols):
            raise ValueError("invalid exchange symbol response")
        counts[exchange] = len(symbols)
        rows.extend({"symbol": s, "exchange": exchange, "type": "STOCK", "active": True} for s in symbols)
    previous = now.date() - timedelta(days=1)
    while previous.weekday() >= 5:
        previous -= timedelta(days=1)
    return {"generated_at": now.isoformat(), "source": "DNSE public board /chart-api/symbols",
            "complete": True, "trading_dates": [str(previous), str(now.date())],
            "instruments": rows, "board_counts": counts, "calendar_verified": False,
            "security_types_verified": False}


def completed_daily(bars, now, previous):
    result = [b for b in bars if datetime.fromtimestamp(b["t"], v1.VN_TZ).date() < now.date()]
    if len(result) < 60:
        raise ValueError("INSUFFICIENT_DATA: need 60 completed daily bars")
    if datetime.fromtimestamp(result[-1]["t"], v1.VN_TZ).date() != previous:
        raise ValueError("STALE: latest daily bar does not match previous trading date")
    return result


def legacy_input(completed):
    # v1 strategies drop their last element unconditionally. Append a sentinel
    # so every genuine completed bar remains available without modifying v1.
    return completed + [dict(completed[-1])]


def daily_screen(daily):
    """Conservative superset of daily prerequisites; no new strategy thresholds."""
    padded = legacy_input(daily)
    probe = [dict(daily[-1]) for _ in range(10)]
    probe[-2]["c"] = daily[-1]["c"]
    if any((v1.detect_s1(padded, probe, 0), v1.detect_s2(padded, probe, 0),
            v1.detect_s4(padded, probe))):
        return True
    # S3 has no daily trend prerequisite: retain all symbols with valid history.
    # S5 is therefore also retained; narrower liquidity filters require approval.
    return len(daily) >= 60 and sum(b["v"] for b in daily[-20:]) > 0


def evaluate(daily, intraday, benchmark, now, regime):
    closed = [b for b in intraday if b["t"] + 60 <= now.timestamp()
              and datetime.fromtimestamp(b["t"], v1.VN_TZ).date() == now.date()]
    item = {"status": "INSUFFICIENT_DATA", "block_reasons": []}
    if not closed:
        return item
    item["last_closed_1m_bar"] = v1.snapshot_bar(closed[-1])
    age = now.timestamp() - closed[-1]["t"] - 60
    item["closed_bar_age_seconds"] = age
    if not 0 <= age <= 240:
        item.update(status="STALE", block_reasons=["intraday stale"])
        return item
    if len(closed) < 9:
        return item
    d, i, vn = legacy_input(daily), legacy_input(closed), legacy_input(benchmark)
    vr = v1.volume_ratio(closed, d, now)
    rs = v1.relative_strength(d, vn)
    candidates = [v1.detect_s5(d, i, vr), v1.detect_s3(d, i, vr),
                  v1.detect_s4(d, i), v1.detect_s1(d, i, vr), v1.detect_s2(d, i, vr)]
    signal = next((s for s in candidates if s), None)
    item.update(volume_ratio=vr, relative_strength_20d_vs_vn30=rs)
    if signal is None:
        item["status"] = "NO_SETUP"
        return item
    risk = v1.risk_engine(signal["price"], signal["level"], d, signal["strategy"])
    score, parts = v1.score_signal(d, vr, rs, signal["strategy"], risk)
    blocked = []
    if regime not in ALLOWED[signal["strategy"]]:
        blocked.append("market regime not allowed")
    if score < v1.MIN_SCORE:
        blocked.append("score below 75")
    if not risk or risk["rr"] < v1.MIN_RR:
        blocked.append("risk engine failed or RR below 2")
    item.update(status="BLOCKED" if blocked else "PAPER_VALIDATED", strategy=signal["strategy"],
                trigger=signal["trigger"], score=score, score_parts=parts, risk=risk, block_reasons=blocked)
    return item


class Ledger:
    """Durable at-most-once reservation. Ambiguous sends require manual review."""
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS alerts (key TEXT PRIMARY KEY, status TEXT, message_id INTEGER)")
        self.db.commit()

    def reserve(self, key):
        try:
            with self.db:
                self.db.execute("INSERT INTO alerts VALUES (?, 'PENDING', NULL)", (key,))
            return True
        except sqlite3.IntegrityError:
            return False

    def sent(self, key, message_id):
        with self.db:
            self.db.execute("UPDATE alerts SET status='ALERTED', message_id=? WHERE key=?", (message_id, key))

    def close(self):
        self.db.close()


class GitHubLedger:
    """Commit reservation BEFORE Telegram; survives runner termination/cache loss."""
    branch = "ds1-v2-alert-state"

    def __init__(self, repository, token, session=None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("invalid ledger repository")
        self.base = f"https://api.github.com/repos/{repository}"
        self.session = session or requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        self.reservations = {}
        response = self.session.get(self.base + f"/git/ref/heads/{self.branch}", timeout=20)
        if response.status_code == 404:
            main = self.session.get(self.base + "/git/ref/heads/main", timeout=20)
            main.raise_for_status()
            created = self.session.post(self.base + "/git/refs", json={"ref": f"refs/heads/{self.branch}",
                                       "sha": main.json()["object"]["sha"]}, timeout=20)
            if created.status_code != 201:
                # A concurrent initializer may already have created the branch.
                check = self.session.get(self.base + f"/git/ref/heads/{self.branch}", timeout=20)
                check.raise_for_status()
        else:
            response.raise_for_status()

    def reserve(self, key):
        path = "data/ds1_v2_reservations/" + hashlib.sha256(key.encode()).hexdigest() + ".json"
        url = self.base + "/contents/" + path
        existing = self.session.get(url, params={"ref": self.branch}, timeout=20)
        if existing.status_code == 200:
            return False
        if existing.status_code != 404:
            raise RuntimeError("remote ledger cannot be read")
        value = base64.b64encode(json.dumps({"key": key, "status": "PENDING"}).encode()).decode()
        result = self.session.put(url, json={"message": "Reserve DS1 v2 alert", "branch": self.branch,
                                  "content": value}, timeout=20)
        if result.status_code != 201:
            # No Telegram on ambiguity or concurrent reservation conflict.
            raise RuntimeError("remote reservation not acknowledged")
        self.reservations[key] = (url, result.json()["content"]["sha"])
        return True

    def sent(self, key, message_id):
        url, sha = self.reservations[key]
        value = base64.b64encode(json.dumps({"key": key, "status": "ALERTED", "message_id": message_id}).encode()).decode()
        result = self.session.put(url, json={"message": "Acknowledge DS1 v2 alert", "branch": self.branch,
                                  "sha": sha, "content": value}, timeout=20)
        if result.status_code != 200:
            raise RuntimeError("remote acknowledgement failed; reservation retained")

    def close(self):
        self.session.close()


def send_alert(symbol, item, now, ledger, session=None):
    key = f"{now.date()}|{symbol}|{item['strategy']}"
    if not ledger.reserve(key):
        return "DUPLICATE_SUPPRESSED"
    risk = item["risk"]
    message = (f"DS1 v2 BUY — {symbol}\n{item['strategy']} | Score {item['score']}/100\n"
               f"Entry {risk['entry']:.2f} VND | SL {risk['sl']:.2f}\n"
               f"TP1 {risk['tp1']:.2f} | TP2 {risk['tp2']:.2f} | R {risk['rr']:.2f}\n"
               f"Size {risk['shares']} cp | Risk {risk['risk_vnd']:.0f} VND\n"
               f"{item['trigger']}\nBar {item['last_closed_1m_bar']['bar_time']}\n"
               "Quyết định giao dịch cuối cùng do người dùng thực hiện.")
    try:
        response = (session or requests).post(
            f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
            json={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": message}, timeout=(5, 20))
        response.raise_for_status()
        payload = response.json()
        message_id = payload.get("result", {}).get("message_id")
        if payload.get("ok") is not True or not isinstance(message_id, int):
            raise ValueError("Telegram did not acknowledge message")
        ledger.sent(key, message_id)
        item["telegram_message_id"] = message_id
        return "ALERTED"
    except Exception:
        # Do not log requests exception URLs, which contain the bot token.
        item["error"] = "Telegram delivery uncertain; reservation retained for manual review"
        return "ERROR"


def run(args, client=None, now=None):
    now = now or datetime.now(v1.VN_TZ)
    client = client or Client(args.interval)
    snapshot = {"schema_version": 2, "generated_at": now.isoformat(), "mode": args.mode,
                "price_unit": "VND", "price_type": "completed_1m_ohlcv_close_not_tick",
                "status": "INITIALIZING", "symbols": {}, "alerts_sent": 0}
    ledger = None
    started = time.monotonic()
    try:
        if now.weekday() >= 5 or not v1.in_session(now):
            snapshot["status"] = "OUT_OF_SESSION"
            return 0
        if args.universe_url:
            payload = client.get(args.universe_url)
        elif args.universe_file:
            payload = json.loads(Path(args.universe_file).read_text(encoding="utf-8"))
        else:
            payload = discover(client, now)
        symbols, previous, excluded = parse_manifest(payload, now)
        snapshot.update(universe_source=payload["source"], universe_count=len(symbols),
                        excluded=excluded, previous_trading_date=str(previous),
                        calendar_verified=payload.get("calendar_verified", False),
                        security_types_verified=payload.get("security_types_verified", False))
        # Production requires explicit operational validation, never inferred from CI.
        if args.mode == "live" and os.environ.get("DS1_V2_VALIDATED") != "true":
            raise ValueError("live requires DS1_V2_VALIDATED=true after operational validation")
        if args.mode == "live" and (payload.get("calendar_verified") is not True or payload.get("security_types_verified") is not True):
            raise ValueError("live requires independently verified calendar and security types")
        if args.mode == "live" and not all(os.environ.get(k) for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")):
            raise ValueError("Telegram configuration missing")
        benchmark = completed_daily(client.ohlcv("VN30", "1D", now), now, previous)
        regime = v1.market_regime(legacy_input(benchmark))
        snapshot["market_regime"] = regime
        cache_path = ROOT / "daily_cache.json"
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
        if cache.get("date") != str(now.date()) or cache.get("source") != payload["source"]:
            cache = {"date": str(now.date()), "source": payload["source"], "symbols": {}}
        candidates = []
        for symbol, exchange in sorted(symbols.items()):
            item = {"exchange": exchange, "status": "FETCHING"}
            snapshot["symbols"][symbol] = item
            try:
                raw = cache["symbols"].get(symbol)
                if raw is None:
                    raw = client.ohlcv(symbol, "1D", now)
                    cache["symbols"][symbol] = raw
                daily = completed_daily(raw, now, previous)
                item["last_daily_bar"] = v1.snapshot_bar(daily[-1])
                if daily_screen(daily):
                    candidates.append((symbol, daily))
                else:
                    item["status"] = "NO_SETUP"
            except ValueError as exc:
                item.update(status="STALE" if str(exc).startswith("STALE") else "INSUFFICIENT_DATA", error=str(exc))
            except Exception:
                item.update(status="ERROR", error="daily fetch failed")
        atomic_json(cache_path, cache)
        snapshot["candidate_count"] = len(candidates)
        if args.mode == "live":
            if os.environ.get("GITHUB_ACTIONS") == "true":
                ledger = GitHubLedger(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
            else:
                ledger = Ledger(ROOT / "alerts.sqlite3")
        for symbol, daily in candidates:
            item = snapshot["symbols"][symbol]
            try:
                # Fetch time is used for freshness, not the beginning of a long full-market scan.
                scan_now = datetime.now(v1.VN_TZ) if args.clock_live else now
                if not v1.in_session(scan_now) or scan_now.date() != now.date():
                    item.update(status="BLOCKED", block_reasons=["session ended during scan"])
                    continue
                intraday = client.ohlcv(symbol, "1", scan_now)
                # A slow request/retry must not freeze freshness at request start.
                scan_now = datetime.now(v1.VN_TZ) if args.clock_live else now
                if not v1.in_session(scan_now) or scan_now.date() != now.date():
                    item.update(status="BLOCKED", block_reasons=["session ended during fetch"])
                    continue
                item.update(evaluate(daily, intraday, benchmark, scan_now, regime))
                item["market_regime"] = regime
                if item["status"] == "PAPER_VALIDATED" and ledger:
                    item["status"] = send_alert(symbol, item, scan_now, ledger)
                    snapshot["alerts_sent"] += item["status"] == "ALERTED"
            except Exception:
                item.update(status="ERROR", error="intraday evaluation failed")
            ROOT.mkdir(parents=True, exist_ok=True)
            with (ROOT / "history.jsonl").open("a", encoding="utf-8") as output:
                output.write(json.dumps({"timestamp": now.isoformat(), "symbol": symbol, **item}, allow_nan=False) + "\n")
        snapshot["status"] = "PARTIAL_ERROR" if any(i["status"] == "ERROR" for i in snapshot["symbols"].values()) else "COMPLETE"
        return 1 if snapshot["status"] == "PARTIAL_ERROR" else 0
    except Exception as exc:
        snapshot.update(status="BLOCKED", error=str(exc) if isinstance(exc, ValueError) else "pipeline initialization failed")
        return 1
    finally:
        if ledger:
            ledger.close()
        snapshot.update(finished_at=datetime.now(v1.VN_TZ).isoformat(), elapsed_seconds=time.monotonic()-started,
                        request_metrics=client.metrics)
        atomic_json(ROOT / "latest_snapshot.json", snapshot)


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--universe-url")
    source.add_argument("--universe-file")
    parser.add_argument("--mode", choices=("paper", "live"), default="paper")
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    args.clock_live = True
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())

