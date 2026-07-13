# Quest taxonomy rework: fill the board with things people actually want

Written 2026-07-13 from a 5-angle Reddit/forum research sweep + synthesis + an
adversarial pass that grounded every claim against the live registry, the
scrapers, the payment constitution, and the B2B pilot doc. Driven by the
founder's complaint: "beat the house, join a study, take the stage, pitch it"
feel weak/off; "look after" is mostly kids, what about pets; fill the board with
things people actually want, not ambiguous or frightening.

The headline: the instincts were right, but the fixes are smaller and more
surgical than "add new categories," because most of the problem is **labels and
ordering, not supply**. Three of the first draft's "facts" were wrong in the
code; the corrected calls are below.

## Verdict per current kind (reconciled)

| kind | now | verdict | why |
|---|---|---|---|
| think | Tell them what you think | **Promote to hero (order 1)** | Best-loved, best-paying, least-scary thing in the whole sweep (focus groups/mock juries, "$300-600/day, more than my job," free meals). Only fear is "is it legit," which "if it's pinned here it's real" kills. |
| lookafter | Look after | **Pets-first (small fix)** | Care.com ALREADY ingests petcare; childcare posts just crowd pet rows out (40-fetch cap, newest-first). Add a per-vertical quota so pet rows are guaranteed; reframe copy pets-first. |
| house | Beat the house | **Rename, de-gamble** | The supply was never gambling: it's already bank/card bonuses (Doctor of Credit, BankRewards). The label is the lie. Rename to "Bank & card bonuses," drop matched betting + casino hue. Pure copy/registry edit. |
| skill | Bring a skill | Keep | Durable home for ongoing skilled work (tutoring, voiceover, AI-training). |
| odd | Odd jobs | Keep, honestly empty | High want (assembly/mounting $130-250) but no crawlable source (TaskRabbit/Airtasker/Craigslist all fail). Don't fake-fill. |
| perform | Perform & entertain | Keep | Real live casting sources. Guard against brand-ambassador drift. |
| body | Join a study | **De-scare, don't cut** | Not weak, frightening ("drug trial = guinea pig"). Fix with a per-row "what happens / does it hurt / how long / how you're screened" line. Do NOT relabel to "plasma" until a plasma source is wired (live rows are drug trials; relabeling = false advertising). |
| deliver | Deliver & drive | Keep as evergreen entry | Gig apps have no public per-gig feed. Honest "start here" only. |
| flip | Flip & rent | Keep paused | Drop TTLs are minutes, no scheduler; "verified" would be a false badge. |
| party | Party quests | Keep, don't headline | Self-made novelty. |
| speak | Take the stage | **De-rank, don't cut (yet)** | Genuinely too B2B/niche for a normal browser. BUT a dated B2B pilot (docs/b2b-pilot.md, decision 2026-10-12) is measured by saves/clips of these rows. Cutting now kills the experiment before its decision, and there's no B2B surface to move it to. De-rank to the bottom under a "for makers & founders" shelf; let the Oct 12 decision make the cut. |
| pitch | Pitch it | **De-rank, don't cut (yet)** | Same as speak: founder inside baseball, but part of the dated pilot. De-rank, don't cut. Contest remnant can seed the new bounty lane. |
| bounty | (new) Claim a bounty | **Add** | Bug bounties + design/code contests. Real crawlable sources, constitution-clean (sponsor pays the winner, Questboard takes nothing). Copy must be honest: spec work, most entrants win $0; scope/authorization legible for bug bounties. |
| shop | (new, optional) Shop in secret | **Hold / last** | Mystery shopping. The real fraud is the fake-check/overpayment scam and scammers impersonate the exact firms you'd link (Market Force/BestMark). Weakest add; ship last with the right anti-scam copy or not at all. |

`work` (Find work) = the separate careers lane, untouched.

## The anti-scary / anti-ambiguous rules (the real deliverable)

Turn each fear into a fixed poster field:

1. **Show WHO is behind it** — source name + verified link on the poster face. The #1 anxiety-killer.
2. **Pay as a specific number + WHEN it pays + HOW** — "$600 for 2 days, paid by gift card after the session." Never "up to $X" (reads as bait).
3. **One plain "what you'll actually do + how long" line** — "Two days, 8am-5pm, listen and discuss a case." Ambiguity is the fear; a concrete script is the cure.
4. **"You never pay to start" marker, enforced structurally** — refuse to pin anything that asks the seeker for money, kits, gift cards, or off-platform contact. Also the anti-slop stance.
5. **A "what they'll ask you for" line: none / ID / bank** — make the identity cost a known price up front, not a mid-flow ambush.
6. **Match honesty to the lane's fear** — body: the "what happens, does it hurt, how long" line; care/odd/deliver: surface meet-first / reviews / background-check scaffolding (and show its absence when missing); studies: "most people don't qualify for every study" so a reject reads as normal.

## Sequence

**Quick wins (copy/registry only, no scraping, immediate trust upgrade):**
1. **De-gamble `house`** → "Bank & card bonuses" (label, sub, hue, KindStamp). Supply already wired.
2. **Promote `think` to hero (order 1)** and re-lead its copy with "$300-600/day, real venue, meals, here's a day."

**Best add (biggest want, easiest real source, constitution-clean):**
3. **Pets front-and-center:** add a per-vertical quota to the existing Care.com scraper so pet rows are guaranteed each sweep; reframe `lookafter` copy pets-first ("dogs, cats, houses, kids"), meet-first, honest fees, name the two scams (refuses in-person meet / off-platform pay / overpay-by-check). Rover/Wag/TrustedHousesitters stay evergreen "start here" links (no crawlable feed).

**Then:**
4. **Ship `bounty`** (arkadiyt/bounty-targets-data for bug bounties, 99designs/IssueHunt/Opire for design+code), honest spec-work + scope copy.
5. **De-scare `body`** with the per-row honesty line (hold the "plasma" re-sub until a plasma poster ships).
6. **De-rank `speak` + `pitch`** to the bottom under a "for makers & founders" shelf (keep them measured through the 2026-10-12 pilot decision, do not cut).

**Hold:** `shop` (mystery shopping) until the anti-fake-check copy is right, or drop it.

Constitution + verifiability thread: every add is seeker-side (the sponsor/company/family pays the seeker, Questboard never takes the poster's money or ranks posters), and every add terminates at a named counterparty with live-checkable state. Sources that fail live-verifiability (Rover/Wag profiles, mystery-shop portals, TaskRabbit) stay honest evergreen "start here" entries, never dressed up as live rows.

## Files to touch

- `packages/kinds/kinds.json` — house rename/sub/hue, think order=1, de-rank speak/pitch, add bounty.
- `frontend/src/features/board/kind-copy.ts` — house de-gamble, lookafter pets-first, body de-scare line.
- `src/job_finder/tools/scrapers/carecom.py` — per-vertical pet quota (petcare already in `_KEPT_VERTICALS`).
- `@questboard/ui` KindStamp — house glyph off the casino motif; new bounty stamp.
- new `bounty` scraper file.

Relates to [[project_questboard_content_strategy_2026_07]] (prior "content feels weak" work, ICP), the payment constitution, and the B2B pilot (docs/b2b-pilot.md, 2026-10-12 decision).
