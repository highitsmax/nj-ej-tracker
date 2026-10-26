#!/usr/bin/env python3
"""NJ EJ Tracker, stream 4: grants. Grants.gov search2 API (keyless POST, confirmed live 2026-10-25) split into
two lists per the build brief:

  grants_org.json         "organizations could apply" -- eligibilities 12 (501(c)(3) nonprofits, other than higher ed)
                           and 99 (Unrestricted, open to any entity type).
  grants_individual.json  "individuals could apply" -- eligibilities 21 (Individuals), PLUS the hand-kept
                           data/fellowships.json (Switzer, Agents of Change -- grants.gov itself returned 0
                           individual-eligible EJ opportunities on 2026-10-25, consistent with the research
                           doc's finding that grants.gov is overwhelmingly org-only).

Eligibility codes were NOT taken from memory: each was confirmed live by calling
POST https://api.grants.gov/v1/api/fetchOpportunity on real opportunities and reading the applicantTypes
list the API itself returns. Confirmed 2026-10-25:
  12 = "Nonprofits having a 501(c)(3) status with the IRS, other than institutions of higher education"
  99 = "Unrestricted (i.e., open to any type of entity above), subject to any clarification in text field..."
  21 = "Individuals"
Multiple eligibility codes are OR'd with "|" (same separator grants.gov uses for oppStatuses); confirmed live.

Writes data/grants_org.json, data/grants_individual.json + their .status.json files. Run: python3 src/grants.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR, curl, load_json, row_id, run_stream  # noqa: E402

SEARCH2_URL = 'https://api.grants.gov/v1/api/search2'
KEYWORD = '"environmental justice"'
ELIG_ORG = '12|99'
ELIG_INDIVIDUAL = '21'


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
    }


import re as _re
TOPIC = _re.compile(r"(environment|environmental justice|climate|pollut|air quality|water|toxic|brownfield|resilien|community|neighborhood|equity|health|energy|urban|justice)", _re.I)


def topical(rows):
    """Keep only titles that are plausibly EJ/community. Added 2026-10-25: v1's full-text keyword
    search returned humanities and newspaper grants."""
    return [r for r in rows if TOPIC.search(r.get('title', ''))]


def run_org():
    hits = search2(ELIG_ORG)
    rows = topical([to_row(h) for h in hits])
    print(f'grants_org: {len(rows)} Grants.gov opportunities (nonprofit 501(c)(3) / unrestricted, "environmental justice")')
    return rows


def run_individual():
    hits = search2(ELIG_INDIVIDUAL)
    rows = topical([to_row(h) for h in hits])
    fellowships = load_json(os.path.join(DATA_DIR, 'fellowships.json'), [])
    print(f'grants_individual: {len(hits)} Grants.gov individual-eligible hits + {len(fellowships)} hand-kept fellowships')
    return rows + fellowships


if __name__ == '__main__':
    rc1 = run_stream('grants_org', run_org)
    rc2 = run_stream('grants_individual', run_individual)
    sys.exit(rc1 or rc2)
