"""Read-only S4 audit; never mutates DS1 or emits orders. Standard-library only."""
import argparse
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import hashlib
import json
import math
import urllib.request

ICT = ZoneInfo('Asia/Ho_Chi_Minh')
SYMBOLS = ['SSI', 'VCI', 'KDH', 'NLG', 'TPB']
BASE = 'https://services.entrade.com.vn/chart-api/v2/ohlcs/'
HOLIDAYS = {'2026-01-01','2026-01-02','2026-02-16','2026-02-17','2026-02-18','2026-02-19','2026-02-20','2026-04-27','2026-04-30','2026-05-01','2026-08-31','2026-09-01','2026-09-02'}

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')

def validate(payload, target, index=False):
    if not isinstance(payload, dict) or payload.get('s') not in (None, 'ok'):
        raise ValueError('invalid envelope')
    arrays = [payload.get(k) for k in 'tohlcv']
    if any(not isinstance(a, list) for a in arrays) or len({len(a) for a in arrays}) != 1:
        raise ValueError('missing/unequal arrays')
    out = []
    for row in zip(*arrays):
        if any(isinstance(x, bool) or not isinstance(x, (int,float)) or not math.isfinite(x) for x in row):
            raise ValueError('non-numeric/nonfinite')
        t,o,h,l,c,v = row
        if not 946684800 <= t <= 4102444800 or int(t) != t:
            raise ValueError('timestamp must be epoch seconds')
        day = datetime.fromtimestamp(t, ICT).date()
        if day > target or (out and (t <= out[-1]['t'] or str(day) <= out[-1]['date'])):
            raise ValueError('future/unordered/duplicate daily timestamp')
        if not 0 < l <= min(o,c) <= max(o,c) <= h or v < 0 or int(v) != v:
            raise ValueError('invalid OHLC/volume')
        scale = 1 if index else 1000  # repo endpoint contract, not magnitude inference
        out.append(dict(t=t,date=str(day),o=o*scale,h=h*scale,l=l*scale,c=c*scale,v=v))
    if len(out) < 100 or out[-1]['date'] != str(target):
        raise ValueError(f'need >=100 bars and exact EOD; received {len(out)}, latest {out[-1]["date"] if out else None}')
    days = set(b['date'] for b in out)
    expected = []
    d = date.fromisoformat(out[0]['date'])
    while d <= target:
        if d.weekday()<5 and str(d) not in HOLIDAYS:
            expected.append(str(d))
        d += timedelta(days=1)
    missing = sorted(set(expected)-days)
    unexpected = sorted(days-set(expected))
    if missing or unexpected:
        raise ValueError(f'calendar mismatch missing={missing}, unexpected={unexpected}')
    return out

def wilder(values, n=14):
    result = sum(values[:n])/n
    for x in values[n:]:
        result = (result*(n-1)+x)/n
    return result

