#!/usr/bin/env python3
"""NJ EJ Tracker: build build/index.html from data/*.json. Plain HTML/CSS, no JS, no framework. Run this
AFTER every stream script so it reads their freshest output. Run: python3 src/build_page.py

v2 layout (2026-10-26, see BRIEF_builder_v2_2026-10-26.md): one screen, 3 columns x 2 rows --
  New Jersey | Deadlines next 30 days | Opportunities
  National & outlets | Weigh in | Pitch & publish
plus a heat/air-quality alert line under the header (only when active) and a "new since yesterday" bar
under the stats strip. Tone rule: opportunities and signal only -- no tutorial copy, no explanatory
paragraphs, plain labels.
"""
import html
import json
import urllib.parse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR, load_json, mark_seen, now, status_path, today  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join(ROOT, 'build')

KIND_LABEL = {'comment': 'comment', 'grant': 'grant', 'fellowship': 'fellowship', 'job': 'job', 'hearing': 'hearing'}


def esc(s):
    return html.escape(s or '', quote=True)


def load_panel(name):
    rows = load_json(os.path.join(DATA_DIR, f'{name}.json'), [])
    st = load_json(status_path(name), {})
    return rows, st


def nice_date(d):
    """'Oct 22' for this year, 'Dec 17, 2025' for older -- month/day alone made multi-year lists look scrambled."""
    try:
        x = datetime.fromisoformat((d or '')[:10]).date()
    except Exception:
        return ''
    return x.strftime('%b %-d') if x.year == datetime.now(timezone.utc).year else x.strftime('%b %-d, %Y')


def days_left(deadline):
    try:
        d = (datetime.fromisoformat(deadline).date() - datetime.now(timezone.utc).date()).days
    except Exception:
        return ''
    return 'today' if d == 0 else f'{d}d'


_PW = None


def paywalled(source):
    global _PW
    if _PW is None:
        try:
            _PW = [o.lower() for o in json.load(open(os.path.join(ROOT, 'config', 'paywalled.json')))['outlets']]
        except Exception:
            _PW = []
    s = (source or '').lower()
    return any(o in s for o in _PW)


def fmt_row(r, show_kind=False):
    date = esc(nice_date(r.get('date')))
    title = esc(r.get('title') or '')
    url = esc(r.get('url') or '#')
    source = esc(r.get('source') or '')
    st = esc(r.get('state') or '')
    dl = r.get('deadline')
    due = f'<span class="due">due {esc(dl[5:].replace("-", "/"))}</span>' if dl else ''
    markers = ''
    if r.get('town'):
        markers += f'<b class="town">{esc(r["town"])}</b> · '
    if r.get('pitch'):
        markers += '<b class="pitchmark">pitches</b> · '
    free = ''
    if paywalled(r.get('source')) and r.get('kind') in (None, 'news'):
        q = urllib.parse.quote_plus(f'"{(r.get("title") or "")[:120]}"')
        free = (f' &middot; <span class="pw">paywall</span> &middot; <a class="free" href="https://news.google.com/search?q={q}" '
                f'target="_blank" rel="noopener">free coverage</a>')
    kind_tag = ''
    if show_kind and r.get('kind') and KIND_LABEL.get(r['kind']):
        kind_tag = f'<span class="kindtag">{esc(KIND_LABEL[r["kind"]])}</span>'
    return (f'<li><span class="dt">{date}</span>{kind_tag}<a href="{url}" target="_blank" rel="noopener">{title}</a>'
            f'<span class="meta">{markers}{st and f"<b>{st}</b> &middot; "}{source}{free}{due and " &middot; "}{due}</span></li>')


