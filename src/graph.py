"""
LangChain Concept #6: LangGraph Stateful Orchestration & Conditional Routing
Defines a 4-node `StateGraph` (`retrieve_node` -> `generate_node` -> `grade_node` ->
conditional branch to `auto_approve_node` OR `escalate_hitl_node`).
"""

from typing import TypedDict, List, Optional, Literal
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langgraph.graph import StateGraph, START, END

from src.schemas import RFPAnswerOutput, HallucinationGrade, ProcessedRFPItem
from src.retriever import format_docs_runnable
from src.chains import build_rfp_generator_chain, build_hallucination_grader_chain
from src.tools import dispatch_n8n_hitl_escalation


class RFPGraphState(TypedDict):
    """Typed state dictionary passed between LangGraph nodes."""

    question_id: str
    category: str
    question: str
    retrieved_docs: List[Document]
    formatted_context: str
    draft_output: Optional[RFPAnswerOutput]
    grade_output: Optional[HallucinationGrade]
    routing_action: Literal["AUTO_APPROVED", "ESCALATED_TO_HUMAN_N8N"]
    final_record: Optional[ProcessedRFPItem]


def build_rfp_langgraph(retriever: BaseRetriever):
    """
    Compiles and returns the executable LangGraph workflow for RFP question answering
    with automatic hallucination grading and Human-in-the-Loop (HITL) escalation.
    """
    generator_chain = build_rfp_generator_chain()
    grader_chain = build_hallucination_grader_chain()

    def retrieve_node(state: RFPGraphState) -> dict:
        """Node 1: Retrieve top-k relevant policy chunks from VectorStore."""
        query = f"{state['category']}: {state['question']}"
        docs = retriever.invoke(query)
        context_str = format_docs_runnable.invoke(docs)
        return {
            "retrieved_docs": docs,
            "formatted_context": context_str,
        }

    def generate_node(state: RFPGraphState) -> dict:
        """Node 2: Run LCEL Generator Chain with `.with_structured_output(RFPAnswerOutput)`."""
        draft: RFPAnswerOutput = generator_chain.invoke(
            {
                "category": state["category"],
                "question": state["question"],
                "context": state["formatted_context"],
            }
        )
        return {"draft_output": draft}

    def grade_node(state: RFPGraphState) -> dict:
        """Node 3: Audit drafted answer for grounding, citations, and >= 0.80 confidence threshold."""
        draft = state["draft_output"]
        assert draft is not None
        grade: HallucinationGrade = grader_chain.invoke(
            {
                "question": state["question"],
                "context": state["formatted_context"],
                "draft_answer": draft.answer,
                "compliance_status": draft.compliance_status,
                "confidence_score": draft.confidence_score,
                "source_document": draft.source_document,
                "section_reference": draft.section_reference,
            }
        )
        return {"grade_output": grade}

    def route_after_grading(
        state: RFPGraphState,
    ) -> Literal["auto_approve_node", "escalate_hitl_node"]:
        """Conditional Edge: Routes grounded high-confidence answers to approval, others to n8n HITL."""
        grade = state["grade_output"]
        draft = state["draft_output"]
        if (
            grade is None
            or draft is None
            or grade.needs_human_review
            or not grade.is_grounded
            or grade.grader_confidence < 0.80
        ):
            return "escalate_hitl_node"
        return "auto_approve_node"

    def auto_approve_node(state: RFPGraphState) -> dict:
        """Node 4A: Marks response as AUTO_APPROVED and packages final record."""
        draft = state["draft_output"]
        grade = state["grade_output"]
        assert draft is not None and grade is not None
        record = ProcessedRFPItem(
            question_id=state["question_id"],
            category=state["category"],
            question=state["question"],
            compliance_status=draft.compliance_status,
            answer=draft.answer,
            source_document=draft.source_document,
            section_reference=draft.section_reference,
            verbatim_quote=draft.verbatim_quote,
            confidence_score=grade.grader_confidence,
            is_grounded=grade.is_grounded,
            needs_human_review=False,
            routing_action="AUTO_APPROVED",
            grader_reasoning=grade.grader_reasoning,
            retrieved_chunks_count=len(state["retrieved_docs"]),
        )
        return {
            "routing_action": "AUTO_APPROVED",
            "final_record": record,
        }

    def escalate_hitl_node(state: RFPGraphState) -> dict:
        """Node 4B: Invokes `@tool dispatch_n8n_hitl_escalation` and marks for human review."""
        draft = state["draft_output"]
        grade = state["grade_output"]
        assert draft is not None and grade is not None

        dispatch_n8n_hitl_escalation.invoke(
            {
                "question_id": state["question_id"],
                "category": state["category"],
                "question": state["question"],
                "draft_answer": draft.answer,
                "compliance_status": draft.compliance_status,
                "confidence_score": grade.grader_confidence,
                "grader_reasoning": grade.grader_reasoning,
            }
        )

        record = ProcessedRFPItem(
            question_id=state["question_id"],
            category=state["category"],
            question=state["question"],
            compliance_status=draft.compliance_status,
            answer=draft.answer,
            source_document=draft.source_document,
            section_reference=draft.section_reference,
            verbatim_quote=draft.verbatim_quote,
            confidence_score=grade.grader_confidence,
            is_grounded=grade.is_grounded,
            needs_human_review=True,
            routing_action="ESCALATED_TO_HUMAN_N8N",
            grader_reasoning=grade.grader_reasoning,
            retrieved_chunks_count=len(state["retrieved_docs"]),
        )
        return {
            "routing_action": "ESCALATED_TO_HUMAN_N8N",
            "final_record": record,
        }

    workflow = StateGraph(RFPGraphState)
    workflow.add_node("retrieve_node", retrieve_node)
    workflow.add_node("generate_node", generate_node)
    workflow.add_node("grade_node", grade_node)
    workflow.add_node("auto_approve_node", auto_approve_node)
    workflow.add_node("escalate_hitl_node", escalate_hitl_node)

    workflow.add_edge(START, "retrieve_node")
    workflow.add_edge("retrieve_node", "generate_node")
    workflow.add_edge("generate_node", "grade_node")
    workflow.add_conditional_edges(
        "grade_node",
        route_after_grading,
        {
            "auto_approve_node": "auto_approve_node",
            "escalate_hitl_node": "escalate_hitl_node",
        },
    )
    workflow.add_edge("auto_approve_node", END)
    workflow.add_edge("escalate_hitl_node", END)

    return workflow.compile()
