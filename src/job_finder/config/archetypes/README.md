# Profession archetypes

This directory holds **profession archetype presets**. Each YAML file is a
small delta on top of `../profiles/default.yaml` that adapts Launchboard for
a specific career family — healthcare, education, government, trades,
nonprofit, creative, finance, etc.

The motivation is the user-friendliness ask: a brand-new user (think: a
non-technical brother who just downloaded the app) shouldn't have to fight
tech-coded defaults to find a nursing job. The archetype picker on the
first-run wizard maps the user's profession to one of these presets, which
swaps:

- **Scoring weights** — `platform_building_score` doesn't matter for an
  ICU nurse but `culture_fit_score` does
- **Default keywords** — "patient acuity", "clinical workflow", "RN license"
  vs. "Kubernetes", "platform engineering"
- **Scraper allowlist** — disable CryptoJobsList and YC for healthcare,
  enable USAJobs for federal, etc.
- **Recommended target boards** — surface profession-specific job board
  suggestions in the search page

## Schema

Each archetype YAML has the following shape (every field is optional —
unspecified fields fall through to `default.yaml`):

```yaml
archetype:
  name: "Healthcare"
  description: "Nurses, doctors, therapists, allied health"
  emoji: "🏥"  # purely cosmetic, used for the picker UI

# Override scoring weights. Must sum to 1.0 if specified.
scoring:
  technical_skills: 0.20      # specialty certs, modalities
  leadership_signal: 0.10
  career_progression: 0.15
  platform_building: 0.05     # rare in healthcare
  comp_potential: 0.15
  company_trajectory: 0.10
  culture_fit: 0.25           # huge: shift type, ratios, work-life

# Profession-specific keyword expansion. These get added on top of the
# base keyword list, not replacing it — but they bias the scorer.
keywords:
  technical:
    - "RN license"
    - "BSN"
    - "ICU"
    - "Med-Surg"
  leadership:
    - "charge nurse"
    - "preceptor"
    - "clinical lead"

# Allowlist of scraper names from the registry. The CLI / UI uses this to
# decide which boards to query by default. Empty list means "all enabled
# scrapers" (same as default behavior).
enabled_scrapers:
  - indeed         # JobSpy
  - linkedin       # JobSpy
  - google         # JobSpy
  - themuse
  # NB: cryptojobslist, yc_workatastartup, builtin, hackernews, remoteok
  # are all disabled by omission

# Example role titles to seed the wizard's "Target roles" input.
target_roles:
  - "Registered Nurse"
  - "ICU Nurse"
  - "Nurse Practitioner"

# Sensible default comp targets per archetype. The user can edit them.
compensation:
  currency: "USD"
  pay_period: "annual"
  min_base: 65000
  target_total_comp: 95000
```

## Loading

The loader lives at `src/job_finder/profiles/archetypes.py`. Use it like:

```python
from job_finder.profiles.archetypes import list_archetypes, load_archetype

# Discover available archetypes
for arch in list_archetypes():
    print(arch.name, arch.description)

# Apply an archetype on top of a base profile
profile = load_archetype("healthcare")
```

## Adding a new archetype

1. Drop a `<slug>.yaml` file in this directory.
2. Make sure scoring weights sum to 1.0 if you override them.
3. Use scraper names from `src/job_finder/tools/scrapers/_registry.py`.
4. Run `make doctor` to confirm nothing broke.
5. Optional: add a test in `tests/test_archetypes.py`.

The wizard wiring (so the user actually picks an archetype on first run)
is a separate piece of work — see the next milestone. This directory just
provides the data structure so future UI work has stable presets to consume.
