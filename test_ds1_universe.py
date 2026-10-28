"""Archive migration: preserve original entries while excluding setup scans."""
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch
from tempfile import TemporaryDirectory
from scripts import ds1_universe as u, ds1_performance as p
from scripts import ds1_watch as live, ds1_prebreakout_paper as paper
from scripts.ds1_paper_watch import run, present

class ArchiveTests(unittest.TestCase):
    def test_shared_scan_universe_and_original_entries(self):
        self.assertEqual(len(u.ACTIVE),18)
        self.assertEqual(len(set(u.ACTIVE)),18)
        self.assertEqual(set(u.ARCHIVED),{'BSR','GVR'})
        self.assertFalse(set(u.ACTIVE)&set(u.ARCHIVED))
        self.assertEqual(set(p.CONFIG),set(u.ACTIVE)|set(u.ARCHIVED))
        self.assertEqual(live.DS1,list(u.ACTIVE))
        self.assertEqual(paper.ACTIVE+paper.WATCH_RISK,u.ACTIVE)
        self.assertEqual(str(p.CONFIG['BSR']),'2026-09-22')
        self.assertEqual(str(p.CONFIG['GVR']),'2026-10-08')

    @patch.object(p,'get_payload')
    def test_archive_collection_and_separate_statistics(self,fetch):
        day=date(2026,10,23)
        def payload(symbol, session_day, session):
            c=20 if session_day==day else 10
            if symbol in u.ARCHIVED and session_day==day: c=5
            return dict(t=[int(datetime.combine(session_day,p.time(9),p.eod.ICT).timestamp())],o=[c],h=[c],l=[c],c=[c],v=[100])
        fetch.side_effect=payload
        with TemporaryDirectory(dir='.') as tmp:
            r=p.collect(day,datetime(2026,10,23,17,tzinfo=p.eod.ICT),Mock(),Path(tmp))
            self.assertEqual(r['prices_validated_count'],20)
            self.assertEqual(fetch.call_count,40)
            self.assertEqual(r['cohorts']['ACTIVE']['count'],18)
            self.assertEqual(r['cohorts']['ARCHIVED']['count'],2)
            self.assertEqual(r['cohorts']['ACTIVE']['reference_equal_weight_change_pct'],100)
            self.assertEqual(r['cohorts']['ARCHIVED']['reference_equal_weight_change_pct'],-50)
            self.assertEqual(r['reference_equal_weight_change_pct'],85)
            self.assertIsNone(r['equal_weight_return_pct'])
            self.assertTrue(all(x['return_pct'] is None for x in r['rows']))
            p.write_report(Path(tmp),r)
            self.assertIn('ARCHIVED',(Path(tmp)/'report.csv').read_text(encoding='utf-8-sig'))
            self.assertIn('ACTIVE: 18',(Path(tmp)/'report.md').read_text())

    def test_historical_cohort_not_rewritten(self):
        self.assertEqual(u.membership('BSR',date(2026,10,22)),'ACTIVE')
        self.assertEqual(u.membership('BSR',date(2026,10,23)),'ARCHIVED')
        self.assertEqual(u.membership('GVR',date(2026,10,23)),'ARCHIVED')

    @patch('scripts.ds1_paper_watch.compare')
    def test_paper_run_excludes_archives_and_rejects_duplicate_missing(self,compare):
        compare.return_value={'symbols':[{'symbol':s,'v1':None,'v2':{'score':80,'gates':[],'metrics':{}}} for s in u.ACTIVE]}
        with TemporaryDirectory(dir='.') as tmp:
            r=run('2026-10-23',Mock(),Path(tmp)/'paper.json')
            self.assertEqual(r['candidate_count'],18)
            self.assertEqual(compare.call_args.args[0],u.ACTIVE)
            self.assertFalse(set(u.ARCHIVED)&{x['symbol'] for x in r['rows']})
            compare.return_value['symbols'][-1]=compare.return_value['symbols'][0]
            with self.assertRaises(ValueError):run('2026-10-23',Mock(),Path(tmp)/'bad.json')

if __name__=='__main__':unittest.main()
