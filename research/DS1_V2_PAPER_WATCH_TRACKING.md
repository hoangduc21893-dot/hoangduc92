# DS1 V2 Paper Watch — 20–30 session validation protocol

Status: RESEARCH_ONLY. Operational start is the FIRST successful scheduled main-branch snapshot (not the initial historical smoke test).

- Daily schedule: 16:10 Asia/Ho_Chi_Minh on weekdays. GitHub cron is best-effort; late/missed runs must be reported.
- Each completed session saves one JSON artifact containing as-of date, 20 DS1 scores, candidate flag, close, pivot, gates, and machine-readable validation state.
- GVR must never be a candidate. No orders, BUY labels, or Telegram tokens.
- Collect at least 20, preferably 30, unique trading sessions. Failed, stale, holiday, or incomplete snapshots DO NOT count.
- Signals: score >=70, with trend, pivot and liquidity gates satisfied; missing market/sector context remains unverified.
- At horizons 5, 10, 20 completed market sessions, independently compute forward returns from DNSE closing daily bars, event-label availability and cohort win rate. Use next-session open only for any tradable-entry simulation; account for costs separately.
- Track count of WATCH, average post-WATCH return, positive-return fraction, breakout follow-through (requires frozen numeric definition), and unresolved data anomalies. Do not report false-breakout rates without a pre-registered definition.
- Retain artifacts for 90 days; download/archive elsewhere before expiry. GitHub artifacts do NOT form a permanent database.
- Do not claim V2 beats V1, enable production BUY or merge unvalidated research modules without a proper walk-forward audit.
- The historical 2026-10-14 smoke test and research data are NOT part of the 20–30 new paper-validation trading days.

Acceptance: 20–30 valid distinct daily records, reconciled data dates, reproducible forward outcome calculations, zero production side effects.
