import unittest
from unittest.mock import patch, Mock
import scripts.kbs_oi_adapter_v1 as a

class KBSOIAdapterV1Tests(unittest.TestCase):
    def test_krx_candidate(self):
        self.assertEqual(a.krx_candidate("VN30F2610"), "41I1GA000")

    @patch("scripts.kbs_oi_adapter_v1.requests.request")
    def test_normalize_live_shape(self, req):
        group=Mock(status_code=200,ok=True)
        group.json.return_value={"data":["41I1GA000","41I1GB000"]}
        iss=Mock(status_code=201,ok=True)
        iss.json.return_value={"data":[{"SB":"41I1GA000","FN":"VN30 Index Futures 102026","ULS":"VN30","OP":"1889","CP":"1900.1","HI":"1906.1","LO":"1884.5","OI":"37458","TT":"214672","TV":"40679956260000","LTD":"15/10/2026","TSI":"CLOSED","t":"1791187201631"}]}
        req.side_effect=[group,iss]
        out=a.get_snapshot()
        self.assertEqual(out["contract_code"],"41I1GA000")
        self.assertEqual(out["open_interest"],37458.0)
        self.assertEqual(out["price"],1900.1)
        self.assertEqual(out["volume"],214672.0)
        self.assertEqual(out["underlying"],"VN30")
        self.assertEqual(out["source"],"KBS")

    @patch("scripts.kbs_oi_adapter_v1.requests.request")
    def test_fail_closed_when_mapping_not_in_kbs_group(self, req):
        group=Mock(status_code=200,ok=True)
        group.json.return_value={"data":["41I1GB000"]}
        req.side_effect=[group]
        with self.assertRaises(RuntimeError):
            a.get_snapshot()

if __name__=="__main__": unittest.main()
