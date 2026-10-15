import csv,tempfile,unittest
from pathlib import Path
from scripts.ds1_independent_history import load_csv,compare
class IndependentHistoryTests(unittest.TestCase):
 def test_basis_cannot_be_asserted_without_docs(self):
  with self.assertRaises(ValueError):load_csv("missing.csv","GMD","SSI","RAW")
 def test_validated_import_and_ratio(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"x.csv"
   with p.open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=["date","open","high","low","close","volume"]);w.writeheader();w.writerow({"date":"2026-10-06","open":100,"high":105,"low":95,"close":100,"volume":1000})
   a=load_csv(p,"GMD","SSI","UNKNOWN")
   b=load_csv(p,"GMD","VCI","UNKNOWN")
   rows=compare(a,b)
   self.assertEqual(len(rows),1)
   self.assertEqual(rows[0]["status"],"CROSS_SOURCE_ONLY_NOT_OFFICIALLY_VERIFIED")
   with self.assertRaises(ValueError):compare(a,a)
 def test_invalid_range(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"bad.csv";p.write_text("date,open,high,low,close,volume\\n2026-10-06,100,90,95,100,10\\n".replace("\\n","\n"))
   with self.assertRaises(ValueError):load_csv(p,"GMD","SSI","UNKNOWN")
if __name__=="__main__":unittest.main()
