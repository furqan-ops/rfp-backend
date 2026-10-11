# Vector Store Choice: InMemoryVectorStore is used consistently for this demo so the pipeline runs locally with zero external database dependencies.
"""
LangChain Concept #1: Document Loaders, Text Splitters, Embeddings & Vector Stores
Loads enterprise security/SLA/RFP policy documents, splits them by Markdown headers
and recursive character boundaries, preserves citation metadata, and indexes into InMemoryVectorStore.
"""

import os
import re
import math
from pathlib import Path
from typing import List
from collections import Counter

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)


class LocalDomainKeywordEmbeddings(Embeddings):
    """
    Deterministic LangChain Embeddings implementation (subclasses `langchain_core.embeddings.Embeddings`).
    Used automatically when no cloud API key (GEMINI_API_KEY / OPENAI_API_KEY) is set in `.env`,
    allowing you to test the full LangChain + LangGraph pipeline offline with high domain accuracy.
    """

    VOCAB = [
        "encrypt", "aes-256", "tls", "kms", "rotate", "365", "rest", "transit", "hmac", "sha256",
        "soc", "soc2", "type", "hipaa", "baa", "gdpr", "ccpa", "iso", "27001", "fedramp",
        "zdr", "zero", "retention", "train", "llm", "foundation", "model", "prompt", "privacy",
        "delete", "deletion", "purge", "30", "60", "90", "destroy", "termination", "audit",
        "sla", "uptime", "99.95", "credit", "rto", "rpo", "4", "15", "disaster", "recovery", "pitr",
        "p1", "p2", "p3", "incident", "breach", "pagerduty", "response", "critical", "outage",
        "webhook", "500", "1500", "rps", "rate", "limit", "dlq", "retry", "backoff", "idempotency",
        "duplicate", "hallucination", "hitl", "human", "confidence", "0.80", "citation", "grounded",
        "pgvector", "supabase", "rls", "hubspot", "gohighlevel", "ghl", "salesforce", "whatsapp",
        "n8n", "sap", "erp", "mainframe", "air-gapped", "on-premise", "binary", "timeline",
        "week", "implementation", "onboarding", "pricing", "1500", "3500", "sso", "saml", "mfa",
        "pentest", "penetration", "vulnerability", "cvss", "patch"
    ]

    def _tokenize(self, text: str) -> List[str]:
        cleaned = re.sub(r"[^a-z0-9.\-]", " ", text.lower())
        return [tok for tok in cleaned.split() if len(tok) > 1]

    def _embed_single(self, text: str) -> List[float]:
        tokens = self._tokenize(text)
        counts = Counter(tokens)
        vec: List[float] = []
        raw_lower = text.lower()
        for term in self.VOCAB:
            score = float(counts.get(term, 0)) + 1e-4
            if term in raw_lower:
                score += 1.5
            vec.append(score)
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_single(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed_single(text)


def get_embeddings() -> Embeddings:
    """Selects cloud embeddings (Google Gemini / OpenAI) if configured, or deterministic local embeddings."""
    provider = os.getenv("EMBEDDING_PROVIDER", "auto").lower()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    if provider in ("gemini", "auto") and gemini_key and not gemini_key.startswith("your_"):
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        return GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=gemini_key,
        )
    if provider in ("openai", "auto") and openai_key and not openai_key.startswith("your_"):
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model="text-embedding-3-small",
             api_key=openai_key,
        )
    return LocalDomainKeywordEmbeddings()


def load_and_split_knowledge_base(kb_dir: str | Path) -> List[Document]:
    """
    1. Loads all Markdown/Text documents from `data/knowledge_base/`.
    2. Splits first by Markdown semantic headers (`#`, `##`) using `MarkdownHeaderTextSplitter`.
    3. Splits oversized sections using `RecursiveCharacterTextSplitter` while preserving metadata.
    """
    kb_path = Path(kb_dir)
    if not kb_path.exists():
        raise FileNotFoundError(f"Knowledge base directory not found: {kb_path}")

    headers_to_split_on = [
        ("#", "document_header"),
        ("##", "section_header"),
    ]
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False,
    )
    recursive_splitter = RecursiveCharacterTextSplitter(
        chunk_size=700,
        chunk_overlap=100,
        separators=["\n## ", "\n- ", "\n", " ", ""],
    )

    all_chunks: List[Document] = []

    for file_path in sorted(kb_path.glob("*.md")):
        raw_text = file_path.read_text(encoding="utf-8")

        # Extract Document ID and Title from top metadata lines if present
        doc_id_match = re.search(r"#\s*Document ID:\s*(.+)", raw_text)
        title_match = re.search(r"#\s*Title:\s*(.+)", raw_text)
        doc_id = doc_id_match.group(1).strip() if doc_id_match else file_path.stem
        doc_title = title_match.group(1).strip() if title_match else file_path.name

        header_splits = md_splitter.split_text(raw_text)
        sub_chunks = recursive_splitter.split_documents(header_splits)

        for idx, chunk in enumerate(sub_chunks):
            section = chunk.metadata.get("section_header", "General Policy")
            chunk.metadata.update(
                {
                    "source_file": file_path.name,
                    "doc_id": doc_id,
                    "doc_title": doc_title,
                    "section_header": section,
                    "chunk_index": idx,
                }
            )
            all_chunks.append(chunk)

    return all_chunks


def build_vector_store(chunks: List[Document]) -> InMemoryVectorStore:
    """
    Builds and returns LangChain's `InMemoryVectorStore` consistently for the demo.
    """
    embeddings = get_embeddings()
    return InMemoryVectorStore.from_documents(documents=chunks, embedding=embeddings)
