# Architecture conventions

Written 2026-07-09, at the end of the board wiring (PRs #55-#58). Local-agent boundary updated
2026-07-16. This is the map of where code
goes and why; `docs/board-wiring-plan.md` holds the build history, `docs/adding-a-source.md` the
growth contract.

## The one rule

Adding a source is one file; adding a kind is one registry entry plus a stamp. Anything that makes
those operations touch more places is a regression. The registry (`packages/kinds/kinds.json`) is
the single source of truth for the taxonomy; both languages load it and sync tests pin it.

## Layout

```
packages/
  kinds/                 # the taxonomy registry: kinds.json + TS wrapper (+ vitest sync test)
  ui/                    # @questboard/ui, the trade-paper design system
    src/tokens.*         # colors, fonts, radii (CSS custom properties + TS mirror)
    src/components/      # Poster, KindStamp, QuestCard, Chip, Sheet, ... one file each
    src/components.css   # the design system's one stylesheet

frontend/src/
  features/              # feature modules; new UI work starts here
    shell/               # topbar + drawer (+ its css + drawer-contract tests)
    board/               # kind rail, kind params, poster model, kind copy, felt css (+ tests)
  components/            # legacy home for pre-convention code; migrate on touch, never big-bang
    ui/                  # shadcn-style primitives only
    shared/              # cross-feature bits until they graduate to @questboard/ui
  routes/                # TanStack Router pages; routes stay THIN (data wiring + composition)
  api/                   # one module per backend resource, typed, all through lib/api-client
  hooks/                 # useQuery/useMutation wrappers over api/
  utils/ lib/ types/     # feature-agnostic helpers

backend/app/
  local_mcp.py           # local stdio MCP transport, no hosted auth or model calls
  api/                   # one router per resource (board.py, applications.py, ...)
  schemas/               # pydantic shapes, one module per resource
  services/              # business logic shared across REST and MCP

src/job_finder/
  kinds.py               # Python side of the registry (loads packages/kinds/kinds.json)
  tools/scrapers/        # one decorated file per source; _registry.py validates kinds
```

## Rules of thumb

- **Routes stay thin.** A route file wires data and composes feature components; presentation and
  models live in `features/<name>/`.
- **Design system vs feature CSS.** A visual that any surface may reuse (poster, stamp, chip)
  lives in `@questboard/ui`. Page furniture (the felt, the rail grid) lives in the feature's css.
- **Icons.** Utility icons come from Hugeicons (`@hugeicons/react` + core-free-icons) at
  strokeWidth 1.7. Brand-specific marks stay hand-drawn: the quest mark, kind stamps, pushpins,
  the horizon art. If an icon carries meaning only Questboard has, draw it; otherwise import it.
- **Vocabulary lives in the registry.** Never write a vertical/kind string list in code again;
  derive from `@questboard/kinds` / `job_finder.kinds` (APPLICATION_VERTICALS already does).
- **Honesty is structural.** Pay renders only as stated; bring lines come from the requirements
  model (`docs/board-ux-research.md`); descriptions are the posting's own text or nothing;
  screen-outs never mark the log. Copy that promises anything else fails review.
- **Motion.** Every animation carries a `prefers-reduced-motion` fallback. Depth inside the app
  is a border; true shadows belong to the felt world (posters, drawer) and the landing.
- **The landing mirrors the product.** The landing hero renders real components with real board
  data (the standing sync rule); when the board's look changes, the landing follows in the same
  PR series.
- **Row pools (hosted).** Quest rows live in ONE shared pool (workspace_id NULL) that the
  scheduler sweeps; every visitor's board reads it. Career rows stay per-workspace. Touching a
  shared quest row clones it into your workspace first (clone-on-touch), so your log is yours
  and the shared row stays pristine; reads hide the original behind your copy (job_url dedupe).
  URL uniqueness is per pool, never global. The visibility contract is
  `backend/app/services/row_scope.py`; reads declare `scope=board` (the felt) or `scope=mine`
  (the log). Local/desktop own one NULL pool, where both scopes are identical.
- **MCP stays thin.** Put search, serialization, profile selection, and state behavior in
  `services/local_agent_service.py`; MCP decorators adapt those functions to stdio. Tools never
  construct an LLM. The client owns reasoning and model cost.
- **Retrieval is not fit.** Deterministic rank fields may retrieve candidates but cannot be named
  or displayed as resume confidence. Fit requires requirement evidence from the connected agent.
- **Work and Side Quests are separate contracts.** Work may use a resume after consent. Side
  Quests use goals and constraints and never require a resume.
