import copy
import json
from pathlib import Path

import pytest

import merge

FIX = Path(__file__).parent / "fixtures" / "good.json"


def good():
    return json.loads(FIX.read_text())[0]


def parts(tmp_path, records, name="a.json"):
    d = tmp_path / "parts"
    d.mkdir(exist_ok=True)
    (d / name).write_text(json.dumps(records))
    return d


def test_merge_dedupes_and_sorts(tmp_path):
    recs, problems = merge.merge(parts(tmp_path, json.loads(FIX.read_text())))
    assert problems == []
    assert [r["id"] for r in recs] == ["t-0", "t-1"]


@pytest.mark.parametrize("mutate,word", [
    (lambda r: r.pop("excerpt"), "missing excerpt"),
    (lambda r: r.update(excerpt="x" * 601), "excerpt over"),
    (lambda r: r.update(context="x" * 161), "context over"),
    (lambda r: r.update(date="2012-13-40"), "bad date"),
    (lambda r: r.update(date="27/02/2012"), "bad date"),
    (lambda r: r["source"].update(url="http://example.org/x"), "https"),
    (lambda r: r.update(company=[]), "company"),
])
def test_validate_rejects_bad_record(mutate, word):
    r = copy.deepcopy(good())
    mutate(r)
    assert any(word in e for e in merge.validate(r))


def test_valid_record_passes():
    assert merge.validate(good()) == []


def test_merge_reports_bad_record(tmp_path):
    bad = good()
    bad["excerpt"] = "x" * 601
    _, problems = merge.merge(parts(tmp_path, [good(), bad]))
    assert problems


def test_main_exits_nonzero_and_writes_nothing(tmp_path):
    bad = good()
    bad["source"]["url"] = "http://insecure"
    out = tmp_path / "emails.json"
    assert merge.main(["m", str(parts(tmp_path, [bad])), str(out)]) == 1
    assert not out.exists()


def test_main_no_parts_fails(tmp_path):
    (tmp_path / "p").mkdir()
    assert merge.main(["m", str(tmp_path / "p"), str(tmp_path / "o.json")]) == 1


def test_output_is_minified(tmp_path):
    out = tmp_path / "emails.json"
    assert merge.main(["m", str(parts(tmp_path, [good()])), str(out)]) == 0
    text = out.read_text()
    assert text == json.dumps(json.loads(text), ensure_ascii=False, separators=(",", ":"))
    assert json.loads(text)[0]["id"] == "t-1"
