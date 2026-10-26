#!/usr/bin/env python3
"""NJ EJ Tracker, stream 5: jobs. USAJOBS Search API -- only active if USAJOBS_API_KEY and USAJOBS_EMAIL are
both set (USAJOBS requires a registered key + a userEmail header on every call, free, ~1 day turnaround per
the research doc). Without both, the panel shows "not connected yet" (this script writes an empty list, not
an error -- an unconfigured stream isn't a failed one).

NOT independently tested live in this build: no USAJOBS key was available in this sandbox. The query shape
below follows USAJOBS's documented Search API (https://developer.usajobs.gov/api-reference/get-api-search);
verify the field names against a real response once a key is available (see README).

Writes data/jobs.json and data/jobs.status.json. Run: python3 src/jobs.py
"""
import json
import os
import sys
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import curl, row_id, run_stream  # noqa: E402

SEARCH_URL = 'https://data.usajobs.gov/api/search'


def run():
    key, email = os.environ.get('USAJOBS_API_KEY'), os.environ.get('USAJOBS_EMAIL')
    if not (key and email):
        print('jobs: USAJOBS_API_KEY / USAJOBS_EMAIL not set; panel will show "not connected yet".')
        return []
    params = urlencode({'Keyword': 'environmental justice', 'ResultsPerPage': 25})
    r = curl(f'{SEARCH_URL}?{params}', headers=[
        f'Authorization-Key: {key}', f'User-Agent: {email}', f'Host: data.usajobs.gov',
    ])
    if not r['ok']:
        raise RuntimeError(f'USAJOBS fetch failed: {r["error"]}')
    data = json.loads(r['body'])
    rows = []
    for item in data.get('SearchResult', {}).get('SearchResultItems', []):
        d = item.get('MatchedObjectDescriptor', {})
        close = (d.get('ApplicationCloseDate') or '')[:10] or None
        pos_loc = ', '.join(l.get('LocationName', '') for l in (d.get('PositionLocation') or []))[:120]
        rows.append({
            'id': row_id('usajobs', d.get('PositionID')),
            'date': (d.get('PublicationStartDate') or '')[:10] or None,
            'title': f"{d.get('PositionTitle', '')} ({pos_loc})" if pos_loc else d.get('PositionTitle', ''),
            'url': d.get('PositionURI') or d.get('ApplyURI', [None])[0],
            'source': d.get('DepartmentName', 'USAJOBS'),
            'deadline': close,
            'tags': ['federal'],
            'state': 'US',
        })
    print(f'jobs: {len(rows)} USAJOBS result(s)')
    return rows


if __name__ == '__main__':
    sys.exit(run_stream('jobs', run))
