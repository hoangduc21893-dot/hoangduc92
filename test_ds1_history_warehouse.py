import unittest
from datetime import date
from scripts.ds1_history_warehouse import windows,audit_series,corporate_action_flags
class WarehouseTests(unittest.TestCase):
 def test_windows_no_gaps(self):
  v=list(windows(date(2023,1,1),date(2023,12,31),150))
  self.assertEqual(v[0][0],date(2023,1,1))
  self.assertEqual(v[-1][1],date(2023,12,31))
  for a,b in zip(v,v[1:]):self.assertEqual((a[1]+__import__("datetime").timedelta(days=1)),b[0])
 def test_missing_calendar(self):
  bars=[{"t":1672534800,"o":10,"h":11,"l":9,"c":10,"v":100}]
  chk=audit_series(bars,{date(2023,1,2)})
  self.assertEqual(chk["missing_count"],1)
 def test_raw_gap_flag_not_corporate_adjustment(self):
  bars=[{"t":1,"o":10,"h":11,"l":9,"c":10,"v":10},{"t":90000,"o":7,"h":8,"l":6,"c":7,"v":10}]
  x=corporate_action_flags(bars)
  self.assertEqual(len(x),1)
  self.assertIn("UNVERIFIED",x[0]["status"])
if __name__=="__main__":unittest.main()
