"""
generate_brief.py — given a report name and its official source URL, uses
Claude's own web_fetch and web_search tools (server-side, executed by
Anthropic) to actually read the report's page — and follow links to a
methodology page or PDF if one exists — then draft structured brief
content. Writes that content as JSON for build_pptx.js to turn into an
actual .pptx.

This replaced an earlier version that did a single manual requests.get()
call with crude regex tag-stripping. That approach couldn't follow links,
couldn't verify anything, and returned an empty/wrong page for any site
that loads its real data via JavaScript after the initial page load. Using
Claude's own tools here means Claude does the actual navigating — reading
the page, deciding whether to fetch a linked methodology page, and only
falling back to a web search if something genuinely needs verifying —
much closer to how a person (or Claude in a normal chat) would work
through the same page by hand.

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

MODEL = "claude-sonnet-4-6"
WEB_FETCH_BETA_HEADER = "web-fetch-2025-09-10"

DRAFT_SYSTEM_PROMPT = """You are drafting a short executive brief for the UAE's \
Federal Competitiveness and Statistics Centre (FCSC). You have web_fetch and \
web_search tools available — use them to actually read the report's real \
page content before writing anything. Extract only what is genuinely \
present in what you fetch — never invent a ranking, score, methodology \
detail, or comparison figure that isn't actually stated somewhere you \
fetched.

How to use your tools on this task:
  1. Start by fetching the SOURCE URL you're given — that's the report's \
official page.
  2. If that page references a separate methodology page, a full report \
PDF, or a detailed data page on the SAME site, fetch that too if it looks \
like it would meaningfully improve the brief (e.g. it has the actual \
ranking table or methodology explanation the summary page lacks).
  3. Only use web_search if something specific genuinely needs verifying \
and isn't resolved by what you've already fetched — do not use it to go \
looking for unrelated sources. Stay focused on this one report.
  4. Do not fetch or cite anything outside the report's own official \
domain family — no news articles, no social media, for this task.

FCSC's standard benchmark groups are:
  G7: Canada, France, Germany, Italy, Japan, United Kingdom, United States
  G20: the G7 above, plus Argentina, Australia, Brazil, China, India, \
Indonesia, Mexico, Russia, Saudi Arabia, South Africa, South Korea, Turkey, \
and the European Union
  BRICS: Brazil, Russia, India, China, South Africa, and (since the 2024 \
expansion) Egypt, Ethiopia, Iran, and the United Arab Emirates — note the \
UAE is itself now a BRICS member, so BRICS comparisons should note this \
rather than list UAE as an external peer

For each group, check what you fetched for any of that group's member \
countries and their rank/score. Only include a country if it is explicitly \
named with a rank or score in what you fetched — never estimate or infer a \
country's figure. For each group where at least one member's figure is \
found, compute a simple average of the figures found IF they are the same \
type of number (e.g. all ranks, or all scores on the same scale) — and \
ALWAYS state exactly how many of the group's members that average is based \
on (e.g. "average of 3 of 7 G7 members shown on this page"). If fewer than \
half a group's members are found, still report the individual figures found \
but do not compute an average for that group — label it as insufficient \
data instead. If zero members of a group are found, omit that group \
entirely rather than including it empty.

Once you've fetched what you need, respond with ONLY a JSON object (no \
other text, no markdown fences) with this exact shape:

{
  "report_name": "clean official name of the report/index",
  "organisation": "publishing organisation",
  "edition_year": "the report edition/year, if stated",
  "uae_headline": "one sentence: UAE's specific rank/score, as stated in what you fetched",
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
  ],
  "methodology_summary": "2-4 sentences on how the index/ranking is built, \
ONLY if a page you fetched actually describes this. If not described \
anywhere you fetched, use exactly: 'Methodology not detailed on the source page.'",
  "key_findings": [
    "2-4 short bullet-style findings actually stated in what you fetched, \
beyond the UAE headline — global trends, notable movers, etc."
  ],
  "summary": "one paragraph (3-5 sentences) summarizing the report and its \
relevance to UAE competitiveness, in a neutral analytical tone.",
  "sources_used": ["list of the actual URLs you fetched, for reference"]
}
"""


def draft_brief_content(report_name: str, source_url: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")
    client = anthropic.Anthropic(api_key=api_key)

    user_prompt = (
        f"REPORT NAME (as known): {report_name}\n"
        f"SOURCE URL (fetch this first): {source_url}\n\n"
        f"Fetch this page, follow up on a methodology/data page on the same "
        f"site if it would genuinely help, then draft the brief content as "
        f"specified."
    )

    messages = [{"role": "user", "content": user_prompt}]
    tools = [
        {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 5},
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 2},
    ]

    print(f"[generate_brief] asking Claude to fetch and analyze {source_url}")

    final_text = None
    # Server-executed tool tasks can occasionally pause and need a follow-up
    # turn to continue — loop a few times in case that happens, rather than
    # assuming one call always finishes the job.
    for turn in range(4):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=DRAFT_SYSTEM_PROMPT,
            messages=messages,
            tools=tools,
            extra_headers={"anthropic-beta": WEB_FETCH_BETA_HEADER},
        )

        text_blocks = [block.text for block in response.content if block.type == "text"]
        if text_blocks:
            final_text = "".join(text_blocks).strip()

        fetch_count = sum(1 for b in response.content if getattr(b, "type", "") == "server_tool_use")
        print(f"[generate_brief] turn {turn + 1}: stop_reason={response.stop_reason}, "
              f"{fetch_count} tool call(s) this turn")

        if response.stop_reason != "pause_turn":
            break

        # Continue the conversation so Claude can finish its work
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": "Please continue."})

    if not final_text:
        raise RuntimeError("Claude did not return any text content after fetching.")

    text = final_text
    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json\n", "", 1) if text.startswith("json\n") else text

    try:
        content = json.loads(text)
    except json.JSONDecodeError as e:
        print("[generate_brief] failed to parse Claude's response as JSON:")
        print(text[:1500])
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
