"""
LangChain Concept #2: Retrievers & Context Formatting Runnables
Converts the VectorStore into a Retriever interface and formats retrieved `Document`
chunks with explicit citation headers for the LCEL prompt pipeline.
"""

from typing import List, Optional
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableLambda
from langchain_core.vectorstores import InMemoryVectorStore


def get_rfp_retriever(
    vector_store: InMemoryVectorStore,
    top_k: int = 3,
    source_filter: Optional[str] = None,
) -> BaseRetriever:
    """
    Creates a LangChain Retriever (`VectorStoreRetriever`) with optional metadata filtering.
    """
    search_kwargs: dict = {"k": top_k}
    if source_filter:
        search_kwargs["filter"] = lambda doc: doc.metadata.get("source_file") == source_filter

    return vector_store.as_retriever(
        search_type="similarity",
        search_kwargs=search_kwargs,
    )


def format_retrieved_documents(docs: List[Document]) -> str:
    """
    Formats retrieved LangChain `Document` objects into an audit-traceable context block
    so the LLM can cite exact `source_file` and `section_header` metadata.
    """
    if not docs:
        return "NO_RELEVANT_DOCUMENTS_FOUND"

    formatted_blocks: List[str] = []
    for idx, doc in enumerate(docs, start=1):
        source_file = doc.metadata.get("source_file", "Unknown_Document.md")
        doc_id = doc.metadata.get("doc_id", "N/A")
        section = doc.metadata.get("section_header", "General Section")
        block = (
            f"[CHUNK #{idx} | FILE: {source_file} | DOC_ID: {doc_id} | SECTION: {section}]\n"
            f"{doc.page_content.strip()}"
        )
        formatted_blocks.append(block)

    return "\n\n---\n\n".join(formatted_blocks)


# LangChain Runnable wrapper for use inside LCEL pipe expressions (`|`)
format_docs_runnable = RunnableLambda(format_retrieved_documents)
