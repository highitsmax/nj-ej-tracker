#!/usr/bin/env python3
"""NJ EJ Tracker, stream 1: news. RSS fetch/parse/dedupe: no alerting, no grouping, no SQLite -- this is a
personal one-page tracker, not a buzz dispatcher.

v2 (2026-10-26): two output panels, each with a hard definition (see BRIEF_builder_v2_2026-10-26.md):

  news_nj.json       "New Jersey" panel -- NJ outlet/GN-query stories whose TEXT names NJ or an NJ place
                      (unchanged v1 logic) + NJ allied-org press feeds (no EJ filter) + NJ hyperlocal
                      town queries (EJ filter).
  news_national.json "National & outlets" panel -- pitch-outlet stories (EJ filter OR nj_local_terms,
                      since beat outlets rarely use EJ's own vocabulary) + national allied-org press
                      feeds (no EJ filter) + Baltimore/MD hyperlocal query (EJ filter, tag MD).

A feed's tags in feeds.txt (state:XX, kind:allied|pitch|hyperlocal, town:Name) decide its routing
DETERMINISTICALLY -- only the untagged "NJ outlet" / GN-NJ-query feeds still use the old text-sniffing
NJ_RX approach, because those are generic-query feeds that can return off-topic-state stories.

Writes data/news_nj.json and data/news_national.json (list of {id, date, title, url, source, deadline,
tags, state, kind} plus optional "town" and "pitch" keys) + their .status.json files. Run: python3 src/news.py
"""
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import EJMatcher, curl, load_rules, parse_feed, row_id, run_stream, split_outlet, today  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
NJ_RX = re.compile(r"(New Jersey|N\.J\.|\bNJ\b|NJDEP|Newark|Camden|Paterson|Trenton|Jersey City|Ironbound|Elizabeth, N|Linden|Perth Amboy|Bayonne|Hackensack|Meadowlands|Garden State)")
FEED_META = {}  # label -> {'state': 'XX', 'kind': 'allied'|'pitch'|'hyperlocal', 'town': 'Name'}
from datetime import datetime as _dt, timedelta as _td
MAX_AGE = (_dt.utcnow() - _td(days=365)).strftime('%Y-%m-%d')  # news older than 12 months is dropped


def load_feeds():
    out = []
    FEED_META.clear()
    for raw in open(os.path.join(HERE, 'feeds.txt')):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        data, _, comment = line.partition('#')
        data = data.strip()
        if not data:
            continue
        url, _, label = data.partition('|')
        url, label = url.strip(), (label.strip() or url.strip())
        out.append((url, label))
        meta = {}
        for tok in comment.strip().split():
            k, _, v = tok.partition(':')
            if k in ('state', 'kind'):
                meta[k] = v
            elif k == 'town':
                meta['town'] = tok[len('town:'):]
        if meta:
            FEED_META[label] = meta
    return out


def fetch_one(feed):
    url, label = feed
    r = curl(url, headers=['Accept: application/rss+xml, application/atom+xml, application/xml, text/xml, */*'])
    if not r['ok']:
        return {'url': url, 'label': label, 'ok': False, 'items': [], 'error': r['error']}
    try:
        items = parse_feed(r['body'])
        return {'url': url, 'label': label, 'ok': True, 'items': items, 'error': ''}
    except Exception as e:
        return {'url': url, 'label': label, 'ok': False, 'items': [], 'error': f'not RSS/Atom: {e}'[:200]}


