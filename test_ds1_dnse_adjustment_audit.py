import unittest
from scripts.ds1_dnse_adjustment_audit import audit
class DnseAdjustmentAuditTests(unittest.TestCase):
 def test_no_inferred_price_adjustment(self):
  ledger={"symbols":[{"symbol":"GMD","events":[{"record_date":"2026-10-08","ex_date":"2026-10-07","stock_ratio_new_per_old":.5,"cash_dividend_vnd":None,"source_url":"https://vsdc.vn"}]}]}
  x=audit(ledger,"/nonexistent")[0]
  self.assertEqual(x["evidence_status"],"BLOCKED_RAW_REFERENCE_AND_ADJUSTMENT_UNVERIFIED")
  self.assertIsNone(x["previous_close_if_unadjusted"])
  self.assertAlmostEqual(x["theoretical_stock_factor"],2/3)
if __name__=="__main__":unittest.main()
