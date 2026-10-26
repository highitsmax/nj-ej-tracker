#!/usr/bin/env python3
"""NJ EJ Tracker, stream: NJ Legislature committee hearings on EJ bills.

Feature B of BRIEF_builder_v3_hearings_2026-10-26.md. The committee-schedule pages on njleg.state.nj.us
are a Next.js app -- the HTML has no data. Discovery (plain curl, no bot-protection workaround) found the
JSON the app itself calls:

  1. GET /api/schedules/house/S  (Senate) and /api/schedules/house/A (Assembly) -- every committee meeting
     for that house: Code_Description (committee name), Committee_House (code), Agenda_Date_Parameter,
     AgendaTypeDescription, Agenda_Location, ScheduleStatus ('upcoming' | 'current' | 'past' | 'cancelled'),
     ScheduleLink.
  2. For a given meeting: GET /api/committeeWork/agendas/billsOnAgenda/<Agenda_Date_Parameter>/
     <Committee_House>/<AgendaTypeDescription> -- the bills on that meeting's agenda: Bill, Synopsis,
     Sponsors, IdenticalBillNumber. Confirmed live 2026-10-26 (e.g. SLP 2026-10-15 returned S1800/S4312).

Matching (brief step 2): a meeting is kept if at least one agenda bill either (a) is already in our NJ
bill tracker (data/bills.json -- Bill or its IdenticalBillNumber matches a bill number we already
EJ-matched there), or (b) matches the EJ vocabulary in src/ej_terms.json applied to the agenda bill's
Synopsis. ASSUMPTION (brief says "match against X and Y", not spelled out further): treated as OR --
either criterion alone qualifies a bill. Logged in BUILD_REPORT per the brief's "log it" instruction.

Writes data/nj_committees.json and data/nj_committees.status.json. Run: python3 src/nj_committees.py
Manual verification only (not used by the GitHub Actions workflow): --include-past (or env
NJCOMM_INCLUDE_PAST=1) also checks every past meeting in the current session (~250 meetings, ~1 minute),
so a one-time check can prove the matching code works even when the Legislature isn't currently in
session (the brief
flags this is likely true in late October of an election year).
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import EJMatcher, curl, data_path, load_json, load_rules, row_id, run_stream  # noqa: E402

SCHEDULE_URL = 'https://www.njleg.state.nj.us/api/schedules/house/{house}'
AGENDA_BILLS_URL = 'https://www.njleg.state.nj.us/api/committeeWork/agendas/billsOnAgenda/{date}/{committee}/{atype}'
LIVE_STATUSES = {'upcoming', 'current'}


def already_tracked_bill_numbers():
    """Base bill numbers (e.g. 'A5692', 'S1800') already EJ-matched in data/bills.json -- bills.py's title
    field always starts with the actual bill number, optionally followed by an amendment suffix."""
    nums = set()
    for b in load_json(data_path('bills'), []):
        m = re.match(r'^([A-Za-z]+\d+)', b.get('title') or '')
        if m:
            nums.add(m.group(1).upper())
    return nums


def fetch_house_meetings(house):
    """-> (meetings, error-or-None). A blocked/failed fetch is logged and skipped -- no retries, no
    header tricks, per the brief's bot-protection rule."""
    r = curl(SCHEDULE_URL.format(house=house))
    if not r['ok']:
        return [], f'schedules/house/{house}: {r["error"]}'
    try:
        data = json.loads(r['body'])
        return (data[0] if data else []), None
    except Exception as e:
        return [], f'schedules/house/{house}: parse failed ({type(e).__name__}: {e})'


def fetch_bills_on_agenda(meeting):
    date_param = meeting.get('Agenda_Date_Parameter')
    committee = meeting.get('Committee_House')
    atype = meeting.get('AgendaTypeDescription')
    if not (date_param and committee and atype):
        return []
    url = AGENDA_BILLS_URL.format(date=date_param, committee=committee, atype=atype)
    r = curl(url)
    if not r['ok']:
        print(f'nj_committees: billsOnAgenda failed for {committee} {date_param} ({r["error"]})', file=sys.stderr)
        return []
    try:
        return json.loads(r['body'])
    except Exception:
        return []


def bill_matches(bill, tracked, matcher):
    base = (bill.get('Bill') or '').strip().upper()
    ident = (bill.get('IdenticalBillNumber') or '').strip().upper()
    if base in tracked or (ident and ident in tracked):
        return True
    return bool(matcher.match(bill.get('Synopsis') or ''))


def meeting_date(meeting):
    for key in ('Agenda_Time_Start', 'Agenda_Date_for_Query', 'Agenda_Date'):
        v = meeting.get(key)
        if v:
            return v[:10]
    return None


def build_row(meeting, matched_bills):
    committee = meeting.get('Code_Description') or meeting.get('Committee_House') or 'Committee'
    bill_nums = sorted({(b.get('Bill') or '').strip() for b in matched_bills if b.get('Bill')})
    bills_str = ', '.join(bill_nums)
    short_title = re.sub(r'\s+', ' ', (matched_bills[0].get('Synopsis') or '')).strip()[:90]
    date = meeting_date(meeting)
    link = meeting.get('ScheduleLink') or ''
    url = f'https://www.njleg.state.nj.us{link}' if link else 'https://www.njleg.state.nj.us/committees'
    return {
        'id': row_id('njcomm', meeting.get('Committee_House'), meeting.get('Agenda_Date_Parameter'), bills_str),
        'date': date,
        'title': f'{committee} — {bills_str}: {short_title}'[:220],
        'url': url,
        'source': 'NJ Legislature',
        'deadline': date,
        'state': 'NJ',
        'kind': 'hearing',
    }


def run():
    include_past = '--include-past' in sys.argv or os.environ.get('NJCOMM_INCLUDE_PAST') == '1'
    statuses = LIVE_STATUSES | {'past'} if include_past else LIVE_STATUSES
    tracked = already_tracked_bill_numbers()
    rules = load_rules()
    matcher = EJMatcher(rules['core_terms'], rules.get('exclude_phrases'), rules.get('siting_nouns'))

    rows, errors, n_checked = [], [], 0
    for house in ('S', 'A'):
        meetings, err = fetch_house_meetings(house)
        if err:
            errors.append(err)
            continue
        cand = [m for m in meetings if m.get('ScheduleStatus') in statuses]
        cand.sort(key=lambda m: m.get('Agenda_Date') or '', reverse=True)
        for m in cand:
            n_checked += 1
            matched = [b for b in fetch_bills_on_agenda(m) if bill_matches(b, tracked, matcher)]
            if matched:
                rows.append(build_row(m, matched))

    note = f' -- {len(errors)} fetch error(s): {"; ".join(errors)}' if errors else ''
    mode = 'past-included (verification)' if include_past else 'upcoming-only (live)'
    print(f'nj_committees: {mode}, checked {n_checked} meeting(s), {len(rows)} hearing(s) with EJ-matched bills{note}')
    return rows


if __name__ == '__main__':
    sys.exit(run_stream('nj_committees', run))
