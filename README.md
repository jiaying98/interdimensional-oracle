# Interdimensional Oracle

A grounded RAG-powered AI agent for exploring the Rick and Morty universe.

## Project structure

```text
backend/     API, ingestion, retrieval and chat
frontend/    Vue application
data/        Generated local data
```

## Data ingestion

The ingestion module downloads all characters, episodes, and locations and
stores them in SQLite with full-text search.

```powershell
cd backend
python -m app.ingestion
```

### Data consistency

The API contains a few inconsistent bidirectional relationships. A character
may reference an episode or location that does not reference the character
back. To keep ingestion deterministic, character records are the canonical
source for episode appearances and current locations.

The following inconsistencies were found during full data validation:

- Flansian references episodes 18 and 21, but those episodes do not list Flansian.
- Episode 10 lists Reggie, but Reggie's character record does not reference it.
- Flansian references Planet Squanch as the current location, but Planet Squanch
  does not list Flansian as a resident.

These differences come from the upstream API rather than the local ingestion.

Test retrieval with a natural-language question:

```powershell
python -m app.retrieval "Which episodes feature Summer Smith?"
```

Retrieval uses a schema-driven query plan rather than raw model-generated SQL.
The planner can request filtering, `IN`, partial matches, counts, distinct
values, grouping, `HAVING`, ordering, limits, simple yes/no checks, and known
table relationships. Episode dates are also stored in ISO format so earliest
and latest queries sort by real dates rather than display text.
The backend validates every table, field, operator, and relationship before it
builds a parameterized SQLite query. Chat connections are read-only, and data
modification requests are rejected. Ambiguous questions return a clarification
instead of guessing.

Show available data and example entities:

```powershell
python -m app.database
```

Run the retrieval tests:

```powershell
python -m unittest discover -s tests
```

## OpenAI

Install the backend dependency and set the API key:

```powershell
pip install -r requirements.txt
$env:OPENAI_API_KEY="your-key"
```

The chat flow uses `gpt-5.4-mini`, compact retrieval context, and structured
outputs. Query planning and answer generation each allow one validation retry;
there is no open-ended retry loop.

## Run locally

Start the backend in the first terminal:

```powershell
cd backend
$env:OPENAI_API_KEY="your-key"
python -m uvicorn app.main:app --reload
```

Start the Vue frontend in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173` in the browser.
