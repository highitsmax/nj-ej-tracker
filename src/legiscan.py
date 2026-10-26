#!/usr/bin/env python3
"""NJ EJ Tracker, stream 2b (v2): state bills for NY, PA, DE, MD, DC via the LegiScan API. NJ itself stays
on src/bills.py's keyless NJ Legislature bulk-ZIP path -- this script is the "other 49 states" lane the
v1 README flagged as the next build.

Disabled entirely (writes nothing, leaves last good data alone) unless LEGISCAN_API_KEY is set -- per the
build brief, "the bills stream does NJ only and the page shows nothing extra" without a key.

Rate discipline (per build brief):
  - getMasterList once per state per run (cheap, gets title+description+change_hash for the whole state).
  - getBill only for a bill whose title/description matches that state's EJ vocabulary (ej_terms.json
    core_terms + src/legiscan_state_terms.json) AND whose change_hash changed since data/legiscan_hash.json.
  - LegiScan itself runs at most once per 24h (checked against data/bills_legiscan.status.json's own
    'legiscan_last_run' field -- kept in this stream's OWN status file rather than NJ's data/bills.status.json
    so the two scripts never race on the same file; see BUILD_REPORT ASSUMPTIONS).
  - Every API call (getMasterList + getBill) is counted into data/legiscan_usage.json {"YYYY-MM": count};
    the LegiScan part stops for the rest of the month at 2,500 calls (NJ bills, comments, grants, jobs
    streams are unaffected -- this script just returns early).

Writes data/bills_legiscan.json and data/bills_legiscan.status.json. Run: python3 src/legiscan.py
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA_DIR, EJMatcher, curl, load_json, load_rules, now, row_id,  # noqa: E402
                     run_stream, status_path, write_json)

HERE = os.path.dirname(os.path.abspath(__file__))
API = 'https://api.legiscan.com/'
STATES = ['NY', 'PA', 'DE', 'MD', 'DC']
MONTHLY_CAP = 2500
HASH_PATH = os.path.join(DATA_DIR, 'legiscan_hash.json')
USAGE_PATH = os.path.join(DATA_DIR, 'legiscan_usage.json')
LEGISCAN_STATUS = status_path('bills_legiscan')


def month_key():
    return datetime.now(timezone.utc).strftime('%Y-%m')


def bump_usage(n=1):
    usage = load_json(USAGE_PATH, {})
    mk = month_key()
    usage[mk] = usage.get(mk, 0) + n
    write_json(USAGE_PATH, usage)
    return usage[mk]


def usage_remaining():
    usage = load_json(USAGE_PATH, {})
    return MONTHLY_CAP - usage.get(month_key(), 0)


def call(op, **params):
    key = os.environ['LEGISCAN_API_KEY']
    qs = '&'.join([f'key={key}', f'op={op}'] + [f'{k}={v}' for k, v in params.items()])
    r = curl(f'{API}?{qs}')
    bump_usage(1)
    if not r['ok']:
        raise RuntimeError(f'LegiScan {op} failed: {r["error"]}')
    data = json.loads(r['body'])
    if data.get('status') != 'OK':
        raise RuntimeError(f'LegiScan {op} returned status={data.get("status")}: {data.get("alert", {})}')
    return data


def throttle_ok():
    st = load_json(LEGISCAN_STATUS, {})
    last = st.get('legiscan_last_run')
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return True
    return (datetime.now(timezone.utc) - last_dt).total_seconds() >= 23 * 3600  # a little under 24h so a
    # slightly-early cron tick doesn't push the "once per day" window back by a full extra day.


def set_throttle():
    st = load_json(LEGISCAN_STATUS, {})
    st['legiscan_last_run'] = now()
    write_json(LEGISCAN_STATUS, st)


def run():
    if not os.environ.get('LEGISCAN_API_KEY'):
        print('legiscan: LEGISCAN_API_KEY not set; bills stream stays NJ-only, nothing written.')
        return None  # signal "skip" -- do not touch data/bills_legiscan.json either way
    if not throttle_ok():
        print('legiscan: ran within the last ~24h; skipping this cycle (rate discipline), keeping last good data.')
        return None
    if usage_remaining() <= 0:
        print(f'legiscan: monthly cap ({MONTHLY_CAP}) reached for {month_key()}; skipping for the rest of the month.')
        return None

    rules = load_rules()
    state_terms = json.load(open(os.path.join(HERE, 'legiscan_state_terms.json')))
    hashes = load_json(HASH_PATH, {})
    rows = []
    for st in STATES:
        if usage_remaining() <= 0:
            print(f'legiscan: cap hit mid-run after {st} -- stopping early this cycle.')
            break
        extra_terms = [t for t in state_terms.get(st, []) if not t.startswith('_')]
        matcher = EJMatcher(rules['core_terms'] + extra_terms, rules.get('exclude_phrases'), rules.get('siting_nouns'))
        try:
            data = call('getMasterList', state=st)
        except Exception as e:
            print(f'legiscan: getMasterList({st}) failed: {e}', file=sys.stderr)
            continue
        ml = data.get('masterlist', {})
        n_total, n_matched, n_changed = 0, 0, 0
        for k, b in ml.items():
            if k == 'session':
                continue
            n_total += 1
            title, desc = b.get('title', ''), b.get('description', '')
            if not matcher.match(title, desc):
                continue
            n_matched += 1
            bill_id = str(b.get('bill_id'))
            chash = b.get('change_hash')
            if hashes.get(bill_id) == chash:
                # matched but unchanged since we last saw it -- still show it (it's still an open/live
                # EJ-relevant bill), just don't spend a getBill call re-fetching it.
                rows.append(_row_from_masterlist(st, b))
                continue
            n_changed += 1
            if usage_remaining() <= 0:
                rows.append(_row_from_masterlist(st, b))  # cap hit -- fall back to masterlist data, no getBill
                continue
            try:
                bd = call('getBill', id=bill_id)
                rows.append(_row_from_getbill(st, bd.get('bill', {}), b))
            except Exception as e:
                print(f'legiscan: getBill({st}, {bill_id}) failed: {e}; using masterlist data instead.', file=sys.stderr)
                rows.append(_row_from_masterlist(st, b))
            hashes[bill_id] = chash
        print(f'legiscan[{st}]: {n_total} bills scanned, {n_matched} match EJ vocabulary, {n_changed} fetched via getBill')
    write_json(HASH_PATH, hashes)
    set_throttle()
    print(f'legiscan: {len(rows)} total EJ-matched bill(s) across {", ".join(STATES)}; '
          f'{load_json(USAGE_PATH, {}).get(month_key(), 0)}/{MONTHLY_CAP} LegiScan calls used this month')
    return rows


def _row_from_masterlist(state, b):
    num = b.get('number', '')
    return {
        'id': row_id('legiscan', state, str(b.get('bill_id'))),
        'date': b.get('last_action_date') or b.get('status_date'),
        'title': f"{num}: {b.get('title', '')}"[:200],
        'url': b.get('url'),
        'source': f'{state} Legislature',
        'deadline': None,
        'tags': ['legiscan'],
        'state': state,
        'kind': None,
    }


def _row_from_getbill(state, bill, fallback):
    num = bill.get('bill_number') or fallback.get('number', '')
    title = bill.get('title') or fallback.get('title', '')
    return {
        'id': row_id('legiscan', state, str(bill.get('bill_id') or fallback.get('bill_id'))),
        'date': bill.get('last_action_date') or fallback.get('last_action_date'),
        'title': f"{num}: {title}"[:200],
        'url': bill.get('url') or fallback.get('url'),
        'source': f'{state} Legislature',
        'deadline': None,
        'tags': ['legiscan'],
        'state': state,
        'kind': None,
    }


if __name__ == '__main__':
    result = run()
    if result is None:
        sys.exit(0)  # skip (no key / throttled / capped) -- never an error, never touches the data file
    sys.exit(run_stream('bills_legiscan', lambda: result))