def run():
    rules = load_rules()
    matcher = EJMatcher(rules['core_terms'], rules.get('exclude_phrases'), rules.get('siting_nouns'))
    nj_local_rx = re.compile('|'.join(r'\b' + re.escape(w.rstrip('*')) + (r'\w*' if w.endswith('*') else r'\b') for w in rules['nj_local_terms']), re.I)
    feeds = load_feeds()
    gn = [f for f in feeds if 'news.google.com' in f[0]]
    other = [f for f in feeds if 'news.google.com' not in f[0]]

    def gn_seq(fs):  # one Google News call at a time, politely spaced (same courtesy as before)
        out = []
        for f in fs:
            out.append(fetch_one(f))
            time.sleep(1.0)
        return out

    with ThreadPoolExecutor(max_workers=8) as ex:
        gfut = ex.submit(gn_seq, gn)
        results = list(ex.map(fetch_one, other)) + gfut.result()

    ok = sum(1 for r in results if r['ok'])
    failing = [f"{r['label']}: {r['error']}" for r in results if not r['ok']]
    print(f'news: {ok}/{len(results)} feeds ok')
    for f in failing:
        print('  FAIL', f)

    nj_rows, national_rows = [], []
    for r in results:
        meta = FEED_META.get(r['label'], {})
        kind = meta.get('kind')
        for it in r['items']:
            if not it['title']:
                continue
            headline, outlet = split_outlet(it['title'])
            summary = it.get('summary', '')
            source = outlet or r['label']
            if any(x in source.lower() for x in rules.get('exclude_outlets', [])):
                continue
            if (it['date'] or today()) < MAX_AGE:
                continue
            base = {
                'id': row_id(headline.lower(), it['link']),
                'date': it['date'] or today(),
                'title': headline,
                'url': it['link'],
                'kind': None,
            }

            if kind == 'allied':
                # Allied-org press feeds: no EJ filter, keep every item, source is the org (the feed
                # label), not whatever the feed's own <title>-suffix outlet guess produced.
                row = dict(base, source=r['label'], tags=['allied'], state=meta.get('state', 'US'))
                (nj_rows if meta.get('state') == 'NJ' else national_rows).append(row)
                continue

            if kind == 'pitch':
                # Beat outlets: keep a story if it hits a core EJ term OR an nj_local_term -- a strict
                # EJ-only filter empties these feeds (they're general climate/justice beats, not EJ-only).
                hits = matcher.match(headline, summary)
                if not hits:
                    local_hits = nj_local_rx.findall(f'{headline} {summary}')
                    if not local_hits:
                        continue
                    hits = [f'nj-local:{w}' for w in local_hits][:3]
                row = dict(base, source=source, tags=hits, state='US', pitch=True)
                national_rows.append(row)
                continue

            if kind == 'hyperlocal':
                hits = matcher.match(headline, summary)
                if not hits:
                    continue
                st = meta.get('state', 'NJ')
                row = dict(base, source=source, tags=hits, state=st, town=meta.get('town', ''))
                (nj_rows if st == 'NJ' else national_rows).append(row)
                continue

            # Untagged: NJ outlets + GN-NJ queries -- v1 logic. EJ core term, OR (story text names NJ/a
            # place AND hits an nj_local_term). Routed NJ vs dropped by whether the text names NJ --
            # there is no longer a catch-all "National News" panel for stories that match the keyword
            # filter but never mention NJ, since National & outlets is now a hard-defined set (pitch +
            # allied + MD hyperlocal) that doesn't include general NJ-outlet-feed overflow.
            hits = matcher.match(headline, summary)
            text = f'{headline} {summary} {outlet or ""}'
            is_nj_text = bool(NJ_RX.search(text))
            if not hits and is_nj_text:
                hits = [f'nj:{w}' for w in nj_local_rx.findall(text)][:3]
            if not hits:
                continue
            if not is_nj_text:
                continue  # no home panel for this story under the v2 definition; drop (see note above)
            row = dict(base, source=source, tags=hits, state='NJ')
            nj_rows.append(row)

    if ok == 0:
        raise RuntimeError(f'all {len(results)} feeds failed; refusing to overwrite news data with an empty set')
    return nj_rows, national_rows


_cache = {}


def _rows():
    if 'rows' not in _cache:
        _cache['rows'] = run()
    return _cache['rows']


if __name__ == '__main__':
    rc1 = run_stream('news_nj', lambda: _rows()[0])
    rc2 = run_stream('news_national', lambda: _rows()[1])
    sys.exit(rc1 or rc2)
