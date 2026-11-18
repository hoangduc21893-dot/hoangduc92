"""Offline regression checks for the user-approved watchlist reset and its history."""
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch
from scripts import ds1_universe as u, ds1_performance as p, ds1_paper_watch as paper

REMOVED = {"PVT", "BSR", "PVS", "VPB", "PLX", "GVR", "PHR", "DCM"}
ADDED = {"BAF", "VIX", "NKG", "DBC", "NT2"}


class UniverseTests(unittest.TestCase):
    def test_reset_boundary_and_retained_dates(self):
        old = u.performance_config("2026-11-17")
        new = u.performance_config("2026-11-18")
        self.assertEqual(len(old), 20)
        self.assertEqual(len(new), 17)
        self.assertEqual(set(old) - set(new), REMOVED)
        self.assertEqual(set(new) - set(old), ADDED)
        for symbol in set(old) & set(new):
            self.assertEqual(old[symbol], new[symbol])
        for symbol in ADDED:
            self.assertEqual(new[symbol], date(2026, 11, 18))

    def test_collect_new_members_at_t0_and_immutable_bundle(self):
        day = date(2026, 11, 18)
        now = datetime(2026, 11, 18, 17, tzinfo=p.eod.ICT)
        def payload(symbol, target, session):
            return dict(t=[int(datetime.combine(target, p.time(9), p.eod.ICT).timestamp())],
                        o=[20], h=[20], l=[20], c=[20], v=[100])
        with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as stage:
            with patch.object(p, "get_payload", side_effect=payload):
                report = p.collect(day, now, Mock(), Path(stage))
            self.assertEqual(report["expected_count"], 17)
            self.assertEqual(report["prices_validated_count"], 17)
            self.assertEqual(report["reference_equal_weight_change_pct"], 0)
            self.assertIsNone(report["equal_weight_return_pct"])
            for row in report["rows"]:
                if row["symbol"] in ADDED:
                    self.assertEqual(row["t_plus"], 0)
            self.assertTrue(p.publish(Path(out), report, Path(stage)))
            self.assertFalse(p.publish(Path(out), report, Path(stage)))
            manifest = json.loads((Path(out)/"report_2026-11-18.sha256.json").read_text())
            self.assertEqual(len(manifest), 37)

    def test_paper_watch_accepts_exact_17_only(self):
        names = u.symbols("2026-11-18")
        def source(names):
            return {"symbols": [{"symbol": s, "v1": {"score": 0},
                    "v2": {"score": 0, "status": "RESEARCH_BLOCKED", "gates": []}}
                    for s in names]}
        with tempfile.TemporaryDirectory() as tmp, patch.object(paper, "compare", return_value=source(names)):
            result = paper.run("2026-11-18", Mock(), Path(tmp)/"paper.json")
            self.assertEqual(len(result["rows"]), 17)
            self.assertFalse(result["validated_buy_signals"])
            self.assertFalse(result["telegram_enabled"])
        wrong = list(names)
        wrong[-1] = "PVT"
        with tempfile.TemporaryDirectory() as tmp, patch.object(paper, "compare", return_value=source(wrong)):
            with self.assertRaises(ValueError):
                paper.run("2026-11-18", Mock(), Path(tmp)/"paper.json")

    def test_packaged_engine_uses_shared_list_and_no_telegram(self):
        from scripts import run_ds1_engine as runner
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"main.py"
            path.write_text('DS1=("PVT",)\ndef main(): return 0\n')
            engine = runner.load_engine(path)
            self.assertEqual(set(engine.DS1), set(u.symbols()))
        with patch.object(runner, "load_engine", return_value=engine), patch.dict(runner.os.environ, {"TELEGRAM_BOT_TOKEN":"fake", "TELEGRAM_CHAT_ID":"fake"}):
            runner.main()
            self.assertEqual(runner.os.environ["TELEGRAM_BOT_TOKEN"], "")


if __name__ == "__main__":
    unittest.main()
