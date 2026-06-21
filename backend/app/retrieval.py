import json
import re
import sys

from app.database import get_db


def retrieve(question):
    db = get_db()
    text = question.lower()

    entities = db.execute(
        "SELECT kind, ref_id, title, source FROM entity_fts "
        "ORDER BY length(title) DESC, ref_id"
    ).fetchall()
    entity = next((row for row in entities if row["title"].lower() in text), None)
    match_type = "exact"

    if entity is None:
        filters = {}
        for field in ["status", "species", "gender"]:
            values = db.execute(
                f"SELECT DISTINCT {field} FROM characters "
                f"WHERE {field} != '' ORDER BY length({field}) DESC"
            ).fetchall()
            for row in values:
                value = row[0]
                plural = "s?" if field in {"species", "gender"} else ""
                if re.search(
                    rf"(?<!\w){re.escape(value.lower())}{plural}(?!\w)", text
                ):
                    filters[field] = value
                    break

        if filters:
            where = " AND ".join(f"lower({field}) = lower(?)" for field in filters)
            rows = [
                dict(row) for row in db.execute(
                    f"""
                    SELECT id, name, status, species, gender,
                           location_name AS location, url
                    FROM characters
                    WHERE {where}
                    ORDER BY id
                    """,
                    tuple(filters.values()),
                )
            ]
            sources = [
                {"type": "character", "name": row["name"], "url": row["url"]}
                for row in rows
            ]
            result = {
                "results": rows,
                "sources": sources,
                "context": json.dumps(
                    {"filters": filters, "total": len(rows)}, ensure_ascii=False
                ),
                "match_type": "filter",
                "filters": filters,
                "table": {
                    "type": "characters",
                    "total": len(rows),
                    "rows": rows,
                },
            }
            db.close()
            return result

        collection = next(
            (
                name
                for name in ["characters", "episodes", "locations"]
                if re.search(rf"(?<!\w){name}(?!\w)", text)
            ),
            None,
        )
        if collection == "characters":
            rows = [
                dict(row) for row in db.execute(
                    """
                    SELECT id, name, status, species, gender,
                           location_name AS location, url
                    FROM characters
                    ORDER BY id
                    """
                )
            ]
        elif collection == "episodes":
            rows = [
                dict(row) for row in db.execute(
                    "SELECT id, name, code, air_date, url FROM episodes ORDER BY id"
                )
            ]
        elif collection == "locations":
            rows = [
                dict(row) for row in db.execute(
                    "SELECT id, name, type, dimension, url FROM locations ORDER BY id"
                )
            ]
        else:
            rows = []

        if collection:
            kind = collection[:-1] if collection != "characters" else "character"
            sources = [
                {"type": kind, "name": row["name"], "url": row["url"]}
                for row in rows
            ]
            result = {
                "results": rows,
                "sources": sources,
                "context": json.dumps(
                    {"collection": collection, "total": len(rows)},
                    ensure_ascii=False,
                ),
                "match_type": "collection",
                "table": {
                    "type": collection,
                    "total": len(rows),
                    "rows": rows,
                },
            }
            db.close()
            return result

    if entity is None:
        ignored = {
            "a", "about", "an", "and", "are", "did", "do", "does", "from",
            "how", "in", "is", "me", "of", "on", "please", "tell", "the",
            "to", "what", "when", "where", "which", "who",
        }
        words = [word for word in re.findall(r"[a-z0-9]+", text) if word not in ignored]
        query = " OR ".join(words)
        entity = db.execute(
            "SELECT kind, ref_id, title, source FROM entity_fts "
            "WHERE entity_fts MATCH ? ORDER BY rank LIMIT 1",
            (query,),
        ).fetchone() if query else None
        match_type = "fts"

    if entity is None:
        db.close()
        return {"results": [], "sources": [], "context": "", "match_type": None}

    kind = entity["kind"]
    ref_id = entity["ref_id"]

    if kind == "character":
        result = dict(db.execute(
            """
            SELECT id, name, status, species, type, gender,
                   origin_name AS origin, origin_id,
                   location_name AS location, location_id,
                   image, url, created
            FROM characters
            WHERE id = ?
            """,
            (ref_id,),
        ).fetchone())
        result["episodes"] = [
            dict(row) for row in db.execute(
                """
                SELECT e.id, e.name, e.code, e.air_date, e.url
                FROM episodes e
                JOIN character_episodes ce ON ce.episode_id = e.id
                WHERE ce.character_id = ?
                ORDER BY e.id
                """,
                (ref_id,),
            )
        ]
    elif kind == "episode":
        result = dict(db.execute(
            """
            SELECT id, name, air_date, code, url, created
            FROM episodes
            WHERE id = ?
            """,
            (ref_id,),
        ).fetchone())
        result["characters"] = [
            dict(row) for row in db.execute(
                """
                SELECT c.id, c.name, c.status, c.species, c.url
                FROM characters c
                JOIN character_episodes ce ON ce.character_id = c.id
                WHERE ce.episode_id = ?
                ORDER BY c.id
                """,
                (ref_id,),
            )
        ]
    else:
        result = dict(db.execute(
            """
            SELECT id, name, type, dimension, url, created
            FROM locations
            WHERE id = ?
            """,
            (ref_id,),
        ).fetchone())
        result["residents"] = [
            dict(row) for row in db.execute(
                """
                SELECT id, name, status, species, url
                FROM characters
                WHERE location_id = ?
                ORDER BY id
                """,
                (ref_id,),
            )
        ]

    results = [result]
    sources = [
        {"type": kind, "name": entity["title"], "url": entity["source"]}
    ]
    context = json.dumps(
        {"entity": sources[0], "data": results},
        ensure_ascii=False,
        indent=2,
    )
    result = {
        "results": results,
        "sources": sources,
        "context": context,
        "match_type": match_type,
    }
    db.close()
    return result


if __name__ == "__main__":
    question = " ".join(sys.argv[1:])
    print(json.dumps(retrieve(question), indent=2, ensure_ascii=False))