def panel_html(label, rows, note='', empty_msg='Nothing open right now.', cls=''):
    head = f'<div class="ph"><span>{esc(label)}</span><span class="n">{len(rows)}</span></div>'
    if not rows:
        note_html = f'<p class="stale">{esc(note)}</p>' if note else ''
        return f'<section class="p {cls}">{head}{note_html}<p class="empty">{esc(empty_msg)}</p></section>'
    note_html = f'<p class="stale">{esc(note)}</p>' if note else ''
    body = '\n'.join(fmt_row(r) for r in rows)
    return f'<section class="p {cls}">{head}{note_html}<ul>{body}</ul></section>'


def stale_note(st):
    if st.get('ok') is False:
        return f'Last update failed; showing data from {(st.get("last_success") or "unknown")[:10]}.'
    return ''


def sub(label, rows, env=None, show_kind=False):
    if env and not rows:
        return f'<div class="sub2">{esc(label)}</div><p class="empty">Not connected yet.</p>'
    if not rows:
        return f'<div class="sub2">{esc(label)}</div><p class="empty">Nothing open right now.</p>'
    return (f'<div class="sub2">{esc(label)} · {len(rows)}</div><ul>'
            + '\n'.join(fmt_row(r, show_kind=show_kind) for r in rows) + '</ul>')


def deadline_strip(all_rows):
    cutoff = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    tdy = today()
    seen, due = set(), []
    for r in sorted((r for r in all_rows if r.get('deadline') and tdy <= r['deadline'] <= cutoff), key=lambda r: r['deadline']):
        if r.get('title') in seen:
            continue
        seen.add(r.get('title')); due.append(r)
    head = f'<div class="ph"><span>Deadlines · next 30 days</span><span class="n">{len(due)}</span></div>'
    if not due:
        return due, f'<section class="p due-panel">{head}<p class="empty">Nothing due in the next 30 days.</p></section>'
    def _kind_tag(r):
        lbl = KIND_LABEL.get(r.get('kind'))
        return f'<span class="kindtag">{esc(lbl)}</span>' if lbl else ''

    items = '\n'.join(
        f'<li><span class="left">{days_left(r["deadline"])}</span>{_kind_tag(r)}'
        f'<a href="{esc(r.get("url") or "#")}" target="_blank" rel="noopener">{esc(r.get("title") or "")}</a>'
        f'<span class="meta">{esc(r.get("source") or "")} &middot; due {esc(r["deadline"][5:].replace("-", "/"))}</span></li>' for r in due)
    return due, f'<section class="p due-panel">{head}<ul>{items}</ul></section>'


def alert_line():
    rows = load_json(os.path.join(DATA_DIR, 'alerts.json'), [])
    if not rows:
        return ''
    parts = []
    for r in rows:
        until = r.get('until')
        until_s = ''
        if until:
            try:
                until_s = datetime.fromisoformat(until).strftime('%b %-d, %-I%p').replace('AM', 'am').replace('PM', 'pm')
            except Exception:
                until_s = until
        parts.append(f"{esc(r.get('event', ''))} · {esc(r.get('area', ''))}{until_s and f' · until {esc(until_s)}'}")
    return f'<div class="alertline">{" &nbsp;|&nbsp; ".join(parts)}</div>'


def njdep_line():
    """v3 (2026-10-26): Feature A (a live NJDEP hearings probe/parser) dropped -- dep.nj.gov sits behind an
    Incapsula/Imperva WAF that blocks plain scripted requests, and this project does not try to get past bot
    protection. The plain link line stays unconditionally so a person can still open the real calendar."""
    return ('<p class="njdeplink"><a href="https://dep.nj.gov/ej/meetings/" target="_blank" '
            'rel="noopener">NJDEP EJ hearings calendar</a> &middot; <a href="https://public.govdelivery.com/accounts/NJDEP/subscriber/new" '
            'target="_blank" rel="noopener">Get NJDEP EJ hearing notices by county (email)</a></p>')


