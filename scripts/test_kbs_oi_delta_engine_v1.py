import unittest
from scripts.kbs_oi_delta_engine_v1 import classify, compute_delta

class TestOIDeltaEngine(unittest.TestCase):
    def test_long_buildup(self):
        self.assertEqual(classify(1900,1905,37000,38000),"LONG_BUILDUP")

    def test_short_buildup(self):
        self.assertEqual(classify(1900,1895,37000,38000),"SHORT_BUILDUP")

    def test_short_covering(self):
        self.assertEqual(classify(1900,1905,37000,36000),"SHORT_COVERING")

    def test_long_unwinding(self):
        self.assertEqual(classify(1900,1895,37000,36000),"LONG_UNWINDING")

    def test_neutral_when_one_side_unchanged(self):
        self.assertEqual(classify(1900,1905,37000,37000),"NEUTRAL")
        self.assertEqual(classify(1900,1900,37000,38000),"NEUTRAL")

    def test_compute_delta(self):
        prev={"symbol_alias":"VN30F2610","contract_code":"41I1GA000","price":1900,"open_interest":37000,"timestamp":"t1"}
        curr={"symbol_alias":"VN30F2610","contract_code":"41I1GA000","price":1905,"open_interest":38000,"timestamp":"t2"}
        r=compute_delta(prev,curr)
        self.assertEqual(r["classification"],"LONG_BUILDUP")
        self.assertEqual(r["price_delta"],5.0)
        self.assertEqual(r["oi_delta"],1000.0)

    def test_contract_mismatch_fails_safe(self):
        prev={"contract_code":"41I1GA000","price":1900,"open_interest":37000}
        curr={"contract_code":"41I1GB000","price":1905,"open_interest":38000}
        with self.assertRaises(ValueError):
            compute_delta(prev,curr)

    def test_invalid_previous_oi_fails_safe(self):
        with self.assertRaises(ValueError):
            classify(1900,1905,0,38000)

if __name__=="__main__":
    unittest.main()
