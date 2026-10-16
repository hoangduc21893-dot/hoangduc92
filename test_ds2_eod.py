from datetime import date, datetime
import unittest
from unittest.mock import Mock, patch
import requests
from scripts import ds2_eod as d

DAY = date(2026, 10, 16)
NOW = datetime(2026, 10, 16, 16, 10, tzinfo=d.ICT)


def payload(close=23.65):
    return {'t': [1792116000], 'o': [close], 'h': [close],
            'l': [close], 'c': [close], 'v': [100]}


class DS2Tests(unittest.TestCase):
    def test_scaling_and_target_date(self):
        self.assertEqual(d.closed_bar(payload(), DAY)['close_vnd'], 23650)

    def test_reject_invalid_payloads(self):
        cases = [None, {}, {'s': 'error', **payload()}]
        for key, value in [('t', []), ('t', [1792029600]), ('t', [1792202400]),
                           ('c', [float('nan')]), ('c', [True]), ('c', ['23.65']),
                           ('c', [0]), ('c', [23650]), ('v', [-1]), ('v', [0]),
                           ('h', [1]), ('t', [1792116000000])]:
            p = payload(); p[key] = value; cases.append(p)
        p = payload()
        for k in p: p[k] *= 2
        cases.append(p)
        for p in cases:
            with self.subTest(p=p), self.assertRaises((ValueError, OverflowError)):
                d.closed_bar(p, DAY)

    def test_eod_clock(self):
        for now in [NOW.replace(hour=15), NOW.replace(tzinfo=None), NOW.replace(day=15)]:
            with self.assertRaises(ValueError):
                d.collect(DAY, now, Mock())

    def test_calendar(self):
        for day in ['2026-10-17', '2026-09-02', '2026-02-18', '2026-01-02']:
            self.assertFalse(d.trading_day(date.fromisoformat(day)))
        with self.assertRaises(ValueError): d.trading_day(date(2027, 1, 4))
        session = Mock()
        self.assertEqual(d.collect(date(2026, 9, 2), NOW, session)['status'], 'NON_TRADING_DAY')
        session.get.assert_not_called()

    @patch.object(d, 'get_payload', side_effect=[payload(23.65), payload(45), payload(34)])
    def test_nav_pnl(self, fetch):
        r = d.collect(DAY, NOW, Mock())
        self.assertEqual(r['cost_basis_vnd'], 72455000)
        self.assertEqual(r['nav_vnd'], 72150000)
        self.assertEqual(r['pnl_vnd'], -305000)
        self.assertEqual([p['quantity'] for p in r['positions']], [1000, 700, 500])

    @patch.object(d, 'get_payload', side_effect=[payload(), {}, payload()])
    def test_partial_failure_blocks_nav(self, fetch):
        with self.assertRaises(ValueError): d.collect(DAY, NOW, Mock())

    def test_transport(self):
        session = Mock()
        session.get.side_effect = requests.Timeout()
        with self.assertRaises(RuntimeError): d.get_payload('PVT', DAY, session, lambda _: None)
        self.assertEqual(session.get.call_count, 3)

    def test_http_json_and_recovery(self):
        session = Mock(); response = session.get.return_value
        response.status_code = 401
        response.raise_for_status.side_effect = requests.HTTPError()
        with self.assertRaises(RuntimeError): d.get_payload('PVT', DAY, session)
        self.assertEqual(session.get.call_count, 1)
        response.raise_for_status.side_effect = None
        response.status_code = 200
        response.json.side_effect = ValueError()
        with self.assertRaises(RuntimeError): d.get_payload('PVT', DAY, session)
        response.json.side_effect = None; response.json.return_value = payload()
        self.assertEqual(d.get_payload('PVT', DAY, session), payload())
        self.assertEqual(session.get.call_args.kwargs['params']['resolution'], '1D')


if __name__ == '__main__': unittest.main()
