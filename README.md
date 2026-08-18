# UAE Report Discovery

Finds new global reports, indices, rankings, and benchmarks that mention the
UAE, Dubai, or Abu Dhabi — before they land on your desk secondhand.

This is "Project 2" from the original brief: it doesn't track reports you
already know about (that's a separate Report Hunt system). It answers a
different question — **"what might we not know about yet?"** — and feeds
candidates into your Report Hunt once you've reviewed them.

## How it works

```
search.py      → builds ~240 targeted queries from config.yaml and runs
                  them against a search API (broad terms + org site:
                  searches + news-style searches)
dedupe.py       → collapses duplicate hits (same report, multiple URLs)
                  and drops anything already in the inbox from a past run
classify.py     → sends new results to Claude, which scores each one
                  🔴 High / 🟠 Medium / 🟡 Low / ⚪ Ignore and extracts the
                  report name, organisation, UAE mention, type, and year
inbox.py        → appends new rows to data/discovery_inbox.csv
digest.py       → builds a short Markdown summary of the day's findings
main.py         → runs all of the above in sequence
```

Runs daily via GitHub Actions, commits the updated CSV back to the repo,
and opens a GitHub Issue with the digest (so you get a notification without
needing to set up email/SMTP).

## One-time setup

**1. Get a search API key** (pick one — Serper is simpler and cheaper for this volume):
- [serper.dev](https://serper.dev) — free tier, then ~$50/50,000 queries. At
  ~240 queries/day this is roughly 7,000/month, comfortably inside the free
  or lowest paid tier.
- Or [Bing Web Search API](https://www.microsoft.com/en-us/bing/apis/bing-web-search-api)
  via Azure, if you'd rather use an existing Microsoft/Azure account.

**2. Get an Anthropic API key** (for classification) — from
[console.anthropic.com](https://console.anthropic.com).

**3. Push this project to a GitHub repo**, then add both keys as repo secrets:
`Settings → Secrets and variables → Actions → New repository secret`
- `SERPER_API_KEY` (or `BING_API_KEY`)
- `ANTHROPIC_API_KEY`

**4. Enable Actions** on the repo if it's not on by default, and the daily
cron in `.github/workflows/daily_discovery.yml` will start running
(currently set to 06:00 Gulf time / 02:00 UTC — edit the cron line to change
that).

That's it — no server, no always-on process. GitHub Actions runs it for you.

## Running it locally (optional, for testing)

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in your real keys
export $(cat .env | xargs)
python -m discovery.main --max-queries 20   # cheap test run, ~20 queries instead of 240
```

Drop `--max-queries` for a full run. Add `--keep-ignored` if you want to see
what got filtered out as ⚪ Ignore (useful for tuning the classifier prompt).

## Reviewing results

Everything lands in `data/discovery_inbox.csv` with a `Status` column that
starts as `🟡 Review`. The pipeline never touches a row you've already
edited — it only appends new rows. Update `Status` to:
- `Add to Report Hunt` — this becomes a report you track going forward
- `Ignore` — not relevant, leave it and move on

The `Already Tracked` column flags anything that matches a report already
listed in `config.yaml`'s `already_tracked` list, so you're not re-reviewing
things you already know about.

## Tuning it over time

Everything that controls *what* gets searched and *how* it's scored lives in
`config.yaml` — no code changes needed for:
- Adding a newly-discovered organisation to `priority_orgs` (site: search)
- Expanding `relevance_vocabulary` as FCSC's portfolio grows
- Updating `already_tracked` as your Report Hunt list changes
- Adjusting `years` each January

If the classifier is being too strict or too loose, the rubric it follows is
in `discovery/classify.py` (`SYSTEM_PROMPT_TEMPLATE`) — tightening or
loosening the definitions there is usually more effective than editing the
vocabulary list.

## Cost estimate

At ~240 queries/day and maybe 20-40 genuinely new results/day to classify:
- Search API: free tier or low tens of dollars/month depending on provider
- Anthropic API: a few cents/day (classification prompts are short)

Both scale down fast if you reduce query volume (e.g. drop the `years` list
to one year once you're past a report's usual release window, or trim
`terminology` if certain terms rarely produce anything useful).

## Known limitations / things to watch

- **Search snippets are short.** Sometimes a rank/score is in the full PDF
  but not the search snippet — Claude will score these as Medium/Low even
  if a look at the source would show High. Worth spot-checking Medium items.
- **First run will be noisy.** The first time this runs, everything is "new"
  since the inbox is empty — expect a larger batch than subsequent daily runs.
- **Same-report variants.** Org press release vs. news coverage vs. PDF
  sometimes still slip past dedup as separate rows if titles differ a lot.
  Not harmful (redundant review), just occasionally repetitive.
