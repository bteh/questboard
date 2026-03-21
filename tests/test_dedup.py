from __future__ import annotations

import unittest

from job_finder.pipeline import _deduplicate


class DeduplicateJobsTest(unittest.TestCase):
    def test_keeps_same_title_in_different_locations(self) -> None:
        jobs = [
            {
                "title": "Software Engineer",
                "company": "Example Co",
                "location": "San Francisco, CA",
                "url": "https://jobs.example.com/1",
                "description": "Build internal platforms for the payments team.",
                "source": "indeed",
            },
            {
                "title": "Software Engineer",
                "company": "Example Co",
                "location": "New York, NY",
                "url": "https://jobs.example.com/2",
                "description": "Build internal platforms for the payments team.",
                "source": "linkedin",
            },
        ]

        deduped = _deduplicate(jobs)
        self.assertEqual(len(deduped), 2)

    def test_merges_cross_source_duplicates_with_matching_location_and_description(self) -> None:
        jobs = [
            {
                "title": "Product Manager",
                "company": "Example Co",
                "location": "Remote",
                "url": "https://jobs.example.com/a",
                "description": (
                    "Own roadmap prioritization, partner with engineering and design, "
                    "and ship customer-facing workflow improvements."
                ),
                "source": "indeed",
            },
            {
                "title": "Product Manager",
                "company": "Example Co",
                "location": "Remote - US",
                "url": "https://jobs.example.com/b",
                "description": (
                    "Own roadmap prioritization, partner with engineering and design, "
                    "and ship customer-facing workflow improvements."
                ),
                "source": "glassdoor",
            },
        ]

        deduped = _deduplicate(jobs)
        self.assertEqual(len(deduped), 1)


if __name__ == "__main__":
    unittest.main()
