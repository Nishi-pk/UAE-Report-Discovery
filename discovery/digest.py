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


def build_digest(new_rows: List[Dict]) -> str:
    today_str = date.today().strftime("%d %B %Y").upper()

    high = [r for r in new_rows if r["Priority"].startswith("🔴")]
    medium = [r for r in new_rows if r["Priority"].startswith("🟠")]
    low = [r for r in new_rows if r["Priority"].startswith("🟡")]

    lines = [
        f"# 🔎 UAE Report Discovery — {today_str}",
        "",
        f"**{len(new_rows)} new potentially relevant reports found** "
        f"({len(high)} high / {len(medium)} medium / {len(low)} low priority)",
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
    lines += section("🟡 Low Priority", low)

    if not new_rows:
        lines.append("_No new reports found today._")

    lines.append("")
    lines.append("---")
    lines.append(
        "Review the full inbox in `data/discovery_inbox.csv` and update the "
        "**Status** column to `Add to Report Hunt` or `Ignore` for each row."
    )

    return "\n".join(lines)


def save_digest(text: str, path: str = "data/latest_digest.md"):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
