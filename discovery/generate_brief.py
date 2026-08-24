"""
generate_brief.py — given a report name and its official source URL, fetches
the page, has Claude draft structured brief content (identification, UAE
ranking, benchmark comparison, methodology, summary), and writes that
content as JSON for build_pptx.js to turn into an actual .pptx.

Usage:
    python -m discovery.generate_brief --report-name "Henley Passport Index" \
        --source-url "https://www.henleyglobal.com/passport-index/ranking" \
        --output brief_content.json
"""

import argparse
import json
import os
import sys

import anthropic
import requests

MODEL = "claude-sonnet-4-6"

DRAFT_SYSTEM_PROMPT = """You are drafting a short executive brief for the UAE's \
Federal Competitiveness and Statistics Centre (FCSC), based on the actual \
content of a report's official page (provided below). Extract only what is \
genuinely present in the page content — never invent a ranking, score, \
methodology detail, or comparison figure that isn't actually stated.

FCSC's standard benchmark groups are:
  G7: Canada, France, Germany, Italy, Japan, United Kingdom, United States
  G20: the G7 above, plus Argentina, Australia, Brazil, China, India, \
Indonesia, Mexico, Russia, Saudi Arabia, South Africa, South Korea, Turkey, \
and the European Union
  BRICS: Brazil, Russia, India, China, South Africa, and (since the 2024 \
expansion) Egypt, Ethiopia, Iran, and the United Arab Emirates — note the \
UAE is itself now a BRICS member, so BRICS comparisons should note this \
rather than list UAE as an external peer

For each group, check the page content for any of that group's member \
countries and their rank/score. Only include a country if it is explicitly \
named with a rank or score in the page content — never estimate or infer a \
country's figure. For each group where at least one member's figure is \
found, compute a simple average of the figures found IF they are the same \
type of number (e.g. all ranks, or all scores on the same scale) — and \
ALWAYS state exactly how many of the group's members that average is based \
on (e.g. "average of 3 of 7 G7 members shown on this page"). If fewer than \
half a group's members are found, still report the individual figures found \
but do not compute an average for that group — label it as insufficient \
data instead. If zero members of a group are found, omit that group \
entirely rather than including it empty.

Produce a JSON object with this exact shape:

{
  "report_name": "clean official name of the report/index",
  "organisation": "publishing organisation",
  "edition_year": "the report edition/year, if stated",
  "uae_headline": "one sentence: UAE's specific rank/score, as stated on the page",
  "benchmark_groups": [
    {
      "group": "G7" | "G20" | "BRICS",
      "members_found": [
        {"country": "name", "value": "rank or score as stated"}
      ],
      "average": "computed average as a string, or null if not computed",
      "coverage_note": "e.g. 'Average of 3 of 7 G7 members shown on this page' \
or 'Insufficient data for a group average — individual figures shown' or \
'UAE is itself a BRICS member as of 2024'"
    }
    // include only groups where at least one member was found
  ],
  "methodology_summary": "2-4 sentences on how the index/ranking is built, \
ONLY if the page actually describes this. If not described on the page, \
use exactly: 'Methodology not detailed on the source page.'",
  "key_findings": [
    "2-4 short bullet-style findings actually stated on the page, beyond the \
UAE headline — global trends, notable movers, etc."
  ],
  "summary": "one paragraph (3-5 sentences) summarizing the report and its \
relevance to UAE competitiveness, in a neutral analytical tone."
}

Respond with ONLY the JSON object, no other text, no markdown fences.
"""


def fetch_page_text(url: str, max_chars: int = 15000) -> str:
    """Fetches a URL and returns a crude text extraction (strips HTML tags).
    Not a full readability parser — good enough to hand to Claude, which is
    tolerant of messy input, without pulling in a heavy dependency."""
    resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    html = resp.text

    # Crude tag stripping: good enough for feeding to Claude, not for display
    import re
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def draft_brief_content(report_name: str, source_url: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")
    client = anthropic.Anthropic(api_key=api_key)

    print(f"[generate_brief] fetching {source_url}")
    page_text = fetch_page_text(source_url)
    print(f"[generate_brief] fetched {len(page_text)} chars of page text")

    user_prompt = (
        f"REPORT NAME (as known): {report_name}\n"
        f"SOURCE URL: {source_url}\n\n"
        f"PAGE CONTENT:\n{page_text}"
    )

    print("[generate_brief] drafting brief content with Claude...")
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=DRAFT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json\n", "", 1) if text.startswith("json\n") else text

    try:
        content = json.loads(text)
    except json.JSONDecodeError as e:
        print("[generate_brief] failed to parse Claude's response as JSON:")
        print(text[:1000])
        raise RuntimeError(f"Could not parse brief content: {e}")

    return content


def main():
    parser = argparse.ArgumentParser(description="Draft brief content for a report")
    parser.add_argument("--report-name", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--output", default="brief_content.json")
    args = parser.parse_args()

    content = draft_brief_content(args.report_name, args.source_url)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=2)

    print(f"[generate_brief] wrote content to {args.output}")


if __name__ == "__main__":
    sys.exit(main())
