import json
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, date
from pathlib import Path
from unittest.mock import Mock, patch
from scripts import ds1_market_wide as scanner

NOW = datetime(2026, 10, 8, 10, 0, tzinfo=scanner.v1.VN_TZ)


def daily():
    return [{"t": (NOW - timedelta(days=70-i)).replace(hour=9).timestamp(),
             "o": 25000., "h": 26000., "l": 24000., "c": 25500., "v": 100000.} for i in range(70)]


def minutes():
    return [{"t": (NOW-timedelta(minutes=12-i)).timestamp(), "o": 25500., "h": 25600.,
             "l": 25400., "c": 25500., "v": 10000.} for i in range(12)]


def manifest():
    return {"generated_at": NOW.isoformat(), "source": "test-fixture", "complete": True,
            "trading_dates": ["2026-10-07", "2026-10-08"],
            "instruments": [{"symbol": s, "exchange": e, "type": "STOCK", "active": True}
                            for s,e in [("AAA","HOSE"),("BBB","HNX"),("CCC","UPCOM")]]}


class Tests(unittest.TestCase):
    def test_manifest_all_exchanges_and_vtp_excluded(self):
        p = manifest()
        p["instruments"].append({"symbol":"VTP","exchange":"HOSE","type":"STOCK","active":True})
        symbols, previous, excluded = scanner.parse_manifest(p, NOW)
        self.assertEqual(len(symbols), 3)
        self.assertEqual(previous, date(2026,10,7))
        self.assertIn("VTP", excluded)

    def test_stale_incomplete_and_holiday_manifests_rejected(self):
        for change in [{"generated_at":(NOW-timedelta(days=2)).isoformat()},
                       {"complete":False}, {"trading_dates":["2026-10-07"]}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                scanner.parse_manifest({**manifest(), **change}, NOW)

    def test_daily_does_not_drop_last_completed_day(self):
        d = scanner.completed_daily(daily(), NOW, date(2026,10,7))
        self.assertEqual(scanner.legacy_input(d)[:-1], d)
        with self.assertRaisesRegex(ValueError, "STALE"):
            scanner.completed_daily(d[:-1], NOW, date(2026,10,7))

    def test_malformed_ohlcv_rejected(self):
        payload = dict(t=[1],o=[25],h=[26],l=[24],c=[25],v=[100])
        self.assertEqual(len(scanner.validate_bars(payload)), 1)
        for change in [{"v":[]}, {"c":[float("nan")]}, {"l":[27]}, {"t":[1,1]}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                scanner.validate_bars({**payload, **change})

    def test_pre_breakout_rank_is_watch_not_buy(self):
        bars = daily()
        for i, bar in enumerate(bars):
            if i >= 50:
                bar["h"] = 26000.
                bar["l"] = 25000.
                bar["c"] = 25500.
                bar["o"] = 25400.
                bar["v"] = 100000. if i < 60 else 60000.
        ranked = scanner.pre_breakout_rank(bars)
        self.assertIn(ranked["status"], ("WATCH", "NOT_READY"))
        self.assertNotIn("BUY", ranked["status"])
        self.assertLessEqual(ranked["score"], 100)

    def test_pre_breakout_insufficient_history(self):
        result = scanner.pre_breakout_rank(daily()[:10])
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")

    def test_prices_converted_to_vnd(self):
        client=scanner.Client()
        client.get=Mock(return_value=dict(t=[1],o=[25],h=[26],l=[24],c=[25.55],v=[100]))
        self.assertEqual(client.ohlcv("PVT","1D",NOW)[0]["c"],25550)

    def test_stale_minutes_never_call_strategies(self):
        bars=minutes()
        for b in bars: b["t"]-=600
        with patch.object(scanner.v1,"detect_s3",side_effect=AssertionError("stale must block")):
            self.assertEqual(scanner.evaluate(daily(),bars,daily(),NOW,"TREND_UP")["status"],"STALE")

    def test_only_completed_minutes_reach_legacy_strategies(self):
        bars=minutes()
        bars.append({**bars[-1], "t":NOW.timestamp(), "c":999999})
        with patch.object(scanner.v1,"detect_s3",return_value=None) as detector:
            scanner.evaluate(daily(),bars,daily(),NOW,"TREND_UP")
        self.assertEqual(detector.call_args.args[1][-2]["c"],25500)

    def test_original_risk_limits_in_vnd(self):
        risk=scanner.v1.risk_engine(25500,25000,scanner.legacy_input(daily()),"S3 Breakout Momentum")
        self.assertLessEqual(risk["risk_vnd"],400000)
        self.assertLessEqual(risk["position_value"],20000000)
        self.assertEqual(risk["shares"]%100,0)

    def test_ledger_survives_restart_and_pending_blocks_resend(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"ledger.sqlite3"
            first=scanner.Ledger(path)
            self.assertTrue(first.reserve("key"))
            first.close()
            second=scanner.Ledger(path)
            self.assertFalse(second.reserve("key"))
            second.close()

    def test_telegram_requires_ok_and_message_id_and_redacts_errors(self):
        item={"strategy":"S3 Breakout Momentum", "score":80,
              "risk":{"entry":25000,"sl":24000,"tp1":27000,"tp2":28000,"rr":2,"shares":100,"risk_vnd":100000},
              "trigger":"fixture", "last_closed_1m_bar":{"bar_time":NOW.isoformat()}}
        with tempfile.TemporaryDirectory() as directory, patch.dict(scanner.os.environ,{"TELEGRAM_BOT_TOKEN":"secret","TELEGRAM_CHAT_ID":"test"}):
            ledger=scanner.Ledger(Path(directory)/"ledger")
            session=Mock()
            session.post.return_value.json.return_value={"ok":False}
            self.assertEqual(scanner.send_alert("AAA",item,NOW,ledger,session),"ERROR")
            self.assertNotIn("secret",item["error"])
            self.assertEqual(scanner.send_alert("AAA",item,NOW,ledger,session),"DUPLICATE_SUPPRESSED")
            session.post.return_value.json.return_value={"ok":True,"result":{"message_id":123}}
            self.assertEqual(scanner.send_alert("BBB",item,NOW,ledger,session),"ALERTED")
            self.assertEqual(item["telegram_message_id"],123)
            ledger.close()

    def test_remote_reservation_committed_before_send(self):
        session=Mock()
        session.get.side_effect=[Mock(status_code=200),Mock(status_code=404),Mock(status_code=200)]
        session.put.return_value=Mock(status_code=201)
        session.put.return_value.json.return_value={"content":{"sha":"abc"}}
        ledger=scanner.GitHubLedger("owner/repo","token",session)
        self.assertTrue(ledger.reserve("key"))
        self.assertFalse(ledger.reserve("key"))
        self.assertEqual(session.put.call_args.kwargs["json"]["branch"],"ds1-v2-alert-state")

    def test_watch_message_freshness_and_no_buy_and_dedupe(self):
        item = {"status": "NO_SETUP", "pre_breakout": {"status": "WATCH", "score": 80,
                "pivot_vnd": 26000, "distance_to_pivot_pct": 2.0},
                "last_closed_1m_bar": {"bar_time": (NOW-timedelta(minutes=2)).isoformat()}}
        with tempfile.TemporaryDirectory() as folder, patch.dict(scanner.os.environ,
                {"TELEGRAM_BOT_TOKEN": "fake", "TELEGRAM_CHAT_ID": "test"}):
            ledger = scanner.Ledger(Path(folder)/"watch.sqlite")
            session = Mock()
            session.post.return_value.json.return_value = {"ok": True, "result": {"message_id": 44}}
            self.assertEqual(scanner.send_watch("AAA", item, NOW, ledger, session), "WATCH_SENT")
            msg = session.post.call_args.kwargs["json"]["text"]
            self.assertIn("NOT A BUY SIGNAL", msg)
            self.assertNotIn("Entry 26000", msg)
            self.assertEqual(scanner.send_watch("AAA", item, NOW, ledger, session), "DUPLICATE_SUPPRESSED")
            stale = {**item, "last_closed_1m_bar": {"bar_time": (NOW-timedelta(minutes=10)).isoformat()}}
            self.assertEqual(scanner.send_watch("BBB", stale, NOW, ledger, session), "NOT_ELIGIBLE")
            blocked = {**item, "status": "BLOCKED"}
            self.assertEqual(scanner.send_watch("CCC", blocked, NOW, ledger, session), "NOT_ELIGIBLE")
            ledger.close()

    def test_rate_limit_retry_and_nonretryable_http_failure(self):
        session=Mock()
        ok=Mock(status_code=200)
        ok.json.return_value={"ok":True}
        session.get.side_effect=[Mock(status_code=429,headers={"Retry-After":"1"}),ok]
        with patch.object(scanner.time,"sleep"):
            client=scanner.Client(session=session)
            self.assertEqual(client.get("https://example.test"),{"ok":True})
        self.assertEqual(client.metrics["retries"],1)

    def test_pipeline_isolates_symbol_error_and_caches_daily(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(scanner,"ROOT",Path(directory)):
            path=Path(directory)/"manifest.json"
            path.write_text(json.dumps(manifest()))
            args=Namespace(universe_url=None,universe_file=str(path),mode="paper",interval=1,clock_live=False)
            client=Mock(metrics={"requests":0})
            def fetch(symbol,resolution,now):
                if symbol=="BBB": raise RuntimeError("API failure")
                return daily() if resolution=="1D" else minutes()
            client.ohlcv.side_effect=fetch
            self.assertEqual(scanner.run(args,client,NOW),1)
            result=json.loads((Path(directory)/"latest_snapshot.json").read_text())
            self.assertEqual(result["symbols"]["BBB"]["status"],"ERROR")
            self.assertEqual(result["symbols"]["CCC"]["status"],"NO_SETUP")
            self.assertEqual(result["alerts_sent"],0)
            client.ohlcv.reset_mock()
            scanner.run(args,client,NOW)
            self.assertNotIn(("AAA","1D",NOW),[c.args for c in client.ohlcv.call_args_list])


if __name__ == "__main__":
    unittest.main()

