# Source reliability: the trust layer

Written 2026-07-09. Trust is the product: a dead link or a silently broken
scraper costs more than a missing feature. This doc holds the operating
contract, what is built, what is queued, and the research behind the
choices.

## The failure we are defending against

A scraper that breaks LOUDLY (exception, timeout) is easy. The dangerous
case is the silent one: a site redesign that returns 0 rows or garbage with
HTTP 200, a soft block serving a placeholder page, selector drift putting
the wrong text in the right field. To the old code, all of those looked
exactly like a quiet day. Users then see an empty or wrong board and blame
the product, never the pipeline.

## Built now (PR: source run log + health)

**1. The run log, `scrape_runs`.** One row per source per fetch, written by
`run_scrapers()` in `tools/scrapers/_registry.py`:

| column | meaning |
|---|---|
| source | scraper name from the registry |
| vertical | the board lane it feeds |
| started_at, duration_s | when and how long |
| finish_reason | ok, zero_rows, exception, timeout |
| rows_found | listings returned before filtering |
| error_sample | first 500 chars of the failure, empty when fine |

A source that hangs past the pool timeout still gets a row (finish_reason
timeout). Recording never raises: a broken log must not kill a scrape.

**2. Health verdicts, `job_finder/source_health.py`.** Each source's latest
run is compared against its own recent history (relative baseline, not a
fixed floor, so thresholds do not rot):

- `failing`: latest run raised or timed out
- `zero_rows`: latest run found nothing while the source's median says it
  normally finds rows. This is the silent-breakage signature.
- `dropped`: latest run found less than half the recent median (rule only
  applies when the median is at least 8, a 3-row source dipping to 1 is
  noise)
- `quiet`: finds nothing and never has lately, honest low supply
- `ok`: everything else

**3. The triage endpoint.** `GET /api/v1/scrapers/health` returns every
source, worst verdicts first, with the last error line inline plus a
`needs_attention` count. Triage is one call. The `/health` page in the app
renders it (tiles, verdicts, and the raw run log via
`GET /api/v1/scrapers/runs`); the door in is the board legend's
"sources checked" line.

**4. Healthy-run-gated expiry** (`job_finder/expiry.py`). Every row
carries `last_seen_at` (stamped on every re-scrape). Each source declares
its own expiry contract in its registry entry: `full_snapshot=True`
sources (one fetch is the whole current set, e.g. BankRewards) expire
rows absent from TWO consecutive healthy runs; windowed sources declare
`stale_after_days` instead, because absence from a newest-N fetch proves
nothing. Backstops: a mass-expiry guard skips any sweep that would
tombstone more than 30% of a source's live rows (a URL-format change must
page a human, not wipe a lane); expired rows are tombstones, not deletes
(they leave the board, keep the record, and keep their place in the log);
a re-listed URL revives automatically; and confirmation never bumps
updated_at, so a nightly re-scrape cannot reshuffle the user's log.

**5. Rotating database snapshots** (`job_finder/backup.py`). Every quest
refresh takes a snapshot first when the newest one is 20+ hours old
(SQLite online backup API, keep 5, `<data>/backups/`). A bad sweep, a bad
migration, or an over-eager source can always be undone.

**6. Freshness as UX.** `/board/summary` carries `checked_at` from the
run log and the board legend renders "sources checked Xh ago" plus the
plain-words expiry promise. Accuracy is shown, not claimed.

## Queued next, in impact order

These come from the research below; each is its own small PR.

1. **HEAD re-verification for aging rows.** The existing url_status +
   check_urls machinery extended to quest lanes: HEAD-check HTML-source
   URLs as they age; for ATS sources, absence from the JSON endpoint is
   the cheap closed signal.
2. **Original posted dates from ATS fields** (Greenhouse first_published,
   Lever createdAt), never a repost-reset date.
3. **Row contract validation.** Pydantic check per scraped row (url parses,
   pay only as stated, dates not in the future), with rows_invalid counted
   into the run log and alarmed like volume drops. Catches selector drift
   that volume checks miss.
4. **Canary URL per source.** One known-good listing re-checked each run;
   the cheapest early warning for redesigns.
5. **Per-source config knobs.** rate_limit, expected_min_rows, enabled flag
   in the registry so a hostile source can be switched off without a
   deploy, plus a circuit breaker: after 2-3 consecutive failing runs,
   auto-disable and alert (the JobSpy boards already have one; this brings
   the plugin sources up to par).
6. **Hosting the DB.** SQLite stays for launch: WAL mode,
   busy_timeout 5000, one writer doing batched transactions, Litestream
   streaming the WAL to S3 for continuous backup. That setup is a
   legitimate production shape for a read-heavy board with batch writes
   (10-20 microsecond reads, per Fly.io's writeup). The Postgres moment is
   deployment-shaped, not load-shaped: it arrives when we want multiple app
   instances or rolling deploys.

## Research digest (2026-07-09, online sweep)

Battle-tested patterns from teams that run scraper fleets in production.

- **Post-run monitor suites**: Zyte's Spidermon fails a run on
  items-below-floor, error counts, unexpected finish reason, or field
  coverage below a threshold, and routes to Slack/Sentry.
  (scrapeops.io/python-scrapy-playbook/extensions/scrapy-spidermon-guide,
  zyte.com/blog/spidermon-scrapy-spider-monitoring)
- **Relative baselines beat fixed floors**: ScrapeOps checks every run
  against the spider's 7-day moving average; Scrapfly's multi-source guide
  alarms below 50% of the previous run and treats zero rows as its own
  alarm class. (scrapeops.io/monitoring-scheduling, scrapfly.io/blog)
- **Silent failure modes to test for**: soft blocks (200 OK placeholder),
  JS-rendering gaps (skeleton HTML), selector drift (plausible wrong
  values). Canary records are "the cheapest ground truth".
  (ficstar.com/why-scraping-fails-silently)
- **Freshness numbers for job data**: TheirStack re-crawls every 10 minutes
  to daily by source volume; median job closes ~25 days after posting;
  repost dedup window 30 days. Unverified for 72h deserves a re-check;
  past 30 days, out of default results.
  (theirstack.com/en/docs/data/job/freshness)
- **The expiry standard is written down**: Google requires expired postings
  to set validThrough past, 404/410, or drop the markup, and hands out
  manual actions for stale jobs. Job-board practice is a tombstone page,
  not a delete, so dedup history and internal links survive.
  (developers.google.com/search/docs/appearance/structured-data/job-posting)
- **Stale-if-error**: when the origin breaks, serve the last known good
  value, flag it stale, log loudly. Never serve nothing.
  (fastly.com stale docs, web.dev/articles/stale-while-revalidate)
- **Visible freshness builds trust**: an explicit "last verified" stamp per
  listing or source reads as a differentiator; hiding staleness erodes
  trust when users find out. Show the original ATS posted date, not the
  repost-reset date. (whenthisjobwasposted.com/about, dqops.com)
- **SQLite in production**: Fly.io's Litestream writeup and the WAL +
  busy_timeout + single-writer discipline. (fly.io/blog/all-in-on-sqlite-litestream)
