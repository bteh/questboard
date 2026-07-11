# The concierge test

The Scout, run by hand, before any Scout code exists. The council's
cheapest de-risk (2026-07-10 strategy records): if a hand-curated,
verified dispatch doesn't earn the open from 10-20 real people, no
amount of scheduler plumbing will save the automated version.

## How to run one dispatch

1. Get a brief from a real person, in their words. One sentence is
   enough ("an extra $500 this month, remote, no acting"). Fill a copy
   of `brief_example.json`: their sentence verbatim in `brief`, then
   translate it into `kinds`, `search`, `place`, `pay_floor`.
2. Backend running (`make dev`), then:
   `/usr/bin/python3 scripts/concierge/digest.py scripts/concierge/<name>.json`
3. Read the digest BEFORE sending. You are the verification layer in
   this test: click every link, confirm every listing is live and says
   what the digest says. Cut anything you would not stake the board's
   promise on. Hand-curation is the point.
4. Send the HTML (paste into an email) or the markdown, personally.
   No blast tools, no tracking pixels; this is a note from a person.

## What to record, per send (a row in a spreadsheet)

- date sent, brief (verbatim), items sent
- opened? (ask, or infer from the reply)
- acted on any item? which one?
- replied at all? what did they say, verbatim?
- would they want the next one? (the real question)

## What decides the Scout build

From the council verdicts: digest act-rate and do-they-want-the-next-one
are the signals; never "applications sent". A few weeks and 10-20 people
is enough to know. Zero-match dispatches count as sends: the honest
"nothing cleared your bar, nearest miss failed on X" note is part of
what is being tested.

## Rules the digest already enforces

Pay renders only as stated (ceilings say "ceiling, not a promise");
every item carries an evidence line (source, when it was last checked,
where the link goes); prep notes derive from row fields and the board's
own kind copy, never from guesses. Keep hand edits inside those rules.
