import unittest
import pandas as pd
import realtime_opportunity_scanner as scanner

def df():
    n=80; close=[100.0]*n
    for i in range(60,n): close[i]=100+(i-59)*0.2
    close[-1]=105
    return pd.DataFrame({
        "ts":pd.date_range("2026-10-05 09:00",periods=n,freq="min",tz="UTC"),
        "open":close,"high":[x+.5 for x in close],"low":[x-.5 for x in close],
        "close":close,"volume":[1000.0]*(n-1)+[2200.0]})

class ScannerTests(unittest.TestCase):
    def test_candidate_has_required_fields(self):
        x=scanner.score_symbol("MWG",df())
        self.assertIsNotNone(x)
        self.assertIn("candidate_score",x)
        self.assertIn("candidate_strategy",x)
    def test_far_symbol_not_candidate(self):
        d=df(); d["close"]=80.; d["open"]=80.; d["high"]=80.5; d["low"]=79.5; d["volume"]=500.
        self.assertIsNone(scanner.score_symbol("TEST",d))
    def test_short_data_safe(self):
        self.assertIsNone(scanner.score_symbol("TEST",df().head(20)))

if __name__=="__main__": unittest.main()
