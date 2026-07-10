# Source coverage by kind

Written 2026-07-09 after the kind-sources research push (three parallel
research passes: Reddit via arctic-shift plus live endpoint probes on
every candidate). Read this before adding or rejecting a source; the
skip list records WHY things are out, so nobody re-litigates them cold.
The operating contract for keeping sources healthy is
`docs/source-reliability.md`; the one-file recipe is
`docs/adding-a-source.md`.

## Live sources per kind (2026-07-09)

| kind | sources | pay shape |
|---|---|---|
| skill | 18 career scrapers + JobSpy boards, r/forhire gigs | stated ranges |
| think | FocusGroups.org, **User Interviews** | per-session, stated |
| perform | AuditionsFree, Casting Networks, 1iota, Project Casting, Standing Room Only | stated when posted |
| odd | **r/slavelabour** | stated in titles, note-first |
| flip | **r/PKMNTCGDeals** | never (a price is not a payout) |
| deliver | none, by verdict (see below) | n/a |
| lookafter | **Sittercity** | poster-set hourly ranges |
| house | **Doctor of Credit**, **BankRewards.io** | exact stated bonuses |
| body | **ClinicalTrials.gov** (refiled from think), **Study Scavenger** | stated, up-to maps to a ceiling |
| party | none, by design (make your own) | n/a |

Bold = added in the kind-sources push. Every source is one decorated
file under `src/job_finder/tools/scrapers/`, lane-validated at import,
and judged per run by `GET /api/v1/scrapers/health`.

## Verdicts that shaped the lineup

- **User Interviews** serves its public browse page from an open JSON
  API with compensation on every listing. The best-liked paid-research
  platform on r/beermoney. The find of the research pass.
- **Doctor of Credit is canonical for house**: r/churning treats it as
  the source of record, and its "Offer at a glance" block publishes the
  hard-pull and ChexSystems facts that ARE our catch line. BankRewards
  rides along for clean structured fields; it is a solo community tool
  that may vanish, and the health endpoint will say so if it does.
- **Clinical trials moved from think to body.** The communities have
  self-sorted: r/plassing and phase-1 forums talk confinement economics
  and hematocrit; r/focusgroups talks screeners and gift cards. Selling
  an opinion and renting a body are different quests. The alembic data
  revision refiled existing rows.
- **Deliver has no listings, only programs.** DoorDash, Instacart,
  Spark, Flex, Roadie, and GoShare are signup funnels behind interactive
  forms; no per-listing feed exists anywhere. If the lane should light
  up, the honest move is hand-curated evergreen program posters with
  saturation and waitlist caveats, which is a product decision, not a
  scraper.
- **Plasma is the same shape**: no chain publishes a structured pay
  schedule (the real rates are weight-tiered, per-center, app-only), so
  plasma belongs as evergreen program posters or not at all.
- **Flip cards mostly carry no pay on purpose.** Deal sources state a
  price (what you pay), never a profit. Rendering "not stated" on a
  drop lead is the truth of flipping, not a data gap.

## Declined, with reasons (do not re-add without new facts)

- **Craigslist gigs**: technically trivial (an open JSON search API
  exists and probes clean, with verbatim stated pay, ~70 posts/day per
  metro), but Craigslist is famously litigious about scraping (3taps).
  Wrong risk for a hosted product. Revisit only with a real legal read.
- **Respondent.io**: listings behind a signup wall, and community
  reputation is poor.
- **focusgroup.com (Sago)**: panel signup only; the community reports
  collapsed pay and months-late payments since the Sago merger. Fails
  the honesty bar even if it were scrapable.
- **TaskRabbit / Nextdoor / Rover**: no public listing surfaces at all
  (app-gated or login-walled). Confirmed by probe, not assumption.
- **BrickSeek**: useful tiers are paid, endpoints 404, community trusts
  its data less than its marketing.
- **HustlerMoneyBlog**: scrapable but affiliate-respun; DoC covers the
  same ground with honesty fields.
- **CenterWatch**: derived from ClinicalTrials.gov; adds nothing over
  the v2 API we already use.
- **Email-only recruitment listings** (the FocusQuota pattern flooding
  r/paidstudies): never ingest a listing whose only apply path is a
  bare email address; the community reports non-payment.
- **Prolific**: never scraped, never probed, standing rule.

## Probed and queued (good, just not built yet)

In rough impact order: FindFocusGroups.com (think; sitemap + clean HTML,
pay always stated), Fortrea phase-1 units (body; a literal compensation
column, $7k-$15k posters), Care.com SEO job pages (lookafter; biggest
volume, moderate HTML build), r/sportsbook sbpotdbot daily promos
(house; needs state-legality gating), TrustedHousesitters + MindMyHouse
(lookafter; unpaid free-stay exchange, render the actual deal),
r/buildapcsales + Slickdeals search RSS (flip; strict title grammar,
watch for shopping-feed drift), r/DoneDirtCheap (odd; overlaps
slavelabour).

## Ingest guardrails (apply to every future source)

- Pay renders only as the source states it; "up to $X" maps to a
  ceiling, never a floor; a price is never a payout.
- Platform-manipulation tasks (karma, upvotes, reviews) and gift-card
  payment tasks fail house rules even when real.
- Subreddit sources ride the shared `_reddit.py` helpers and gate on
  the sub's own moderation signals (flairs), not keyword guessing.
- A source that throttles or breaks shows up in
  `GET /api/v1/scrapers/health`; that is the first place to look when a
  kind runs thin.
