All source material verified. Key code-level facts checked before synthesis: the mock's `data-enter` handler goes to the home page (mock line 1650), the mock's mobile bar is Home / The board / Your log with no Settings, the current board route is a `position: fixed` overlay with a "Back to the app" link, the CSV export exists only as a backend endpoint (`/api/v1/applications/export/csv`) with no frontend button today, and `questboard:first-run-pending` already establishes a localStorage key convention. Willow confirmed as brochure-with-no-way-back-in; Perena's app URL loads the product directly.

SYNTHESIS: QUESTBOARD IA, THE BUILD BRIEF

WHAT WAS DECIDED AND WHY

Stolen from capability-guardian: the entry switch at / (landing for strangers, app for returners), /welcome as the stable marketing URL, first CTA landing on /board, the auth gate (hosted mode only) wrapping the app layout and never the landing, /log children for ledger and figures, avatar rendered only in hosted mode.

Stolen from returning-user: board filter state serialized to URL params and persisted locally so Tuesday's board is already set up, the Perena-style rule that the pitch never replays for a known user, the restock doors (masthead line, stale states, Settings), the one-number-two-doors treatment of the salary floor.

Stolen from first-impression: the adaptive CTA on the landing for entered users ("Back to the board"), the 404 in voice, the strict reading of the approved mock as the shell spec, the career kit row as the contextual resume ask.

Rejected, with reasons:
- first-impression's landing-always-at-root. It taxes every habitual visit and its own weakness list concedes the point. The landing is a pitch surface; a subscriber's front page is the masthead, not the pitch.
- returning-user's fold of home into the board. The owner approved home and board as two pages (brand button goes home, "See the full board" links out). The fold also overloads the board header. Home survives as the returning user's front page.
- capability-guardian's /board/restock Sheet and separate /restocks history page. SearchConfigForm (roles, keywords, places, strictness, mode, sources) does not fit a sheet; guardian conceded this. Restock is a full quiet page and the run report lives on it, not on a fourth surface.
- returning-user's /log?view=ledger query param. A path child (/log/ledger) is a clearer document boundary and behaves better with phone back buttons.
- first-impression's split of the analytics charts across two pages. All four charts stay together at /log/numbers; the per-run filter funnel is a different artifact and already lives in SearchRunView on /restock.
- All three proposals' claim that a CSV export button survives. There is no such button today; only the endpoint exists. The new ledger adds one (net-new UI, satisfies zero capability loss at the API level).

Design-guidance folded in: from huashu-design, answer-before-ask as the first-run spine, honest placeholders over fake data (no invented counts, flaps read live totals), show the shell early in the build order, no filler stats. From gpt-taste, the one-or-two-line hero rule (the approved hero is one line, keep it that way at all breakpoints) and the meta-label ban (no "SECTION 01" grammar anywhere). Rejected from gpt-taste: GSAP scroll pinning, scrubbing reveals, and hover physics. DESIGN.md's motion budget (three deliberate motions per page, hovers darken only) wins outright.

1. ROUTE TABLE

| Path | Renders | Register | Auth |
|---|---|---|---|
| / | Entry switch. No entered flag: the approved landing, full bleed, no app chrome. Flag present: beforeLoad redirect to /home, no flash. | brand (first visit) | none |
| /welcome | The landing, always, same component. Never sets the flag on mount. CTA label flips to "Back to the board" when the flag exists. | brand | none |
| /home | The masthead home from the mock: lede with live totals, flap row (posted last 24 hours, closes this week), "Start here" line, Today's bounty, New on the board rows, credo line, log strip. | product, shell | hosted gate only |
| /board | The live board, promoted into the shell. Current board.tsx minus the fixed-overlay hack and the "Back to the app" link. Chips with true counts, presets, search box, pay from/to, sort, kit rows, requirement sheet, explain sheet, Clip. Filter state mirrors to search params (?v, ?q, ?from, ?to, preset keys); params beat saved state; last state persists at questboard:board.v1. | product, shell | hosted gate only |
| /restock | Old Search whole: SearchConfigForm, SearchRunView, per-run filter funnel, saved-defaults actions. Reskinned trade paper. Not in the sidebar. | product, shell | hosted gate only |
| /log | Your log from the mock: composer ("Add your own quest"), clipped and applied cards with status editing, Done block with paid-out total, the optional email row. Chapter tail: two headline numbers and a TextLink "See the charts" to /log/numbers, plus a TextLink "The full ledger" to /log/ledger. | product, shell | hosted gate only |
| /log/ledger | Old Applications whole: JobTable, filter chips, scope toggle (new / latest / all), status editing, pagination, purge, URL check, detail sheet. Adds a "Download CSV" button in the header hitting /api/v1/applications/export/csv. Header links back to Your log. | product, shell | hosted gate only |
| /log/numbers | Old Analytics whole: KPI row and the four charts (score distribution, recommendations, pipeline funnel, sources), reskinned in ink and sage. Title "Your numbers". | product, shell | hosted gate only |
| /settings | Tabs via ?tab=: Resume, Restock (was Search), AI, Auto-apply. ?tab=search maps to restock. Footer TextLink "See the front page" to /welcome. | product, shell | hosted gate only |
| /design | Component sheet, kept, gated behind import.meta.env.DEV, bare (no shell). | internal | none |
| /search | Permanent redirect to /restock. | n/a | n/a |
| /applications | Permanent redirect to /log/ledger, run and scope params carried. | n/a | n/a |
| /analytics | Permanent redirect to /log/numbers. | n/a | n/a |
| * (404) | "That page is not on the board." One TextLink "Go to the board". | brand voice, bare | none |

