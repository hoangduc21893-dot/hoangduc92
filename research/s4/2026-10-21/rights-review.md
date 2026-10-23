# Rights and adjustment review

Reviewed 2026-10-21 ICT. This is a partial primary-source check, not a certified complete corporate-action calendar. All five eligibility decisions remain FAIL on the provider series, with rights/adjustment certification BLOCKED. Absence of a >7% opening gap is not evidence of no dividend, split or back adjustment.

SSI: https://www.ssi.com.vn/quan-he-nha-dau-tu lists a dividend of 1,000 VND, record date 2026-08-18 and payment 2026-09-14. Its current 2026-10-21 price of 20.40 agrees with the DNSE 20.40 raw close. The page labels prices in thousand VND; its volume footer says 10 shares, so it is not used to certify DNSE volume units. Repo DNSE volume contract is retained explicitly.

TPB: https://vsdc.vn/vi/ad/200697 (published 2026-09-25) states record date 2026-10-05, cash dividend 500 VND/share paid 2026-10-14, and stock dividend 15%. This record date is within the RS20 lookback: TPB RS20 and moving averages must remain provisional until the provider's adjustment basis is certified. Do not infer an ex-date from the record date or apply the factors again.

VCI, KDH, NLG: web queries targeting VSD/VSDC and 2026 rights did not establish a complete authoritative event history through this EOD. No claim of 'no events' is made. The NLG bond-interest notices are not common-stock dividends and are not used as adjustments.

Queries: site.vsd.vn + each ticker + 2026 + quyen/rights; SSI issuer investor relations; VSDC TPB related notices. Search failure is a coverage limitation. Source HTML attempts and hashes are retained in evidence/rights-sources.json. No adjusted/unadjusted series is silently mixed.

This audit preserves scripts/ds1_watch.py S4 daily gates from base aa4f06a6368f6b983b2cebd119652c9d79be2e2c. The daily volume contraction cap and the requested same-day expansion floor are mathematically incompatible: if P is prior20 mean, V today's volume and X oldest volume, inclusive20 mean=(20P-X+V)/20. V<=1.1*inclusive20 implies V/P<=22/18.9=1.1641 even for X=0, below 1.5. We do not redefine S4 or reinterpret a daily WATCH as an intraday BUY. A two-stage pullback/confirmation variant would need a separate explicit specification.

Reproduce: python -m scripts.s4_eod_research --date 2026-10-21 --output research/s4/2026-10-21

Validation: 28 tests passed across the new research suite and DS2 EOD, DS1 performance, snapshot and paper-watch suites. Initial sandbox run had two Windows temporary-directory permission errors; the same 28 tests passed outside that restriction. No production list or workflow changed. Scores are a new disclosed research formula (not the production MIN_SCORE=75), with the requested WATCH threshold kept at 80 and volume floor at 1.5. Equal scores use ticker alphabetical order; ranking is provisional and not an eligibility recommendation.