def metrics(bars, benchmark):
    c = [b['c'] for b in bars]
    last, prev = bars[-1], bars[-2]
    ma20, ma50 = sum(c[-20:])/20, sum(c[-50:])/50
    delta = [b-a for a,b in zip(c,c[1:])]
    gain, loss = wilder([max(x,0) for x in delta]), wilder([max(-x,0) for x in delta])
    rsi = 100-100/(1+gain/loss) if loss else (100 if gain else 50)
    tr = [max(b['h']-b['l'],abs(b['h']-a['c']),abs(b['l']-a['c'])) for a,b in zip(bars,bars[1:])]
    atr = wilder(tr)
    adv = sum(b['v'] for b in bars[-21:-1])/20
    vr = last['v']/adv if adv else None
    avg_inclusive = sum(b['v'] for b in bars[-20:])/20
    rs = None
    if benchmark:
        bm = {b['date']:b['c'] for b in benchmark}
        if [b['date'] for b in bars[-21:]] == [b['date'] for b in benchmark[-21:]]:
            rs = c[-1]/c[-21]-bm[last['date']]/bm[bars[-21]['date']]
    gates = {'ma20_above_ma50':ma20>ma50,'near_ma20_1_5pct':abs(c[-1]/ma20-1)<=.015,
             'bullish_body':c[-1]>last['o'],'higher_close':c[-1]>prev['c'],
             's4_volume_contraction':last['v']<=avg_inclusive*1.10,
             'required_volume_ratio_1_5':vr is not None and vr>=1.5}
    # Public research score, no RR/BUY target fabricated. Max 100.
    components = {'trend':25 if c[-1]>ma20>ma50 else 10 if ma20>ma50 else 0,
                  'pullback':25 if gates['near_ma20_1_5pct'] else 0,
                  'reversal':10*int(gates['bullish_body'])+10*int(gates['higher_close']),
                  'volume':15 if vr is not None and vr>=1.5 else 0,
                  'relative_strength':None if rs is None else 15 if rs>=.05 else 10 if rs>=.02 else 5 if rs>=0 else 0}
    score = sum(components.values()) if rs is not None else None
    gates['watch_score_80'] = None if score is None else score>=80
    failed = [k for k,v in gates.items() if v is False]
    return {'close_vnd':c[-1],'eod_timestamp':last['t'],'eod_ict':datetime.fromtimestamp(last['t'],ICT).isoformat(),
            'distance_ma20_pct':100*(c[-1]/ma20-1),
            'ma20_vnd':ma20,'ma50_vnd':ma50,'rsi14_wilder':rsi,
            'rs20_fraction':rs,'atr14_wilder_vnd':atr,'atr14_pct':100*atr/c[-1],
            'volume_shares':last['v'],'adv20_prior_shares':adv,'volume_ratio':vr,
            'avg20_daily_close_times_volume_vnd':sum(b['c']*b['v'] for b in bars[-20:])/20,
            'liquidity_note':'close*volume proxy, not actual turnover; no liquidity gate supplied',
            'pivot_prior20_high_vnd':max(b['h'] for b in bars[-21:-1]),
            'base_prior20_low_vnd':min(b['l'] for b in bars[-21:-1]),
            'score':score,'score_components':components,'gates':gates,
            'technical_failures':failed,
            'status':'FAIL' if failed else 'BLOCKED',
            'blockers':['corporate-action calendar and provider adjustment basis not certified']+([] if rs is not None else ['benchmark unavailable']),
            'large_gaps_gt7pct':[b['date'] for a,b in zip(bars,bars[1:]) if abs(b['o']/a['c']-1)>.07]}

