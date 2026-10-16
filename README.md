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
| `scripts/extract.py` | No-AI: downloads new candidates, pdftotext, writes `data/sources/<id>.txt` (gitignored) and `data/extracted/<id>.json` (raw messages) |
| `data/BRIEF.md` | Selection rules the Claude step follows (email and chat) |
| `scripts/verify.py` | Guard: every excerpt and chat text must occur verbatim in its source text; url must be a known candidate |
| `.github/workflows/watch.yml` | Weekly: watch, extract, select, verify, merge, open a PR (never pushes to main) |

## Weekly pipeline

| Step | Needs |
|---|---|
| watch, extract | nothing |
| select (`anthropics/claude-code-action`, pinned to the commit of v1) | secret `ANTHROPIC_API_KEY`; without it the step is skipped with a log line |
| verify, merge | a failure of either fails the job, no PR |

Chat record: `kind: "chat"`, `messages: [{speaker, text}]` (at most 30, each <= 600). Email records may carry `kind: "email"` (default).

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

Plugin views (from `plugin/`):

| What | Command |
|---|---|
| Lint | `./bin/trmnlp lint` |
| Tests, every view on OG, X, BWRY and 7-color | `./bin/trmnlp test` |
| Preview PNGs of all four views from the live data | `./bin/trmnlp build --png` (writes `_build/*.png`; `--color-depth 8` for gray) |
| Live preview in the browser | `./bin/trmnlp serve` |
| Same without Ruby, with Docker | `docker run --rm --pull always -p 4567:4567 -v "$(pwd):/plugin" trmnl/trmnlp serve --bind 0.0.0.0` (`bin/trmnlp` itself falls back to this image when Ruby is missing) |

`build --png` has no device option: BWRY and color looks are checked by the `trmnlp test` cases for `og_bwry` and `inky_impression_7_3`.

## Icon

`assets/icon.svg` (source) and `assets/icon-512.png` (upload), TRMNL coral `#f8654b`.
