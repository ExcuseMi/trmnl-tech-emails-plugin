import json

import watch

CONFIG = {
    "courtlistener": {"dockets": [{"id": 7, "name": "Case"}]},
    "pages": [{"name": "Page", "url": "https://x.gov/ex"}],
    "rss": [{"name": "Feed", "url": "https://feed.test/rss"}],
}
CL = json.dumps({"results": [{"entry_number": 5, "description": "Exhibit list"}]})
HTML = '<a href="/a/ex1.pdf">Exhibit 1</a><a href="/about">About</a>'
RSS = "<rss><channel><item><title>Mail</title><link>https://feed.test/p1</link></item></channel></rss>"


def fake(url, headers=None):
    if "courtlistener" in url:
        return CL
    if url.startswith("https://x.gov"):
        return HTML
    return RSS


def test_adds_new_items():
    new, errors = watch.run(CONFIG, [], get=fake, today="2026-10-16")
    assert errors == []
    urls = {n["url"]: n for n in new}
    assert "https://www.courtlistener.com/docket/7/#entry-5" in urls
    assert "https://x.gov/a/ex1.pdf" in urls
    assert urls["https://feed.test/p1"]["tip"] is True
    assert all(n["first_seen"] == "2026-10-16" for n in new)
    assert "https://x.gov/about" not in urls


def test_ignores_known_item():
    known = [{"url": "https://x.gov/a/ex1.pdf"}, {"url": "https://feed.test/p1"}]
    new, _ = watch.run(CONFIG, known, get=fake)
    assert [n["url"] for n in new] == ["https://www.courtlistener.com/docket/7/#entry-5"]


def test_one_failing_source_does_not_stop_others():
    def get(url, headers=None):
        if "courtlistener" in url:
            raise TimeoutError("boom")
        return fake(url)
    new, errors = watch.run(CONFIG, [], get=get)
    assert len(errors) == 1 and "Case" in errors[0]
    assert len(new) == 2


def test_garbage_response_is_an_error_not_a_crash():
    new, errors = watch.run(CONFIG, [], get=lambda u, h=None: "not json or xml <<<")
    assert len(errors) >= 1


def test_courtlistener_auth_or_throttle_is_skipped_not_failed():
    import urllib.error

    def get(url, headers=None):
        if "courtlistener" in url:
            raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
        return fake(url)
    skipped = []
    new, errors = watch.run(CONFIG, [], get=get, skipped=skipped)
    assert errors == [] and len(skipped) == 1 and "401" in skipped[0]
    assert len(new) == 2


def test_baseline_marks_every_present_item_known():
    new, errors = watch.run(CONFIG, [], get=fake, today="2026-10-16", baseline=True)
    assert errors == [] and len(new) == 3
    assert all(n["baseline"] is True for n in new)
    again, _ = watch.run(CONFIG, new, get=fake)
    assert again == []  # nothing is new after the baseline


def test_normal_run_does_not_mark_baseline():
    new, _ = watch.run(CONFIG, [], get=fake)
    assert all("baseline" not in n for n in new)
