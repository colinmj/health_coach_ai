"""CLI tool to ingest exercise form reference documents into the knowledge base.

Wraps sync/documents.py to use a namespaced document_name convention so that
sync/form_analysis.py can find them at analysis time.

Usage:
    python -m sync.seed_form_standards https://example.com/squat-guide barbell_squat
    python -m sync.seed_form_standards /path/to/deadlift_guide.pdf deadlift

Supported exercise keys:
    barbell_squat, deadlift, bench_press, overhead_press
"""

import sys

from dotenv import load_dotenv

from sync.documents import _chunk_text, _fetch_pdf, _fetch_web, _upsert_chunks
from sync.form_analysis import SUPPORTED_EXERCISES

load_dotenv()


def main() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage:\n"
            "  python -m sync.seed_form_standards <url_or_pdf_path> <exercise_name>\n\n"
            f"Supported exercise keys: {', '.join(sorted(SUPPORTED_EXERCISES))}",
            file=sys.stderr,
        )
        sys.exit(1)

    source = sys.argv[1]
    exercise_name = sys.argv[2].lower().strip()

    if exercise_name not in SUPPORTED_EXERCISES:
        print(
            f"ERROR: '{exercise_name}' is not a supported exercise key.\n"
            f"Supported: {', '.join(sorted(SUPPORTED_EXERCISES))}",
            file=sys.stderr,
        )
        sys.exit(1)

    document_name = f"form_standards_{exercise_name}"
    is_url = source.startswith("http://") or source.startswith("https://")

    print(f"Ingesting {'URL' if is_url else 'PDF'}: {source}")
    print(f"Document name: {document_name!r}")

    if is_url:
        text = _fetch_web(source)
        source_url: str | None = source
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
        user_id=None,  # global — shared across all users
    )
    print(f"Done. {count} chunks upserted for {document_name!r}.")


if __name__ == "__main__":
    main()
