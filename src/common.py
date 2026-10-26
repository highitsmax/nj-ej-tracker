"""Shared helpers for the NJ EJ Tracker streams. Plain stdlib + curl. No AI, no third-party packages.

Each stream script writes data/<name>.json (a list of row dicts: id, date, title, url, source, deadline, tags)
and data/<name>.status.json (ok, last_success, last_attempt, note, count) so the page can show "last good: <date>"
when a stream's live pass fails. A failed stream NEVER erases its last good data/<name>.json (point 8 of the spec).
"""
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

UA = 'nj-ej-tracker/0.1 (+https://github.com/highitsmax/nj-ej-tracker)'
TIMEOUT = 30
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(ROOT, 'data')
MAX_ROWS = 50


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def today():
    return datetime.now(timezone.utc).date().isoformat()


def data_path(name):
    return os.path.join(DATA_DIR, f'{name}.json')


def status_path(name):
    return os.path.join(DATA_DIR, f'{name}.status.json')


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        return json.load(open(path))
    except Exception:
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    json.dump(obj, open(tmp, 'w'), indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def row_id(*parts):
    return hashlib.sha1('|'.join(p or '' for p in parts).encode('utf-8', 'ignore')).hexdigest()[:16]


def run_stream(name, fn):
    """Call fn() -> list[row dict]. On success, write data/<name>.json (capped, newest first) and a status row
    with ok=True. On any exception, LEAVE the existing data/<name>.json alone and write a status row with
    ok=False + the error, so the page can show 'last good: <date>' instead of going blank. Never raises:
    one stream's failure must never take down the whole Actions run (spec point 8)."""
    st = load_json(status_path(name), {'ok': None, 'last_success': None, 'last_attempt': None, 'note': '', 'count': 0})
    st['last_attempt'] = now()
    try:
        rows = fn()
        rows = dedupe_sort(rows)
        write_json(data_path(name), rows[:MAX_ROWS])
        st['ok'] = True
        st['note'] = ''
        st['count'] = len(rows)
        st['last_success'] = st['last_attempt']
        write_json(status_path(name), st)
        print(f'{name}: OK, {len(rows)} rows')
        return 0
    except Exception as e:
        st.update(ok=False, note=f'{type(e).__name__}: {e}'[:300])
        write_json(status_path(name), st)
        print(f'{name}: FAILED ({st["note"]}) -- keeping last good data', file=sys.stderr)
        return 0  # never fail the job over one stream


def dedupe_sort(rows):
    seen, out = set(), []
    for r in rows:
        if r['id'] in seen:
            continue
        seen.add(r['id'])
        out.append(r)
    out.sort(key=lambda r: r.get('date') or '', reverse=True)
    return out


# ---------------------------------------------------------------- HTTP (curl, not urllib: handles chunked bodies
# more reliably across the feeds this project touches).
def curl(url, method='GET', data=None, headers=None, timeout=TIMEOUT):
    cmd = ['curl', '-sS', '-L', '--compressed', '-A', UA, '--max-time', str(timeout), '-w', '\n%{http_code}']
    for h in (headers or []):
        cmd += ['-H', h]
    if method == 'POST':
        cmd += ['-X', 'POST']
        if data is not None:
            cmd += ['-H', 'Content-Type: application/json', '-d', data]
    try:
        p = subprocess.run(cmd + [url], capture_output=True, timeout=timeout + 15)
    except Exception as e:
        return {'ok': False, 'status': None, 'body': b'', 'error': f'{type(e).__name__}: {e}'[:200]}
    body, _, code = p.stdout.rpartition(b'\n')
    status = int(code or 0)
    if p.returncode != 0:
        return {'ok': False, 'status': None, 'body': b'', 'error': 'curl: ' + p.stderr.decode(errors='replace').strip()[:200]}
    if status >= 400:
        return {'ok': False, 'status': status, 'body': body, 'error': f'HTTP {status}'}
    return {'ok': True, 'status': status, 'body': body, 'error': ''}


# ---------------------------------------------------------------- RSS/Atom (clone of Pulse news.py's parser)
ATOM = '{http://www.w3.org/2005/Atom}'


def clean(s):
    s = html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))
    return re.sub(r'\s+', ' ', s).strip()


def _text(el, *names):
    for n in names:
        f = el.find(n)
        if f is not None and (f.text or '').strip():
            return f.text.strip()
    return ''


def parse_date(s):
    from email.utils import parsedate_to_datetime
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace('Z', '+00:00'))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).date().isoformat()


