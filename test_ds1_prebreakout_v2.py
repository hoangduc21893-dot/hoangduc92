import unittest
from scripts.ds1_prebreakout_v2 import score_v2, WEIGHTS

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
    def test_invalid(self):
        d=bars(); d[-1]["c"]=-1
        self.assertEqual(score_v2(d,bars())["status"],"INVALID_DATA")

if __name__=="__main__": unittest.main()
