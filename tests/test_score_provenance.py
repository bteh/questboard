"""Score provenance: which scale scored a row.

The LLM scorer and the keyword fallback share one recommendation label
space but not one scale (keyword STRONG_APPLY fires at strong_apply * 0.65).
These tests pin the provenance stamps and the startup backfill heuristic:

1. score_job_basic always stamps score_source='keyword', with or without
   AI company-intel baselines.
2. The pipeline's LLM path stamps score_source='ai' on fresh and cached
   results; the per-job fallback inside _score_jobs_ai lands 'keyword'.
3. _migrate_db backfills existing scored rows from the stored reasoning
   format: "Scoring (...)" means the keyword scorer wrote it, prose means
   the LLM did, empty reasoning with a score means keyword, no score stays
   NULL.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from job_finder.pipeline import JobFinderPipeline
from job_finder.scoring.core import score_job_basic


_JD = "We need a Python engineer to build data pipelines on AWS with Kubernetes."
_RESUME = "Python engineer, 6 years building data pipelines, AWS, Kubernetes."


def _pipeline_with_mock_llm(llm_response) -> JobFinderPipeline:
    p = JobFinderPipeline.__new__(JobFinderPipeline)
    p.llm = MagicMock()
    p.llm.is_configured = True
    p.llm._is_anthropic_provider.return_value = False
    p.llm.chat_json.return_value = llm_response
    p.config = {}
    return p


class KeywordScorerStampTest(unittest.TestCase):
    def test_score_job_basic_stamps_keyword(self) -> None:
        result = score_job_basic(_JD, _RESUME, job_title="Data Engineer")
        self.assertEqual(result["score_source"], "keyword")

    def test_ai_intel_baselines_still_stamp_keyword(self) -> None:
        # Company baselines come from LLM intel, but the job itself is still
        # scored on the keyword scale; the reasoning says "Scoring (AI intel)".
        result = score_job_basic(
            _JD, _RESUME,
            job_title="Data Engineer",
            company_baselines={
                "technical": 70, "leadership": 50, "comp": 60,
                "platform": 55, "trajectory": 65, "culture": 60,
            },
        )
        self.assertEqual(result["score_source"], "keyword")
        self.assertTrue(result["score_reasoning"].startswith("Scoring ("))


class LlmPathStampTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.dict(
            "os.environ", {"QUESTBOARD_DISABLE_AI_SCORE_CACHE": "1"},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_score_job_with_ai_stamps_ai(self) -> None:
        p = _pipeline_with_mock_llm({
            "overall_score": 82, "recommendation": "STRONG_APPLY",
        })
        job = {"title": "Data Engineer", "company": "Acme", "description": _JD}
        result = p.score_job_with_ai(job, _RESUME)
        self.assertIsNotNone(result)
        self.assertEqual(result["score_source"], "ai")

    def test_cached_result_gets_stamped_too(self) -> None:
        # Entries cached before provenance shipped lack the key; the read
        # path must stamp them so old cache hits stay honest.
        p = _pipeline_with_mock_llm(None)
        job = {"title": "Data Engineer", "company": "Acme", "description": _JD}
        with patch(
            "job_finder.pipeline.load_cached_ai_score",
            return_value={"overall_score": 75, "recommendation": "STRONG_APPLY"},
        ):
            result = p.score_job_with_ai(job, _RESUME)
        self.assertEqual(result["score_source"], "ai")

    def test_score_jobs_ai_success_lands_ai_on_job(self) -> None:
        p = _pipeline_with_mock_llm({
            "overall_score": 88, "recommendation": "STRONG_APPLY",
        })
        job = {"title": "Data Engineer", "company": "Acme", "description": _JD}
        p._score_jobs_ai([job], _RESUME)
        self.assertEqual(job["score_source"], "ai")

    def test_score_jobs_ai_fallback_lands_keyword_on_job(self) -> None:
        # LLM returns None (down/rate-limited): the per-job fallback scores
        # with keywords and the row must say so.
        p = _pipeline_with_mock_llm(None)
        job = {"title": "Data Engineer", "company": "Acme", "description": _JD}
        p._score_jobs_ai([job], _RESUME)
        self.assertEqual(job["score_source"], "keyword")
        self.assertIsNotNone(job.get("overall_score"))


class BackfillHeuristicTest(unittest.TestCase):
    """_migrate_db classifies pre-existing scored rows by reasoning format."""

    def _legacy_engine(self, tmp_db: str):
        engine = create_engine(f"sqlite:///{tmp_db}")
        with engine.begin() as conn:
            conn.execute(text(
                """
                CREATE TABLE applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_title VARCHAR(500) NOT NULL,
                    company VARCHAR(300) NOT NULL,
                    location VARCHAR(300),
                    job_url VARCHAR(2000) UNIQUE,
                    source VARCHAR(100),
                    description TEXT,
                    is_remote BOOLEAN,
                    salary_min FLOAT,
                    salary_max FLOAT,
                    overall_score FLOAT,
                    recommendation VARCHAR(50),
                    score_reasoning TEXT,
                    status VARCHAR(50),
                    date_found DATETIME,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            ))
            rows = [
                ("Keyword Row", "Scoring (Big Tech): 64/100 overall. Technical 50.", 64.0),
                ("Intel Row", "Scoring (AI intel): 58/100 overall. Technical 44.", 58.0),
                ("AI Row", "Your pipeline experience covers most of what they ask for.", 82.0),
                ("Bare Row", "", 45.7),
                ("Unscored Row", "", None),
            ]
            for i, (title, reasoning, score) in enumerate(rows):
                conn.execute(
                    text(
                        "INSERT INTO applications "
                        "(job_title, company, job_url, score_reasoning, overall_score) "
                        "VALUES (:t, 'Acme', :u, :r, :s)"
                    ),
                    {"t": title, "u": f"https://example.com/{i}", "r": reasoning, "s": score},
                )
        return engine

    def _source_by_title(self, engine) -> dict[str, str | None]:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT job_title, score_source FROM applications")
            ).fetchall()
        return {title: source for title, source in rows}

    def test_backfill_classifies_by_reasoning_format(self) -> None:
        import tempfile

        from job_finder.models.database import _migrate_db

        with tempfile.TemporaryDirectory() as tmp:
            engine = self._legacy_engine(f"{tmp}/legacy.db")
            _migrate_db(engine)
            by_title = self._source_by_title(engine)

        self.assertEqual(by_title["Keyword Row"], "keyword")
        self.assertEqual(by_title["Intel Row"], "keyword")
        self.assertEqual(by_title["AI Row"], "ai")
        self.assertEqual(by_title["Bare Row"], "keyword")
        self.assertIsNone(by_title["Unscored Row"])

    def test_backfill_is_idempotent_and_keeps_existing_values(self) -> None:
        import tempfile

        from job_finder.models.database import _migrate_db

        with tempfile.TemporaryDirectory() as tmp:
            engine = self._legacy_engine(f"{tmp}/legacy.db")
            _migrate_db(engine)
            # Flip one row, then run again: a set value is never rewritten.
            with engine.begin() as conn:
                conn.execute(text(
                    "UPDATE applications SET score_source = 'ai' "
                    "WHERE job_title = 'Keyword Row'"
                ))
            _migrate_db(engine)
            by_title = self._source_by_title(engine)

        self.assertEqual(by_title["Keyword Row"], "ai")
        self.assertEqual(by_title["AI Row"], "ai")


if __name__ == "__main__":
    unittest.main()
