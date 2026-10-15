import json,unittest
from pathlib import Path
from scripts.ds1_corporate_action_gate import assess
class CorporateActionGateTests(unittest.TestCase):
 def test_ledger_is_fail_closed(self):
  ledger=json.loads((Path(__file__).parent/"data/ds1_v2/corporate_action_ledger.json").read_text())
  x=assess(ledger)
  self.assertEqual(x["symbols"],20)
  self.assertGreaterEqual(x["events"],35)
  self.assertEqual(x["status"],"BLOCKED")
  self.assertFalse(x["eligible_for_official_backtest"])
 def test_prevent_unverified_adjustment(self):
  d=json.loads((Path(__file__).parent/"data/ds1_v2/corporate_action_ledger.json").read_text())
  for row in d["symbols"]:
   for e in row["events"]:
    self.assertEqual(e["data_application"],"NEVER_AUTO_APPLY")
if __name__=="__main__":unittest.main()
