"""Document loader for Amazon financial PDFs.

Downloads PDFs from public URLs and falls back to local files in
docs/documents/ when a download fails.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).resolve().parents[2] / "docs" / "documents"

AMAZON_PDF_URLS: list[dict[str, str]] = [
    {
        "url": "https://s2.q4cdn.com/299287126/files/doc_financials/2025/ar/Amazon-2024-Annual-Report.pdf",
        "filename": "Amazon-2024-Annual-Report.pdf",
    },
    {
        "url": "https://s2.q4cdn.com/299287126/files/doc_financials/2025/q3/AMZN-Q3-2025-Earnings-Release.pdf",
        "filename": "AMZN-Q3-2025-Earnings-Release.pdf",
    },
    {
        "url": "https://s2.q4cdn.com/299287126/files/doc_financials/2025/q2/AMZN-Q2-2025-Earnings-Release.pdf",
        "filename": "AMZN-Q2-2025-Earnings-Release.pdf",
    },
]

TEXT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def _download_pdf(url: str, dest: Path) -> bool:
    """Download a PDF to *dest*. Returns True on success."""
    try:
        with httpx.Client(follow_redirects=True, timeout=60) as client:
            resp = client.get(url)
            resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        logger.info("Downloaded %s -> %s", url, dest)
        return True
    except Exception as e:
        logger.warning("Failed to download %s: %s", url, e)
        return False


def _load_single_pdf(path: Path) -> list[Document]:
    """Load and split a single PDF into Documents."""
    try:
        loader = PyPDFLoader(str(path))
        pages = loader.load()
        chunks = TEXT_SPLITTER.split_documents(pages)
        logger.info("Loaded %d chunks from %s", len(chunks), path.name)
        return chunks
    except Exception as e:
        logger.error("Error loading PDF %s: %s", path, e)
        return []


def load_amazon_documents() -> list[Document]:
    """Download (or load locally) Amazon financial PDFs and return chunked Documents.

    For each configured PDF:
    1. Try to download from the public URL.
    2. If download fails, look for the file in docs/documents/.
    3. Split into chunks with RecursiveCharacterTextSplitter.

    Returns:
        List of LangChain Document objects ready for embedding.
    """
    all_chunks: list[Document] = []

    for entry in AMAZON_PDF_URLS:
        local_path = DOCS_DIR / entry["filename"]

        # Try download if we don't already have it locally
        if not local_path.exists():
            _download_pdf(entry["url"], local_path)

        if local_path.exists():
            chunks = _load_single_pdf(local_path)
            all_chunks.extend(chunks)
        else:
            logger.warning(
                "Skipping %s — not available online or locally.", entry["filename"]
            )

    logger.info("Total document chunks loaded: %d", len(all_chunks))
    return all_chunks
