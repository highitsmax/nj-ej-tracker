# NJ Environmental Justice Tracker

A PIN-protected, one-page tracker covering
environmental justice in New Jersey: pollution/industry/highway siting in overburdened communities, plus
grants, fellowships, and jobs that individuals or community organizations could apply for.

Static site. GitHub Actions cron (every 3 hours) runs plain Python scripts (stdlib + curl, no third-party
packages, no AI), builds one HTML page, encrypts it with [StatiCrypt](https://github.com/robinmoisson/staticrypt)
using a PIN, and deploys the encrypted page to GitHub Pages. Only the encrypted page is ever public.

Repo: https://github.com/highitsmax/nj-ej-tracker

## How it works

Six streams, each a small script under `src/`, each writing `data/<stream>.json` (a list of
`{id, date, title, url, source, deadline, tags, state}`) and `data/<stream>.status.json`:

| Stream | Script | Source | Needs a key? |
|---|---|---|---|
| News | `src/news.py` | RSS feeds in `src/feeds.txt`, filtered by `src/ej_terms.json` | No |
| NJ Bills | `src/bills.py` | NJ Legislature bulk ZIP (keyless) | No |
| Comment Periods | `src/comments.py` | Federal Register API (keyless) + Regulations.gov | Regulations.gov only |
| Grants (org) | `src/grants.py` | Grants.gov search2, eligibility 12/99 | No |
| Grants (individual) | `src/grants.py` | Grants.gov search2 eligibility 21 + `data/fellowships.json` (hand-kept) | No |
| Jobs | `src/jobs.py` | USAJOBS API | Yes |
| Federal Bills | `src/congress.py` | Congress.gov API | Yes |

`src/build_page.py` reads every `data/*.json` file and writes `build/index.html` -- plain HTML/CSS, no JS,
mobile-friendly. If a stream's live pass fails, its panel keeps showing the last good data with a
"last good: &lt;date&gt;" note instead of going blank (see `common.run_stream`).

If one stream's data is missing or stale, every other stream is unaffected -- each script catches its own
errors and never takes down the whole Actions run.

## Secrets to add (repo Settings -> Secrets and variables -> Actions)

| Secret | Required? | What it does |
|---|---|---|
| `PAGE_PIN` | **Required.** The workflow refuses to deploy if this is empty. | The PIN visitors type to unlock the page. StatiCrypt remembers it in the visitor's browser for 30 days. |
| `USAJOBS_API_KEY` + `USAJOBS_EMAIL` | Optional | Turns on the Jobs panel (USAJOBS federal job search). Free, request at https://developer.usajobs.gov/apirequest/ (~1 day turnaround). Without these, the panel shows "not connected yet". |
| `CONGRESS_API_KEY` | Optional | Turns on the Federal Bills panel. Free, instant signup at https://api.congress.gov/. |
| `REGS_API_KEY` | Optional | Adds Regulations.gov docket data to the Comment Periods panel (Federal Register alone works without it). Free, register at https://open.gsa.gov/api/regulationsgov/. |
| `LEGISCAN_API_KEY` | Optional, inert in v1 | NJ bills come from NJ's own keyless bulk file. LegiScan (other 49 states) is a disabled stub in `src/bills.py` -- setting this key does NOT turn on anything yet; see "Known cuts" below. |

## Changing keywords or feeds

- **News feeds:** edit `src/feeds.txt` (one `URL | Label` per line; `# state:XX` tags a feed's home state).
- **EJ keyword rules:** edit `src/ej_terms.json` -- `core_terms` match alone, `siting_nouns` only count
  combined with a core term, `exclude_phrases` are stripped before matching. Every entry has a `_why`.
- **Hand-kept fellowships:** edit `data/fellowships.json` directly (the Switzer and Agents of Change seed
  entries are marked `"verify"` -- their dollar figures are secondary-source, not re-confirmed on the
  programs' own sites).
- **States this tracker knows about:** `config/states.json`. v1 only actively pulls NJ (bills, some news
  feeds) and US (everything federal). Adding NY/PA/DE/MD/DC is the next lane -- add feeds/sources tagged
  with that state and the page already has a `state` field on every row to filter or group by.

## Running it locally

```
cd nj-ej-tracker
python3 src/news.py
python3 src/bills.py
python3 src/comments.py
python3 src/grants.py
python3 src/jobs.py       # writes an empty list unless USAJOBS_API_KEY/USAJOBS_EMAIL are set
python3 src/congress.py   # writes an empty list unless CONGRESS_API_KEY is set
python3 src/build_page.py
open build/index.html     # unencrypted, local only -- never commit build/ or deploy it directly
```

## Transferring the repo

1. GitHub -> repo Settings -> General -> "Transfer ownership" -> the new owner's GitHub account/org.
2. The new owner re-adds the secrets above (old secrets don't transfer).
3. Any key registered to the previous owner's email (USAJOBS_EMAIL, other API keys) should be
   re-registered under the new owner's email.
4. GitHub Pages settings carry over with the repo; double check Settings -> Pages still points at the
   `gh-pages`/Pages deployment after transfer.

## Known cuts / v1 scope 

- LegiScan (bill tracking for states other than NJ) is a disabled stub, not implemented.
- Jobs and Federal Bills panels are untested live (no keys were available during this build) -- verify the
  field names against a real response the first time a key is added.
- Several feeds the research doc flagged as Cloudflare-blocked from a sandboxed curl (WE ACT, NRDC, SELC,
  The New Lede, UCS, Floodlight) were not retried here; they may work fine from the GitHub Actions runner.
