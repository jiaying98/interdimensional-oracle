import json
import unittest

from app.chat import MAX_QUESTION_LENGTH, chat


class FakeResponse:
    def __init__(self, output, response_id="resp_test"):
        self.output_text = json.dumps(output)
        self.id = response_id


class FakeResponses:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def create(self, **request):
        self.calls.append(request)
        return FakeResponse(self.outputs.pop(0))


class FakeClient:
    def __init__(self, outputs):
        self.responses = FakeResponses(outputs)


class ChatTests(unittest.TestCase):
    def test_empty_question_does_not_call_llm(self):
        client = FakeClient([])
        result = chat("", client=client)
        self.assertEqual(result["sources"], [])
        self.assertEqual(len(client.responses.calls), 0)

    def test_long_question_does_not_call_llm(self):
        client = FakeClient([])
        result = chat("x" * (MAX_QUESTION_LENGTH + 1), client=client)
        self.assertEqual(result["sources"], [])
        self.assertEqual(len(client.responses.calls), 0)

    def test_no_data_does_not_call_llm(self):
        client = FakeClient([])
        result = chat("How do I cook pasta?", client=client)
        self.assertEqual(result["sources"], [])
        self.assertEqual(len(client.responses.calls), 0)

    def test_filter_returns_table_without_llm(self):
        client = FakeClient([])
        result = chat("Who is alive?", client=client)
        self.assertEqual(result["table"]["total"], 439)
        self.assertEqual(result["match_type"], "filter")
        self.assertEqual(len(client.responses.calls), 0)

    def test_collection_returns_table_without_llm(self):
        client = FakeClient([])
        result = chat("List me all the characters", client=client)
        self.assertEqual(result["table"]["total"], 826)
        self.assertEqual(result["match_type"], "collection")
        self.assertEqual(len(client.responses.calls), 0)

    def test_grounded_answer(self):
        source = "https://rickandmortyapi.com/api/character/1"
        client = FakeClient([
            {"answerable": True, "answer": "Rick Sanchez is human.", "source_urls": [source]}
        ])
        result = chat("Who is Rick Sanchez?", client=client)
        self.assertEqual(result["answer"], "Rick Sanchez is human.")
        self.assertEqual(result["sources"][0]["url"], source)
        self.assertEqual(len(client.responses.calls), 1)

    def test_invalid_source_is_retried_once(self):
        source = "https://rickandmortyapi.com/api/character/1"
        client = FakeClient([
            {"answerable": True, "answer": "Invalid", "source_urls": ["https://example.com"]},
            {"answerable": True, "answer": "Rick Sanchez is human.", "source_urls": [source]},
        ])
        result = chat("Who is Rick Sanchez?", client=client)
        self.assertEqual(result["answer"], "Rick Sanchez is human.")
        self.assertEqual(len(client.responses.calls), 2)

    def test_previous_response_id_is_forwarded(self):
        source = "https://rickandmortyapi.com/api/character/1"
        client = FakeClient([
            {"answerable": True, "answer": "His origin is Earth.", "source_urls": [source]}
        ])
        chat(
            "What is his origin?",
            previous_response_id="resp_previous",
            last_entity={"name": "Rick Sanchez"},
            client=client,
        )
        request = client.responses.calls[0]
        self.assertEqual(request["previous_response_id"], "resp_previous")

    def test_pronoun_uses_previous_entity_instead_of_filter(self):
        source = "https://rickandmortyapi.com/api/character/1"
        client = FakeClient([
            {"answerable": True, "answer": "Yes, Rick is alive.", "source_urls": [source]}
        ])

        result = chat(
            "Is he alive?",
            last_entity={"name": "Rick Sanchez"},
            client=client,
        )

        self.assertEqual(result["answer"], "Yes, Rick is alive.")
        self.assertEqual(result["last_entity"]["name"], "Rick Sanchez")
        self.assertEqual(result["match_type"], "exact")
        self.assertEqual(len(client.responses.calls), 1)


if __name__ == "__main__":
    unittest.main()
