#!/usr/bin/env python3
"""NJ EJ Tracker, stream 6 (v2): jobs. Three sources feeding one data/jobs.json, each wrapped so one
source's failure never drops the others:

  1. USAJOBS Search API -- only if USAJOBS_API_KEY + USAJOBS_EMAIL are both set (unchanged from v1).
  2. The ATS orgs in src/orgs_ats.json (Greenhouse/Lever/Workable/BambooHR, all keyless, all confirmed
     live 2026-10-25 per round2/orgs.json) -- keyless, always runs.
  3. JobSpy (python-jobspy), if importable -- general job-board fallback (Indeed/LinkedIn/Google), guarded
     by try/except per the build brief: "a JobSpy failure must never fail the jobs stream."

Every posting from every source is run through src/orgs_ats.json's job_filter (include/exclude keyword
match on title) before it's written. Deduped by (org, title). Capped at 40 rows.

Writes data/jobs.json and data/jobs.status.json. Run: python3 src/jobs.py
"""
import json
import os
import sys
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import curl, row_id, run_stream  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEARCH_URL = 'https://data.usajobs.gov/api/search'
MAX_JOBS = 40


def load_filter():
    return json.load(open(os.path.join(HERE, 'orgs_ats.json')))


def passes_filter(title, dept, filt):
    text = f'{title or ""} {dept or ""}'.lower()
    if any(x in text for x in filt['exclude_keywords']):
        return False
    return any(x in text for x in filt['include_keywords'])


def fetch_usajobs():
    key, email = os.environ.get('USAJOBS_API_KEY'), os.environ.get('USAJOBS_EMAIL')
    if not (key and email):
        print('jobs: USAJOBS_API_KEY / USAJOBS_EMAIL not set; USAJOBS skipped (panel still gets ATS orgs).')
        return []
    params = urlencode({'Keyword': 'environmental justice', 'ResultsPerPage': 25})
    r = curl(f'{SEARCH_URL}?{params}', headers=[
        f'Authorization-Key: {key}', f'User-Agent: {email}', 'Host: data.usajobs.gov',
    ])
    if not r['ok']:
        print(f'jobs: USAJOBS fetch failed ({r["error"]}); continuing with other sources.')
        return []
    rows = []
    try:
        data = json.loads(r['body'])
        for item in data.get('SearchResult', {}).get('SearchResultItems', []):
            d = item.get('MatchedObjectDescriptor', {})
            close = (d.get('ApplicationCloseDate') or '')[:10] or None
            pos_loc = ', '.join(l.get('LocationName', '') for l in (d.get('PositionLocation') or []))[:120]
            title = d.get('PositionTitle', '')
            rows.append({
                'id': row_id('usajobs', d.get('PositionID')),
                'date': (d.get('PublicationStartDate') or '')[:10] or None,
                'title': f'{title} ({pos_loc})' if pos_loc else title,
                'url': d.get('PositionURI') or (d.get('ApplyURI') or [None])[0],
                'source': d.get('DepartmentName', 'USAJOBS'),
                'deadline': close,
                'tags': ['federal'],
                'state': 'US',
                'kind': 'job',
                '_org': d.get('DepartmentName', 'USAJOBS'), '_title': title,
            })
    except Exception as e:
        print(f'jobs: USAJOBS response parse failed: {e}')
        return []
    print(f'jobs: {len(rows)} USAJOBS result(s) (pre-filter)')
    return rows


def _greenhouse(org, endpoint):
    r = curl(endpoint)
    if not r['ok']:
        raise RuntimeError(r['error'])
    data = json.loads(r['body'])
    out = []
    for j in data.get('jobs', []):
        loc = (j.get('location') or {}).get('name', '')
        out.append((j.get('title', ''), loc, j.get('absolute_url'), (j.get('updated_at') or '')[:10], None))
    return out


def _lever(org, endpoint):
    r = curl(endpoint)
    if not r['ok']:
        raise RuntimeError(r['error'])
    data = json.loads(r['body'])
    out = []
    for j in data:
        cats = j.get('categories', {}) or {}
        out.append((j.get('text', ''), cats.get('location', ''), j.get('hostedUrl'), (j.get('createdAt') and str(j.get('createdAt'))[:10]) or None, cats.get('team')))
    return out


