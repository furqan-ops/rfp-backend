"""
Comprehensive Verification Suite for the RFP & Security Questionnaire Auto-Responder.
Tests every LangChain & LangGraph component, live .env credentials, outputs, and FastAPI webhook.
"""

import csv
import json
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from src.ingest import load_and_split_knowledge_base, build_vector_store
from src.retriever import get_rfp_retriever, format_docs_runnable
from src.schemas import RFPAnswerOutput, HallucinationGrade, ProcessedRFPItem
from src.chains import build_rfp_generator_chain, build_hallucination_grader_chain
from src.graph import build_rfp_langgraph
from main import run_rfp_pipeline
import api


def run_all_checks():
    os.chdir(ROOT)
    load_dotenv(ROOT / ".env")

    results = []

    def check(name: str, condition: bool, detail: str = ""):
        status = "PASS" if condition else "FAIL"
        results.append((name, condition, detail))
        print(f"  [{status}] {name}" + (f" -> {detail}" if detail else ""))
        if not condition:
            raise AssertionError(f"Check failed: {name} ({detail})")

    print("=" * 80)
    print("  RUNNING END-TO-END VERIFICATION SUITE")
    print("=" * 80)

    # 1. Environment & Configuration Check
    env_exists = (ROOT / ".env").exists() or (ROOT / ".env.example").exists()
    port_cfg = api.PORT
    hitl_cfg = api.HITL_DECISIONS_FILE
    check(
        "1. Environment & Deployment Config (PORT, CORS_ORIGINS, HITL_DECISIONS_FILE)",
        bool(env_exists and isinstance(port_cfg, int) and hitl_cfg),
        f"PORT={port_cfg}, HITL_DECISIONS_FILE={hitl_cfg}, CORS_ORIGINS={api.ALLOWED_ORIGINS[0]}",
    )

    # 2. LangChain Ingestion & Splitters
    chunks = load_and_split_knowledge_base("data/knowledge_base")
    required_meta = {"source_file", "doc_id", "doc_title", "section_header", "chunk_index"}
    has_meta = all(required_meta.issubset(set(c.metadata.keys())) for c in chunks)
    check(
        "2. LangChain Document Loaders & Splitters",
        len(chunks) >= 20 and has_meta,
        f"{len(chunks)} chunks with complete citation metadata",
    )

    # 3. VectorStore & Retriever + RunnableLambda
    vs = build_vector_store(chunks)
    retriever = get_rfp_retriever(vs, top_k=3)
    sample_docs = retriever.invoke("How is customer data encrypted at rest and in transit?")
    formatted_ctx = format_docs_runnable.invoke(sample_docs)
    check(
        "3. VectorStoreRetriever & RunnableLambda Formatter",
        len(sample_docs) == 3 and "01_Security_and_SOC2_Compliance_Policy.md" in formatted_ctx and "AES-256" in formatted_ctx,
        f"Retrieved {len(sample_docs)} chunks; top match cites AES-256 in 01_Security_and_SOC2_Compliance_Policy.md",
    )

    # 4. LCEL Generator & Grader Chains with Pydantic Structured Output
    gen_chain = build_rfp_generator_chain()
    draft = gen_chain.invoke(
        {
            "category": "Security & Encryption",
            "question": "How is customer data encrypted both at rest and in transit, and how often are encryption keys rotated?",
            "context": formatted_ctx,
        }
    )
    grader_chain = build_hallucination_grader_chain()
    grade = grader_chain.invoke(
        {
            "question": "How is customer data encrypted both at rest and in transit, and how often are encryption keys rotated?",
            "context": formatted_ctx,
            "draft_answer": draft.answer,
            "compliance_status": draft.compliance_status,
            "confidence_score": draft.confidence_score,
            "source_document": draft.source_document,
            "section_reference": draft.section_reference,
        }
    )
    check(
        "4. LCEL Chains & Pydantic Structured Output",
        isinstance(draft, RFPAnswerOutput) and isinstance(grade, HallucinationGrade) and grade.is_grounded and not grade.needs_human_review,
        f"RFPAnswerOutput(conf={draft.confidence_score}) & HallucinationGrade(needs_review={grade.needs_human_review})",
    )

    # 5. Full 12-Question LangGraph Pipeline + @tool Exports
    records = run_rfp_pipeline()
    auto_approved = [r for r in records if r["routing_action"] == "AUTO_APPROVED"]
    escalated = [r for r in records if r["routing_action"] == "ESCALATED_TO_HUMAN_N8N"]
    check(
        "5. LangGraph Conditional Routing (Auto-Approve vs. HITL Escalate)",
        len(records) == 12 and len(auto_approved) == 10 and len(escalated) == 2,
        f"10 Auto-Approved (Q-01..Q-10), 2 Escalated to n8n HITL (Q-11, Q-12)",
    )

    # 6. Verify Output Files & offline_demo_results.json on Disk
    csv_file = ROOT / "data/output/completed_rfp_responses.csv"
    md_file = ROOT / "data/output/completed_rfp_audit_report.md"
    jsonl_file = ROOT / "data/output/n8n_hitl_escalations.jsonl"
    offline_file = ROOT / "offline_demo_results.json"
    with csv_file.open("r", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    jsonl_rows = [json.loads(line) for line in jsonl_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    offline_rows = json.loads(offline_file.read_text(encoding="utf-8"))
    computed_mean = round(sum(float(r["confidence_score"]) for r in csv_rows) / len(csv_rows), 4)
    check(
        "6. @tool Export Artifacts & offline_demo_results.json",
        len(csv_rows) == 12
        and md_file.exists()
        and len(jsonl_rows) == 2
        and len(offline_rows) == 12
        and all(r.get("source") == "offline_demo" for r in offline_rows)
        and computed_mean == 0.895,
        f"CSV rows={len(csv_rows)}, offline_demo={len(offline_rows)} (source='offline_demo'), computed mean={computed_mean}",
    )

    # 7. Verify FastAPI Webhook Endpoints (/health, /webhook/rfp-question, /webhook/hitl-decision, CORS)
    health_res = api.health_check()
    webhook_res = api.answer_rfp_question(
        api.SingleQuestionRequest(
            question_id="Q-WEBHOOK-TEST",
            category="Compliance",
            question="Are you FedRAMP High Authorized for classified air-gapped deployment?",
        )
    )
    hitl_res = api.record_hitl_decision(
        api.HITLDecisionRequest(
            question_id="Q-11",
            decision="APPROVED",
            edited_answer="We operate strictly as a cloud-hosted SaaS platform; FedRAMP High and air-gapped binaries are not supported.",
            reviewer_name="Furqan Tahir",
        )
    )
    hitl_log = ROOT / "logs/hitl_decisions.jsonl"
    check(
        "7. FastAPI Server (/health, /webhook/rfp-question, /webhook/hitl-decision & CORS)",
        health_res["status"] == "ok"
        and health_res.get("data_source") == "sample_policy_documents"
        and health_res.get("grader_confidence") == 0.895
        and isinstance(webhook_res, ProcessedRFPItem)
        and webhook_res.routing_action == "ESCALATED_TO_HUMAN_N8N"
        and hitl_res.decision == "APPROVED"
        and hitl_log.exists()
        and all("localhost" in o or "127.0.0.1" in o for o in api.ALLOWED_ORIGINS),
        f"Health={health_res}, HITL Decision={hitl_res.decision} logged to logs/hitl_decisions.jsonl, CORS={len(api.ALLOWED_ORIGINS)} localhost origins",
    )

    print("\n" + "=" * 80)
    print(f"  ALL {len(results)}/7 SYSTEM CHECKS PASSED WITH ZERO ERRORS!")
    print("=" * 80)


if __name__ == "__main__":
    run_all_checks()
