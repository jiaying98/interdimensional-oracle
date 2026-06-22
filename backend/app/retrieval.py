"""Plan safe database queries and return grounded Rick and Morty records."""

import json
import os
import re
import sys

from openai import OpenAI

from app.database import get_db


MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
MAX_RESULTS = 1000

# Only application tables and known relationships are available to the planner.
TABLES = {
    "characters": {
        "alias": "c",
        "label": "characters",
        "source": "https://rickandmortyapi.com/api/character",
        "display": [
            "id", "name", "status", "species", "gender",
            "location_name AS location", "url",
        ],
    },
    "episodes": {
        "alias": "e",
        "label": "episodes",
        "source": "https://rickandmortyapi.com/api/episode",
        "display": ["id", "name", "code", "air_date", "air_date_iso", "url"],
    },
    "locations": {
        "alias": "l",
        "label": "locations",
        "source": "https://rickandmortyapi.com/api/location",
        "display": ["id", "name", "type", "dimension", "url"],
    },
}

RELATIONS = {
    "none": {"base": None, "tables": set(), "sql": ""},
    "character_episodes": {
        "base": "characters",
        "tables": {"characters", "episodes"},
        "sql": (
            "JOIN character_episodes ce ON ce.character_id = c.id "
            "JOIN episodes e ON e.id = ce.episode_id"
        ),
    },
    "episode_characters": {
        "base": "episodes",
        "tables": {"episodes", "characters"},
        "sql": (
            "JOIN character_episodes ce ON ce.episode_id = e.id "
            "JOIN characters c ON c.id = ce.character_id"
        ),
    },
    "location_residents": {
        "base": "locations",
        "tables": {"locations", "characters"},
        "sql": "JOIN characters c ON c.location_id = l.id",
    },
    "origin_characters": {
        "base": "locations",
        "tables": {"locations", "characters"},
        "sql": "JOIN characters c ON c.origin_id = l.id",
    },
}

FIELD_NOTES = {
    "characters.origin_name": "where a character originally comes from",
    "characters.location_name": "a character's current known location",
    "characters.status": "whether a character is Alive, Dead, or unknown",
    "characters.species": "a character's species, such as Human or Alien",
    "episodes.air_date_iso": "the episode air date in sortable YYYY-MM-DD format",
}

RESTRICTED_SQL = re.compile(r"\b(DROP|DELETE|UPDATE|INSERT)\b", re.IGNORECASE)

PLAN_FORMAT = {
    "type": "json_schema",
    "name": "query_plan",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "lookup", "list", "count", "distinct", "group",
                    "extreme", "check", "clarify", "reject",
                ],
            },
            "answer_mode": {
                "type": "string",
                "enum": ["boolean", "scalar", "entity", "table"],
            },
            "table": {"type": "string", "enum": list(TABLES)},
            "field": {"type": "string"},
            "filters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "operator": {
                            "type": "string",
                            "enum": ["eq", "ne", "contains", "in", "gt", "gte", "lt", "lte"],
                        },
                        "values": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["field", "operator", "values"],
                    "additionalProperties": False,
                },
            },
            "distinct": {"type": "boolean"},
            "relation": {"type": "string", "enum": list(RELATIONS)},
            "quantifier": {"type": "string", "enum": ["all", "any", "none"]},
            "check": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "operator": {
                        "type": "string",
                        "enum": ["eq", "ne", "contains", "in", "gt", "gte", "lt", "lte"],
                    },
                    "values": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["field", "operator", "values"],
                "additionalProperties": False,
            },
            "having": {
                "type": "object",
                "properties": {
                    "operator": {"type": "string", "enum": ["none", "gt", "gte", "lt", "lte", "eq"]},
                    "value": {"type": "integer"},
                },
                "required": ["operator", "value"],
                "additionalProperties": False,
            },
            "order_by": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "direction": {"type": "string", "enum": ["asc", "desc"]},
                },
                "required": ["field", "direction"],
                "additionalProperties": False,
            },
            "limit": {"type": "integer"},
            "question": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": [
            "action", "answer_mode", "table", "field", "filters", "distinct",
            "relation", "quantifier", "check", "having", "order_by", "limit",
            "question", "confidence",
        ],
        "additionalProperties": False,
    },
}


