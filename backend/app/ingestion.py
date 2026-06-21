import json
import sqlite3
import time
from pathlib import Path
from urllib.request import Request, urlopen


api_url = "https://rickandmortyapi.com/api"
db_path = Path(__file__).resolve().parents[2] / "data" / "oracle.db"


def download(resource):
    url = f"{api_url}/{resource}"
    results = []

    while url:
        request = Request(url, headers={"User-Agent": "interdimensional-oracle"})
        with urlopen(request, timeout=30) as response:
            data = json.load(response)

        results.extend(data["results"])
        url = data["info"]["next"]
        print(f"{resource}: {len(results)} records")
        time.sleep(0.5)

    return results


characters = download("character")
episodes = download("episode")
locations = download("location")

character_names = {item["id"]: item["name"] for item in characters}
episode_names = {item["id"]: item["name"] for item in episodes}

db = sqlite3.connect(db_path)
db.execute("PRAGMA foreign_keys = ON")
db.executescript(
    """
    DROP TABLE IF EXISTS character_episodes;
    DROP TABLE IF EXISTS entity_fts;
    DROP TABLE IF EXISTS characters;
    DROP TABLE IF EXISTS episodes;
    DROP TABLE IF EXISTS locations;
    DROP TABLE IF EXISTS documents;

    CREATE TABLE locations (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT,
        dimension TEXT,
        url TEXT NOT NULL,
        created TEXT
    );

    CREATE TABLE episodes (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        air_date TEXT,
        code TEXT,
        url TEXT NOT NULL,
        created TEXT
    );

    CREATE TABLE characters (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT,
        species TEXT,
        type TEXT,
        gender TEXT,
        origin_name TEXT,
        origin_id INTEGER,
        location_name TEXT,
        location_id INTEGER,
        image TEXT,
        url TEXT NOT NULL,
        created TEXT,
        FOREIGN KEY (origin_id) REFERENCES locations(id),
        FOREIGN KEY (location_id) REFERENCES locations(id)
    );

    CREATE TABLE character_episodes (
        character_id INTEGER,
        episode_id INTEGER,
        PRIMARY KEY (character_id, episode_id),
        FOREIGN KEY (character_id) REFERENCES characters(id),
        FOREIGN KEY (episode_id) REFERENCES episodes(id)
    );

    CREATE VIRTUAL TABLE entity_fts USING fts5(
        kind UNINDEXED,
        ref_id UNINDEXED,
        title,
        content,
        source UNINDEXED
    );
    """
)

for item in locations:
    db.execute(
        "INSERT INTO locations VALUES (?, ?, ?, ?, ?, ?)",
        (
            item["id"],
            item["name"],
            item["type"],
            item["dimension"],
            item["url"],
            item["created"],
        ),
    )
    resident_names = [
        character_names[int(url.rsplit("/", 1)[-1])] for url in item["residents"]
    ]
    content = (
        f'{item["name"]} is a {item["type"]} in {item["dimension"]}. '
        f'Residents: {", ".join(resident_names)}.'
    )
    db.execute(
        "INSERT INTO entity_fts VALUES (?, ?, ?, ?, ?)",
        ("location", item["id"], item["name"], content, item["url"]),
    )

for item in episodes:
    db.execute(
        "INSERT INTO episodes VALUES (?, ?, ?, ?, ?, ?)",
        (
            item["id"],
            item["name"],
            item["air_date"],
            item["episode"],
            item["url"],
            item["created"],
        ),
    )
    cast_names = [
        character_names[int(url.rsplit("/", 1)[-1])] for url in item["characters"]
    ]
    content = (
        f'{item["name"]} is episode {item["episode"]}, aired on {item["air_date"]}. '
        f'Characters: {", ".join(cast_names)}.'
    )
    db.execute(
        "INSERT INTO entity_fts VALUES (?, ?, ?, ?, ?)",
        ("episode", item["id"], item["name"], content, item["url"]),
    )

for item in characters:
    origin_url = item["origin"]["url"]
    location_url = item["location"]["url"]
    origin_id = int(origin_url.rsplit("/", 1)[-1]) if origin_url else None
    location_id = int(location_url.rsplit("/", 1)[-1]) if location_url else None

    db.execute(
        "INSERT INTO characters VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            item["id"],
            item["name"],
            item["status"],
            item["species"],
            item["type"],
            item["gender"],
            item["origin"]["name"],
            origin_id,
            item["location"]["name"],
            location_id,
            item["image"],
            item["url"],
            item["created"],
        ),
    )

    episode_list = []
    for url in item["episode"]:
        episode_id = int(url.rsplit("/", 1)[-1])
        episode_list.append(episode_names[episode_id])
        db.execute(
            "INSERT INTO character_episodes VALUES (?, ?)",
            (item["id"], episode_id),
        )

    content = (
        f'{item["name"]} is {item["status"]}, {item["species"]}, '
        f'{item["gender"]}. Origin: {item["origin"]["name"]}. '
        f'Last known location: {item["location"]["name"]}. '
        f'Episodes: {", ".join(episode_list)}.'
    )
    db.execute(
        "INSERT INTO entity_fts VALUES (?, ?, ?, ?, ?)",
        ("character", item["id"], item["name"], content, item["url"]),
    )

db.commit()
db.close()

print(f"Created {db_path}")
