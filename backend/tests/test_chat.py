"""Test chat orchestration with a small fake OpenAI client."""

import json
import unittest

from app.chat import MAX_QUESTION_LENGTH, chat


def plan(**changes):
    value = {
        "action": "list",
        "answer_mode": "table",
        "table": "characters",
        "field": "*",
        "filters": [],
        "distinct": False,
        "relation": "none",
        "quantifier": "any",
        "check": {"field": "name", "operator": "eq", "values": []},
        "having": {"operator": "none", "value": 0},
        "order_by": {"field": "", "direction": "asc"},
        "limit": 0,
        "question": "",
        "confidence": 1,
    }
    value.update(changes)
    return value


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
    def test_empty_and_long_questions_do_not_call_llm(self):
        client = FakeClient([])
        self.assertEqual(chat("", client=client)["sources"], [])
        self.assertEqual(chat("x" * (MAX_QUESTION_LENGTH + 1), client=client)["sources"], [])
        self.assertEqual(len(client.responses.calls), 0)

    def test_rejected_question_uses_planner_only(self):
        client = FakeClient([plan(action="reject")])
        result = chat("How do I cook pasta?", client=client)
        self.assertEqual(result["match_type"], "reject")
        self.assertEqual(len(client.responses.calls), 1)

    def test_list_returns_table_after_planning(self):
        client = FakeClient([plan(
            filters=[{"field": "status", "operator": "eq", "values": ["Alive"]}]
        )])
        result = chat("Who is alive?", client=client)
        self.assertEqual(result["table"]["match_total"], 439)
        self.assertEqual(result["match_type"], "query")
        self.assertEqual(len(client.responses.calls), 1)

    def test_written_number_is_supplied_by_planner(self):
        client = FakeClient([plan(
            filters=[{"field": "gender", "operator": "eq", "values": ["Female"]}],
            limit=5,
        )])
        result = chat("Give me five female character names", client=client)
        self.assertEqual(result["table"]["total"], 5)
        self.assertIn("5 of 148", result["answer"])

    def test_group_answer_includes_values(self):
        client = FakeClient([plan(
            action="group",
            field="status",
            order_by={"field": "count", "direction": "desc"},
        )])
        result = chat("How many statuses are there?", client=client)
        self.assertIn("3 distinct status values", result["answer"])
        self.assertIn("Alive", result["answer"])
        self.assertEqual(len(client.responses.calls), 1)

    def test_filtered_count_includes_readable_answer_and_names(self):
        client = FakeClient([plan(
            action="count",
            filters=[
                {"field": "status", "operator": "eq", "values": ["Dead"]},
                {"field": "location_name", "operator": "eq", "values": ["Citadel of Ricks"]},
            ],
        )])
        result = chat("How many dead characters live on the Citadel?", client=client)
        self.assertEqual(
            result["answer"],
            "There are 37 dead characters currently located at Citadel of Ricks.",
        )
        self.assertEqual(result["table"]["title"], "37 matching characters")
        self.assertTrue(result["table"]["rows"][0]["name"])

    def test_check_returns_a_natural_boolean_answer(self):
        client = FakeClient([plan(
            action="check",
            answer_mode="boolean",
            filters=[
                {"field": "status", "operator": "eq", "values": ["Dead"]},
                {"field": "location_name", "operator": "eq", "values": ["Citadel of Ricks"]},
            ],
            quantifier="all",
            check={"field": "gender", "operator": "eq", "values": ["Male"]},
        )])
        result = chat("Are they all male?", client=client)
        self.assertEqual(result["answer"], "Yes. All 37 matching characters are male.")
        self.assertNotIn("table", result)

    def test_extreme_returns_the_episode_and_display_date(self):
        client = FakeClient([plan(
            action="extreme",
            answer_mode="entity",
            table="episodes",
            field="air_date_iso",
            filters=[{"field": "air_date_iso", "operator": "contains", "values": ["2014"]}],
            order_by={"field": "air_date_iso", "direction": "asc"},
            limit=1,
        )])
        result = chat("Which 2014 episode aired first?", client=client)
        self.assertEqual(
            result["answer"],
            "The earliest episode is M. Night Shaym-Aliens!, with air date January 13, 2014.",
        )

    def test_mutation_request_is_rejected_before_planning(self):
        client = FakeClient([])
        result = chat("Delete all characters", client=client)
        self.assertEqual(result["match_type"], "reject")
        self.assertEqual(len(client.responses.calls), 0)

    def test_benign_update_phrase_is_not_blocked(self):
        client = FakeClient([plan(action="reject")])
        chat("Update me on Rick Sanchez", client=client)
        self.assertEqual(len(client.responses.calls), 1)

    def test_clarification_is_returned_without_answer_call(self):
        client = FakeClient([plan(
            action="clarify",
            question="Do you mean Rick Sanchez's origin or current location?",
        )])
        result = chat("How many locations does Rick have?", client=client)
        self.assertEqual(result["match_type"], "clarify")
        self.assertIn("current location", result["answer"])
        self.assertEqual(len(client.responses.calls), 1)

    def test_invalid_plan_is_corrected_once(self):
        client = FakeClient([
            plan(action="distinct", table="episodes", field="status"),
            plan(action="group", field="status"),
        ])
        result = chat("How many statuses are there?", client=client)
        self.assertIn("3 distinct status values", result["answer"])
        self.assertIn("previous plan was invalid", client.responses.calls[1]["input"].lower())
        self.assertEqual(len(client.responses.calls), 2)

    def test_grounded_lookup_uses_planner_then_answer(self):
        source = "https://rickandmortyapi.com/api/character/1"
        client = FakeClient([
            plan(
                action="lookup",
                filters=[{"field": "name", "operator": "eq", "values": ["Rick Sanchez"]}],
            ),
            {"answerable": True, "answer": "Rick Sanchez is human.", "source_urls": [source]},
        ])
        result = chat("Who is Rick Sanchez?", client=client)
        self.assertEqual(result["answer"], "Rick Sanchez is human.")
        self.assertEqual(result["sources"][0]["url"], source)
        self.assertEqual(len(client.responses.calls), 2)

    def test_invalid_answer_source_is_retried_once(self):
        source = "https://rickandmortyapi.com/api/character/1"
        client = FakeClient([
            plan(
                action="lookup",
                filters=[{"field": "name", "operator": "eq", "values": ["Rick Sanchez"]}],
            ),
            {"answerable": True, "answer": "Invalid", "source_urls": ["https://example.com"]},
            {"answerable": True, "answer": "Rick is human.", "source_urls": [source]},
        ])
        result = chat("Who is Rick?", client=client)
        self.assertEqual(result["answer"], "Rick is human.")
        self.assertEqual(len(client.responses.calls), 3)

    def test_previous_context_is_forwarded(self):
        source = "https://rickandmortyapi.com/api/character/1"
        client = FakeClient([
            plan(
                action="lookup",
                filters=[{"field": "name", "operator": "eq", "values": ["Rick Sanchez"]}],
            ),
            {"answerable": True, "answer": "Yes, Rick is alive.", "source_urls": [source]},
        ])
        result = chat(
            "Is he alive?",
            previous_response_id="resp_previous",
            last_entity={"name": "Rick Sanchez"},
            last_query={"table": "characters"},
            client=client,
        )
        planner_prompt = client.responses.calls[0]["input"]
        answer_request = client.responses.calls[1]
        self.assertIn("Rick Sanchez", planner_prompt)
        self.assertEqual(answer_request["previous_response_id"], "resp_previous")
        self.assertEqual(result["last_entity"]["name"], "Rick Sanchez")


if __name__ == "__main__":
    unittest.main()
