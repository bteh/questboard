"""Backend-backed location suggestion service with Pelias and local fallback."""

from __future__ import annotations

import time
from typing import Any

import requests

from app.config import get_settings
from app.schemas.workspace import LocationSuggestion

_CACHE: dict[str, tuple[float, list[LocationSuggestion]]] = {}

_LOCAL_PLACES: list[dict[str, Any]] = [
    {"label": "United States", "kind": "country", "country": "United States", "country_code": "US"},
    {"label": "Canada", "kind": "country", "country": "Canada", "country_code": "CA"},
    {"label": "United Kingdom", "kind": "country", "country": "United Kingdom", "country_code": "GB"},
    {"label": "Germany", "kind": "country", "country": "Germany", "country_code": "DE"},
    {"label": "France", "kind": "country", "country": "France", "country_code": "FR"},
    {"label": "India", "kind": "country", "country": "India", "country_code": "IN"},
    {"label": "Japan", "kind": "country", "country": "Japan", "country_code": "JP"},
    {"label": "Singapore", "kind": "country", "country": "Singapore", "country_code": "SG"},
    {"label": "Australia", "kind": "country", "country": "Australia", "country_code": "AU"},
    {"label": "Brazil", "kind": "country", "country": "Brazil", "country_code": "BR"},
    {"label": "Mexico", "kind": "country", "country": "Mexico", "country_code": "MX"},
    {"label": "South Africa", "kind": "country", "country": "South Africa", "country_code": "ZA"},
    {"label": "California, United States", "kind": "region", "region": "California", "country": "United States", "country_code": "US"},
    {"label": "New York, United States", "kind": "region", "region": "New York", "country": "United States", "country_code": "US"},
    {"label": "Ontario, Canada", "kind": "region", "region": "Ontario", "country": "Canada", "country_code": "CA"},
    {"label": "Bavaria, Germany", "kind": "region", "region": "Bavaria", "country": "Germany", "country_code": "DE"},
    {"label": "England, United Kingdom", "kind": "region", "region": "England", "country": "United Kingdom", "country_code": "GB"},
    {"label": "New South Wales, Australia", "kind": "region", "region": "New South Wales", "country": "Australia", "country_code": "AU"},
    {"label": "San Francisco, CA, United States", "kind": "city", "city": "San Francisco", "region": "CA", "country": "United States", "country_code": "US", "lat": 37.7749, "lon": -122.4194},
    {"label": "New York, NY, United States", "kind": "city", "city": "New York", "region": "NY", "country": "United States", "country_code": "US", "lat": 40.7128, "lon": -74.0060},
    {"label": "Seattle, WA, United States", "kind": "city", "city": "Seattle", "region": "WA", "country": "United States", "country_code": "US", "lat": 47.6062, "lon": -122.3321},
    {"label": "Austin, TX, United States", "kind": "city", "city": "Austin", "region": "TX", "country": "United States", "country_code": "US", "lat": 30.2672, "lon": -97.7431},
    {"label": "Toronto, ON, Canada", "kind": "city", "city": "Toronto", "region": "ON", "country": "Canada", "country_code": "CA", "lat": 43.6532, "lon": -79.3832},
    {"label": "Vancouver, BC, Canada", "kind": "city", "city": "Vancouver", "region": "BC", "country": "Canada", "country_code": "CA", "lat": 49.2827, "lon": -123.1207},
    {"label": "London, England, United Kingdom", "kind": "city", "city": "London", "region": "England", "country": "United Kingdom", "country_code": "GB", "lat": 51.5072, "lon": -0.1276},
    {"label": "Berlin, Germany", "kind": "city", "city": "Berlin", "region": "Berlin", "country": "Germany", "country_code": "DE", "lat": 52.52, "lon": 13.405},
    {"label": "Munich, Bavaria, Germany", "kind": "city", "city": "Munich", "region": "Bavaria", "country": "Germany", "country_code": "DE", "lat": 48.1351, "lon": 11.5820},
    {"label": "Paris, France", "kind": "city", "city": "Paris", "region": "Ile-de-France", "country": "France", "country_code": "FR", "lat": 48.8566, "lon": 2.3522},
    {"label": "Bengaluru, Karnataka, India", "kind": "city", "city": "Bengaluru", "region": "Karnataka", "country": "India", "country_code": "IN", "lat": 12.9716, "lon": 77.5946},
    {"label": "Hyderabad, Telangana, India", "kind": "city", "city": "Hyderabad", "region": "Telangana", "country": "India", "country_code": "IN", "lat": 17.3850, "lon": 78.4867},
    {"label": "Singapore, Singapore", "kind": "city", "city": "Singapore", "region": "Singapore", "country": "Singapore", "country_code": "SG", "lat": 1.3521, "lon": 103.8198},
    {"label": "Sydney, New South Wales, Australia", "kind": "city", "city": "Sydney", "region": "New South Wales", "country": "Australia", "country_code": "AU", "lat": -33.8688, "lon": 151.2093},
    {"label": "Melbourne, Victoria, Australia", "kind": "city", "city": "Melbourne", "region": "Victoria", "country": "Australia", "country_code": "AU", "lat": -37.8136, "lon": 144.9631},
    {"label": "Sao Paulo, Brazil", "kind": "city", "city": "Sao Paulo", "region": "Sao Paulo", "country": "Brazil", "country_code": "BR", "lat": -23.5558, "lon": -46.6396},
    {"label": "Mexico City, Mexico", "kind": "city", "city": "Mexico City", "region": "Mexico City", "country": "Mexico", "country_code": "MX", "lat": 19.4326, "lon": -99.1332},
    {"label": "Cape Town, South Africa", "kind": "city", "city": "Cape Town", "region": "Western Cape", "country": "South Africa", "country_code": "ZA", "lat": -33.9249, "lon": 18.4241},
]


