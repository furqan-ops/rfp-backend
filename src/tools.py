"""
LangChain Concept #5: Custom Tools (`@tool` decorator)
Wraps external actions (n8n Human-in-the-Loop escalation webhook + CSV/Markdown matrix export)
as standard LangChain `BaseTool` objects with typed arguments and docstrings.
"""

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any
import requests
from langchain_core.tools import tool


@tool
def dispatch_n8n_hitl_escalation(
    question_id: str,
    category: str,
    question: str,
    draft_answer: str,
    compliance_status: str,
    confidence_score: float,
    grader_reasoning: str,
) -> str:
    """
    Dispatches a low-confidence or unsupported RFP question to an n8n Human-in-the-Loop (HITL)
    webhook for Solutions Engineering review in Slack/Email, and logs the escalation locally.
    """
    payload = {
        "event": "RFP_HITL_ESCALATION_REQUIRED",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "question_id": question_id,
        "category": category,
        "question": question,
        "draft_answer": draft_answer,
        "compliance_status": compliance_status,
        "confidence_score": confidence_score,
        "grader_reasoning": grader_reasoning,
    }

    output_dir = Path("data/output")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = output_dir / "n8n_hitl_escalations.jsonl"
        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except OSError:
        jsonl_path = Path("/tmp/n8n_hitl_escalations.jsonl")
        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")

    webhook_url = os.getenv("N8N_HITL_WEBHOOK_URL", "").strip()
    if webhook_url and webhook_url.startswith("http") and "example.com" not in webhook_url:
        try:
            resp = requests.post(webhook_url, json=payload, timeout=5)
            return f"DISPATCHED_TO_N8N_HTTP_{resp.status_code}"
        except Exception as exc:
            return f"LOGGED_LOCALLY_N8N_OFFLINE ({exc})"

    return f"LOGGED_TO_{jsonl_path.as_posix()}"


@tool
def export_completed_rfp_matrix(records: List[Dict[str, Any]], output_csv_path: str) -> str:
    """
    Exports all completed RFP questionnaire responses, citations, confidence scores,
    and LangGraph routing decisions to a CSV file and a Markdown Executive Audit Report.
    """
    csv_path = Path(output_csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "question_id",
        "category",
        "question",
        "compliance_status",
        "answer",
        "source_document",
        "section_reference",
        "verbatim_quote",
        "confidence_score",
        "is_grounded",
        "needs_human_review",
        "routing_action",
        "grader_reasoning",
        "retrieved_chunks_count",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    # Also generate a readable Markdown audit summary alongside the CSV
    md_path = csv_path.with_name("completed_rfp_audit_report.md")
    auto_count = sum(1 for r in records if r.get("routing_action") == "AUTO_APPROVED")
    hitl_count = len(records) - auto_count
    avg_conf = (
        sum(float(r.get("confidence_score", 0.0)) for r in records) / len(records)
        if records
        else 0.0
    )

    lines = [
        "# Enterprise RFP & Security Questionnaire — LangChain + LangGraph Audit Report",
        "",
        f"- **Total Questions Processed:** `{len(records)}`",
        f"- **Auto-Approved (`>= 0.80` Confidence & Grounded):** `{auto_count}`",
        f"- **Escalated to Human-in-the-Loop (`< 0.80` or Unsupported):** `{hitl_count}`",
        f"- **Mean grader_confidence:** `{avg_conf:.3f}`",
        "",
        "## Response Matrix Summary",
        "",
        "| ID | Category | Status | Confidence | Source Document | Routing Decision |",
        "| :--- | :--- | :--- | :---: | :--- | :--- |",
    ]
    for r in records:
        lines.append(
            f"| `{r['question_id']}` | {r['category']} | `{r['compliance_status']}` | "
            f"**{float(r['confidence_score']):.2f}** | `{r['source_document']}` | `{r['routing_action']}` |"
        )

    lines.extend(["", "## Detailed Grounded Responses & Citations", ""])
    for r in records:
        badge = "AUTO_APPROVED" if r["routing_action"] == "AUTO_APPROVED" else "ESCALATED_TO_HUMAN_N8N"
        lines.extend(
            [
                f"### {r['question_id']} ({r['category']}) — `{badge}`",
                f"- **Client Question:** {r['question']}",
                f"- **Drafted Response:** {r['answer']}",
                f"- **Citation:** `{r['source_document']}` $\\rightarrow$ *{r['section_reference']}*",
                f"- **Verbatim Evidence:** > \"{r['verbatim_quote']}\"",
                f"- **Grader Audit (`{float(r['confidence_score']):.2f}`):** {r['grader_reasoning']}",
                "",
            ]
        )

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return f"Exported {len(records)} rows to {csv_path.as_posix()} and {md_path.as_posix()}"
