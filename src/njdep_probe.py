#!/usr/bin/env python3
"""NJ EJ Tracker (v2, 2026-10-26): NJDEP hearings probe. No parser exists -- dep.nj.gov's entire domain,
including this page, sits behind an Incapsula/Imperva WAF that returns a tiny JS-challenge iframe shell
to any scripted request (confirmed live 2026-10-26: 1,161 bytes, body contains "Incapsula"). This script
just records whether that's still true today, so a future check (or a person opening the real URL in a
browser, which passes the JS challenge automatically) knows when it's worth revisiting.

Writes data/njdep_probe.json = {date, http_code, bytes, incapsula}. Meant to be run with
continue-on-error in the workflow -- a probe failure is informational, never fatal. Does NOT use
run_stream/the row schema; build_page.py reads this file directly to decide whether to show the one
"NJDEP EJ hearings calendar" link line in the Weigh-in panel (per the build brief: "Nothing on the page
except: if blocked, the Weigh-in panel shows one link line"). Run: python3 src/njdep_probe.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import curl, today, write_json, DATA_DIR  # noqa: E402

URL = 'https://dep.nj.gov/ej/meetings/'
OUT = os.path.join(DATA_DIR, 'njdep_probe.json')


def run():
    r = curl(URL)
    body = r.get('body') or b''
    incapsula = b'Incapsula' in body or b'incapsula' in body
    result = {'date': today(), 'http_code': r.get('status'), 'bytes': len(body), 'incapsula': incapsula}
    write_json(OUT, result)
    state = 'blocked (Incapsula)' if incapsula else ('ok' if r.get('ok') else f'error: {r.get("error")}')
    print(f'njdep_probe: {URL} -> {state} ({result["bytes"]} bytes, HTTP {result["http_code"]})')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(run())
    except Exception as e:
        print(f'njdep_probe: FAILED ({type(e).__name__}: {e}) -- non-fatal, continue-on-error in the workflow', file=sys.stderr)
        sys.exit(0)
