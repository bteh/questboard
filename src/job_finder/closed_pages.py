"""Closed-job pages that still answer HTTP 200.

The link checker tombstones a row only on a definitive 404/410, because bot
walls must never hide a live posting. Some hosts keep a closed job's URL alive
and render a notice instead, so a status-only check stamps the row alive and
the board's still-open rule (freshness basis "verified_open") keeps it past
the freshness window.

Each template is scoped to its own host and judged on the final page after
redirects, so a generic phrase on an unrelated page never kills a row. Real
cases from Brian's board, Oct 6 2026, phrasing copied from the live pages:

- builtin.com keeps the editorial page at 200 with "Sorry, this job was
  removed at ..." (Sift Stack, Teamworks, Horizon3.ai).
- linkedin.com redirects a closed job to a search page carrying
  ``trk=expired_jd_redirect`` (Whatnot, Calance), or keeps /jobs/view with the
  "No longer accepting applications" banner.
- apply.workable.com redirects a removed job to ``/oops`` or to the account
  index with ``?not_found=true`` (Tiger Analytics).
- Getro-hosted boards (jobs.<fund>/companies/<slug>/jobs/<id>) say "no longer
  available" (shape from jobs.techstars.com; not seen closed live).
- Greenhouse "The job you are looking for is no longer open" and Lever "This
  job is no longer accepting applications" are the ATS's own closed notices
  (both close with a 404 or ``?error=true`` redirect today; kept as belts).

CONTENT_CHECK_HOSTS and SOFT_DEAD_PHRASES are the older phrase-only layer:
those phrases are read only on those hosts, or on an apply target the caller
explicitly asked to inspect.

dead_redirect() is the host-free redirect rule. A job URL carries its
identity (a numeric job id, ``gh_jid``, the job slug after ``/jobs/``). A
redirect that lands on a URL carrying none of it is the site sending a closed
job to a listing index. Real cases, Nov 5 2026: 15 of 15 stale Himalayas rows
redirected to himalayas.app/jobs; 5 of 10 Greenhouse rows redirected to a
careers index (3Cloud to 3cloudsolutions.com/join-us, its posting 404 on the
Greenhouse boards API; Databricks, Instacart). Descript (boards to
job-boards.greenhouse.io) and Elastic (``?gh_jid=`` to a slug page ending in
the id) keep the id and stay alive. A URL with no recognizable identity is
never judged by this rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse


@dataclass(frozen=True)
class ClosedPageTemplate:
    name: str
    host: str
    phrases: tuple[str, ...] = ()
    final_paths: tuple[str, ...] = ()
    final_query: tuple[tuple[str, str], ...] = ()
    path: str = ""

    def _owns_host(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").casefold()
        return re.fullmatch(self.host, host) is not None

    def owns(self, url: str) -> bool:
        if not self._owns_host(url):
            return False
        return not self.path or re.match(self.path, urlparse(url).path) is not None

    def closes(self, final_url: str, body: str) -> bool:
        if not self._owns_host(final_url):
            return False
        final = urlparse(final_url)
        if final.path.rstrip("/") in self.final_paths:
            return True
        query = parse_qs(final.query)
        if any(value in query.get(key, []) for key, value in self.final_query):
            return True
        lowered = body.casefold()
        return any(phrase in lowered for phrase in self.phrases)


TEMPLATES: tuple[ClosedPageTemplate, ...] = (
    ClosedPageTemplate(
        "builtin",
        r"(?:[\w-]+\.)*builtin\.com",
        phrases=("sorry, this job was removed", "sorry, this job is no longer"),
    ),
    ClosedPageTemplate(
        "linkedin",
        r"(?:[\w-]+\.)*linkedin\.com",
        phrases=("no longer accepting applications", "this job is no longer available"),
        final_query=(("trk", "expired_jd_redirect"),),
    ),
    ClosedPageTemplate(
        "workable",
        r"apply\.workable\.com",
        final_paths=("/oops",),
        final_query=(("not_found", "true"),),
    ),
    ClosedPageTemplate(
        "greenhouse",
        r"(?:job-boards(?:\.eu)?|boards)\.greenhouse\.io",
        phrases=("the job you are looking for is no longer open",),
    ),
    ClosedPageTemplate(
        "lever",
        r"jobs\.lever\.co",
        phrases=("this job is no longer accepting applications",),
    ),
    ClosedPageTemplate(
        "getro",
        r"jobs\.[\w.-]+",
        path=r"/companies/[^/]+/jobs/[^/]+",
        phrases=("no longer available",),
    ),
)

CONTENT_CHECK_HOSTS: tuple[str, ...] = (
    "ashbyhq.com",
    "greenhouse.io",
    "lever.co",
    "myworkdayjobs.com",
    "smartrecruiters.com",
    # Web3.career keeps closed listing pages at HTTP 200 with an explicit
    # "This job is closed" banner.
    "web3.career",
    "workable.com",
)

SOFT_DEAD_PHRASES: tuple[str, ...] = (
    "job is no longer available",
    "job posting is no longer available",
    "position is no longer available",
    "job you are looking for is no longer open",
    "job posting has expired",
    "this job has expired",
    "position has been filled",
    "opportunity is no longer available",
    "no longer accepting applications",
    "this job is closed",
    "this position has been closed",
    "this vacancy is no longer available",
    "the job is no longer open",
    "the job you requested was not found",
)


def host_matches(host: str, suffixes: tuple[str, ...]) -> bool:
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes)


def template_for(url: str) -> ClosedPageTemplate | None:
    return next((template for template in TEMPLATES if template.owns(url)), None)


def needs_body(url: str) -> bool:
    """True when a 200 alone is not enough evidence for this URL."""
    host = (urlparse(url).hostname or "").casefold()
    return host_matches(host, CONTENT_CHECK_HOSTS) or template_for(url) is not None


_JOB_PATH_WORDS = frozenset({"job", "jobs", "posting", "postings", "position", "positions"})
# Only query keys that name a job: a utm or tracking number dropped by the
# redirect must not read as the job's identity going away.
_JOB_QUERY_KEYS = frozenset({"gh_jid", "jid", "jobid", "job_id", "job", "id", "reqid", "req_id"})


def _is_id(segment: str) -> bool:
    if re.fullmatch(r"\d{5,}", segment):
        return True
    # UUIDs (Lever, Ashby) and compact codes (Workable 3844870A3A); a worded
    # slug like "staff-data-engineer-2" is not an id.
    return any(ch.isdigit() for ch in segment) and (
        re.fullmatch(r"[0-9a-f-]{8,}|[0-9a-z]{8,}", segment) is not None
    )


def job_identity(url: str) -> frozenset[str]:
    """The tokens that name this specific job in ``url``; empty when none."""
    parsed = urlparse(url)
    tokens: set[str] = set()
    segments = [unquote(part).casefold() for part in parsed.path.split("/") if part]
    for index, segment in enumerate(segments):
        if _is_id(segment):
            tokens.add(segment)
        elif index > 0 and segments[index - 1] in _JOB_PATH_WORDS and "-" in segment:
            tokens.add(segment)
    for key, values in parse_qs(parsed.query, keep_blank_values=True).items():
        key = key.casefold()
        if re.fullmatch(r"\d{5,}", key):
            tokens.add(key)
        elif key in _JOB_QUERY_KEYS:
            tokens.update(v.casefold() for v in values if re.fullmatch(r"\w{5,}", v))
    return frozenset(tokens)


def redirect_lost_job(requested_url: str, final_url: str) -> bool:
    """True when a redirect dropped every identity token of the requested job."""
    final = urlparse(final_url or "")
    if final.scheme not in ("http", "https") or not final.hostname:
        return False
    if final_url.rstrip("/") == requested_url.rstrip("/"):
        return False
    tokens = job_identity(requested_url)
    if not tokens:
        return False
    # Fully unquoted so a login wall's return URL (sessionRedirect=...%2F<id>)
    # still counts as carrying the job.
    landed = unquote(unquote(final_url)).casefold()
    return not any(token in landed for token in tokens)


def dead_redirect(requested_url: str, final_url: str) -> bool:
    """Whether a 2xx/3xx answer for ``requested_url`` that ended at ``final_url``
    is a closed job. Status codes are the caller's job: a bot wall is never
    passed in here."""
    final_url = final_url or requested_url
    final = urlparse(final_url)
    query = {key.casefold(): [v.casefold() for v in values] for key, values in parse_qs(final.query).items()}
    if "true" in query.get("error", []):
        return True
    requested = urlparse(requested_url)
    requested_host = (requested.hostname or "").casefold()
    final_host = (final.hostname or "").casefold()
    if (
        host_matches(requested_host, ("greenhouse.io",))
        and host_matches(final_host, ("greenhouse.io",))
        and "/jobs/" in requested.path.casefold()
        and "/jobs/" not in final.path.casefold()
    ):
        return True
    return redirect_lost_job(requested_url, final_url)


def closed_page(
    url: str, final_url: str, status: int, body: str, *, inspect: bool = False
) -> bool:
    """Whether the page a GET of ``url`` landed on is a closed-job notice.

    ``inspect`` extends the generic phrase layer to a host outside
    CONTENT_CHECK_HOSTS, for an apply target the caller chose to read. Error
    statuses are bot walls or outages, never evidence.
    """
    if status >= 400:
        return False
    template = template_for(url)
    if template is not None and template.closes(final_url or url, body):
        return True
    host = (urlparse(url).hostname or "").casefold()
    if inspect or host_matches(host, CONTENT_CHECK_HOSTS):
        lowered = body.casefold()
        return any(phrase in lowered for phrase in SOFT_DEAD_PHRASES)
    return False
