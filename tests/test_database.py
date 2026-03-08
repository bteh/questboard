from __future__ import annotations

import os
import tempfile
import unittest

from job_finder.models import database


class PurgeNonMatchingLocationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        database.init_db(os.path.join(self.tmpdir.name, "job_tracker.db"))

    def tearDown(self) -> None:
        if database._SessionLocal is not None:
            database._SessionLocal.remove()
        self.tmpdir.cleanup()

    def test_purge_can_be_scoped_to_one_profile(self) -> None:
        database.save_application(
            job_title="Data Engineer",
            company="Alpha",
            location="New York, NY",
            job_url="https://example.com/alpha",
            profile="alice",
        )
        database.save_application(
            job_title="Data Engineer",
            company="Beta",
            location="Los Angeles, CA",
            job_url="https://example.com/beta",
            profile="alice",
        )
        database.save_application(
            job_title="Data Engineer",
            company="Gamma",
            location="New York, NY",
            job_url="https://example.com/gamma",
            profile="bob",
        )

        deleted = database.purge_non_matching_locations(
            preferred_states=["CA"],
            profile="alice",
        )

        self.assertEqual(deleted, 1)

        remaining = {
            (app.company, app.profile)
            for app in database.get_all_applications()
        }
        self.assertEqual(
            remaining,
            {
                ("Beta", "alice"),
                ("Gamma", "bob"),
            },
        )


if __name__ == "__main__":
    unittest.main()
