"""
main.py — orchestrates the full pipeline:

  1. Build & run search queries
  2. Dedupe within this run's results
  3. Filter out results already in the inbox from previous runs
  4. Classify remaining results with Claude (relevance + priority)
  5. Drop "ignore" tier (configurable) and write new rows to the inbox CSV
  6. Build a digest and save it (GitHub Action posts it as an Issue)

Usage:
    python -m discovery.main                  # full run
    python -m discovery.main --max-queries 20  # cheaper test run
    python -m discovery.main --keep-ignored    # also log ⚪ Ignore rows
"""

import argparse
import sys

import yaml

from discovery.search import run_all_searches
from discovery.dedupe import dedupe_results, filter_against_existing, matches_already_tracked
from discovery.classify import classify_all
from discovery.inbox import load_existing_urls, append_rows, build_row
from discovery.digest import build_digest, save_digest


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="UAE Report Discovery pipeline")
    parser.add_argument("--max-queries", type=int, default=None,
                         help="Cap number of search queries run (cost control / testing)")
    parser.add_argument("--keep-ignored", action="store_true",
                         help="Also write ⚪ Ignore rows to the inbox instead of dropping them")
    args = parser.parse_args()

    config = load_config()

    print("[main] running searches...")
    raw_results = run_all_searches(config, max_queries=args.max_queries)
    print(f"[main] {len(raw_results)} raw results from search")

    print("[main] deduping within this run...")
    deduped = dedupe_results(raw_results)
    print(f"[main] {len(deduped)} unique results")

    print("[main] filtering against existing inbox...")
    existing_urls = load_existing_urls()
    new_results = filter_against_existing(deduped, existing_urls)
    print(f"[main] {len(new_results)} genuinely new results to classify")

    if not new_results:
        print("[main] nothing new — writing empty digest and exiting")
        digest_text = build_digest([])
        save_digest(digest_text)
        print(digest_text)
        return

    print("[main] classifying with Claude...")
    result_dicts = [r.to_dict() for r in new_results]
    classified = classify_all(result_dicts, config["relevance_vocabulary"])

    if not args.keep_ignored:
        before = len(classified)
        classified = [c for c in classified if c["priority"] != "ignore"]
        print(f"[main] dropped {before - len(classified)} ⚪ ignore results")

    already_tracked_list = config.get("already_tracked", [])
    rows = []
    for item in classified:
        tracked = matches_already_tracked(item.get("report_name") or item["title"], already_tracked_list)
        rows.append(build_row(item, already_tracked=tracked))

    print(f"[main] writing {len(rows)} new rows to inbox")
    append_rows(rows)

    digest_text = build_digest(rows)
    save_digest(digest_text)
    print(digest_text)


if __name__ == "__main__":
    sys.exit(main())
