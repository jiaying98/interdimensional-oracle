"""Open the local SQLite database and summarize its available data."""

import sqlite3
import json
from pathlib import Path


db_path = Path(__file__).resolve().parents[2] / "data" / "oracle.db"


def get_db():
    db = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only = ON")
    return db


def get_info():
    db = get_db()
    info = {}

    for table in ["characters", "episodes", "locations", "character_episodes", "entity_fts"]:
        fields = [row["name"] for row in db.execute(f"PRAGMA table_info({table})")]
        foreign_keys = [
            {
                "field": row["from"],
                "references": f'{row["table"]}.{row["to"]}',
            }
            for row in db.execute(f"PRAGMA foreign_key_list({table})")
        ]
        table_info = {
            "count": db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
            "fields": fields,
            "foreign_keys": foreign_keys,
        }

        if "name" in fields:
            table_info["examples"] = [
                row[0]
                for row in db.execute(f"SELECT name FROM {table} ORDER BY id LIMIT 5")
            ]
        elif "title" in fields:
            table_info["examples"] = [
                row[0]
                for row in db.execute(f"SELECT title FROM {table} LIMIT 5")
            ]

        info[table] = table_info

    db.close()
    return info


if __name__ == "__main__":
    print(json.dumps(get_info(), indent=2, ensure_ascii=False))
