import copy
from datetime import date,datetime,time,timedelta
import json
from pathlib import Path
import unittest
from scripts.s4_eod_research import validate,metrics,wilder,ICT,HOLIDAYS

class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.target=date(2026,10,21)
        days=[]
        d=date(2026,3,16)
        while d<=self.target:
            if d.weekday()<5 and str(d) not in HOLIDAYS: days.append(d)
            d+=timedelta(days=1)
        self.p={'t':[int(datetime.combine(d,time(9),ICT).timestamp()) for d in days],
                'o':[20]*len(days),'h':[21]*len(days),'l':[19]*len(days),'c':[20]*len(days),'v':[100]*len(days)}
    def test_units_flat_indicators_rs(self):
        b=validate(self.p,self.target)
        m=metrics(b,validate(self.p,self.target,True))
        self.assertEqual(m['close_vnd'],20000)
        self.assertEqual(m['rsi14_wilder'],50)
        self.assertEqual(m['atr14_wilder_vnd'],2000)
        self.assertEqual(m['rs20_fraction'],0)
        self.assertEqual(m['volume_ratio'],1)
    def test_invalid_payloads(self):
        for mutation in ['length','duplicate','ms','nan','bounds','missing','future']:
            p=copy.deepcopy(self.p)
            if mutation=='length': p['v'].pop()
            if mutation=='duplicate': p['t'][-1]=p['t'][-2]
            if mutation=='ms': p['t'][-1]*=1000
            if mutation=='nan': p['c'][-1]=float('nan')
            if mutation=='bounds': p['c'][-1]=99
            if mutation=='missing':
                for a in p.values(): a.pop(70)
            if mutation=='future': p['t'][-1]+=86400
            with self.subTest(mutation=mutation),self.assertRaises(ValueError): validate(p,self.target)
    def test_no_benchmark_not_zero_rs(self):
        m=metrics(validate(self.p,self.target),None)
        self.assertIsNone(m['score'])
        self.assertIsNone(m['rs20_fraction'])
    def test_volume_excludes_current_and_s4_conflict(self):
        self.p['v'][-1]=150
        m=metrics(validate(self.p,self.target),None)
        self.assertEqual(m['volume_ratio'],1.5)
        self.assertTrue(m['gates']['required_volume_ratio_1_5'])
        self.assertFalse(m['gates']['s4_volume_contraction'])
    def test_wilder_known(self):
        self.assertEqual(wilder([14]*14+[28]),15)
    def test_live_evidence_reproduces(self):
        root=Path('research/s4/2026-10-21')
        if not (root/'report.json').exists(): self.skipTest('live audit not collected')
        report=json.loads((root/'report.json').read_text(encoding='utf-8'))
        bm=validate(json.loads((root/'evidence/VNINDEX.json').read_text()),self.target,True)
        for row in report['rows']:
            b=validate(json.loads((root/f'evidence/{row["symbol"]}.json').read_text()),self.target)
            actual=metrics(b,bm)
            for key in ['close_vnd','ma20_vnd','ma50_vnd','rsi14_wilder','rs20_fraction','atr14_wilder_vnd','volume_ratio','score','status']:
                self.assertEqual(actual[key],row[key])

if __name__=='__main__': unittest.main()