def new_since_yesterday(panel_buckets):
    """panel_buckets: {panel_label: [row, ...]}. Marks every id seen today, returns the HTML bar."""
    all_ids = [r['id'] for rows in panel_buckets.values() for r in rows if r.get('id')]
    new_ids = mark_seen(all_ids)
    groups = []
    counts, titles = [], []
    for label, rows in panel_buckets.items():
        new_rows = [r for r in rows if r.get('id') in new_ids]
        if new_rows:
            counts.append(f'<b>{esc(label)}</b> {len(new_rows)}')
            titles += [(label, r) for r in new_rows]
    if not counts:
        return '<div class="newbar">Nothing new since yesterday.</div>'
    picks = ' &middot; '.join(f'<a href="{esc(r.get("url") or "#")}" target="_blank" rel="noopener">{esc((r.get("title") or "")[:80])}</a>' for _, r in titles[:3])
    pieces, more_s = [' &middot; '.join(counts) + (f' &nbsp;|&nbsp; {picks}' if picks else '')], ''
    return f'<div class="newbar"><b class="newlabel">New since yesterday:</b> {" &middot; ".join(pieces)}{more_s}</div>'


CSS = """
:root { --bg:#f6efe6; --card:#fffaf4; --ink:#3d2a1e; --muted:#8b6f5c; --rule:#e8dccd;
        --terra:#c4663f; --terra-d:#a24f2d; --brown:#6b4430; }
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--bg); color: var(--ink); }
body { font-family: Inter, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; font-size: 12.5px;
       font-variant-numeric: tabular-nums; height: 100vh; display: flex; flex-direction: column; }
header { background: var(--brown); color: #fbf3ea; padding: 10px 18px; display: flex; align-items: baseline;
         gap: 16px; flex-wrap: wrap; border-bottom: 3px solid var(--terra); }
header h1 { font-family: Fraunces, Georgia, serif; font-weight: 600; font-size: 21px; margin: 0; letter-spacing: .2px; }
header .sub { color: #e7cdb8; font-size: 12px; }
header .upd { margin-left: auto; color: #e7cdb8; font-size: 11.5px; }
.alertline { background: var(--terra-d); color: #fff3ea; font-size: 11.5px; font-weight: 600;
             padding: 5px 18px; letter-spacing: .2px; }
.stats { display: flex; gap: 0; background: var(--card); border-bottom: 1px solid var(--rule); flex-wrap: wrap; }
.stats div { padding: 7px 18px; border-right: 1px solid var(--rule); }
.stats b { font-size: 16px; color: var(--terra-d); margin-right: 5px; }
.stats span { color: var(--muted); font-size: 11.5px; text-transform: uppercase; letter-spacing: .5px; }
.newbar { background: #f8efe4; border-bottom: 1px solid var(--rule); padding: 6px 18px; font-size: 11.5px;
          color: var(--ink); white-space: normal; line-height: 1.5; }
.pw { color: var(--muted); font-style: italic; }
.meta a.free { color: var(--terra-d); font-weight: 400; text-decoration: underline; }
.newbar a { color: var(--ink); } .newbar a:hover { color: var(--terra-d); }
.newbar .newlabel { color: var(--brown); text-transform: uppercase; letter-spacing: .4px; font-size: 10.5px; margin-right: 4px; }
main { flex: 1; min-height: 0; display: grid; gap: 10px; padding: 10px;
       grid-template-columns: 1.35fr 1fr 1fr; grid-template-rows: 1fr 1fr;
       grid-template-areas: "nj due opps" "national weighin pitch"; }
.p { background: var(--card); border: 1px solid var(--rule); border-top: 3px solid var(--terra);
     display: flex; flex-direction: column; min-height: 0; }
.p.nj { grid-area: nj; border-top-color: var(--brown); }
.p.national { grid-area: national; border-top-color: var(--brown); }
.p.due-panel { grid-area: due; border-top-color: var(--terra-d); }
.p.opps { grid-area: opps; }
.p.weighin { grid-area: weighin; }
.p.pitch { grid-area: pitch; }
.ph { display: flex; justify-content: space-between; padding: 7px 10px 6px; border-bottom: 1px solid var(--rule);
      font-weight: 600; font-size: 11.5px; text-transform: uppercase; letter-spacing: .6px; color: var(--brown); }
.ph .n { color: var(--terra-d); }
ul { list-style: none; margin: 0; padding: 0; overflow-y: auto; flex: 1; }
li { padding: 6px 10px; border-bottom: 1px solid var(--rule); line-height: 1.35; }
li:hover { background: #fbf1e6; }
li a { color: var(--ink); text-decoration: none; font-weight: 500; }
li a:hover { color: var(--terra-d); text-decoration: underline; }
.dt { color: var(--muted); margin-right: 7px; font-size: 11.5px; white-space: nowrap; }
.left { display: inline-block; min-width: 34px; color: var(--terra-d); font-weight: 700; }
.meta { display: block; color: var(--muted); font-size: 11px; margin-top: 1px; }
.meta b { color: var(--brown); font-weight: 600; }
.meta b.town { color: var(--terra-d); }
.meta b.pitchmark { color: var(--terra-d); text-transform: uppercase; font-size: 10px; letter-spacing: .4px; }
.due { color: var(--terra-d); font-weight: 600; }
.kindtag { display: inline-block; font-size: 9.5px; text-transform: uppercase; letter-spacing: .4px;
           color: var(--terra-d); border: 1px solid var(--terra-d); border-radius: 3px; padding: 0 4px;
           margin-right: 6px; vertical-align: 1px; }
.sub2 { padding: 5px 10px; font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase;
        letter-spacing: .5px; background: #f8efe4; border-bottom: 1px solid var(--rule); }
.empty { color: var(--muted); font-style: italic; padding: 8px 10px; margin: 0; }
.stale { color: var(--terra-d); font-size: 11px; padding: 4px 10px; margin: 0; }
.njdeplink { padding: 6px 10px; margin: 0; font-size: 11.5px; border-top: 1px solid var(--rule); }
.stack { overflow-y: auto; flex: 1; }
.stack ul { overflow: visible; }
footer { color: var(--muted); font-size: 11px; padding: 4px 18px 8px; }
footer a { color: var(--brown); }
@media (max-width: 900px) {
  body { height: auto; display: block; }
  main { display: flex; flex-direction: column; }
  .p { max-height: 70vh; }
  .stats { flex-wrap: wrap; }
  header .upd { margin-left: 0; width: 100%; }
  .newbar { white-space: normal; }
}
"""

