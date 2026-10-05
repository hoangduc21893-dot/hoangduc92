import unittest
from unittest.mock import patch

import scripts.kbs_oi_live_collector_v1 as c

class TestKBSOILiveCollector(unittest.TestCase):
    def snapshot(self, price, oi, ts):
        return {
            "symbol_alias":"VN30F2610",
            "contract_code":"41I1GA000",
            "price":price,
            "open_interest":oi,
            "timestamp":ts,
        }

    def test_collects_consecutive_samples_and_delta(self):
        samples=[
            self.snapshot(1900,37000,"t1"),
            self.snapshot(1905,38000,"t2"),
            self.snapshot(1902,39000,"t3"),
        ]
        with patch.object(c,"append") as out:
            with patch.object(c.time,"monotonic",side_effect=[0,1,2,11]):
                with patch.object(c.time,"sleep"):
                    result=c.run(duration_sec=10,interval_sec=1,fetcher=iter(samples).__next__)
        self.assertEqual(result["samples"],3)
        self.assertEqual(result["errors"],0)
        self.assertEqual(result["delta_classifications"]["LONG_BUILDUP"],2)
        rows=[x.args[0] for x in out.call_args_list]
        self.assertIsNone(rows[0]["delta"])
        self.assertEqual(rows[1]["delta"]["oi_delta"],1000.0)

    def test_fetch_error_is_recorded_and_collection_continues(self):
        values=iter([RuntimeError("temporary"), self.snapshot(1900,37000,"t1")])
        def fetch():
            v=next(values)
            if isinstance(v,Exception): raise v
            return v
        with patch.object(c,"append"):
            with patch.object(c.time,"monotonic",side_effect=[0,1,11]):
                with patch.object(c.time,"sleep"):
                    result=c.run(duration_sec=10,interval_sec=1,fetcher=fetch)
        self.assertEqual(result["samples"],1)
        self.assertEqual(result["errors"],1)
        self.assertEqual(result["status"],"PARTIAL")

if __name__=="__main__":
    unittest.main()
