#!/usr/bin/env python3
"""NJ EJ Tracker, stream 5 (v2): "Pitch & publish" panel.

  outlets.json      Hand-kept, built from src/outlets_seed.json (NEEDS doc section 5, pitch-channel-
                    verified rows only -- see outlets_seed.json's own _note for what was skipped and why).
                    Pay rates only ever show a figure this session fetched and found verbatim on the
                    outlet's own pitch/guidelines page; everything else reads "rates: see guidelines".
  pitch_calls.json  Live: one Google News RSS query for "call for pitches" / "looking for pitches" /
                    "pitch us" language in a climate/EJ context, newest first, capped at 10.

Writes data/outlets.json, data/pitch_calls.json + their .status.json files. Run: python3 src/outlets.py
"""
import json
import os
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import curl, parse_feed, row_id, run_stream, split_outlet  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PITCH_CALLS_QUERY = '("call for pitches" OR "looking for pitches" OR "pitch us") (climate OR environment OR "environmental justice")'
GN_URL = f"https://news.google.com/rss/search?q={quote(PITCH_CALLS_QUERY)}&hl=en-US&gl=US&ceid=US:en"


def build_outlets():
    seed = json.load(open(os.path.join(HERE, 'outlets_seed.json')))
    rows = []
    for o in seed['outlets']:
        rate = f"rates: {o['rate']}" if o.get('rate') else 'rates: see guidelines'
        rows.append({
            'id': row_id('outlet', o['outlet']),
            'date': None,
            'title': o['outlet'],
            'url': o.get('pitch_url') or '#',
            'source': f"{o.get('formats', '')} · {o.get('pitch_channel', '')} · {rate}",
            'deadline': None,
            'tags': ['outlet'],
            'state': 'US',
            'kind': None,
        })
    print(f"outlets: {len(rows)} pitch outlets with a verified channel (of {len(seed['outlets'])} in the seed list; "
          f"{len(seed.get('skipped_unverified_channel', []))} skipped for an unverified channel)")
    return rows


def build_pitch_calls():
    r = curl(GN_URL, headers=['Accept: application/rss+xml, application/atom+xml, application/xml, text/xml, */*'])
    if not r['ok']:
        raise RuntimeError(f'pitch-calls GN query failed: {r["error"]}')
    items = parse_feed(r['body'])
    rows = []
    for it in items[:10]:
        headline, outlet = split_outlet(it['title'])
        rows.append({
            'id': row_id('pitchcall', headline, it['link']),
            'date': it['date'],
            'title': headline,
            'url': it['link'],
            'source': outlet or 'Google News',
            'deadline': None,
            'tags': ['pitch-call'],
            'state': 'US',
            'kind': None,
        })
    print(f'pitch_calls: {len(rows)} result(s) (capped at 10, newest first)')
    return rows


if __name__ == '__main__':
    rc1 = run_stream('outlets', build_outlets)
    rc2 = run_stream('pitch_calls', build_pitch_calls)
    sys.exit(rc1 or rc2)
