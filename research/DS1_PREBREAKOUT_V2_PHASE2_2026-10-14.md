# DS1 Pre-Breakout V2 — Phase 2 Comparison (research only)

Data: DNSE 1D close through 2026-10-14; GitHub Actions run 38671289279, artifact 11943523448. Not live signals. V2 model thresholds not backtested.

## V1 vs V2 (20 symbols)

| Symbol | V1 | V2 | Status |
|---|---:|---:|---|
| VPB | 100 | 80 | RESEARCH_BLOCKED |
| HDB | 60 | 75 | RESEARCH_BLOCKED |
| DCM | 80 | 75 | RESEARCH_BLOCKED |
| TCB | 60 | 75 | RESEARCH_BLOCKED |
| MWG | 60 | 70 | RESEARCH_BLOCKED |
| PET | 50 | 55 | RESEARCH_BLOCKED |
| GMD | 30 | 55 | RESEARCH_BLOCKED |
| PVT | 50 | 50 | RESEARCH_BLOCKED |
| MSB | 60 | 50 | RESEARCH_BLOCKED |
| HPG | 30 | 50 | RESEARCH_BLOCKED |
| BSR | 40 | 45 | RESEARCH_BLOCKED |
| HAH | 20 | 40 | RESEARCH_BLOCKED |
| VGC | 30 | 40 | RESEARCH_BLOCKED |
| PVS | 0 | 33 | RESEARCH_BLOCKED |
| PLX | 0 | 33 | RESEARCH_BLOCKED |
| ANV | 30 | 30 | RESEARCH_BLOCKED |
| VHC | 0 | 30 | RESEARCH_BLOCKED |
| DHC | 0 | 25 | RESEARCH_BLOCKED |
| GVR | 0 | 25 | WATCH_RISK |
| PHR | 0 | 15 | RESEARCH_BLOCKED |

## Deep dive

- VPB V2 80: trend15, base0, pivot10, dryup10, contraction10, RS15, pressure10, liquidity10, market_sector0. Base depth 13.03% vs experimental 12% threshold; RS20 vs VN30 +16.40pp; CLV proxy +0.249; average 20d turnover ~499.52bn VND. Missing market-sector verification.
- DCM V2 75: trend15, base15, pivot10, dryup10, contraction0, RS15, pressure0, liquidity10, market_sector0. Base depth 9.32%; RS20 +7.31pp; CLV proxy -0.012; average turnover ~95.07bn VND. Missing market-sector verification.
- HDB V2 75: RS20 +16.48pp; base depth 11.77%; CLV +0.190; volume dry-up and range contraction not met.
- TCB V2 75: RS20 +6.91pp; base depth 6.23%; CLV +0.158; volume dry-up and range contraction not met.
- MWG V2 70: still RESEARCH_BLOCKED.

## Critical research caveats / audit follow-ups

1. Every eligible symbol remains RESEARCH_BLOCKED due to unavailable sector strength and market-regime inputs. This is correct fail-closed behavior; no production BUY.
2. V2 WATCH score does not establish predictive validity, hit rate, or expected return; threshold selection requires walk-forward testing and transaction costs.
3. V1 and V2 scores have different feature weights and are not comparable as calibrated probabilities.
4. Volume, liquidity, and corporate-action-adjusted OHLCV require separate point-in-time provider audits (not proved by 31 unit tests).
5. CLV is only an order-pressure proxy and must not be represented as actual institutional flow.
6. Current benchmark uses VN30 for relative strength; benchmark choice and sector mapping need explicit policy and historical availability.
7. The V2 input check validates monotonic trading dates for stocks and benchmark independently; calendar alignment across historical gaps and ex-right price adjustments need broader backtest data QA.
8. Base-depth threshold 12% is heuristic; evaluate robustness by industry and volatility regime without hand-tuning on VPB.

## Phase 2 outcome

Side-by-side scores and VPB/DCM explanations complete for EOD 2026-10-14. Feature calibration, sector data, and historical out-of-sample validation remain OPEN. Do not merge or enable production BUY.