Register mechanics: __root.tsx shrinks to providers plus Outlet (QueryClient, Workspace, Profile, Search contexts stay). A pathless layout route (id 'app') owns the trade-paper shell and parents home, board, restock, log, log/ledger, log/numbers, settings. The hosted-mode auth check moves onto this layout; HostedAuthScreen renders only there, only when hostedMode is on. Landing, welcome, design, 404, and the three redirects register directly under root. The shadcn Sidebar, FirstRunHero, ReadyToLaunchHero, MobileHeader, and the overlay hacks die.

2. ENTRY LOGIC

Flag: localStorage key questboard:entered, value '1' (follows the existing questboard:first-run-pending convention). All reads and writes in try/catch as search.tsx already does.

First visit: / renders the landing. Flaps and the three pinned cards come from the same live queries the board chips use (page_size 1 totals; never hardcoded). Clip works on the landing cards and writes through the normal clip mutation. Any "Open the board" click sets the flag and navigates to /board.

Returning visit: the index route's beforeLoad reads the flag synchronously and throws a redirect to /home before first paint. Home is built for returners: the flap counters are a what-changed surface and the log strip only means something once you have activity.

Flag hygiene: the app layout's beforeLoad also sets the flag, so a deep link to /board or /log on a phone counts as having entered and / never bounces that person through marketing again.

Brand link in the app: the sidebar brand tile navigates to /home, exactly as the mock wires it. The landing brand mark is inert.

/welcome: always renders the landing, linked from the Settings footer ("See the front page"). Private window or cleared storage: the person sees the landing once and is one click back in. When hosted mode ships, the flag check gains a session check on the app layout only; the landing never requires a session. The landing CTA is entry, not auth.

3. SHELL SPEC

Desktop sidebar, exactly the approved mock, in order: brand tile plus wordmark (to /home), The board (/board), Your log (/log), Alerts (disabled, "soon" tag), Settings (/settings). Bottom side-note: "Every listing links straight to the source, with pay shown when the listing states it."

Topbar: "Search the board" input; typing submits to /board?q=. Avatar disc renders only in hosted mode with a session; local-first shows nothing there because there is no account to represent.

Mobile bar (phone-web, under 880px): the mock's three mtabs, Home, The board, Your log, plus a small gear at the right end for Settings. The gear is the one extension to the mock, flagged as such. Browsing, filtering, clipping, and the explain sheet are first-class on the phone; restock and the ledger work there but are laptop-shaped, matching the discover-on-phone complete-on-laptop split in PRODUCT.md.

The board page hosts: the board head (title, live count, sort toggle), the restock line under the head ("Restocked {date}. Restock", or "Restocking, {n} of {m} sources in." during a run, or "Nothing new this week. Restock the board." when stale), vertical chips, preset chips, the search box and pay from/to inputs, the per-vertical kit row (career kit carries the resume ask with an inline file input), the first-run notice line, and the card grid with the "more" pager. Restock is a verb on this page, not a nav item; the machinery stays invisible.

4. OLD-SURFACE MAP

- Dashboard (routes/index.tsx): dies as a page. Its metric tiles become the home log strip; "Top matches" becomes the board's best-score sort; "Recent activity" becomes New on the board rows on /home. FirstRunHero and ReadyToLaunchHero die; the stocked board is the first run. The guided wizard stays reachable via Settings, Resume ("Restart onboarding"), which already exists.
- Search (routes/search.tsx): becomes /restock, all components intact. Doors: the board restock line, board stale and empty states, Settings, Restock tab. When a run finishes, the primary action is "Back to the board". /search redirects.
- Applications (routes/applications.tsx): survives whole at /log/ledger, restyled to ledger grammar (mono tabular numbers, hairlines, applied stamps). Both cards and table views kept in the first pass to avoid capability loss. Gains the Download CSV button (see the caught gap above). /applications redirects with params.
- Analytics (routes/analytics.tsx): survives whole at /log/numbers. /analytics redirects.
- Settings (routes/settings.tsx): stays at /settings, same four tabs with Search renamed Restock, reskinned. The AI tab keeps TheAiDownload and the Remove button; the word AI appears there and nowhere else.
- Resume upload: canonical home Settings, Resume. Contextual entry is the career kit row on the board: with a resume, "Resume on file, updated {date}. Career quests show how much of it you already cover." with Update; without one, "Add a resume and career quests show how much of them you already cover." with an inline Add link. Career cards render fully either way; fit lines appear only once a resume exists.
- Salary controls: browse-time pay from/to inputs stay on the board ("Only counts pay the posting states; jobs with no stated pay stay on the board."). The pipeline floor (min_base) and match strictness live on the /restock form and in Settings, Restock. Same stored value, two doors.
- Fit reports and requirement sheets: on the board card sheet and on the ledger row detail. Same component, two doors.

