# Interdimensional Oracle

A grounded Rick and Morty assistant built with FastAPI, SQLite, OpenAI, and Vue.
It downloads the public API, retrieves local facts, and returns answers with
source links instead of relying on the model's memory.

## What the MVP includes

- **Data ingestion:** Downloads every page of characters, episodes, and locations
- **Local knowledge base:** SQLite tables, relationships, and an FTS index
- **Query planning:** Schema-driven plans for filters, joins, counts, groups, and dates
- **Safe retrieval:** Validated fields and parameterized read-only `SELECT` queries
- **Grounded answers:** Compact database context, source URLs, and one validation retry
- **Guardrails:** Code-level input checks and prompt-level grounding rules
- **Backend API:** FastAPI chat, health, database information, and feedback endpoints
- **Frontend:** Vue chat, local conversation history, result tables, sources, and themes

## Request flow

- **User question:** Vue sends the question and conversation context to FastAPI
- **Guardrails:** Empty, long, off-topic, and data-modification requests are stopped
- **Query plan:** The model selects allowed tables, fields, filters, and relationships
- **SQLite retrieval:** The backend validates the plan and runs a parameterized query
- **Answer:** Lists and counts are returned directly; entity details use the grounded LLM
- **Response:** The frontend displays the answer, table, and API source links

## Project structure

```text
backend/app/    ingestion, retrieval, chat, database and FastAPI
backend/tests/  backend tests
frontend/       Vue and Vite interface
data/           generated database and feedback (not committed)
```

## Run locally from a fresh clone

Requirements: Git, Python 3.12+, and Node.js 20.19+.

All commands below use PowerShell.

### 1. Clone and install the backend

```powershell
git clone https://github.com/jiaying98/interdimensional-oracle.git
cd interdimensional-oracle
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

The repository is already configured for Git. Do not run `git init` after
cloning it.

### 2. Create the local environment file

```powershell
Copy-Item .env.example .env
```

Open `.env` and add the API key:

```text
OPENAI_API_KEY=your-key
OPENAI_MODEL=gpt-5.4-mini
```

`.env.example` is safe to commit. The real `.env` is ignored by Git and must
never be uploaded.

### 3. Download the data

```powershell
cd backend
python -m app.ingestion
```

This follows every API page and creates `data/oracle.db`. The generated database
is local and is not stored in Git.

### 4. Start the application

Keep the first terminal in `backend/` and start FastAPI:

```powershell
python -m uvicorn app.main:app --reload
```

Open a second terminal at the repository root and start Vue:

```powershell
cd frontend
npm install
npm run dev
```

- Frontend: `http://127.0.0.1:8080`
- Backend: `http://127.0.0.1:8000`
- API documentation: `http://127.0.0.1:8000/docs`

Both terminals must remain running while the application is in use.

## Test the project

Backend tests:

```powershell
cd backend
python -m unittest discover -s tests -v
cd ..
```

Frontend production build:

```powershell
cd frontend
npm run build
cd ..
```

Inspect the local database or test retrieval:

```powershell
cd backend
python -m app.database
python -m app.retrieval "Which episodes feature Summer Smith?"
```

## Example questions

- Who is Rick Sanchez?
- Which episodes feature Summer Smith?
- Who lives on the Citadel of Ricks?
- Which 2014 episode aired first?
- How many dead characters live on the Citadel of Ricks?
- Are they all male?
- How do I cook pasta? (rejected as off-topic)

## Safety and grounding

- Questions are length-checked and off-topic or data-modification requests stop early.
- SQLite connections are read-only and generated SQL is limited to parameterized `SELECT`.
- Invalid or empty retrieval results never reach answer generation.
- The answer prompt allows only retrieved context and known source URLs.
- Planning and answer validation retry at most once.
- Conversations remain in browser storage; feedback is written to `data/feedback.jsonl`.

## Data notes and limitations

- **Relationship source:** Character records define episode appearances and current locations
- **API inconsistencies:** Some reverse episode and location links do not match character records
- **Duplicate names:** Exact matches use the earliest API entity instead of merging dimensions
- **Available content:** The API provides structured facts, not dialogue or plot summaries
- **Conversation storage:** Chat history remains in the current browser
- **Feedback storage:** Helpful/not-helpful records remain in local `data/feedback.jsonl`
- **Not included:** Streaming, authentication, and cross-device conversation storage
