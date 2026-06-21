import unittest

from app.retrieval import retrieve


class RetrievalTests(unittest.TestCase):
    def test_character_details(self):
        result = retrieve("Who is Rick Sanchez?")
        self.assertEqual(result["results"][0]["name"], "Rick Sanchez")
        self.assertEqual(result["sources"][0]["url"], "https://rickandmortyapi.com/api/character/1")

    def test_character_episodes(self):
        result = retrieve("Which episodes feature Summer Smith?")
        episodes = result["results"][0]["episodes"]
        self.assertEqual(len(episodes), 42)
        self.assertEqual(episodes[0]["name"], "Rick Potion #9")

    def test_episode_characters(self):
        result = retrieve("Who appears in the Pilot episode?")
        names = [item["name"] for item in result["results"][0]["characters"]]
        self.assertIn("Rick Sanchez", names)
        self.assertIn("Morty Smith", names)

    def test_location_residents(self):
        result = retrieve("Who lives on the Citadel of Ricks?")
        names = [item["name"] for item in result["results"][0]["residents"]]
        self.assertIn("Rick Sanchez", names)

    def test_fuzzy_entity(self):
        result = retrieve("Tell me about Sanchez")
        self.assertTrue(result["results"])
        self.assertEqual(result["match_type"], "fts")

    def test_no_result(self):
        result = retrieve("How do I cook pasta?")
        self.assertEqual(result["results"], [])
        self.assertEqual(result["context"], "")

    def test_character_filter_returns_all_matches(self):
        result = retrieve("Who is alive?")
        self.assertEqual(result["match_type"], "filter")
        self.assertEqual(result["table"]["total"], 439)
        self.assertEqual(result["results"][0]["name"], "Rick Sanchez")

    def test_character_filter_combines_database_values(self):
        result = retrieve("Show me alive female aliens")
        self.assertTrue(result["results"])
        self.assertTrue(all(row["status"] == "Alive" for row in result["results"]))
        self.assertTrue(all(row["species"] == "Alien" for row in result["results"]))
        self.assertTrue(all(row["gender"] == "Female" for row in result["results"]))

    def test_character_collection(self):
        result = retrieve("List me all the characters")
        self.assertEqual(result["match_type"], "collection")
        self.assertEqual(result["table"]["type"], "characters")
        self.assertEqual(result["table"]["total"], 826)

    def test_episode_and_location_collections(self):
        episodes = retrieve("List all episodes")
        locations = retrieve("Show all locations")
        self.assertEqual(episodes["table"]["total"], 51)
        self.assertEqual(locations["table"]["total"], 126)

    def test_context_contains_source(self):
        result = retrieve("Who is Rick Sanchez?")
        self.assertIn("https://rickandmortyapi.com/api/character/1", result["context"])


if __name__ == "__main__":
    unittest.main()
