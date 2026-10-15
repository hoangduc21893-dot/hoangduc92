# DS1 Data Quality & Corporate Action Audit — 2026-10-15

Source: GitHub Actions run 38675394284, artifact 11945702649; DNSE 1D warehouse 2023-01-03 to 2026-10-14.

## Data findings
- 20 stock symbols, VN30: all 21 fetched, no fetch errors.
- VN30: 938 dates; 19 stocks: 940 dates each; BSR: 932 dates.
- Benchmark VN30 lacks stock-trading dates 2023-04-07 and 2025-04-03. This warrants benchmark calendar audit.
- BSR absent on 2025-01-07, 08, 09, 10, 13, 14, 15, 16. Confirmed transfer: first HOSE trading date 2025-01-17. Venue transfer is the likely non-trading explanation; don't interpolate.
  Official issuer: https://www.bsr.com.vn/vi/w/3-1-t%E1%BB%B7-c%E1%BB%95-phi%E1%BA%BFu-bsr-ch%C3%ADnh-th%E1%BB%A9c-ni%C3%AAm-y%E1%BA%BFt-tr%C3%AAn-hose
- Zero overnight discontinuities exceeded a raw 18% detector threshold; this is NOT a corporate-action clearance.

## Rights and price adjustments
- GMD ex-right 2026-10-07: 2:1 bonus (50% new shares), VSDC https://vsdc.vn/vi/ad1/200797 . Theoretical ratio 1/1.5. DNSE historical closes 2026-10-06: 52,000; 2026-10-07: 54,200 VND, indicating the series is already retrospectively adjusted.
- HDB ex-right 2026-10-09: 25% stock dividend plus 5% bonus, theoretical ratio 1/1.30. MBS https://www.mbs.com.vn/thong-bao-ho-tro-tinh-quyen-co-phieu-100926/ . DNSE historical closes 2026-10-08: 21,540; 2026-10-09: 22,400 VND, indicating apparent retrospective adjustment.
- Never reapply theoretical factors without establishing the DNSE history adjustment basis. Full corporate action histories from 2023 onward are not yet verified.

## Release gates
1. Explain BSR non-trading gap with venue transfer event and verify last UPCoM day. Verify equity-only dates omitted by VN30, using an official market calendar.
2. Maintain a rights ledger with symbol, ex-date, event type, ratio/cash, provenance and adjustment basis, and explicit review status.
3. Confirm raw/adjusted DNSE basis against exchange reference prices, and prevent double adjustment.
4. Repeat data QA after exceptions, including finite/valid OHLCV, duplicates, benchmark alignment and checksum.
5. Keep GVR in historical analysis but never BUY. Block production, signal migration and official backtest until all relevant actions reconciled.

STATUS: DATA_INCOMPLETE; CORPORATE_ACTION_PARTIAL; BACKTEST_BLOCKED.
