import unittest
from scripts.ds1_paper_watch import present
class WatchTests(unittest.TestCase):
 def test_paper_candidate_is_not_buy(self):
  source={"symbols":[{"symbol":"VPB","v1":{"score":100},"v2":{"score":80,"status":"RESEARCH_BLOCKED","gates":["UNVERIFIED_MARKET_SECTOR"],"metrics":{}}},{"symbol":"GVR","v1":{"score":0},"v2":{"score":90,"status":"WATCH_RISK","gates":["WATCH_RISK"],"metrics":{}}}]}
  out=present(source)
  self.assertEqual(out[0]["paper_status"],"PAPER_WATCH")
  self.assertFalse(next(x for x in out if x["symbol"]=="GVR")["candidate"])
 def test_hard_gate_blocks_paper_candidate(self):
  source={"symbols":[{"symbol":"PVT","v1":None,"v2":{"score":85,"status":"RESEARCH_BLOCKED","gates":["PIVOT_GATE"],"metrics":{}}}]}
  self.assertFalse(present(source)[0]["candidate"])
if __name__=="__main__":unittest.main()
