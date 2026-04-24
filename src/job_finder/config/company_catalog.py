"""Curated company catalog for direct ATS career page scraping.

These companies are pre-configured with their ATS platform and career
page slug so Launchboard can scrape their career pages directly —
catching jobs that may not appear on Indeed or LinkedIn yet.

The catalog is organized by category and merged with the user's
AI-suggested target companies at search time. Users don't need to
know about ATS slugs — they just add "Anthropic" to their target
companies list and we match it to the right scraper automatically.

To add a company: add an entry with name, ats (greenhouse/lever/ashby/
workday), and slug (the identifier in their career page URL).
"""

from __future__ import annotations

COMPANY_CATALOG: list[dict[str, str]] = [
    # ── AI Labs & LLM Providers ──────────────────────────────────────
    {"name": "Anthropic", "ats": "greenhouse", "slug": "anthropic"},
    {"name": "Cohere", "ats": "ashby", "slug": "cohere"},
    {"name": "LangChain", "ats": "ashby", "slug": "langchain"},
    {"name": "Pinecone", "ats": "ashby", "slug": "pinecone"},
    {"name": "Mistral AI", "ats": "lever", "slug": "mistral"},
    {"name": "Perplexity", "ats": "ashby", "slug": "perplexity"},
    {"name": "Stability AI", "ats": "greenhouse", "slug": "stabilityai"},
    {"name": "Hugging Face", "ats": "workable", "slug": "huggingface"},
    {"name": "Weights & Biases", "ats": "lever", "slug": "wandb"},
    {"name": "Arize AI", "ats": "greenhouse", "slug": "arizeai"},
    {"name": "Black Forest Labs", "ats": "greenhouse", "slug": "blackforestlabs"},

    # ── Voice AI & Conversational AI ─────────────────────────────────
    {"name": "ElevenLabs", "ats": "ashby", "slug": "elevenlabs"},
    {"name": "Deepgram", "ats": "ashby", "slug": "deepgram"},
    {"name": "Vapi", "ats": "ashby", "slug": "vapi"},
    {"name": "Bland AI", "ats": "ashby", "slug": "bland"},
    {"name": "Hume AI", "ats": "greenhouse", "slug": "humeai"},
    {"name": "PolyAI", "ats": "greenhouse", "slug": "polyai"},
    {"name": "Parloa", "ats": "greenhouse", "slug": "parloa"},
    {"name": "Speechmatics", "ats": "greenhouse", "slug": "speechmatics"},

    # ── AI Platforms & Developer Tools ───────────────────────────────
    {"name": "Vercel", "ats": "greenhouse", "slug": "vercel"},
    {"name": "Supabase", "ats": "ashby", "slug": "supabase"},
    {"name": "Clerk", "ats": "ashby", "slug": "clerk"},
    {"name": "WorkOS", "ats": "ashby", "slug": "workos"},
    {"name": "Inngest", "ats": "ashby", "slug": "inngest"},
    {"name": "Resend", "ats": "ashby", "slug": "resend"},
    {"name": "PlanetScale", "ats": "greenhouse", "slug": "planetscale"},
    {"name": "Temporal", "ats": "greenhouse", "slug": "temporal"},
    {"name": "Hightouch", "ats": "greenhouse", "slug": "hightouch"},
    {"name": "Clay Labs", "ats": "ashby", "slug": "claylabs"},
    {"name": "Runway", "ats": "greenhouse", "slug": "runwayml"},
    {"name": "Glean", "ats": "greenhouse", "slug": "gleanwork"},
    {"name": "RunPod", "ats": "greenhouse", "slug": "runpod"},
    {"name": "Airtable", "ats": "greenhouse", "slug": "airtable"},

    # ── Automation ───────────────────────────────────────────────────
    {"name": "n8n", "ats": "ashby", "slug": "n8n"},
    {"name": "Zapier", "ats": "ashby", "slug": "zapier"},
    {"name": "Lindy", "ats": "ashby", "slug": "lindy"},

    # ── Contact Center & CX ──────────────────────────────────────────
    {"name": "Ada", "ats": "greenhouse", "slug": "ada"},
    {"name": "Sierra", "ats": "ashby", "slug": "sierra"},
    {"name": "Decagon", "ats": "ashby", "slug": "decagon"},
    {"name": "Intercom", "ats": "greenhouse", "slug": "intercom"},

    # ── Enterprise & SaaS ────────────────────────────────────────────
    {"name": "Palantir", "ats": "lever", "slug": "palantir"},
    {"name": "Spotify", "ats": "lever", "slug": "spotify"},
    {"name": "Attio", "ats": "ashby", "slug": "attio"},

    # ── Fintech ──────────────────────────────────────────────────────
    {"name": "N26", "ats": "greenhouse", "slug": "n26"},
    {"name": "Trade Republic", "ats": "greenhouse", "slug": "traderepublicbank"},
    {"name": "SumUp", "ats": "greenhouse", "slug": "sumup"},
    {"name": "Qonto", "ats": "lever", "slug": "qonto"},

    # ── European Tech ────────────────────────────────────────────────
    {"name": "Factorial", "ats": "greenhouse", "slug": "factorial"},
    {"name": "Tinybird", "ats": "ashby", "slug": "tinybird"},
    {"name": "Clarity AI", "ats": "lever", "slug": "clarity-ai"},
    {"name": "DeepL", "ats": "ashby", "slug": "DeepL"},
    {"name": "Aleph Alpha", "ats": "ashby", "slug": "AlephAlpha"},
    {"name": "Celonis", "ats": "greenhouse", "slug": "celonis"},
    {"name": "Contentful", "ats": "greenhouse", "slug": "contentful"},
    {"name": "GetYourGuide", "ats": "greenhouse", "slug": "getyourguide"},
    {"name": "HelloFresh", "ats": "greenhouse", "slug": "hellofresh"},
    {"name": "Helsing", "ats": "greenhouse", "slug": "helsing"},
    {"name": "Forto", "ats": "lever", "slug": "forto"},
    {"name": "Vinted", "ats": "lever", "slug": "vinted"},
    {"name": "Pigment", "ats": "lever", "slug": "pigment"},
    {"name": "Lovable", "ats": "ashby", "slug": "lovable"},

    # ── UK & Frontier AI ─────────────────────────────────────────────
    {"name": "Wayve", "ats": "greenhouse", "slug": "wayve"},
    {"name": "Isomorphic Labs", "ats": "greenhouse", "slug": "isomorphiclabs"},
    {"name": "Synthesia", "ats": "ashby", "slug": "synthesia"},
    {"name": "Faculty", "ats": "ashby", "slug": "faculty"},
    {"name": "Photoroom", "ats": "ashby", "slug": "photoroom"},

    # ── Biotech / Health ─────────────────────────────────────────────
    {"name": "Lakera", "ats": "ashby", "slug": "lakera.ai"},
    {"name": "Scandit", "ats": "greenhouse", "slug": "scandit"},
    {"name": "Cradle", "ats": "ashby", "slug": "cradlebio"},
    {"name": "Causaly", "ats": "ashby", "slug": "causaly"},

    # ── Data & Analytics ─────────────────────────────────────────────
    {"name": "Amplemarket", "ats": "greenhouse", "slug": "amplemarket"},
]


