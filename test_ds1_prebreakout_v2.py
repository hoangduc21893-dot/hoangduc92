import unittest
import math
from datetime import date,datetime,timedelta
from zoneinfo import ZoneInfo
from scripts.ds1_prebreakout_v2 import score_v2, WEIGHTS, validate_series

def bars(n=80, rise=0.13, volume=1000000):
    return [{"o":100+rise*i-0.2,"h":100+rise*i+0.3,"l":100+rise*i-0.4,
             "c":100+rise*i,"v":volume} for i in range(n)]

class ResearchV2Tests(unittest.TestCase):
    def test_weights(self):
        self.assertEqual(sum(WEIGHTS.values()),100)
    def test_insufficient(self):
        self.assertEqual(score_v2(bars(40),bars())["status"],"INSUFFICIENT_DATA")
    def test_gate_missing_context(self):
        a=score_v2(bars(),bars())
        self.assertEqual(a["status"],"RESEARCH_BLOCKED")
        self.assertIn("UNVERIFIED_MARKET_SECTOR",a["gates"])
        self.assertTrue(0<=a["score"]<=100)
    def test_benchmark_strength(self):
        a=score_v2(bars(rise=.2),bars(rise=.01))
        self.assertGreater(a["metrics"]["rs20_pct_points"],0)
    def test_nonfinite_ohlcv(self):
        for val in (math.nan,math.inf):
            d=bars(); d[-1]["c"]=val
            self.assertEqual(score_v2(d,bars())["status"],"INVALID_DATA")

    def test_malformed_ohlcv(self):
        d=bars(); d[-1]["l"]=-2
        self.assertEqual(score_v2(d,bars())["status"],"INVALID_DATA")

    def test_duplicate_or_stale_dates(self):
        tz=ZoneInfo("Asia/Ho_Chi_Minh")
        end=date(2026,10,14)
        d=bars()
        for i,b in enumerate(d):
            b["t"]=datetime(2026,7,27,tzinfo=tz).timestamp()+i*86400
        with self.assertRaisesRegex(ValueError,"TARGET_DATE_MISSING"):
            validate_series(d,end,"TEST")
        d[-1]["t"]=datetime(2026,10,14,tzinfo=tz).timestamp()
        d[-2]["t"]=d[-1]["t"]
        with self.assertRaisesRegex(ValueError,"DUPLICATE_OR_UNSORTED"):
            validate_series(d,end,"TEST")

    def test_invalid(self):
        d=bars(); d[-1]["c"]=-1
        self.assertEqual(score_v2(d,bars())["status"],"INVALID_DATA")

if __name__=="__main__": unittest.main()
