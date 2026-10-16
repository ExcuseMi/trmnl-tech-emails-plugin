#!/usr/bin/env python3
"""Extract raw candidate messages from the documents in data/candidates.json (no AI).

For each candidate without data/extracted/<id>.json: download (bounded), turn a
PDF into text with pdftotext, save data/sources/<id>.txt (gitignored), split
into emails (From/To/Date/Subject headers) and chat lines (sender lines),
and write data/extracted/<id>.json.
"""
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from textutil import candidate_id

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 60
MAX_BYTES = 25_000_000
MAX_BODY = 3000
MAX_PER_RUN = 10  # new documents per run, oldest first; the rest wait for the next run
UA = "tech-emails-extractor (+https://github.com/ExcuseMi)"

FROM_RE = re.compile(r"^\s*From:\s*(\S.*)$")
HDR_RE = re.compile(r"^\s*(To|Cc|CC|Date|Sent|Subject)\s*:\s*(.*)$")
CHAT_RE = re.compile(r"^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AaPp][Mm])?\]?\s*)?([A-Z][\w.'-]*(?: [\w.'-]+){0,3}):\s+(\S.*)$")
NOT_SPEAKER = {"From", "To", "Cc", "CC", "Bcc", "Subject", "Date", "Sent", "Re", "Importance",
               "Attachments", "Attachment", "Note", "Notes", "Fwd", "Fw"}
MAX_CHAT = 30


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"document over {MAX_BYTES} bytes")
    return data


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("p", "br", "div", "li", "tr", "h1", "h2", "h3"):
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def to_text(data):
    if data[:5] == b"%PDF-":
        with tempfile.TemporaryDirectory() as d:
            pdf = Path(d) / "in.pdf"
            pdf.write_bytes(data)
            res = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, timeout=120)
        if res.returncode != 0:
            raise RuntimeError("pdftotext failed: " + res.stderr.decode("utf-8", "replace")[:200])
        return res.stdout.decode("utf-8", "replace")
    p = _Text()
    p.feed(data.decode("utf-8", "replace"))
    return "".join(p.out)


def _locator(text, offset):
    while text[offset:offset + 1] == "\f":  # a page break opens the line
        offset += 1
    return f"p. {text.count(chr(12), 0, offset) + 1}"


def split_emails(text):
    """Messages that start at a 'From:' line followed by To/Date/Subject headers."""
    lines = text.split("\n")
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1
    starts = []
    for i, ln in enumerate(lines):
        m = FROM_RE.match(ln)
        if not m:
            continue
        hdr, j = {"from": m.group(1).strip()}, i + 1
        while j < len(lines) and j <= i + 12:
            h = HDR_RE.match(lines[j])
            if h:
                key = h.group(1).lower()
                hdr[key] = h.group(2).strip()
                j += 1
                if key == "subject":
                    break
            elif not lines[j].strip() or (hdr.keys() - {"from"} and lines[j].startswith(" ") and not hdr.get("subject")):
                j += 1  # blank or wrapped header value
            else:
                break
        if "subject" in hdr and ("to" in hdr) and ("date" in hdr or "sent" in hdr):
            starts.append((i, j, hdr))
    out = []
    for k, (i, j, hdr) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        body = "\n".join(lines[j:end]).replace("\f", "\n").strip()
        out.append({
            "kind": "email",
            "from": hdr["from"],
            "to": [x.strip() for x in re.split(r"[;]", hdr.get("to", "")) if x.strip()],
            "cc": [x.strip() for x in re.split(r"[;]", hdr.get("cc", hdr.get("Cc", ""))) if x.strip()],
            "date_raw": hdr.get("date", hdr.get("sent", "")),
            "subject": hdr["subject"],
            "body": body[:MAX_BODY],
            "locator": _locator(text, offsets[i]),
        })
    return out


def split_chats(text):
    """Runs of sender lines ('Name: text') with at least 2 speakers and 3 lines."""
    lines = text.split("\n")
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1
    runs, cur = [], None
    for i, ln in enumerate(lines):
        m = CHAT_RE.match(ln)
        if m and m.group(1) not in NOT_SPEAKER and not HDR_RE.match(ln):
            if cur is None or len(cur["messages"]) >= MAX_CHAT:
                cur = {"start": i, "messages": []}
                runs.append(cur)
            cur["messages"].append({"from": m.group(1), "text": m.group(2).strip()})
        elif cur is not None and ln.strip() and ln.startswith((" ", "\t")):
            cur["messages"][-1]["text"] += " " + ln.strip()
        elif ln.strip():
            cur = None
    out = []
    for r in runs:
        if len(r["messages"]) >= 3 and len({m["from"] for m in r["messages"]}) >= 2:
            out.append({"kind": "chat", "messages": r["messages"], "locator": _locator(text, offsets[r["start"]])})
    return out


def extract_candidate(cand, data_dir, fetch=download):
    cid = candidate_id(cand["url"])
    text = to_text(fetch(cand["url"]))
    (data_dir / "sources").mkdir(parents=True, exist_ok=True)
    (data_dir / "sources" / f"{cid}.txt").write_text(text, encoding="utf-8")
    emails = split_emails(text)
    chats = split_chats(text) if not emails else []
    doc = {
        "id": cid,
        "source": {"title": cand.get("title", cand["url"]), "url": cand["url"]},
        "messages": emails + chats,
    }
    (data_dir / "extracted").mkdir(parents=True, exist_ok=True)
    (data_dir / "extracted" / f"{cid}.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


def run(data_dir, fetch=download, limit=MAX_PER_RUN):
    """Return (new_ids, errors). Extracted, baseline and tip candidates are skipped;
    at most `limit` documents are tried, oldest first_seen first."""
    cands = json.loads((data_dir / "candidates.json").read_text(encoding="utf-8"))
    new, errors = [], []
    pending = []
    for c in cands:
        if c.get("tip") or c.get("baseline"):
            continue  # tips are leads only; baseline items were seen before the first run
        if (data_dir / "extracted" / f"{candidate_id(c['url'])}.json").exists():
            continue
        pending.append(c)
    pending.sort(key=lambda c: c.get("first_seen", ""))  # stable: file order within a day
    for c in pending[:limit]:
        try:
            extract_candidate(c, data_dir, fetch)
            new.append(candidate_id(c["url"]))
        except Exception as exc:  # one document must not stop the others
            errors.append(f"{c['url']}: {exc}")
    return new, errors


def main():
    new, errors = run(ROOT / "data")
    for e in errors:
        print("WARN:", e, file=sys.stderr)
    print("\n".join(new))
    print(f"{len(new)} extracted, {len(errors)} failed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