# Fast lookup by normalized name
_CATALOG_BY_NAME: dict[str, dict[str, str]] = {}


def _normalize(name: str) -> str:
    return name.lower().strip().replace(" ", "").replace("-", "").replace(".", "")


def _build_index() -> None:
    if _CATALOG_BY_NAME:
        return
    for entry in COMPANY_CATALOG:
        key = _normalize(entry["name"])
        _CATALOG_BY_NAME[key] = entry


def lookup_company(name: str) -> dict[str, str] | None:
    """Look up a company by name and return its ATS config.

    Returns {"name": ..., "ats": ..., "slug": ...} or None.
    Fuzzy-matches on normalized name (case-insensitive, no spaces/dashes).
    """
    _build_index()
    key = _normalize(name)
    if key in _CATALOG_BY_NAME:
        return _CATALOG_BY_NAME[key]
    # Partial match — "Anthropic" matches "Anthropic AI"
    for catalog_key, entry in _CATALOG_BY_NAME.items():
        if key in catalog_key or catalog_key in key:
            return entry
    return None


def resolve_watchlist(company_names: list[str]) -> list[dict[str, str]]:
    """Convert a list of company names into watchlist entries with ATS info.

    Companies found in the catalog get their ATS + slug resolved automatically.
    Unknown companies are returned with ats="unknown" so they're still tracked
    but won't be scraped (they'll show up in aggregator results instead).
    """
    _build_index()
    entries = []
    seen: set[str] = set()
    for name in company_names:
        key = _normalize(name)
        if key in seen:
            continue
        seen.add(key)
        match = lookup_company(name)
        if match:
            entries.append({
                "name": match["name"],
                "ats": match["ats"],
                "slug": match["slug"],
            })
        else:
            entries.append({
                "name": name,
                "ats": "unknown",
                "slug": "",
            })
    return entries
