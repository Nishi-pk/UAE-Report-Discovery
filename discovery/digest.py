"""
digest.py — builds a short Markdown digest of the day's new discoveries,
grouped by priority, in the style from the original brief:

  🔎 UAE REPORT DISCOVERY — 18 AUGUST 2026
  5 new potentially relevant reports found
  🔴 1 High Priority
  ...

Delivery: the GitHub Action posts this as a new GitHub Issue, which
notifies you (Nish) the same way any GitHub notification would — no SMTP
setup required. If you'd rather get it by email, see the README for a
Power Automate / SMTP variant.
"""

from datetime import date
from typing import List, Dict


GITHUB_ISSUE_CHAR_LIMIT = 65536
SAFE_CHAR_BUDGET = 60000  # leave headroom below the hard limit


def build_digest(new_rows: List[Dict], max_low_shown: int = 15) -> str:
    """
    Builds the digest, keeping it well under GitHub's issue body size limit.

    GitHub Issues cap out at ~65,536 characters. A large first run (or a
    noisy day) can easily produce a digest longer than that, so:
      - 🔴 High and 🟠 Medium are always shown in full (these are the ones
        that matter most and there are usually few of them).
      - 🟡 Low is capped at `max_low_shown` entries, with a note pointing to
        the full CSV for the rest — low-priority items rarely need a
        same-day read anyway.
      - As a final safety net, if the digest is still too long (e.g. an
        unusually large 🔴/🟠 batch), it gets hard-truncated with a clear
        note, so the Issue post never fails outright.
    """
    today_str = date.today().strftime("%d %B %Y").upper()

    high = [r for r in new_rows if r["Priority"].startswith("🔴")]
    medium = [r for r in new_rows if r["Priority"].startswith("🟠")]
    low = [r for r in new_rows if r["Priority"].startswith("🟡")]
    unclassified = [r for r in new_rows if r["Priority"].startswith("⚠️")]

    count_line = f"**{len(new_rows)} new potentially relevant reports found**"
    if unclassified:
        # A --skip-classify run: nothing has priority labels, say so plainly
        # rather than showing a misleading "0 high / 0 medium / 0 low".
        count_line += f" ({len(unclassified)} unclassified — run without --skip-classify to prioritize)"
    else:
        count_line += f" ({len(high)} high / {len(medium)} medium / {len(low)} low priority)"

    lines = [
        f"# 🔎 UAE Report Discovery — {today_str}",
        "",
        count_line,
        "",
        "_Full list, including every 🟡 Low item, is always in "
        "`data/discovery_inbox.csv`._",
        "",
    ]

    def section(title: str, rows: List[Dict]):
        if not rows:
            return []
        out = [f"## {title}", ""]
        for r in rows:
            out.append(f"**{r['Report']}**")
            details = []
            if r.get("Organisation"):
                details.append(r["Organisation"])
            if r.get("UAE Mention"):
                details.append(r["UAE Mention"])
            if r.get("Year"):
                details.append(str(r["Year"]))
            if details:
                out.append(" · ".join(details))
            if r.get("Already Tracked") == "Yes":
                out.append("_Already tracked in Report Hunt_")
            out.append(f"[Source]({r['Source']})")
            out.append("")
        return out

    lines += section("🔴 High Priority", high)
    lines += section("🟠 Medium Priority", medium)

    # Low priority: capped, with an overflow note rather than every entry
    low_shown = low[:max_low_shown]
    low_remaining = len(low) - len(low_shown)
    lines += section("🟡 Low Priority" if not low_remaining
                      else f"🟡 Low Priority (showing {len(low_shown)} of {len(low)})",
                      low_shown)
    if low_remaining > 0:
        lines.append(f"_...and {low_remaining} more 🟡 Low items — see the CSV for the full list._")
        lines.append("")

    # Unclassified: capped the same way as Low, since there can be hundreds
    unclass_shown = unclassified[:max_low_shown]
    unclass_remaining = len(unclassified) - len(unclass_shown)
    lines += section(
        "⚠️ Unclassified (found, not yet scored)" if not unclass_remaining
        else f"⚠️ Unclassified (showing {len(unclass_shown)} of {len(unclassified)})",
        unclass_shown,
    )
    if unclass_remaining > 0:
        lines.append(f"_...and {unclass_remaining} more unclassified items — see the CSV._")
        lines.append("")

    if not new_rows:
        lines.append("_No new reports found today._")

    lines.append("")
    lines.append("---")
    lines.append(
        "Review the full inbox in `data/discovery_inbox.csv` and update the "
        "**Status** column to `Add to Report Hunt` or `Ignore` for each row."
    )

    digest = "\n".join(lines)

    # Final safety net: if 🔴/🟠 alone somehow still exceed the limit
    # (a genuinely unusual day), hard-truncate rather than let the Issue
    # post fail outright.
    if len(digest) > SAFE_CHAR_BUDGET:
        digest = (
            digest[:SAFE_CHAR_BUDGET]
            + "\n\n---\n_⚠️ Digest truncated — too many results to fit in one "
            "GitHub Issue today. Full list is in `data/discovery_inbox.csv`._"
        )

    return digest


def save_digest(text: str, path: str = "data/latest_digest.md"):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
