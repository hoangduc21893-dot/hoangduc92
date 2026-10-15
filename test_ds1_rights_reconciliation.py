import unittest
from scripts.ds1_rights_reconciliation import build
class RightsEvidenceTests(unittest.TestCase):
 def setUp(self):
  self.ledger={"symbols":[{"symbol":"AAA","events":[{"record_date":"2026-10-08","ex_date":"2026-10-07","event_type":"BONUS_SHARES","stock_ratio_new_per_old":0.5,"cash_dividend_vnd":None,"source_url":"https://example.org/issuer"}]}]}
  self.key="AAA:2026-10-07:0"
 def test_missing_proof_is_blocked(self):
  row=build(self.ledger)[0]
  self.assertEqual(row["status"],"BLOCKED_UNVERIFIED")
  self.assertIn("official_reference_vnd",row["missing_evidence"])
 def test_source_only_does_not_verify(self):
  row=build(self.ledger,{self.key:{"official_reference_vnd":20000,"official_reference_source":"source"}})[0]
  self.assertNotEqual(row["status"],"VERIFIED")
 def test_ratios_and_evidence_complete(self):
  bar={"open":100,"high":101,"low":99,"close":100,"volume":1000}
  adj={"open":70,"high":71,"low":69,"close":70,"volume":1500}
  proof={"official_reference_vnd":70,"official_reference_source":"official","raw_ohlcv_source":"source_raw","adjusted_ohlcv_source":"source_adj","raw_ohlcv":bar,"adjusted_ohlcv":adj,"vendor_adjustment_documentation":"verified docs","reviewed_against_official_source":True}
  row=build(self.ledger,{self.key:proof})[0]
  self.assertEqual(row["status"],"VERIFIED")
  self.assertAlmostEqual(row["theoretical_price_factor"],2/3)
  self.assertAlmostEqual(row["observed_price_factor"],0.7)
  self.assertAlmostEqual(row["observed_volume_factor"],1.5)
if __name__=="__main__":unittest.main()
