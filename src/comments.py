#!/usr/bin/env python3
"""NJ EJ Tracker, stream 3: open comment periods. Federal Register API (keyless, always runs) + Regulations.gov
(needs REGS_API_KEY; skipped otherwise). Parameter names verified live against
https://www.federalregister.gov/developers/documentation/api/v1 on 2026-10-25 (conditions[term],
conditions[type][], conditions[publication_date][gte] -- confirmed by a live call, not from memory).

Federal Register's term search is full-text over the whole document, not just the title (confirmed live: a
quoted "environmental justice" phrase still pulls boilerplate NEPA-consideration notices). We narrow with a
publication-date floor (last ~120 days) and keep only items with a comments_close_on date of today or later
(per the build brief: never show a closed comment period).

Writes data/comments.json and data/comments.status.json. Run: python3 src/comments.py
"""
import json
import re
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import EJMatcher, curl, load_rules, row_id, run_stream, today  # noqa: E402

FR_URL = 'https://www.federalregister.gov/api/v1/documents.json'
FR_TERM = '"environmental justice"'
FIELDS = ['title', 'html_url', 'publication_date', 'type', 'comments_close_on', 'agencies', 'comment_url']


def fetch_federal_register():
    since = (datetime.now(timezone.utc) - timedelta(days=120)).date().isoformat()
    params = [
        ('conditions[term]', FR_TERM),
        ('conditions[type][]', 'PRORULE'),
        ('conditions[type][]', 'NOTICE'),
        ('conditions[publication_date][gte]', since),
        ('order', 'newest'),
        ('per_page', '50'),
    ]
    for f in FIELDS:
        params.append(('fields[]', f))
    url = FR_URL + '?' + urlencode(params)
    r = curl(url)
    if not r['ok']:
        raise RuntimeError(f'Federal Register fetch failed: {r["error"]}')
    data = json.loads(r['body'])
    rows = []
    tdy = today()
    for d in data.get('results', []):
        close = d.get('comments_close_on')
        if not close or close < tdy:
            continue  # only open comment periods (spec: today or later)
        agencies = ', '.join(a.get('name', '') for a in (d.get('agencies') or []))[:120]
        rows.append({
            'id': row_id('fr', d.get('html_url')),
            'date': d.get('publication_date'),
            'title': d.get('title', '')[:200],
            'url': d.get('comment_url') or d.get('html_url'),
            'source': f"Federal Register ({agencies})" if agencies else 'Federal Register',
            'deadline': close,
            'tags': [d.get('type', '').lower()],
            'state': 'US',
        })
    return rows


def fetch_regulations_gov():
    key = os.environ.get('REGS_API_KEY')
    if not key:
        print('comments: REGS_API_KEY not set; Regulations.gov skipped (Federal Register only).')
        return []
    url = ('https://api.regulations.gov/v4/documents?filter[searchTerm]=environmental+justice'
           f'&page[size]=25&sort=-postedDate&api_key={key}')
    r = curl(url)
    if not r['ok']:
        print(f'comments: Regulations.gov fetch failed ({r["error"]}); continuing with Federal Register only.')
        return []
    data = json.loads(r['body'])
    rows = []
    tdy = today()
    for d in data.get('data', []):
        a = d.get('attributes', {})
        close = (a.get('commentEndDate') or '')[:10] or None
        if not close or close < tdy:
            continue
        rows.append({
            'id': row_id('regs', d.get('id')),
            'date': (a.get('postedDate') or '')[:10],
            'title': (a.get('title') or '')[:200],
            'url': f"https://www.regulations.gov/document/{d.get('id')}",
            'source': f"Regulations.gov ({a.get('agencyId', '')})",
            'deadline': close,
            'tags': ['docket'],
            'state': 'US',
        })
    return rows


MY_STATES = re.compile(r"\b(New Jersey|NJ|New York|NY|Pennsylvania|PA|Delaware|DE|Maryland|MD|District of Columbia|DC)\b")
STATE_SIP = re.compile(r"(Air (Quality )?Plan|Implementation Plans?|Air Plan Approval|Primacy|Nonattainment|Maintenance Plan|Designated Facilities|Approval of State)", re.I)


def fetch_epa_open():
    """Every EPA proposed rule with an open comment period (EPA rules ARE the topic). State-specific air-plan
    approvals are dropped unless they name one of the tracked states (NJ/NY/PA/DE/MD/DC). Added 2026-10-25
    after v1's full-text EJ search returned an NRC reactor rule."""
    since = (datetime.now(timezone.utc) - timedelta(days=120)).strftime('%Y-%m-%d')
    params = [('per_page', '200'), ('conditions[agencies][]', 'environmental-protection-agency'),
              ('conditions[type][]', 'PRORULE'), ('conditions[publication_date][gte]', since)] + [('fields[]', f) for f in FIELDS]
    r = curl(FR_URL + '?' + urlencode(params))
    if not r['ok']:
        raise RuntimeError(f'Federal Register (EPA) fetch failed: {r["error"]}')
    rows, tdy = [], today()
    for d in json.loads(r['body']).get('results', []):
        close, title = d.get('comments_close_on'), d.get('title', '')
        if not close or close < tdy:
            continue
        if STATE_SIP.search(title) and not MY_STATES.search(title):
            continue
        st = 'US'
        m = MY_STATES.search(title) if STATE_SIP.search(title) else None
        if m:
            st = {'New Jersey':'NJ','New York':'NY','Pennsylvania':'PA','Delaware':'DE','Maryland':'MD','District of Columbia':'DC'}.get(m.group(1), m.group(1))
        rows.append({'id': row_id('fr', d.get('html_url')), 'date': d.get('publication_date'), 'title': title[:200],
                     'url': d.get('comment_url') or d.get('html_url'), 'source': 'Federal Register (EPA)',
                     'deadline': close, 'tags': ['prorule', 'epa'], 'state': st})
    return rows


def run():
    rows = fetch_federal_register()
    rules = load_rules()
    m = EJMatcher(rules['core_terms'], rules.get('exclude_phrases'), rules.get('siting_nouns'))
    rows = [x for x in rows if m.match(x['title'])]   # EJ term must be in the TITLE (full-text was noise)
    rows += fetch_epa_open()
    rows += fetch_regulations_gov()
    print(f'comments: {len(rows)} open comment period(s) matching EJ terms')
    return rows


if __name__ == '__main__':
    sys.exit(run_stream('comments', run))
