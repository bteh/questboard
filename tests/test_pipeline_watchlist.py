"""The pipeline must trust stored watchlist tokens.

Discovery (or a pasted careers link) stores the confirmed ats/slug on the
profile entry. Re-resolving names through the company catalog threw that
token away, so a company the catalog does not know (BILL -> billcom)
silently never reached its scraper.
"""

from __future__ import annotations

from job_finder.pipeline import watchlist_tokens_by_ats


def _no_catalog(names):
    """A catalog that knows nothing, like it does for BILL."""
    return [{"name": n, "ats": "unknown", "slug": ""} for n in names]


def test_stored_tokens_win_without_catalog_help():
    raw = [{"name": "BILL", "ats": "greenhouse", "slug": "billcom", "job_count": 50}]
    out = watchlist_tokens_by_ats(raw, resolve=_no_catalog)
    assert out == {"greenhouse": ["billcom"]}


def test_bare_names_still_resolve_through_the_catalog():
    def catalog(names):
        assert names == ["Anthropic"]
        return [{"name": "Anthropic", "ats": "greenhouse", "slug": "anthropic"}]

    out = watchlist_tokens_by_ats(["Anthropic"], resolve=catalog)
    assert out == {"greenhouse": ["anthropic"]}


def test_unknown_entries_fall_back_to_the_catalog():
    def catalog(names):
        return [{"name": n, "ats": "lever", "slug": "acme"} for n in names]

    raw = [{"name": "Acme", "ats": "unknown", "slug": ""}]
    out = watchlist_tokens_by_ats(raw, resolve=catalog)
    assert out == {"lever": ["acme"]}


def test_mixed_entries_and_no_duplicate_tokens():
    def catalog(names):
        return [{"name": n, "ats": "greenhouse", "slug": "billcom"} for n in names]

    raw = [
        {"name": "BILL", "ats": "greenhouse", "slug": "billcom"},
        "BILL Holdings",
    ]
    out = watchlist_tokens_by_ats(raw, resolve=catalog)
    assert out == {"greenhouse": ["billcom"]}
