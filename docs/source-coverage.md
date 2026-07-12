# Source coverage by kind

Written 2026-07-09 after the kind-sources research push (three parallel
research passes: Reddit via arctic-shift plus live endpoint probes on
every candidate). Read this before adding or rejecting a source; the
skip list records WHY things are out, so nobody re-litigates them cold.
The operating contract for keeping sources healthy is
`docs/source-reliability.md`; the one-file recipe is
`docs/adding-a-source.md`.

## THE CURATION VERDICT (2026-07-10): reddit is research, never content

A live audit found the board's promise broken three ways: r/PKMNTCGDeals
bot announcements ("Rumored Target drop tonight", a literal
"[ Removed by moderator ]") pinned as quests, a Project Casting scam-alert
BLOG POST published as a casting call through the article fallback, and
scam-shaped posts ("TikToks $100-1600/month") among real r/slavelabour
tasks. Deep research (6 probes) plus a three-model debate (Codex, Sonnet,
Fable; blinded round) settled it:

- **Reddit is demoted to research-only, product-wide** (`research_only=True`
  on the registry entry; no sweep or refresh may run one). Two structural
  reasons beat per-lane gating: the arctic-shift mirror cannot see mod
  removals, and on marketplace subs mod removal IS the scam filter, so a
  removed scam would stay pinned for days; and gate regexes lose to an
  adaptive adversary (two gate patches shipped in two days; a new scam
  shape appeared anyway). Legal reinforces it: a monetized product
  republishing reddit content via an unauthorized mirror is the shape
  Reddit acted against with Pushshift (2024). Reddit's job here is what
  it was always best at: telling us WHERE to crawl.
  Re-entry bar: authorized Reddit API access with live post state, plus a
  validator that rejects removed/locked/deleted posts.
- **The flip lane is paused** (unanimous verdict). Drop freshness is
  minutes; the board restocks manually today, so even a verified retailer
  URL goes stale dishonestly fast, and "verified at scrape time" would be
  a false badge. Re-entry bar: the scheduler with minute-capable cadence,
  plus at least one sanctioned source (Best Buy Products API, TCGplayer
  API, or Pokemon Center poll-and-diff), plus a minutes-scale TTL.
- **The odd lane goes honestly empty** (r/slavelabour was its only
  supply). Same state as deliver: a lane with no live sources renders
  empty rather than filling with rows we can't stand behind.
  r/DoneDirtCheap inherits the reddit verdict; finding crawlable
  odd-jobs sources with real counterparties is an open research task.
- **Every row must terminate at a place you can act** (the projectcasting
  fallback that turned articles into rows is deleted). The per-row
  actionability contract (specific ask, way to act, real counterparty,
  real date) is the next trust build; rejects will land in the run log
  as rows_invalid.

Principle, from the debate synthesis: scarcity is less damaging than
false actionability. Debate record:
`~/.claude-octopus/debates/.../001-board-curation/synthesis.md`.

## Live sources per kind (2026-07-11, post-supply-push)

| kind | sources | pay shape |
|---|---|---|
| skill | 18 career scrapers + JobSpy boards | stated ranges |
| think | FocusGroups.org, **User Interviews** | per-session, stated |
| perform | AuditionsFree, Casting Networks, 1iota, Project Casting, Standing Room Only | stated when posted |
| odd | none (honest state; see the 2026-07-11 verdicts) | n/a |
| flip | none, paused by curation verdict (was r/PKMNTCGDeals) | n/a |
| deliver | none, by verdict (see below) | n/a |
| lookafter | **Sittercity** (429 postmortem fixed), **Care.com**, **UrbanSitter** | poster-set hourly ranges only |
| house | **Doctor of Credit**, **BankRewards.io** | exact stated bonuses |
| body | **ClinicalTrials.gov**, **Study Scavenger**, **Trialmed (PPD clinics)**, **Fortrea**, **ICON** | stated, up-to maps to a ceiling |
| speak | **CallingAllPapers**, **PaperCall** (B2B pilot, docs/b2b-pilot.md) | never; stated travel assistance rides in the perk note |
| pitch | **SBIR.gov**, **California Grants Portal**, **Accelerator majors (YC/Techstars/500)** (B2B pilot) | amounts only as stated; up-to = ceiling |
| party | none, by design (make your own) | n/a |

Bold = added in the kind-sources push. Every source is one decorated
file under `src/job_finder/tools/scrapers/`, lane-validated at import,
and judged per run by `GET /api/v1/scrapers/health`. The three reddit
scrapers stay in the tree as research tooling (`research_only=True`).

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

## The 2026-07-11 supply push (three live-probe research passes)

