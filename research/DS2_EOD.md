# DS2 DNSE EOD

Independent read-only report: PVT 1000 @ 23230, DGW 700 @ 45750,
DCM 500 @ 34400 VND. No production files or workflows changed; no orders,
signals, AI, Telegram or broker credentials used.

Run `python -m unittest -v test_ds2_eod`, then
`python -m scripts.ds2_eod` (or `--date YYYY-MM-DD` for historical audit).
Reports: `data/ds2/YYYY-MM-DD.json`; failure exits 1 and writes ERROR without NAV.
Only a complete set of three exact-date daily bars after 16:10 ICT is valued.
No fallback, cache, previous-session substitution or inferred price units.
NAV represents these holdings only; cash, fees, taxes and dividends excluded.

Endpoint audit 2026-10-16: chart-api/v2/ohlcs/stock returns parallel
t/o/h/l/c/v arrays; resolution=1D, epoch seconds, thousand VND prices.
Live PVT/DGW/DCM closes were 23.65/44.5/33.9 at timestamp 1792116000.
1D history does not carry a closed flag: closure is enforced by exact ICT
session date and the conservative 16:10 ICT time gate. It cannot certify
provider corrections or exceptional exchange closures.

Official newer APIs are documented at
https://developers.dnse.com.vn/docs/dnse/get-ohlc-history/ and
https://developers.dnse.com.vn/docs/dnse/get-market-working-dates/ .
The probed services.entrade.com.vn/market-api/market/working-dates requires
authentication (401); api.dnse.com.vn/market-data/market/working-dates is 404.
No silent switch to an unverified authenticated API.

Weekday Actions cron 09:10 UTC = 16:10 ICT, with runtime 2026 exchange holiday
gate; 2027 fails closed until the calendar is reviewed. Calendar reference:
https://www.hsx.vn/vi/tin-tuc/hose-thong-bao-lich-nghi-giao-dich-nam-2026/2437411
and https://www.dnse.com.vn/nhan-dinh-thi-truong/thong-bao-lich-nghi-giao-dich-chung-khoan-nam-2026 .
Scheduled Actions may start late; a run delayed to a different ICT day cannot
publish the previous day's bars as current. Artifacts are retained 90 days.
Historical smoke on code pushes/PRs; current session on schedule/manual run.