def collect(target, root):
    now = datetime.now(ICT)
    if target.year != 2026 or target>now.date() or (target==now.date() and now.time()<time(16,30)):
        raise ValueError('require covered calendar and closed EOD >=16:30 ICT')
    root.mkdir(parents=True,exist_ok=True)
    evidence = root/'evidence'
    evidence.mkdir(exist_ok=True)
    fetched, provenance = {}, []
    for symbol in SYMBOLS+['VNINDEX']:
        kind = 'index' if symbol=='VNINDEX' else 'stock'
        start = datetime.combine(target-timedelta(days=220),time(),ICT)
        end = datetime.combine(target+timedelta(days=1),time(),ICT)
        url = BASE+kind+f'?symbol={symbol}&resolution=1D&from={int(start.timestamp())}&to={int(end.timestamp())-1}'
        info = {'symbol':symbol,'url':url,'retrieved_at':datetime.now(ICT).isoformat()}
        try:
            req = urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Origin':'https://www.dnse.com.vn','Referer':'https://www.dnse.com.vn/'})
            with urllib.request.urlopen(req,timeout=25) as response:
                raw=response.read()
                info['http_status']=response.status
            (evidence/f'{symbol}.json').write_bytes(raw)
            info['sha256']=hashlib.sha256(raw).hexdigest()
            payload=json.loads(raw)
            bars=validate(payload,target,kind=='index')
            fetched[symbol]=bars
            info.update(bar_count=len(bars),first_date=bars[0]['date'],last_date=bars[-1]['date'],missing_sessions=[],price_unit='index points' if kind=='index' else '1000 VND converted once to VND',volume_unit='shares (repo contract)' if kind=='stock' else 'provider index volume')
        except Exception as exc:
            info['error']=str(exc)
        provenance.append(info)
    rows=[]
    for symbol in SYMBOLS:
        row={'symbol':symbol,'rank':None}
        if symbol in fetched:
            row.update(metrics(fetched[symbol],fetched.get('VNINDEX')))
        else:
            row.update(status='BLOCKED',score=None,blockers=[next(p.get('error') for p in provenance if p['symbol']==symbol)])
        rows.append(row)
    rows.sort(key=lambda r: (r['score'] is None,-(r['score'] or 0),r['symbol']))
    for rank,row in enumerate(rows,1):
        if row['score'] is not None: row['rank']=rank
    report={'as_of':str(target),'collected_at':now.isoformat(),'benchmark':'VNINDEX',
            'ranking_basis':'provisional raw-provider technical score; not eligibility rank',
            'corporate_actions':{'status':'UNVERIFIED','adjustment_applied':False,'note':'Chart payload has no adjustment metadata. Search is not a complete rights calendar. No inferred or double adjustment. All metrics provisional on provider basis.'},
            'thresholds':{'watch_score_min':80,'volume_ratio_min':1.5},
            'strategy_note':'Literal repo S4 daily contraction <=1.10*inclusive ADV20 retained; user volume >=1.5*prior ADV20 retained. These same-day gates are incompatible. Intraday confirmation is outside this 1D WATCH audit, never claimed.',
            'benchmark_eod':fetched.get('VNINDEX',[None])[-1],
            'rows':rows,'provenance':provenance,'ds1_watch_proposals':[], 'buy_signals':[]}
    dump(root/'report.json',report)
    lines=['# S4 EOD research '+str(target),'','Research only; DS1 unchanged; no BUY.','',report['strategy_note'],'',
           'Score = trend (25 if close>MA20>MA50, 10 if MA20>MA50, else 0) + near MA20 within 1.5% (25) + bullish body (10) + higher close (10) + VR>=1.5 (15) + RS20 (15 if >=5pp, 10 if >=2pp, 5 if >=0, else 0). Score >=80 AND all S4 gates AND VR>=1.5 required. No threshold optimized after results.','',
           'RS20 = stock 20-session return minus VNINDEX return on exactly matching endpoint dates. Wilder RSI/ATR seeded from first 14 changes/TRs. MA includes target EOD. VR excludes target from prior20 denominator. Pivot/base = prior20 high/low, descriptive, not a certified pattern. Liquidity = mean20(close*volume), proxy only.','',
           'Rights/adjustment basis UNVERIFIED; metrics provisional. No adjustment applied. Calendar: existing scripts/ds2_eod.py 2026 holiday list. Missing/extra weekdays fail closed.','',
           '|Rank|Symbol|Status|Close VND|MA20|MA50|RSI14|RS20 pp|ATR14 VND|VR|Score|',
           '|---|---|---|---|---|---|---|---|---|---|---|']
    def fmt(x): return 'N/A' if x is None else f'{x:.4f}'
    for r in rows:
        vals=[r['rank'],r['symbol'],r['status']]+[fmt(r.get(k)) for k in ['close_vnd','ma20_vnd','ma50_vnd','rsi14_wilder']]+[fmt(None if r.get('rs20_fraction') is None else r['rs20_fraction']*100)]+[fmt(r.get(k)) for k in ['atr14_wilder_vnd','volume_ratio','score']]
        lines.append('|'+ '|'.join(str(x) for x in vals)+'|')
    for r in rows:
        lines += ['',r['symbol']+': '+json.dumps({k:r.get(k) for k in ['technical_failures','blockers','pivot_prior20_high_vnd','base_prior20_low_vnd','avg20_daily_close_times_volume_vnd','large_gaps_gt7pct']},ensure_ascii=False)]
    lines+=['','No DS1 WATCH additions. See report.json for source URLs, timestamps, validation and all numeric fields. Raw API bytes and SHA256 hashes in evidence/ and manifest.json.']
    (root/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    dump(root/'manifest.json',{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file() and p.name!='manifest.json'})
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--date',type=date.fromisoformat,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(collect(a.date,a.output),ensure_ascii=False,indent=2))
