#!/usr/bin/env python3
"""NJ EJ Tracker, stream 4: grants + fellowships (v2 layout: these feed the "Opportunities" panel's
"Grants -- organizations" and "Fellowships" sub-sections).

  grants_org.json    Grants.gov search2 API (keyless POST, eligibilities 12/99 = 501(c)(3) nonprofit /
                     unrestricted) + the hand-kept data/funders.json (built here from src/funders_seed.json,
                     filtered to funders whose region covers NJ or MD/DC AND that accept unsolicited
                     proposals OR have a published open cycle -- see build_funders()).
  fellowships.json   Hand-kept, built from src/fellowships_seed.json. v2 DROPS the old Grants.gov
                     "individual eligibility 21" pull and the separate grants_individual.json file --
                     the new build brief folds fellowships into "Opportunities" as their own hand-kept
                     sub-section, not a Grants.gov search (grants.gov returned ~0 individual-eligible EJ
                     opportunities in round 1 research anyway). Logged as a cut in the build report.

Writes data/grants_org.json, data/funders.json, data/fellowships.json + their .status.json files.
Run: python3 src/grants.py
"""
import json
import os
import re
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import curl, row_id, run_stream  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEARCH2_URL = 'https://api.grants.gov/v1/api/search2'
KEYWORD = '"environmental justice"'
ELIG_ORG = '12|99'

TOPIC = re.compile(r"(environment|environmental justice|climate|pollut|air quality|water|toxic|brownfield|resilien|community|neighborhood|equity|health|energy|urban|justice)", re.I)


def search2(eligibilities):
    body = json.dumps({'keyword': KEYWORD, 'rows': 25, 'oppStatuses': 'posted|forecasted', 'eligibilities': eligibilities})
    r = curl(SEARCH2_URL, method='POST', data=body)
    if not r['ok']:
        raise RuntimeError(f'Grants.gov search2 failed: {r["error"]}')
    data = json.loads(r['body'])
    if data.get('errorcode') != 0:
        raise RuntimeError(f'Grants.gov search2 error: {data.get("msg")}')
    return data.get('data', {}).get('oppHits', [])


def to_row(h):
    close = h.get('closeDate') or ''
    deadline = None
    if close and '/' in close:
        mm, dd, yy = close.split('/')
        deadline = f'{yy}-{mm}-{dd}'
    title = (h.get('title') or '').replace('&ndash;', '-').replace('&mdash;', '-').replace('&amp;', '&')
    return {
        'id': row_id('grant', h.get('id')),
        'date': None,
        'title': f"{title} ({h.get('agencyCode', '')})",
        'url': f"https://www.grants.gov/search-results-detail/{h.get('id')}",
        'source': h.get('agency', 'Grants.gov'),
        'deadline': deadline,
        'tags': ['grants.gov'],
        'state': 'US',
        'kind': 'grant',
    }


def topical(rows):
    """Keep only titles that are plausibly EJ/community. v1 full-text keyword search returned humanities
    and newspaper grants without this filter."""
    return [r for r in rows if TOPIC.search(r.get('title', ''))]


def next_recurring_deadline(mmdd_list, today=None):
    if not mmdd_list:
        return None
    today = today or date.today()
    candidates = []
    for mmdd in mmdd_list:
        mm, dd = (int(x) for x in mmdd.split('-'))
        d = date(today.year, mm, dd)
        if d < today:
            d = date(today.year + 1, mm, dd)
        candidates.append(d)
    return min(candidates).isoformat()


def build_funders():
    """data/funders.json: src/funders_seed.json filtered to region NJ/MD/DC AND (unsolicited OR an open
    cycle). See funders_seed.json's own _note for exactly which entries this excludes and why. Row label
    stays the panel's own ('Grants -- organizations') -- never any one funder's name."""
    seed = json.load(open(os.path.join(HERE, 'funders_seed.json')))
    rows = []
    for f in seed['funders']:
        region_ok = any(t in ('NJ', 'MD', 'DC', 'national') for t in f.get('region_tags', []))
        deadline = f.get('deadline') or next_recurring_deadline(f.get('recurring_deadlines'))
        open_cycle = bool(deadline) or (isinstance(f.get('cycle'), str) and 'rolling' in f['cycle'].lower())
        if not (region_ok and (f.get('unsolicited') is True or open_cycle)):
            continue
        meta = ' · '.join(x for x in [f.get('typical_range'), f.get('cycle')] if x)
        rows.append({
            'id': row_id('funder', f['name']),
            'date': None,
            'title': f['name'],
            'url': f['url'],
            'source': meta or 'See guidelines',
            'deadline': deadline,
            'tags': ['funder'],
            'state': 'US',
            'kind': 'grant',
        })
    return rows


def build_fellowships():
    """data/fellowships.json: src/fellowships_seed.json, dropping any entry whose deadline has already
    passed (defense-in-depth -- the seed file is also hand-curated to omit those, per its own _note)."""
    seed = json.load(open(os.path.join(HERE, 'fellowships_seed.json')))
    today_s = date.today().isoformat()
    rows = []
    for f in seed['fellowships']:
        if f.get('deadline') and f['deadline'] < today_s:
            continue
        title = f['name']
        if f.get('amount_verified') and f.get('amount'):
            title = f"{title} — {f['amount']}"
        rows.append({
            'id': row_id('fellowship', f['name']),
            'date': None,
            'title': title,
            'url': f['url'],
            'source': 'Fellowship',
            'deadline': f.get('deadline'),
            'tags': ['fellowship'],
            'state': 'US',
            'kind': 'fellowship',
        })
    return rows


def run_org():
    hits = search2(ELIG_ORG)
    rows = topical([to_row(h) for h in hits])
    print(f'grants_org: {len(rows)} Grants.gov opportunities (nonprofit 501(c)(3) / unrestricted, "environmental justice")')
    return rows


def run_funders():
    rows = build_funders()
    total = len(json.load(open(os.path.join(HERE, 'funders_seed.json')))['funders'])
    print(f'funders: {len(rows)} of {total} seed funders pass the region + (unsolicited OR open-cycle) filter')
    return rows


if __name__ == '__main__':
    rc1 = run_stream('grants_org', run_org)
    rc2 = run_stream('funders', run_funders)
    rc3 = run_stream('fellowships', build_fellowships)
    sys.exit(rc1 or rc2 or rc3)
