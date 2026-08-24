"""
classify.py — uses the Anthropic API to score each search result for
relevance and assign a priority tier, following the rubric from the
original project brief:

  🔴 High priority   — UAE has an explicit rank/score (e.g. "UAE ranked 24/140")
  🟠 Medium priority  — UAE is explicitly included and benchmarked against others
  🟡 Low priority     — UAE is mentioned but there's no meaningful ranking/score
  ⚪ Ignore           — No meaningful UAE/competitiveness relevance

Batches results to keep API calls efficient (default: 10 per call).
"""

import os
import json
import time
from typing import List, Dict, Any

import anthropic

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT_TEMPLATE = """You are a research triage assistant for the UAE's \
Federal Competitiveness and Statistics Centre (FCSC). Your job is to review \
raw web search results and decide which ones are genuinely new, relevant \
global reports, indices, rankings, or benchmarks that mention the UAE, \
Dubai, or Abu Dhabi.

FCSC cares about topics including (but not limited to): {vocabulary}

Score each result using this exact rubric:

- "high": The result clearly shows the UAE (or Dubai/Abu Dhabi) has an \
explicit rank or numeric score in a global index/ranking/report \
(e.g. "UAE ranked 24th of 140 countries").
- "medium": The UAE is explicitly included and compared/benchmarked against \
other countries, but no single clean rank/score is visible in the snippet.
- "low": The UAE/Dubai/Abu Dhabi is mentioned, but there's no indication of \
a meaningful ranking, score, or benchmarking exercise (e.g. a general news \
mention).
- "ignore": No meaningful connection to UAE competitiveness — irrelevant \
domain (e.g. real estate listings, sports rankings, unrelated local news), \
duplicate/old report, or not actually about a report/index/ranking at all.

For each result also extract, if visible from the title/snippet:
  - report_name: best-guess clean name of the report/index (not the article title)
  - organisation: publishing organisation, if identifiable
  - uae_mention: short phrase describing UAE's mention (e.g. "UAE #31/140", \
"UAE included, no score visible", "UAE mentioned only")
  - report_type: one of "Index", "Ranking", "Report", "Survey", "Benchmark", \
"Other"
  - year: the edition/reference year the report itself covers, if identifiable, \
else null (this may differ from any year mentioned only because of when an \
article about it was published)
  - publication_date: the publication date of the SPECIFIC PAGE this result's \
URL points to — not the report's edition year. Two cases:
      1. If the URL is the report's own official page (the publishing \
         organisation's own site, e.g. weforum.org, imd.org, worldbank.org), \
         give that report's own stated publish/release date.
      2. If the URL is a secondary source about the report — a news article, \
         or a Facebook/Instagram/LinkedIn/X post — give the date THAT \
         article or post was published/posted, not the underlying report's \
         date (which may be different and isn't what this field is for).
    Give the most precise value available: a full date if stated (e.g. \
"2026-03-14"), otherwise month + year (e.g. "March 2026"), otherwise just \
the year, otherwise null if genuinely undeterminable from the snippet. \
Never guess a date not implied by the text.
  - source_type: "Official" if the URL is the report's own publisher's page \
(the organisation's own domain, e.g. weforum.org for a WEF report, imd.org \
for an IMD report) — "Secondary" if it's a news article, or a social post on \
Facebook, Instagram, LinkedIn, X/Twitter, TikTok, or YouTube reporting ON the \
report rather than being the report's own page.
  - category: classify the report into EXACTLY ONE of these 8 categories, \
choosing the single best fit even if the report could arguably touch more \
than one:
      "Political Representation" — governance, elections, government \
      effectiveness, public trust in government, rule of law, political \
      participation
      "Economic and Workforce" — GDP, growth, competitiveness, labor market, \
      employment, entrepreneurship, trade, investment climate
      "Legal Rights and Freedom" — civil liberties, press freedom, judicial \
      systems, corruption, human rights
      "Financial and Business Rights" — banking, credit ratings, financial \
      centres, business regulation, property/ownership rights
      "Family, Maternity and Pension" — family policy, maternity/parental \
      leave, gender balance, retirement/pension systems, social protection
      "Education" — schools, universities, rankings, skills, literacy
      "Health" — healthcare systems, public health, wellbeing, life expectancy
      "Technology" — AI, digital transformation, innovation, R&D, smart cities, \
      telecom, cybersecurity
      If truly none fit, use "Other".

Respond with ONLY a JSON array, one object per input result, in the same \
order as given, with this exact shape and no other text:

[
  {{
    "index": 0,
    "priority": "high" | "medium" | "low" | "ignore",
    "report_name": "string or null",
    "organisation": "string or null",
    "uae_mention": "string or null",
    "report_type": "string or null",
    "year": "string or null",
    "publication_date": "string or null",
    "source_type": "Official" or "Secondary",
    "category": "one of the 8 categories above, or 'Other'",
    "reasoning": "one short sentence"
  }}
]
"""

