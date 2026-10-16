import json

import verify
from textutil import candidate_id

URL = "https://example.org/doc.pdf"
TEXT = "From: A B\nTo: C D\nDate: 1 May 2012\nSubject: s\n\nWe should buy them\nbefore the others do. It is cheap.\n"


def setup(tmp_path):
    d = tmp_path / "data"
    (d / "sources").mkdir(parents=True)
    (d / "extracted").mkdir()
    (d / "candidates.json").write_text(json.dumps([{"url": URL, "title": "t"}]))
    (d / "sources" / f"{candidate_id(URL)}.txt").write_text(TEXT)
    return d


def email(excerpt, url=URL):
    return {"id": "r1", "kind": "email", "excerpt": excerpt, "source": {"url": url}}


def test_accepts_exact_excerpt_across_line_break(tmp_path):
    d = setup(tmp_path)
    assert verify.verify_records([email("We should buy them before the others do.")], d) == []


def test_rejects_one_word_changed(tmp_path):
    d = setup(tmp_path)
    probs = verify.verify_records([email("We should buy them before the others did.")], d)
    assert probs and "r1" in probs[0]


def test_rejects_unknown_url(tmp_path):
    d = setup(tmp_path)
    assert verify.verify_records([email("It is cheap.", "https://evil.test/x")], d)


def test_missing_source_text_fails(tmp_path):
    d = setup(tmp_path)
    (d / "sources" / f"{candidate_id(URL)}.txt").unlink()
    assert verify.verify_records([email("It is cheap.")], d)


def test_chat_every_message_checked(tmp_path):
    d = setup(tmp_path)
    ok = {"id": "c1", "kind": "chat", "source": {"url": URL},
          "messages": [{"speaker": "A", "text": "It is cheap."}, {"speaker": "B", "text": "We should buy them"}]}
    assert verify.verify_records([ok], d) == []
    ok["messages"][1]["text"] = "We should sell them"
    assert verify.verify_records([ok], d)
