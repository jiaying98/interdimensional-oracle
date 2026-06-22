"""Expose the Oracle chat, health, database info, and feedback API routes."""

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.chat import chat
from app.database import get_db, get_info


feedback_path = Path(__file__).resolve().parents[2] / "data" / "feedback.jsonl"
app = FastAPI(title="Interdimensional Oracle")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str
    previous_response_id: str | None = None
    last_entity: dict | None = None
    last_query: dict | None = None

    model_config = {
        "json_schema_extra": {"example": {"question": "Who is Rick Sanchez?"}}
    }


class FeedbackRequest(BaseModel):
    conversation_id: str
    question: str
    answer: str
    helpful: bool


@app.get("/api/health")
def health():
    """Confirm that the API can open and query the local database."""
    db = get_db()
    db.execute("SELECT 1")
    db.close()
    return {"status": "ok"}


@app.get("/api/info")
def info():
    """Return the entity totals displayed on the frontend welcome screen."""
    data = get_info()
    return {
        "characters": data["characters"]["count"],
        "episodes": data["episodes"]["count"],
        "locations": data["locations"]["count"],
    }


@app.post("/api/chat")
def api_chat(request: ChatRequest):
    """Pass one question and its small conversation context to the chat flow."""
    return chat(
        request.question,
        request.previous_response_id,
        request.last_entity,
        request.last_query,
    )


@app.post("/api/feedback")
def feedback(request: FeedbackRequest):
    """Append helpful/not-helpful feedback to a local JSON Lines file."""
    record = request.model_dump()
    record["created_at"] = datetime.now(timezone.utc).isoformat()
    feedback_path.parent.mkdir(parents=True, exist_ok=True)
    with feedback_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"status": "saved"}
