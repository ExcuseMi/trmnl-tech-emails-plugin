#!/usr/bin/env python3
"""Merge data/parts/*.json into data/emails.json (dedupe, validate, sort, minify).

Exits non-zero on any invalid record or when no records are found.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_EXCERPT = 600
MAX_CONTEXT = 160
DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")
COMMON = {
    "id": str, "date": str, "context": str,
    "company": list, "people": list, "source": dict,
}
EMAIL = {
    "from": str, "to": list, "cc": list,
    "subject": str, "excerpt": str,
}
CHAT = {"messages": list}
SOURCE_REQUIRED = ("title", "url", "locator")
MAX_MESSAGES = 30


def check_date(value):
    m = DATE_RE.match(value)
    if not m:
        return False
    y, mo, d = m.groups()
    try:
        if d:
            date(int(y), int(mo), int(d))
        elif mo:
            date(int(y), int(mo), 1)
    except ValueError:
        return False
    return True


def _check_types(rec, spec, errs):
    for key, typ in spec.items():
        if key not in rec:
            errs.append(f"missing {key}")
        elif not isinstance(rec[key], typ):
            errs.append(f"{key} must be {typ.__name__}")


def validate(rec):
    """Return a list of problems (empty when the record is valid).

    kind is "email" (default when absent) or "chat".
    """
    errs = []
    if not isinstance(rec, dict):
        return ["record is not an object"]
    kind = rec.get("kind", "email")
    if kind not in ("email", "chat"):
        return [f"bad kind {kind!r}"]
    _check_types(rec, COMMON, errs)
    _check_types(rec, EMAIL if kind == "email" else CHAT, errs)
    if errs:
        return errs
    for key in ("id", "context"):
        if not rec[key].strip():
            errs.append(f"{key} is empty")
    for key in ("company", "people") + (("to", "cc") if kind == "email" else ()):
        if not all(isinstance(x, str) for x in rec[key]):
            errs.append(f"{key} must hold strings")
    if not rec["company"]:
        errs.append("company is empty")
    if kind == "email":
        for key in ("from", "excerpt"):
            if not rec[key].strip():
                errs.append(f"{key} is empty")
        if len(rec["excerpt"]) > MAX_EXCERPT:
            errs.append(f"excerpt over {MAX_EXCERPT} chars ({len(rec['excerpt'])})")
    else:
        msgs = rec["messages"]
        if not msgs:
            errs.append("messages is empty")
        if len(msgs) > MAX_MESSAGES:
            errs.append(f"more than {MAX_MESSAGES} messages ({len(msgs)})")
        for i, m in enumerate(msgs):
            if not (isinstance(m, dict) and isinstance(m.get("from"), str)
                    and isinstance(m.get("text"), str) and m["from"].strip() and m["text"].strip()):
                errs.append(f"message {i} needs from and text")
            elif len(m["text"]) > MAX_EXCERPT:
                errs.append(f"message {i} text over {MAX_EXCERPT} chars ({len(m['text'])})")
    if len(rec["context"]) > MAX_CONTEXT:
        errs.append(f"context over {MAX_CONTEXT} chars ({len(rec['context'])})")
    if not check_date(rec["date"]):
        errs.append(f"bad date {rec['date']!r}")
    src = rec["source"]
    for key in SOURCE_REQUIRED:
        if not isinstance(src.get(key), str) or not src[key].strip():
            errs.append(f"source.{key} missing")
    if isinstance(src.get("url"), str) and not src["url"].startswith("https://"):
        errs.append("source.url must be https")
    return errs


def dedupe_key(rec):
    if rec.get("kind") == "chat":
        m = rec["messages"][0]
        return (m["from"].strip().lower(), rec["date"], m["text"].strip()[:60].lower())
    return (rec["from"].strip().lower(), rec["date"], rec["excerpt"].strip()[:60].lower())


def merge(parts_dir):
    """Return (records, problems). problems is a list of 'file#i id: msg'."""
    records, problems, seen = [], [], set()
    files = sorted(Path(parts_dir).glob("*.json"))
    if not files:
        problems.append(f"no part files in {parts_dir}")
    for f in files:
        try:
            items = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{f.name}: unreadable ({exc})")
            continue
        if not isinstance(items, list):
            problems.append(f"{f.name}: not a JSON array")
            continue
        for i, rec in enumerate(items):
            errs = validate(rec)
            if errs:
                rid = rec.get("id", "?") if isinstance(rec, dict) else "?"
                problems.append(f"{f.name}#{i} {rid}: " + "; ".join(errs))
                continue
            key = dedupe_key(rec)
            if key in seen:
                continue
            seen.add(key)
            records.append(rec)
    ids = [r["id"] for r in records]
    for dup in sorted({x for x in ids if ids.count(x) > 1}):
        problems.append(f"duplicate id {dup}")
    records.sort(key=lambda r: (r["date"], r["id"]))
    return records, problems


def main(argv):
    parts = Path(argv[1]) if len(argv) > 1 else ROOT / "data" / "parts"
    out = Path(argv[2]) if len(argv) > 2 else ROOT / "data" / "emails.json"
    records, problems = merge(parts)
    if problems:
        for p in problems:
            print("INVALID:", p, file=sys.stderr)
        return 1
    data = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    out.write_text(data, encoding="utf-8")
    print(f"{len(records)} records, {len(data.encode('utf-8'))} bytes -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
