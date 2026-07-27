"""The LinkedIn description backfill must spend its budget on survivors.

Real report, 2026-07-27: a Walt Disney "Manager, Software Engineering - BI &
Analytics" row showed "REWARD not stated" on the board while the LinkedIn
posting states $171,600 - $252,000. The row had no description at all, so
there was nothing for salary extraction to read, and the assistant ranked it
on title and company alone.

The cause is ordering, not fetching. The fast search pass skips LinkedIn's
detail page (`linkedin_fetch_description=False`), and a capped backfill is
supposed to fill the gap afterwards. That backfill ran against every deduped
job, capped at 25, BEFORE the location, level, and role gates ran. So the
budget went to jobs that were about to be discarded, and rows that survived
to the board were left empty. The code even said so:

    # Jobs that get filtered out by the location/role gates below
    # never needed their description anyway

The gates were below. The fetch was above.

The backfill still has to run before the salary filter, or a pay figure that
only exists in the description can never take part in it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

PIPELINE = (ROOT / "src" / "job_finder" / "pipeline.py").read_text()


def _line_of(needle: str) -> int:
    for i, line in enumerate(PIPELINE.splitlines(), start=1):
        if needle in line:
            return i
    raise AssertionError(f"anchor vanished from pipeline.py: {needle!r}")


def test_backfill_runs_after_the_location_gate() -> None:
    """Location is the widest gate; paying to fetch rows it will drop is the
    whole waste."""
    backfill = _line_of("_backfill_linkedin_descriptions(no_desc")
    location_gate = _line_of("# --- Salary filter: remove jobs with known salary below minimum ---")
    assert backfill < location_gate, "backfill must still precede the salary filter"

    classify = _line_of('progress("Classifying remote/hybrid/onsite...")')
    assert backfill > classify, (
        "the backfill still runs before the location gate, so its capped budget "
        "goes to jobs that are about to be discarded"
    )


def test_backfill_runs_before_the_salary_filter() -> None:
    """A salary that only appears in the description has to be parsed before
    the floor is applied, or the row is judged on pay nobody read."""
    backfill = _line_of("_backfill_linkedin_descriptions(no_desc")
    salary_filter = _line_of("# --- Salary filter: remove jobs with known salary below minimum ---")
    assert backfill < salary_filter


def test_salary_is_re_extracted_after_the_fetch() -> None:
    """Fetching the text is only half of it; those rows were finalized with
    salary_source=None before the description existed."""
    backfill = _line_of("_backfill_linkedin_descriptions(no_desc")
    refinalize = _line_of("finalize_scraper_jobs(no_desc)")
    assert refinalize > backfill


def test_the_disney_posting_shape_yields_its_band() -> None:
    """The real posting's pay wording, through the real extractor."""
    from job_finder.tools.scrapers._utils import extract_salary_range

    # Condensed from the live LinkedIn page for job 4433613222.
    text = (
        "The hiring range for this position in Glendale, CA is "
        "$171,600 to $252,000 per year. The base pay actually offered will "
        "take into account internal equity and may vary."
    )
    result = extract_salary_range(text)
    assert (result.salary_min, result.salary_max) == (171600.0, 252000.0)
    assert result.period == "annual"
