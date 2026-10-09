import unittest
from datetime import datetime, date, timezone
from scripts.vn30f_health_report import summarize, render, TZ

def run_at(hour,minute,conclusion="success",event="schedule"):
    dt=datetime(2026,10,9,hour,minute,tzinfo=TZ).astimezone(timezone.utc)
    return {"created_at":dt.isoformat().replace("+00:00","Z"),"conclusion":conclusion,"event":event}

class HealthTests(unittest.TestCase):
    def test_session_filter_and_gap(self):
        s=summarize([run_at(8,40),run_at(9,0),run_at(9,5),run_at(9,30),run_at(12,0)],date(2026,10,9))
        self.assertEqual(s["runs"],3)
        self.assertEqual(s["max_gap_minutes"],25)
        self.assertIn("WARN",render(s))
    def test_failures(self):
        s=summarize([run_at(9,0,"failure")],date(2026,10,9))
        self.assertEqual(s["failed_or_cancelled"],1)
        self.assertIn("WARN",render(s))
    def test_no_runs(self):
        self.assertIn("WARN",render(summarize([],date(2026,10,9))))
    def test_api_failure_not_success(self):
        self.assertIn("UNKNOWN",render(summarize([],date(2026,10,9)),"HTTPError"))
    def test_manual_runs_excluded(self):
        self.assertEqual(summarize([run_at(9,0,event="workflow_dispatch")],date(2026,10,9))["runs"],0)

if __name__=="__main__": unittest.main()
