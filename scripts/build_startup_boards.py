"""Build src/job_finder/config/startup_boards.json from the public YC directory.

Maintainer tool, run by hand (needs network, ~10 minutes):

    uv run python scripts/build_startup_boards.py

For every active YC company it probes the public Ashby, Greenhouse and Lever
job-board APIs under the company's likely board names and keeps a board only
when the board itself proves it belongs to that company:

- board name == the company's website name (trmlabs.com -> "trmlabs"): the
  postings must mention the YC company name. Stops medium.bio (Medium
  Biosciences) claiming the Medium blog's board.
- any other board name (the YC slug or the plain company name): the postings
  must mention the company's website domain. Stops a 2-person YC "Hopper"
  (tryhopper.com) claiming Hopper the travel app's board.

Companies not hiring on YC are only checked against boards already in our
catalogs, so the run stays near a few thousand requests.

Source: https://yc-oss.github.io/api/companies/all.json, an unofficial daily
export of YC's public company directory. Only company facts are kept.
"""

from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "src/job_finder/tools/scrapers/data"
OUT = ROOT / "src/job_finder/config/startup_boards.json"
YC_URL = "https://yc-oss.github.io/api/companies/all.json"
HOSTS = ("ashby", "greenhouse", "lever")
UA = {"User-Agent": "Questboard/startup-boards (+https://github.com/bteh/questboard)"}


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def website_parts(url: str) -> tuple[str, str]:
    """(domain, label): https://www.trmlabs.com/ -> ("trmlabs.com", "trmlabs")."""
    host = urlparse(url or "").netloc.lower().removeprefix("www.")
    return host, norm(host.split(".")[0]) if host else ""


def catalog_slugs() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for host in HOSTS:
        slugs: set[str] = set()
        for name in (f"{host}_seed.txt", f"{host}_verified_full.txt"):
            for line in (CATALOG_DIR / name).read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    slugs.add(line.lower())
        out[host] = slugs
    return out


def fetch_board_text(host: str, slug: str) -> tuple[str, str] | None:
    """(board_name, postings_text) for a live board with jobs, else None."""
    urls = {
        "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
        "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
        "lever": f"https://api.lever.co/v0/postings/{slug}?mode=json",
    }
    for attempt in range(3):
        try:
            resp = requests.get(urls[host], headers=UA, timeout=15)
        except requests.RequestException:
            time.sleep(1 + attempt)
            continue
        if resp.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except ValueError:
            return None
        break
    else:
        return None

    board_name = ""
    if host == "greenhouse":
        jobs = data.get("jobs") or []
        try:
            meta = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}", headers=UA, timeout=15,
            ).json()
            board_name = meta.get("name") or ""
        except (requests.RequestException, ValueError):
            pass
        text = " ".join(
            (j.get("title") or "") + " " + (j.get("content") or "") for j in jobs
        )
    elif host == "ashby":
        jobs = data.get("jobs") or []
        text = " ".join(
            (j.get("title") or "") + " " + (j.get("descriptionPlain") or "")
            + " " + (j.get("jobUrl") or "") for j in jobs
        )
    else:
        jobs = data if isinstance(data, list) else []
        text = " ".join(
            (j.get("text") or "") + " " + (j.get("descriptionPlain") or "")
            + " " + (j.get("additionalPlain") or "") for j in jobs
        )
    if not jobs:
        return None
    return board_name, text.lower()


def mentions(text: str, phrase: str) -> bool:
    phrase = phrase.lower().strip()
    if len(phrase) < 3:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text) is not None


def board_belongs(company: dict, slug: str, board: tuple[str, str]) -> bool:
    board_name, text = board
    domain, label = website_parts(company.get("website") or "")
    names = [company["name"], *(company.get("former_names") or [])]
    if domain and mentions(text, domain):
        return True
    # A multi-word board name (trm-labs) is specific enough to trust a name
    # mention; a single word (hopper) needs the website.
    if slug == label or ("-" in slug and slug == (company.get("slug") or "").lower()):
        if board_name and norm(board_name) in {norm(n) for n in names}:
            return True
        return any(mentions(text, n) for n in names)
    return False


def candidates(company: dict) -> list[str]:
    """Board names to try. Boards keep hyphens: TRM Labs is ashby/trm-labs."""
    _, label = website_parts(company.get("website") or "")
    hyphenated = re.sub(r"[^a-z0-9]+", "-", company["name"].lower()).strip("-")
    seen: list[str] = []
    for slug in (
        label,
        (company.get("slug") or "").lower(),
        hyphenated,
        norm(company.get("slug") or ""),
        norm(company["name"]),
    ):
        if slug and len(slug) >= 3 and slug not in seen:
            seen.append(slug)
    return seen


def probe(company: dict, known: dict[str, set[str]]) -> dict | None:
    hiring = bool(company.get("isHiring"))
    for host in HOSTS:
        for slug in candidates(company):
            if not hiring and slug not in known[host]:
                continue
            board = fetch_board_text(host, slug)
            if board and board_belongs(company, slug, board):
                return {
                    "ats": host,
                    "slug": slug,
                    "name": company["name"],
                    "stage": company.get("stage") or "",
                    "batch": company.get("batch") or "",
                    "team_size": company.get("team_size"),
                    "website": company.get("website") or "",
                    "hiring": hiring,
                }
    return None


def main() -> int:
    companies = [
        c for c in requests.get(YC_URL, headers=UA, timeout=60).json()
        if c.get("status") == "Active"
    ]
    known = catalog_slugs()
    print(f"{len(companies)} active YC companies", flush=True)
    found: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=12) as pool:
        for row in pool.map(lambda c: probe(c, known), companies):
            done += 1
            if row:
                found.append(row)
            if done % 250 == 0:
                print(f"  {done}/{len(companies)} checked, {len(found)} boards", flush=True)
    found.sort(key=lambda r: (r["ats"], r["slug"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": YC_URL,
        "built_at": time.strftime("%Y-%m-%d"),
        "boards": found,
    }, indent=1) + "\n")
    print(f"wrote {len(found)} boards to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
