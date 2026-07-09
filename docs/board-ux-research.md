# Board UX research: pain points, navigation, and true requirements

Logged 2026-07-09. Companion to `sidequest-research.md`. Source: a 5-agent sweep (Reddit via
arctic-shift + web verification against official platform pages). Re-read this before changing the
card requirements model, the nav shell, or the trust signals.

---

## Pain points in the apps Questboard replaces

### Gig-finding apps (TaskRabbit, Instawork, Wonolo, Fiverr)
The four failure modes repeat identically across every platform sampled:

1. **Silent deactivation, dead-end appeals.** Five-year, thousand-task veterans buried or removed
   over one ambiguous "policy violation," appeals go nowhere. The single most repeated post type
   on r/TaskRabbit.
2. **Support unreachable exactly when pay is at stake.** No phone number, chatbot loops, tickets
   dead for weeks. Present in every subreddit pulled. ("Why don't they have a number we can call?
   I'm dead broke.")
3. **"Near you" is a lie.** Instawork repeatedly shows shifts 2+ hours away; support tells people
   to accept far shifts to "unlock" close ones. Several independent threads.
4. **The board looks alive but the market died.** Wonolo areas that were "saturated with jobs" go
   blank for six months while support insists jobs post daily. Chronic, 2022 through 2026.

Plus: payout confusion/shortage across all four, scam listings living inside the real marketplace,
reputation tiers you can't enter without already having reputation, and fragmentation so bad an
Instawork user built a whole Slack community just to track work across Wonolo/Upshift/Instawork/
Qwick. That fragmentation workaround is Questboard's central pitch confirmed.

**What they want:** one aggregated view, honest local distance, an honest signal of whether a
market has real work right now, scam protection before wasted time, transparent payouts.

### Job boards (Indeed, LinkedIn, ZipRecruiter)
People have stopped trusting the category, not just individual listings.

1. **Ghost jobs and repost churn**: recycled listings marked "new," reissued under new IDs after
   you interviewed. Highest-volume complaint. Fix: first-seen date + repost count on every card
   (confirms the ghost-job trust-signal work already shipped on the career side).
2. **The application black hole**: silence after interviews, no status anywhere. Fix: never a
   submit-and-vanish flow; Your log answers "which application is this."
3. **Managing the search costs more than applying**: LinkedIn + Indeed + a spreadsheet + memory.
   Two of the highest-scored threads in the pull. Fix: the log replaces the spreadsheet.
4. **Filters that don't filter**, stale results resurfacing, black-box match scores. Fix: literal,
   legible filters that show why a card matched.
5. **Hidden salary until deep in the funnel.** Fix: pay on the card, always (already core).
6. **Scam/spam listings**: SSN/ID upfront, fake recruiters, Telegram "jobs." Fix: verified sources
   only, and a visible "we never ask for your SSN or ID" statement.
7. **Login walls**: no account needed to browse or see real detail.

### Casting / study / promo platforms (Backstage, UserInterviews, Prolific, BA agencies)
The pay level isn't the complaint; being structurally cheated out of time is.

1. **Screened out but coded as a rejection** ("finished too quickly"), dinging account standing.
   Fix: structurally separate "did not qualify" from "did not deliver"; a screen-out never touches
   the user's log as a failure.
2. **Non-payment with no escalation path**: the most repeated complaint across all three platform
   types, spanning years. Fix: a payout-reliability signal per poster/agency, surfaced BEFORE the
   time is spent.
3. **Unpaid screener time** sometimes as long as the paid task. Fix: show expected screener length
   and screen-out risk up front.
4. **Upfront-fee BA scams** recurring under new names since 2014. Fix: standing blocklist patterns,
   hard-filtered (already in House rules).
5. **Waitlists that produce nothing** (Prolific): be honest about time-to-first-quest.
6. **"Is this paid casting site still worth the fee"**: track submission-to-callback activity per
   platform like ghost-job signals.

---

## Navigation: replacing the default SaaS sidebar

Seven concepts researched (diegetic game UI, editorial mastheads, desk metaphors, physical tabs,
radial menus, spatial pan/zoom, ticket-stub bottom bars). Full pros/cons in the workflow journal.

**Verdict (adopted):**
- **Desktop: editorial masthead byline.** Wordmark as a printed nameplate, destinations as a
  small-caps inline text rule (The board · Your log · Alerts · Settings), current section circled
  in red ink. Cheapest to build, purest fit with the paper identity, words not mystery icons.
- **Alternative worth prototyping: notebook divider tabs** (physical index tabs on the page edge,
  active tab flush) and **desk-object row** (illustrated objects with visible labels).
- **Phone: torn ticket-stub bottom bar**, drawn from scratch (perforation, hand stamp), never a
  reskinned Material bar.
- **Rejected: spatial pan/zoom board and radial fan-out.** Most distinctive, but they tax the
  destinations people hit fast (Alerts, Settings) and carry accessibility debt.
- Rule from the icon-literacy risk: text labels always visible, never icon-only nav.

Three variants were prototyped from this (masthead / ledger tabs / desk objects); see scratchpad
board-vA/vB/vC and the artifacts in the session.

---

## The requirements model (what "bring:" may show, per kind)

Verified against official pages (Backstage, Central Casting, Amazon Flex, Turo, CSL Plasma,
Instawork help, Rover support, FTC). Cards must never cross-contaminate kinds.

| Kind | Must bring | Watch out |
|---|---|---|
| Bring a skill (career job) | resume (+ fit shown) | background checks common even for office roles; never a headshot |
| Bring a skill (gig tier) | portfolio/samples + own gear | TIPS de facto required for bartending; notary = exam + bond + $100-400; online ordination free but some counties require registration |
| Odd jobs (person-posted) | nothing, just show up | shift apps differ: Instawork background-checks every worker before the first shift |
| Deliver & drive | 4-door car (Flex rejects 2-door hatchbacks), license, insurance, 21+, background check | personal auto policies often exclude delivery; checks take days |
| Tell them what you think | honest screener answers; mic + webcam for remote | no audio = unpaid (UserTesting); NEVER a resume; mystery-shop signup fees are always a scam (FTC) |
| Lend your body | government ID + address proof + health screen | tattoo/piercing in last 4 months disqualifies (CSL); FDA cap 2x/week; new-donor bonuses are time-limited; taxable |
| Perform & entertain | casting/extras: current UNEDITED photo + sizes + availability; VO: mic + interface + quiet room + short demo | a retouched headshot gets you REJECTED for background work; principal roles want a theatrical credits sheet, never a corporate resume |
| Look after | informal: references; platform: profile + mandatory background check | Rover: $40 non-refundable application fee, 10-20 business days to approval |
| Flip & rent | cash upfront or an ELIGIBLE asset | Turo: car must be 12 years or newer, under 130k miles, clean title; the host gets vetted too |
| Beat the house | 21+ (18 in KY/NH/MT/RI/DC/WY), KYC ID before betting, funded bank account, legal state | bonuses taxable (1099); fast churning trips ChexSystems; DD minimums often exceed the bonus |
| Party quests | 4 friends + a Saturday | nothing else |

Positive absence is a feature: quests that need nothing say "bring: nothing, just show up."

---

## What this means for the product (the build checklist)

- Career cards: first-seen date + repost flag (freshness proof).
- Distance shown literally ("2 blocks from you"), never a padded "near me."
- Supply honesty: a thin kind says "quiet this week" instead of inflating.
- Study cards: screener length shown; screen-outs never logged as failures.
- Pay-speed chip where truthfully known ("cash same day").
- House rules carries: no MLMs, no pay-to-start, nothing adult, never asks SSN/ID, browse
  without an account.
- Nav: masthead byline (desktop) or one of the two physical alternatives; ticket-stub bar on phone;
  labels always visible.
