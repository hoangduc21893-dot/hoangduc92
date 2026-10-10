import unittest
from scripts.vn30f_data_diagnostic import inspect

class DiagnosticTests(unittest.TestCase):
    def test_recent_is_unverified_not_live(self):
        self.assertEqual(inspect({"t":[1000,1060],"c":[100,101]},1100,60)["status"],"UNVERIFIED")
    def test_stale(self):
        self.assertEqual(inspect({"t":[1000,1060],"c":[100,101]},2000,60)["status"],"STALE")
    def test_future(self):
        self.assertEqual(inspect({"t":[1000,1200],"c":[100,101]},1100,60)["reason"],"FUTURE_TIMESTAMP")
    def test_duplicate(self):
        self.assertEqual(inspect({"t":[1000,1000],"c":[100,101]},1100,60)["status"],"ERROR")
    def test_bad_payload(self):
        self.assertEqual(inspect({},1100,60)["status"],"ERROR")
    def test_no_false_timestamp_certification(self):
        self.assertEqual(inspect({"t":[1000,1060],"c":[100,101]},1100,60)["reason"],"CANDLE_TIMESTAMP_SEMANTICS_UNVERIFIED")

if __name__=="__main__":unittest.main()