5. FIRST-RUN, BEAT BY BEAT, FIRST 60 SECONDS

- 0 to 3s: landing paints. "One board for every side quest." Sub: "Real quests from real sources, with pay shown when the source states it." The flap row ticks once to the live totals (592 on the board, N pay $500 or more). CTA visible without scrolling: "Open the board", note "Free. Your log lives in your browser." Nothing asked.
- 3 to 14s: scroll. The engraved horizon closes the hero; three real cards from today's board sit pinned on it, mixed verticals, stated pay, true post dates. Clip works right here. Then the centered statement, the 2x2 grid (true post date, the Done ledger, counting chips, the plain-words demo with its one price line), the stamp strip.
- 15s: "Open the board." Flag set, land on /board. Zero questions asked.
- 15 to 25s: the board paints with live chips and counts. A dismissible notice line: "Never done any of this? Most quests here need nothing you don't already have. Start here" (Start here activates the no-experience preset once its API param exists; the notice ships without the link until then, see phase 6). Restock line reads "Restocked {date}."
- 25 to 45s: they tap Career. The kit row makes the one soft ask (add a resume, get the covers-x-of-y line). They ignore it, open a card, read the explain sheet, follow the source link. The board never traps.
- 45 to 60s: they Clip. The postmark presses, the stamp reads "Clipped, {date}". Your log now holds the clip, the composer, and later the one optional email row: "Your log lives in this browser. Add an email if you want it to survive a lost laptop." At no point in the first minute does the app request a resume, an email, an account, or a setting.
- Visit two: typing the root URL lands on /home. The masthead lede reads the day's true numbers, the flaps run once, Today's bounty and New on the board are one glance, the full board is one click.

6. BUILD PHASES

- PR 1, shell split: __root.tsx to providers plus Outlet; pathless app layout with the trade-paper sidebar, topbar, mobile bar from @questboard/ui; board moves inside the shell (delete the fixed overlay and "Back to the app"); design route goes bare and DEV-gated; hosted auth check moves to the layout. Old pages render inside the new shell untouched for now. Risk: medium. Big mechanical diff across every route; behavior should not change.
- PR 2, landing and entry: landing component ported from the mock (live totals, three real cards, working Clip), / entry switch, /welcome, questboard:entered flag, CTA to /board, 404 page. Risk: medium. Mostly new UI on existing primitives (SplitFlap, QuestCard, StampDefs).
- PR 3, home: masthead page with live lede numbers, flap counters, Today's bounty, New on the board rows, log strip; brand tile to /home; returning redirect goes live. Risk: medium. The posted-last-24h and closes-this-week counts likely need one small backend addition; if closes-this-week has no honest data source for career rows, the second flap group shows a count only for quest verticals that carry close dates. No invented numbers.
- PR 4, the log trio: /log (composer, clips, Done block, email row), /log/ledger (move Applications, reskin, add Download CSV), /log/numbers (move Analytics, reskin), redirects for /applications and /analytics. Risk: high. The composer and Done ledger need a personal-quest store that does not exist yet (local-first table); log and ledger must share the same query cache so a status edit in one reflects in the other instantly.
- PR 5, restock and settings: move Search to /restock, reskin, wire the board restock line and stale states, redirect /search; Settings retab (Restock), reskin, add the front-page link. Risk: low to medium. Components move whole.
- PR 6, polish: board state in URL params plus questboard:board.v1 persistence, topbar search submit, first-run notice line with the no-experience preset param (backend field required; ship the notice linkless if the param slips), phone-web pass on landing, board, and log. Risk: low, except the noexp param which is a small backend change.

7. OPEN QUESTIONS

1. First-entry CTA target. The approved mock wires "Open the board" to the home masthead; this spec sends first entry to /board and reserves home for return visits, because the CTA promises the board and the landing already spent the masthead moment. Option A: /board (spec default, one deviation from mock wiring, flagged). Option B: /home (mock-faithful, accepts the two-mastheads-in-forty-seconds repetition).
2. The ledger's cards view. Old Applications has both card and table views of the same records. Option A: keep both at /log/ledger for zero loss now, retire the cards view later if unused. Option B: table only from day one, since cards already live on the board and in Your log (smaller page, one less thing to reskin).
