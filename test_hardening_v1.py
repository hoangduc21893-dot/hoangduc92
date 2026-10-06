#!/usr/bin/env python3
"""Regression tests for DNSE Hardening v1 P1 fixes."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import scripts.vn30f1m_watch as watch


class HardeningV1RegressionTests(unittest.TestCase):
    def test_state_and_paper_ledger_survive_separate_reads(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path = root / "state.json"
            ledger_path = root / "paper.jsonl"
            with patch.object(watch, "STATE_PATH", state_path), patch.object(watch, "PAPER_LEDGER_PATH", ledger_path):
                watch.save_state({"alert_keys": {"2026-10-07|F1 Trend Following|LONG": "saved"}})
                watch._save_paper_trades([{"id": "paper-1", "status": "OPEN", "side": "LONG"}])
                self.assertEqual(watch.load_state()["alert_keys"]["2026-10-07|F1 Trend Following|LONG"], "saved")
                rows = watch._load_paper_trades()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["status"], "OPEN")

    def test_kbs_exception_fails_closed_without_name_error(self):
        tz = ZoneInfo("Asia/Ho_Chi_Minh")
        now = datetime(2026, 10, 7, 9, 30, tzinfo=tz)
        fut = [{"t": now.timestamp() - (80-i)*60, "o": 1900.0, "h": 1901.0, "l": 1899.0, "c": 1900.0, "v": 100.0} for i in range(80)]
        v30 = [{"t": now.timestamp() - (40-i)*300, "o": 1880.0, "h": 1881.0, "l": 1879.0, "c": 1880.0, "v": 100.0} for i in range(40)]
        payloads = [
            ({"t":[x["t"] for x in fut],"o":[x["o"] for x in fut],"h":[x["h"] for x in fut],"l":[x["l"] for x in fut],"c":[x["c"] for x in fut],"v":[x["v"] for x in fut]}, "fut-endpoint", []),
            ({"t":[x["t"] for x in v30],"o":[x["o"] for x in v30],"h":[x["h"] for x in v30],"l":[x["l"] for x in v30],"c":[x["c"] for x in v30],"v":[x["v"] for x in v30]}, "spot-endpoint", []),
        ]
        history_rows = []
        with patch.object(watch, "datetime") as dt,              patch.object(watch, "fetch", side_effect=payloads),              patch.object(watch, "get_kbs_oi_snapshot", side_effect=RuntimeError("simulated KBS outage")),              patch.object(watch, "history", side_effect=history_rows.append),              patch.object(watch, "_execution_summary") as summary:
            dt.now.return_value = now
            rc = watch.main()
        self.assertEqual(rc, 0)
        self.assertEqual(history_rows[-1]["status"], "WAIT")
        self.assertEqual(history_rows[-1]["oi_status"], "UNAVAILABLE")
        self.assertIn("simulated KBS outage", history_rows[-1]["reason"])
        self.assertEqual(summary.call_args.args[-2], "WAIT")


if __name__ == "__main__":
    unittest.main()
