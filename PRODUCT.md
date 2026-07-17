# Questboard product contract

_Decision updated: July 16, 2026_

## What Questboard is

Questboard is a local opportunity radar with two distinct workflows:

- **Find Work** finds fresh career opportunities, enforces hard constraints, and lets a user-owned agent compare the best candidates with the user's resume.
- **Side Quests** finds paid studies, freelance work, auditions, grants, events, bonuses, and other worthwhile opportunities from interests and practical constraints. A resume is not part of this workflow unless the user explicitly asks for it.

The desktop app owns discovery, source receipts, local data, filters, and workflow memory. Codex, Claude Code, or another MCP client can supply the optional reasoning. Questboard does not sell, fund, proxy, or meter AI tokens.

The website is the public front door for the story, download, documentation, source status, and eventually a limited public opportunity preview. It is not the primary personalized product.

## The promise

Find something worth pursuing while it is still fresh. Know where it came from, whether you can legally and practically do it, and why it does or does not fit.

For career work, the order is:

1. source validity and freshness;
2. location, remote scope, work authorization, compensation, and seniority constraints;
3. role-family retrieval;
4. requirement-by-requirement resume evidence from the user's agent;
5. a plain-language fit label and important unknowns.

Retrieval order is never presented as a resume-fit verdict. Unknown facts stay unknown.

## Why this is not JustHireMe

JustHireMe is a useful reference for local, deterministic job matching. Questboard must not compete by rebuilding the same resume-to-posting scorer with different colors.

Questboard's differentiated product is:

- **freshness radar:** first-seen timestamps, true source dates, source health, direct ATS monitoring, and an agent-triggered source refresh;
- **the full opportunity market:** Find Work and Side Quests live in one product but follow different matching rules;
- **agent-owned judgment:** the user's existing agent reads the resume, investigates finalists, and explains evidence without Questboard paying for inference;
- **eligibility honesty:** remote country scope, local jurisdiction, dates, stated pay, and source confidence are hard product fields, not prose afterthoughts;
- **receipts over aggregation:** every result has a local ID and stored source URL; direct application links are preferred and surfaced when they can be resolved;
- **outcome memory:** clip, apply, interview, complete, get paid, and learn from those outcomes without mass auto-apply.

Palmier Pro is the closer architecture reference: a local product exposes useful tools to the agent the user already has. Questboard applies that pattern to opportunity discovery rather than creative production. “Melius” is an interface reference only until the exact product is confirmed; it is not part of Questboard's competitive definition.

More detail: [Local agent product](docs/local-agent-product.md).

## Product boundaries

Questboard will:

- run locally without an account;
- work without AI for source discovery, filtering, browsing, and tracking;
- expose a local stdio MCP server to supported agents;
- ask before returning resume text to an agent;
- keep Side Quests resume-independent;
- prefer primary sources and preserve source uncertainty;
- let the user control every external application, message, purchase, or registration.

Questboard will not:

- offer hosted resume ranking in the first local-agent release;
- provide AI credits or silently use a founder-owned API key;
- claim that a deterministic retrieval score proves fit;
- auto-apply, send outreach, register, buy, or transact;
- let advertisers, employers, or affiliates buy ranking position;
- require payment before a user can run a useful first search.

## Business model

The free local core includes source browsing, filters, resume storage, MCP access, and workflow tracking. Paid value must fund convenience or durable infrastructure, not access to the user's own AI:

- signed desktop releases and automatic updates;
- premium source packs and higher-frequency local monitoring;
- advanced watches, digests, change alerts, and application memory;
- team or career-coach workflows;
- optional source utilities and clearly disclosed affiliate recommendations outside result ranking.

No ad, affiliate, listing fee, or commercial relationship may change organic ranking. Short job-search lifecycles make permanent user lock-in the wrong goal; Side Quests, ongoing opportunity watches, and reusable local workflow history are the honest reasons to return.

## Register

The app is a plainspoken field guide. The visual world is a trade paper: postal stamps, ledgers, postmarks, a masthead. It says less and shows receipts.

The landing page sells the outcome. The app does the work. Agent-facing tools use precise technical language because another system consumes them.

## Anti-references

- invented pay, post dates, fit percentages, or urgency;
- employer-paid placement and sponsored ranking;
- mass auto-apply;
- AI credits disguised as a product subscription;
- forced accounts and upgrade interruptions;
- gamification, streaks, XP, leaderboards, or confetti;
- generic AI copy and unexplained “magic” scores.

## Accessibility

Atkinson Hyperlegible Next for app UI. WCAG AA contrast. Keyboard reachable. Plain language for a non-technical reader. Reduced-motion users receive complete final states without animation.
