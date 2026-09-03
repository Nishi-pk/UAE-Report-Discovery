"""
search.py — builds queries from config.yaml and runs them against a
pluggable web search provider.

Why a pluggable provider instead of scraping Google/Bing directly?
Scraping search engines directly is unreliable (they block bots, layouts
change, and it can violate ToS). Cheap, stable APIs exist instead:

  - Serper.dev       (default here — cheap, simple REST API, ~$50/50k queries)
  - Bing Web Search   (Azure Cognitive Services)
  - Google Custom Search JSON API (100 free queries/day, then paid)

Only ONE of these needs an API key for this project to run. Set it as a
GitHub Actions secret (see .github/workflows/daily_discovery.yml) or a
local .env file.
"""

import os
import time
import itertools
import requests
from typing import List, Dict, Any


class SearchResult:
    def __init__(self, title: str, url: str, snippet: str, query: str):
        self.title = title
        self.url = url
        self.snippet = snippet
        self.query = query  # which query surfaced this, useful for debugging

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "query": self.query,
        }


def build_queries(config: dict) -> List[Dict[str, Any]]:
    """
    Builds the full list of search queries from config.yaml:
      1. subject x year x terminology combos   (broad discovery)
      2. subject x year x priority_org site: searches (targeted discovery)
      3. subject x year "news" style combos     (catches news coverage
         of reports that aren't well indexed on the org's own site)

    Each query is returned as {"query": str, "is_news": bool}. Only "news"
    style queries (recipe 3) are flagged is_news=True — these are the ones
    prone to surfacing old articles, since a page can mention "2026" while
    having been published months ago. Recipes 1 and 2 are left unrestricted
    on purpose: a report can sit unindexed on a page for a long time before
    ever surfacing, and restricting those to "recent" would work against
    the whole point of catching things that were previously missed.
    """
    queries = []
    subjects = config["subjects"]
    years = config["years"]
    terminology = config["terminology"]
    orgs = config["priority_orgs"]

    # 1. Broad discovery: "UAE" "2026" ranking / index / benchmark / etc.
    for subject, year, term in itertools.product(subjects, years, terminology):
        queries.append({"query": f'"{subject}" "{year}" {term}', "is_news": False})

    # 2. Targeted org discovery: site:weforum.org UAE 2026
    for subject, year, org in itertools.product(subjects, years, orgs):
        queries.append({"query": f'site:{org["domain"]} {subject} {year}', "is_news": False})

    # 3. News-style coverage: catches "UAE climbs five places in..." articles.
    # Flagged for the recency filter — this is exactly the category prone to
    # surfacing old news, so restricting it to the past month cuts that
    # noise without touching the broader, unrestricted searches above.
    for subject, year in itertools.product(subjects, years):
        queries.append({"query": f'"{subject}" "{year}" ranking news', "is_news": True})

    # Dedup by query text while preserving order. If the same text somehow
    # appears from both a non-news and a news recipe, keep it flagged
    # is_news=True (the more restrictive/cautious choice) rather than silently
    # dropping the flag.
    seen = {}
    for item in queries:
        q = item["query"]
        if q not in seen:
            seen[q] = item
        elif item["is_news"]:
            seen[q]["is_news"] = True
    return list(seen.values())


class SerperProvider:
    """Search provider using serper.dev (Google Search API wrapper)."""

    ENDPOINT = "https://google.serper.dev/search"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, num: int = 10, recency: str = None) -> List[SearchResult]:
        headers = {"X-API-KEY": self.api_key, "Content-Type": "application/json"}
        payload = {"q": query, "num": num}
        if recency:
            payload["tbs"] = recency  # e.g. "qdr:m" = past month
        resp = requests.post(self.ENDPOINT, json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("organic", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    query=query,
                )
            )
        return results


class BingProvider:
    """Search provider using Bing Web Search API (Azure Cognitive Services)."""

    ENDPOINT = "https://api.bing.microsoft.com/v7.0/search"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, num: int = 10, recency: str = None) -> List[SearchResult]:
        headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        params = {"q": query, "count": num}
        if recency:
            params["freshness"] = recency  # e.g. "Month" — Bing's own equivalent value
        resp = requests.get(self.ENDPOINT, headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("webPages", {}).get("value", []):
            results.append(
                SearchResult(
                    title=item.get("name", ""),
                    url=item.get("url", ""),
                    snippet=item.get("snippet", ""),
                    query=query,
                )
            )
        return results


def get_provider():
    """Picks a provider based on which API key is set in the environment."""
    if os.environ.get("SERPER_API_KEY"):
        return SerperProvider(os.environ["SERPER_API_KEY"])
    if os.environ.get("BING_API_KEY"):
        return BingProvider(os.environ["BING_API_KEY"])
    raise RuntimeError(
        "No search provider API key found. Set SERPER_API_KEY (recommended, "
        "https://serper.dev) or BING_API_KEY as an environment variable / "
        "GitHub Actions secret."
    )


def run_all_searches(
    config: dict, max_queries: int = None, sleep_seconds: float = 0.3
) -> List[SearchResult]:
    """
    Runs every built query against the configured provider and returns the
    combined, raw result list (not yet deduped or classified).

    max_queries: cap for testing / cost control. None = run everything.
    sleep_seconds: small delay between calls to stay well under rate limits.
    """
    provider = get_provider()
    queries = build_queries(config)
    if max_queries:
        queries = queries[:max_queries]

    # News-style queries get restricted to the past month — see build_queries()
    # for why only this category is time-restricted. The two providers use
    # different value formats for the same concept, so pick the right one.
    if isinstance(provider, SerperProvider):
        news_recency = "qdr:m"  # Google's own "past month" syntax, passed through Serper
    elif isinstance(provider, BingProvider):
        news_recency = "Month"
    else:
        news_recency = None

    all_results: List[SearchResult] = []
    for i, item in enumerate(queries):
        q = item["query"]
        recency = news_recency if item["is_news"] else None
        try:
            results = provider.search(q, recency=recency)
            all_results.extend(results)
        except Exception as e:
            print(f"[search] query failed: {q!r} — {e}")
        time.sleep(sleep_seconds)
        if (i + 1) % 20 == 0:
            print(f"[search] {i + 1}/{len(queries)} queries done, "
                  f"{len(all_results)} results so far")

    return all_results
