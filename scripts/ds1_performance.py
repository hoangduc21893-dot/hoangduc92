"""Read-only DNSE DS1 close-to-close performance; no trading integration."""
import argparse
import csv
import hashlib
import json
import os
import tempfile
import shutil
import time as clock_time
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
import requests
from scripts import ds2_eod as eod

GROUPS = {
    '2026-09-22': 'PVT MSB HAH BSR VGC PET', '2026-09-23': 'DHC',
    '2026-09-25': 'MWG', '2026-09-29': 'PVS', '2026-10-02': 'HDB',
    '2026-10-05': 'VPB', '2026-10-08': 'PLX ANV VHC GVR',
    '2026-10-10': 'PHR DCM GMD HPG TCB',
}
CONFIG = {s: date.fromisoformat(d) for d, symbols in GROUPS.items() for s in symbols.split()}

def sessions(start, end):
    result = []
    while start <= end:
        if eod.trading_day(start):
            result.append(start)
        start += timedelta(days=1)
    return result

def effective(day):
    while not eod.trading_day(day):
        day += timedelta(days=1)
    return day

def latest_completed(now):
    if now.tzinfo is None:
        raise ValueError('timezone-aware clock required')
    now = now.astimezone(eod.ICT)
    day = now.date()
    if now.time() < time(16, 45):
        day -= timedelta(days=1)
    while not eod.trading_day(day):
        day -= timedelta(days=1)
    return day

def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()

def basis_verified(evidence, symbol, start, end, hashes):
    """Evidence must bind the exact two responses; a generic endpoint label is insufficient."""
    item = evidence.get(symbol, {})
    return (item.get('source') == eod.URL and item.get('resolution') == '1D'
            and item.get('start') == str(start) and item.get('end') == str(end)
            and item.get('payload_sha256') == hashes
            and item.get('basis') == 'same_adjusted_basis'
            and isinstance(item.get('evidence_url'), str)
            and item['evidence_url'].startswith('https://')
            and bool(item.get('reviewed_by')) and bool(item.get('explanation')))

def get_payload(symbol, day, session, sleep=clock_time.sleep):
    """Bounded GET retries, honoring Retry-After seconds without unbounded waits."""
    start = datetime.combine(day, time(), eod.ICT)
    params = {'symbol': symbol, 'resolution': '1D', 'from': int(start.timestamp()),
              'to': int((start + timedelta(days=1)).timestamp()) - 1}
    for attempt in range(5):
        delay = min(60, 2 ** attempt + random.random())
        try:
            response = session.get(eod.URL, params=params, timeout=(5, 20), headers={
                'User-Agent': 'DS1-Performance-Collector/1.0',
                'Origin': 'https://www.dnse.com.vn', 'Referer': 'https://www.dnse.com.vn/'})
            if response.status_code == 429 or response.status_code >= 500:
                retry = response.headers.get('Retry-After', '')
                if str(retry).isdigit():
                    delay = min(120, max(delay, int(retry)))
                raise requests.ConnectionError('retryable response')
            response.raise_for_status()
            return response.json()
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 4:
                raise RuntimeError(f'{symbol}: DNSE retries exhausted') from None
            sleep(delay)
        except (requests.RequestException, ValueError):
            raise RuntimeError(f'{symbol}: DNSE HTTP/JSON failure') from None


def closed_bar(payload, day):
    bar = eod.closed_bar(payload, day)
    expected = int(datetime.combine(day, time(9), eod.ICT).timestamp())
    if bar['timestamp'] != expected:
        raise ValueError('unexpected DNSE 1D session timestamp (require 09:00 ICT)')
    return bar

