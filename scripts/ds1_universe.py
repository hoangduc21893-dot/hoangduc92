"""Date-effective DS1 research membership; never represents actual DS2 holdings."""
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PATH = Path(__file__).resolve().parents[1] / "data" / "ds1_watchlist.json"


def _day(asof=None):
    if asof is None:
        return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    return date.fromisoformat(asof) if isinstance(asof, str) else asof


def membership(asof=None):
    day = _day(asof)
    data = json.loads(PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported DS1 watchlist schema")
    versions = data["versions"]
    dates = [date.fromisoformat(v["effective_date"]) for v in versions]
    if dates != sorted(set(dates)):
        raise ValueError("unordered or duplicate membership versions")
    eligible = [v for v, start in zip(versions, dates) if start <= day]
    if not eligible:
        raise ValueError("no DS1 membership for requested date")
    version = eligible[-1]
    members = version["members"]
    names = [m["symbol"] for m in members]
    if not names or len(names) != len(set(names)):
        raise ValueError("empty or duplicate DS1 membership")
    if any(not s.isascii() or not s.isalnum() or s != s.upper() for s in names):
        raise ValueError("invalid DS1 symbol")
    if any(m["status"] not in ("WATCH", "WATCH_RISK") for m in members):
        raise ValueError("DS1 membership is research-only")
    return version["version"], [dict(m) for m in members
                                if date.fromisoformat(m["added_date"]) <= day]


def symbols(asof=None):
    return tuple(m["symbol"] for m in membership(asof)[1])


def risk_symbols(asof=None):
    return tuple(m["symbol"] for m in membership(asof)[1] if m["status"] == "WATCH_RISK")


def performance_config(asof=None):
    return {m["symbol"]: date.fromisoformat(m["added_date"]) for m in membership(asof)[1]}


def watchlist_version(asof=None):
    return membership(asof)[0]