def _workable(org, endpoint):
    r = curl(endpoint, method='POST', data='{}')
    if not r['ok']:
        raise RuntimeError(r['error'])
    data = json.loads(r['body'])
    out = []
    for j in data.get('results', []):
        loc = j.get('location', {}) or {}
        loc_s = ', '.join(x for x in [loc.get('city'), loc.get('region')] if x)
        out.append((j.get('title', ''), loc_s, j.get('url'), None, j.get('department')))
    return out


def _bamboohr(org, endpoint):
    r = curl(endpoint, headers=['Accept: application/json'])
    if not r['ok']:
        raise RuntimeError(r['error'])
    data = json.loads(r['body'])
    out = []
    for j in data.get('result', []):
        loc = j.get('location', {}) or {}
        loc_s = ', '.join(x for x in [loc.get('city'), loc.get('state')] if x)
        out.append((j.get('jobOpeningName', ''), loc_s, f"https://{org.lower().replace(' ', '')}.bamboohr.com/careers/{j.get('id')}", None, j.get('departmentLabel')))
    return out


FETCHERS = {'greenhouse': _greenhouse, 'lever': _lever, 'workable': _workable, 'bamboohr': _bamboohr}


def fetch_ats_orgs(filt):
    cfg = load_filter()
    rows = []
    for org in cfg['orgs']:
        fn = FETCHERS.get(org['ats'])
        if not fn:
            continue
        try:
            postings = fn(org['name'], org['endpoint'])
        except Exception as e:
            print(f"jobs: ATS org {org['name']} ({org['ats']}) failed: {e}", file=sys.stderr)
            continue
        for title, loc, url, date_s, dept in postings:
            rows.append({
                'id': row_id('ats', org['name'], title, url or ''),
                'date': date_s,
                'title': f'{title} ({loc})' if loc else title,
                'url': url,
                'source': org['name'],
                'deadline': None,
                'tags': ['org'],
                'state': 'US',
                'kind': 'job',
                '_org': org['name'], '_title': title, '_dept': dept,
            })
    print(f'jobs: {len(rows)} ATS-org result(s) (pre-filter) across {len(cfg["orgs"])} org(s)')
    return rows


def fetch_jobspy():
    try:
        from jobspy import scrape_jobs
    except Exception as e:
        print(f'jobs: JobSpy not importable ({e}); skipping (guarded, never fails the stream). '
              f'See BUILD_REPORT for the sandbox-specific pip install note.')
        return []
    terms = ['environmental justice', 'environmental justice communications', 'environmental health communications', 'community organizer environmental']
    locations = ['New Jersey', 'Baltimore, MD', 'Washington, DC']
    rows = []
    for term in terms:
        for loc in locations:
            try:
                df = scrape_jobs(site_name=['indeed', 'linkedin', 'google'], search_term=term, location=loc,
                                  results_wanted=15, hours_old=168, country_indeed='USA')
                rows += _jobspy_rows(df)
            except Exception as e:
                print(f'jobs: JobSpy search failed (term={term!r}, location={loc!r}): {e}', file=sys.stderr)
        try:
            df = scrape_jobs(site_name=['indeed', 'linkedin', 'google'], search_term=term, is_remote=True,
                              results_wanted=15, hours_old=168, country_indeed='USA')
            rows += _jobspy_rows(df)
        except Exception as e:
            print(f'jobs: JobSpy remote search failed (term={term!r}): {e}', file=sys.stderr)
    print(f'jobs: {len(rows)} JobSpy result(s) (pre-filter)')
    return rows


def _jobspy_rows(df):
    out = []
    try:
        records = df.to_dict('records')
    except Exception:
        return out
    for r in records:
        title, company = r.get('title', ''), r.get('company', '') or 'JobSpy'
        out.append({
            'id': row_id('jobspy', company, title, str(r.get('job_url', ''))),
            'date': str(r.get('date_posted') or '')[:10] or None,
            'title': f"{title} ({r.get('location', '')})" if r.get('location') else title,
            'url': r.get('job_url'),
            'source': company,
            'deadline': None,
            'tags': ['jobspy'],
            'state': 'US',
            'kind': 'job',
            '_org': company, '_title': title, '_desc': str(r.get('description') or '')[:6000],
        })
    return out


import re as _re
IN_REGION = _re.compile(r"(New Jersey|\bNJ\b|New York|\bNY\b|Pennsylvania|\bPA\b|Philadelphia|Delaware|\bDE\b|Maryland|\bMD\b|Baltimore|Washington,? DC|\bD\.?C\.?\b|District of Columbia|Remote|Anywhere|Mid-Atlantic|Northeast)", _re.I)


