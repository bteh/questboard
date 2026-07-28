"""Ask each ATS whether a cached company board still exists.

Slug discovery harvests company names out of search results, so a share of
what it caches never had a board on that host. ``DeadBoards`` drops those as a
pull happens to fetch them, which means an entry nothing searched for stays
forever: Ashby was still carrying ~33 dead slugs days after they were found.
``sweep_dead_slugs`` is the direct pass, and this module is what it probes
with.

The board URL lives in exactly one place, the scraper that owns it. Rather
than copy four URL templates here (where a change to Ashby's API path would
leave this file quietly probing a dead endpoint and calling 247 live
companies dead), the probe calls each scraper's own per-board fetch and reads
the status off its ``on_status`` hook.

Reading the hook rather than the returned rows is the point. Every scraper
returns an empty list both for a board that 404s and for a healthy board with
nothing matching the roles asked about, and a probe asks about no roles at
all, so judging by the list would condemn the whole cache.
"""

from __future__ import annotations

import argparse
import logging
from typing import Any, Callable

from job_finder.tools.scrapers._ats_discovery import ATS_HOSTS, sweep_dead_slugs

logger = logging.getLogger(__name__)


# host -> (module name, per-board fetch function name). Each scraper named its
# own fetch before this existed; renaming them to match would touch four files
# to save one dict.
PROBES: dict[str, tuple[str, str]] = {
    "ashby": ("ashby", "_fetch_company_jobs"),
    "greenhouse": ("greenhouse", "_fetch_company_jobs"),
    "lever": ("lever", "_fetch_company_postings"),
    "workable": ("workable", "_fetch_company_jobs"),
}


def _scraper_module(host: str):
    from importlib import import_module

    module_name, _ = PROBES[host]
    return import_module(f"job_finder.tools.scrapers.{module_name}")


def probe_status(host: str) -> Callable[[str], int | None]:
    """Build a probe: slug in, the HTTP status its board answered out.

    None means the request never got a status (refused, DNS, timeout). That is
    deliberately not 404: a host having a bad minute must not read as hundreds
    of companies ceasing to exist.
    """
    _, func_name = PROBES[host]
    fetch = getattr(_scraper_module(host), func_name)

    def probe(slug: str) -> int | None:
        seen: list[int | None] = []
        try:
            # roles=None asks for every posting, so a board is judged on
            # whether it answers at all, not on what it happens to be hiring.
            fetch(slug, None, on_status=seen.append)
        except Exception:
            return None
        return seen[0] if seen else None

    return probe


def sweep(
    hosts: list[str] | None = None, *, workers: int = 8, dry_run: bool = False
) -> dict[str, Any]:
    """Probe every cached slug for each host and forget the ones that 404."""
    results: dict[str, Any] = {}
    for host in hosts or sorted(PROBES):
        results[host] = sweep_dead_slugs(
            host, probe_status(host), workers=workers, report=True, dry_run=dry_run
        )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="questboard-sweep-boards",
        description=(
            "Probe every cached ATS company slug and forget the boards that "
            "answer 404. Makes one network call per cached slug; a pull does "
            "this incidentally, this does it on purpose."
        ),
    )
    parser.add_argument(
        "--host",
        action="append",
        choices=sorted(PROBES),
        help="Sweep only this host (repeatable). Default: all of them.",
    )
    parser.add_argument(
        "--workers", type=int, default=8, help="Concurrent probes (default 8)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be dropped without writing the cache",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    hosts = args.host or sorted(PROBES)

    for host in hosts:
        report = sweep([host], workers=args.workers, dry_run=args.dry_run)[host]
        verb = "would drop" if args.dry_run else "dropped"
        print(
            f"{host}: checked {report['checked']}, {verb} {report['dropped']}, "
            f"unreachable {report['unreachable']}"
        )
        for slug in report["dead"]:
            print(f"  {slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
