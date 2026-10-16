#!/usr/bin/env python3
"""The guard for automatic records (no AI).

Every email excerpt and every chat message text must occur verbatim (only
whitespace and line breaks normalized) in data/sources/<id>.txt, and every
source.url must be a known candidate or an already extracted source.
Any miss prints the record id and exits 1.

usage: verify.py [part.json ...]   (default: data/parts/auto-*.json)
"""
import json
import sys
from pathlib import Path

from textutil import candidate_id, norm

ROOT = Path(__file__).resolve().parent.parent


def known_urls(data_dir):
    urls = set()
    cp = data_dir / "candidates.json"
    if cp.exists():
        urls |= {c["url"] for c in json.loads(cp.read_text(encoding="utf-8"))}
    for f in (data_dir / "extracted").glob("*.json"):
        urls.add(json.loads(f.read_text(encoding="utf-8"))["source"]["url"])
    return urls


def texts_of(rec):
    if rec.get("kind") == "chat":
        return [m.get("text", "") for m in rec.get("messages", [])]
    return [rec.get("excerpt", "")]


def verify_records(records, data_dir):
    """Return a list of problems naming the record."""
    problems, urls, cache = [], known_urls(data_dir), {}
    for rec in records:
        rid = rec.get("id", "?") if isinstance(rec, dict) else "?"
        url = (rec.get("source") or {}).get("url") if isinstance(rec, dict) else None
        if url not in urls:
            problems.append(f"{rid}: source.url is not a known candidate or source ({url})")
            continue
        sp = data_dir / "sources" / f"{candidate_id(url)}.txt"
        if not sp.exists():
            problems.append(f"{rid}: source text {sp.name} missing")
            continue
        if sp not in cache:
            cache[sp] = norm(sp.read_text(encoding="utf-8"))
        for t in texts_of(rec):
            if not norm(t) or norm(t) not in cache[sp]:
                problems.append(f"{rid}: text not verbatim in source: {norm(t)[:80]!r}")
    return problems


def main(argv):
    data_dir = ROOT / "data"
    files = [Path(a) for a in argv[1:]] or sorted((data_dir / "parts").glob("auto-*.json"))
    problems = []
    for f in files:
        try:
            recs = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(recs, list):
                raise ValueError("not a JSON array")
        except (OSError, ValueError) as exc:
            problems.append(f"{f.name}: unreadable ({exc})")
            continue
        problems += [f"{f.name} {p}" for p in verify_records(recs, data_dir)]
    for p in problems:
        print("UNVERIFIED:", p, file=sys.stderr)
    print(f"{len(files)} file(s), {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
