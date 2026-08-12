"""Dead/expired postings should be hidden from listings by default — and only
TRULY dead URLs (404/410) should be marked dead, not bot-blocked HEADs (403/
405/timeouts), which would otherwise hide good jobs.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for p in (BACKEND_PATH, SRC_PATH):
    if p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)


class _Resp:
    def __init__(self, code, url=""):
        self.status_code = code
        self.url = url


class _JsonResp(_Resp):
    def __init__(self, code, payload, url=""):
        super().__init__(code, url)
        self.payload = payload

    def json(self):
        return self.payload


class _PageResp(_Resp):
    def __init__(self, code, body, url=""):
        super().__init__(code, url)
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def iter_content(self, _chunk_size, decode_unicode=False):
        yield self.body


class DeadLinkTest(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = {k: os.environ.get(k) for k in
                      ["DATA_DIR", "HOSTED_MODE", "MANAGE_SCHEMA_ON_STARTUP", "DATABASE_URL"]}
        self.temp_dir = tempfile.mkdtemp(prefix="questboard-deadlink-")
        self.db_path = os.path.join(self.temp_dir, "job_tracker.db")
        os.environ["HOSTED_MODE"] = "false"
        os.environ["MANAGE_SCHEMA_ON_STARTUP"] = "true"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        for name in list(sys.modules):
            if name == "app" or name.startswith("app.") or name.startswith("job_finder.models"):
                sys.modules.pop(name, None)
        self.db_mod = importlib.import_module("app.models.database")
        self.db_mod.init_db(self.db_path)
        self.svc = importlib.import_module("app.services.application_service")
        self.AR = importlib.import_module("app.models.application").ApplicationRecord

    def tearDown(self) -> None:
        for k, v in self._orig.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _session(self):
        return self.db_mod._SessionLocal()

    def _add(
        self,
        title,
        status="unknown",
        url="https://x/1",
        source="test",
        search_run_id=None,
    ):
        db = self._session()
        try:
            db.add(self.AR(
                job_title=title,
                company="Acme",
                job_url=url,
                url_status=status,
                source=source,
                search_run_id=search_run_id,
            ))
            db.commit()
        finally:
            db.close()

    def test_listings_exclude_dead_by_default(self) -> None:
        self._add("Alive Engineer", status="alive", url="https://x/alive")
        self._add("Dead Engineer", status="dead", url="https://x/dead")
        self._add("Unknown Engineer", status="unknown", url="https://x/unknown")
        db = self._session()
        try:
            items, _ = self.svc.get_applications(db, exclude_dead=True)
            titles = {i.job_title for i in items}
            self.assertIn("Alive Engineer", titles)
            self.assertIn("Unknown Engineer", titles)
            self.assertNotIn("Dead Engineer", titles)
            # opt-in to show all
            items_all, _ = self.svc.get_applications(db, exclude_dead=False)
            self.assertIn("Dead Engineer", {i.job_title for i in items_all})
        finally:
            db.close()

    def test_check_urls_only_404_410_marks_dead(self) -> None:
        self._add("Gone", url="https://x/404")
        self._add("Live", url="https://x/200")
        self._add("Blocked", url="https://x/403")
        self._add("Slow", url="https://x/timeout")

        def fake_head(url, **kwargs):
            if url.endswith("/404"):
                return _Resp(404)
            if url.endswith("/200"):
                return _Resp(200)
            if url.endswith("/403"):
                return _Resp(403)
            raise TimeoutError("slow")

        with patch("requests.head", side_effect=fake_head):
            db = self._session()
            try:
                self.svc.check_urls(db)
            finally:
                db.close()

        db = self._session()
        try:
            by_title = {r.job_title: r.url_status for r in db.query(self.AR).all()}
        finally:
            db.close()
        self.assertEqual(by_title["Gone"], "dead")
        self.assertEqual(by_title["Live"], "alive")
        self.assertEqual(by_title["Blocked"], "unknown")   # 403 bot-block ≠ dead
        self.assertEqual(by_title["Slow"], "unknown")      # timeout ≠ dead

    def test_greenhouse_error_redirect_is_dead_even_when_http_200(self) -> None:
        url = "https://job-boards.greenhouse.io/acme/jobs/123"
        self._add("Gone at Greenhouse", url=url, source="greenhouse")

        with patch(
            "requests.head",
            return_value=_Resp(200, "https://job-boards.greenhouse.io/acme?error=true"),
        ):
            db = self._session()
            try:
                result = self.svc.check_urls(db)
            finally:
                db.close()

        self.assertEqual(result["dead"], 1)
        db = self._session()
        try:
            self.assertEqual(db.query(self.AR).one().url_status, "dead")
        finally:
            db.close()

    def test_builtin_checks_the_external_apply_target(self) -> None:
        builtin_url = "https://builtin.com/job/data-engineering-manager/8376822"
        direct_url = "https://job-boards.greenhouse.io/acme/jobs/456"
        self._add("Expired behind aggregator", url=builtin_url, source="builtin")

        def fake_head(url, **_kwargs):
            if url == direct_url:
                return _Resp(200, "https://job-boards.greenhouse.io/acme?error=true")
            return _Resp(200, url)

        with (
            patch("requests.head", side_effect=fake_head),
            patch(
                "job_finder.tools.scrapers.builtin.fetch_builtin_detail",
                return_value={"direct_application_url": direct_url},
            ),
        ):
            db = self._session()
            try:
                result = self.svc.check_urls(db)
            finally:
                db.close()

        self.assertEqual(result["dead"], 1)
        db = self._session()
        try:
            self.assertEqual(db.query(self.AR).one().url_status, "dead")
        finally:
            db.close()

    def test_web3career_http_200_closed_banner_is_dead(self) -> None:
        url = "https://web3.career/data-engineer-bitgo/69250"
        self._add("Closed at Web3.career", url=url, source="web3career")

        with (
            patch("requests.head", return_value=_Resp(200, url)),
            patch(
                "requests.get",
                return_value=_PageResp(200, "Apply Now: This job is closed", url),
            ) as get,
        ):
            db = self._session()
            try:
                result = self.svc.check_urls(db)
            finally:
                db.close()

        self.assertEqual(result, {"checked": 1, "alive": 0, "dead": 1, "unknown": 0})
        get.assert_called_once()
        db = self._session()
        try:
            self.assertEqual(db.query(self.AR).one().url_status, "dead")
        finally:
            db.close()

    def test_aggregator_copy_missing_from_known_greenhouse_board_is_dead(self) -> None:
        self._add(
            "Founding Sr. Data Engineer",
            url="https://www.indeed.com/viewjob?jk=stale",
            source="indeed",
        )

        def fake_get(url, **_kwargs):
            self.assertIn("boards-api.greenhouse.io", url)
            return _JsonResp(200, {"jobs": [{"title": "Fleet Engineer"}]}, url)

        with (
            patch("requests.head", return_value=_Resp(200)),
            patch("requests.get", side_effect=fake_get),
            patch(
                "job_finder.config.company_catalog.lookup_company",
                return_value={
                    "name": "Diligent Robotics",
                    "ats": "greenhouse",
                    "slug": "diligentrobotics",
                },
            ),
        ):
            db = self._session()
            try:
                result = self.svc.check_urls(db)
            finally:
                db.close()

        self.assertEqual(result, {"checked": 1, "alive": 0, "dead": 1, "unknown": 0})
        db = self._session()
        try:
            self.assertEqual(db.query(self.AR).one().url_status, "dead")
        finally:
            db.close()

    def test_ashby_uses_live_board_membership_despite_http_200_job_shell(self) -> None:
        live_id = "9721a4c7-ff1e-47ca-a89e-97688ebff96c"
        gone_id = "c8f46a18-3347-42e6-9fae-c0dbc3e89618"
        self._add(
            "Live at Ashby",
            url=f"https://jobs.ashbyhq.com/hackerone/{live_id}",
            source="ashby",
        )
        self._add(
            "Gone at Ashby",
            url=f"https://jobs.ashbyhq.com/hackerone/{gone_id}",
            source="ashby",
        )

        with (
            patch(
                "requests.get",
                return_value=_JsonResp(200, {"jobs": [{"id": live_id}]}),
            ) as get,
            patch("requests.head") as head,
        ):
            db = self._session()
            try:
                result = self.svc.check_urls(db)
            finally:
                db.close()

        self.assertEqual(result, {"checked": 2, "alive": 1, "dead": 1, "unknown": 0})
        get.assert_called_once()
        head.assert_not_called()
        db = self._session()
        try:
            by_title = {row.job_title: row.url_status for row in db.query(self.AR).all()}
        finally:
            db.close()
        self.assertEqual(by_title["Live at Ashby"], "alive")
        self.assertEqual(by_title["Gone at Ashby"], "dead")

    def test_ashby_api_block_does_not_hide_the_job(self) -> None:
        self._add(
            "Unverifiable at Ashby",
            url="https://jobs.ashbyhq.com/acme/job-id",
            source="ashby",
        )

        with patch("requests.get", return_value=_JsonResp(429, {})):
            db = self._session()
            try:
                result = self.svc.check_urls(db)
            finally:
                db.close()

        self.assertEqual(result, {"checked": 1, "alive": 0, "dead": 0, "unknown": 1})
        db = self._session()
        try:
            self.assertEqual(db.query(self.AR).one().url_status, "unknown")
        finally:
            db.close()

    def test_search_run_scope_checks_the_fresh_pull_not_oldest_global_rows(self) -> None:
        self._add("Older unrelated", url="https://x/old", search_run_id="old-run")
        self._add("Current result", url="https://x/current", search_run_id="new-run")

        with patch("requests.head", return_value=_Resp(404)):
            db = self._session()
            try:
                result = self.svc.check_urls(db, search_run_id="new-run")
            finally:
                db.close()

        self.assertEqual(result, {"checked": 1, "alive": 0, "dead": 1, "unknown": 0})
        db = self._session()
        try:
            by_title = {row.job_title: row.url_status for row in db.query(self.AR).all()}
        finally:
            db.close()
        self.assertEqual(by_title["Older unrelated"], "unknown")
        self.assertEqual(by_title["Current result"], "dead")


if __name__ == "__main__":
    unittest.main()
