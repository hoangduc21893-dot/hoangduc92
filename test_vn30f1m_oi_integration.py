import unittest
import scripts.vn30f1m_watch as w

class VN30F1MOIIntegrationTests(unittest.TestCase):
    def test_kbs_oi_snapshot_valid(self):
        snap={"source":"KBS","underlying":"VN30","open_interest":37458,"price":1900.1,
              "contract_code":"41I1GA000","timestamp":"2026-10-05T08:00:01+00:00"}
        out=w.oi_snapshot(snap,1900.0)
        self.assertIsNotNone(out)
        self.assertEqual(out["current"],37458.0)
        self.assertEqual(out["source"],"KBS")
        self.assertTrue(out["price_valid"])
        self.assertIsNone(out["delta_pct"])

    def test_kbs_oi_price_mismatch(self):
        snap={"source":"KBS","underlying":"VN30","open_interest":37458,"price":1900.1}
        out=w.oi_snapshot(snap,1910.5)
        self.assertIsNotNone(out)
        self.assertFalse(out["price_valid"])

    def test_invalid_kbs_oi_fails_closed(self):
        snap={"source":"KBS","underlying":"VN30","open_interest":0,"price":1900.1}
        self.assertIsNone(w.oi_snapshot(snap,1900.1))

if __name__=="__main__":
    unittest.main()
