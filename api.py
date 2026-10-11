"""
FastAPI Webhook Server for n8n / Google Sheets / CRM Integration.
Run:
    uvicorn api:app --reload --port 8010
"""

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from src.ingest import load_and_split_knowledge_base, build_vector_store
from src.retriever import get_rfp_retriever
from src.graph import build_rfp_langgraph
from src.schemas import ProcessedRFPItem

load_dotenv()

PORT = int(os.getenv("PORT", "8010"))
HITL_DECISIONS_FILE = os.getenv("HITL_DECISIONS_FILE", "logs/hitl_decisions.jsonl")

DEFAULT_LOCALHOST_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://localhost:8010",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8010",
]
_raw_origins = os.getenv("CORS_ORIGINS") or os.getenv("CORS_ALLOWED_ORIGINS") or "http://localhost:3000"
_env_origins = [origin.strip() for origin in _raw_origins.split(",") if origin.strip()]
ALLOWED_ORIGINS = list(dict.fromkeys(_env_origins + DEFAULT_LOCALHOST_ORIGINS))

app = FastAPI(
    title="Enterprise RFP & Security Questionnaire Auto-Responder (LangChain + LangGraph)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize VectorStore and LangGraph once on startup
_chunks = load_and_split_knowledge_base("data/knowledge_base")
_vector_store = build_vector_store(_chunks)
_retriever = get_rfp_retriever(_vector_store, top_k=3)
_rfp_graph = build_rfp_langgraph(_retriever)


def compute_mean_grader_confidence(
    csv_path: str | Path = "data/output/completed_rfp_responses.csv",
) -> float:
    """Computes the exact mean confidence score from the 12 saved dataset rows."""
    p = Path(csv_path)
    if not p.exists():
        return 0.0
    with p.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    scores = [float(r["confidence_score"]) for r in rows if r.get("confidence_score") is not None]
    return round(sum(scores) / len(scores), 4) if scores else 0.0


class SingleQuestionRequest(BaseModel):
    question_id: str = "Q-API-01"
    category: str = "Security & Compliance"
    question: str


class HITLDecisionRequest(BaseModel):
    question_id: str
    decision: Literal["APPROVED", "REJECTED"]
    edited_answer: Optional[str] = None
    reviewer_name: str


class HITLDecisionRecord(BaseModel):
    timestamp_utc: str
    question_id: str
    decision: Literal["APPROVED", "REJECTED"]
    edited_answer: Optional[str] = None
    reviewer_name: str


@app.get("/")
def root_status():
    return {
        "service": "Enterprise RFP & Security Questionnaire Auto-Responder",
        "status": "ok",
        "indexed_chunks": len(_chunks),
        "confidence_threshold": 0.80,
        "grader_confidence": compute_mean_grader_confidence(),
        "endpoints": ["/health", "/webhook/rfp-question", "/webhook/hitl-decision", "/docs"],
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "indexed_chunks": len(_chunks),
        "confidence_threshold": 0.80,
        "grader_confidence": compute_mean_grader_confidence(),
        "data_source": "sample_policy_documents",
    }


@app.post("/webhook/rfp-question", response_model=ProcessedRFPItem)
def answer_rfp_question(req: SingleQuestionRequest):
    """n8n Webhook endpoint: processes a single RFP question through the LangGraph pipeline."""
    result = _rfp_graph.invoke(
        {
            "question_id": req.question_id,
            "category": req.category,
            "question": req.question,
            "retrieved_docs": [],
            "formatted_context": "",
            "draft_output": None,
            "grade_output": None,
            "routing_action": "AUTO_APPROVED",
            "final_record": None,
        }
    )
    return result["final_record"]


@app.post("/webhook/hitl-decision", response_model=HITLDecisionRecord)
def record_hitl_decision(req: HITLDecisionRequest):
    """
    Stores a Human-in-the-Loop reviewer decision (APPROVED or REJECTED) in HITL_DECISIONS_FILE
    with a UTC timestamp and returns the saved record. Does not call n8n.
    """
    saved_record = HITLDecisionRecord(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        question_id=req.question_id,
        decision=req.decision,
        edited_answer=req.edited_answer,
        reviewer_name=req.reviewer_name,
    )
    log_file = Path(os.getenv("HITL_DECISIONS_FILE", HITL_DECISIONS_FILE))
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(saved_record.model_dump()) + "\n")
    except OSError:
        fallback_file = Path("/tmp/hitl_decisions.jsonl")
        fallback_file.parent.mkdir(parents=True, exist_ok=True)
        with fallback_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(saved_record.model_dump()) + "\n")

    return saved_record


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=PORT)


