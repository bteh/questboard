"""The release gate's stranger flow: a first-time user with nothing
configured uploads a resume and gets a full board.

Pinned after Sep 8 2026, when the only proof that the shipped build could
do this was a hand-run against the DMG. The network half runs only under
``--live-search``; these pin the parts that can be checked offline.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS = str(Path(__file__).resolve().parents[1] / "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import verify_desktop_bundle as vdb


class TestMultipart:
    def test_body_carries_the_file_under_the_field_the_api_reads(self):
        body, content_type = vdb._multipart("file", "resume.pdf", b"%PDF-1.4 fake")
        assert content_type.startswith("multipart/form-data; boundary=")
        assert b'name="file"; filename="resume.pdf"' in body
        assert b"%PDF-1.4 fake" in body
        assert body.endswith(b"--\r\n")


class TestSyntheticResume:
    def test_resume_reads_as_a_data_engineer_so_roles_can_be_derived(self):
        # The search derives roles from the resume text when no roles are
        # set, so the synthetic resume must name a role, not just skills.
        assert "Data Engineer" in vdb.SYNTHETIC_RESUME
        assert "dbt" in vdb.SYNTHETIC_RESUME

    @pytest.mark.skipif(shutil.which("cupsfilter") is None, reason="cupsfilter is macOS-only")
    def test_pdf_is_real_and_non_empty(self, tmp_path):
        pdf = vdb.synthetic_resume_pdf(tmp_path / "resume.pdf")
        assert pdf.read_bytes().startswith(b"%PDF")
        assert pdf.stat().st_size > 1000


class TestPlaceShape:
    def test_place_matches_the_preferences_schema(self):
        place = vdb.LIVE_SEARCH_PLACE
        assert place["kind"] == "city"
        assert place["match_scope"] in {"city", "metro", "region", "country"}
        assert place["label"] and place["country_code"] == "US"
