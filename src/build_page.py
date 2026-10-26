#!/usr/bin/env python3
"""NJ EJ Tracker: build build/index.html from data/*.json. Plain HTML/CSS, no JS, no framework. Run this
AFTER the stream scripts (news.py, bills.py, comments.py, grants.py, jobs.py, congress.py) so it reads their
freshest output. Run: python3 src/build_page.py
"""
import html
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR, load_json, now, status_path, today  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.path.join(ROOT, 'build')

PANELS = [
    ('news', 'News', None),
    ('bills', 'NJ Bills', None),
    ('comments', 'Comment Periods', None),
    ('grants_org', 'Grants -- organizations could apply (501(c)(3))', None),
    ('grants_individual', 'Grants & Fellowships -- individuals could apply', None),
    ('jobs', 'Jobs', 'USAJOBS_API_KEY / USAJOBS_EMAIL'),
    ('federal_bills', 'Federal Bills', 'CONGRESS_API_KEY'),
]


def esc(s):
    return html.escape(s or '', quote=True)


def load_panel(name):
    rows = load_json(os.path.join(DATA_DIR, f'{name}.json'), [])
    st = load_json(status_path(name), {})
    return rows, st


def days_left(deadline):
    try:
        d = (datetime.fromisoformat(deadline).date() - datetime.now(timezone.utc).date()).days
    except Exception:
        return ''
    return 'today' if d == 0 else f'{d}d'


def fmt_row(r):
    date = esc((r.get('date') or '')[5:10].replace('-', '/'))
    title = esc(r.get('title') or '')
    url = esc(r.get('url') or '#')
    source = esc(r.get('source') or '')
    st = esc(r.get('state') or '')
    dl = r.get('deadline')
    due = f'<span class="due">due {esc(dl[5:].replace("-", "/"))}</span>' if dl else ''
    return (f'<li><span class="dt">{date}</span><a href="{url}" target="_blank" rel="noopener">{title}</a>'
            f'<span class="meta">{st and f"<b>{st}</b> · "}{source}{due and " · "}{due}</span></li>')


def panel_html(name, label, unconfigured_env, rows, st, cls=''):
    head = f'<div class="ph"><span>{esc(label)}</span><span class="n">{len(rows)}</span></div>'
    if unconfigured_env and not rows and st.get('ok') is not False:
        return f'<section class="p {cls}">{head}<p class="empty">Not connected yet.</p></section>'
    note = ''
    if st.get('ok') is False:
        note = f'<p class="stale">Last update failed; showing data from {esc((st.get("last_success") or "unknown")[:10])}.</p>'
    if not rows:
        return f'<section class="p {cls}">{head}{note}<p class="empty">Nothing open right now.</p></section>'
    body = '\n'.join(fmt_row(r) for r in rows)
    return f'<section class="p {cls}">{head}{note}<ul>{body}</ul></section>'


def top_strip(all_rows):
    cutoff = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    tdy = today()
    seen, due = set(), []
    for r in sorted((r for r in all_rows if r.get('deadline') and tdy <= r['deadline'] <= cutoff), key=lambda r: r['deadline']):
        if r.get('title') in seen:
            continue
        seen.add(r.get('title')); due.append(r)
    head = f'<div class="ph"><span>Apply / comment by · next 30 days</span><span class="n">{len(due)}</span></div>'
    if not due:
        return f'<section class="p due-panel">{head}<p class="empty">Nothing due in the next 30 days.</p></section>'
    items = '\n'.join(
        f'<li><span class="left">{days_left(r["deadline"])}</span><a href="{esc(r.get("url") or "#")}" target="_blank" rel="noopener">{esc(r.get("title") or "")}</a>'
        f'<span class="meta">{esc(r.get("source") or "")} · due {esc(r["deadline"][5:].replace("-", "/"))}</span></li>' for r in due)
    return f'<section class="p due-panel">{head}<ul>{items}</ul></section>'


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
.stats { display: flex; gap: 0; background: var(--card); border-bottom: 1px solid var(--rule); }
.stats div { padding: 7px 18px; border-right: 1px solid var(--rule); }
.stats b { font-size: 16px; color: var(--terra-d); margin-right: 5px; }
.stats span { color: var(--muted); font-size: 11.5px; text-transform: uppercase; letter-spacing: .5px; }
main { flex: 1; min-height: 0; display: grid; gap: 10px; padding: 10px;
       grid-template-columns: 1.35fr 1fr 1fr; grid-template-rows: 1fr 1fr;
       grid-template-areas: "news due bills" "news comments grants"; }
.p { background: var(--card); border: 1px solid var(--rule); border-top: 3px solid var(--terra);
     display: flex; flex-direction: column; min-height: 0; }