def database_schema(db):
    """Read allowed columns and small categorical value sets from SQLite."""
    schema = {}
    for table in TABLES:
        columns = [row[1] for row in db.execute(f"PRAGMA table_info({table})")]
        schema[table] = {"columns": columns}

        # Small sets of real database values help the model use exact filters.
        values = {}
        for column in columns:
            count = db.execute(
                f'SELECT COUNT(DISTINCT "{column}") FROM "{table}"'
            ).fetchone()[0]
            if 0 < count <= 20:
                values[column] = [
                    row[0] for row in db.execute(
                        f'SELECT DISTINCT "{column}" FROM "{table}" '
                        f'WHERE "{column}" IS NOT NULL AND "{column}" != "" '
                        f'ORDER BY "{column}"'
                    )
                ]
        schema[table]["values"] = values
    return schema


def plan_query(question, schema, last_query=None, client=None, error=None):
    """Ask the model for a typed query plan, never for executable SQL."""
    if client is None:
        if not os.getenv("OPENAI_API_KEY"):
            return None
        client = OpenAI(max_retries=0, timeout=30.0)

    instructions = f"""Convert the question into one safe database query plan.
Available schema: {json.dumps(schema, ensure_ascii=False)}
Field meanings: {json.dumps(FIELD_NOTES, ensure_ascii=False)}
Available relations: {json.dumps({key: sorted(value['tables']) for key, value in RELATIONS.items()}, ensure_ascii=False)}

Use lookup for one named entity, list for records, count for totals, distinct for unique values,
and group for a value with COUNT(*). Use extreme with order_by and limit=1 for earliest,
latest, highest, or lowest questions. Use check for yes/no questions about whether all, any,
or none of the current result match one predicate; keep the current population in filters and
put only the tested predicate in check. Use field='*' when counting rows. Filters may use a
base column or a qualified related column such as characters.name. Use contains for partial
text and in for multiple accepted values. Convert written quantities to limit. A limit of 0
means no requested limit. Use order_by.field='count' for grouped counts.

Prefer a group plan when a user asks how many category values exist, so the answer can include
both the number of values and their names. Use location_name for where someone currently lives,
origin_name for where someone comes from, status for Alive/Dead, and species for Human/Alien.
For the category with the most or fewest records, use group with order_by.field='count',
direction='desc' or 'asc', and limit=1. Do not use extreme for grouped counts.
Use air_date_iso, never air_date, for episode date filtering and ordering. For follow-up questions,
preserve relevant filters and relations from the previous query unless the user replaces them.
Choose boolean, scalar, entity, or table as answer_mode according to the requested answer.
If the meaning is genuinely ambiguous, return clarify with a short question. If it is outside
the Rick and Morty database domain or asks to modify data, return reject. Never produce SQL or
invent a table or field.
Review the plan against the question before returning it."""

    prompt = f"QUESTION:\n{question}"
    if last_query:
        prompt += f"\n\nPREVIOUS QUERY CONTEXT:\n{json.dumps(last_query, ensure_ascii=False)}"
    if error:
        prompt += f"\n\nTHE PREVIOUS PLAN WAS INVALID:\n{error}\nReturn one corrected plan."

    try:
        response = client.responses.create(
            model=MODEL,
            reasoning={"effort": "low"},
            instructions=instructions,
            input=prompt,
            text={"verbosity": "low", "format": PLAN_FORMAT},
            max_output_tokens=800,
            store=False,
        )
        return json.loads(response.output_text)
    except Exception:
        return None


def qualified_field(field, base, relation, schema):
    """Resolve a planned field only when its table and column are allowed."""
    if field == "*":
        return "*"

    if "." in field:
        table, column = field.split(".", 1)
    else:
        table, column = base, field

    allowed_tables = {base} | RELATIONS[relation]["tables"]
    if table not in allowed_tables or column not in schema.get(table, {}).get("columns", []):
        raise ValueError(f"Invalid field: {field}")

    return f'{TABLES[table]["alias"]}."{column}"'


