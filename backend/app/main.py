from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.chat import chat
from app.database import get_db, get_info


app = FastAPI(title="Interdimensional Oracle")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str
    previous_response_id: str | None = None
    last_entity: dict | None = None

    model_config = {
        "json_schema_extra": {"example": {"question": "Who is Rick Sanchez?"}}
    }


@app.get("/api/health")
def health():
    db = get_db()
    db.execute("SELECT 1")
    db.close()
    return {"status": "ok"}


@app.get("/api/info")
def info():
    data = get_info()
    return {
        "characters": data["characters"]["count"],
        "episodes": data["episodes"]["count"],
        "locations": data["locations"]["count"],
    }


@app.post("/api/chat")
def api_chat(request: ChatRequest):
    return chat(
        request.question,
        request.previous_response_id,
        request.last_entity,
    )
