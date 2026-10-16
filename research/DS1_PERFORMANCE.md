# DS1 DNSE Performance Collector

Read-only, separate from all trading and Telegram workflows. Runs at 09:10 UTC
(16:10 Vietnam), weekdays with the existing DS2 2026 exchange calendar gate.
GitHub schedules may start late. Unknown calendar years fail closed.

Run: `python -m scripts.ds1_performance --date 2026-10-16`.
Omit date for latest completed exchange session (16:10 local cutoff).
All entries use the closing DNSE stock 1D bar of the configured session;
non-trading entry dates advance to the next exchange session. 10 October becomes
12 October 2026. T+ counts exchange sessions strictly after entry, entry = T+0;
it is an elapsed-session measure, not settlement availability.

Reuses DS2 transport, calendar, exact-date OHLCV validation and thousand-VND
conversion. Each response is archived with query session, collection timestamp,
source and SHA256. No forward fill, nearest-bar lookup or substitute feed.
Failures retain diagnostic JSON, CSV, Markdown and available raw responses.
Old output is cleared before reruns. Missing or inconsistent data exits nonzero.

The DNSE chart response alone does not prove adjustment basis. Prices may be
reported as validated observations while returns, outcomes and portfolio
statistics remain null. HDB and GMD always carry corporate-action warnings.
No dividend/share multiplier is ever applied by this code.

For independently reviewed evidence, pass `--basis-evidence evidence.json`.
Each symbol must map to source (exact endpoint), resolution `1D`, start/end ISO
dates, payload_sha256 (ordered start/end response digests), basis
`same_adjusted_basis`, evidence_url (HTTPS supporting document), reviewed_by and
explanation. The reviewer must establish that both observed closes are on the
same adjusted basis, including HDB/GMD actions; the program validates binding
and fields, not the truth of the external document. Do not fabricate evidence.
No evidence file is supplied or implicitly trusted. A BLOCKED smoke is expected
until evidence exists; it must not be relabeled as verified.

Only 20/20 validated prices AND bound basis evidence release equal-weight mean,
win/loss/flat counts and top/bottom three. Return = (end/start - 1)*100,
close-to-close price return, excluding fees, taxes and cash dividends. This is
not a cash-flow or total-return portfolio valuation.

Artifacts: report.json, report.csv, report.md, raw/*.json. Unit tests use synthetic
fixtures only; fixture values are not market evidence.
