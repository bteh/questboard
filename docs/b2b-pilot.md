# The B2B pilot: companies side-quest too

Shipped 2026-07-12 per the strategy council and debates (unanimous on
shape). A small studio hunting clients, stages, and funding is a seeker
the same way a person is; the mission ("help people land something")
generalizes to them. This pilot tests demand with free board content
before any studio-facing product exists.

## What shipped

Two kinds behind the registry, filled by live-probed sources:

- **speak · Take the stage** (talks, panels, CFPs): CallingAllPapers
  (the aggregate open-CFP set, ~295 rows) + PaperCall (~224 direct, with
  the stated travel-assistance perk flag). Rows link to the SUBMISSION
  page and expire at their own stated deadline. No pay is ever rendered;
  exposure is not pay, stated travel assistance rides in the perk note.
- **pitch · Pitch it** (grants, accelerators, competitions): SBIR.gov
  open topics (small-business by legal definition), the California
  Grants Portal open dataset (Business-eligible rows only), and the
  accelerator majors (YC, Techstars, 500 Global) as a curated
  full-snapshot set. Amounts render only as stated; entry-fee
  competitions are declined as a class (docs/source-coverage.md).

The payment constitution (docs/payment-constitution.md) published the
same day: listed parties never pay; only seekers ever pay, person or
studio.

## The decision, dated

**Decision date: 2026-10-12** (one quarter). The pilot is judged on:

- saves/clips of speak+pitch rows (the act signal)
- standing briefs mentioning company-shaped asks, once briefs exist
- concierge digests sent against studio briefs, and their act-rate
- reported wins ("we got the talk / the grant"), by hand

Never judged on: listing traffic, page views, row counts.

Possible outcomes: (a) signal → the Studio Scout becomes a build (same
Scout engine family, capability-brief matcher, priced as a studio
season pass under the constitution); (b) no signal → the kinds stay as
free board content or retire; the decision must be MADE on the date,
not deferred (the pilot may not become indefinite avoidance).

## Known caveats (from the 2026-07-12 accuracy audit)

- **California Grants Portal "active" status can lag the real cycle.**
  The CKAN dataset marked a Song-Brown training grant `active` while the
  program page said it "will not be accepting applications for the
  2026-27 cycle". The page returns 200, so neither the dead-link
  re-verify (HTTP-level) nor the row contract catches it; detecting it
  would need a per-row program-page fetch, which the scraper does not do.
  For the pilot this is accepted and the row is tombstoned by hand when
  found. If it proves frequent, cagrants gets stricter handling or drops
  at the quarterly review.
- **Speak lane:** predatory pay-to-present conference mills and sentinel
  placeholder deadlines (e.g. 2050-01-01) are now filtered at the source
  (`_speak.py`), after the audit found one of each on the board.

## Deferred with reasons

- Grants.gov search2 API: works (448 small-business-eligible rows) but
  skews institutional (NIH-shaped); needs a relevance-filter design so
  the lane doesn't read "not for me" to a studio. Queued.
- MCP/verified-data feed: parked by the council until user-directed
  agents are an observed channel and this pilot has reported.