def validate_plan(plan, schema):
    """Reject invalid tables, fields, relations, operators, and limits before SQL."""
    if not plan or plan.get("action") not in {
        "lookup", "list", "count", "distinct", "group",
        "extreme", "check", "clarify", "reject",
    }:
        raise ValueError("Invalid action")
    if plan.get("answer_mode") not in {"boolean", "scalar", "entity", "table"}:
        raise ValueError("Invalid answer mode")
    if plan["action"] in {"clarify", "reject"}:
        return plan

    table = plan.get("table")
    relation = plan.get("relation")
    if table not in TABLES or relation not in RELATIONS:
        raise ValueError("Invalid table or relation")
    if relation != "none" and RELATIONS[relation]["base"] != table:
        raise ValueError("Relation does not start from the selected table")

    action = plan["action"]
    field = plan.get("field", "*")
    if action in {"distinct", "group"} and field == "*":
        raise ValueError("This action requires a field")
    qualified_field(field, table, relation, schema)

    allowed_operators = {"eq", "ne", "contains", "in", "gt", "gte", "lt", "lte"}
    for item in plan.get("filters", []):
        qualified_field(item["field"], table, relation, schema)
        if item.get("operator") not in allowed_operators or not item.get("values"):
            raise ValueError("A filter requires a valid operator and value")

    having = plan.get("having", {})
    if having.get("operator") != "none" and action != "group":
        raise ValueError("HAVING is only valid for grouped results")

    order_field = plan.get("order_by", {}).get("field", "")
    if order_field and order_field != "count":
        qualified_field(order_field, table, relation, schema)

    if action == "extreme":
        if order_field == "count" and field != "*":
            # Grouped extrema use COUNT ordering rather than entity-field ordering.
            plan["action"] = "group"
            action = "group"
            plan["limit"] = 1
        elif not order_field:
            raise ValueError("Extreme queries require an ordered field")
        else:
            plan["limit"] = 1

    if action == "check":
        check = plan.get("check", {})
        qualified_field(check.get("field", ""), table, relation, schema)
        if (
            check.get("operator") not in allowed_operators
            or not check.get("values")
            or plan.get("quantifier") not in {"all", "any", "none"}
        ):
            raise ValueError("Check queries require one complete predicate")
        if plan["answer_mode"] != "boolean":
            raise ValueError("Check queries require a boolean answer")

    plan["limit"] = min(max(plan.get("limit", 0), 0), MAX_RESULTS)
    return plan


def where_sql(plan, schema):
    """Compile validated filters into parameterized WHERE clauses."""
    conditions = []
    params = []
    operators = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "="}

    for item in plan["filters"]:
        field = qualified_field(item["field"], plan["table"], plan["relation"], schema)
        operator = item["operator"]
        values = item["values"]

        # Exact related names resolve to the earliest API ID instead of merging variants.
        filter_table, filter_column = (
            item["field"].split(".", 1)
            if "." in item["field"]
            else (plan["table"], item["field"])
        )
        if (
            filter_table != plan["table"]
            and filter_column == "name"
            and operator == "eq"
        ):
            filter_alias = TABLES[filter_table]["alias"]
            conditions.append(
                f'{filter_alias}.id = (SELECT MIN(id) FROM "{filter_table}" '
                'WHERE LOWER(name) = LOWER(?))'
            )
            params.append(values[0])
            continue

        if operator == "contains":
            conditions.append(f"LOWER(CAST({field} AS TEXT)) LIKE LOWER(?)")
            params.append(f"%{values[0]}%")
        elif operator == "in":
            placeholders = ", ".join("LOWER(?)" for _ in values)
            conditions.append(f"LOWER(CAST({field} AS TEXT)) IN ({placeholders})")
            params.extend(values)
        elif operator == "ne":
            conditions.append(f"LOWER(CAST({field} AS TEXT)) != LOWER(?)")
            params.append(values[0])
        elif operator == "eq":
            conditions.append(f"LOWER(CAST({field} AS TEXT)) = LOWER(?)")
            params.append(values[0])
        else:
            conditions.append(f"{field} {operators[operator]} ?")
            params.append(values[0])

    return ("WHERE " + " AND ".join(conditions) if conditions else ""), params


def select_db(db, sql, params=()):
    """Apply a final read-only check before executing generated SELECT SQL."""
    if not sql.lstrip().upper().startswith("SELECT") or RESTRICTED_SQL.search(sql):
        raise ValueError("Only read-only SELECT queries are allowed")
    return db.execute(sql, params)


