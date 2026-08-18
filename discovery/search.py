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


def build_queries(config: dict) -> List[str]:
    """
    Builds the full list of search queries from config.yaml:
      1. subject x year x terminology combos   (broad discovery)
      2. subject x year x priority_org site: searches (targeted discovery)
      3. subject x year "news" style combos     (catches news coverage
         of reports that aren't well indexed on the org's own site)
    """
    queries = []
    subjects = config["subjects"]
    years = config["years"]
    terminology = config["terminology"]
    orgs = config["priority_orgs"]

    # 1. Broad discovery: "UAE" "2026" ranking / index / benchmark / etc.
    for subject, year, term in itertools.product(subjects, years, terminology):
        queries.append(f'"{subject}" "{year}" {term}')

    # 2. Targeted org discovery: site:weforum.org UAE 2026
    for subject, year, org in itertools.product(subjects, years, orgs):
        queries.append(f'site:{org["domain"]} {subject} {year}')

    # 3. News-style coverage: catches "UAE climbs five places in..." articles
    for subject, year in itertools.product(subjects, years):
        queries.append(f'"{subject}" "{year}" ranking news')

    # Dedup while preserving order
    seen = set()
    unique_queries = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique_queries.append(q)
    return unique_queries


class SerperProvider:
    """Search provider using serper.dev (Google Search API wrapper)."""

    ENDPOINT = "https://google.serper.dev/search"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, num: int = 10) -> List[SearchResult]:
        headers = {"X-API-KEY": self.api_key, "Content-Type": "application/json"}
        payload = {"q": query, "num": num}
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

    def search(self, query: str, num: int = 10) -> List[SearchResult]:
        headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        params = {"q": query, "count": num}
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

    all_results: List[SearchResult] = []
    for i, q in enumerate(queries):
        try:
            results = provider.search(q)
            all_results.extend(results)
        except Exception as e:
            print(f"[search] query failed: {q!r} — {e}")
        time.sleep(sleep_seconds)
        if (i + 1) % 20 == 0:
            print(f"[search] {i + 1}/{len(queries)} queries done, "
                  f"{len(all_results)} results so far")

    return all_results
