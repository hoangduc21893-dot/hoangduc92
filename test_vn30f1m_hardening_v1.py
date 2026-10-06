import importlib.util
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("watch", "scripts/vn30f1m_watch.py")
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)

class HardeningV1Tests(unittest.TestCase):
    def test_state_and_paper_ledger_survive_fresh_module_load(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "state.json"
            ledger = Path(td) / "ledger.jsonl"
            old_state, old_ledger = watch.STATE_PATH, watch.PAPER_LEDGER_PATH
            try:
                watch.STATE_PATH, watch.PAPER_LEDGER_PATH = state, ledger
                watch.save_state({"alert_keys": {"2026-10-07|F1|LONG": "saved"}})
                watch._save_paper_trades([{"id":"t1","status":"OPEN","side":"LONG","entry":100,"sl":99,"tp1":102,"tp2":103}])
                self.assertEqual(watch.load_state()["alert_keys"]["2026-10-07|F1|LONG"], "saved")
                self.assertEqual(watch._load_paper_trades()[0]["status"], "OPEN")
            finally:
                watch.STATE_PATH, watch.PAPER_LEDGER_PATH = old_state, old_ledger

    def test_kbs_failure_is_fail_closed_not_nameerror(self):
        now = datetime(2026, 10, 7, 9, 30, tzinfo=watch.VN_TZ)
        fut=[{"t": now.timestamp()+i*60, "o":100+i*.01, "h":101+i*.01, "l":99+i*.01, "c":100.5+i*.01, "v":1000+i} for i in range(80)]
        v30=[{"t": now.timestamp()+i*300, "o":100, "h":101, "l":99, "c":100.5+i*.01, "v":1000} for i in range(40)]
        payload=lambda rows: {k:[r[k] for r in rows] for k in ("t","o","h","l","c","v")}
        def fake_fetch(symbol,resolution,seconds):
            rows=fut if symbol==watch.SYMBOL else v30
            return payload(rows), "test-endpoint", []
        records=[]
        with patch.object(watch, "datetime") as dt, \
             patch.object(watch, "fetch", side_effect=fake_fetch), \
             patch.object(watch, "get_kbs_oi_snapshot", side_effect=RuntimeError("forced KBS failure")), \
             patch.object(watch, "history", side_effect=lambda x: records.append(x)), \
             patch.object(watch, "_execution_summary"):
            dt.now.return_value=now
            dt.fromtimestamp.side_effect=datetime.fromtimestamp
            rc=watch.main()
        self.assertEqual(rc,0)
        self.assertEqual(records[-1]["status"],"WAIT")
        self.assertEqual(records[-1]["oi_status"],"UNAVAILABLE")
        self.assertIn("forced KBS failure", records[-1]["reason"])

if __name__ == "__main__":
    unittest.main()