def execute_plan(db, plan, schema):
    """Build and run one validated relational query with bound parameters."""
    table = plan["table"]
    alias = TABLES[table]["alias"]
    relation_sql = RELATIONS[plan["relation"]]["sql"]
    where, params = where_sql(plan, schema)
    base = f'FROM "{table}" {alias} {relation_sql} {where}'
    field = qualified_field(plan["field"], table, plan["relation"], schema)
    action = plan["action"]
    requested_limit = 1 if action == "lookup" else plan["limit"] or MAX_RESULTS
    limit = f"LIMIT {requested_limit}" if requested_limit else ""

    if action == "check":
        total = select_db(
            db, f"SELECT COUNT(DISTINCT {alias}.id) {base}", params
        ).fetchone()[0]
        check_plan = {**plan, "filters": [*plan["filters"], plan["check"]]}
        check_where, check_params = where_sql(check_plan, schema)
        check_base = f'FROM "{table}" {alias} {relation_sql} {check_where}'
        matching = select_db(
            db, f"SELECT COUNT(DISTINCT {alias}.id) {check_base}", check_params
        ).fetchone()[0]
        quantifier = plan["quantifier"]
        result = (
            total > 0 and matching == total if quantifier == "all"
            else matching > 0 if quantifier == "any"
            else matching == 0
        )
        return [{"result": result, "total": total, "matching": matching}], 1

    if action in {"lookup", "list", "extreme"}:
        columns = ", ".join(f"{alias}.{column}" for column in TABLES[table]["display"])
        order_field = plan["order_by"]["field"]
        order = (
            f"ORDER BY {qualified_field(order_field, table, plan['relation'], schema)} "
            f"{plan['order_by']['direction'].upper()}"
            if order_field else f"ORDER BY {alias}.id"
        )
        rows = [
            dict(row) for row in select_db(
                db,
                f"SELECT DISTINCT {columns} {base} {order} {limit}", params
            )
        ]
        total = select_db(
            db,
            f"SELECT COUNT(DISTINCT {alias}.id) {base}", params
        ).fetchone()[0]
        return rows, total

    if action == "count" and plan["field"] == "*":
        value = select_db(
            db,
            f"SELECT COUNT(DISTINCT {alias}.id) AS count {base}", params
        ).fetchone()[0]
        return [{"count": value}], 1

    if action == "distinct":
        rows = [
            dict(row) for row in select_db(
                db,
                f"SELECT DISTINCT {field} AS value {base} ORDER BY value {limit}", params
            )
        ]
        return rows, len(rows)

    having = ""
    if plan["having"]["operator"] != "none":
        operator = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "="}[
            plan["having"]["operator"]
        ]
        having = f"HAVING COUNT(*) {operator} ?"
        params = [*params, plan["having"]["value"]]

    order_field = plan["order_by"]["field"]
    order_expression = "count" if order_field == "count" else "value"
    order = f"ORDER BY {order_expression} {plan['order_by']['direction'].upper()}"
    rows = [
        dict(row) for row in select_db(
            db,
            f"SELECT {field} AS value, COUNT(*) AS count {base} "
            f"GROUP BY {field} {having} {order} {limit}",
            params,
        )
    ]
    return rows, len(rows)


def entity_details(db, table, item):
    """Expand one entity with its related episodes, characters, or residents."""
    if table == "characters":
        result = dict(db.execute(
            """
            SELECT id, name, status, species, type, gender,
                   origin_name AS origin, origin_id,
                   location_name AS location, location_id,
                   image, url, created
            FROM characters WHERE id = ?
            """,
            (item["id"],),
        ).fetchone())
        result["episodes"] = [
            dict(row) for row in db.execute(
                """
                SELECT e.id, e.name, e.code, e.air_date, e.url
                FROM episodes e
                JOIN character_episodes ce ON ce.episode_id = e.id
                WHERE ce.character_id = ? ORDER BY e.id
                """,
                (item["id"],),
            )
        ]
        return result

    if table == "episodes":
        result = dict(db.execute(
            "SELECT id, name, air_date, code, url, created FROM episodes WHERE id = ?",
            (item["id"],),
        ).fetchone())
        result["characters"] = [
            dict(row) for row in db.execute(
                """
                SELECT c.id, c.name, c.status, c.species, c.url
                FROM characters c
                JOIN character_episodes ce ON ce.character_id = c.id
                WHERE ce.episode_id = ? ORDER BY c.id
                """,
                (item["id"],),
            )
        ]
        return result

    result = dict(db.execute(
        "SELECT id, name, type, dimension, url, created FROM locations WHERE id = ?",
        (item["id"],),
    ).fetchone())
    result["residents"] = [
        dict(row) for row in db.execute(
            "SELECT id, name, status, species, url FROM characters WHERE location_id = ? ORDER BY id",
            (item["id"],),
        )
    ]
    return result


