"""Verify that ingestion follows API pagination before writing the database."""

import unittest
from unittest.mock import patch

from app.ingestion import download


class IngestionTests(unittest.TestCase):
    @patch("app.ingestion.time.sleep")
    @patch("app.ingestion.json.load")
    @patch("app.ingestion.urlopen")
    def test_download_follows_next_until_null(self, mock_open, mock_load, _mock_sleep):
        mock_open.return_value.__enter__.return_value = object()
        mock_load.side_effect = [
            {"info": {"next": "https://example.test/page/2"}, "results": [{"id": 1}]},
            {"info": {"next": None}, "results": [{"id": 2}]},
        ]

        result = download("character")

        self.assertEqual(result, [{"id": 1}, {"id": 2}])
        self.assertEqual(mock_open.call_count, 2)


if __name__ == "__main__":
    unittest.main()
