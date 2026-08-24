"""
backfill.py — one-time (or occasional) utility to fill in Category and
Publication Date for rows already in discovery_inbox.csv that predate
those columns existing.

Unlike main.py, this does NOT search the web or re-score Priority — it
only asks Claude to categorize + date rows that already have a Report
name, Organisation, and UAE Mention filled in from a previous run.

Usage:
    python -m discovery.backfill
"""

import csv
import sys

from discovery.inbox import INBOX_PATH, FIELDNAMES
from discovery.classify import backfill_all


def main():
    with open(INBOX_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    before_missing = sum(1 for r in rows if not r.get("Category"))
    print(f"[backfill] loaded {len(rows)} rows, {before_missing} missing Category")

    if before_missing == 0:
        print("[backfill] nothing to do — every row already has a Category.")
        return

    updated = backfill_all(rows)

    with open(INBOX_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[backfill] done — updated {updated} rows, saved to {INBOX_PATH}")


if __name__ == "__main__":
    sys.exit(main())
