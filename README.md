# Enterprise RFP & Security Questionnaire Auto-Responder (`LangChain` + `LangGraph`)

Automated B2B RFP & Security Questionnaire response engine built with **LangChain**, **LangGraph**, **Pydantic Structured Outputs**, and **`InMemoryVectorStore`**.

> **Data Source Note (`data_source: "sample_policy_documents"`):** The policy documents in `data/knowledge_base/` (`01_Security_and_SOC2_Compliance_Policy.md`, `02_Architecture_and_SLA_Specification.md`, and `03_Past_Winning_RFP_Responses_2026.md`) are sample data written specifically for this demo.

---

## Architecture & LangChain Concepts Covered

| File | LangChain / LangGraph Concept | What It Does |
| :--- | :--- | :--- |
| [`src/ingest.py`](src/ingest.py) | **`Document`**, **`MarkdownHeaderTextSplitter`**, **`RecursiveCharacterTextSplitter`**, **`Embeddings`**, **`InMemoryVectorStore`** | Splits policy docs by semantic Markdown headers + recursive character windows while preserving `source_file`, `doc_id`, and `section_header` metadata. |
| [`src/retriever.py`](src/retriever.py) | **`VectorStoreRetriever`**, **`RunnableLambda`** | Converts `InMemoryVectorStore` into a LangChain `BaseRetriever` (`top_k=3`) and formats retrieved chunks into citation-tagged context blocks. |
| [`src/schemas.py`](src/schemas.py) | **Pydantic v2 Schemas (`BaseModel`, `Field`)** | Defines strict output contracts (`RFPAnswerOutput`, `HallucinationGrade`, `ProcessedRFPItem`) for `.with_structured_output()`. |
| [`src/chains.py`](src/chains.py) | **`ChatPromptTemplate`**, **LCEL (`\|`)**, **`.with_structured_output()`** | Composes two modular LCEL pipelines: `rfp_generation_chain` (grounded answer + citation) and `hallucination_grader_chain` (audits grounding & `grader_confidence`). |
| [`src/tools.py`](src/tools.py) | **`@tool` Decorator (`BaseTool`)** | Wraps `dispatch_n8n_hitl_escalation` (fires n8n webhook for `< 0.80` confidence items) and `export_completed_rfp_matrix` (CSV + Markdown audit report). |
| [`src/graph.py`](src/graph.py) | **`StateGraph`**, **`TypedDict` State**, **Conditional Edges** | Orchestrates `retrieve_node` $\rightarrow$ `generate_node` $\rightarrow$ `grade_node` $\rightarrow$ conditional branch to `auto_approve_node` (`>= 0.80`) or `escalate_hitl_node` (`< 0.80`). |
| [`api.py`](api.py) | **FastAPI Webhook Gateway + CORS + HITL Decision Log** | Exposes `GET /health`, `POST /webhook/rfp-question`, and `POST /webhook/hitl-decision` (saves reviewer approvals/rejections to `logs/hitl_decisions.jsonl`). |

---

## Quick Start

### 1. Run the Full 12-Question Enterprise RFP Batch Pipeline
```bash
python main.py
```
- Works **out-of-the-box** without API keys using the built-in deterministic LangChain `Embeddings` & `Runnable` fallback.
- To run against live cloud LLMs (`Gemini 2.5 Flash`, `Groq Llama 3.3 70B`, or `OpenAI GPT-4o-mini`) and `Supabase pgvector`, copy `.env.example` to `.env` and add your key.

### 2. Inspect Generated Outputs
- **Completed RFP Matrix (CSV):** [`data/output/completed_rfp_responses.csv`](data/output/completed_rfp_responses.csv)
- **Executive Audit Report (Markdown):** [`data/output/completed_rfp_audit_report.md`](data/output/completed_rfp_audit_report.md)
- **n8n HITL Escalation Payloads (JSONL):** [`data/output/n8n_hitl_escalations.jsonl`](data/output/n8n_hitl_escalations.jsonl)