def collect(day, now, session, output, evidence=None):
    if now.tzinfo is None or day > now.astimezone(eod.ICT).date():
        raise ValueError('invalid clock or future date')
    if not eod.trading_day(day):
        return {'status': 'NON_TRADING_DAY', 'date': str(day), 'rows': []}
    if day > latest_completed(now):
        raise ValueError('requested session is not completed')
    rows = []
    for symbol, added in CONFIG.items():
        start = effective(added)
        row = dict(symbol=symbol, added_date=str(added), start_date=str(start),
                   end_date=str(day), start_close_vnd=None, end_close_vnd=None,
                   t_plus=None, return_pct=None, outcome=None, verified=False,
                   warning='Review corporate actions: no manual adjustment' if symbol in ('HDB', 'GMD') else '')
        try:
            if start > day:
                raise ValueError('entry session is after report session')
            hashes = []
            bars = []
            for label, target in [('start', start), ('end', day)]:
                payload = get_payload(symbol, target, session)
                h = digest(payload)
                raw = output / 'raw' / str(day) / f'{symbol}-{label}.json'
                raw.parent.mkdir(parents=True, exist_ok=True)
                raw.write_text(json.dumps({'source': eod.URL, 'session': str(target), 'symbol': symbol, 'resolution': '1D',
                    'currency': 'VND', 'price_multiplier': 1000,
                    'fetched_at': datetime.now(eod.ICT).isoformat(), 'payload_sha256': h,
                    'payload': payload}, indent=2, allow_nan=False), encoding='utf-8')
                hashes.append(h)
                bars.append(closed_bar(payload, target))
            row.update(start_close_vnd=bars[0]['close_vnd'], end_close_vnd=bars[1]['close_vnd'],
                       t_plus=len(sessions(start, day))-1, payload_sha256=hashes,
                       prices_validated=True, start_bar=bars[0], end_bar=bars[1],
                       reference_change_pct=float((Decimal(bars[1]['close_vnd']) / Decimal(bars[0]['close_vnd']) - 1) * 100),
                       price_status='PRICE_VALIDATED', returns_status='RETURNS_UNVERIFIED',
                       corporate_action_audit={'status': 'UNVERIFIED', 'manual_adjustment_applied': False,
                           'note': 'All corporate actions and DNSE adjustment basis require independent review; no additional adjustment.'})
            if not basis_verified(evidence or {}, symbol, start, day, hashes):
                raise ValueError('adjustment basis unverified: return withheld')
            value = (Decimal(bars[1]['close_vnd']) / Decimal(bars[0]['close_vnd']) - 1) * 100
            row.update(return_pct=float(value), outcome='WIN' if value > 0 else 'LOSS' if value < 0 else 'FLAT', verified=True, returns_status='VERIFIED')
        except (ValueError, RuntimeError, OverflowError) as exc:
            row['error'] = str(exc)
        rows.append(row)
    complete = len(rows) == 20 and all(r['verified'] for r in rows)
    ranked = sorted(rows, key=lambda r: r['return_pct']) if complete else []
    prices_complete = len(rows) == 20 and all(r.get('prices_validated') for r in rows)
    reference = sorted(rows, key=lambda r: (-r.get('reference_change_pct', 0), r['symbol'])) if prices_complete else []
    for rank, row in enumerate(reference, 1):
        row['reference_rank'] = rank
    return dict(status='VERIFIED' if complete else 'PRICE_VALIDATED' if prices_complete else 'BLOCKED',
        returns_status='VERIFIED' if complete else 'RETURNS_UNVERIFIED',
        reference_equal_weight_change_pct=sum(r['reference_change_pct'] for r in rows)/20 if prices_complete else None,
        reference_up=sum(r['reference_change_pct'] > 0 for r in rows) if prices_complete else None,
        reference_down=sum(r['reference_change_pct'] < 0 for r in rows) if prices_complete else None,
        reference_flat=sum(r['reference_change_pct'] == 0 for r in rows) if prices_complete else None,
        reference_ranking=[r['symbol'] for r in reference],
        provenance={'collector_commit': os.environ.get('GITHUB_SHA'), 'run_url': os.environ.get('DS1_RUN_URL'),
                    'payload_hash': 'SHA256 of json.dumps(payload, sort_keys=True, allow_nan=False), UTF-8',
                    'entry_prices': 'Historical DNSE observations fetched at collection time, not original-entry snapshots'}, date=str(day), source=eod.URL,
        resolution='1D', currency='VND', price_multiplier=1000,
        verified_count=sum(r['verified'] for r in rows), expected_count=20,
        prices_validated_count=sum(r.get('prices_validated', False) for r in rows),
        collected_at=now.isoformat(), scope='close-to-close price return; excludes fees, taxes and cash dividends; T+0 is entry session',
        equal_weight_return_pct=sum(r['return_pct'] for r in rows)/20 if complete else None,
        wins=sum(r['outcome']=='WIN' for r in rows) if complete else None,
        losses=sum(r['outcome']=='LOSS' for r in rows) if complete else None,
        flats=sum(r['outcome']=='FLAT' for r in rows) if complete else None,
        top=[r['symbol'] for r in ranked[-3:][::-1]], bottom=[r['symbol'] for r in ranked[:3]], rows=rows)

