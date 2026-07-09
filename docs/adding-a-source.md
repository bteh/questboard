# Adding a source, adding a kind

The two growth paths are deliberately one-change operations. If either ever needs edits in more
than the places listed here, that's a regression against the modularity goal; fix the structure,
not the checklist.

## Adding a source (a new scraper)

One decorated file in `src/job_finder/tools/scrapers/`:

```python
from job_finder.tools.scrapers._registry import register_scraper


@register_scraper(
    name="roadie",
    display_name="Roadie",
    url="https://www.roadie.com",
    description="Package delivery gigs along routes you already drive",
    kind="deliver",          # canonical kind id from packages/kinds/kinds.json
)
def search(config: dict, progress=None) -> list[dict]:
    ...
```

That's it. The package auto-discovers the module on import, restock picks it up, and the board
counts it under its kind. The decorator validates `kind` against the registry, so a typo fails at
import time (there's a test asserting every registered scraper sits in a known lane).

Rules that keep the board honest:
- Only emit pay the source states. No guessing, no ranges invented from titles.
- Emit the truest post date you can find; freshness signals depend on it.
- Existing sources use the older `vertical=` spelling (career/camera/study/lens/party); both work.
  New sources should use `kind=`.
- Respect each site's terms. Never scrape Prolific (they ban automation). On Cloudflare blocks,
  try playwright-stealth or crawl4ai before giving up.

## Adding a kind (a new category)

Two changes:
1. **`packages/kinds/kinds.json`**: add an entry (id, label, sub, hue, order, `legacy_verticals: []`).
   Both the TypeScript wrapper and the Python loader read this file; sync tests on both sides pin it.
2. **A stamp in `@questboard/ui`**: the hand-drawn postmark icon for the kind (match the 1.7 stroke).

The board rail, filters, and `/api/v1/board/summary` pick the new kind up from the registry. New
sources can then register with the new kind id immediately.

## Where things live

- `packages/kinds/kinds.json`: the taxonomy, single source of truth.
- `packages/kinds/src/index.ts`: TS access (`KINDS`, `kindForVertical`, `verticalValuesFor`).
- `src/job_finder/kinds.py`: Python access (same shapes, same names in snake_case).
- `src/job_finder/tools/scrapers/`: one file per source, `_registry.py` is the contract.
- `backend/app/api/board.py`: the summary endpoint the board rail reads.
- Taxonomy rationale: `docs/sidequest-research.md`. Requirements per kind: `docs/board-ux-research.md`.
