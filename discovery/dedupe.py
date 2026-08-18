"""
dedupe.py — collapses duplicate/near-duplicate results.

Two kinds of dedup happen:
  1. Within a single run: the same report often surfaces from multiple
     queries (broad search + org site: search + news search all find it).
  2. Across runs: don't re-flag something already sitting in the inbox CSV
     from a previous day, unless its status changed.

Matching is done on a normalized URL first (strip query params, trailing
slash, http vs https) and a fuzzy title match as a fallback, since the same
report can be linked from two different URLs (press release vs PDF vs org
landing page).
"""

import re
from difflib import SequenceMatcher
from typing import List, Set
from urllib.parse import urlparse

from discovery.search import SearchResult


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    netloc = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.rstrip("/")
    return f"{netloc}{path}"


def normalize_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^a-z0-9 ]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def titles_similar(a: str, b: str, threshold: float = 0.82) -> bool:
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio() >= threshold


def dedupe_results(results: List[SearchResult]) -> List[SearchResult]:
    """Removes duplicates within a single batch of search results."""
    unique: List[SearchResult] = []
    seen_urls: Set[str] = set()

    for r in results:
        norm_url = normalize_url(r.url)
        if norm_url in seen_urls:
            continue

        is_dupe = False
        for existing in unique:
            if titles_similar(existing.title, r.title):
                is_dupe = True
                break

        if not is_dupe:
            unique.append(r)
            seen_urls.add(norm_url)

    return unique


def filter_against_existing(
    results: List[SearchResult], existing_urls: Set[str]
) -> List[SearchResult]:
    """Removes results whose normalized URL is already in the inbox CSV."""
    return [r for r in results if normalize_url(r.url) not in existing_urls]


def matches_already_tracked(title: str, already_tracked: List[str]) -> bool:
    """Checks if a result title matches a report FCSC already actively tracks
    (Project 1 / Report Hunt), so it can be labeled instead of re-surfaced
    as a brand-new discovery."""
    norm_title = normalize_title(title)
    for tracked in already_tracked:
        norm_tracked = normalize_title(tracked)
        if norm_tracked in norm_title or norm_title in norm_tracked:
            return True
        if SequenceMatcher(None, norm_title, norm_tracked).ratio() >= 0.7:
            return True
    return False
