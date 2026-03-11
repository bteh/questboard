"""Lightweight web search for grounding LLM outputs with real-time data.

Uses DuckDuckGo (free, no API key) to fetch recent company info, funding
news, tech stack signals, and Glassdoor snippets. Results are formatted
as context blocks for injection into LLM prompts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    snippet: str
    url: str


@dataclass
class CompanyResearchContext:
    """Aggregated web search results for a single company."""

    company: str
    general: list[SearchResult] = field(default_factory=list)
    funding: list[SearchResult] = field(default_factory=list)
    engineering: list[SearchResult] = field(default_factory=list)
    reviews: list[SearchResult] = field(default_factory=list)

    def format_for_prompt(self, max_chars: int = 6000) -> str:
        """Format all results into a single context block for LLM injection."""
        sections: list[str] = []

        for label, results in [
            ("GENERAL", self.general),
            ("FUNDING & NEWS", self.funding),
            ("ENGINEERING & TECH", self.engineering),
            ("EMPLOYEE REVIEWS", self.reviews),
        ]:
            if not results:
                continue
            lines = [f"### {label}"]
            for r in results:
                lines.append(f"- [{r.title}]({r.url})")
                if r.snippet:
                    lines.append(f"  {r.snippet}")
            sections.append("\n".join(lines))

        text = "\n\n".join(sections)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n...(truncated)"
        return text

    @property
    def total_results(self) -> int:
        return len(self.general) + len(self.funding) + len(self.engineering) + len(self.reviews)


def _search(query: str, max_results: int = 5) -> list[SearchResult]:
    """Run a single DuckDuckGo text search. Returns empty list on failure."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        ddgs = DDGS()
        raw = list(ddgs.text(query, max_results=max_results))
        return [
            SearchResult(
                title=r.get("title", ""),
                snippet=r.get("body", ""),
                url=r.get("href", ""),
            )
            for r in raw
            if r.get("title")
        ]
    except ImportError:
        logger.debug("ddgs not installed — web search disabled (pip install ddgs)")
        return []
    except Exception as e:
        logger.warning("Web search failed for %r: %s", query, e)
        return []


def search_company(
    company_name: str, job_title: str = "", fast: bool = False,
) -> CompanyResearchContext:
    """Run targeted web searches to build a grounding context for company research.

    When ``fast=True``, runs only 2 queries (general + funding) instead of 4
    to reduce latency during batch enhancement. Sequential to avoid
    rate limiting from the search provider.
    """
    import time

    ctx = CompanyResearchContext(company=company_name)

    role_hint = f" {job_title}" if job_title else ""
    # Include "company" to disambiguate common names
    queries = [
        ("general", f'"{company_name}" company about{role_hint} site overview'),
        ("funding", f'"{company_name}" company funding raised investors valuation'),
    ]
    if not fast:
        queries += [
            ("engineering", f'"{company_name}" engineering blog tech stack infrastructure'),
            ("reviews", f'"{company_name}" company glassdoor reviews compensation culture'),
        ]

    for key, query in queries:
        results = _search(query, max_results=5)
        setattr(ctx, key, results)
        if results:
            time.sleep(0.15)  # brief polite delay

    logger.info(
        "Web search for %s: %d results across %d categories",
        company_name,
        ctx.total_results,
        sum(1 for r in [ctx.general, ctx.funding, ctx.engineering, ctx.reviews] if r),
    )
    return ctx
