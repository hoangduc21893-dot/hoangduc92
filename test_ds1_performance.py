from contextlib import contextmanager
import shutil
import uuid
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch, Mock
from scripts import ds1_performance as d

DAY = date(2026, 10, 16)
NOW = datetime(2026, 10, 16, 17, tzinfo=d.eod.ICT)

@contextmanager
def temporary_directory():
    path = Path('test-output-' + uuid.uuid4().hex)
    path.mkdir()
    try:
        yield str(path)
    finally:
        shutil.rmtree(path)

def payload(symbol, day, session):
    c = 20 if day == DAY else 10
    return dict(t=[int(datetime.combine(day, d.time(9), d.eod.ICT).timestamp())],
                o=[c], h=[c], l=[c], c=[c], v=[100])

class PerformanceTests(unittest.TestCase):
    def test_config_calendar(self):
        self.assertEqual(len(d.CONFIG), 20)
        self.assertEqual(str(d.effective(date(2026, 10, 10))), '2026-10-12')
        self.assertEqual(len(d.sessions(date(2026, 10, 12), DAY))-1, 4)
        with self.assertRaises(ValueError): d.effective(date(2027, 1, 1))

    def test_latest(self):
        self.assertEqual(d.latest_completed(NOW.replace(hour=15)), date(2026, 10, 15))
        self.assertEqual(d.latest_completed(NOW.replace(day=18)), DAY)
        with self.assertRaises(ValueError): d.latest_completed(NOW.replace(tzinfo=None))

    @patch.object(d.eod, 'get_payload', side_effect=payload)
    def test_basis_blocks_all_statistics(self, fetch):
        with temporary_directory() as tmp:
            r = d.collect(DAY, NOW, Mock(), Path(tmp))
            self.assertEqual(r['status'], 'BLOCKED')
            self.assertEqual(r['prices_validated_count'], 20)
            self.assertEqual(r['verified_count'], 0)
            self.assertIsNone(r['equal_weight_return_pct'])
            self.assertTrue(all(x['return_pct'] is None for x in r['rows']))
            self.assertEqual(len(list((Path(tmp)/'raw').glob('*.json'))), 40)
            d.write_report(Path(tmp), r)
            self.assertTrue((Path(tmp)/'report.csv').exists())

    @patch.object(d.eod, 'get_payload', side_effect=payload)
    def test_verified_and_tamper(self, fetch):
        evidence = {}
        for symbol, added in d.CONFIG.items():
            start = d.effective(added)
            evidence[symbol] = dict(source=d.eod.URL, resolution='1D', start=str(start), end=str(DAY),
                payload_sha256=[d.digest(payload(symbol,start,None)),d.digest(payload(symbol,DAY,None))],
                basis='same_adjusted_basis', evidence_url='https://example.org/test-fixture-only',
                reviewed_by='unit test fixture', explanation='synthetic adjusted series')
        with temporary_directory() as tmp:
            r = d.collect(DAY, NOW, Mock(), Path(tmp), evidence)
            self.assertEqual(r['verified_count'], 20)
            self.assertEqual(r['wins'], 20)
            self.assertEqual(r['equal_weight_return_pct'], 100)
            evidence['HDB']['payload_sha256'][0] = 'wrong'
            r = d.collect(DAY, NOW, Mock(), Path(tmp), evidence)
            self.assertEqual(r['verified_count'], 19)
            self.assertIsNone(r['equal_weight_return_pct'])

    @patch.object(d.eod, 'get_payload', return_value={})
    def test_missing_data_and_clock(self, fetch):
        with temporary_directory() as tmp:
            r = d.collect(DAY, NOW, Mock(), Path(tmp))
            self.assertEqual(r['prices_validated_count'], 0)
            self.assertEqual(len(r['rows']), 20)
            with self.assertRaises(ValueError):
                d.collect(DAY, NOW.replace(hour=15), Mock(), Path(tmp))
            self.assertEqual(d.collect(date(2026,10,17), NOW.replace(day=18), Mock(), Path(tmp))['status'], 'NON_TRADING_DAY')

if __name__ == '__main__': unittest.main()
