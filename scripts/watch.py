#!/usr/bin/env python3
"""Weekly watcher (no AI): find new items on watched sources.

Appends {url, title, source, first_seen[, tip]} to data/candidates.json.
Never writes data/emails.json. One failing source does not stop the others.
"""
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import yaml

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 20
MAX_BYTES = 5_000_000
CL_API = "https://www.courtlistener.com/api/rest/v4/docket-entries/"
UA = "tech-emails-watcher (+https://github.com/ExcuseMi)"


def http_get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read(MAX_BYTES).decode("utf-8", "replace")


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self._href, self._text = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._text = dict(attrs).get("href"), []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


def items_courtlistener(src, get):
    token = os.environ.get("COURTLISTENER_TOKEN")
    headers = {"Authorization": f"Token {token}"} if token else {}
    did = src["id"]
    data = json.loads(get(f"{CL_API}?docket={did}&order_by=-date_filed", headers))
    out = []
    for e in data.get("results", []):
        n = e.get("entry_number")
        desc = " ".join((e.get("description") or "").split())
        title = f"{src.get('name', did)}: entry {n} {desc}".strip()[:300]
        out.append({"url": f"https://www.courtlistener.com/docket/{did}/#entry-{n}", "title": title})
    return out


def items_page(src, get):
    p = _Links()
    p.feed(get(src["url"]))
    out = []
    for href, text in p.links:
        low = href.lower()
        if href and (low.endswith(".pdf") or "exhibit" in low or "exhibit" in text.lower()):
            out.append({"url": urljoin(src["url"], href), "title": text or href})
    return out


def items_rss(src, get):
    root = ET.fromstring(get(src["url"]))
    out = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        if link:
            out.append({"url": link, "title": (it.findtext("title") or link).strip(), "tip": True})
    return out


def run(config, candidates, get=http_get, today=None):
    """Return (new_items, errors). `candidates` is the current list."""
    today = today or date.today().isoformat()
    known = {c["url"] for c in candidates}
    new, errors = [], []
    jobs = [("courtlistener", s, items_courtlistener) for s in config.get("courtlistener", {}).get("dockets") or []]
    jobs += [("page", s, items_page) for s in config.get("pages") or []]
    jobs += [("rss", s, items_rss) for s in config.get("rss") or []]
    for kind, src, fn in jobs:
        label = src.get("name") or src.get("url") or src.get("id")
        try:
            found = fn(src, get)
        except Exception as exc:  # one source must not stop the others
            errors.append(f"{kind} {label}: {exc}")
            continue
        for it in found:
            if it["url"] in known:
                continue
            known.add(it["url"])
            new.append({**it, "source": label, "first_seen": today})
    return new, errors


def main():
    cfg_path = ROOT / "data" / "watch.yml"
    cand_path = ROOT / "data" / "candidates.json"
    config = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    candidates = json.loads(cand_path.read_text(encoding="utf-8")) if cand_path.exists() else []
    new, errors = run(config, candidates)
    for e in errors:
        print("WARN:", e, file=sys.stderr)
    if new:
        cand_path.write_text(json.dumps(candidates + new, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(new)} new candidates, {len(errors)} failed sources")
    return 0


if __name__ == "__main__":
    sys.exit(main())
