"""Vector store retriever backed by FAISS + HuggingFace embeddings.

Keeps everything in-memory for simplicity.  Call ``initialize_knowledge_base``
at application startup to download documents, embed them, and populate the
global vector store.
"""

from __future__ import annotations

import logging

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from src.agent.tools import load_documents as _set_tool_chunks
from src.knowledge_base.loader import load_amazon_documents

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# ── Global singleton ────────────────────────────────────────────────

_vector_store: VectorStore | None = None


class VectorStore:
    """Thin wrapper around a FAISS index with HuggingFace embeddings."""

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        self._embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        self._store: FAISS | None = None

    def add_documents(self, docs: list[Document]) -> None:
        """Embed *docs* and add them to the FAISS index."""
        if not docs:
            logger.warning("No documents to add.")
            return

        if self._store is None:
            self._store = FAISS.from_documents(docs, self._embeddings)
        else:
            self._store.add_documents(docs)

        logger.info("Vector store now holds %d vectors.", self._store.index.ntotal)

    def search(self, query: str, k: int = 5) -> list[str]:
        """Return the top-*k* most relevant text chunks for *query*."""
        if self._store is None:
            return ["Knowledge base is empty."]

        results = self._store.similarity_search(query, k=k)
        return [doc.page_content for doc in results]


def get_vector_store() -> VectorStore:
    """Return the global VectorStore singleton (must call initialize first)."""
    if _vector_store is None:
        raise RuntimeError("Knowledge base not initialized. Call initialize_knowledge_base() first.")
    return _vector_store


def initialize_knowledge_base() -> VectorStore:
    """One-time startup routine: load docs, embed, and populate stores.

    Also pushes plain-text chunks into the agent tool's in-memory
    search index so ``search_financial_documents`` works immediately.
    """
    global _vector_store

    logger.info("Initializing knowledge base...")
    docs = load_amazon_documents()

    _vector_store = VectorStore()
    _vector_store.add_documents(docs)

    # Sync plain-text chunks to the keyword-based tool search
    _set_tool_chunks([doc.page_content for doc in docs])

    logger.info("Knowledge base ready.")
    return _vector_store