PRIORITY_EMOJI = {
    "high": "🔴 High",
    "medium": "🟠 Medium",
    "low": "🟡 Low",
    "ignore": "⚪ Ignore",
}


def _client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")
    return anthropic.Anthropic(api_key=api_key)


def _build_batch_prompt(results_batch: List[Dict[str, Any]]) -> str:
    lines = []
    for i, r in enumerate(results_batch):
        lines.append(
            f'{i}. TITLE: {r["title"]}\n   URL: {r["url"]}\n   SNIPPET: {r["snippet"]}'
        )
    return "Classify these search results:\n\n" + "\n\n".join(lines)


def classify_batch(
    results_batch: List[Dict[str, Any]], vocabulary: List[str], client: anthropic.Anthropic
) -> List[Dict[str, Any]]:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(vocabulary=", ".join(vocabulary))
    user_prompt = _build_batch_prompt(results_batch)

    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = "".join(block.text for block in response.content if block.type == "text")
    text = text.strip()
    # Strip accidental markdown fences
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json\n", "", 1) if text.startswith("json\n") else text

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        print("[classify] failed to parse model output, skipping batch:")
        print(text[:500])
        return []

    return parsed


def classify_all(
    results: List[Dict[str, Any]],
    vocabulary: List[str],
    batch_size: int = 10,
    sleep_seconds: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    Classifies a full list of search results (as dicts, e.g. from
    SearchResult.to_dict()). Returns the same results enriched with
    classification fields, with 'ignore' items still included so callers
    can decide whether to filter them.
    """
    client = _client()
    enriched: List[Dict[str, Any]] = []

    for start in range(0, len(results), batch_size):
        batch = results[start : start + batch_size]
        classifications = classify_batch(batch, vocabulary, client)

        class_by_index = {c["index"]: c for c in classifications}
        for i, r in enumerate(batch):
            c = class_by_index.get(i)
            merged = dict(r)
            if c:
                merged["priority"] = c.get("priority", "low")
                merged["priority_label"] = PRIORITY_EMOJI.get(c.get("priority", "low"), "🟡 Low")
                merged["report_name"] = c.get("report_name") or r["title"]
                merged["organisation"] = c.get("organisation")
                merged["uae_mention"] = c.get("uae_mention")
                merged["report_type"] = c.get("report_type")
                merged["year"] = c.get("year")
                merged["publication_date"] = c.get("publication_date")
                merged["source_type"] = c.get("source_type") or "Secondary"
                merged["category"] = c.get("category") or "Other"
                merged["reasoning"] = c.get("reasoning")
            else:
                # classification failed for this item — default to low priority
                # for manual review rather than silently dropping it
                merged["priority"] = "low"
                merged["priority_label"] = "🟡 Low"
                merged["report_name"] = r["title"]
                merged["organisation"] = None
                merged["uae_mention"] = None
                merged["report_type"] = None
                merged["year"] = None
                merged["publication_date"] = None
                merged["source_type"] = "Secondary"  # default to the safer assumption on failure
                merged["category"] = "Other"
                merged["reasoning"] = "Classification failed; needs manual review."
            enriched.append(merged)

        print(f"[classify] {min(start + batch_size, len(results))}/{len(results)} done")
        time.sleep(sleep_seconds)

    return enriched


BACKFILL_SYSTEM_PROMPT = """You are helping categorize already-reviewed reports \
for the UAE's Federal Competitiveness and Statistics Centre (FCSC). Each item \
below already has a report name, organisation, and a short description of how \
the UAE is mentioned — your only job is to assign a category and, if possible, \
a publication date.

Classify each item into EXACTLY ONE of these 8 categories:
  "Political Representation" — governance, elections, government effectiveness,
  public trust in government, rule of law, political participation
  "Economic and Workforce" — GDP, growth, competitiveness, labor market,
  employment, entrepreneurship, trade, investment climate
  "Legal Rights and Freedom" — civil liberties, press freedom, judicial
  systems, corruption, human rights
  "Financial and Business Rights" — banking, credit ratings, financial
  centres, business regulation, property/ownership rights
  "Family, Maternity and Pension" — family policy, maternity/parental leave,
  gender balance, retirement/pension systems, social protection
  "Education" — schools, universities, rankings, skills, literacy
  "Health" — healthcare systems, public health, wellbeing, life expectancy
  "Technology" — AI, digital transformation, innovation, R&D, smart cities,
  telecom, cybersecurity
  If truly none fit, use "Other".

Also provide publication_date: the most precise date you can determine from
the report name / organisation / UAE mention / year given — a full date if
somehow implied, otherwise month+year, otherwise just the year, otherwise
null if genuinely undeterminable. Never guess a date not implied by the input.

Also provide source_type: "Official" if the SOURCE URL's domain is the
publishing organisation's own site (e.g. weforum.org for a WEF report), or
"Secondary" if the URL is a news site, or Facebook/Instagram/LinkedIn/X/
TikTok/YouTube — anything reporting ON the report rather than being the
report's own page. Compare the URL's domain against the given ORGANISATION
name to judge this.

Respond with ONLY a JSON array, one object per input item, in the same order
given, with this exact shape and no other text:

[
  {"index": 0, "category": "one of the 8 categories above, or 'Other'", "publication_date": "string or null", "source_type": "Official" or "Secondary"}
]
"""


def _build_backfill_prompt(items_batch: List[Dict[str, Any]]) -> str:
    lines = []
    for i, r in enumerate(items_batch):
        lines.append(
            f'{i}. REPORT: {r.get("Report", "")}\n'
            f'   ORGANISATION: {r.get("Organisation", "")}\n'
            f'   UAE MENTION: {r.get("UAE Mention", "")}\n'
            f'   YEAR: {r.get("Year", "")}\n'
            f'   SOURCE: {r.get("Source", "")}'
        )
    return "Categorize these already-reviewed items:\n\n" + "\n\n".join(lines)


def backfill_batch(items_batch: List[Dict[str, Any]], client: anthropic.Anthropic) -> List[Dict[str, Any]]:
    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=BACKFILL_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_backfill_prompt(items_batch)}],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json\n", "", 1) if text.startswith("json\n") else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print("[backfill] failed to parse model output, skipping batch:")
        print(text[:500])
        return []


def backfill_all(rows: List[Dict[str, Any]], batch_size: int = 10, sleep_seconds: float = 0.5) -> int:
    """
    Fills in Category and Publication Date for rows that are missing them,
    modifying `rows` in place. Returns the count of rows successfully updated.
    Rows that already have a Category are left untouched and not re-billed.
    """
    client = _client()
    to_process = [(i, r) for i, r in enumerate(rows) if not r.get("Category") or not r.get("Source Type")]
    print(f"[backfill] {len(to_process)} rows need backfilling (out of {len(rows)} total)")

    updated_count = 0
    for start in range(0, len(to_process), batch_size):
        batch = to_process[start:start + batch_size]
        batch_items = [r for _, r in batch]
        results = backfill_batch(batch_items, client)
        result_by_index = {r["index"]: r for r in results}

        for local_i, (global_i, row) in enumerate(batch):
            result = result_by_index.get(local_i)
            if result:
                rows[global_i]["Category"] = result.get("category") or "Other"
                rows[global_i]["Publication Date"] = result.get("publication_date") or ""
                rows[global_i]["Source Type"] = result.get("source_type") or "Secondary"
                updated_count += 1
            else:
                rows[global_i]["Category"] = "Other"  # mark as attempted, avoid infinite re-tries
                rows[global_i]["Source Type"] = "Secondary"

        print(f"[backfill] {min(start + batch_size, len(to_process))}/{len(to_process)} done")
        time.sleep(sleep_seconds)

    return updated_count
