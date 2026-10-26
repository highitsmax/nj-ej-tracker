#!/usr/bin/env python3
"""NJ EJ Tracker, stream 6: federal bills. Congress.gov API -- only active if CONGRESS_API_KEY is set (free
key, instant signup per the research doc; DEMO_KEY also works unregistered at a low rate limit but isn't
relied on here). Without a key, the panel shows "not connected yet".

NOT independently tested live in this build: no Congress.gov key was available in this sandbox. The endpoint
shape below follows the documented Bill API (https://api.congress.gov/#/bill/bill_list); verify field names
against a real response once a key is added (see README).

Writes data/federal_bills.json and data/federal_bills.status.json. Run: python3 src/congress.py
"""
import json
import os
import sys
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import curl, row_id, run_stream  # noqa: E402

SEARCH_URL = 'https://api.congress.gov/v3/bill'


def run():
    key = os.environ.get('CONGRESS_API_KEY')
    if not key:
        print('federal_bills: CONGRESS_API_KEY not set; panel will show "not connected yet".')
        return []
    params = urlencode({'query': 'environmental justice', 'api_key': key, 'format': 'json', 'limit': 25, 'sort': 'updateDate+desc'})
    r = curl(f'{SEARCH_URL}?{params}')
    if not r['ok']:
        raise RuntimeError(f'Congress.gov fetch failed: {r["error"]}')
    data = json.loads(r['body'])
    rows = []
    for b in data.get('bills', []):
        rows.append({
            'id': row_id('congress', b.get('url')),
            'date': (b.get('updateDate') or '')[:10] or None,
            'title': f"{b.get('type', '')}{b.get('number', '')}: {b.get('title', '')}"[:200],
            'url': b.get('url'),
            'source': f"Congress.gov ({b.get('congress', '')}th Congress)",
            'deadline': None,
            'tags': ['federal-bill'],
            'state': 'US',
        })
    print(f'federal_bills: {len(rows)} Congress.gov result(s)')
    return rows


if __name__ == '__main__':
    sys.exit(run_stream('federal_bills', run))