def write_report(output, report):
    (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    fields = ['symbol','added_date','start_date','end_date','start_close_vnd','end_close_vnd','t_plus','reference_rank','reference_change_pct','returns_status','return_pct','outcome','verified','warning','error']
    with (output / 'report.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(report.get('rows', []))
    lines = [f"# DS1 {report.get('date')} - {report['status']}",
             f"Verified basis: {report.get('verified_count', 0)}/20. Prices: {report.get('prices_validated_count', 0)}/20.",
             'HDB/GMD: corporate action review required; no manual adjustment is applied.',
             f"Returns: {report.get('returns_status')}. Reference equal-weight: {report.get('reference_equal_weight_change_pct')}%; up/down/flat: {report.get('reference_up')}/{report.get('reference_down')}/{report.get('reference_flat')}.",
             'Reference change is observed price movement, not verified investment or total return. Historical prices may already be adjusted.',
             '|Symbol|Entry|Start VND|End VND|T+|Rank|Reference %|Returns status|Return %|Error|', '|---|---|---:|---:|---:|---:|---:|---|---:|---|']
    for r in sorted(report.get('rows', []), key=lambda r: r.get('reference_rank', 999)):
        lines.append('|'+ '|'.join(str(r.get(k)) if r.get(k) is not None else 'N/A' for k in
            ['symbol','start_date','start_close_vnd','end_close_vnd','t_plus','reference_rank','reference_change_pct','returns_status','return_pct','error'])+'|')
    if report.get('error'):
        lines.append(report['error'])
    (output/'report.md').write_text('\n'.join(lines), encoding='utf-8')

def publish(output, report, stage):
    """Immutable dated bundles. Failed reruns only write diagnostics, never dated reports."""
    stem = 'report_' + report['date']
    target = output / (stem + '.json')
    if target.exists():
        old = json.loads(target.read_text(encoding='utf-8'))
        if old.get('prices_validated_count') == 20 and old.get('status') in ('PRICE_VALIDATED', 'VERIFIED'):
            manifest_path = output / (stem + '.sha256.json')
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            required = {stem + '.' + ext for ext in ('json', 'csv', 'md')}
            if not required.issubset(manifest) or len(manifest) != 43:
                raise ValueError('incomplete existing provenance manifest')
            for name, expected_hash in manifest.items():
                path = output / name
                if path.resolve().is_relative_to(output.resolve()) is False or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
                    raise ValueError('existing bundle hash mismatch')
            # The first valid bundle is immutable, including its raw provenance.
            return False
        raise ValueError('existing dated bundle is not valid; manual review required')
    write_report(stage, report)
    evidence = output / 'raw' / report['date']
    evidence.parent.mkdir(parents=True, exist_ok=True)
    if evidence.exists():
        raise ValueError('orphan raw evidence requires manual review')
    shutil.copytree(stage / 'raw' / report['date'], evidence)
    # JSON is the completion marker and is published last.
    for ext in ('csv', 'md', 'json'):
        temp = output / (stem + '.' + ext + '.tmp')
        shutil.copyfile(stage / ('report.' + ext), temp)
        temp.replace(output / (stem + '.' + ext))
    manifest = {}
    for path in sorted([*evidence.glob('*.json'), *output.glob(stem + '.*')]):
        manifest[str(path.relative_to(output))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (output / (stem + '.sha256.json')).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return True

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', type=date.fromisoformat)
    parser.add_argument('--output', type=Path, default=Path('data/ds1_performance'))
    parser.add_argument('--basis-evidence', type=Path)
    args = parser.parse_args()
    now = datetime.now(eod.ICT)
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        day = args.date or latest_completed(now)
        evidence = json.loads(args.basis_evidence.read_text(encoding='utf-8')) if args.basis_evidence else {}
        with requests.Session() as session:
            with tempfile.TemporaryDirectory(prefix='ds1-') as staging:
                stage = Path(staging)
                report = collect(day, now, session, stage, evidence)
                if report['status'] in ('VERIFIED', 'PRICE_VALIDATED'):
                    publish(args.output, report, stage)
                elif report['status'] != 'NON_TRADING_DAY':
                    diagnostic = args.output / 'diagnostics' / now.strftime('%Y%m%dT%H%M%S%f')
                    shutil.copytree(stage, diagnostic)
                    write_report(diagnostic, report)
    except Exception as exc:
        report = {'status': 'ERROR', 'date': str(args.date), 'error': str(exc), 'rows': []}
    if report['status'] not in ('VERIFIED', 'PRICE_VALIDATED', 'NON_TRADING_DAY'):
        write_report(args.output, report)
    if report['status'] == 'PRICE_VALIDATED':
        print('::warning::20/20 prices validated; RETURNS_UNVERIFIED; no manual adjustment applied.')
    print(json.dumps(report, indent=2, allow_nan=False))
    raise SystemExit(0 if report['status'] in ('VERIFIED', 'PRICE_VALIDATED', 'NON_TRADING_DAY') else 1)

if __name__ == '__main__':
    main()
