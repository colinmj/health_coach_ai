"""CLI ingest script for the RAG knowledge base.

Usage:
    python -m sync.documents path/to/file.pdf "Document Name"
    python -m sync.documents https://example.com/article "Article Name"

Auto-detects source type: URLs (http/https) are fetched and parsed as HTML;
everything else is treated as a local PDF file.
"""

import re
import sys
import warnings
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from db.schema import get_connection

load_dotenv()

# ---------------------------------------------------------------------------
# Chunking constants
# ---------------------------------------------------------------------------

CHUNK_WORDS = 400
OVERLAP_WORDS = 50


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _fetch_web(url: str) -> str:
    """Fetch a URL and extract readable body text."""
    response = httpx.get(
        url,
        follow_redirects=True,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (compatible; HealthCoachBot/1.0)"},
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove non-content tags
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    # Extract from most-specific to least-specific container
    container = soup.find("article") or soup.find("main") or soup.find("body")
    raw = container.get_text(separator="\n") if container else soup.get_text(separator="\n")

    # Collapse whitespace
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def _fetch_pdf(path: str) -> str:
    """Extract text from a PDF file page-by-page."""
    from pypdf import PdfReader  # local import — only required when processing PDFs

    reader = PdfReader(path)
    pages: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
            pages.append(text)
        except Exception as exc:
            warnings.warn(f"Skipping page {i} (corrupt or unreadable): {exc}")

    full_text = "\n\n".join(pages).strip()
    if not full_text:
        print("ERROR: No text extracted. This may be an image-based PDF.", file=sys.stderr)
        sys.exit(1)

    return full_text


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------

def _chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks of ~CHUNK_WORDS words.

    Algorithm:
    1. Split on blank lines to get paragraphs.
    2. Accumulate paragraphs until ~CHUNK_WORDS words, then flush.
    3. Paragraphs that exceed CHUNK_WORDS alone are hard-split with overlap.
    4. Last OVERLAP_WORDS words of each flushed chunk seed the next one.
    5. Deduplicate by 200-char prefix (removes repeated headers/footers).
    6. Drop fragments shorter than 10 words.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    overlap_seed: list[str] = []  # last OVERLAP_WORDS words from previous chunk

    def _flush(word_buf: list[str]) -> None:
        joined = " ".join(word_buf).strip()
        if joined:
            chunks.append(joined)

    current_words: list[str] = list(overlap_seed)

    for para in paragraphs:
        para_words = para.split()

        # Hard-split paragraphs that alone exceed the chunk size
        if len(para_words) > CHUNK_WORDS:
            # Flush whatever we have accumulated first
            if current_words:
                _flush(current_words)
                overlap_seed = current_words[-OVERLAP_WORDS:]
                current_words = list(overlap_seed)

            start = 0
            while start < len(para_words):
                slice_words = para_words[start : start + CHUNK_WORDS]
                _flush(slice_words)
                overlap_seed = slice_words[-OVERLAP_WORDS:]
                current_words = list(overlap_seed)
                start += CHUNK_WORDS
            continue

        # Normal accumulation
        if len(current_words) + len(para_words) >= CHUNK_WORDS:
            _flush(current_words)
            overlap_seed = current_words[-OVERLAP_WORDS:]
            current_words = list(overlap_seed) + para_words
        else:
            current_words.extend(para_words)

    # Flush remainder
    if current_words:
        _flush(current_words)

    # Deduplicate by 200-char prefix
    seen_prefixes: set[str] = set()
    deduped: list[str] = []
    for chunk in chunks:
        prefix = chunk[:200]
        if prefix not in seen_prefixes:
            seen_prefixes.add(prefix)
            deduped.append(chunk)

    # Drop fragments shorter than 10 words
    return [c for c in deduped if len(c.split()) >= 10]


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

def _upsert_chunks(
    document_name: str,
    chunks: list[str],
    source_url: Optional[str],
    user_id: Optional[int],
) -> int:
    """Insert or update document chunks in the database. Returns the chunk count."""
    sql = """
        INSERT INTO document_chunks (user_id, document_name, source_url, chunk_index, content)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (document_name, chunk_index) DO UPDATE
            SET content = EXCLUDED.content,
                source_url = EXCLUDED.source_url,
                created_at = NOW()
    """
    with get_connection() as conn:
        for idx, chunk in enumerate(chunks):
            conn.execute(sql, (user_id, document_name, source_url, idx, chunk))
    return len(chunks)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage:\n"
            "  python -m sync.documents path/to/file.pdf \"Document Name\"\n"
            "  python -m sync.documents https://example.com/article \"Article Name\"",
            file=sys.stderr,
        )
        sys.exit(1)

    source = sys.argv[1]
    document_name = sys.argv[2]

    is_url = source.startswith("http://") or source.startswith("https://")

    print(f"Ingesting {'URL' if is_url else 'PDF'}: {source}")

    if is_url:
        text = _fetch_web(source)
        source_url: Optional[str] = source
    else:
        text = _fetch_pdf(source)
        source_url = None

    chunks = _chunk_text(text)
    if not chunks:
        print("ERROR: No usable chunks extracted from source.", file=sys.stderr)
        sys.exit(1)

    count = _upsert_chunks(
        document_name=document_name,
        chunks=chunks,
        source_url=source_url,
        user_id=None,  # global document
    )
    print(f"Done. {count} chunks upserted for \"{document_name}\".")


if __name__ == "__main__":
    main()
