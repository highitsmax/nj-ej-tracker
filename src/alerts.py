#!/usr/bin/env python3
"""NJ EJ Tracker (v2, 2026-10-26): air-quality / heat alert line. NWS alerts/active API, keyless, one
call per watched zone. Zone ids found live via https://api.weather.gov/points/<lat>,<lon> (not guessed):

  NJZ105  "Western Essex" -- Western Essex County, NJ (forecastZone NJZ105)
  MDZ011  "Southern Baltimore" -- covers Baltimore City, MD (39.2904,-76.6122 -> forecastZone MDZ011)

Only events containing "Heat", "Air Quality", or "Air Stagnation" in the NWS event name are kept (per the
build brief) -- a Winter Storm Warning for the same zone is not shown. Writes data/alerts.json as a list
of {event, area, until} dicts (NOT the generic row schema -- this isn't a clickable-link panel item, it's
a one-line banner build_page.py renders under the header only when non-empty) + data/alerts.status.json.

Run: python3 src/alerts.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import curl, row_id, run_stream  # noqa: E402

ZONES = {'NJZ105': 'Western Essex County, NJ', 'MDZ011': 'Baltimore City, MD (Southern Baltimore)'}
KEEP = ('heat', 'air quality', 'air stagnation')
UA_HEADER = 'User-Agent: nj-ej-tracker (github.com/highitsmax/nj-ej-tracker)'


def run():
    rows = []
    for zone, area_label in ZONES.items():
        r = curl(f'https://api.weather.gov/alerts/active?zone={zone}', headers=[UA_HEADER])
        if not r['ok']:
            print(f'alerts: {zone} fetch failed ({r["error"]}); skipping this zone this run.', file=sys.stderr)
            continue
        data = json.loads(r['body'])
        for f in data.get('features', []):
            p = f.get('properties', {})
            event = p.get('event', '')
            if not any(k in event.lower() for k in KEEP):
                continue
            rows.append({'id': row_id('alert', zone, event, p.get('ends') or ''), 'event': event,
                         'area': area_label, 'until': p.get('ends') or p.get('expires')})
    print(f'alerts: {len(rows)} active heat/air-quality alert(s) across {len(ZONES)} zone(s)')
    return rows


if __name__ == '__main__':
    # Not the generic {id,date,title,...} row schema (run_stream still gives us the free last-good-data-on-
    # failure behavior and a status file; we just overwrite the row-list assumption isn't used downstream).
    sys.exit(run_stream('alerts', run))
