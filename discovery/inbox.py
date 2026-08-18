"""
inbox.py — reads and writes the Discovery Inbox CSV.

Columns match the format from the original project brief:
Date Found | Report | Organisation | UAE Mention | Type | Year | Source |
Priority | Already Tracked | Status

Status starts as "Review" for every new row. You (Nish) update it manually
to "Add to Report Hunt" or "Ignore" as you triage — the pipeline never
overwrites a Status you've already set.
"""

import csv
import os
from datetime import date
from typing import List, Dict, Set

INBOX_PATH = "data/discovery_inbox.csv"

FIELDNAMES = [
    "Date Found",
    "Report",
    "Organisation",
    "UAE Mention",
    "Type",
    "Year",
    "Source",
    "Priority",
    "Already Tracked",
    "Status",
]


def ensure_inbox_exists(path: str = INBOX_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def load_existing_urls(path: str = INBOX_PATH) -> Set[str]:
    """Returns the set of normalized 'Source' URLs already in the inbox."""
    from discovery.dedupe import normalize_url

    ensure_inbox_exists(path)
    urls = set()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Source"):
                urls.add(normalize_url(row["Source"]))
    return urls


def append_rows(rows: List[Dict], path: str = INBOX_PATH):
    ensure_inbox_exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        for row in rows:
            writer.writerow(row)


def build_row(item: Dict, already_tracked: bool) -> Dict:
    return {
        "Date Found": date.today().isoformat(),
        "Report": item.get("report_name") or item.get("title"),
        "Organisation": item.get("organisation") or "",
        "UAE Mention": item.get("uae_mention") or "",
        "Type": item.get("report_type") or "",
        "Year": item.get("year") or "",
        "Source": item.get("url"),
        "Priority": item.get("priority_label", "🟡 Low"),
        "Already Tracked": "Yes" if already_tracked else "No",
        "Status": "🟡 Review",
    }


def read_all_rows(path: str = INBOX_PATH) -> List[Dict]:
    ensure_inbox_exists(path)
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
