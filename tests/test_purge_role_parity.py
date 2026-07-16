"""The DB role purge must keep exactly what the in-memory role filter keeps.

Bug: filter_by_role rescues crypto, founding, and balanced non-remote jobs,
but purge_non_matching_roles used a plain strict _match_roles — so the
pipeline surfaced a crypto/startup job this run while silently deleting that
same record (and prior-run matches) from the Applications DB.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from job_finder.models import database


class PurgeRoleParityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        database.init_db(os.path.join(self.tmpdir.name, "job_tracker.db"))

    def tearDown(self) -> None:
        if database._SessionLocal is not None:
            database._SessionLocal.remove()
        self.tmpdir.cleanup()

    def _titles(self) -> set[str]:
        return {a.job_title for a in database.get_all_applications()}

    def test_purge_keeps_crypto_record_only_with_explicit_rescue(self) -> None:
        database.save_application(
            job_title="Solidity Developer", company="Re7", job_url="u1",
            source="cryptojobslist", profile="p",
        )
        database.save_application(
            job_title="Registered Nurse", company="Hosp", job_url="u2",
            source="remotive", profile="p",
        )
        deleted = database.purge_non_matching_roles(
            ["software engineer"], profile="p", allow_crypto_rescue=True,
        )
        remaining = self._titles()
        self.assertIn("Solidity Developer", remaining)     # crypto kept
        self.assertNotIn("Registered Nurse", remaining)    # non-match purged
        self.assertEqual(deleted, 1)

    def test_purge_keeps_crypto_company_ats_record(self) -> None:
        database.save_application(
            job_title="Smart Contract Engineer", company="Alchemy", job_url="u1",
            source="ashby", profile="p",
        )
        database.purge_non_matching_roles(
            ["data engineer"], profile="p", allow_crypto_rescue=True,
        )
        self.assertIn("Smart Contract Engineer", self._titles())

    def test_purge_keeps_founding_title(self) -> None:
        database.save_application(
            job_title="Founding Engineer", company="Seed", job_url="u1",
            source="workatastartup", profile="p",
        )
        database.purge_non_matching_roles(
            ["data engineer"], profile="p", include_founding=True,
        )
        self.assertIn("Founding Engineer", self._titles())

    def test_purge_matches_filter_by_role_exactly(self) -> None:
        """The survivor set after purge == the kept set from filter_by_role."""
        from job_finder.pipeline import JobFinderPipeline

        jobs = [
            {"title": "Solidity Developer", "company": "Re7", "url": "u1",
             "source": "cryptojobslist", "is_remote": True},
            {"title": "Smart Contract Engineer", "company": "Alchemy", "url": "u2",
             "source": "ashby", "is_remote": True},
            {"title": "ML Platform Engineer", "company": "Acme", "url": "u3",
             "source": "greenhouse", "is_remote": False},
            {"title": "Registered Nurse", "company": "Hosp", "url": "u4",
             "source": "remotive", "is_remote": True},
        ]
        pipe = JobFinderPipeline(llm=None, profile=None)
        pipe.config = {
            "target_roles": ["data engineer"],
            "filters": {"strictness": "balanced"},
        }
        kept_titles = {j["title"] for j in pipe.filter_by_role([dict(j) for j in jobs])}

        for j in jobs:
            database.save_application(
                job_title=j["title"], company=j["company"], job_url=j["url"],
                source=j["source"], is_remote=j["is_remote"], profile="p",
            )
        database.purge_non_matching_roles(
            ["data engineer"], profile="p",
            match_mode="all_significant", include_founding=False, strictness="balanced",
            allow_crypto_rescue=False,
        )
        self.assertEqual(kept_titles, self._titles())


if __name__ == "__main__":
    unittest.main()
