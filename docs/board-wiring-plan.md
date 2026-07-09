# Wiring the board into the real app

Written 2026-07-09, after PR #54. The prototype (pinned-poster felt board + drawer shell, session
artifact 82469e4b) is the visual spec. `docs/board-ux-research.md` holds the requirements model and
trust signals; `docs/sidequest-research.md` holds the taxonomy. This file is the build plan.

## The goal (explicit, per Brian)

Modular and scalable above all. Adding a source is one file. Adding a category (kind) is one
registry entry per layer, with a documented contract. New code lands in feature folders; the design
system stays in packages. Nothing hardcodes the taxonomy as scattered string literals.

## Where the taxonomy lives: one registry, both languages

Today the category vocabulary exists as loose strings in three places: `vertical=` in the scraper
decorator, the `vertical` column values in SQLite, and `verticals` in `@questboard/ui` tokens.

The fix is `packages/kinds/kinds.json`: the single source of truth for the 10 kinds
(id, label, sub-line, hue, display order, legacy vertical aliases). A thin TS wrapper
(`packages/kinds/src/index.ts`) serves the frontend; a thin Python loader
(`src/job_finder/kinds.py`) serves the pipeline and backend; a pytest + vitest pair asserts both
loaders agree with the JSON, so the contract cannot drift silently.

Existing DB rows keep their current `vertical` values (career, camera, study, lens, party): the
registry maps legacy values to kinds at read time, so no migration and no scraper edits are needed.
New sources register with kind ids directly; `register_scraper` validates the id against the
registry so a typo fails at import, not in production.

Kind mapping for existing data: career→skill, lens→skill, camera→perform, study→think, party→party.
Kinds without sources yet (odd, deliver, body, lookafter, flip, house) exist in the registry but the
board only shows kinds with live supply plus Party; supply honesty, not empty shelves.

## How to add things (the contract, also going in docs/adding-a-source.md)

- **Add a source**: one decorated file in `src/job_finder/tools/scrapers/`, `kind="deliver"` in the
  decorator, done. Registry validates the kind. Restock picks it up automatically.
- **Add a kind**: one entry in `kinds.json` (id, label, sub, hue, order) + one stamp SVG in
  `@questboard/ui`. Board rail, filters, and summary endpoint pick it up from the registry.

## PR breakdown (each lands green, Brian merges)

1. **PR 1 · feat/kinds-registry**: `packages/kinds` (json + TS), Python loader + decorator
   validation + sync tests, `GET /api/v1/board/summary` (per-kind counts + new-today, legacy
   mapping applied), `docs/adding-a-source.md`.
2. **PR 2 · feat/shell-drawer**: the Mirjro-pattern shell: slim topbar (hamburger + quest mark +
   search), overlay drawer (scrim, Esc, profile card wired to the real workspace context, nav rows
   with live counts, pinned house-rules note, dawn foot). Hugeicons for all utility icons
   (@hugeicons/react + core-free-icons); hand-drawn stays for brand/stamps/pins.
3. **PR 3 · feat/board-felt**: the board route rebuilt as `features/board/`: felt surface,
   slot + upright pin, Poster component in `@questboard/ui`, two-line kind rail fed by the summary
   endpoint, filter chips, bring-lines (kind template + posting data), catch lines where the data
   is real (career repost/ghost signals exist end-to-end), first-seen dates, "new today".
4. **PR 4 · feat/board-polish**: mobile ticket-stub bottom bar, reduced-motion audit, Hugeicons
   sweep across remaining pages, `docs/architecture.md` (the features/ convention: routes stay
   thin, feature code in `src/features/<name>/`, cross-feature primitives in `@questboard/ui`),
   landing sync check (the landing hero reflects the real board per the standing rule).

## Directory conventions (adopted from PR 2 onward for new code)

```
frontend/src/
  features/          # feature modules: board/, shell/, log/ ... (components + hooks + model per feature)
  components/ui      # shadcn-style primitives only
  components/shared  # cross-feature bits until they graduate to @questboard/ui
  api/ hooks/ utils/ # thin, feature-agnostic
packages/
  kinds/             # the taxonomy registry (json + ts)
  ui/                # trade-paper design system (tokens, stamps, Poster, Chip, ...)
```

Existing folders migrate opportunistically (when touched), never in a big-bang rename PR.
