"""Verify query plans against the real local SQLite data."""

import unittest

from app.database import get_db
from app.retrieval import retrieve


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


class RetrievalTests(unittest.TestCase):
    def test_character_lookup(self):
        result = retrieve("Who is Rick?", plan=plan(
            action="lookup",
            filters=[{"field": "name", "operator": "eq", "values": ["Rick Sanchez"]}],
        ))
        self.assertEqual(result["results"][0]["name"], "Rick Sanchez")
        self.assertEqual(result["match_type"], "lookup")

    def test_join_returns_character_episodes(self):
        result = retrieve("Which episodes feature Summer?", plan=plan(
            table="episodes",
            relation="episode_characters",
            filters=[{"field": "characters.name", "operator": "eq", "values": ["Summer Smith"]}],
        ))
        self.assertEqual(result["table"]["match_total"], 42)
        self.assertEqual(result["results"][0]["name"], "Rick Potion #9")

    def test_combined_filters_and_requested_limit(self):
        result = retrieve("List ten living human women on Earth", plan=plan(
            filters=[
                {"field": "status", "operator": "eq", "values": ["Alive"]},
                {"field": "species", "operator": "eq", "values": ["Human"]},
                {"field": "gender", "operator": "eq", "values": ["Female"]},
                {"field": "location_name", "operator": "contains", "values": ["Earth"]},
            ],
            limit=10,
        ))
        self.assertEqual(len(result["results"]), 10)
        self.assertGreater(result["table"]["match_total"], 10)
        self.assertTrue(all("earth" in row["location"].lower() for row in result["results"]))

    def test_in_filter(self):
        result = retrieve("Humans or aliens", plan=plan(
            filters=[{"field": "species", "operator": "in", "values": ["Human", "Alien"]}],
        ))
        self.assertTrue(all(row["species"] in {"Human", "Alien"} for row in result["results"]))

    def test_count_rows(self):
        result = retrieve("How many characters?", plan=plan(action="count"))
        self.assertEqual(result["results"], [{"count": 826}])

    def test_filtered_count_also_returns_matching_records(self):
        result = retrieve("How many dead characters live on the Citadel?", plan=plan(
            action="count",
            filters=[
                {"field": "status", "operator": "eq", "values": ["Dead"]},
                {"field": "location_name", "operator": "eq", "values": ["Citadel of Ricks"]},
            ],
        ))
        self.assertEqual(result["summary"]["count"], 37)
        self.assertEqual(result["table"]["title"], "37 matching characters")
        self.assertEqual(len(result["table"]["rows"]), 37)
        self.assertTrue(all(row["status"] == "Dead" for row in result["table"]["rows"]))

    def test_group_returns_statuses_and_counts(self):
        result = retrieve("How many statuses?", plan=plan(
            action="group",
            field="status",
            order_by={"field": "count", "direction": "desc"},
        ))
        self.assertEqual(len(result["results"]), 3)
        self.assertEqual(sum(row["count"] for row in result["results"]), 826)
        self.assertEqual({row["value"] for row in result["results"]}, {"Alive", "Dead", "unknown"})

    def test_group_having_and_order(self):
        result = retrieve("Species with over 100 characters", plan=plan(
            action="group",
            field="species",
            having={"operator": "gt", "value": 100},
            order_by={"field": "count", "direction": "desc"},
        ))
        self.assertTrue(all(row["count"] > 100 for row in result["results"]))
        self.assertEqual(result["results"], sorted(result["results"], key=lambda row: row["count"], reverse=True))

    def test_extreme_uses_normalized_episode_date(self):
        result = retrieve("Which Summer episode aired first?", plan=plan(
            action="extreme",
            answer_mode="entity",
            table="episodes",
            field="air_date_iso",
            relation="episode_characters",
            filters=[{"field": "characters.name", "operator": "eq", "values": ["Summer Smith"]}],
            order_by={"field": "air_date_iso", "direction": "asc"},
            limit=1,
        ))
        self.assertEqual(result["results"][0]["name"], "Rick Potion #9")
        self.assertEqual(result["results"][0]["air_date_iso"], "2014-01-27")

    def test_extreme_keeps_previous_year_filter(self):
        result = retrieve("Which 2014 episode aired first?", plan=plan(
            action="extreme",
            answer_mode="entity",
            table="episodes",
            field="air_date_iso",
            filters=[{"field": "air_date_iso", "operator": "contains", "values": ["2014"]}],
            order_by={"field": "air_date_iso", "direction": "asc"},
            limit=1,
        ))
        self.assertEqual(result["results"][0]["name"], "M. Night Shaym-Aliens!")
        self.assertEqual(result["results"][0]["air_date_iso"], "2014-01-13")

    def test_check_all_matching_records(self):
        result = retrieve("Are they all male?", plan=plan(
            action="check",
            answer_mode="boolean",
            filters=[
                {"field": "status", "operator": "eq", "values": ["Dead"]},
                {"field": "location_name", "operator": "eq", "values": ["Citadel of Ricks"]},
            ],
            quantifier="all",
            check={"field": "gender", "operator": "eq", "values": ["Male"]},
        ))
        self.assertEqual(result["results"][0], {
            "result": True, "total": 37, "matching": 37
        })

    def test_database_connection_is_read_only(self):
        db = get_db()
        with self.assertRaises(Exception):
            db.execute("DELETE FROM characters")
        db.close()

    def test_distinct_values(self):
        result = retrieve("What genders exist?", plan=plan(action="distinct", field="gender"))
        self.assertEqual({row["value"] for row in result["results"]}, {
            "Female", "Genderless", "Male", "unknown"
        })

    def test_clarification_does_not_query(self):
        result = retrieve("How many locations does Rick have?", plan=plan(
            action="clarify",
            question="Do you mean Rick's origin or current location?",
        ))
        self.assertEqual(result["match_type"], "clarify")
        self.assertIn("origin", result["answer"])

    def test_invalid_field_is_rejected(self):
        result = retrieve("Bad field", plan=plan(
            table="episodes",
            field="status",
            action="distinct",
        ))
        self.assertEqual(result["results"], [])
        self.assertIsNone(result["match_type"])


if __name__ == "__main__":
    unittest.main()
