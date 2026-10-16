import json

import extract
from textutil import candidate_id

URL = "https://example.org/mails.pdf"
TEXT = (
    "From: Alice Example\nSent: Monday, May 1, 2012 10:00 AM\nTo: Bob Sample; Carol Test\nCc: Dan\n"
    "Subject: Plan\n\nLet us buy it.\nIt is cheap.\n\f"
    "From: Bob Sample\nSent: Monday, May 1, 2012 11:00 AM\nTo: Alice Example\nSubject: RE: Plan\n\nAgreed.\n"
)
CHAT = "Intro line\nAlice: hello there\nBob: hi\n  and more\nAlice: ok\n"


def test_splits_two_emails_with_locator():
    msgs = extract.split_emails(TEXT)
    assert [m["from"] for m in msgs] == ["Alice Example", "Bob Sample"]
    assert msgs[0]["to"] == ["Bob Sample", "Carol Test"] and msgs[0]["cc"] == ["Dan"]
    assert msgs[0]["subject"] == "Plan" and "buy it" in msgs[0]["body"]
    assert msgs[0]["locator"] == "p. 1" and msgs[1]["locator"] == "p. 2"
    assert msgs[1]["body"] == "Agreed."


def test_splits_chat():
    chats = extract.split_chats(CHAT)
    assert len(chats) == 1
    assert [m["from"] for m in chats[0]["messages"]] == ["Alice", "Bob", "Alice"]
    assert chats[0]["messages"][1]["text"] == "hi and more"


def test_header_lines_are_not_chat():
    assert extract.split_chats(TEXT) == []


def test_run_writes_source_and_extracted_and_skips_done(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "candidates.json").write_text(json.dumps([{"url": URL, "title": "T"}, {"url": "https://x.test/tip", "tip": True}]))
    calls = []

    def fetch(url):
        calls.append(url)
        return TEXT.encode()

    new, errors = extract.run(d, fetch)
    cid = candidate_id(URL)
    assert new == [cid] and errors == [] and calls == [URL]
    assert (d / "sources" / f"{cid}.txt").read_text() == TEXT
    doc = json.loads((d / "extracted" / f"{cid}.json").read_text())
    assert len(doc["messages"]) == 2 and doc["source"]["url"] == URL
    assert extract.run(d, fetch) == ([], [])
    assert calls == [URL]


def test_failed_download_is_reported_not_fatal(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "candidates.json").write_text(json.dumps([{"url": URL}]))

    def boom(url):
        raise TimeoutError("slow")

    new, errors = extract.run(d, boom)
    assert new == [] and len(errors) == 1


def test_html_is_stripped():
    assert "Hello" in extract.to_text(b"<html><script>x()</script><p>Hello</p></html>")
