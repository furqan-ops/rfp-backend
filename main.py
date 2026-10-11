"""
Main End-to-End Runner for the LangChain + LangGraph RFP & Security Questionnaire Auto-Responder.
Run:
    python main.py
"""

import csv
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv

from src.ingest import load_and_split_knowledge_base, build_vector_store
from src.retriever import get_rfp_retriever
from src.graph import build_rfp_langgraph
from src.tools import export_completed_rfp_matrix


def run_rfp_pipeline(
    kb_dir: str = "data/knowledge_base",
    questionnaire_csv: str = "data/questionnaires/incoming_enterprise_rfp_questionnaire.csv",
    output_csv: str = "data/output/completed_rfp_responses.csv",
) -> List[Dict[str, Any]]:
    load_dotenv()

    print("=" * 82)
    print("  RFP & SECURITY QUESTIONNAIRE AUTO-RESPONDER (LangChain + LangGraph + pgvector)")
    print("=" * 82)

    # 1. Load & Split Knowledge Base Documents
    print(f"\n[1/4] Ingesting & splitting knowledge base from '{kb_dir}'...")
    chunks = load_and_split_knowledge_base(kb_dir)
    print(f"      -> Created {len(chunks)} semantic chunks across {len({c.metadata['source_file'] for c in chunks})} policy documents.")

    # 2. Index into VectorStore & Create LangChain Retriever
    print("\n[2/4] Building VectorStore & Retriever (top_k=3)...")
    vector_store = build_vector_store(chunks)
    retriever = get_rfp_retriever(vector_store, top_k=3)

    # 3. Compile LangGraph Workflow (Retrieve -> Generate -> Grade -> Route)
    print("\n[3/4] Compiling LangGraph StateGraph (with Hallucination & Confidence Gate >= 0.80)...")
    app = build_rfp_langgraph(retriever)

    # Clear previous escalation log
    escalation_log = Path("data/output/n8n_hitl_escalations.jsonl")
    if escalation_log.exists():
        escalation_log.unlink()

    # 4. Process Incoming Questionnaire CSV
    q_path = Path(questionnaire_csv)
    with q_path.open("r", encoding="utf-8") as f:
        questions = list(csv.DictReader(f))

    print(f"\n[4/4] Processing {len(questions)} incoming enterprise RFP questions...\n")
    processed_records: List[Dict[str, Any]] = []

    for row in questions:
        qid = row["question_id"].strip()
        cat = row["category"].strip()
        q_text = row["question"].strip()

        final_state = app.invoke(
            {
                "question_id": qid,
                "category": cat,
                "question": q_text,
                "retrieved_docs": [],
                "formatted_context": "",
                "draft_output": None,
                "grade_output": None,
                "routing_action": "AUTO_APPROVED",
                "final_record": None,
            }
        )
        rec = final_state["final_record"].model_dump()
        processed_records.append(rec)

        status_icon = "[AUTO-APPROVED]" if rec["routing_action"] == "AUTO_APPROVED" else "[ESCALATED->n8n]"
        print(
            f"  {qid} | {status_icon:<17} | Conf: {rec['confidence_score']:.2f} | "
            f"Status: {rec['compliance_status']:<21} | Cite: {rec['source_document']}"
        )

    # Export using LangChain @tool
    export_msg = export_completed_rfp_matrix.invoke(
        {
            "records": processed_records,
            "output_csv_path": output_csv,
        }
    )

    auto_ok = sum(1 for r in processed_records if r["routing_action"] == "AUTO_APPROVED")
    escalated = len(processed_records) - auto_ok

    print("\n" + "=" * 82)
    print(f"  DONE: {auto_ok}/{len(processed_records)} Auto-Approved | {escalated}/{len(processed_records)} Escalated to Human-in-the-Loop (n8n)")
    print(f"  {export_msg}")
    print("=" * 82)
    return processed_records


if __name__ == "__main__":
    run_rfp_pipeline()
