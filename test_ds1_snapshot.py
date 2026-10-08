"""Offline smoke tests for DS1 timestamped snapshot output."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
from scripts import ds1_watch as scanner


class SnapshotTests(unittest.TestCase):
    def test_snapshot_bar_has_timezone_and_ohlcv(self):
        t = datetime(2026, 10, 8, 9, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")).timestamp()
        result = scanner.snapshot_bar({"t": t, "o": 25.0, "h": 25.2, "l": 24.9, "c": 25.1, "v": 1000})
        self.assertEqual(result["close"], 25.1)
        self.assertEqual(result["volume"], 1000)
        self.assertIn("+07:00", result["bar_time"])

    def test_out_of_session_writes_snapshot_without_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            with patch.object(scanner, "SNAPSHOT_PATH", path), \
                 patch.object(scanner, "in_session", return_value=False), \
                 patch.object(scanner, "fetch", side_effect=AssertionError("no fetch outside session")):
                self.assertEqual(scanner.main(), 0)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "OUT_OF_SESSION")
            self.assertFalse(data["session_active"])
            self.assertIn("generated_at", data)
            self.assertEqual(data["symbols_expected"], scanner.DS1)

    def test_write_snapshot_replaces_previous_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            with patch.object(scanner, "SNAPSHOT_PATH", path):
                scanner.write_snapshot({"status": "OLD"})
                scanner.write_snapshot({"status": "COMPLETE", "symbols": {"PVT": {"status": "NO_SETUP"}}})
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["symbols"]["PVT"]["status"], "NO_SETUP")
            self.assertFalse(path.with_suffix(".json.tmp").exists())


    def test_vn30_uses_index_endpoint_and_stock_uses_stock_endpoint(self):
        class FakeResponse:
            def raise_for_status(self):
                return None
            def json(self):
                return {"t": [], "o": [], "h": [], "l": [], "c": [], "v": []}

        with patch.object(scanner.requests, "get", return_value=FakeResponse()) as get:
            scanner.fetch("VN30", "1D", 86400)
            self.assertEqual(get.call_args.args[0], scanner.INDEX_URL)
            self.assertEqual(get.call_args.kwargs["params"]["symbol"], "VN30")
            scanner.fetch("PVT", "1", 86400)
            self.assertEqual(get.call_args.args[0], scanner.BASE_URL)
            self.assertEqual(get.call_args.kwargs["params"]["symbol"], "PVT")


if __name__ == "__main__":
    unittest.main()
