# S4 EOD research 2026-10-21

Research only; DS1 unchanged; no BUY.

Literal repo S4 daily contraction <=1.10*inclusive ADV20 retained; user volume >=1.5*prior ADV20 retained. These same-day gates are incompatible. Intraday confirmation is outside this 1D WATCH audit, never claimed.

Score = trend (25 if close>MA20>MA50, 10 if MA20>MA50, else 0) + near MA20 within 1.5% (25) + bullish body (10) + higher close (10) + VR>=1.5 (15) + RS20 (15 if >=5pp, 10 if >=2pp, 5 if >=0, else 0). Score >=80 AND all S4 gates AND VR>=1.5 required. No threshold optimized after results.

RS20 = stock 20-session return minus VNINDEX return on exactly matching endpoint dates. Wilder RSI/ATR seeded from first 14 changes/TRs. MA includes target EOD. VR excludes target from prior20 denominator. Pivot/base = prior20 high/low, descriptive, not a certified pattern. Liquidity = mean20(close*volume), proxy only.

Rights/adjustment basis UNVERIFIED; metrics provisional. No adjustment applied. Calendar: existing scripts/ds2_eod.py 2026 holiday list. Missing/extra weekdays fail closed.

|Rank|Symbol|Status|Close VND|MA20|MA50|RSI14|RS20 pp|ATR14 VND|VR|Score|
|---|---|---|---|---|---|---|---|---|---|---|
|1|KDH|FAIL|14850.0000|13842.0000|14907.8000|62.0682|6.5491|450.4934|2.7356|50.0000|
|2|TPB|FAIL|12650.0000|11946.5000|12049.2000|68.6675|5.6766|320.8943|2.6049|50.0000|
|3|NLG|FAIL|22850.0000|21805.0000|23094.0000|57.1785|1.9871|631.7504|1.9733|40.0000|
|4|SSI|FAIL|20400.0000|19730.0000|20260.8000|58.9244|1.3374|521.1909|1.7001|40.0000|
|5|VCI|FAIL|19700.0000|19075.0000|20411.0000|53.2188|1.0204|655.6232|1.4561|25.0000|

KDH: {"technical_failures": ["ma20_above_ma50", "near_ma20_1_5pct", "s4_volume_contraction", "watch_score_80"], "blockers": ["corporate-action calendar and provider adjustment basis not certified"], "pivot_prior20_high_vnd": 14590.0, "base_prior20_low_vnd": 13000, "avg20_daily_close_times_volume_vnd": 57166282550.0, "large_gaps_gt7pct": []}

TPB: {"technical_failures": ["ma20_above_ma50", "near_ma20_1_5pct", "s4_volume_contraction", "watch_score_80"], "blockers": ["corporate-action calendar and provider adjustment basis not certified"], "pivot_prior20_high_vnd": 12460.0, "base_prior20_low_vnd": 11250.0, "avg20_daily_close_times_volume_vnd": 123667498800.0, "large_gaps_gt7pct": []}

NLG: {"technical_failures": ["ma20_above_ma50", "near_ma20_1_5pct", "s4_volume_contraction", "watch_score_80"], "blockers": ["corporate-action calendar and provider adjustment basis not certified"], "pivot_prior20_high_vnd": 23900.0, "base_prior20_low_vnd": 21000, "avg20_daily_close_times_volume_vnd": 31644400750.0, "large_gaps_gt7pct": []}

SSI: {"technical_failures": ["ma20_above_ma50", "near_ma20_1_5pct", "s4_volume_contraction", "watch_score_80"], "blockers": ["corporate-action calendar and provider adjustment basis not certified"], "pivot_prior20_high_vnd": 21200.0, "base_prior20_low_vnd": 18650.0, "avg20_daily_close_times_volume_vnd": 385609154500.0, "large_gaps_gt7pct": []}

VCI: {"technical_failures": ["ma20_above_ma50", "near_ma20_1_5pct", "s4_volume_contraction", "required_volume_ratio_1_5", "watch_score_80"], "blockers": ["corporate-action calendar and provider adjustment basis not certified"], "pivot_prior20_high_vnd": 20600.0, "base_prior20_low_vnd": 18050.0, "avg20_daily_close_times_volume_vnd": 151643739750.0, "large_gaps_gt7pct": []}

No DS1 WATCH additions. See report.json for source URLs, timestamps, validation and all numeric fields. Raw API bytes and SHA256 hashes in evidence/ and manifest.json.

Rights: TPB cash 500 VND and 15% stock dividend, record 2026-10-05, intersects RS20 window; SSI cash 1000 VND, record 2026-08-18. See rights-review.md. TPB RS20 particularly requires adjustment certification.
