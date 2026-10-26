# NJ Environmental Justice Tracker

A PIN-protected, one-page tracker covering environmental justice in New Jersey and the Mid-Atlantic
(NY/PA/DE/MD/DC): pollution/industry/highway siting in overburdened communities, open comment periods and
bills, grants/fellowships/jobs, air-quality and heat alerts, and freelance pitch opportunities at EJ/climate
outlets. v2 (2026-10-26) layout is six panels, one screen: New Jersey, Deadlines next 30 days,
Opportunities, National & outlets, Weigh in, Pitch & publish.

Static site. GitHub Actions cron (every 3 hours) runs plain Python scripts (stdlib + curl, one optional
third-party package, no AI), builds one HTML page, encrypts it with
[StatiCrypt](https://github.com/robinmoisson/staticrypt) using a PIN, and deploys the encrypted page to
GitHub Pages. Only the encrypted page is ever public.

Repo: https://github.com/highitsmax/nj-ej-tracker

## How it works

Each script under `src/` writes `data/<stream>.json` (a list of row dicts: `id, date, title, url, source,
deadline, tags, state, kind`, plus optional `town`/`pitch` markers) and `data/<stream>.status.json`:

| Stream | Script | Source | Needs a key? |
|---|---|---|---|
| New Jersey / National & outlets news | `src/news.py` | RSS feeds in `src/feeds.txt` (NJ outlets, allied-org press, pitch outlets, hyperlocal town queries), filtered by `src/ej_terms.json` | No |
| NJ Bills | `src/bills.py` | NJ Legislature bulk ZIP (keyless) | No |
| NY/PA/DE/MD/DC Bills | `src/legiscan.py` | LegiScan API (`getMasterList` + `getBill`, rate-limited, 2,500 calls/month cap) | Yes (`LEGISCAN_API_KEY`) |
| Comment Periods | `src/comments.py` | Federal Register API (keyless) + Regulations.gov; drops any result naming a state outside NJ/NY/PA/DE/MD/DC | Regulations.gov only |
| Grants -- organizations | `src/grants.py` | Grants.gov search2 (eligibility 12/99) + hand-kept `data/funders.json` (from `src/funders_seed.json`) | No |
| Fellowships | `src/grants.py` | Hand-kept `data/fellowships.json` (from `src/fellowships_seed.json`) | No |
| Jobs | `src/jobs.py` | USAJOBS API + ATS orgs in `src/orgs_ats.json` (Greenhouse/Lever/Workable/BambooHR, keyless) + JobSpy (guarded import) | USAJOBS only |
| Outlets / Pitch calls | `src/outlets.py` | Hand-kept `data/outlets.json` (from `src/outlets_seed.json`) + a live Google News query | No |
| Air/heat alerts | `src/alerts.py` | NWS `alerts/active` for Western Essex County NJ (zone NJZ105) and Baltimore City MD (zone MDZ011) | No |
| NJDEP hearings probe | `src/njdep_probe.py` | Informational only -- dep.nj.gov is Incapsula-walled; writes `data/njdep_probe.json`, no parser | No |
| Federal Bills | `src/congress.py` | Congress.gov API -- script kept, panel removed from the page (see Known cuts) | Yes |

`src/build_page.py` reads every `data/*.json` file and writes `build/index.html` -- plain HTML/CSS, no JS,
mobile-friendly. It also updates `data/seen.json` (first-seen timestamps, pruned after 60 days) to drive
the "new since yesterday" bar. If a stream's live pass fails, its panel keeps showing the last good data
with a "last update failed" note instead of going blank (see `common.run_stream`).

If one stream's data is missing or stale, every other stream is unaffected -- each script catches its own
errors and never takes down the whole Actions run.

## Secrets to add (repo Settings -> Secrets and variables -> Actions)

| Secret | Required? | What it does |
|---|---|---|
| `PAGE_PIN` | **Required.** The workflow refuses to deploy if this is empty. | The PIN visitors type to unlock the page. StatiCrypt remembers it in the visitor's browser for 30 days. |
| `USAJOBS_API_KEY` + `USAJOBS_EMAIL` | Optional | Adds USAJOBS federal postings to the Jobs sub-section (the ATS-org postings run keylessly either way). Free, request at https://developer.usajobs.gov/apirequest/ (~1 day turnaround). |
| `CONGRESS_API_KEY` | Optional | Keeps `src/congress.py` running (its panel is no longer rendered on the page -- see Known cuts). Free, instant signup at https://api.congress.gov/. |
| `REGS_API_KEY` | Optional | Adds Regulations.gov docket data to the Weigh-in panel's Comment periods (Federal Register alone works without it). Free, register at https://open.gsa.gov/api/regulationsgov/. |
| `LEGISCAN_API_KEY` | Optional | Turns on NY/PA/DE/MD/DC bill tracking in `src/legiscan.py`. Without it, bills stay NJ-only and the Weigh-in panel's Bills sub-section shows nothing extra. Free registration at https://legiscan.com/legiscan. |

## Changing keywords, feeds, or hand-kept lists

- **News feeds:** edit `src/feeds.txt` (one `URL | Label` per line; trailing `# state:XX kind:allied|pitch|hyperlocal town:Name` tags route the row -- see the file's own header comment).
- **EJ keyword rules:** edit `src/ej_terms.json` -- `core_terms` match alone, `siting_nouns` only count
  combined with a core term, `nj_local_terms` is the fallback for NJ-place stories and the OR-filter for
  pitch outlets, `exclude_phrases` are stripped before matching.
- **LegiScan per-state vocabulary:** `src/legiscan_state_terms.json`.
- **Hand-kept fellowships:** edit `src/fellowships_seed.json` (amounts only show on the page when
  `amount_verified` is true).
- **Hand-kept funders:** edit `src/funders_seed.json` -- `build_funders()` in `src/grants.py` re-applies
  the region + (unsolicited OR open-cycle) filter every run, so adding an entry doesn't guarantee it
  appears.
- **Hand-kept pitch outlets:** edit `src/outlets_seed.json`.
- **ATS job orgs:** `src/orgs_ats.json` (keyless Greenhouse/Lever/Workable/BambooHR endpoints + the job
  keyword filter).
- **States this tracker knows about:** `config/states.json`.

## Running it locally

```
cd nj-ej-tracker
python3 src/news.py
python3 src/bills.py
python3 src/legiscan.py   # no-op unless LEGISCAN_API_KEY is set
python3 src/comments.py
python3 src/grants.py
python3 src/jobs.py       # ATS orgs run keylessly; USAJOBS/JobSpy are additive if available
python3 src/outlets.py
python3 src/alerts.py
python3 src/njdep_probe.py
python3 src/congress.py   # writes an empty list unless CONGRESS_API_KEY is set; panel not rendered
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

## Known cuts / v2 scope

See `BUILD_REPORT_v2_2026-10-26.md` (outside this repo) for the full list with reasoning. Short version:

- Federal Bills panel removed from the page; `src/congress.py` still runs so the data/secret wiring stays
  live if it's ever re-added.
- The old Grants.gov "individual eligibility" pull is gone -- Fellowships is now a pure hand-kept
  sub-section (grants.gov returned ~0 individual-eligible EJ opportunities anyway).
- General national EJ feeds that aren't pitch outlets, allied orgs, or hyperlocal queries (ProPublica, The
  Guardian, Center for Public Integrity, DeSmog, Earthjustice, CHEJ, Checks and Balances Project, EHN,
  Canary Media) were dropped from `src/feeds.txt` -- the "National & outlets" panel is now a hard-defined
  set (pitch outlets + national allied orgs + Baltimore/MD hyperlocal) with no slot for general national
  EJ coverage.
- Sierra's feed (`sierraclub.org/sierra/feed`) is commented out in `src/feeds.txt` -- it 302-redirects to
  itself in this build's sandbox (a bot-block loop); retest from the Actions runner before re-enabling.
- Jobs and Federal Bills live keys were untested (no keys available during this build) -- verify field
  names against a real response the first time a key is added.
