import unittest
from unittest.mock import patch

from app.main import ChatRequest, api_chat, health, info


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
        mock_chat.assert_called_once_with("Who is Rick Sanchez?", None, None)


if __name__ == "__main__":
    unittest.main()