def parse_feed(xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter('item'):  # RSS 2.0
        items.append({
            'title': clean(_text(it, 'title')),
            'link': _text(it, 'link'),
            'date': parse_date(_text(it, 'pubDate', '{http://purl.org/dc/elements/1.1/}date')),
            'summary': clean(_text(it, 'description'))[:600],
        })
    for it in root.iter(ATOM + 'entry'):  # Atom
        link = ''
        for l in it.findall(ATOM + 'link'):
            if l.get('rel', 'alternate') == 'alternate':
                link = l.get('href', '')
                break
        items.append({
            'title': clean(_text(it, ATOM + 'title')),
            'link': link,
            'date': parse_date(_text(it, ATOM + 'published', ATOM + 'updated')),
            'summary': clean(_text(it, ATOM + 'summary', ATOM + 'content'))[:600],
        })
    return items


def split_outlet(t):
    """Google News appends ' - Outlet' to titles. Returns (headline, outlet-or-'')."""
    m = re.match(r'^(.*\S)\s+-\s+([^-]{2,60})$', t or '')
    return (m.group(1), m.group(2).strip()) if m else (t or '', '')


# ---------------------------------------------------------------- EJ keyword matcher (clone of Pulse bills.py
# Matcher: whole-word, trailing * = stem, an exclude phrase is stripped before matching so it can't be the
# only reason something matches. RESEARCH_sources_2026-10-25.md section 2.)
def _pat(w):
    stem = w.endswith('*')
    body = re.escape(w.rstrip('*').lower()).replace(r'\ ', r'[\s-]?').replace(r'\-', r'[\s-]?')
    return r'(?<![a-z0-9])' + body + ('' if stem else r'(?![a-z0-9])')


class EJMatcher:
    def __init__(self, terms, exclude_phrases=None, siting_nouns=None):
        self.rx = re.compile('|'.join(_pat(w) for w in terms), re.I)
        self.excl = re.compile('|'.join(_pat(w) for w in exclude_phrases), re.I) if exclude_phrases else None
        self.siting_rx = re.compile('|'.join(_pat(w) for w in siting_nouns), re.I) if siting_nouns else None

    def hits(self, text):
        text = text or ''
        if self.excl:
            text = self.excl.sub(' ', text)  # an excluded phrase can't be the only reason something matches
        return sorted({m.group(0).lower() for m in self.rx.finditer(text)})

    def siting_hits(self, text):
        return sorted({m.group(0).lower() for m in self.siting_rx.finditer(text or '')}) if self.siting_rx else []

    def match(self, title, summary=''):
        """-> matched terms, or [] if not EJ-relevant. A bare siting noun (e.g. 'landfill') only counts when an
        EJ-core term is ALSO present somewhere in the text -- the combination rule from the research doc's
        noise problem (never let a generic siting/permit story through on its own)."""
        text = f'{title} {summary}'
        core = self.hits(text)
        siting = self.siting_hits(text)
        if core:
            return core + [f'siting:{s}' for s in siting]
        return []


def load_rules():
    return json.load(open(os.path.join(HERE, 'ej_terms.json')))


# ---------------------------------------------------------------- "New since yesterday" tracking (v2).
# data/seen.json = {item_id: first_seen_iso}. Call mark_seen() once per build with every row id currently on
# the page; it returns the set of ids that are new within the last 24h, and prunes ids not seen in 60 days.
SEEN_PATH = os.path.join(DATA_DIR, 'seen.json')


def mark_seen(all_ids):
    from datetime import timedelta
    seen = load_json(SEEN_PATH, {})
    now_dt = datetime.now(timezone.utc)
    now_s = now_dt.isoformat(timespec='seconds')
    cutoff_24h = (now_dt - timedelta(hours=24)).isoformat(timespec='seconds')
    cutoff_60d = (now_dt - timedelta(days=60)).isoformat(timespec='seconds')
    new_ids = set()
    all_ids = set(all_ids)
    for i in all_ids:
        if i not in seen:
            seen[i] = now_s
            new_ids.add(i)
        elif seen[i] >= cutoff_24h:
            new_ids.add(i)
    # prune: any id not seen (first_seen) within the last 60 days gets dropped from the tracking file,
    # whether or not it's still on the page today -- keeps seen.json from growing forever.
    seen = {i: ts for i, ts in seen.items() if ts >= cutoff_60d}
    write_json(SEEN_PATH, seen)
    return new_ids
