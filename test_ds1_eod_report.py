import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from scripts.ds1_eod_report import extract_daily_close

TZ=ZoneInfo("Asia/Ho_Chi_Minh")
def bar(day,close=25100):
    return {"t":datetime(day.year,day.month,day.day,9,0,tzinfo=TZ).timestamp(),
            "o":25000,"h":26000,"l":24000,"c":close,"v":100000}

class EODTests(unittest.TestCase):
    def test_correct_day_never_falls_back_to_previous(self):
        today=date(2026,10,9)
        self.assertEqual(extract_daily_close([bar(today-timedelta(days=1)),bar(today)],today)["close_vnd"],25100)
        with self.assertRaisesRegex(ValueError,"MISSING"):
            extract_daily_close([bar(today-timedelta(days=1))],today)
    def test_duplicate_and_bad_price_are_rejected(self):
        day=date(2026,10,9)
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            extract_daily_close([bar(day),bar(day)],day)
        with self.assertRaisesRegex(ValueError,"PRICE"):
            extract_daily_close([bar(day,30000)],day)
    def test_price_stays_vnd_and_source_daily(self):
        q=extract_daily_close([bar(date(2026,10,9))],date(2026,10,9))
        self.assertEqual(q["unit"],"VND")
        self.assertEqual(q["resolution"],"1D")