.p.news { grid-area: news; border-top-color: var(--brown); }
.p.due-panel { grid-area: due; border-top-color: var(--terra-d); }
.p.bills { grid-area: bills; border-top-color: var(--brown); }
.p.comments { grid-area: comments; }
.p.grants { grid-area: grants; }
.ph { display: flex; justify-content: space-between; padding: 7px 10px 6px; border-bottom: 1px solid var(--rule);
      font-weight: 600; font-size: 11.5px; text-transform: uppercase; letter-spacing: .6px; color: var(--brown); }
.ph .n { color: var(--terra-d); }
ul { list-style: none; margin: 0; padding: 0; overflow-y: auto; flex: 1; }
li { padding: 6px 10px; border-bottom: 1px solid var(--rule); line-height: 1.35; }
li:hover { background: #fbf1e6; }
li a { color: var(--ink); text-decoration: none; font-weight: 500; }
li a:hover { color: var(--terra-d); text-decoration: underline; }
.dt { color: var(--muted); margin-right: 7px; font-size: 11.5px; }
.left { display: inline-block; min-width: 34px; color: var(--terra-d); font-weight: 700; }
.meta { display: block; color: var(--muted); font-size: 11px; margin-top: 1px; }
.meta b { color: var(--brown); font-weight: 600; }
.due { color: var(--terra-d); font-weight: 600; }
.sub2 { padding: 5px 10px; font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase;
        letter-spacing: .5px; background: #f8efe4; border-bottom: 1px solid var(--rule); }
.empty { color: var(--muted); font-style: italic; padding: 8px 10px; margin: 0; }
.stale { color: var(--terra-d); font-size: 11px; padding: 4px 10px; margin: 0; }
.grants .stack { overflow-y: auto; flex: 1; }
.grants .stack ul { overflow: visible; }
footer { color: var(--muted); font-size: 11px; padding: 4px 18px 8px; }
@media (max-width: 900px) {
  body { height: auto; display: block; }
  main { display: flex; flex-direction: column; }
  .p { max-height: 70vh; }
  .stats { flex-wrap: wrap; }
  header .upd { margin-left: 0; width: 100%; }
}
"""


def build():
    data = {name: load_panel(name) for name, _, _ in PANELS}
    all_rows = [r for rows, _ in data.values() for r in rows]
    news, bills, comments = data['news'], data['bills'], data['comments']
    go, gi, jobs, fed = data['grants_org'], data['grants_individual'], data['jobs'], data['federal_bills']

    def sub(label, rows, st, env=None):
        if env and not rows and st.get('ok') is not False:
            return f'<div class="sub2">{esc(label)}</div><p class="empty">Not connected yet.</p>'
        if not rows:
            return f'<div class="sub2">{esc(label)}</div><p class="empty">Nothing open right now.</p>'
        return f'<div class="sub2">{esc(label)} · {len(rows)}</div><ul>' + '\n'.join(fmt_row(r) for r in rows) + '</ul>'

    n_opps = len(go[0]) + len(gi[0]) + len(jobs[0])
    grants = (f'<section class="p grants"><div class="ph"><span>Grants · Fellowships · Jobs</span><span class="n">{n_opps}</span></div>'
              f'<div class="stack">{sub("Organizations can apply", *go)}{sub("Individuals can apply", *gi)}'
              f'{sub("Jobs", *jobs, env="USAJOBS")}{sub("Federal bills", *fed, env="CONGRESS")}</div></section>')
    cutoff = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    n_due = len({r.get('title') for r in all_rows if r.get('deadline') and today() <= r['deadline'] <= cutoff})
    stats = ''.join(f'<div><b>{n}</b><span>{l}</span></div>' for n, l in [
        (len(news[0]), 'stories'), (len(bills[0]), 'NJ bills'), (len(comments[0]), 'open comment periods'),
        (n_due, 'due in 30 days'), (n_opps, 'opportunities')])

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
<header><h1>Environmental Justice Tracker</h1><span class="sub">New Jersey · region · federal</span>
<span class="upd">Updated {esc(now()[:16].replace('T', ' '))} UTC · refreshes every 3 hours</span></header>
<div class="stats">{stats}</div>
<main>
{panel_html('news', 'News', None, *news, cls='news')}
{top_strip(all_rows)}
{panel_html('bills', 'NJ Bills', None, *bills, cls='bills')}
{panel_html('comments', 'Open Comment Periods', None, *comments, cls='comments')}
{grants}
</main>
<footer>Sources: news feeds, NJ Legislature, Federal Register, Grants.gov. Plain scripts, no AI.</footer>
</body>
</html>
"""
    os.makedirs(BUILD_DIR, exist_ok=True)
    with open(os.path.join(BUILD_DIR, 'index.html'), 'w') as f:
        f.write(doc)
    print(f'build_page: wrote build/index.html ({len(all_rows)} total rows)')


if __name__ == '__main__':
    build()