**Sittercity 429 postmortem: it was us.** The shared headers' `Accept:
application/json` made every city URL 301 onto the generic
`/babysitting-jobs` path (which 406s), and that per-path burst tripped
their rate limiter. Never a bot wall. Fix: ask for HTML, treat a
generic-redirect landing as a failed city.

**Built:** Care.com (jobs sitemap the site publishes deliberately,
JSON-LD JobPosting, poster-set hourly, crawl-delay respected),
UrbanSitter (`__NEXT_DATA__` city pages, poster-set rates or no pay,
3s crawl delay), Trialmed = the PPD clinic network (open WP REST,
US-clinic + enrolling-now gates, data-driven country map), Fortrea
(server-rendered study table, exact stated stipends), ICON
(studies-cards, up-to ceilings, no source dates by the DoC precedent).

**Declined with evidence:**
- **FindFocusGroups (was queued: FLIPPED).** Listings 41 days stale,
  city pages empty, and a live SQL-injection test listing sat
  unmoderated for 15 days. The Project Casting failure shape.
- **Airtasker.** Public browse and an open JSON API exist, but
  robots.txt disallows /tasks and /api. The Craigslist shape: trivial
  tech, the site says no. Revisit only with a legal read or partnership.
- **Think-lane facilities as a class** (Schlesinger=Sago, L&E,
  Fieldwork, WatchLAB, Plaza dead): the industry moved to
  panel-signup + screeners; public session calendars no longer exist.
- **User-testing platforms as a class** (PlaytestCloud, BetaTesting,
  Userlytics, TestingTime): email-invite panels, no public gig lists.
- **Velocity Clinical** (lead form, no rows), **ResearchMatch**
  (register-and-be-contacted), **CenterWatch** (CT.gov-derived,
  standing decline), **Nextdoor** (login-walled, verified),
  TaskRabbit-adjacent apps (Dolly→TaskRabbit, Gigwalk/Field
  Agent/Observa in-app only), gig-shift boards (Wonolo, Instawork,
  Jobble: marketing pages or ad arbitrage, no listings).

**Product decisions, not scraping problems:**
- **House sits** (TrustedHousesitters, MindMyHouse, Nomador): pay is a
  free stay AND applying needs a paid sitter membership. Only honest as
  a labeled "unpaid stay, membership required" poster. MindMyHouse has
  a public RSS if that call ever lands.
- **UW-Madison local student jobs**: a real, rare find (named
  household posters, lump-sum tasks, same-day dates, public board) but
  single-metro. Deferred as the pilot of a "campus community boards"
  pattern; most campuses are login-walled (JobX class verified).

**Watch items:** donedirtcheap.app (the r/DoneDirtCheap mods' own
off-reddit platform; waitlist-only today, purpose-built odd-lane supply
if it launches). The odd lane's honest state is empty: US-wide one-off
task supply with real counterparties lives inside login walls today.

## The 2026-07-12 B2B pilot pass (two live-probe researchers)

**Built (speak):** CallingAllPapers (one GET = the whole open-CFP set,
~295 rows incl. the Sessionize supply that has no public surface of its
own; api robots disallow is search-engine de-indexing, the project's own
homepage offers the API publicly) + PaperCall (~224 direct, permissive
robots, and the only structured stated-perk signal in the lane: "CFP
offers travel assistance"). Queued ride-alongs: confs.tech
conference-data and developers.events all-cfps.json (both MIT
open-JSON, heavy CAP overlap; add when dedupe-by-submission-URL is
worth the volume).

**Built (pitch):** SBIR.gov open topics via server-rendered HTML (the
official JSON API is down for maintenance and is the documented upgrade
path), California Grants Portal (official CKAN dataset on data.ca.gov,
updated daily, Business-eligible rows only; the pilot of a state-portal
pattern, most states run login-walled eCivis/Fluxx instead), and the
accelerator majors as one curated scraper (YC data-page JSON, Techstars
__NEXT_DATA__ programs with ISO deadlines, 500 Global via
strict-grammar-or-skip prose).

**Deferred:** Grants.gov search2 API (works, no auth, 448
small-business-eligible rows, but NIH-shaped institutional skew would
make the lane read "not for me" to a studio; needs a relevance-filter
design first). SAM.gov opportunities API (needs a free API key: a
config decision).

**Declined with evidence:** Sessionize direct (no public open-CFP
directory; /discover 404; supply arrives via CAP; sessionize.com stays
a valid link target), WikiCFP (academic paper/journal CFPs, a
Project-Casting-shaped curation trap, declined on fit), podcast
guesting as a class (MatchMaker.fm Cloudflare-walled, PodcastGuests is
a directory OF guests with guest-wanted listings behind email signup;
the marketplaces monetize the match), F6S (bot wall), OpenGrants (AI
search SPA, no listing rows), Hello Alice (2 listings, deadlines only
in FAQ prose; watch), iFundWomen (403 + membership), **paid design
awards as a class** (Awwwards $65/entry: pay-to-enter with a
non-trivial fee is this lane's scam shape even from a legit operator),
pitch-competition aggregators (blog listicles, article rows), VC4A (no
deadlines on the list surface + curation tells).

## Probed and queued (good, just not built yet)

Most of the 2026-07-09 queue resolved in the 2026-07-11 supply push:
FindFocusGroups flipped to declined, Fortrea and Care.com are built,
the house-sit pair became a product decision, and the reddit entries
died with the reddit-is-research verdict. Still genuinely queued:
Slickdeals search RSS (flip; strict title grammar, watch for
shopping-feed drift; only relevant once the flip lane re-enters),
UW-Madison local student jobs (odd; the campus-boards pilot, see the
supply-push verdicts), donedirtcheap.app (odd; watch for launch).

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
