import unittest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from scripts.ds1_backtest_v2 import walk_forward,metrics
TZ=ZoneInfo("Asia/Ho_Chi_Minh")
def series(count=90,slope=.14):
    t=datetime(2026,1,2,tzinfo=TZ)
    return [{"t":(t+timedelta(days=i)).timestamp(),"o":100+i*slope,"h":101+i*slope,
             "l":99+i*slope,"c":100+i*slope,"v":1000000} for i in range(count)]
class BacktestTests(unittest.TestCase):
    def test_next_open_and_holdout(self):
        d=series()
        rows=walk_forward({"AAA":d},series(slope=.04),train_end="2026-02-15",test_start="2026-02-16",test_end="2026-05-01")
        self.assertTrue(rows)
        self.assertTrue(all(r["split"] in ("train","test") for r in rows))
        self.assertTrue(any(r["split"]=="test" for r in rows))
    def test_no_future_label_leak(self):
        d=series()
        rows=walk_forward({"AAA":d},series(slope=.04),train_end="2026-01-01",test_start="2026-01-02",test_end="2026-05-01")
        d[-1]["c"]*=10
        rows2=walk_forward({"AAA":d},series(slope=.04),train_end="2026-01-01",test_start="2026-01-02",test_end="2026-05-01")
        self.assertEqual([(r["date"],r["v1_score"],r["v2_score"]) for r in rows],[(r["date"],r["v1_score"],r["v2_score"]) for r in rows2])
    def test_empty(self):
        self.assertEqual(metrics([],"v1_watch")["signals"],0)
    def test_negative_fee(self):
        with self.assertRaises(ValueError):walk_forward({},series(),fee_bps=-1)
if __name__=="__main__":unittest.main()