# Mission rule (2026-10-26): communications in the title is not enough -- the work has to be EJ or
# environmental-health work. Energy/clean-tech roles only count when an EJ angle is explicit.
STRONG = _re.compile(r"(environmental justice|climate justice|environmental racism|frontline communit|fenceline|overburdened|disadvantaged communit|environmental health|community health|grassroots|community[- ]led|pollution|clean air|clean water|toxic|cumulative impact)", _re.I)
MEDIUM = _re.compile(r"(environment|climate|conservation|public health|\\bwater\\b)", _re.I)
ENERGY = _re.compile(r"(solar|renewable|clean energy|energy efficiency|electric vehicle|\bEV\b|utility|utilities|power plant|wind energy|battery|decarboni|carbon accounting|emissions software)", _re.I)
# Employer rule (Max 2026-10-26: "she wants to be on the side of the good guys"): no consultancies, engineering
# firms, or industry/corporate employers -- the side that hires to get permits through, not to fight them.
NOT_GOOD_GUYS = _re.compile(r"(consult|engineer|\bEY\b|deloitte|accenture|kpmg|pwc|JLL|CBRE|jacobs|AECOM|WSP|stantec|tetra tech|geosyntec|TRC compan|ramboll|arcadis|plastics|chemical|petroleum|\boil\b|\bgas\b|exxon|chevron|shell|BP\b|refin|pharma|merck|pfizer|johnson & johnson|amazon|google|meta\b|microsoft|coreweave|staffing|recruit|marketing agency|proposals|industry advocacy|private sector engagement|corporate communications)", _re.I)
TRUSTED_ATS = {'jobs-ats'}
# Known advocacy / EJ / environmental-health nonprofits: any communications/organizing role there counts.
GOOD_GUYS = _re.compile(r"(earthjustice|sierra club|clean water action|natural resources defense|\\bNRDC\\b|WE ACT|environmental justice|ironbound|NJ Environmental Justice|NJEJA|union of concerned scientists|evergreen action|groundwork|hip hop caucus|greenpeace|350\\.org|sunrise movement|center for biological diversity|environmental defense|\\bEDF\\b|league of conservation voters|\\bLCV\\b|food & water watch|food and water watch|moms clean air|appalachian voices|south baltimore|clean air council|new jersey future|isles|tri-state transportation|surfrider|waterkeeper|riverkeeper|baykeeper|green ?faith|NAACP|urban league|environmental integrity project|community health|public citizen)", _re.I)   # rows from the hand-picked EJ/environmental org boards


def mission_ok(r):
    head = f"{r.get('_title', '')} {r.get('_org', '')}"
    full = f"{head} {r.get('_desc', '')}"
    trusted = 'jobspy' not in (r.get('tags') or []) and 'usajobs' not in (r.get('tags') or [])
    if ENERGY.search(full) and not STRONG.search(full):
        return False
    if GOOD_GUYS.search(r.get('_org', '')):
        return not (ENERGY.search(full) and not STRONG.search(full))
    if NOT_GOOD_GUYS.search(r.get('_org', '')) or NOT_GOOD_GUYS.search(r.get('_title', '')):
        return False
    if trusted:
        return True
    return bool(STRONG.search(full) or MEDIUM.search(head))


def run():
    filt = load_filter()['job_filter']
    raw = fetch_usajobs() + fetch_ats_orgs(filt) + fetch_jobspy()
    filtered, seen = [], set()
    for r in raw:
        if not passes_filter(r.get('_title'), r.get('_dept'), filt):
            continue
        key = (r.get('_org', '').lower(), r.get('_title', '').lower())
        if key in seen:
            continue
        seen.add(key)
        if not mission_ok(r):
            continue   # not EJ/environmental-health mission, or energy-only work with no EJ angle
        if not IN_REGION.search(f"{r.get('title', '')} {r.get('source', '')}"):
            continue   # outside the tracked region and not remote
        r.pop('_org', None); r.pop('_title', None); r.pop('_dept', None); r.pop('_desc', None)
        filtered.append(r)
    print(f'jobs: {len(filtered)} posting(s) pass the comms/EJ job filter (of {len(raw)} raw, before the {MAX_JOBS}-row cap)')
    return filtered[:MAX_JOBS]


if __name__ == '__main__':
    sys.exit(run_stream('jobs', run))
