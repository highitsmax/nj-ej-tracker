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


def fmt_row(r, with_deadline=True):
    date = esc(r.get('date') or '')
    title = esc(r.get('title') or '')
    url = esc(r.get('url') or '#')
    source = esc(r.get('source') or '')
    deadline = r.get('deadline')
    dl = f'<td class="dl">{esc(deadline)}</td>' if with_deadline else ''
    return (f'<tr><td class="dt">{date}</td><td class="ti"><a href="{url}">{title}</a></td>'
            f'<td class="src">{source}</td>{dl}</tr>')


def panel_html(name, label, unconfigured_env, rows, st):
    note = ''
    if unconfigured_env and not rows and st.get('ok') is not False:
        return f'<h2>{esc(label)}</h2><p class="empty">Not connected yet -- set {esc(unconfigured_env)} as a repo secret to turn this on.</p>'
    if st.get('ok') is False:
        note = f'<p class="stale">Live pass failed this run ({esc(st.get("note", ""))}) -- showing last good data from {esc((st.get("last_success") or "unknown")[:10])}.</p>'
    if not rows:
        return f'<h2>{esc(label)}</h2>{note}<p class="empty">No items currently match.</p>'
    header = '<tr><th>Date</th><th>Item</th><th>Source</th><th>Deadline</th></tr>'
    body = '\n'.join(fmt_row(r) for r in rows)
    return f'<h2>{esc(label)}</h2>{note}<table><thead>{header}</thead><tbody>{body}</tbody></table>'


def top_strip(all_rows):
    cutoff = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    tdy = today()
    due = [r for r in all_rows if r.get('deadline') and tdy <= r['deadline'] <= cutoff]
    due.sort(key=lambda r: r['deadline'])
    if not due:
        return '<p class="empty">Nothing due to apply or comment on in the next 30 days.</p>'
    rows = '\n'.join(
        f'<tr><td class="dl">{esc(r["deadline"])}</td><td class="ti"><a href="{esc(r.get("url") or "#")}">{esc(r.get("title") or "")}</a></td>'
        f'<td class="src">{esc(r.get("source") or "")}</td></tr>' for r in due)
    return f'<table><thead><tr><th>Due</th><th>Item</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table>'


CSS = """
body { font-family: Verdana, Geneva, Arial, sans-serif; font-size: 13px; color: #111; background: #fff;
       margin: 0; padding: 12px 16px 40px; max-width: 980px; }
h1 { font-size: 18px; margin: 0 0 2px; }
.sub { color: #555; font-size: 12px; margin: 0 0 18px; }
h2 { font-size: 14px; border-bottom: 1px solid #999; padding-bottom: 3px; margin: 26px 0 8px; }
table { width: 100%; border-collapse: collapse; margin-bottom: 4px; }
th, td { text-align: left; padding: 3px 8px 3px 0; vertical-align: top; border-bottom: 1px solid #ddd; }
th { font-weight: bold; border-bottom: 1px solid #999; white-space: nowrap; }
td.dt, td.dl, th:first-child, th:last-child { white-space: nowrap; }
td.ti { width: 55%; }
a { color: #0645AD; text-decoration: none; }
a:hover { text-decoration: underline; }
.empty { color: #777; font-style: italic; margin: 4px 0 0; }
.stale { color: #a33; font-size: 12px; margin: 4px 0; }
#top table th, #top table td { border-bottom: 1px solid #999; }
footer { margin-top: 30px; color: #777; font-size: 11px; border-top: 1px solid #ccc; padding-top: 8px; }
@media (max-width: 700px) {
  body { font-size: 14px; padding: 10px 10px 30px; }
  table, thead, tbody, th, td, tr { display: block; }
  thead tr { display: none; }
  tr { border-bottom: 1px solid #ccc; padding: 6px 0; }
  td { border-bottom: none; padding: 1px 0; }
  td.dt::before { content: "Date: "; color: #777; }
  td.dl::before { content: "Deadline: "; color: #777; }
  td.src::before { content: "Source: "; color: #777; }
}
"""


def build():
    all_rows = []
    sections = []
    for name, label, env in PANELS:
        rows, st = load_panel(name)
        all_rows.extend(rows)
        sections.append(panel_html(name, label, env, rows, st))

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NJ EJ Tracker</title>
<style>{CSS}</style>
</head>
<body>
<h1>NJ Environmental Justice Tracker</h1>
<p class="sub">Pollution, industry and highway siting in overburdened NJ communities, plus grants and jobs.
Last updated {esc(now())}.</p>

<h2 id="top">Apply / comment by (next 30 days)</h2>
{top_strip(all_rows)}

{''.join(f'<div>{s}</div>' for s in sections)}

<footer>Plain scripts, no AI. Sources: see README.md. Data refreshes every 3 hours via GitHub Actions.</footer>
</body>
</html>
"""
    os.makedirs(BUILD_DIR, exist_ok=True)
    with open(os.path.join(BUILD_DIR, 'index.html'), 'w') as f:
        f.write(doc)
    print(f'build_page: wrote build/index.html ({len(all_rows)} total rows across {len(PANELS)} panels)')


if __name__ == '__main__':
    build()