def retrieve(question, last_query=None, client=None, plan=None):
    """Plan, validate, execute, and package one source-backed retrieval result."""
    db = get_db()
    schema = database_schema(db)

    # A malformed plan receives one correction attempt; SQL is never executed first.
    if plan is None:
        error = None
        for _ in range(2):
            plan = plan_query(question, schema, last_query, client, error)
            try:
                plan = validate_plan(plan, schema)
                break
            except (KeyError, TypeError, ValueError) as exception:
                error = str(exception)
        else:
            db.close()
            return {"results": [], "sources": [], "context": "", "match_type": None}
    else:
        try:
            plan = validate_plan(plan, schema)
        except (KeyError, TypeError, ValueError):
            db.close()
            return {"results": [], "sources": [], "context": "", "match_type": None}

    if plan["action"] == "clarify":
        db.close()
        return {
            "results": [], "sources": [], "context": "",
            "match_type": "clarify", "answer": plan["question"], "query_context": plan,
        }
    if plan["action"] == "reject":
        db.close()
        return {
            "results": [], "sources": [], "context": "",
            "match_type": "reject",
            "answer": "I can only answer questions about the Rick and Morty database.",
        }

    try:
        rows, total = execute_plan(db, plan, schema)
    except Exception:
        db.close()
        return {"results": [], "sources": [], "context": "", "match_type": None}

    if not rows:
        db.close()
        return {
            "results": [], "sources": [], "context": "", "match_type": "query",
            "query_context": plan,
        }

    table = plan["table"]
    kind = table[:-1] if table != "characters" else "character"
    if plan["action"] == "lookup" and len(rows) == 1:
        item = entity_details(db, table, rows[0])
        source = {"type": kind, "name": item["name"], "url": item["url"]}
        result = {
            "results": [item],
            "sources": [source],
            "context": json.dumps({"entity": source, "data": [item]}, ensure_ascii=False),
            "match_type": "lookup",
            "query_context": plan,
            "last_entity": source,
        }
        db.close()
        return result

    summary = None
    if plan["action"] == "count" and plan["field"] == "*" and plan["filters"]:
        summary = {"count": rows[0]["count"]}
        detail_plan = {
            **plan,
            "action": "list",
            "field": "*",
            "having": {"operator": "none", "value": 0},
            "order_by": {"field": "", "direction": "asc"},
            "limit": min(summary["count"], MAX_RESULTS),
        }
        rows, total = execute_plan(db, detail_plan, schema)

    sources = []
    if plan["action"] in {"lookup", "list", "extreme"} or summary:
        sources = [
            {"type": kind, "name": row["name"], "url": row["url"]}
            for row in rows
        ]
    else:
        sources = [{"type": kind, "name": TABLES[table]["label"], "url": TABLES[table]["source"]}]

    table_result = {
        "type": (
            table
            if plan["action"] in {"lookup", "list", "extreme"} or summary
            else "aggregate"
        ),
        "total": len(rows),
        "match_total": total,
        "rows": rows,
    }
    if summary:
        table_result["title"] = f'{summary["count"]} matching {TABLES[table]["label"]}'
    elif plan["action"] == "extreme":
        table_result["title"] = f'1 matching {TABLES[table]["label"][:-1]}'
    if table_result["type"] == "aggregate":
        if plan["action"] == "count" and plan["field"] == "*":
            table_result["columns"] = [{"key": "count", "label": "Count"}]
            table_result["title"] = f'Total {TABLES[table]["label"]}'
        elif plan["action"] == "distinct":
            table_result["columns"] = [
                {"key": "value", "label": plan["field"].replace("_", " ").title()}
            ]
            table_result["title"] = f'{len(rows)} {plan["field"].replace("_", " ")} values'
        else:
            table_result["columns"] = [
                {"key": "value", "label": plan["field"].replace("_", " ").title()},
                {"key": "count", "label": TABLES[table]["label"].title()},
            ]
            table_result["title"] = f'{len(rows)} {plan["field"].replace("_", " ")} groups'

    result = {
        "results": rows,
        "sources": sources,
        "context": json.dumps(
            {"plan": plan, "summary": summary, "data": rows}, ensure_ascii=False
        ),
        "match_type": "query",
        "table": table_result,
        "query_context": plan,
    }
    if summary:
        result["summary"] = summary
    db.close()
    return result


if __name__ == "__main__":
    question = " ".join(sys.argv[1:])
    print(json.dumps(retrieve(question), indent=2, ensure_ascii=False))
