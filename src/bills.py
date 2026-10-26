#!/usr/bin/env python3
"""NJ EJ Tracker, stream 2: NJ state bills. NJ only (keyless NJ Legislature
bulk ZIP), trimmed down: no stage history, no alerting, no SQLite -- one flat list of currently-matched bills.

LegiScan path (other 49 states): kept as a disabled stub per the build brief ("keep the LegiScan code path
but disabled unless LEGISCAN_API_KEY is set"). NOT wired up to do a real pull in v1 -- scope is NJ only; if
you ever want other states, legiscan_note() is the place to build it out (see README).

Writes data/bills.json and data/bills.status.json. Run: python3 src/bills.py
"""
import csv
import io
import os
import re
import sys
import zipfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import EJMatcher, curl, load_rules, row_id, run_stream  # noqa: E402

NJ_BASE = 'https://pub.njleg.gov/leg-databases/{yr}data/DB{yr}_TEXT.zip'


def nj_session_year(today=None):
    y = (today or datetime.now()).year
    return y if y % 2 == 0 else y - 1


def iso_date(s):
    s = (s or '').strip()
    if not s:
        return None
    for fmt in ('%m/%d/%Y %H:%M:%S', '%m/%d/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def legiscan_note():
    """Disabled unless LEGISCAN_API_KEY is set, and even then not implemented in v1 (NJ bulk covers NJ;
    the research/plan docs scoped this build to NJ only). Returns a one-line note for the status file."""
    if os.environ.get('LEGISCAN_API_KEY'):
        return 'LEGISCAN_API_KEY is set but the LegiScan path is not wired up in v1 (NJ-only scope); see README.'
    return 'LegiScan path disabled (no LEGISCAN_API_KEY set); NJ bills come from the keyless bulk ZIP only.'


def run():
    rules = load_rules()
    matcher = EJMatcher(rules['core_terms'], rules.get('exclude_phrases'), rules.get('siting_nouns'))
    yr = nj_session_year()
    url = NJ_BASE.format(yr=yr)
    r = curl(url, timeout=90)
    if not r['ok']:
        raise RuntimeError(f'NJ Legislature bulk ZIP fetch failed: {r["error"]}')
    z = zipfile.ZipFile(io.BytesIO(r['body']))
    rd = csv.DictReader(io.TextIOWrapper(z.open('MAINBILL.TXT'), encoding='latin-1', newline=''))
    rows, n_total = [], 0
    for m in rd:
        n_total += 1
        bt, bn = (m.get('BillType') or '').strip(), (m.get('BillNumber') or '').strip()
        if not bt or not bn:
            continue
        abstract = (m.get('Abstract') or '').strip()
        synopsis = re.sub(r'\s+', ' ', m.get('Synopsis') or '').strip()
        hits = matcher.match(abstract, synopsis)
        if not hits:
            continue
        num = m.get('ActualBillNumber') or f'{bt}{bn}'
        date = iso_date(m.get('ModDate')) or iso_date(m.get('IntroDate'))
        rows.append({
            'id': row_id('NJ', str(yr), num),
            'date': date,
            'title': f'{num}: {abstract}' if abstract else f'{num}: {synopsis[:100]}',
            'url': f'https://www.njleg.state.nj.us/bill-search/{yr}/{num}',
            'source': 'NJ Legislature',
            'deadline': None,
            'tags': hits,
            'state': 'NJ',
        })
    print(f'bills: {n_total} NJ bills scanned, {len(rows)} match the EJ vocabulary. {legiscan_note()}')
    return rows


if __name__ == '__main__':
    sys.exit(run_stream('bills', run))
