from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from job_finder.tools.scrapers import _utils


class ScraperHttpLoggingTest(unittest.TestCase):
    def test_expected_404_can_be_logged_quietly(self) -> None:
        response = Mock(status_code=404)
        error = requests.HTTPError("404 not found", response=response)
        response.raise_for_status.side_effect = error

        with patch("job_finder.tools.scrapers._utils.requests.get", return_value=response), patch.object(
            _utils.logger, "warning"
        ) as warning, patch.object(_utils.logger, "debug") as debug:
            result = _utils._get_json(
                "https://api.lever.co/v0/postings/openai",
                quiet_statuses={404},
            )

        self.assertIsNone(result)
        warning.assert_not_called()
        debug.assert_called_once()

    def test_unexpected_http_error_still_warns(self) -> None:
        response = Mock(status_code=500)
        error = requests.HTTPError("500 server error", response=response)
        response.raise_for_status.side_effect = error

        with patch("job_finder.tools.scrapers._utils.requests.get", return_value=response), patch.object(
            _utils.logger, "warning"
        ) as warning, patch.object(_utils.logger, "debug") as debug:
            result = _utils._get_json("https://api.lever.co/v0/postings/openai")

        self.assertIsNone(result)
        warning.assert_called_once()
        debug.assert_not_called()


if __name__ == "__main__":
    unittest.main()
