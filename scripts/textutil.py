"""Shared helpers: candidate ids and whitespace normalization."""
import hashlib
import re

_WS = re.compile(r"\s+")


def candidate_id(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def norm(text):
    """Collapse all whitespace runs (incl. line breaks) to one space."""
    return _WS.sub(" ", text).strip()