def _normalize(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def _subtitle(item: dict[str, Any]) -> str:
    if item["kind"] == "country":
        return "Country"
    if item["kind"] == "region":
        return f"Region in {item.get('country') or ''}".strip()
    parts = [item.get("region") or "", item.get("country") or ""]
    return " · ".join([part for part in parts if part])


def _to_suggestion(item: dict[str, Any], provider: str) -> LocationSuggestion:
    return LocationSuggestion(
        label=item["label"],
        kind=item.get("kind", "manual"),
        subtitle=_subtitle(item),
        city=item.get("city", "") or "",
        region=item.get("region", "") or "",
        country=item.get("country", "") or "",
        country_code=item.get("country_code", "") or "",
        lat=item.get("lat"),
        lon=item.get("lon"),
        provider=provider,
        provider_id=item.get("provider_id", "") or item.get("label", ""),
    )


def _cache_get(key: str) -> list[LocationSuggestion] | None:
    cached = _CACHE.get(key)
    if not cached:
        return None
    expires_at, results = cached
    if expires_at < time.time():
        _CACHE.pop(key, None)
        return None
    return results


def _cache_put(key: str, results: list[LocationSuggestion]) -> None:
    ttl = max(get_settings().location_cache_ttl_seconds, 30)
    _CACHE[key] = (time.time() + ttl, results)


def _search_local(query: str, limit: int) -> list[LocationSuggestion]:
    normalized = _normalize(query)
    if not normalized:
        return []
    matches: list[dict[str, Any]] = []
    for item in _LOCAL_PLACES:
        haystacks = [
            item["label"],
            item.get("city", ""),
            item.get("region", ""),
            item.get("country", ""),
            item.get("country_code", ""),
        ]
        if any(normalized in _normalize(value) for value in haystacks if value):
            matches.append(item)
    if not matches:
        return []
    return [_to_suggestion(item, "local") for item in matches[:limit]]


def _search_pelias(query: str, limit: int) -> list[LocationSuggestion]:
    settings = get_settings()
    if settings.location_provider != "pelias" or not settings.pelias_url:
        return []
    try:
        response = requests.get(
            f"{settings.pelias_url.rstrip('/')}/autocomplete",
            params={"text": query, "size": min(limit, 10)},
            timeout=3,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    features = payload.get("features", []) if isinstance(payload, dict) else []
    suggestions: list[LocationSuggestion] = []
    for feature in features:
        props = feature.get("properties", {}) if isinstance(feature, dict) else {}
        geom = feature.get("geometry", {}) if isinstance(feature, dict) else {}
        coords = geom.get("coordinates", []) if isinstance(geom, dict) else []
        layer = props.get("layer", "")
        kind = "city"
        if layer in {"country"}:
            kind = "country"
        elif layer in {"region"}:
            kind = "region"
        suggestions.append(
            LocationSuggestion(
                label=props.get("label", ""),
                kind=kind,
                subtitle=" · ".join(
                    part for part in [props.get("region"), props.get("country")] if part
                ),
                city=props.get("locality", "") or props.get("localadmin", ""),
                region=props.get("region", ""),
                country=props.get("country", ""),
                country_code=props.get("country_a", ""),
                lat=coords[1] if len(coords) >= 2 else None,
                lon=coords[0] if len(coords) >= 2 else None,
                provider="pelias",
                provider_id=str(props.get("gid", "")),
            )
        )
    return [item for item in suggestions if item.label][:limit]


def suggest_locations(query: str, limit: int = 8) -> list[LocationSuggestion]:
    trimmed = query.strip()
    if len(trimmed) < 2:
        return []
    cache_key = f"{get_settings().location_provider}:{trimmed.lower()}:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    results = _search_pelias(trimmed, limit)
    if not results:
        results = _search_local(trimmed, limit)
    _cache_put(cache_key, results)
    return results
