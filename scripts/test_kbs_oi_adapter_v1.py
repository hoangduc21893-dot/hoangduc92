import unittest
from unittest.mock import patch
import scripts.kbs_oi_adapter_v1 as a

class TestKBSOIAdapter(unittest.TestCase):
    def test_contract_mapping(self):
        self.assertEqual(a.krx_code_from_alias("VN30F2610"),"41I1GA000")
        self.assertEqual(a.krx_code_from_alias("VN30F2611"),"41I1GB000")

    def test_snapshot_normalizes_oi(self):
        group={"data":["41I1GA000","41I1GB000"]}
        payload={"data":[{"SB":"41I1GA000","FN":"VN30 Index Futures 102026","ULS":"VN30","OI":"37458","CP":1900.1,"OP":1889,"HI":1906.1,"LO":1884.5,"TT":214672,"LTD":"15/10/2026","TSI":"CLOSED"}]}
        with patch.object(a,"_request",side_effect=[(200,group),(201,payload)]):
            s=a.fetch_snapshot()
        self.assertEqual(s["contract_code"],"41I1GA000")
        self.assertEqual(s["open_interest"],37458.0)
        self.assertEqual(s["price"],1900.1)
        self.assertEqual(s["volume"],214672.0)

    def test_no_oi_fails_safe(self):
        group={"data":["41I1GA000"]}
        payload={"data":[{"SB":"41I1GA000","FN":"VN30 Index Futures 102026","CP":1900.1}]}
        with patch.object(a,"_request",side_effect=[(200,group),(201,payload)]):
            with self.assertRaises(RuntimeError):
                a.fetch_snapshot()

if __name__=="__main__":
    unittest.main()
