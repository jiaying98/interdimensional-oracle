"""Test the FastAPI route functions without starting a web server."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.main import FeedbackRequest, ChatRequest, api_chat, feedback, health, info


class MainTests(unittest.TestCase):
    def test_health(self):
        self.assertEqual(health(), {"status": "ok"})

    def test_info(self):
        self.assertEqual(
            info(), {"characters": 826, "episodes": 51, "locations": 126}
        )

    @patch("app.main.chat")
    def test_chat(self, mock_chat):
        mock_chat.return_value = {"answer": "Rick Sanchez is human.", "sources": []}
        request = ChatRequest(question="Who is Rick Sanchez?")

        result = api_chat(request)

        self.assertEqual(result["answer"], "Rick Sanchez is human.")
        mock_chat.assert_called_once_with("Who is Rick Sanchez?", None, None, None)

    def test_feedback_is_logged_locally(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "feedback.jsonl"
            request = FeedbackRequest(
                conversation_id="conversation-1",
                question="Who is Rick Sanchez?",
                answer="Rick Sanchez is human.",
                helpful=True,
            )
            with patch("app.main.feedback_path", path):
                result = feedback(request)

            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(result, {"status": "saved"})
            self.assertTrue(record["helpful"])
            self.assertEqual(record["conversation_id"], "conversation-1")


if __name__ == "__main__":
    unittest.main()
