# DS1 Market-Wide v2 — testable implementation, not production-ready

This module/workflow is independent of DS1 v1 and VN30F1M. Existing strategy
functions, priority, allowed regimes, score 75, RR 2, NAV 100m VND, risk 400k
VND, maximum position 20%, and 100-share sizing are reused unchanged. VTP is
excluded. No order-placement API exists in v2.

## Run

```
python -m pip install requests tzdata
python -m unittest -v test_ds1_market_wide test_ds1_snapshot
python -m scripts.ds1_market_wide --mode paper
```

Use the manually dispatched `DS1 Market-Wide v2 Paper Validation` workflow
after merge, or dispatch its branch for validation. No schedule is enabled and
no Telegram secrets are supplied to this workflow. A dispatch outside the v1
session window writes OUT_OF_SESSION without fetching market data.

## Data and discovery evidence (2026-10-08)

DNSE's own public board JavaScript calls `/symbols?type=...` on chart-api.
Read-only probes of `https://services.entrade.com.vn/chart-api/symbols` returned
769 HOSE, 299 HNX, 817 UPCOM entries. Three-character alphanumeric candidates
yielded 1,521 symbols after VTP exclusion, including GVR and MSN. Longer symbols
(including warrants and funds) are excluded. This heuristic does not prove
security type, listing status, completeness against exchange registers, or
suspension status. Those checks are mandatory before live activation.

PVT daily chart probe returned close 25.55, volume 13,543,600. Chart prices are
converted from thousand VND to VND before strategy/risk evaluation. The probe
does not establish all endpoints' timeliness or intraday behavior. The last
bar is retained if its exchange-local date precedes today; freshness requires
the expected prior session. Intraday bars are closed only when timestamp+60
seconds <= evaluation time, and latest close age must be <=240 seconds.

Public discovery uses the previous weekday as a conservative paper calendar.
After holidays it can block fresh data; it never silently relaxes daily age.
Live requires an independently verified trading calendar and security types.

Official references:
- https://developers.dnse.com.vn/docs/dnse/get-instruments/
- https://developers.dnse.com.vn/docs/dnse/get-market-working-dates/
- https://hdsd.dnse.com.vn/die-u-khoa-n-di-ch-vu-dnse/dieu-khoan-san-pham-dich-vu/dieu-khoan-san-pham-lightspeed-api

Provider rate limits for the public chart endpoint remain unverified. Default
pacing is one sequential request/second, timeout 5s connect/20s read, at most
three attempts for transport/429/5xx. This is an internal limit, not a claim of
DNSE permission or quota. Requests are processed sequentially without fanout.

## Pipeline and scale limits

Discovery -> daily validation/cache -> daily pre-screen -> intraday confirmation
-> original S1–S5/risk -> paper history or verified live alert.

Daily cache is keyed by Vietnam date and source; every cached symbol is still
checked against the prior session. Per-symbol errors do not terminate the scan.
Malformed/unequal arrays, nonfinite prices, negative volume, invalid OHLC,
duplicate and unordered timestamps are rejected. Benchmark failure blocks all
signals. Snapshot includes source, counts, bar timestamps, statuses, risks,
request/retry counts and elapsed time. PAPER_VALIDATED means a signal passed
the current filters; it is not an outcome/performance backtest.

S3 has no daily trend prerequisite, so the conservative pre-screen retains
essentially all symbols with sufficient history and positive recent volume.
This avoids inventing new strategy thresholds but does NOT yet solve the
intraday request load. At 1,521 candidates, one-second pacing means at least
25 minutes per intraday sweep and over 50 minutes for a cold daily+intraday
pass, before retries. A new five-minute market-wide schedule is therefore NOT
enabled. A tighter approved pre-screen, validated batching or streaming input,
and measured in-session load are required before production scheduling.

## Verified manifest contract / live gate

Optional `--universe-file manifest.json` or `--universe-url https://...` consumes:

```json
{
  "generated_at": "2026-10-08T09:00:00+07:00",
  "source": "verified provider/export identity",
  "complete": true,
  "calendar_verified": true,
  "security_types_verified": true,
  "trading_dates": ["2026-10-07", "2026-10-08"],
  "instruments": [
    {"symbol": "AAA", "exchange": "HOSE", "type": "STOCK", "active": true},
    {"symbol": "BBB", "exchange": "HNX", "type": "STOCK", "active": true},
    {"symbol": "CCC", "exchange": "UPCOM", "type": "STOCK", "active": true}
  ]
}
```

The example is a schema fixture, not real market discovery. Production adapters
must normalize actual DNSE instruments and working-dates responses including
pagination, type/status mapping and completeness evidence. Manifest age must
be <=24h, today must be a trading date, all three exchanges must be present.

`--mode live` additionally requires `DS1_V2_VALIDATED=true`, real Telegram
credentials, and the verified manifest. Setting the flag alone is not proof
of operational validation. The supplied workflow intentionally supports paper
only. Build the scheduled live workflow only after the checklist below passes.

Local live state uses a SQLite ledger on durable local storage. On GitHub
Actions it uses the GitHub Contents API with `GITHUB_TOKEN`, contents:write,
and `GITHUB_REPOSITORY`. Reservations are committed before sending on the
separate `ds1-v2-alert-state` branch; all scanner workflows must share that
branch. Existing reservation suppresses repeat delivery even after runner
termination. Telegram requires HTTP success plus `ok=true` and message_id.
Ambiguous delivery remains PENDING and is never automatically retried. Inspect
Telegram and ledger manually; do not clear reservations merely to rerun. This
provides at-most-once attempts, not guaranteed delivery. Protect/preserve the
state branch and do not delete/rewrite it. No state-branch write occurs in paper.

## Before production

1. Verify instruments classification, completeness, delisted/suspended handling
   and holiday calendar from actual provider data.
2. Confirm DNSE quota and measure full-universe request counts/latency; resolve
   intraday sweep duration without modifying strategy thresholds implicitly.
3. Validate fresh completed daily/intraday bars across HOSE/HNX/UPCOM and VN30.
4. Run in-session paper scans and inspect excluded/error/stale counts; record
   representative setups and manual false-positive assessment.
5. Validate remote ledger contention, permission failures and runner termination.
6. Verify Telegram delivery in the intended chat and retain its message_id;
   never fabricate a BUY solely for testing.
7. Only then add a separately reviewed schedule/live workflow. Do not call this
   release production-ready based on offline CI alone.


## Pre-breakout priority (paper-only)

Before intraday scanning, completed daily bars now produce a transparent 0–100 **WATCH priority** from MA20>MA50 and close>=MA20 (30), price within 5% below 20-session resistance (30), contraction of 10-day ranges (20), and contraction of 10-day volume (20). Candidates are processed in priority order. `pre_breakout_watchlist` in the snapshot contains at most 50 WATCH candidates for review. This prioritization does not bypass S1–S5, change the risk/score gate, or emit BUY. It does not claim calibrated predictive performance and does not solve total-universe runtime; same request count is required for a full scan. No live schedule or Telegram permissions are enabled.

## Paper workflow schedule (proposed, inactive until merge)

The workflow has weekday UTC cron entries at 02:20 and 06:10 (09:20/13:10 Vietnam time). GitHub schedules execute only on the default branch, so while PR #6 remains Draft these schedules do **not** run. Manual workflow_dispatch on the PR branch is available for isolated validation; no Telegram credentials are passed and the scanner is fixed to `--mode paper`. `contents: read` only. PR validation runs offline tests and does not scan live markets. Weekdays are not equivalent to exchange trading days: the scanner's session/date checks and source validation must be reviewed for holidays. GitHub cron can start late or skip under load, and long requests may run past the trading session; freshness gates must fail closed. Merge only after in-session data, quotas and pacing are verified; do not enable a production paper schedule by inference from CI success.