FOOTER_LINKS = [
    ('NJ overburdened communities map', 'https://dep.nj.gov/ej/'),
    ('NJ EJ law (N.J.S.A. 13:1D-157)', 'https://codes.findlaw.com/nj/title-13-conservation-and-development-parks-and-reservations/nj-st-sect-13-1d-157/'),
    ('CDC Environmental Justice Index', 'https://www.atsdr.cdc.gov/place-health/php/eji/index.html'),
    ('CEJST (unofficial mirror)', 'https://screening-tools.com/climate-economic-justice-screening-tool'),
    ('Candid foundation search', 'https://grantspace.candid.org/'),
]


def build():
    nj, nj_st = load_panel('news_nj')
    national, national_st = load_panel('news_national')
    bills_nj, bills_nj_st = load_panel('bills')
    bills_leg, bills_leg_st = load_panel('bills_legiscan')
    comments, comments_st = load_panel('comments')
    grants_org, grants_org_st = load_panel('grants_org')
    funders, funders_st = load_panel('funders')
    fellowships, fellowships_st = load_panel('fellowships')
    jobs, jobs_st = load_panel('jobs')
    outlets, outlets_st = load_panel('outlets')
    pitch_calls, pitch_calls_st = load_panel('pitch_calls')
    hearings, hearings_st = load_panel('nj_committees')

    bills_all = bills_nj + bills_leg
    grants_all = grants_org + funders
    hearings_sorted = sorted(hearings, key=lambda r: r.get('date') or '')
    all_rows = nj + national + bills_all + comments + grants_all + fellowships + jobs + outlets + pitch_calls + hearings

    # -- New Jersey --
    nj_html = panel_html('New Jersey', nj, note=stale_note(nj_st), cls='nj')

    # -- National & outlets --
    national_html = panel_html('National & outlets', national, note=stale_note(national_st), cls='national')

    # -- Deadlines next 30 days --
    due_rows, due_html = deadline_strip(all_rows)

    # -- Opportunities (Jobs / Fellowships / Grants -- organizations) --
    n_opps = len(jobs) + len(fellowships) + len(grants_all)
    opps_html = (f'<section class="p opps"><div class="ph"><span>Opportunities</span><span class="n">{n_opps}</span></div>'
                 f'<div class="stack">{sub("Jobs", jobs)}'
                 f'{sub("Fellowships", fellowships)}'
                 f'{sub("Grants -- organizations", grants_all)}</div></section>')

    # -- Weigh in (Hearings / Comment periods / Bills) + NJDEP hearings link line --
    n_weighin = len(hearings_sorted) + len(comments) + len(bills_all)
    weighin_html = (f'<section class="p weighin"><div class="ph"><span>Weigh in</span><span class="n">{n_weighin}</span></div>'
                     f'<div class="stack">{sub("Hearings", hearings_sorted)}'
                     f'{sub("Comment periods", comments)}'
                     f'{sub("Bills", bills_all)}</div>{njdep_line()}</section>')

    # -- Pitch & publish (outlets / pitch calls) --
    n_pitch = len(outlets) + len(pitch_calls)
    pitch_html = (f'<section class="p pitch"><div class="ph"><span>Pitch &amp; publish</span><span class="n">{n_pitch}</span></div>'
                   f'<div class="stack">{sub("Outlets", outlets)}'
                   f'{sub("Pitch calls", pitch_calls)}</div></section>')

    cutoff = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    n_due = len({r.get('title') for r in all_rows if r.get('deadline') and today() <= r['deadline'] <= cutoff})
    stats = ''.join(f'<div><b>{n}</b><span>{l}</span></div>' for n, l in [
        (len(nj), 'NJ stories'), (len(national), 'national & outlets'), (n_weighin, 'weigh in'),
        (n_due, 'due in 30 days'), (n_opps, 'opportunities'), (n_pitch, 'pitch & publish')])

    newbar = new_since_yesterday({
        'New Jersey': nj, 'National & outlets': national, 'Deadlines': due_rows,
        'Opportunities': jobs + fellowships + grants_all, 'Weigh in': comments + bills_all + hearings_sorted,
        'Pitch & publish': outlets + pitch_calls,
    })

    footer_links = ' &middot; '.join(f'<a href="{esc(u)}" target="_blank" rel="noopener">{esc(l)}</a>' for l, u in FOOTER_LINKS)

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NJ EJ Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<header><h1>Environmental Justice Tracker</h1><span class="sub">New Jersey &middot; region &middot; federal</span>
<span class="upd">Updated {esc(now()[:16].replace('T', ' '))} UTC &middot; refreshes every 3 hours</span></header>
{alert_line()}
<div class="stats">{stats}</div>
{newbar}
<main>
{nj_html}
{due_html}
{opps_html}
{national_html}
{weighin_html}
{pitch_html}
</main>
<footer>{footer_links}</footer>
</body>
</html>
"""
    os.makedirs(BUILD_DIR, exist_ok=True)
    with open(os.path.join(BUILD_DIR, 'index.html'), 'w') as f:
        f.write(doc)
    print(f'build_page: wrote build/index.html ({len(all_rows)} total rows)')


if __name__ == '__main__':
    build()
