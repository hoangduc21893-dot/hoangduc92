# DS1 DNSE Performance Collector

Isolated report collector; no trading, orders, broker credentials or Telegram imports.
Schedule: `45 9 * * 1-5` UTC = 16:45 ICT. GitHub may delay scheduled starts.
The 2026 HOSE/HNX/UPCoM exchange holiday gate rejects weekends and holidays;
unknown years fail closed and require a reviewed calendar update before 2027.
Calendar sources:
- https://www.hsx.vn/vi/tin-tuc/hose-thong-bao-lich-nghi-giao-dich-nam-2026/2437411
- https://cms.hnx.vn/vi-vn/chi-tiet-lich-nghi-gd-60021971.html?_page=1

Manual/backfill: Actions > DS1 DNSE Performance Collector > Run workflow, main,
`date=YYYY-MM-DD`. Blank selects latest completed session at 16:45 ICT.
CLI: `python -m scripts.ds1_performance --date 2026-10-20`.
Entry dates are in GROUPS; non-session entries advance to the next trading day.
T+ is elapsed trading sessions after entry, entry=T+0, not settlement availability.

DNSE chart stock 1D is the only price source. Exact target date and 09:00 ICT
bar timestamp, OHLC bounds, finite numeric values, positive integer volume,
and explicit thousand-VND to VND scaling are validated. No fill or fake prices.
Transport: 5 attempts, bounded exponential backoff with jitter, Retry-After
seconds (capped at 120s), connect/read timeouts 5/20s. HTTP/JSON errors fail.

20/20 prices with unverified adjustment basis is successful PRICE_VALIDATED
with a warning and RETURNS_UNVERIFIED. Reference ranking, arithmetic equal-weight
price movement and up/down/flat counts are labeled reference only. Verified
return/outcome statistics stay null unless independent evidence is bound to the
exact start/end payload hashes. Historical entry closes are fetched now, not
archived original entry prices. No manual corporate-action adjustment is applied.
HDB/GMD and every other symbol have UNVERIFIED corporate-action audit status.
Issuer disclosures do not establish the chart endpoint's adjustment basis;
never double adjust or infer absence of corporate actions from a smooth price.
Evidence schema remains: symbol -> source, resolution=1D, start, end,
payload_sha256 ordered start/end hashes, basis=same_adjusted_basis,
evidence_url HTTPS, reviewed_by, explanation. The program checks evidence
binding, not documentary truth. No such evidence is bundled as verified.

Outputs: data/ds1_performance/report_YYYY-MM-DD.{json,md,csv},
report_YYYY-MM-DD.sha256.json and raw/YYYY-MM-DD/*.json (40 responses).
Payload digest is canonical sorted JSON UTF-8; the manifest hashes actual files.
Dated valid bundles are immutable; reruns verify all manifest hashes and do not
replace them. Failed attempts write diagnostics, never overwrite dated results.
Interrupted/orphan bundles fail closed for manual review. JSON is the completion
marker. Artifact upload always runs, retention 90 days.

Only schedule/manual runs on main commit report data using GITHUB_TOKEN with
contents:write; no extra secret needed. Non-fast-forward pushes fetch/rebase and
retry four times, never force. Content conflicts stop safely with artifacts.
PR/push runs only test and fetch historical smoke data to work/ds1-smoke.
Merging activates this collector; existing trading workflows remain unchanged.
A configured cron is not proof of execution: check an Actions run with event
schedule and its report commit. This deployment cannot claim that before it occurs.
