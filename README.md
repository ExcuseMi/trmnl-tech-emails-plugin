# Tech Emails (TRMNL plugin data)

Public-record tech emails. No backend: the plugin fetches the static `data/emails.json` and picks one email in its serverless transform.

| Path | Job |
|---|---|
| `data/parts/*.json` | Hand-curated records (schema below), one file per source group |
| `data/emails.json` | Built file: merged, deduped, validated, sorted, minified. Never edit by hand |
| `data/watch.yml` | Sources the weekly watcher checks |
| `data/candidates.json` | Watcher output: new items (url, title, source, first_seen, tip). Review only |
| `scripts/merge.py` | `python scripts/merge.py` builds `emails.json`; exits 1 on any invalid record |
| `scripts/watch.py` | No-AI watcher; never writes `emails.json` |
| `.github/workflows/watch.yml` | Weekly run, opens a PR when `candidates.json` changes |

## Record

`id, from, to[], cc[], date (YYYY | YYYY-MM | YYYY-MM-DD), subject, excerpt (<= 600), context (<= 160), company[], people[], source{title, url (https), locator}`.
Duplicates: same from + date + first 60 chars of excerpt.

## Watched sources

| Type | Config | Notes |
|---|---|---|
| CourtListener | docket ids | optional secret `COURTLISTENER_TOKEN` |
| Exhibit pages | URL | links to PDFs or "exhibit" |
| techemails.com RSS | URL | tips only, never copied |

URLs and docket ids in `watch.yml` need a check by a person before the first run.

## Tests

`python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-test.txt && .venv/bin/pytest`
