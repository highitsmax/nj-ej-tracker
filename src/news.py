#!/usr/bin/env python3
"""NJ EJ Tracker, stream 1: news. RSS fetch/parse/dedupe: no alerting,
no grouping, no SQLite -- this is a personal one-page tracker, not a buzz dispatcher. Every feed in feeds.txt
is filtered through the EJ keyword rules in ej_terms.json (src/common.py EJMatcher); see feeds.txt header for
why there's no [filter]/unfiltered split here.

Writes data/news.json (list of {id, date, title, url, source, deadline, tags}, deadline always null for news)
and data/news.status.json. Run: python3 src/news.py
"""
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import EJMatcher, curl, load_rules, parse_feed, row_id, run_stream, split_outlet, today  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FEED_STATE = {}  # label -> state code, from a feed line's trailing "# state:XX" (see feeds.txt header)


def load_feeds():
    out = []
    FEED_STATE.clear()
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
        m = re.match(r'state:([A-Z]{2})', comment.strip())
        if m:
            FEED_STATE[label] = m.group(1)
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
    feeds = load_feeds()
    gn = [f for f in feeds if 'news.google.com' in f[0]]
    other = [f for f in feeds if 'news.google.com' not in f[0]]

    def gn_seq(fs):  # one Google News call at a time, politely spaced (same courtesy as Pulse)
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

    rows = []
    for r in results:
        for it in r['items']:
            if not it['title']:
                continue
            headline, outlet = split_outlet(it['title'])
            hits = matcher.match(headline, it.get('summary', ''))
            if not hits:
                continue
            rows.append({
                'id': row_id(headline.lower(), it['link']),
                'date': it['date'] or today(),
                'title': headline,
                'url': it['link'],
                'source': outlet or r['label'],
                'deadline': None,
                'tags': hits,
                'state': FEED_STATE.get(r['label'], 'US'),
            })
    if ok == 0:
        raise RuntimeError(f'all {len(results)} feeds failed; refusing to overwrite data/news.json with an empty set')
    return rows


if __name__ == '__main__':
    sys.exit(run_stream('news', run))
