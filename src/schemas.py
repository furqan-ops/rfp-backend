"""
LangChain Concept #3: Structured Output Schemas (Pydantic v2)
Used with `llm.with_structured_output(Schema)` to force deterministic JSON responses
instead of brittle regex parsing.
"""

from typing import Literal, List
from pydantic import BaseModel, Field


class RFPAnswerOutput(BaseModel):
    """Structured output schema for the primary RAG Generator Chain."""

    answer: str = Field(
        description=(
            "Concise, audit-ready enterprise response strictly grounded in the retrieved "
            "context. If the context explicitly states a capability is NOT supported, state "
            "that clearly. If evidence is missing, state that human verification is required."
        )
    )
    compliance_status: Literal[
        "FULLY_SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "NOT_SUPPORTED",
        "INSUFFICIENT_EVIDENCE",
    ] = Field(
        description="Categorization of whether our platform supports the requested requirement."
    )
    source_document: str = Field(
        description="Exact filename of the primary source document used (e.g., '01_Security_and_SOC2_Compliance_Policy.md' or 'NONE')."
    )
    section_reference: str = Field(
        description="Section header or Document ID where the evidence was found."
    )
    verbatim_quote: str = Field(
        description="Short verbatim quote or factual metric extracted directly from the retrieved chunk."
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Grader confidence score between 0.00 and 1.00 based on evidence match.",
    )


class HallucinationGrade(BaseModel):
    """Structured output schema for the LangGraph Self-Reflection / Grader Node."""

    is_grounded: bool = Field(
        description="True ONLY if every factual claim and number in the drafted answer exists in the retrieved chunks."
    )
    addresses_question: bool = Field(
        description="True if the drafted answer directly answers all parts of the client's RFP question."
    )
    grader_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Final audited grader_confidence score (0.00 to 1.00). Penalize heavily if any part of the question is unverified.",
    )
    needs_human_review: bool = Field(
        description="True if grader_confidence < 0.80, is_grounded is False, or compliance_status is INSUFFICIENT_EVIDENCE."
    )
    grader_reasoning: str = Field(
        description="One-sentence explanation of why the answer passed auto-approval or was routed to Human-in-the-Loop review."
    )


class ProcessedRFPItem(BaseModel):
    """Final combined record exported to CSV / Google Sheets / n8n Webhook."""

    question_id: str
    category: str
    question: str
    compliance_status: str
    answer: str
    source_document: str
    section_reference: str
    verbatim_quote: str
    confidence_score: float
    is_grounded: bool
    needs_human_review: bool
    routing_action: Literal["AUTO_APPROVED", "ESCALATED_TO_HUMAN_N8N"]
    grader_reasoning: str
    retrieved_chunks_count: int
